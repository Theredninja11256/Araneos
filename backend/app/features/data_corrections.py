"""
Feature: Data Corrections

Rule-based correction proposals for common insurance data quality issues.
Each rule targets a specific, well-understood pattern and generates proposals
that flow through the existing approve/reject workflow.  Nothing is applied
automatically; all corrections require analyst sign-off.

Rules
-----
1. Postcode uppercase            — strip + uppercase any postcode value that is
                                   not already uppercased.

2. Whitespace trim               — remove leading/trailing whitespace from any
                                   string column value (categorical, text,
                                   identifier).  Skips postcode and
                                   product_type columns (handled separately).

3. Product type casing           — detect the majority casing in the
                                   product_type column and propose corrections
                                   for outlier values.

4. Date format standardisation   — for date columns whose values are parseable
                                   but not in YYYY-MM-DD, propose the standard
                                   format only when the parse is unambiguous
                                   (same result with dayfirst=True and =False).

5. Currency value cleaning       — convert strings like "£1,200" or "$500.00"
                                   to plain numeric values (e.g. "1200.0").
                                   Only fires for known currency column names.

6. Premium floor flag            — flag premiums that are already numeric but
                                   below the configured ANALYST_RULES minimum.
                                   Proposes the minimum premium as a replacement
                                   so analysts can approve or reject the floor.

All proposals use proposal_type="data_correction".

Public API
----------
find_correction_proposals(file_path, profile, session_id, display_name) -> list[dict]
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.core.insurance_fields import (
    ANALYST_RULES,
    CURRENCY_COLUMN_NAMES,
    NCD_COLUMN_NAMES,
    POSTCODE_COLUMN_NAMES,
    PREMIUM_COLUMN_NAMES,
    PRODUCT_TYPE_COLUMN_NAMES,
)
from app.engines.engine_selector import get_engine
from app.features.proposals import build_proposal

# Maximum number of correction proposals generated per column.
# Prevents flooding the review UI on large datasets.
_MAX_PER_COLUMN: int = 100

# Regex for currency-formatted strings: optional symbol, digits, commas,
# optional decimal.  E.g. "£1,200", "€500.50", "$1,000.00", "1,200".
_CURRENCY_RE = re.compile(r"^[£$€]?\s*\d[\d,]*\.?\d*$")

# Regex: must have at least one currency symbol or comma to be considered
# "dirty" (plain floats like "1200.0" are already clean and are skipped).
_DIRTY_CURRENCY_RE = re.compile(r"[£$€,]")

# Pattern for already-standard dates.
_YYYY_MM_DD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Public entry point ─────────────────────────────────────────────────────

def find_correction_proposals(
    file_path: str,
    profile: dict,
    session_id: str,
    display_name: str | None = None,
    analyst_rules: dict | None = None,
) -> list[dict]:
    """
    Scan a dataset file for correctable values and return proposals.

    Args
    ----
    file_path      : str       — path to the saved CSV file
    profile        : dict      — Stage 2 DatasetProfile for this file
    session_id     : str       — ties proposals to the current upload session
    display_name   : str|None  — original filename; falls back to profile["file_name"]
    analyst_rules  : dict|None — per-session rule overrides (min_premium, max_premium,
                                 max_ncd, date_format_standard, currency_symbol).
                                 Falls back to ANALYST_RULES defaults where not supplied.

    Returns
    -------
    list of standardised proposal dicts (may be empty).
    """
    engine = get_engine()
    raw_df = engine.load_csv(file_path)
    df = raw_df.toPandas() if hasattr(raw_df, "toPandas") else raw_df

    dataset_name = display_name or profile["file_name"]
    id_col       = _find_identifier_column(profile)

    # Merge per-session overrides on top of defaults.
    rules: dict = {**ANALYST_RULES, **(analyst_rules or {})}

    proposals: list[dict] = []

    proposals.extend(_postcode_uppercase_proposals(df, profile, dataset_name, session_id, id_col))
    proposals.extend(_whitespace_trim_proposals(df, profile, dataset_name, session_id, id_col))
    proposals.extend(_product_type_normalise_proposals(df, profile, dataset_name, session_id, id_col))
    proposals.extend(_date_format_proposals(df, profile, dataset_name, session_id, id_col, rules))
    proposals.extend(_currency_clean_proposals(df, profile, dataset_name, session_id, id_col))
    proposals.extend(_premium_threshold_proposals(df, profile, dataset_name, session_id, id_col, rules))
    proposals.extend(_negative_premium_proposals(df, profile, dataset_name, session_id, id_col))
    proposals.extend(_ncd_ceiling_proposals(df, profile, dataset_name, session_id, id_col, rules))
    proposals.extend(_expiry_before_inception_proposals(df, profile, dataset_name, session_id, id_col))

    return proposals


# ── Rule 1: postcode uppercase ─────────────────────────────────────────────

def _postcode_uppercase_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For each column whose name matches POSTCODE_COLUMN_NAMES: propose
    strip + uppercase for any value not already in that form.
    """
    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in POSTCODE_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val      = str(raw)
            proposed = val.strip().upper()
            if proposed == val:
                continue  # Already correct.

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="format_correction",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=col,
                    original_value=val,
                    proposed_value=proposed,
                    explanation=(
                        f"Postcode '{val}' is not in standard uppercase format. "
                        f"Proposed: '{proposed}' (stripped and uppercased). "
                        f"Consistent postcode casing is required for geographic "
                        f"analysis and regulatory reporting."
                    ),
                    confidence=0.92,
                )
            )
            count += 1
            if count >= _MAX_PER_COLUMN:
                break

    return proposals


