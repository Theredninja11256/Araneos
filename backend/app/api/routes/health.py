"""
Health check endpoint.
Used to confirm the API is running and to surface the active engine mode.
"""

from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "engine_mode": settings.engine_mode,
        "version": "0.1.0",
    }
