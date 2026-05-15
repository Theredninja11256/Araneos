"""
Data Platform — FastAPI entry point.

Run with:
    uvicorn main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, upload
from app.api.routes import proposals as proposals_route
from app.api.routes import sessions as sessions_route
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create required directories and database tables on startup."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # Import all ORM models before create_all so SQLAlchemy registers their
    # table definitions with the shared Base metadata.
    from app.models.database import Base, engine as db_engine
    from app.models import proposal, upload_session  # noqa: F401

    Base.metadata.create_all(bind=db_engine)

    from app.models.database import _apply_migrations
    _apply_migrations()

    yield
    # Nothing to tear down for MVP.


app = FastAPI(
    title="Data Platform API",
    description="AI-powered insurance data intelligence and cleaning platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Vite dev server (and any configured prod origin) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(upload.router, prefix=settings.api_prefix)
app.include_router(proposals_route.router, prefix=settings.api_prefix)
app.include_router(sessions_route.router, prefix=settings.api_prefix)