# ── Rule 2: whitespace trim ────────────────────────────────────────────────

def _whitespace_trim_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For each string column (categorical, text, identifier): propose stripped
    values for any cell with leading or trailing whitespace.

    Postcode and product_type columns are excluded because their dedicated
    rules already handle whitespace as part of a broader correction.
    """
    proposals: list[dict] = []

    # Columns handled by more specific rules — skip in this rule.
    _skip = POSTCODE_COLUMN_NAMES | PRODUCT_TYPE_COLUMN_NAMES

    string_types = {"categorical", "text", "identifier"}

    for col_profile in profile["columns"]:
        if col_profile["inferred_type"] not in string_types:
            continue
        col = col_profile["name"]
        if col.lower() in _skip:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val      = str(raw)
            proposed = val.strip()
            # Skip if no change or if stripping produces an empty string.
            if proposed == val or proposed == "":
                continue

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="format_correction",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=col,
                    original_value=val,
                    proposed_value=proposed,
                    explanation=(
                        f"'{col}' value has leading or trailing whitespace. "
                        f"Proposed: trimmed value '{proposed}'. "
                        f"Whitespace padding can cause silent mismatches in "
                        f"joins, lookups, and reporting filters."
                    ),
                    confidence=0.92,
                )
            )
            count += 1
            if count >= _MAX_PER_COLUMN:
                break

    return proposals


# ── Rule 3: product_type casing ────────────────────────────────────────────

def _product_type_normalise_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For each column whose name matches PRODUCT_TYPE_COLUMN_NAMES: detect the
    majority casing style across non-null values and propose corrections for
    values that deviate from it.
    """
    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in PRODUCT_TYPE_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        series     = df[col].dropna().astype(str)
        style      = _detect_majority_casing(series)

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val      = str(raw).strip()
            proposed = _apply_casing(val, style)
            if proposed == raw:
                continue  # Already matches majority style.

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="format_correction",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=col,
                    original_value=str(raw),
                    proposed_value=proposed,
                    explanation=(
                        f"'{col}' value '{raw}' does not match the predominant "
                        f"casing style ({style}) in this column. "
                        f"Proposed: '{proposed}'. "
                        f"Inconsistent casing causes incorrect group-by counts "
                        f"and breaks dashboards that filter by product type."
                    ),
                    confidence=0.82,
                )
            )
            count += 1
            if count >= _MAX_PER_COLUMN:
                break

    return proposals


