"""
Feature: Dataset Profiling

Loads a saved dataset through the configured engine and computes a
comprehensive per-column statistical profile.

Design principle
----------------
This module contains only engine-agnostic logic.  All engine-specific
computation (null counts, quantiles, casing checks, etc.) is delegated to
engine.compute_column_stats() and engine.get_duplicate_row_count().
This module assembles and interprets those raw numbers into a standardised
DatasetProfile dict whose shape never changes regardless of which engine ran.

Public API
----------
profile_dataset(file_path: str) -> dict
    Load a file and return a complete DatasetProfile.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.insurance_fields import (
    CRITICAL_FIELDS,
    DATE_COLUMN_KEYWORDS,
    IDENTIFIER_COLUMN_KEYWORDS,
)
from app.engines.engine_selector import get_engine

# ── Date format patterns ───────────────────────────────────────────────────
# Applied to sample_values from string columns whose names look date-like.
# Each entry is (human-readable label, compiled regex).
_DATE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ISO (YYYY-MM-DD)", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("Slash (DD/MM/YYYY)", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("Long-form (Month D YYYY)", re.compile(r"^[A-Za-z]+ \d{1,2} \d{4}$")),
    ("Long-form (D Month YYYY)", re.compile(r"^\d{1,2} [A-Za-z]+ \d{4}$")),
]

# Uniqueness ratio above which a non-identifier string column is "high-cardinality".
_HIGH_CARDINALITY_THRESHOLD = 0.85


# ── Column-type classifier ─────────────────────────────────────────────────

def _classify_column(col_name: str, raw: dict, row_count: int) -> str:
    """
    Assign a semantic type to a column.

    Order of checks matters — numeric is detected first via the engine's
    is_numeric flag, then heuristics on the column name, then uniqueness ratio.

    Returns one of: 'numeric' | 'date' | 'identifier' | 'categorical' | 'text'
    """
    if raw.get("is_numeric"):
        return "numeric"

    col_lower = col_name.lower()

    if any(kw in col_lower for kw in DATE_COLUMN_KEYWORDS):
        return "date"

    # Identifier heuristic: column name ends with or equals a known keyword.
    if any(col_lower == kw or col_lower.endswith(f"_{kw}") or col_lower.endswith(kw)
           for kw in IDENTIFIER_COLUMN_KEYWORDS):
        return "identifier"

    unique_ratio = raw["unique_count"] / max(row_count, 1)
    if unique_ratio < 0.30:
        return "categorical"

    return "text"


# ── Date format analyser ───────────────────────────────────────────────────

def _detect_date_formats(sample_values: list) -> tuple[int, list[str]]:
    """
    Scan a sample of string values and detect which date-format patterns
    are present.

    Returns
    -------
    invalid_count : int
        Values that matched NO known date pattern.
    formats_found : list[str]
        Sorted list of format names that appeared at least once.
    """
    found: set[str] = set()
    invalid_count = 0

    for raw_val in sample_values:
        val = str(raw_val).strip() if raw_val is not None else ""
        if not val:
            continue
        matched = False
        for label, pattern in _DATE_PATTERNS:
            if pattern.match(val):
                found.add(label)
                matched = True
                break
        if not matched:
            invalid_count += 1

    return invalid_count, sorted(found)


# ── Per-column issue builder ───────────────────────────────────────────────

def _build_column_issues(
    col_name: str,
    col_type: str,
    null_pct: float,
    null_count: int,
    is_critical: bool,
    outlier_count: int | None,
    outlier_pct: float | None,
    casing_count: int | None,
    invalid_date_count: int,
    date_formats: list[str],
    row_count: int,
) -> list[str]:
    """Return a list of human-readable issue strings for a single column."""
    issues: list[str] = []

    # Null-rate issues
    prefix = "Critical field: n" if is_critical else "N"
    if null_pct > 0.50:
        issues.append(
            f"{prefix}ull rate is {null_pct:.0%} — over half of values are missing."
        )
    elif null_pct > 0.20:
        issues.append(f"High null rate: {null_pct:.0%} of values are missing.")
    elif null_pct > 0.05:
        issues.append(f"Elevated null rate: {null_pct:.0%} of values are missing.")
    elif null_count > 0 and is_critical:
        issues.append(
            f"Critical field has {null_count} null value(s) ({null_pct:.1%})."
        )

    # Outlier issues
    if col_type == "numeric" and outlier_count and outlier_pct is not None:
        if outlier_pct > 0.05:
            issues.append(
                f"High outlier rate: {outlier_count} value(s) are statistical outliers "
                f"({outlier_pct:.0%} of non-null values)."
            )

    # Format issues — only meaningful for categorical fields where the same
    # value is expected to appear with a single consistent casing.
    if col_type == "categorical" and casing_count:
        issues.append(
            f"Inconsistent casing: {casing_count} value(s) have mixed case variants "
            f"(e.g. 'Motor' / 'motor' / 'MOTOR')."
        )

    if col_type == "date":
        if len(date_formats) > 1:
            issues.append(
                f"Multiple date formats detected: {', '.join(date_formats)}."
            )
        if invalid_date_count > 0:
            issues.append(
                f"{invalid_date_count} value(s) did not match any known date format."
            )

    return issues


# ── Main entry point ───────────────────────────────────────────────────────

def profile_dataset(file_path: str) -> dict:
    """
    Load a saved CSV file and compute a full statistical profile.

    Args
    ----
    file_path : str
        Path to the file on disk (already saved by the upload route).

    Returns
    -------
    dict
        A DatasetProfile.  The shape is identical regardless of which
        engine (pandas or Spark) was used.  See the 'columns' list for the
        per-column ColumnProfile structure.
    """
    engine = get_engine()
    df = engine.load_csv(file_path)

    row_count = engine.get_row_count(df)
    col_names = engine.get_column_names(df)
    schema = engine.get_schema(df)
    dup_count = engine.get_duplicate_row_count(df)

    column_profiles: list[dict] = []
    dataset_issues: list[dict] = []

    for col in col_names:
        raw = engine.compute_column_stats(df, col, row_count)

        null_count: int = raw["null_count"]
        null_pct: float = null_count / max(row_count, 1)
        unique_count: int = raw["unique_count"]
        unique_ratio: float = unique_count / max(row_count, 1)

        col_type = _classify_column(col, raw, row_count)
        is_critical = col in CRITICAL_FIELDS

        # ── Date format analysis ───────────────────────────────────────
        invalid_date_count = 0
        date_formats: list[str] = []
        if col_type == "date" and raw.get("sample_values"):
            invalid_date_count, date_formats = _detect_date_formats(
                raw["sample_values"]
            )

        # ── Derived numeric stats ──────────────────────────────────────
        outlier_count: int | None = raw.get("outlier_count") if raw.get("is_numeric") else None
        outlier_pct: float | None = (
            _round(outlier_count / max(row_count, 1)) if outlier_count is not None else None
        )

        is_high_cardinality = (
            col_type not in ("identifier", "numeric")
            and unique_ratio > _HIGH_CARDINALITY_THRESHOLD
        )

        issues = _build_column_issues(
            col_name=col,
            col_type=col_type,
            null_pct=null_pct,
            null_count=null_count,
            is_critical=is_critical,
            outlier_count=outlier_count,
            outlier_pct=outlier_pct,
            casing_count=raw.get("casing_inconsistency_count"),
            invalid_date_count=invalid_date_count,
            date_formats=date_formats,
            row_count=row_count,
        )

        # Escalate issues on critical fields to the dataset-level list.
        if issues and is_critical:
            for issue in issues:
                dataset_issues.append(
                    {
                        "column": col,
                        "severity": "critical" if null_count > 0 else "warning",
                        "detail": issue,
                    }
                )

        column_profiles.append(
            {
                "name": col,
                "inferred_type": col_type,
                "dtype_raw": schema.get(col, "unknown"),
                "is_critical_field": is_critical,
                # Null
                "null_count": null_count,
                "null_pct": _round(null_pct),
                # Uniqueness
                "unique_count": unique_count,
                "uniqueness_ratio": _round(unique_ratio),
                "is_high_cardinality": is_high_cardinality,
                # Top values
                "top_values": raw.get("top_values", []),
                # Numeric
                "min": raw.get("min"),
                "max": raw.get("max"),
                "mean": _round(raw.get("mean")),
                "median": _round(raw.get("median")),
                "std": _round(raw.get("std")),
                "outlier_count": outlier_count,
                "outlier_pct": outlier_pct,
                # Categorical / text
                "casing_inconsistency_count": raw.get("casing_inconsistency_count"),
                # Date
                "invalid_date_count": invalid_date_count if col_type == "date" else None,
                "date_formats_detected": date_formats if col_type == "date" else None,
                # Consolidated issues
                "issues": issues,
            }
        )

    return {
        "file_name": Path(file_path).name,
        "file_path": file_path,
        "engine_used": engine.engine_name,
        "row_count": row_count,
        "column_count": len(col_names),
        "duplicate_row_count": dup_count,
        "duplicate_row_pct": _round(dup_count / max(row_count, 1)),
        "columns": column_profiles,
        "dataset_issues": dataset_issues,
    }


# ── Utilities ──────────────────────────────────────────────────────────────

def _round(val: Any, digits: int = 4) -> Any:
    """Round a numeric value to `digits` decimal places, pass None through."""
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return val
