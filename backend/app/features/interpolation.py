"""
Feature: Conservative Sequence Interpolation

Rules implemented for MVP.  Both are intentionally strict — the system
proposes a value only when the inference is structurally clear and the
explanation is unambiguous.

Rule 1 — Annual policy date inference
--------------------------------------
For datasets that have both 'inception_date' and 'expiry_date' columns:
if one column is null and the other is present and parseable as a date, and
the majority of other rows confirm an annual (365-366 day) term, propose
filling the null with inception ± 1 year.

Confidence: DATE_INFERENCE_CONFIDENCE (default 0.75).

Rule 2 — Sequential identifier inference
-----------------------------------------
Applies only to identifier columns (policy_id, policy_number, etc.) when the
dataset also has a clear time-ordering column (timestamp, created_at, etc.).

After sorting rows by the ordering column, if exactly one null exists between
two consecutive IDs whose numeric parts differ by exactly 2 (i.e. one missing
value in the sequence), and the prefix and zero-padding match, the system
proposes the missing ID.

Example: POL-00001 → NULL → POL-00003  ⟹  propose POL-00002

Conditions (all must be true):
  - A column with inferred_type == 'identifier' has at least one null.
  - A timestamp/ordering column is present in the dataset.
  - After sorting by the ordering column, the null is at position i where
    row i-1 and row i+1 are both non-null identifiers.
  - Both surrounding IDs share the same prefix and zero-padding width.
  - prev_num + 2 == next_num  (exactly one missing in the numeric sequence).
  - The timestamp at position i is non-null and lies between the timestamps
    at positions i-1 and i+1.

Confidence: SEQUENTIAL_ID_CONFIDENCE (default 0.65 — medium, not high).

NOTE: The arithmetic gap-fill rule (filling nulls in general numeric columns
such as ncd, premium, or claim_amount by interpolating between adjacent rows)
has been removed.  In row-per-policy insurance data, consecutive rows
represent independent entities; adjacent-row arithmetic inference is
semantically invalid for those columns.

Public API
----------
find_interpolation_proposals(file_path, profile, session_id, display_name) -> list[dict]
"""

from __future__ import annotations

import re

import pandas as pd

from app.core.insurance_fields import (
    ANNUAL_DATE_PAIRS,
    DATE_INFERENCE_CONFIDENCE,
    DATE_INFERENCE_MIN_ANNUAL_RATIO,
    DATE_INFERENCE_MIN_SAMPLE_ROWS,
    SEQUENTIAL_ID_CONFIDENCE,
    TIMESTAMP_COLUMN_KEYWORDS,
)
from app.engines.engine_selector import get_engine
from app.features.proposals import build_proposal

# Regex to split an identifier into (prefix, zero-padded numeric part).
# Matches strings like "POL-00001", "Q123", "CLM-0042", "000999".
_ID_RE = re.compile(r"^(.*?)(\d+)$")


def find_interpolation_proposals(
    file_path: str,
    profile: dict,
    session_id: str,
    display_name: str | None = None,
) -> list[dict]:
    """
    Scan a dataset for interpolation opportunities and return proposals.

    Args
    ----
    file_path    : str       — path to the saved CSV file
    profile      : dict      — Stage 2 DatasetProfile for this file
    session_id   : str       — ties proposals to the current upload session
    display_name : str|None  — original filename for proposal labels;
                               falls back to profile["file_name"] if omitted

    Returns
    -------
    list of standardised proposal dicts (may be empty).
    """
    engine = get_engine()
    raw_df = engine.load_csv(file_path)

    if hasattr(raw_df, "toPandas"):
        df = raw_df.toPandas()
    else:
        df = raw_df

    dataset_name = display_name or profile["file_name"]
    id_col       = _find_identifier_column(profile)

    proposals: list[dict] = []

    # Rule 1 — annual date inference
    proposals.extend(_annual_date_proposals(df, profile, dataset_name, session_id, id_col))

    # Rule 2 — sequential identifier inference
    proposals.extend(_sequential_id_proposals(df, profile, dataset_name, session_id, id_col))

    return proposals


# ── Rule 1: annual date inference ──────────────────────────────────────────

