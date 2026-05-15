"""
Feature: CTO Dashboard

Aggregates outputs from Stages 2, 5, and 7 to produce an executive-level
summary of data health, risk, and opportunity for a session.

This module reuses existing feature modules without duplicating any logic:
  - profiling.profile_dataset()      — Stage 2
  - scoring.score_dataset()          — Stage 2
  - join_intelligence.*              — Stage 7
  - UploadSession table              — Stage 5

No new database tables are introduced.

Public API
----------
build_cto_dashboard(session_id, db) -> dict
    Aggregates all available data into a dashboard summary.
    Raises DashboardError(404) if the session is not found.

export_dashboard_html(session_id, db) -> str
    Returns a self-contained HTML report suitable for download.
    Raises DashboardError if the session is not found.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.features import profiling, scoring
from app.features import join_intelligence

# Industry benchmark score used for the MVP trend comparison (hardcoded).
_INDUSTRY_BENCHMARK: int = 75

# Severity display ordering (lower = more urgent)
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_GRADE_DESCRIPTIONS: dict[str, str] = {
    "Green": "Reliable",
    "Amber": "Caution",
    "Red":   "Action Required",
}


# ── Exceptions ────────────────────────────────────────────────────────────────

class DashboardError(Exception):
    """Raised by public functions on recoverable failures."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


# ── Main entry points ─────────────────────────────────────────────────────────

def build_cto_dashboard(session_id: str, db: Session) -> dict:
    """
    Build the full CTO dashboard for a session.

    Steps
    -----
    1. Locate uploaded files via UploadSession table.
    2. Re-run profiling and scoring on each file (fast, deterministic).
    3. Compute overall weighted health score and RAG grade.
    4. Extract plain-English critical alerts from scoring penalties.
    5. Call join_intelligence to get join opportunities.
    6. Build a simulated trend context (no historical storage in MVP).

    Returns
    -------
    dict with keys:
        session_id, overall_score, grade, dataset_count,
        rag_summary, critical_alerts, join_opportunities,
        trend_data, generated_at
    """
    file_map = _get_session_files(session_id, db)
    if not file_map:
        raise DashboardError(
            404,
            f"Session '{session_id}' not found. "
            "Upload datasets first to generate a dashboard.",
        )

    # Profile and score every uploaded file
    dataset_results: list[dict] = []
    for name, path in file_map.items():
        if not Path(path).exists():
            print(f"[cto_dashboard] Skipping '{name}': file not found at '{path}'.")
            continue
        try:
            profile = profiling.profile_dataset(path)
            score   = scoring.score_dataset(profile)
            dataset_results.append({"name": name, "profile": profile, "score": score})
        except Exception as exc:
            print(f"[cto_dashboard] Analysis failed for '{name}': {exc}")

    if not dataset_results:
        raise DashboardError(400, "No datasets could be analysed for this session.")

    overall_score, grade = _compute_overall_score(dataset_results)
    rag_summary          = _compute_rag_summary(dataset_results)
    critical_alerts      = _extract_critical_alerts(dataset_results)

    # Join intelligence — non-fatal if it fails
    try:
        joins_result      = join_intelligence.analyse_joins_for_session(session_id, db)
        join_opportunities = _extract_join_opportunities(joins_result)
    except Exception as exc:
        print(f"[cto_dashboard] Join intelligence error: {exc}")
        join_opportunities = []

    trend_data = _build_trend_data(overall_score)

    return {
        "session_id":       session_id,
        "overall_score":    round(overall_score, 1),
        "grade":            grade,
        "dataset_count":    len(dataset_results),
        "rag_summary":      rag_summary,
        "critical_alerts":  critical_alerts,
        "join_opportunities": join_opportunities,
        "trend_data":       trend_data,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
    }


def export_dashboard_html(session_id: str, db: Session) -> str:
    """Build the dashboard and render it as a self-contained HTML report."""
    dashboard = build_cto_dashboard(session_id, db)
    return _render_html(dashboard)


