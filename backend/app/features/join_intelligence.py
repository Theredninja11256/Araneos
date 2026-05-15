"""
Feature: Join Intelligence

Analyses all datasets uploaded in a session to:
  1. Detect joinable dataset pairs and compute match quality metrics
  2. Generate rule-based insight suggestions based on available column combinations
  3. Execute simple aggregation tables for selected insights

This module operates purely on uploaded CSV files (via the UploadSession table)
and uses pandas only — no ML, no dynamic SQL, no LLMs.

Public API
----------
analyse_joins_for_session(session_id, db) -> dict
    Detects all joinable pairs and matching insights.
    Raises JoinError(404) if the session is not found.

generate_insight_table(session_id, dataset_a, dataset_b, join_key, insight_id, db) -> dict
    Runs the aggregation for a specific insight and returns table data.
    Raises JoinError on lookup or computation failure.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sqlalchemy.orm import Session

from app.core.insurance_fields import PREFERRED_JOIN_KEYS


# ── Exceptions ────────────────────────────────────────────────────────────────

class JoinError(Exception):
    """Raised by public functions on recoverable failures."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum fraction of non-null values that must be unique for a column to
# qualify as a join key.  Prevents low-cardinality columns (status, product_type)
# from being mistaken for identifiers.
_MIN_UNIQUENESS: float = 0.40

# Column names that are strong join-key candidates regardless of uniqueness.
# Built from the shared config list plus extra common identifiers.
_KEY_COLUMN_NAMES: frozenset[str] = frozenset(PREFERRED_JOIN_KEYS) | frozenset({
    "customer_id",
    "client_id",
    "policyholder_id",
    "risk_id",
    "endorsement_id",
})


# ── Insight rules ─────────────────────────────────────────────────────────────
#
# Each rule contains:
#   id               : str           unique identifier used in API calls
#   name             : str           short display name
#   explanation      : str           plain-English description for the analyst
#   required_columns : set[str]      lowercase column names that must exist
#   confidence       : str           High | Medium | Low
#   cross_dataset    : bool          True = needs a join; False = single-dataset
#
# For cross_dataset=True: the required_columns must be spread across the two
# merged datasets (the merged column union is checked).
# For cross_dataset=False: all required_columns must be in the same dataset.

INSIGHT_RULES: list[dict] = [
    # ── Cross-dataset (require a join) ──────────────────────────────────────
    {
        "id": "avg_claim_by_ncd",
        "name": "Average claim amount by NCD band",
        "explanation": (
            "Join policies and claims on the shared key, then group by NCD tier. "
            "Reveals whether higher no-claims discount bands genuinely produce lower "
            "claim costs — a key check for pricing fairness and reserving assumptions."
        ),
        "required_columns": {"ncd", "claim_amount"},
        "confidence": "High",
        "cross_dataset": True,
    },
    {
        "id": "claim_freq_by_product",
        "name": "Claim frequency by product type",
        "explanation": (
            "Counts claims per product type (e.g. Motor vs Home) after joining on "
            "the shared policy key. Highlights which products are generating the most "
            "loss events and could indicate mis-pricing or selection effects."
        ),
        "required_columns": {"product_type", "claim_amount"},
        "confidence": "High",
        "cross_dataset": True,
    },
    {
        "id": "claim_by_postcode",
        "name": "Claim volume by postcode area",
        "explanation": (
            "Groups claims by the policyholder's postcode to reveal geographic "
            "hotspots for losses. Compare with premium by postcode to identify "
            "territories where the book may be under-priced."
        ),
        "required_columns": {"postcode", "claim_amount"},
        "confidence": "Medium",
        "cross_dataset": True,
    },
    # ── Single-dataset ──────────────────────────────────────────────────────
    {
        "id": "premium_by_postcode",
        "name": "Average premium by postcode",
        "explanation": (
            "Groups written premium by postcode to show geographic pricing variation. "
            "Useful as a standalone check before comparing with claim costs by region."
        ),
        "required_columns": {"premium", "postcode"},
        "confidence": "High",
        "cross_dataset": False,
    },
    {
        "id": "policy_by_product",
        "name": "Policy count by product type",
        "explanation": (
            "Shows the split of your book across product types. A quick measure of "
            "book composition and concentration risk — high concentration in one "
            "product warrants closer scrutiny."
        ),
        "required_columns": {"product_type"},
        "confidence": "High",
        "cross_dataset": False,
    },
    {
        "id": "avg_premium_by_ncd",
        "name": "Average premium by NCD band",
        "explanation": (
            "Compares average written premium across NCD tiers. Checks that NCD "
            "discounts are being applied consistently and at appropriate levels "
            "relative to expected claim frequency."
        ),
        "required_columns": {"premium", "ncd"},
        "confidence": "High",
        "cross_dataset": False,
    },
    {
        "id": "claims_by_type",
        "name": "Claim distribution by type",
        "explanation": (
            "Counts claims by peril type (e.g. theft, accident, weather). Shows "
            "which claim categories are most prevalent and may need separate "
            "rating factors or reserving treatment."
        ),
        "required_columns": {"claim_type"},
        "confidence": "High",
        "cross_dataset": False,
    },
    {
        "id": "avg_claim_by_type",
        "name": "Average claim cost by type",
        "explanation": (
            "Shows the average claim cost for each peril type. High-severity but "
            "low-frequency perils (e.g. flood) may warrant separate rating or "
            "reinsurance protection."
        ),
        "required_columns": {"claim_amount", "claim_type"},
        "confidence": "High",
        "cross_dataset": False,
    },
]


