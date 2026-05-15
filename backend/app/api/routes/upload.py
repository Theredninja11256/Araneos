"""
Dataset upload endpoint.

Responsibilities of this module:
  1. Validate each uploaded file (extension, size).
  2. Save each file to disk.
  3. Delegate all analysis to app.features.pipeline.run_analysis_pipeline().
  4. Return the HTTP response.

No profiling, scoring, or proposal logic lives here.
All orchestration is in app/features/pipeline.py.
"""

import json
import time
import uuid
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.analyst_rules import AnalystRulesInput
from app.features.pipeline import PipelineError, run_analysis_pipeline
from app.models.database import get_db

router = APIRouter(prefix="/datasets", tags=["datasets"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post("/upload")
async def upload_datasets(
    files: List[UploadFile] = File(...),
    analyst_rules: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Upload one or more insurance dataset files.

    Validates each file, saves it to disk, then runs the full Stage 1-3
    analysis pipeline.  Returns profiling results, reliability scores, and
    a summary of generated null-fill proposals.

    Use GET /api/v1/proposals/{session_id} to retrieve the full proposal list.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    saved_files: list[dict] = []

    # ── Validate and save each file ────────────────────────────────────
    for file in files:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File '{file.filename}' is not supported. "
                    "Only CSV and Excel files (.csv, .xlsx, .xls) are accepted."
                ),
            )

        content = await file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File '{file.filename}' is {size_mb:.1f} MB, which exceeds "
                    f"the {settings.max_file_size_mb} MB limit."
                ),
            )

        timestamp = int(time.time())
        safe_name = f"{timestamp}_{file.filename}"
        save_path = settings.upload_dir / safe_name

        async with aiofiles.open(save_path, "wb") as out_file:
            await out_file.write(content)

        saved_files.append(
            {
                "file_path": str(save_path),
                "saved_as": safe_name,
                "display_name": file.filename,
                "size_bytes": len(content),
            }
        )

    # ── Parse analyst rules ────────────────────────────────────────────
    rules_dict: dict | None = None
    if analyst_rules:
        try:
            rules_input = AnalystRulesInput.model_validate(json.loads(analyst_rules))
            rules_dict  = rules_input.to_dict()
        except Exception:
            rules_dict = None  # Silently use defaults on parse error.

    # ── Run analysis pipeline ──────────────────────────────────────────
    try:
        result = run_analysis_pipeline(saved_files, session_id, db, analyst_rules=rules_dict)
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "session_id": session_id,
        "uploaded": len(saved_files),
        "datasets": result["dataset_results"],
        "proposals_summary": result["proposals_summary"],
    }