# ── Aggregation helpers ───────────────────────────────────────────────────────

def _compute_overall_score(dataset_results: list[dict]) -> tuple[float, str]:
    """Weighted average of dataset scores, weighted by row count."""
    total_rows = sum(d["profile"]["row_count"] for d in dataset_results)
    if total_rows == 0:
        avg = sum(d["score"]["score"] for d in dataset_results) / len(dataset_results)
    else:
        avg = (
            sum(d["score"]["score"] * d["profile"]["row_count"] for d in dataset_results)
            / total_rows
        )
    grade = "Green" if avg >= 75 else "Amber" if avg >= 50 else "Red"
    return avg, grade


def _compute_rag_summary(dataset_results: list[dict]) -> dict:
    green = sum(1 for d in dataset_results if d["score"]["grade"] == "Green")
    amber = sum(1 for d in dataset_results if d["score"]["grade"] == "Amber")
    red   = sum(1 for d in dataset_results if d["score"]["grade"] == "Red")
    return {"green": green, "amber": amber, "red": red, "total": len(dataset_results)}


def _extract_critical_alerts(
    dataset_results: list[dict], max_alerts: int = 5
) -> list[dict]:
    """
    Collect critical and high-severity scoring penalties across all datasets,
    convert them to plain-English business language, deduplicate, and return
    the top max_alerts sorted by urgency.
    """
    all_alerts: list[dict] = []

    for ds in dataset_results:
        ds_name = ds["name"]

        # Scoring penalties (primary source)
        for penalty in ds["score"]["penalties"]:
            if penalty["severity"] in ("critical", "high"):
                alert = _penalty_to_alert(penalty, ds_name)
                if alert:
                    all_alerts.append(alert)

        # Critical field issues (secondary — fills gaps not captured by penalties)
        for cfi in ds["score"].get("critical_field_issues", []):
            if cfi["null_count"] > 0:
                col_label = cfi["field"].replace("_", " ").title()
                ds_label  = Path(ds_name).stem.replace("_", " ").title()
                null_pct  = round(cfi["null_pct"] * 100)
                all_alerts.append({
                    "severity":     "critical",
                    "dataset":      ds_name,
                    "column":       cfi["field"],
                    "alert_text": (
                        f"{col_label} has {null_pct}% missing values in {ds_label} "
                        f"— this is a critical insurance field"
                    ),
                    "points_impact": 20,
                })

    # Deduplicate by (dataset, column) keeping the highest-severity entry,
    # then sort by urgency and return the top max_alerts.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for alert in sorted(
        all_alerts,
        key=lambda a: (_SEVERITY_RANK.get(a["severity"], 9), -a["points_impact"]),
    ):
        key = (alert["dataset"], alert["column"])
        if key not in seen:
            seen.add(key)
            unique.append(alert)

    return unique[:max_alerts]


def _penalty_to_alert(penalty: dict, dataset_name: str) -> dict | None:
    """Convert a scoring penalty dict into a plain-English business alert."""
    reason    = penalty.get("reason", "")
    col       = penalty.get("column") or ""
    severity  = penalty["severity"]
    pts       = penalty.get("points_deducted", 0)

    col_label = col.replace("_", " ").title() if col else ""
    ds_label  = Path(dataset_name).stem.replace("_", " ").title()

    pct_match = re.search(r"(\d+\.?\d*)%", reason)
    pct_str   = f"{float(pct_match.group(1)):.0f}%" if pct_match else ""

    reason_lower = reason.lower()

    if "null" in reason_lower and col:
        if severity == "critical":
            text = (
                f"{col_label} has {pct_str} missing values in {ds_label} "
                f"— may impact pricing accuracy and regulatory compliance"
            )
        else:
            text = f"{col_label} has {pct_str} missing values in {ds_label}"

    elif "duplicate" in reason_lower:
        text = (
            f"{ds_label} contains duplicate rows "
            f"— may indicate data entry errors or system duplication"
        )
    elif "outlier" in reason_lower and col:
        text = (
            f"{col_label} in {ds_label} has statistical outliers "
            f"— review for data entry errors or genuine anomalies"
        )
    elif "casing" in reason_lower and col:
        text = (
            f"{col_label} in {ds_label} has inconsistent text formatting "
            f"— affects data matching and reporting accuracy"
        )
    elif "date" in reason_lower:
        text = (
            f"Date columns in {ds_label} use mixed formats "
            f"— standardisation required for time-series analysis"
        )
    else:
        text = reason

    return {
        "severity":     severity,
        "dataset":      dataset_name,
        "column":       col,
        "alert_text":   text,
        "points_impact": pts,
    }