# ── Main entry points ─────────────────────────────────────────────────────────

def analyse_joins_for_session(session_id: str, db: Session) -> dict:
    """
    Detect joinable dataset pairs and generate insight suggestions.

    Returns
    -------
    dict with:
        session_id              : str
        join_reports            : list[dict]  — one per detected dataset pair
        single_dataset_insights : list[dict]  — insights from individual datasets
    """
    file_map = _get_session_files(session_id, db)
    if not file_map:
        raise JoinError(
            404,
            f"Session '{session_id}' not found or has no uploaded datasets. "
            "Upload datasets first, then explore joins.",
        )

    # Load all DataFrames (we need full data for uniqueness ratios and key sets)
    dfs: dict[str, pd.DataFrame] = {}
    for name, path in file_map.items():
        if not Path(path).exists():
            print(f"[join_intelligence] Skipping '{name}': file not found at '{path}'.")
            continue
        try:
            dfs[name] = pd.read_csv(path)
        except Exception as exc:
            print(f"[join_intelligence] Failed to load '{name}': {exc}")

    if not dfs:
        raise JoinError(400, "No dataset files could be loaded for this session.")

    # Detect pairwise join reports
    join_reports = _detect_join_pairs(dfs)

    # Single-dataset insights
    single_insights = []
    for name, df in dfs.items():
        cols_lower = {c.lower() for c in df.columns}
        insights = _match_single_dataset_rules(cols_lower)
        if insights:
            single_insights.append({"dataset": name, "insights": insights})

    return {
        "session_id": session_id,
        "join_reports": join_reports,
        "single_dataset_insights": single_insights,
    }


def generate_insight_table(
    session_id: str,
    dataset_a: str,
    dataset_b: str | None,
    join_key: str | None,
    insight_id: str,
    db: Session,
) -> dict:
    """
    Run the aggregation for a specific insight and return table data.

    For cross-dataset insights, dataset_b and join_key must be provided.
    For single-dataset insights, only dataset_a is needed.
    """
    file_map = _get_session_files(session_id, db)
    if not file_map:
        raise JoinError(404, f"Session '{session_id}' not found.")

    rule = next((r for r in INSIGHT_RULES if r["id"] == insight_id), None)
    if rule is None:
        raise JoinError(400, f"Unknown insight_id '{insight_id}'.")

    generator = _GENERATORS.get(insight_id)
    if generator is None:
        raise JoinError(400, f"No generator implemented for insight '{insight_id}'.")

    df_a = _load_dataset(dataset_a, file_map)

    if rule["cross_dataset"]:
        if not dataset_b or not join_key:
            raise JoinError(
                400, "Cross-dataset insights require dataset_b and join_key."
            )
        df_b = _load_dataset(dataset_b, file_map)
        # Merge with suffixes so name conflicts are handled gracefully.
        # The join key itself is not duplicated (it's in both but merged cleanly).
        df_work = df_a.merge(
            df_b, on=join_key, how="inner", suffixes=("", "_joined")
        )
    else:
        df_work = df_a

    try:
        result_df = generator(df_work)
    except KeyError as exc:
        raise JoinError(400, f"Required column not found: {exc}") from exc
    except Exception as exc:
        raise JoinError(500, f"Insight computation failed: {exc}") from exc

    # Replace NaN with None for clean JSON serialisation
    result_df = result_df.where(pd.notnull(result_df), None)
    rows = result_df.to_dict(orient="records")

    return {
        "insight_id": insight_id,
        "insight_name": rule["name"],
        "row_count": len(rows),
        "columns": list(result_df.columns),
        "rows": rows,
    }


