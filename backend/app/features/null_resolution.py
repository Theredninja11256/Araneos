"""
Feature: Cross-Dataset Null Resolution

For each ordered pair of datasets uploaded in the same session:

  1. Identify candidate join keys — columns that appear in both datasets,
     are of 'identifier' type, have high uniqueness, and low null rates.

  2. Identify fillable columns — shared columns (excluding join key,
     identifier columns, and excluded column names) where the target
     dataset has nulls and the source dataset has non-null values.

  3. Perform a pandas lookup for each null row using the join key.
     Emit a proposal for every successful match.

Notes on engine usage
---------------------
This module uses engine.load_csv() to load datasets through the configured
engine.  The join/lookup logic itself uses pandas DataFrames directly because
the pandas engine is the MVP default and the abstraction of multi-dataset
joins would require engine.join_on_key() — a method intentionally deferred
to a later stage to avoid over-engineering.

For Spark mode: load_csv() returns a Spark DataFrame; convert to pandas via
.toPandas() before the lookup.  This is acceptable for the small datasets
in scope for this MVP.

Public API
----------
find_cross_dataset_fills(uploaded_datasets, session_id) -> list[dict]
"""

from __future__ import annotations

import pandas as pd

from app.core.insurance_fields import (
    CROSS_DATASET_FILL_EXCLUSIONS,
    CROSS_FILL_CONFIDENCE_PRIMARY,
    CROSS_FILL_CONFIDENCE_SECONDARY,
    JOIN_KEY_MAX_NULL_PCT,
    JOIN_KEY_MIN_UNIQUENESS,
    JOIN_KEY_PRIMARY_UNIQUENESS_THRESHOLD,
    PREFERRED_JOIN_KEYS,
)
from app.engines.engine_selector import get_engine
from app.features.proposals import build_proposal


def find_cross_dataset_fills(
    uploaded_datasets: list[dict],
    session_id: str,
) -> list[dict]:
    """
    Generate cross-dataset null-fill proposals for all uploaded datasets.

    Args
    ----
    uploaded_datasets : list of dicts, each containing:
        file_path    : str   — path to the saved file
        display_name : str   — original filename shown to the analyst
        profile      : dict  — Stage 2 DatasetProfile

    Returns
    -------
    list of standardised proposal dicts (all status='pending').
    """
    if len(uploaded_datasets) < 2:
        return []

    engine = get_engine()

    # Load all datasets into pandas DataFrames.
    # SparkSession is started lazily so this is cheap in pandas mode.
    loaded: dict[str, dict] = {}
    for ds in uploaded_datasets:
        raw_df = engine.load_csv(ds["file_path"])

        # Normalise to pandas if the engine returned a Spark DataFrame.
        if hasattr(raw_df, "toPandas"):
            df = raw_df.toPandas()
        else:
            df = raw_df

        loaded[ds["display_name"]] = {
            "df": df,
            "profile": ds["profile"],
        }

    proposals: list[dict] = []
    names = list(loaded.keys())

    # Check every ordered pair (A, B) — A is the dataset with nulls,
    # B is the source dataset used to fill them.
    for i, name_a in enumerate(names):
        for j, name_b in enumerate(names):
            if i == j:
                continue

            df_a = loaded[name_a]["df"]
            df_b = loaded[name_b]["df"]
            profile_a = loaded[name_a]["profile"]
            profile_b = loaded[name_b]["profile"]

            join_keys = _find_join_keys(profile_a, profile_b)
            if not join_keys:
                continue

            join_key = _select_best_join_key(join_keys, profile_a, profile_b)
            fillable_cols = _find_fillable_columns(profile_a, profile_b, join_key)

            for col in fillable_cols:
                batch = _generate_fill_proposals(
                    df_a=df_a,
                    df_b=df_b,
                    name_a=name_a,
                    name_b=name_b,
                    join_key=join_key,
                    col=col,
                    session_id=session_id,
                    profile_a=profile_a,
                    profile_b=profile_b,
                )
                proposals.extend(batch)

    return proposals


# ── Join-key helpers ───────────────────────────────────────────────────────

def _find_join_keys(profile_a: dict, profile_b: dict) -> list[str]:
    """
    Return columns that are valid join keys between the two datasets.

    Criteria:
    - Column name appears in both datasets.
    - 'identifier' inferred type in at least one dataset.
    - uniqueness_ratio >= 0.80 in both datasets.
    - null_pct < 0.10 in both datasets.
    """
    cols_a = {c["name"]: c for c in profile_a["columns"]}
    cols_b = {c["name"]: c for c in profile_b["columns"]}
    common = set(cols_a) & set(cols_b)

    keys: list[str] = []
    for col in common:
        ca = cols_a[col]
        cb = cols_b[col]

        is_identifier = (
            ca["inferred_type"] == "identifier" or cb["inferred_type"] == "identifier"
        )
        high_uniqueness = (
            ca["uniqueness_ratio"] >= JOIN_KEY_MIN_UNIQUENESS
            and cb["uniqueness_ratio"] >= JOIN_KEY_MIN_UNIQUENESS
        )
        low_nulls = (
            ca["null_pct"] < JOIN_KEY_MAX_NULL_PCT
            and cb["null_pct"] < JOIN_KEY_MAX_NULL_PCT
        )

        if is_identifier and high_uniqueness and low_nulls:
            keys.append(col)

    return keys