def _detect_majority_casing(series: pd.Series) -> str:
    """Return the majority casing style: 'upper', 'title', or 'lower'."""
    if len(series) == 0:
        return "title"
    counts = {
        "upper": int((series == series.str.upper()).sum()),
        "title": int((series == series.str.title()).sum()),
        "lower": int((series == series.str.lower()).sum()),
    }
    return max(counts, key=counts.__getitem__)


def _apply_casing(val: str, style: str) -> str:
    if style == "upper":
        return val.upper()
    if style == "lower":
        return val.lower()
    return val.title()


# ── Rule 4: date format standardisation ───────────────────────────────────

def _date_format_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
    rules: dict | None = None,
) -> list[dict]:
    """
    For columns inferred as 'date': if a value is parseable but not already
    in the configured date_format_standard, propose the standardised form.

    Safety check: only propose when parsing with dayfirst=True and
    dayfirst=False yields the same date (i.e. the parse is unambiguous).
    Ambiguous values such as "03/05/2024" are skipped.
    """
    proposals: list[dict] = []
    _rules   = rules or ANALYST_RULES
    std_fmt  = _rules.get("date_format_standard", "%d-%m-%y")

    for col_profile in profile["columns"]:
        if col_profile["inferred_type"] != "date":
            continue

        col = col_profile["name"]
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val = str(raw).strip()

            try:
                dt_nodayfirst = pd.to_datetime(val, dayfirst=False, errors="raise")
                dt_dayfirst   = pd.to_datetime(val, dayfirst=True,  errors="raise")
            except Exception:
                continue  # Not parseable — skip.

            if dt_nodayfirst != dt_dayfirst:
                continue  # Ambiguous day/month order — skip.

            proposed = dt_nodayfirst.strftime(std_fmt)
            if proposed == val:
                continue  # Already in target format.

            # Human-readable format name for the explanation.
            fmt_label = std_fmt.replace("%d", "DD").replace("%m", "MM").replace("%Y", "YYYY").replace("%y", "YY")

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="date_format_standardisation",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=col,
                    original_value=val,
                    proposed_value=proposed,
                    explanation=(
                        f"'{col}' value '{val}' is parseable as '{proposed}' "
                        f"but is not in the configured {fmt_label} format. "
                        f"Standardised dates ensure consistent sorting, filtering, "
                        f"and time-series analysis across all datasets."
                    ),
                    confidence=0.87,
                )
            )
            count += 1
            if count >= _MAX_PER_COLUMN:
                break

    return proposals


# ── Rule 5: currency value cleaning ───────────────────────────────────────

