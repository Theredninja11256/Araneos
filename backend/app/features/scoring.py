"""
Feature: Reliability Scoring

Consumes a DatasetProfile (produced by profiling.py) and computes a 0–100
reliability score with a Green / Amber / Red grade.

The scoring framework is fully configurable via SCORING_CONFIG in
app.core.insurance_fields.  Every point deduction is logged as a penalty
so the analyst can understand exactly why the score is what it is.

Public API
----------
score_dataset(profile: dict) -> dict
    Score a profiled dataset and return a ScoreResult dict.
"""

from __future__ import annotations

from app.core.insurance_fields import SCORING_CONFIG


def score_dataset(profile: dict) -> dict:
    """
    Compute a reliability score for a profiled dataset.

    Args
    ----
    profile : dict
        The output of profiling.profile_dataset().

    Returns
    -------
    dict with keys:
        score                : float  (0–100, floored at 0)
        grade                : "Green" | "Amber" | "Red"
        penalties            : list of penalty dicts
        critical_field_issues: list of critical-field problem dicts
        summary              : one-line plain-English summary
    """
    cfg = SCORING_CONFIG
    score = 100.0
    penalties: list[dict] = []
    critical_issues: list[dict] = []

    row_count: int = profile["row_count"]

    # ── 1. Duplicate row penalty (one penalty per dataset) ─────────────
    dup_count: int = profile["duplicate_row_count"]
    dup_pct: float = profile["duplicate_row_pct"]

    if dup_count > 0:
        entry = _threshold_penalty(
            rate=dup_pct,
            thresholds=cfg["duplicate_penalties"],
            reason=(
                f"Duplicate rows: {dup_count} row(s) ({dup_pct:.1%}) are exact duplicates."
            ),
            severity="high",
        )
        if entry:
            score -= entry["points_deducted"]
            penalties.append(entry)

    # ── 2. Per-column penalties ────────────────────────────────────────
    for col in profile["columns"]:
        col_name: str = col["name"]
        null_pct: float = col["null_pct"]
        null_count: int = col["null_count"]
        is_critical: bool = col["is_critical_field"]
        col_type: str = col["inferred_type"]

        # 2a. Null-rate penalty
        null_entry = _threshold_penalty(
            rate=null_pct,
            thresholds=cfg["null_penalties"],
            reason=(
                f"Column '{col_name}': {null_pct:.1%} of values are null "
                f"({null_count} missing)."
            ),
            severity="high" if is_critical else "medium",
            column=col_name,
        )
        if null_entry:
            score -= null_entry["points_deducted"]
            penalties.append(null_entry)

        # 2b. Extra penalty for nulls in a critical insurance field
        if is_critical and null_count > 0:
            extra = cfg["critical_field_null_penalty"]
            reason = (
                f"Critical field '{col_name}' has {null_count} null value(s) "
                f"— heavy penalty applied."
            )
            score -= extra
            crit_entry = {
                "reason": reason,
                "points_deducted": extra,
                "severity": "critical",
                "column": col_name,
            }
            penalties.append(crit_entry)
            critical_issues.append(
                {
                    "field": col_name,
                    "null_count": null_count,
                    "null_pct": null_pct,
                    "detail": reason,
                }
            )

        # 2c. Casing inconsistency — only meaningful for categorical columns where
        #     the same value should appear with one consistent casing.
        if col_type == "categorical":
            casing = col.get("casing_inconsistency_count") or 0
            if casing > 0:
                pts = cfg["format_inconsistency_penalty"]
                score -= pts
                penalties.append(
                    {
                        "reason": (
                            f"Column '{col_name}': {casing} value(s) have inconsistent "
                            f"casing (mixed upper / lower case)."
                        ),
                        "points_deducted": pts,
                        "severity": "low",
                        "column": col_name,
                    }
                )

        # 2d. Date format inconsistency
        if col_type == "date":
            formats = col.get("date_formats_detected") or []
            invalid_dates = col.get("invalid_date_count") or 0

            if len(formats) > 1:
                pts = cfg["date_format_inconsistency_penalty"]
                score -= pts
                penalties.append(
                    {
                        "reason": (
                            f"Column '{col_name}': {len(formats)} different date formats "
                            f"detected ({', '.join(formats)})."
                        ),
                        "points_deducted": pts,
                        "severity": "medium",
                        "column": col_name,
                    }
                )

            if invalid_dates > 0:
                pts = cfg["invalid_date_penalty"]
                score -= pts
                penalties.append(
                    {
                        "reason": (
                            f"Column '{col_name}': {invalid_dates} value(s) did not match "
                            f"any recognised date format."
                        ),
                        "points_deducted": pts,
                        "severity": "medium",
                        "column": col_name,
                    }
                )

        # 2e. Statistical outliers (numeric columns)
        if col_type == "numeric":
            outlier_count = col.get("outlier_count") or 0
            outlier_pct = col.get("outlier_pct") or 0.0
            non_null = row_count - null_count

            if non_null > 0 and outlier_count > 0:
                outlier_rate = outlier_count / non_null
                if outlier_rate > cfg["outlier_rate_threshold"]:
                    pts = cfg["outlier_penalty"]
                    score -= pts
                    penalties.append(
                        {
                            "reason": (
                                f"Column '{col_name}': {outlier_count} statistical "
                                f"outlier(s) detected ({outlier_rate:.1%} of non-null values)."
                            ),
                            "points_deducted": pts,
                            "severity": "low",
                            "column": col_name,
                        }
                    )

    # ── 3. Floor at 0 ──────────────────────────────────────────────────
    score = max(0.0, round(score, 1))

    # ── 4. Grade ───────────────────────────────────────────────────────
    grade_cfg = cfg["grade"]
    if score >= grade_cfg["green"]:
        grade = "Green"
    elif score >= grade_cfg["amber"]:
        grade = "Amber"
    else:
        grade = "Red"

    # ── 5. Summary ─────────────────────────────────────────────────────
    total_deducted = round(100.0 - score, 1)
    n_issues = len(penalties)
    summary = (
        f"Score {score}/100 ({grade}). "
        f"{n_issues} issue(s) found, {total_deducted} point(s) deducted."
    )
    if critical_issues:
        fields = ", ".join(i["field"] for i in critical_issues)
        summary += f" Critical fields with null values: {fields}."

    return {
        "score": score,
        "grade": grade,
        "penalties": penalties,
        "critical_field_issues": critical_issues,
        "summary": summary,
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _threshold_penalty(
    rate: float,
    thresholds: list[dict],
    reason: str,
    severity: str = "medium",
    column: str | None = None,
) -> dict | None:
    """
    Return a penalty dict if `rate` exceeds the highest applicable threshold.
    Thresholds must be ordered highest-first (as in SCORING_CONFIG).
    Returns None if no threshold is exceeded.
    """
    for t in thresholds:
        if rate > t["threshold"]:
            entry: dict = {
                "reason": reason,
                "points_deducted": t["penalty"],
                "severity": severity,
            }
            if column is not None:
                entry["column"] = column
            return entry
    return None
