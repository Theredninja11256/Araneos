"""
Engine selector — returns the configured processing engine.

The ENGINE_MODE environment variable (or .env file) controls which engine
is returned. Feature modules should call get_engine() rather than
instantiating an engine directly.

Supported values:
  pandas  — PandasEngine  (default, no extra dependencies)
  spark   — SparkEngine   (requires PySpark + Java 11+)
"""

from .base_engine import BaseEngine
from .pandas_engine import PandasEngine
from .spark_engine import SparkEngine


def get_engine() -> BaseEngine:
    """
    Return the appropriate engine instance based on the ENGINE_MODE setting.

    Import is deferred to avoid a circular import with app.core.config at
    module load time.
    """
    from app.core.config import settings

    mode = settings.engine_mode.strip().lower()

    if mode == "pandas":
        return PandasEngine()

    if mode == "spark":
        return SparkEngine()

    raise ValueError(
        f"Unknown ENGINE_MODE: '{mode}'. "
        "Valid options are 'pandas' or 'spark'. "
        "Check your .env file or environment variables."
    )
