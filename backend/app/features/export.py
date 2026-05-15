"""
Feature: Dataset Export

Applies approved proposals to in-memory copies of the original uploaded
datasets and returns a ZIP archive containing:

  - {dataset_stem}_cleaned.csv  for each dataset that had at least one
                                 approved proposal successfully applied
  - audit_manifest.csv          one row per proposal for the session,
                                 covering all statuses (pending / approved /
                                 rejected) so the full decision history is
                                 preserved

Original files on disk are never opened for writing.  Every modification
happens on a copy of the DataFrame that was read from the original path.

Public API
----------
export_session(session_id, db) -> tuple[bytes, str]
    Returns (zip_bytes, suggested_zip_filename).
    Raises ExportError with an appropriate HTTP status code on failure.
"""

from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session


# ── Exceptions ──────────────────────────────────────────────────────────────

class ExportError(Exception):
    """
    Raised by export_session() on recoverable failures.

    The route handler catches this and converts it to an HTTPException with
    status_code = self.status_code so the frontend receives a clear message.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


# ── Main entry point ─────────────────────────────────────────────────────────

def export_session(session_id: str, db: Session) -> tuple[bytes, str]:
    """
    Build and return a ZIP archive for the given session.

    Steps
    -----
    1. Resolve session → file paths on disk via the UploadSession table.
    2. Fetch all proposals for the session from the database.
    3. Validate that at least one proposal is approved.
    4. Group approved proposals by dataset name.
    5. For each affected dataset:
         a. Read the original CSV into a DataFrame.
         b. Immediately copy it — all changes happen on the copy.
         c. For each approved proposal: validate row/column, then write the
            proposed_value (cast to the column's dtype).  Log and skip on
            any validation failure.
    6. Build an audit manifest covering ALL proposals (not just approved ones).
       The manifest records whether each proposal was actually applied.
    7. Pack cleaned CSVs + audit manifest into an in-memory ZIP and return
       the raw bytes.

    Raises
    ------
    ExportError
        404 — session not found in UploadSession table.
        400 — no proposals exist, or none are approved.
    """
    # 1. Resolve file paths for this session
    file_map = _get_session_files(session_id, db)
    if not file_map:
        raise ExportError(
            404,
            f"Session '{session_id}' not found. "
            "Make sure the session ID is correct and that you have uploaded "
            "datasets for this session.",
        )

    # 2. Fetch all proposals
    from app.features.proposals import get_proposals
    all_proposals = get_proposals(session_id, db)
    if not all_proposals:
        raise ExportError(
            400,
            "No proposals have been generated for this session. "
            "Run the analysis pipeline by uploading datasets first.",
        )

    # 3. Validate at least one approved proposal exists
    approved_proposals = [p for p in all_proposals if p["status"] == "approved"]
    if not approved_proposals:
        raise ExportError(
            400,
            "No proposals have been approved yet. "
            "Approve at least one proposal in the review screen before exporting.",
        )

    # 4. Group approved proposals by dataset
    by_dataset: dict[str, list[dict]] = defaultdict(list)
    for p in approved_proposals:
        by_dataset[p["dataset_name"]].append(p)

    # 5. Apply changes per dataset
    cleaned_datasets: dict[str, pd.DataFrame] = {}
    applied_ids: set[str] = set()

    for dataset_name, proposals in by_dataset.items():
        # Validate the file can be found
        if dataset_name not in file_map:
            print(
                f"[export] Skipping proposals for '{dataset_name}': "
                "dataset not found in session file map."
            )
            continue

        file_path = file_map[dataset_name]
        if not Path(file_path).exists():
            print(
                f"[export] Skipping '{dataset_name}': "
                f"file not found on disk at '{file_path}'."
            )
            continue

        df = pd.read_csv(file_path)
        # Work on a copy — the original file is never opened for writing.
        df_copy = df.copy()

        for p in proposals:
            row_idx = p["row_index"]
            col = p["column_name"]

            # Guard: row index must be present and in-bounds
            if row_idx is None:
                print(
                    f"[export] Skipping proposal {p['id']} "
                    f"({dataset_name}.{col}): row_index is None."
                )
                continue

            if row_idx >= len(df_copy):
                print(
                    f"[export] Skipping proposal {p['id']} "
                    f"({dataset_name}.{col}): row_index {row_idx} out of range "
                    f"(dataset has {len(df_copy)} rows)."
                )
                continue

            # Guard: column must exist
            if col not in df_copy.columns:
                print(
                    f"[export] Skipping proposal {p['id']} "
                    f"({dataset_name}.{col}): column not found in dataset."
                )
                continue

            # Apply with dtype-aware casting so numeric columns stay numeric
            new_val = _cast_value(p["proposed_value"], df_copy[col].dtype)
            df_copy.at[row_idx, col] = new_val
            applied_ids.add(p["id"])

        cleaned_datasets[dataset_name] = df_copy

    # 6. Build audit manifest (all proposals, all statuses)
    audit_rows = [
        {
            "dataset_name":  p["dataset_name"],
            "row_index":     p["row_index"],
            "row_identifier": p["row_identifier"],
            "column_name":   p["column_name"],
            "original_value": p["original_value"],
            "proposed_value": p["proposed_value"],
            "proposal_type": p["proposal_type"],
            "source_method": p["source_method"],
            "confidence":    p["confidence"],
            "status":        p["status"],
            "reviewed_at":   p["reviewed_at"],
            # True only for approved proposals where row/column was found
            "applied":       p["id"] in applied_ids,
        }
        for p in all_proposals
    ]
    audit_df = pd.DataFrame(audit_rows)

    # 7. Pack into an in-memory ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dataset_name, clean_df in cleaned_datasets.items():
            stem = Path(dataset_name).stem
            zf.writestr(f"{stem}_cleaned.csv", clean_df.to_csv(index=False))

        zf.writestr("audit_manifest.csv", audit_df.to_csv(index=False))

    buf.seek(0)
    filename = f"export_{session_id[:8]}.zip"
    return buf.read(), filename


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_session_files(session_id: str, db: Session) -> dict[str, str]:
    """Return {dataset_name: absolute_file_path} for the given session."""
    from app.models.upload_session import UploadSession

    records = (
        db.query(UploadSession)
        .filter(UploadSession.session_id == session_id)
        .all()
    )
    return {r.dataset_name: r.file_path for r in records}


def _cast_value(proposed_value: str, dtype: Any) -> Any:
    """
    Cast proposed_value (always stored as a string in the DB) to match the
    target column's dtype.

    Falls back to the raw string on any conversion error so the export never
    crashes due to a type mismatch — a string in a previously-numeric column
    is still better than a crash or leaving the cell null.
    """
    try:
        if pd.api.types.is_integer_dtype(dtype):
            return int(float(proposed_value))
        if pd.api.types.is_float_dtype(dtype):
            return float(proposed_value)
    except (ValueError, TypeError):
        pass
    return proposed_value
