"""
Feature: Analysis Pipeline

Orchestrates the full Stage 1-3 analysis for a batch of uploaded files.

Separation of concerns
----------------------
This module exists so that upload.py (a route handler) does not contain
business logic.  The route is responsible for HTTP concerns only:
  - reading file bytes
  - validating file extension and size
  - saving files to disk
  - calling run_analysis_pipeline()
  - returning the HTTP response

Everything that happens after the files are saved lives here.

Public API
----------
run_analysis_pipeline(saved_files, session_id, db) -> dict
    saved_files : list of {file_path, saved_as, display_name, size_bytes}
    Returns     : {dataset_results, proposals_summary}
    Raises      : PipelineError on fatal profiling or scoring failures.
                  Stage 3 (null_resolution, interpolation, save) failures
                  are non-fatal: they are logged and the pipeline continues,
                  returning an empty proposals_summary rather than aborting.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.features import (
    data_corrections,
    interpolation,
    null_resolution,
    profiling,
    proposals,
    scoring,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _record_session_files(
    saved_files: list[dict],
    session_id: str,
    db: Session,
    analyst_rules: dict | None = None,
) -> None:
    """
    Persist the mapping from (session_id, display_name) → file_path for every
    uploaded file so the Stage 5 export feature can locate the originals.
    Also stores analyst_rules_json for use in the row-context endpoint.

    Imported inline to avoid circular imports at module load time.
    """
    import json as _json
    from app.models.upload_session import UploadSession

    rules_json = _json.dumps(analyst_rules) if analyst_rules else None

    for sf in saved_files:
        db.add(
            UploadSession(
                session_id=session_id,
                dataset_name=sf["display_name"],
                file_path=sf["file_path"],
                saved_as=sf["saved_as"],
                analyst_rules_json=rules_json,
            )
        )
    db.commit()


# ── Exceptions ─────────────────────────────────────────────────────────────

class PipelineError(Exception):
    """
    Raised when a fatal pipeline step fails (profiling or scoring).

    The route handler catches this and converts it to an HTTP 500 response.
    Stage 3 failures (null resolution, interpolation, proposal persistence)
    are non-fatal and do not raise PipelineError.
    """

    def __init__(self, filename: str, stage: str, cause: Exception) -> None:
        super().__init__(f"Failed to {stage} '{filename}': {cause}")
        self.filename = filename
        self.stage = stage
        self.cause = cause


# ── Pipeline ────────────────────────────────────────────────────────────────

def run_analysis_pipeline(
    saved_files: list[dict],
    session_id: str,
    db: Session,
    analyst_rules: dict | None = None,
) -> dict:
    """
    Run profiling, scoring, null resolution, and interpolation for a batch
    of uploaded files.

    Args
    ----
    saved_files : list of dicts, each containing:
        file_path    : str  — absolute path to the saved file on disk
        saved_as     : str  — filename as stored (may include timestamp prefix)
        display_name : str  — original filename shown to the analyst
        size_bytes   : int  — byte length of the file content

    session_id : str
        UUID that ties all proposals from this upload batch together.

    db : SQLAlchemy Session
        Injected by the FastAPI dependency; used to persist proposals.

    Returns
    -------
    dict with keys:
        dataset_results   : list[dict]  — one entry per file with profile + score
        proposals_summary : dict        — total, by_type, by_confidence counts

    Raises
    ------
    PipelineError
        If profiling or scoring fails for any file.  The route handler
        converts this to an HTTP 500 response with a descriptive message.
    """
    # ── Record session files for Stage 5 export ───────────────────────
    # Must run before analysis so the export feature can find originals
    # even if the pipeline later fails on a specific file.
    try:
        _record_session_files(saved_files, session_id, db, analyst_rules=analyst_rules)
    except Exception as exc:
        # Non-fatal: log and continue.  Export will fail gracefully if the
        # lookup returns no rows, returning a clear 404 to the user.
        print(f"[pipeline] session file recording error: {exc}")

    dataset_results: list[dict] = []
    pipeline_datasets: list[dict] = []  # fed to Stage 3 modules

    # ── Stages 1-2: profile and score each file ────────────────────────
    for sf in saved_files:
        display_name = sf["display_name"]

        try:
            profile = profiling.profile_dataset(sf["file_path"])
        except Exception as exc:
            raise PipelineError(display_name, "profile", exc) from exc

        try:
            score = scoring.score_dataset(profile)
        except Exception as exc:
            raise PipelineError(display_name, "score", exc) from exc

        dataset_results.append(
            {
                "original_filename": display_name,
                "saved_as": sf["saved_as"],
                "size_bytes": sf["size_bytes"],
                "profile": profile,
                "score": score,
            }
        )

        pipeline_datasets.append(
            {
                "file_path": sf["file_path"],
                "display_name": display_name,
                "profile": profile,
            }
        )

    # ── Stage 3: generate proposals ────────────────────────────────────
    all_proposals: list[dict] = []

    try:
        cross_fills = null_resolution.find_cross_dataset_fills(
            pipeline_datasets, session_id
        )
        all_proposals.extend(cross_fills)
    except Exception as exc:
        # Non-fatal: log and continue without cross-dataset proposals.
        print(f"[pipeline] null_resolution error: {exc}")

    for ds in pipeline_datasets:
        try:
            interp = interpolation.find_interpolation_proposals(
                ds["file_path"], ds["profile"], session_id, ds["display_name"]
            )
            all_proposals.extend(interp)
        except Exception as exc:
            print(f"[pipeline] interpolation error for '{ds['display_name']}': {exc}")

        try:
            corrections = data_corrections.find_correction_proposals(
                ds["file_path"], ds["profile"], session_id, ds["display_name"],
                analyst_rules=analyst_rules,
            )
            all_proposals.extend(corrections)
        except Exception as exc:
            print(f"[pipeline] data_corrections error for '{ds['display_name']}': {exc}")

    try:
        proposals.save_proposals(all_proposals, db)
    except Exception as exc:
        print(f"[pipeline] proposal save error: {exc}")

    proposals_summary = proposals.build_proposals_summary(all_proposals)

    return {
        "dataset_results": dataset_results,
        "proposals_summary": proposals_summary,
    }