def _extract_join_opportunities(
    joins_result: dict, top_n: int = 3
) -> list[dict]:
    """
    Select the most valuable join opportunities and express them in
    business language.  Scoring weights match rate (60%) and insight
    coverage (40%).
    """
    reports = joins_result.get("join_reports", [])
    if not reports:
        return []

    max_insights = max((len(r["insights"]) for r in reports), default=1)

    def _value(r: dict) -> float:
        insight_norm = len(r["insights"]) / max(max_insights, 1)
        return r["match_rate"] * 0.6 + insight_norm * 0.4

    top = sorted(reports, key=_value, reverse=True)[:top_n]
    opportunities = []

    for r in top:
        ds_a = Path(r["dataset_a"]).stem.replace("_", " ").lower()
        ds_b = Path(r["dataset_b"]).stem.replace("_", " ").lower()

        insight_names = [i["name"] for i in r["insights"][:2]]
        if insight_names:
            examples = " and ".join(i.lower() for i in insight_names)
            business_text = (
                f"Combining {ds_a} and {ds_b} data enables {examples}"
            )
        else:
            business_text = (
                f"{ds_a.title()} and {ds_b.title()} records can be linked — "
                f"{round(r['match_rate'] * 100)}% of keys match"
            )

        opportunities.append({
            "dataset_a":        r["dataset_a"],
            "dataset_b":        r["dataset_b"],
            "join_key":         r["join_key"],
            "match_rate":       round(r["match_rate"] * 100),
            "insights_count":   len(r["insights"]),
            "business_summary": business_text,
            "top_insights":     [i["name"] for i in r["insights"][:3]],
        })

    return opportunities


def _build_trend_data(current_score: float) -> dict:
    """
    MVP simulated trend.  No historical data is stored, so we compare the
    current session score against a hardcoded industry benchmark for context.
    """
    delta = round(current_score - _INDUSTRY_BENCHMARK, 1)
    if delta >= 5:
        context = (
            f"Your data quality is {delta:.0f} points above the industry benchmark of "
            f"{_INDUSTRY_BENCHMARK}/100 — maintain focus on critical field completeness to stay ahead."
        )
    elif delta >= 0:
        context = (
            f"Your data quality is close to the industry benchmark of {_INDUSTRY_BENCHMARK}/100. "
            "Addressing the critical alerts above could push you into the Green tier."
        )
    else:
        context = (
            f"Your data quality is {abs(delta):.0f} points below the industry benchmark of "
            f"{_INDUSTRY_BENCHMARK}/100. Focus on fixing missing values in critical insurance "
            "fields to improve reliability scores."
        )

    return {
        "current_score":   round(current_score, 1),
        "benchmark_score": _INDUSTRY_BENCHMARK,
        "label":           "Current session",
        "context":         context,
    }


# ── HTML export ───────────────────────────────────────────────────────────────

