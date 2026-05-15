"""
Feature: Proposal Management

Provides:
  build_proposal(...)      — create a standardised proposal dict
  save_proposals(...)      — persist a list of proposals to the database
  get_proposals(...)       — retrieve proposals for a session from the database
  proposal_to_dict(...)    — convert an ORM row to a plain dict for API responses

All proposal dicts share the same 17-field shape regardless of the source
(cross-dataset fill or interpolation).  This is the contract that Stage 4's
review UI depends on — it reads proposals from the DB and adds approve/reject
decisions without caring how the proposal was generated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

# ── Validated type aliases ─────────────────────────────────────────────────
# Using Literal types gives static-analysis tools (mypy, Pylance) the ability
# to catch typos at the call site rather than at runtime.
#
# NOTE: "linear_interpolation" is kept in SourceMethod for backward
# compatibility with existing DB records even though it is no longer generated.

ProposalType = Literal[
    "cross_dataset_fill",
    "interpolation",
    "data_correction",       # Stage N+ cleaning / business-rule corrections
]

SourceMethod = Literal[
    # ── null-fill methods ──────────────────────────────────────────────────
    "cross_dataset_lookup",
    "linear_interpolation",          # legacy — no longer generated
    "date_inference",
    "sequential_id_inference",       # ordered identifier sequence gap-fill
    # ── data correction methods ────────────────────────────────────────────
    "format_correction",             # postcode uppercase, whitespace trim,
                                     # product_type casing
    "date_format_standardisation",   # non-YYYY-MM-DD → YYYY-MM-DD
    "value_cleaning",                # currency strings → numeric
    "business_rule",                 # premium floor / ceiling flags
]


# ── Builder ────────────────────────────────────────────────────────────────

def build_proposal(
    *,
    session_id: str,
    proposal_type: ProposalType,
    source_method: SourceMethod,
    dataset_name: str,
    row_index: int | None,
    row_identifier: str | None,
    column_name: str,
    original_value: Any,
    proposed_value: Any,
    explanation: str,
    confidence: float,
    source_dataset: str | None = None,
    source_column: str | None = None,
    join_key: str | None = None,
    join_value: str | None = None,
) -> dict:
    """
    Return a standardised proposal dict.

    original_value and proposed_value are always coerced to strings so they
    can be stored in and retrieved from SQLite without type ambiguity.
    Stage 4 will display these strings side-by-side in the review UI.
    """
    return {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "proposal_type": proposal_type,
        "source_method": source_method,
        "dataset_name": dataset_name,
        "row_index": row_index,
        "row_identifier": row_identifier,
        "column_name": column_name,
        "original_value": str(original_value) if original_value is not None else None,
        "proposed_value": str(proposed_value),
        "explanation": explanation,
        "confidence": round(float(confidence), 3),
        "status": "pending",
        "source_dataset": source_dataset,
        "source_column": source_column,
        "join_key": join_key,
        "join_value": join_value,
        "created_at": datetime.utcnow().isoformat(),
        "reviewed_at": None,
        "user_decision": None,
    }


# ── Persistence ────────────────────────────────────────────────────────────

def save_proposals(proposals: list[dict], db: Session) -> None:
    """
    Persist a list of proposal dicts to the database.

    Imports the ORM model inline to avoid circular imports at module load time.
    """
    from app.models.proposal import Proposal

    for p in proposals:
        orm_obj = Proposal(
            id=p["id"],
            session_id=p["session_id"],
            proposal_type=p["proposal_type"],
            source_method=p["source_method"],
            dataset_name=p["dataset_name"],
            row_index=p["row_index"],
            row_identifier=p["row_identifier"],
            column_name=p["column_name"],
            original_value=p["original_value"],
            proposed_value=p["proposed_value"],
            explanation=p["explanation"],
            confidence=p["confidence"],
            status=p["status"],
            source_dataset=p["source_dataset"],
            source_column=p["source_column"],
            join_key=p["join_key"],
            join_value=p["join_value"],
        )
        db.add(orm_obj)

    db.commit()


def get_proposals(session_id: str, db: Session) -> list[dict]:
    """Return all proposals for a session as plain dicts, sorted by confidence."""
    from app.models.proposal import Proposal

    rows = (
        db.query(Proposal)
        .filter(Proposal.session_id == session_id)
        .order_by(Proposal.confidence.desc())
        .all()
    )
    return [_to_dict(row) for row in rows]


def build_proposals_summary(proposals: list[dict]) -> dict:
    """
    Build the compact summary included in the upload API response.
    Contains counts by proposal_type and a confidence distribution.
    """
    by_type: dict[str, int] = {}
    high = medium = low = 0

    for p in proposals:
        by_type[p["proposal_type"]] = by_type.get(p["proposal_type"], 0) + 1
        c = p["confidence"]
        if c >= 0.80:
            high += 1
        elif c >= 0.60:
            medium += 1
        else:
            low += 1

    return {
        "total": len(proposals),
        "by_type": by_type,
        "by_confidence": {"high": high, "medium": medium, "low": low},
    }


# ── Serialisation ──────────────────────────────────────────────────────────

def _to_dict(row: Any) -> dict:
    """Convert a SQLAlchemy Proposal ORM row to a plain dict."""
    return {
        "id": row.id,
        "session_id": row.session_id,
        "proposal_type": row.proposal_type,
        "source_method": row.source_method,
        "dataset_name": row.dataset_name,
        "row_index": row.row_index,
        "row_identifier": row.row_identifier,
        "column_name": row.column_name,
        "original_value": row.original_value,
        "proposed_value": row.proposed_value,
        "explanation": row.explanation,
        "confidence": row.confidence,
        "status": row.status,
        "source_dataset": row.source_dataset,
        "source_column": row.source_column,
        "join_key": row.join_key,
        "join_value": row.join_value,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "user_decision": row.user_decision,
    }
