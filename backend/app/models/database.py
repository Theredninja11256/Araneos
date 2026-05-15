"""
SQLAlchemy database configuration.

Uses SQLite for the MVP.  The file is written to the backend working directory
as data_platform.db.  For production, swap the DATABASE_URL for a Postgres URI
and remove the check_same_thread argument.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./data_platform.db"

engine = create_engine(
    DATABASE_URL,
    # SQLite requires this flag when used across multiple threads (FastAPI workers).
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _apply_migrations() -> None:
    """
    Lightweight schema migrations for SQLite MVP.

    SQLAlchemy's create_all only creates missing tables, not missing columns.
    For each additive schema change, we try an ALTER TABLE and swallow the
    OperationalError that SQLite raises when the column already exists.
    """
    from sqlalchemy import text

    migrations = [
        "ALTER TABLE upload_sessions ADD COLUMN analyst_rules_json TEXT",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists or table doesn't exist yet — both are fine.


def get_db():
    """
    FastAPI dependency that yields a database session and closes it afterwards.

    Usage in route:
        @router.get("/...")
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
