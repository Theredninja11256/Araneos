"""
Sessions router — session-level operations.

Routes
------
POST /api/v1/sessions/{session_id}/export               (Stage 5)
    Apply approved proposals and return a ZIP archive.

GET  /api/v1/sessions/{session_id}/joins                (Stage 7)
    Detect dataset join pairs and return insight suggestions.

POST /api/v1/sessions/{session_id}/joins/generate       (Stage 7)
    Run an aggregation for a specific insight and return table data.

GET  /api/v1/sessions/{session_id}/dashboard            (Stage 8)
    Return the CTO dashboard summary for a session.

GET  /api/v1/sessions/{session_id}/dashboard/export     (Stage 8)
    Return a downloadable HTML health report.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.features import export as export_feature
from app.features import join_intelligence
from app.features import cto_dashboard
from app.features.review import bulk_review_cleaning
from app.models.database import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Stage 5: Export ───────────────────────────────────────────────────────────

@router.post("/{session_id}/export")
def export_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """
    Export cleaned datasets for a session.

    Applies every approved proposal to a copy of the original data and returns
    a ZIP containing the cleaned CSV(s) and a full audit manifest.
    """
    try:
        zip_bytes, filename = export_feature.export_session(session_id, db)
    except export_feature.ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Stage 13: Bulk standard-cleaning review ───────────────────────────────────

@router.patch("/{session_id}/standard-cleaning/approve")
def approve_standard_cleaning(session_id: str, db: Session = Depends(get_db)):
    """
    Bulk-approve all pending standard-cleaning proposals for a session.

    Standard-cleaning proposals are low-risk formatting fixes (postcode casing,
    date format normalisation, currency symbol removal).  Approving them in
    bulk is safe and preserves every individual proposal's audit record.
    """
    return bulk_review_cleaning(session_id, "approved", db)


@router.patch("/{session_id}/standard-cleaning/reject")
def reject_standard_cleaning(session_id: str, db: Session = Depends(get_db)):
    """
    Bulk-reject all pending standard-cleaning proposals for a session.
    """
    return bulk_review_cleaning(session_id, "rejected", db)


# ── Stage 7: Join Intelligence ────────────────────────────────────────────────

@router.get("/{session_id}/joins")
def get_joins(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Detect joinable dataset pairs for a session and return insight suggestions.

    Returns
    -------
    {
        session_id              : str,
        join_reports            : list  — one per detected pair with match metrics,
        single_dataset_insights : list  — per-dataset insights that don't need a join
    }
    """
    try:
        return join_intelligence.analyse_joins_for_session(session_id, db)
    except join_intelligence.JoinError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


class GenerateInsightRequest(BaseModel):
    """Request body for the insight generation endpoint."""
    dataset_a: str
    dataset_b: str | None = None   # required for cross-dataset insights
    join_key: str | None = None    # required for cross-dataset insights
    insight_id: str


@router.post("/{session_id}/joins/generate")
def generate_insight(
    session_id: str,
    body: GenerateInsightRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    Run the aggregation for a specific insight and return table data.

    For cross-dataset insights supply dataset_b and join_key.
    For single-dataset insights only dataset_a is required.

    Returns
    -------
    {
        insight_id   : str,
        insight_name : str,
        row_count    : int,
        columns      : list[str],
        rows         : list[dict]
    }
    """
    try:
        return join_intelligence.generate_insight_table(
            session_id=session_id,
            dataset_a=body.dataset_a,
            dataset_b=body.dataset_b,
            join_key=body.join_key,
            insight_id=body.insight_id,
            db=db,
        )
    except join_intelligence.JoinError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


# ── Stage 8: CTO Dashboard ────────────────────────────────────────────────────

@router.get("/{session_id}/dashboard")
def get_dashboard(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Build and return the CTO dashboard summary for a session.

    Aggregates profiling scores, RAG status, critical alerts, and join
    opportunities from Stages 2 and 7 into a single executive summary.

    Returns
    -------
    {
        session_id, overall_score, grade, dataset_count,
        rag_summary, critical_alerts, join_opportunities,
        trend_data, generated_at
    }
    """
    try:
        return cto_dashboard.build_cto_dashboard(session_id, db)
    except cto_dashboard.DashboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/{session_id}/dashboard/export")
def export_dashboard_report(
    session_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """
    Generate and return a downloadable HTML health report for a session.

    The report includes overall score, RAG summary, critical alerts,
    join opportunities, quality context, and a timestamp.
    No PDF or external libraries are used.
    """
    try:
        html = cto_dashboard.export_dashboard_html(session_id, db)
    except cto_dashboard.DashboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    short_id = session_id[:8]
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Disposition": (
                f'attachment; filename="health_report_{short_id}.html"'
            )
        },
    )