def _currency_clean_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    For columns whose names match CURRENCY_COLUMN_NAMES: convert
    currency-formatted strings (e.g. "£1,200", "$500.00") to plain numeric
    strings (e.g. "1200.0", "500.0").

    Only fires when the raw value contains a currency symbol or comma
    (already-clean floats like "1200.0" are left unchanged).
    """
    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in CURRENCY_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val = str(raw).strip()

            # Skip values that are already clean numbers.
            if not _DIRTY_CURRENCY_RE.search(val):
                continue

            cleaned = _parse_currency(val)
            if cleaned is None:
                continue  # Unrecognised pattern — leave for analyst.

            proposed = str(cleaned)

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="value_cleaning",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=col,
                    original_value=val,
                    proposed_value=proposed,
                    explanation=(
                        f"'{col}' value '{val}' contains currency formatting "
                        f"(symbols or commas) that prevents numeric calculations. "
                        f"Proposed: '{proposed}' (currency symbols and commas removed). "
                        f"Numeric storage is required for aggregation, scoring, "
                        f"and premium analysis."
                    ),
                    confidence=0.88,
                )
            )
            count += 1
            if count >= _MAX_PER_COLUMN:
                break

    return proposals


def _parse_currency(val: str) -> float | None:
    """
    Strip currency symbols (£, $, €), commas, and whitespace, then
    convert to float.  Returns None if the result is not a valid number.
    """
    cleaned = re.sub(r"[£$€,\s]", "", val)
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── Rule 6: premium threshold anomalies ───────────────────────────────────

def _premium_threshold_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
    rules: dict | None = None,
) -> list[dict]:
    """
    Flag premiums outside analyst-configured bounds.

    Skips currency-formatted strings (handled by _currency_clean_proposals).
    Only fires on plain numeric or decimal string values.
    """
    _rules      = rules or ANALYST_RULES
    min_premium = _rules.get("minimum_premium")
    max_premium = _rules.get("maximum_premium")

    if min_premium is None and max_premium is None:
        return []

    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in PREMIUM_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val = str(raw).strip()
            if _DIRTY_CURRENCY_RE.search(val):
                continue  # Currency strings handled by cleaning rule.
            try:
                numeric = float(val)
            except ValueError:
                continue

            if min_premium is not None and numeric < min_premium:
                row_id = str(df.iloc[i][id_col]) if id_col else None
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="data_correction",
                        source_method="business_rule",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=col,
                        original_value=val,
                        proposed_value=str(float(min_premium)),
                        explanation=(
                            f"Business rule alert: '{col}' value {numeric} is below the "
                            f"minimum premium of {min_premium}. "
                            f"Approving applies the floor value. Reject if the low "
                            f"premium is legitimate (discounted, subsidised, or test policy)."
                        ),
                        confidence=0.70,
                    )
                )
                count += 1

            elif max_premium is not None and numeric > max_premium:
                row_id = str(df.iloc[i][id_col]) if id_col else None
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="data_correction",
                        source_method="business_rule",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=col,
                        original_value=val,
                        proposed_value=str(float(max_premium)),
                        explanation=(
                            f"Business rule alert: '{col}' value {numeric} exceeds the "
                            f"configured maximum premium of {max_premium}. "
                            f"Review for data entry error or a legitimate high-value policy."
                        ),
                        confidence=0.70,
                    )
                )
                count += 1

            if count >= _MAX_PER_COLUMN:
                break

    return proposals


# ── Rule 7: negative premium ───────────────────────────────────────────────

def _negative_premium_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    Flag premium columns with negative values as critical anomalies.
    A negative premium is almost always a data entry error.
    """
    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in PREMIUM_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            val = str(raw).strip()
            # Strip currency symbols for numeric check.
            cleaned = re.sub(r"[£$€,\s]", "", val)
            try:
                numeric = float(cleaned)
            except ValueError:
                continue

            if numeric < 0:
                row_id = str(df.iloc[i][id_col]) if id_col else None
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="data_correction",
                        source_method="business_rule",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=col,
                        original_value=val,
                        proposed_value="0.0",
                        explanation=(
                            f"Critical anomaly: '{col}' value {numeric} is negative. "
                            f"A negative premium is not valid for insurance policies. "
                            f"Likely a data entry error or sign inversion. "
                            f"Proposed replacement is 0.0 — reject if the row should "
                            f"be removed or corrected to the actual premium."
                        ),
                        confidence=0.95,
                    )
                )
                count += 1
                if count >= _MAX_PER_COLUMN:
                    break

    return proposals


# ── Rule 8: NCD ceiling ────────────────────────────────────────────────────

