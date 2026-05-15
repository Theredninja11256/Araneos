"""
Feature: Proposal Review

Implements the human-in-the-loop decision workflow for Stage 4.

Each proposal starts as 'pending'.  An analyst may approve or reject it
exactly once.  Attempted re-reviews raise ProposalAlreadyReviewedError.
Unknown IDs raise ProposalNotFoundError.

These exceptions are domain exceptions — they carry no HTTP semantics.
The route handler converts them to 409 / 404 HTTP responses.

Public API
----------
approve_proposal(proposal_id, db) -> dict
reject_proposal(proposal_id, db)  -> dict

Both return the full updated proposal dict (same shape as get_proposals())
so the frontend can update its local state in-place without a re-fetch.

State transitions
-----------------
    pending  →  approved   (via approve_proposal)
    pending  →  rejected   (via reject_proposal)
    approved →  (terminal)
    rejected →  (terminal)

No transitions beyond the two above are implemented in Stage 4.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

# ── Standard cleaning classification ───────────────────────────────────────
# source_methods that are considered low-risk formatting fixes and may be
# bulk-approved or bulk-rejected as a group.  Higher-risk proposal types
# (cross_dataset_lookup, date_inference, sequential_id_inference, business_rule)
# are always reviewed individually.

STANDARD_CLEANING_METHODS: frozenset[str] = frozenset({
    "format_correction",
    "date_format_standardisation",
    "value_cleaning",
})


# ── Domain exceptions ──────────────────────────────────────────────────────

class ProposalNotFoundError(Exception):
    """Raised when no proposal row exists for the given ID."""


class ProposalAlreadyReviewedError(Exception):
    """
    Raised when an approve or reject is attempted on a proposal that is
    not in 'pending' state.  The message includes the current status so
    the caller can surface it to the analyst.
    """


# ── Review logic ───────────────────────────────────────────────────────────

def approve_proposal(proposal_id: str, db: Session) -> dict:
    """
    Mark a pending proposal as approved.

    Args
    ----
    proposal_id : UUID string
    db          : SQLAlchemy session (injected by FastAPI)

    Returns
    -------
    Full updated proposal dict.

    Raises
    ------
    ProposalNotFoundError        — proposal_id does not exist in the DB.
    ProposalAlreadyReviewedError — proposal is not in 'pending' state.
    """
    return _apply_decision(proposal_id, decision="approved", db=db)


def reject_proposal(proposal_id: str, db: Session) -> dict:
    """
    Mark a pending proposal as rejected.

    Args
    ----
    proposal_id : UUID string
    db          : SQLAlchemy session (injected by FastAPI)

    Returns
    -------
    Full updated proposal dict.

    Raises
    ------
    ProposalNotFoundError        — proposal_id does not exist in the DB.
    ProposalAlreadyReviewedError — proposal is not in 'pending' state.
    """
    return _apply_decision(proposal_id, decision="rejected", db=db)


# ── Bulk review ────────────────────────────────────────────────────────────

def bulk_review_cleaning(session_id: str, decision: str, db: Session) -> dict:
    """
    Approve or reject all pending standard-cleaning proposals for a session
    in a single DB transaction.

    Each proposal gets its own reviewed_at timestamp and user_decision, so
    the audit trail is identical to individual approvals.

    Args
    ----
    session_id : str   — the upload session UUID
    decision   : str   — "approved" or "rejected"
    db         : Session

    Returns
    -------
    { "updated": int, "decision": str, "updated_ids": [str, ...] }
    """
    from app.models.proposal import Proposal
    from app.features.proposals import _to_dict  # reuse serialiser

    if decision not in ("approved", "rejected"):
        raise ValueError(f"Invalid decision: {decision!r}")

    rows = (
        db.query(Proposal)
        .filter(
            Proposal.session_id == session_id,
            Proposal.status == "pending",
            Proposal.source_method.in_(STANDARD_CLEANING_METHODS),
        )
        .all()
    )

    now = datetime.utcnow()
    for p in rows:
        p.status        = decision
        p.user_decision = decision
        p.reviewed_at   = now

    db.commit()

    updated_ids = [p.id for p in rows]
    return {
        "updated":     len(rows),
        "decision":    decision,
        "updated_ids": updated_ids,
    }


# ── Internal ───────────────────────────────────────────────────────────────

def _apply_decision(
    proposal_id: str,
    decision: str,
    db: Session,
) -> dict:
    """
    Shared implementation for approve and reject.

    Validates state, writes the decision, commits, and returns the updated
    proposal as a plain dict.
    """
    from app.models.proposal import Proposal
    from app.features.proposals import _to_dict  # reuse the existing serialiser

    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()

    if proposal is None:
        raise ProposalNotFoundError(
            f"Proposal '{proposal_id}' not found."
        )

    if proposal.status != "pending":
        raise ProposalAlreadyReviewedError(
            f"Proposal has already been reviewed "
            f"(current status: '{proposal.status}'). "
            f"Only pending proposals can be approved or rejected."
        )

    proposal.status = decision
    proposal.user_decision = decision
    proposal.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(proposal)

    return _to_dict(proposal)