# ── Join detection ────────────────────────────────────────────────────────────

def _detect_join_pairs(dfs: dict[str, pd.DataFrame]) -> list[dict]:
    """
    For every pair of datasets, find the best join key and compute quality.
    Returns only pairs where a usable join key was found.
    """
    reports = []
    for name_a, name_b in combinations(dfs.keys(), 2):
        df_a = dfs[name_a]
        df_b = dfs[name_b]

        shared_cols = set(df_a.columns) & set(df_b.columns)

        # Filter to columns that look like identifiers: either a known key name
        # or high uniqueness in at least one of the datasets.
        candidates = [
            c for c in shared_cols
            if c.lower() in _KEY_COLUMN_NAMES
            or _uniqueness_ratio(df_a, c) >= _MIN_UNIQUENESS
            or _uniqueness_ratio(df_b, c) >= _MIN_UNIQUENESS
        ]

        if not candidates:
            continue

        # Sort: known preferred keys first, then alphabetical
        candidates.sort(key=lambda c: (0 if c.lower() in _KEY_COLUMN_NAMES else 1, c))
        best_key = candidates[0]

        quality = _compute_join_quality(df_a, df_b, best_key)

        # Discover relevant insights for the merged column union
        all_cols_lower = {c.lower() for c in (set(df_a.columns) | set(df_b.columns))}
        insights = _match_cross_dataset_rules(all_cols_lower)

        reports.append(
            {
                "id": f"{Path(name_a).stem}_{Path(name_b).stem}",
                "dataset_a": name_a,
                "dataset_b": name_b,
                "join_key": best_key,
                "match_rate": quality["match_rate"],
                "matched_keys": quality["matched_keys"],
                "total_keys_a": quality["total_keys_a"],
                "total_keys_b": quality["total_keys_b"],
                "unmatched_in_a": quality["unmatched_in_a"],
                "unmatched_in_b": quality["unmatched_in_b"],
                "base_dataset": (
                    name_a
                    if quality["total_keys_a"] >= quality["total_keys_b"]
                    else name_b
                ),
                "insights": insights,
            }
        )

    return reports


def _compute_join_quality(
    df_a: pd.DataFrame, df_b: pd.DataFrame, key: str
) -> dict:
    keys_a = set(df_a[key].dropna().astype(str))
    keys_b = set(df_b[key].dropna().astype(str))
    matched = keys_a & keys_b
    # Use the larger set as the denominator for match rate
    denominator = max(len(keys_a), len(keys_b), 1)
    return {
        "match_rate": round(len(matched) / denominator, 3),
        "matched_keys": len(matched),
        "total_keys_a": len(keys_a),
        "total_keys_b": len(keys_b),
        "unmatched_in_a": len(keys_a - keys_b),
        "unmatched_in_b": len(keys_b - keys_a),
    }


def _uniqueness_ratio(df: pd.DataFrame, col: str) -> float:
    n = len(df)
    return df[col].nunique() / n if n > 0 else 0.0


# ── Insight matching ──────────────────────────────────────────────────────────

def _match_cross_dataset_rules(cols_lower: set[str]) -> list[dict]:
    return [
        _rule_to_insight(r)
        for r in INSIGHT_RULES
        if r["cross_dataset"] and r["required_columns"].issubset(cols_lower)
    ]


def _match_single_dataset_rules(cols_lower: set[str]) -> list[dict]:
    return [
        _rule_to_insight(r)
        for r in INSIGHT_RULES
        if not r["cross_dataset"] and r["required_columns"].issubset(cols_lower)
    ]


def _rule_to_insight(rule: dict) -> dict:
    return {
        "id": rule["id"],
        "name": rule["name"],
        "explanation": rule["explanation"],
        "columns_used": sorted(rule["required_columns"]),
        "confidence": rule["confidence"],
        "cross_dataset": rule["cross_dataset"],
    }


# ── Insight generators ────────────────────────────────────────────────────────

def _find_col(df: pd.DataFrame, name: str) -> str:
    """
    Locate a column by exact name, accounting for merge suffixes (_joined, _x, _y).
    Raises KeyError if the column cannot be found under any expected name.
    """
    for candidate in [name, f"{name}_joined", f"{name}_x", f"{name}_y"]:
        if candidate in df.columns:
            return candidate
    raise KeyError(
        f"'{name}' (checked suffixed variants too). "
        f"Available columns: {list(df.columns)[:15]}"
    )


