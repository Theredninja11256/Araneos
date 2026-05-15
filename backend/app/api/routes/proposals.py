"""
Proposals API routes.

GET  /api/v1/proposals/{session_id}
    Returns all proposals for a session sorted by confidence descending.

PATCH /api/v1/proposals/{proposal_id}/approve
PATCH /api/v1/proposals/{proposal_id}/reject
    Approve or reject a pending proposal.

GET  /api/v1/proposals/{proposal_id}/context
    Returns row context (rows above and below the changed row) for a proposal,
    so the analyst can review surrounding data before deciding.
    For cross-dataset fill proposals, also returns source dataset context.

All business logic lives in app.features.  This module handles HTTP only.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.features import proposals as proposals_feature
from app.features.review import (
    ProposalAlreadyReviewedError,
    ProposalNotFoundError,
    approve_proposal,
    reject_proposal,
)
from app.models.database import get_db
from app.models.proposal import Proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])

_CONTEXT_WINDOW = 2   # rows above and below the target row


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_val(v: Any) -> Any:
    """Convert pandas NA / float NaN to None for JSON serialisation."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _read_context_rows(
    file_path: str,
    row_index: int,
    highlight_col: str | None = None,
    window: int = _CONTEXT_WINDOW,
) -> dict:
    """
    Read `window` rows above and below `row_index` from a CSV file.

    Returns
    -------
    {
        "columns": [col, ...],
        "rows": [
            {"_position": "above" | "target" | "below", <col>: <val>, ...},
            ...
        ],
        "total_rows": int
    }
    """
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read dataset: {exc}")

    total   = len(df)
    columns = list(df.columns)

    rows_out = []
    start = max(0, row_index - window)
    end   = min(total - 1, row_index + window)

    for i in range(start, end + 1):
        position = "target" if i == row_index else ("above" if i < row_index else "below")
        row_dict: dict[str, Any] = {"_position": position}
        for col in columns:
            raw = df.iloc[i][col]
            row_dict[col] = None if (raw == "" or raw == "nan") else str(raw)
        rows_out.append(row_dict)

    return {
        "columns":    columns,
        "rows":       rows_out,
        "total_rows": total,
        "highlighted_column": highlight_col,
    }


def _find_source_context(
    file_path: str,
    join_key: str,
    join_value: str,
    source_col: str | None = None,
    window: int = _CONTEXT_WINDOW,
) -> dict | None:
    """
    Find the row in source_file where `join_key == join_value` and return
    context rows around it.
    """
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception:
        return None

    if join_key not in df.columns:
        return None

    match_mask = df[join_key].astype(str) == str(join_value)
    matches    = match_mask[match_mask].index.tolist()
    if not matches:
        return None

    source_idx = matches[0]
    context    = _read_context_rows(file_path, source_idx, highlight_col=source_col, window=window)
    context["matched_key"]   = join_key
    context["matched_value"] = join_value
    context["match_row_index"] = source_idx
    return context


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/{session_id}")
def get_session_proposals(session_id: str, db: Session = Depends(get_db)):
    """Return all proposals for a session, sorted by confidence descending."""
    results = proposals_feature.get_proposals(session_id, db)
    summary = proposals_feature.build_proposals_summary(results)
    return {"session_id": session_id, **summary, "proposals": results}


@router.patch("/{proposal_id}/approve")
def approve(proposal_id: str, db: Session = Depends(get_db)):
    try:
        return approve_proposal(proposal_id, db)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProposalAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/{proposal_id}/reject")
def reject(proposal_id: str, db: Session = Depends(get_db)):
    try:
        return reject_proposal(proposal_id, db)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProposalAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{proposal_id}/context")
def get_proposal_context(proposal_id: str, db: Session = Depends(get_db)):
    """
    Return row context for a single proposal.

    Response
    --------
    {
        "target": {
            "dataset": str,
            "column": str,
            "columns": [str, ...],
            "rows": [{"_position": "above"|"target"|"below", <col>: <val>}, ...],
            "total_rows": int,
            "highlighted_column": str
        },
        "source": null | {
            "dataset": str,
            "matched_key": str,
            "matched_value": str,
            "match_row_index": int,
            "columns": [...],
            "rows": [...],
            "total_rows": int,
            "highlighted_column": str
        }
    }
    """
    # ── Load the proposal ─────────────────────────────────────────────
    proposal: Proposal | None = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

    if proposal.row_index is None:
        raise HTTPException(status_code=422, detail="This proposal has no row_index — context unavailable.")

    # ── Look up the session files ─────────────────────────────────────
    from app.models.upload_session import UploadSession

    session_rows = (
        db.query(UploadSession)
        .filter(UploadSession.session_id == proposal.session_id)
        .all()
    )
    file_map: dict[str, str] = {row.dataset_name: row.file_path for row in session_rows}

    target_path = file_map.get(proposal.dataset_name)
    if not target_path:
        raise HTTPException(
            status_code=404,
            detail=f"Original file for '{proposal.dataset_name}' not found."
        )

    # ── Build target context ──────────────────────────────────────────
    target_context = _read_context_rows(
        target_path,
        proposal.row_index,
        highlight_col=proposal.column_name,
    )
    target_context["dataset"] = proposal.dataset_name
    target_context["column"]  = proposal.column_name

    # ── Build source context (cross-dataset fills only) ───────────────
    source_context = None
    if (
        proposal.proposal_type == "cross_dataset_fill"
        and proposal.source_dataset
        and proposal.join_key
        and proposal.join_value
    ):
        source_path = file_map.get(proposal.source_dataset)
        if source_path:
            source_context = _find_source_context(
                source_path,
                proposal.join_key,
                proposal.join_value,
                source_col=proposal.source_column,
            )
            if source_context:
                source_context["dataset"] = proposal.source_dataset
                source_context["column"]  = proposal.source_column

    return {"target": target_context, "source": source_context}
