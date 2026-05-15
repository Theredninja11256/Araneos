"""
Central application configuration.
All settings are read from environment variables or a .env file.
Defaults are safe for local MVP development with the pandas engine.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Engine ───────────────────────────────────────────────────────
    # "pandas" for MVP / local dev; "spark" for scale / production.
    engine_mode: str = "pandas"

    # ── File storage ──────────────────────────────────────────────────
    upload_dir: Path = Path("./uploads")
    max_file_size_mb: int = 50

    # ── API ───────────────────────────────────────────────────────────
    api_prefix: str = "/api/v1"
    debug: bool = False

    # ── LLM (wired up in Stage 5) ─────────────────────────────────────
    openai_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Single shared instance used across the app.
settings = Settings()