def _annual_date_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For each configured date pair (inception_date, expiry_date):
    if one is null and the other is a parseable date, and the dataset
    confirms most policies are annual, propose the missing date as ± 1 year.
    """
    proposals: list[dict] = []
    col_names = {c["name"] for c in profile["columns"]}

    for start_col, end_col in ANNUAL_DATE_PAIRS:
        if start_col not in col_names or end_col not in col_names:
            continue

        try:
            start_series = pd.to_datetime(df[start_col], errors="coerce")
            end_series   = pd.to_datetime(df[end_col],   errors="coerce")
        except Exception:
            continue

        both_present = start_series.notna() & end_series.notna()
        if both_present.sum() < DATE_INFERENCE_MIN_SAMPLE_ROWS:
            continue

        days = (end_series[both_present] - start_series[both_present]).dt.days
        annual_count = ((days >= 364) & (days <= 367)).sum()
        if annual_count / both_present.sum() < DATE_INFERENCE_MIN_ANNUAL_RATIO:
            continue

        for i in range(len(df)):
            s = start_series.iloc[i]
            e = end_series.iloc[i]
            row_id = str(df.iloc[i][id_col]) if id_col else None

            if pd.isna(e) and pd.notna(s):
                proposed_date = (s + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="interpolation",
                        source_method="date_inference",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=end_col,
                        original_value=None,
                        proposed_value=proposed_date,
                        explanation=(
                            f"'{start_col}' is {s.strftime('%Y-%m-%d')}. "
                            f"{annual_count}/{both_present.sum()} rows with both dates "
                            f"confirm an annual policy term (365–366 days). "
                            f"Proposed {end_col} = {proposed_date} (inception + 1 year). "
                            f"Verify for non-standard terms (e.g. short-term or multi-year)."
                        ),
                        confidence=DATE_INFERENCE_CONFIDENCE,
                    )
                )

            elif pd.isna(s) and pd.notna(e):
                proposed_date = (e - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="interpolation",
                        source_method="date_inference",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=start_col,
                        original_value=None,
                        proposed_value=proposed_date,
                        explanation=(
                            f"'{end_col}' is {e.strftime('%Y-%m-%d')}. "
                            f"{annual_count}/{both_present.sum()} rows with both dates "
                            f"confirm an annual policy term (365–366 days). "
                            f"Proposed {start_col} = {proposed_date} (expiry − 1 year). "
                            f"Verify for non-standard terms (e.g. short-term or multi-year)."
                        ),
                        confidence=DATE_INFERENCE_CONFIDENCE,
                    )
                )

    return proposals


# ── Rule 2: sequential identifier inference ────────────────────────────────

def _sequential_id_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For identifier columns that have nulls: if the dataset has a timestamp
    ordering column, sort by it and look for exactly one null between two
    consecutive IDs whose numeric parts differ by exactly 2.  Propose the
    missing intermediate ID.

    This rule is about structural ordering of records (e.g. sequentially
    generated policy numbers), NOT about inferring customer behaviour or
    financial values.

    Confidence is medium (SEQUENTIAL_ID_CONFIDENCE) because ordering provides
    structural evidence but does not guarantee the sequence was intentional.
    """
    proposals: list[dict] = []

    # Find a timestamp / ordering column.
    ts_col = _find_timestamp_column(profile)
    if ts_col is None:
        return proposals

    # Find identifier columns with at least one null.
    id_cols_with_nulls = [
        c["name"] for c in profile["columns"]
        if c["inferred_type"] == "identifier" and c["null_count"] > 0
    ]
    if not id_cols_with_nulls:
        return proposals

    # Sort a copy of the dataframe by the ordering column.
    try:
        ts_parsed = pd.to_datetime(df[ts_col], errors="coerce")
        # sort_values preserves NaT at the end; argsort doesn't accept na_position.
        sort_order = ts_parsed.sort_values(na_position="last").index
        sorted_df  = df.loc[sort_order].reset_index(drop=True)
        sorted_ts  = ts_parsed.loc[sort_order].reset_index(drop=True)
    except Exception:
        return proposals

    for col in id_cols_with_nulls:
        if col not in sorted_df.columns:
            continue

        series = sorted_df[col].fillna("").astype(str)
        n = len(series)

        def _is_null_val(v: str) -> bool:
            return v.strip() == "" or v.lower() in ("nan", "none", "null", "<na>")

        for i in range(1, n - 1):
            if not _is_null_val(series.iloc[i]):
                continue

            # The null row must itself have a non-null timestamp.
            if pd.isna(sorted_ts.iloc[i]):
                continue

            prev_val = series.iloc[i - 1]
            next_val = series.iloc[i + 1]

            if _is_null_val(prev_val) or _is_null_val(next_val):
                continue  # Multi-null gap — too uncertain.

            parsed_prev = _parse_id(str(prev_val))
            parsed_next = _parse_id(str(next_val))

            if parsed_prev is None or parsed_next is None:
                continue

            prefix_prev, num_prev, width_prev = parsed_prev
            prefix_next, num_next, width_next = parsed_next

            # All three must share: same prefix, same zero-pad width,
            # and next_num == prev_num + 2  (exactly one missing).
            if prefix_prev != prefix_next:
                continue
            if width_prev != width_next:
                continue
            if num_next != num_prev + 2:
                continue

            proposed_num   = num_prev + 1
            proposed_id    = f"{prefix_prev}{str(proposed_num).zfill(width_prev)}"

            # Timestamps must be monotonically ordered at the gap.
            ts_prev = sorted_ts.iloc[i - 1]
            ts_null = sorted_ts.iloc[i]
            ts_next = sorted_ts.iloc[i + 1]
            if not (pd.notna(ts_prev) and ts_prev <= ts_null <= ts_next):
                continue

            # Use the row_id labelling column if available.
            row_id = str(sorted_df.iloc[i][id_col]) if id_col else None

            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="interpolation",
                    source_method="sequential_id_inference",
                    dataset_name=dataset_name,
                    row_index=int(sort_order[i]),   # original (pre-sort) row index
                    row_identifier=row_id,
                    column_name=col,
                    original_value=None,
                    proposed_value=proposed_id,
                    explanation=(
                        f"After ordering by '{ts_col}', the record at "
                        f"{ts_null} sits between '{prev_val}' "
                        f"({ts_prev}) and '{next_val}' ({ts_next}). "
                        f"The numeric parts {num_prev} and {num_next} differ by 2, "
                        f"suggesting one record is missing. "
                        f"Proposed identifier: {proposed_id}. "
                        f"This is based on ordered identifier sequence — "
                        f"it does NOT infer customer behaviour or financial values. "
                        f"Verify that the sequence was generated sequentially before applying."
                    ),
                    confidence=SEQUENTIAL_ID_CONFIDENCE,
                )
            )

    return proposals


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_id(val: str) -> tuple[str, int, int] | None:
    """
    Split an identifier string into (prefix, numeric_value, zero_padded_width).

    Examples
    --------
    "POL-00001" → ("POL-", 1, 5)
    "Q0042"     → ("Q",    42, 4)
    "000999"    → ("",     999, 6)

    Returns None if the value does not end with digits.
    """
    m = _ID_RE.match(val.strip())
    if not m:
        return None
    prefix     = m.group(1)
    numeric_str = m.group(2)
    return (prefix, int(numeric_str), len(numeric_str))


def _find_timestamp_column(profile: dict) -> str | None:
    """
    Return the name of a time-ordering column suitable for sorting before
    sequential ID inference.  Checks column names against
    TIMESTAMP_COLUMN_KEYWORDS (case-insensitive).
    """
    col_names_lower = {c["name"].lower(): c["name"] for c in profile["columns"]}
    for keyword in TIMESTAMP_COLUMN_KEYWORDS:
        if keyword in col_names_lower:
            return col_names_lower[keyword]
    return None


def _find_identifier_column(profile: dict) -> str | None:
    """
    Return the name of the best 'identifier' column to use as a row label
    in proposal descriptions.  Picks the identifier column with the highest
    uniqueness ratio and no nulls (so every row has a label).
    """
    candidates = [
        c for c in profile["columns"]
        if c["inferred_type"] == "identifier" and c["null_count"] == 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["uniqueness_ratio"])["name"]
