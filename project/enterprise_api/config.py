"""Environment configuration utilities.

- Loads configuration from environment variables.
- Optionally loads a local .env file if python-dotenv is installed.

We intentionally keep this minimal and do not require external keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv_if_available(env_path: str | None = None) -> None:
    """Load a .env file if python-dotenv is installed.

    This is optional to avoid adding dependencies; it will no-op if python-dotenv
    is not installed.
    """

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    if env_path:
        load_dotenv(env_path, override=False)
        return

    # Search for .env in repo root (two levels up from project/enterprise_api)
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / ".env"
    if candidate.exists():
        load_dotenv(str(candidate), override=False)


@dataclass(frozen=True)
class Settings:
    database_url: str
    enterprise_db_path: str
    enterprise_api_key: str
    metrics_enabled: bool


def get_settings() -> Settings:
    """Get settings with sane defaults."""
    base_dir = Path(__file__).resolve().parents[1]  # .../project
    default_db_path = base_dir / "enterprise.db"
    database_url = os.getenv("DATABASE_URL") or f"sqlite:///{default_db_path}"

    api_key = os.getenv("ENTERPRISE_API_KEY") or ""
    metrics_enabled = os.getenv("ENTERPRISE_METRICS_ENABLED", "1") not in {"0", "false", "False"}

    return Settings(
        database_url=database_url,
        enterprise_db_path=str(default_db_path),
        enterprise_api_key=api_key,
        metrics_enabled=metrics_enabled,
    )
