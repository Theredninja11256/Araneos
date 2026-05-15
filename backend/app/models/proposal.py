"""
Proposal ORM model.

One row per proposed data change.  All proposals start with status='pending'.
Stage 4 will add approval/rejection by updating status, user_decision, and
reviewed_at — no schema migration required.

Proposal types:
    cross_dataset_fill  — value sourced from another uploaded dataset
    interpolation       — value inferred from arithmetic/date sequence

Source methods:
    cross_dataset_lookup    — exact key match across two datasets
    linear_interpolation    — arithmetic sequence gap-fill
    date_inference          — annual policy date inference (inception ↔ expiry)

Status values (Stage 4):
    pending   — not yet reviewed
    approved  — analyst accepted the proposed change
    rejected  — analyst rejected the proposed change
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.models.database import Base


class Proposal(Base):
    __tablename__ = "proposals"

    # ── Identity ──────────────────────────────────────────────────────
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)

    # ── Proposal classification ───────────────────────────────────────
    proposal_type = Column(String, nullable=False)   # cross_dataset_fill | interpolation
    source_method = Column(String, nullable=False)   # cross_dataset_lookup | linear_interpolation | date_inference

    # ── Location ──────────────────────────────────────────────────────
    dataset_name = Column(String, nullable=False)    # original filename shown to the analyst
    row_index = Column(Integer, nullable=True)       # 0-based row index in the original dataframe
    row_identifier = Column(String, nullable=True)   # human-readable row label (e.g. "POL-007")
    column_name = Column(String, nullable=False)

    # ── Values ────────────────────────────────────────────────────────
    # original_value is null for null-fill proposals because the value being
    # filled IS null by definition.  For format-normalisation proposals
    # (Stage 4+), original_value should be populated with the malformed string
    # so the analyst can see what was there before the proposed correction.
    original_value = Column(String, nullable=True)
    proposed_value = Column(String, nullable=False)

    # ── Explanation ───────────────────────────────────────────────────
    explanation = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)        # 0.0 – 1.0

    # ── Cross-dataset fill metadata (null for interpolation proposals) ─
    source_dataset = Column(String, nullable=True)
    source_column = Column(String, nullable=True)
    join_key = Column(String, nullable=True)
    join_value = Column(String, nullable=True)

    # ── Workflow state (Stage 4 will write these) ─────────────────────
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    user_decision = Column(String, nullable=True)   # "approved" | "rejected"