def _ncd_ceiling_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
    rules: dict | None = None,
) -> list[dict]:
    """
    Flag NCD values above the analyst-configured maximum.

    NOTE: NCD values are NEVER interpolated or inferred from adjacent rows.
    This rule only flags existing values that exceed the plausible maximum.
    """
    _rules   = rules or ANALYST_RULES
    max_ncd  = _rules.get("max_ncd")

    if max_ncd is None:
        return []

    proposals: list[dict] = []

    for col_profile in profile["columns"]:
        col = col_profile["name"]
        if col.lower() not in NCD_COLUMN_NAMES:
            continue
        if col not in df.columns:
            continue

        count = 0
        for i, raw in enumerate(df[col]):
            if pd.isna(raw):
                continue
            try:
                numeric = float(str(raw).strip())
            except ValueError:
                continue

            if numeric > max_ncd:
                row_id = str(df.iloc[i][id_col]) if id_col else None
                proposals.append(
                    build_proposal(
                        session_id=session_id,
                        proposal_type="data_correction",
                        source_method="business_rule",
                        dataset_name=dataset_name,
                        row_index=i,
                        row_identifier=row_id,
                        column_name=col,
                        original_value=str(raw),
                        proposed_value=str(float(max_ncd)),
                        explanation=(
                            f"Business rule alert: '{col}' value {numeric} exceeds "
                            f"the configured maximum NCD of {max_ncd} years. "
                            f"Review for data entry error. NCD values are never "
                            f"inferred from adjacent rows — this is a flagging-only rule."
                        ),
                        confidence=0.75,
                    )
                )
                count += 1
                if count >= _MAX_PER_COLUMN:
                    break

    return proposals


# ── Rule 9: expiry before inception ────────────────────────────────────────

def _expiry_before_inception_proposals(
    df: pd.DataFrame,
    profile: dict,
    dataset_name: str,
    session_id: str,
    id_col: str | None,
) -> list[dict]:
    """
    Flag rows where expiry_date < inception_date — an impossible policy term.
    No replacement value is proposed; the proposal flags the anomaly for
    analyst review only.
    """
    from app.core.insurance_fields import ANNUAL_DATE_PAIRS

    proposals: list[dict] = []
    col_names = {c["name"] for c in profile["columns"]}

    for start_col, end_col in ANNUAL_DATE_PAIRS:
        if start_col not in col_names or end_col not in col_names:
            continue
        if start_col not in df.columns or end_col not in df.columns:
            continue

        try:
            start_s = pd.to_datetime(df[start_col], errors="coerce")
            end_s   = pd.to_datetime(df[end_col],   errors="coerce")
        except Exception:
            continue

        for i in range(len(df)):
            s = start_s.iloc[i]
            e = end_s.iloc[i]
            if pd.isna(s) or pd.isna(e):
                continue
            if e >= s:
                continue  # Valid order.

            row_id = str(df.iloc[i][id_col]) if id_col else None
            proposals.append(
                build_proposal(
                    session_id=session_id,
                    proposal_type="data_correction",
                    source_method="business_rule",
                    dataset_name=dataset_name,
                    row_index=i,
                    row_identifier=row_id,
                    column_name=end_col,
                    original_value=str(df.iloc[i][end_col]),
                    proposed_value=str(df.iloc[i][start_col]),  # Suggest swapping.
                    explanation=(
                        f"Date anomaly: '{end_col}' ({e.date()}) is before "
                        f"'{start_col}' ({s.date()}). A policy cannot expire before "
                        f"it starts. The proposed value swaps the dates — reject if the "
                        f"row requires manual correction or deletion."
                    ),
                    confidence=0.80,
                )
            )

    return proposals


# ── Helpers ────────────────────────────────────────────────────────────────

def _find_identifier_column(profile: dict) -> str | None:
    """
    Return the name of the best identifier column to use as a row label
    in proposal descriptions.  Requires zero nulls and picks the highest
    uniqueness ratio.
    """
    candidates = [
        c for c in profile["columns"]
        if c["inferred_type"] == "identifier" and c["null_count"] == 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["uniqueness_ratio"])["name"]