def _gen_avg_claim_by_ncd(df: pd.DataFrame) -> pd.DataFrame:
    ncd = _find_col(df, "ncd")
    amt = _find_col(df, "claim_amount")
    return (
        df.groupby(ncd)[amt]
        .agg(avg_claim_amount="mean", claim_count="count")
        .reset_index()
        .rename(columns={ncd: "ncd"})
        .sort_values("ncd")
        .round({"avg_claim_amount": 2})
    )


def _gen_claim_freq_by_product(df: pd.DataFrame) -> pd.DataFrame:
    prod = _find_col(df, "product_type")
    amt = _find_col(df, "claim_amount")
    return (
        df.groupby(prod)[amt]
        .agg(claim_count="count", total_claim_amount="sum")
        .reset_index()
        .rename(columns={prod: "product_type"})
        .sort_values("claim_count", ascending=False)
        .round({"total_claim_amount": 2})
    )


def _gen_claim_by_postcode(df: pd.DataFrame) -> pd.DataFrame:
    pc = _find_col(df, "postcode")
    amt = _find_col(df, "claim_amount")
    return (
        df.groupby(pc)[amt]
        .agg(claim_count="count", avg_claim_amount="mean")
        .reset_index()
        .rename(columns={pc: "postcode"})
        .sort_values("claim_count", ascending=False)
        .round({"avg_claim_amount": 2})
    )


def _gen_premium_by_postcode(df: pd.DataFrame) -> pd.DataFrame:
    pc = _find_col(df, "postcode")
    prem = _find_col(df, "premium")
    return (
        df.groupby(pc)[prem]
        .agg(avg_premium="mean", policy_count="count")
        .reset_index()
        .rename(columns={pc: "postcode"})
        .sort_values("avg_premium", ascending=False)
        .round({"avg_premium": 2})
    )


def _gen_policy_by_product(df: pd.DataFrame) -> pd.DataFrame:
    prod = _find_col(df, "product_type")
    return (
        df.groupby(prod)
        .size()
        .reset_index(name="policy_count")
        .rename(columns={prod: "product_type"})
        .sort_values("policy_count", ascending=False)
    )


def _gen_avg_premium_by_ncd(df: pd.DataFrame) -> pd.DataFrame:
    ncd = _find_col(df, "ncd")
    prem = _find_col(df, "premium")
    return (
        df.groupby(ncd)[prem]
        .agg(avg_premium="mean", policy_count="count")
        .reset_index()
        .rename(columns={ncd: "ncd"})
        .sort_values("ncd")
        .round({"avg_premium": 2})
    )


def _gen_claims_by_type(df: pd.DataFrame) -> pd.DataFrame:
    ct = _find_col(df, "claim_type")
    return (
        df.groupby(ct)
        .size()
        .reset_index(name="claim_count")
        .rename(columns={ct: "claim_type"})
        .sort_values("claim_count", ascending=False)
    )


def _gen_avg_claim_by_type(df: pd.DataFrame) -> pd.DataFrame:
    ct = _find_col(df, "claim_type")
    amt = _find_col(df, "claim_amount")
    return (
        df.groupby(ct)[amt]
        .agg(avg_claim_amount="mean", claim_count="count")
        .reset_index()
        .rename(columns={ct: "claim_type"})
        .sort_values("avg_claim_amount", ascending=False)
        .round({"avg_claim_amount": 2})
    )


# Dispatch table: insight_id → generator function
_GENERATORS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "avg_claim_by_ncd":      _gen_avg_claim_by_ncd,
    "claim_freq_by_product": _gen_claim_freq_by_product,
    "claim_by_postcode":     _gen_claim_by_postcode,
    "premium_by_postcode":   _gen_premium_by_postcode,
    "policy_by_product":     _gen_policy_by_product,
    "avg_premium_by_ncd":    _gen_avg_premium_by_ncd,
    "claims_by_type":        _gen_claims_by_type,
    "avg_claim_by_type":     _gen_avg_claim_by_type,
}


# ── Data access ───────────────────────────────────────────────────────────────

def _get_session_files(session_id: str, db: Session) -> dict[str, str]:
    from app.models.upload_session import UploadSession
    rows = (
        db.query(UploadSession)
        .filter(UploadSession.session_id == session_id)
        .all()
    )
    return {r.dataset_name: r.file_path for r in rows}


def _load_dataset(name: str, file_map: dict[str, str]) -> pd.DataFrame:
    if name not in file_map:
        raise JoinError(404, f"Dataset '{name}' not found in session files.")
    path = file_map[name]
    if not Path(path).exists():
        raise JoinError(404, f"File for '{name}' not found on disk.")
    return pd.read_csv(path)