def _select_best_join_key(
    join_keys: list[str],
    profile_a: dict,
    profile_b: dict,
) -> str:
    """
    Pick the best join key, preferring policy-level identifiers over
    customer-level ones (a customer can have multiple policies, making
    customer_id an unreliable fill key).  Among keys of the same
    preference tier, choose by highest uniqueness and lowest null rate.
    """
    cols_a = {c["name"]: c for c in profile_a["columns"]}
    cols_b = {c["name"]: c for c in profile_b["columns"]}

    def score(key: str) -> tuple[int, float]:
        # Prefer named policy-level keys (tier 0) over others (tier 1).
        preference_tier = 0 if key in PREFERRED_JOIN_KEYS else 1
        ca, cb = cols_a[key], cols_b[key]
        avg_uniqueness = (ca["uniqueness_ratio"] + cb["uniqueness_ratio"]) / 2
        avg_null_penalty = (ca["null_pct"] + cb["null_pct"]) / 2
        quality = avg_uniqueness - avg_null_penalty
        # Lower tier is better; higher quality is better.
        return (-preference_tier, quality)

    return max(join_keys, key=score)


def _confidence_for_key(
    join_key: str,
    profile_a: dict,
    profile_b: dict,
) -> float:
    """
    Return 0.90 if the join key behaves like a true primary key in both datasets
    (near-unique, very low nulls).  Otherwise 0.75.
    """
    cols_a = {c["name"]: c for c in profile_a["columns"]}
    cols_b = {c["name"]: c for c in profile_b["columns"]}
    ca, cb = cols_a[join_key], cols_b[join_key]

    is_primary = (
        ca["uniqueness_ratio"] >= JOIN_KEY_PRIMARY_UNIQUENESS_THRESHOLD
        and cb["uniqueness_ratio"] >= JOIN_KEY_PRIMARY_UNIQUENESS_THRESHOLD
    )
    return CROSS_FILL_CONFIDENCE_PRIMARY if is_primary else CROSS_FILL_CONFIDENCE_SECONDARY


# ── Column selection ───────────────────────────────────────────────────────

def _find_fillable_columns(
    profile_a: dict,
    profile_b: dict,
    join_key: str,
) -> list[str]:
    """
    Return columns that satisfy all fill conditions:
    - Shared name between A and B.
    - Not the join key itself.
    - Not in the exclusion list.
    - Not identifier type (we don't fill identifiers).
    - Has at least one null in A.
    - Has at least one non-null value in B.
    - Same inferred type in A and B (prevents filling premium with a date, etc.).
    """
    cols_a = {c["name"]: c for c in profile_a["columns"]}
    cols_b = {c["name"]: c for c in profile_b["columns"]}
    common = set(cols_a) & set(cols_b)

    fillable: list[str] = []
    for col in common:
        if col == join_key:
            continue
        if col in CROSS_DATASET_FILL_EXCLUSIONS:
            continue

        ca, cb = cols_a[col], cols_b[col]

        if ca["inferred_type"] == "identifier":
            continue
        if ca["inferred_type"] != cb["inferred_type"]:
            continue
        if ca["null_count"] == 0:
            continue
        non_null_in_b = cb["row_count"] - cb["null_count"] if "row_count" in cb else (
            profile_b["row_count"] - cb["null_count"]
        )
        if non_null_in_b == 0:
            continue

        fillable.append(col)

    return fillable


# ── Proposal generation ────────────────────────────────────────────────────

def _generate_fill_proposals(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    name_a: str,
    name_b: str,
    join_key: str,
    col: str,
    session_id: str,
    profile_a: dict,
    profile_b: dict,
) -> list[dict]:
    """
    For each row in df_a where `col` is null, look up the value in df_b using
    `join_key`.  Return a proposal for every successful lookup.
    """
    proposals: list[dict] = []
    confidence = _confidence_for_key(join_key, profile_a, profile_b)

    # Rows in df_a that: (a) have null in the target column, (b) have a non-null join key.
    null_mask = df_a[col].isnull() & df_a[join_key].notna()
    null_rows = df_a[null_mask]

    if null_rows.empty:
        return []

    # Build a lookup table from df_b: join_key → col value (first non-null per key).
    lookup_df = (
        df_b[[join_key, col]]
        .dropna(subset=[col])
        .drop_duplicates(subset=[join_key], keep="first")
        .set_index(join_key)
    )

    for idx, row in null_rows.iterrows():
        key_val = row[join_key]

        if key_val not in lookup_df.index:
            continue

        src_val = lookup_df.loc[key_val, col]

        # Format numeric proposals cleanly (avoid "580.0" vs "580").
        if isinstance(src_val, float) and src_val == int(src_val):
            proposed_str = str(int(src_val))
        else:
            proposed_str = str(src_val)

        proposals.append(
            build_proposal(
                session_id=session_id,
                proposal_type="cross_dataset_fill",
                source_method="cross_dataset_lookup",
                dataset_name=name_a,
                row_index=int(idx),
                row_identifier=str(key_val),
                column_name=col,
                original_value=None,
                proposed_value=proposed_str,
                explanation=(
                    f"Value '{proposed_str}' found in '{name_b}' for "
                    f"{join_key} = '{key_val}'. "
                    f"Source column: '{col}' (same name, same type)."
                ),
                confidence=confidence,
                source_dataset=name_b,
                source_column=col,
                join_key=join_key,
                join_value=str(key_val),
            )
        )

    return proposals