_GRADE_COLOURS: dict[str, tuple[str, str, str]] = {
    # (score_colour, badge_background, badge_text)
    "Green": ("#16a34a", "#dcfce7", "#15803d"),
    "Amber": ("#d97706", "#fef3c7", "#b45309"),
    "Red":   ("#dc2626", "#fee2e2", "#b91c1c"),
}

_SEVERITY_ICONS: dict[str, str] = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "⚪",
}

_SEVERITY_HTML_STYLES: dict[str, str] = {
    "critical": "background:#fff1f2;border-left:4px solid #ef4444;",
    "high":     "background:#fff7ed;border-left:4px solid #f97316;",
    "medium":   "background:#fffbeb;border-left:4px solid #f59e0b;",
    "low":      "background:#f8fafc;border-left:4px solid #94a3b8;",
}


def _render_html(dash: dict) -> str:
    grade                           = dash["grade"]
    score_colour, badge_bg, badge_text = _GRADE_COLOURS.get(grade, _GRADE_COLOURS["Amber"])
    grade_desc                      = _GRADE_DESCRIPTIONS.get(grade, grade)
    rag                             = dash["rag_summary"]
    ts = datetime.fromisoformat(dash["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    trend = dash["trend_data"]

    # ── Alerts HTML ─────────────────────────────────────────────────────────
    alerts_html = ""
    for alert in dash["critical_alerts"]:
        style = _SEVERITY_HTML_STYLES.get(alert["severity"], _SEVERITY_HTML_STYLES["low"])
        icon  = _SEVERITY_ICONS.get(alert["severity"], "⚪")
        col_hint = f" · {alert['column']}" if alert.get("column") else ""
        alerts_html += (
            f'<div style="padding:12px 16px;border-radius:8px;margin-bottom:10px;{style}">'
            f'<div style="font-size:14px;color:#334155;">{icon} {alert["alert_text"]}</div>'
            f'<div style="font-size:11px;color:#94a3b8;margin-top:4px;">'
            f'{alert["dataset"]}{col_hint} · {alert["severity"].upper()}</div>'
            f'</div>\n'
        )
    if not alerts_html:
        alerts_html = '<p style="color:#94a3b8;font-size:14px;">No critical alerts detected — data quality looks good.</p>'

    # ── Opportunities HTML ──────────────────────────────────────────────────
    opps_html = ""
    for opp in dash["join_opportunities"]:
        insights_li = "".join(
            f'<li style="margin-top:3px;">{ins}</li>'
            for ins in opp["top_insights"]
        )
        opps_html += (
            f'<div style="padding:16px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span style="font-size:22px;font-weight:900;color:#1e40af;">{opp["match_rate"]}%</span>'
            f'<span style="font-size:12px;color:#64748b;">key match via '
            f'<code style="background:#f1f5f9;padding:2px 5px;border-radius:4px;">'
            f'{opp["join_key"]}</code></span></div>'
            f'<p style="font-size:14px;color:#334155;margin-top:8px;">{opp["business_summary"]}</p>'
            f'<ul style="margin-top:6px;padding-left:18px;font-size:12px;color:#64748b;">{insights_li}</ul>'
            f'</div>\n'
        )
    if not opps_html:
        opps_html = '<p style="color:#94a3b8;font-size:14px;">No join opportunities detected in this session.</p>'

    cur_pct   = max(1, round(trend["current_score"]))
    bench_pct = max(1, round(trend["benchmark_score"]))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Health Report — {ts}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;color:#1e293b}}
  .wrap{{max-width:820px;margin:0 auto;padding:48px 24px}}
  .hero{{text-align:center;margin-bottom:40px}}
  .label{{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.12em;margin-bottom:16px}}
  .big-score{{font-size:88px;font-weight:900;line-height:1;color:{score_colour}}}
  .grade-pill{{display:inline-block;padding:7px 22px;border-radius:999px;font-size:16px;font-weight:700;margin-top:14px;background:{badge_bg};color:{badge_text}}}
  .meta{{color:#64748b;font-size:14px;margin-top:14px}}
  .rag{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:32px}}
  .rag-card{{background:white;border-radius:12px;padding:20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
  .section{{background:white;border-radius:12px;padding:24px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
  .stitle{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#64748b;margin-bottom:16px}}
  .bar-wrap{{margin-bottom:14px}}
  .bar-row{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px}}
  .bar-bg{{background:#e2e8f0;border-radius:999px;height:10px}}
  .footer{{text-align:center;font-size:12px;color:#94a3b8;margin-top:40px;padding-top:24px;border-top:1px solid #e2e8f0}}
</style>
</head>
<body>
<div class="wrap">

  <div class="hero">
    <p class="label">Insurance Data Health Report</p>
    <div class="big-score">{round(dash['overall_score'])}<span style="font-size:32px;font-weight:400;color:#cbd5e1">/100</span></div>
    <div class="grade-pill">{grade} — {grade_desc}</div>
    <p class="meta">{dash['dataset_count']} dataset{'s' if dash['dataset_count'] != 1 else ''} analysed &nbsp;·&nbsp; {ts}</p>
  </div>

  <div class="rag">
    <div class="rag-card">
      <div style="font-size:40px;font-weight:900;color:#16a34a">{rag['green']}</div>
      <div style="font-size:13px;color:#64748b;margin-top:4px">Green datasets</div>
      <div style="font-size:11px;color:#86efac;margin-top:2px">Reliable</div>
    </div>
    <div class="rag-card">
      <div style="font-size:40px;font-weight:900;color:#d97706">{rag['amber']}</div>
      <div style="font-size:13px;color:#64748b;margin-top:4px">Amber datasets</div>
      <div style="font-size:11px;color:#fcd34d;margin-top:2px">Review needed</div>
    </div>
    <div class="rag-card">
      <div style="font-size:40px;font-weight:900;color:#dc2626">{rag['red']}</div>
      <div style="font-size:13px;color:#64748b;margin-top:4px">Red datasets</div>
      <div style="font-size:11px;color:#fca5a5;margin-top:2px">Action required</div>
    </div>
  </div>

  <div class="section">
    <div class="stitle">Critical Alerts</div>
    {alerts_html}
  </div>

  <div class="section">
    <div class="stitle">Data Join Opportunities</div>
    {opps_html}
  </div>

  <div class="section">
    <div class="stitle">Quality Context</div>
    <div class="bar-wrap">
      <div class="bar-row">
        <span>Your data</span>
        <span style="font-weight:700;color:{score_colour}">{round(dash['overall_score'])}/100</span>
      </div>
      <div class="bar-bg"><div style="background:{score_colour};border-radius:999px;height:10px;width:{cur_pct}%"></div></div>
    </div>
    <div class="bar-wrap">
      <div class="bar-row">
        <span>Industry benchmark</span>
        <span style="font-weight:700;color:#64748b">{bench_pct}/100</span>
      </div>
      <div class="bar-bg"><div style="background:#94a3b8;border-radius:999px;height:10px;width:{bench_pct}%"></div></div>
    </div>
    <p style="margin-top:16px;font-size:13px;color:#475569;line-height:1.65">{trend['context']}</p>
  </div>

  <div class="footer">
    <p>Data Platform &nbsp;·&nbsp; Insurance Data Intelligence</p>
    <p style="margin-top:4px">Session: {dash['session_id']}</p>
    <p style="margin-top:4px">Generated automatically. Verify findings before use in business decisions.</p>
  </div>

</div>
</body>
</html>"""


# ── Data access ───────────────────────────────────────────────────────────────

def _get_session_files(session_id: str, db: Session) -> dict[str, str]:
    from app.models.upload_session import UploadSession
    rows = (
        db.query(UploadSession)
        .filter(UploadSession.session_id == session_id)
        .all()
    )
    return {r.dataset_name: r.file_path for r in rows}
