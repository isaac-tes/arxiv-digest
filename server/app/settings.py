"""Runtime settings for the digest service.

The same code runs in two modes (ADR 0003):
- **local**: SQLite, single-user, no-op auth (development / personal use).
- **remote**: Postgres, multi-user, JWT auth (deployable / public).

Mode is selected by the ``DIGEST_MODE`` env var; everything else has a sensible
default so ``uvicorn app.main:app`` works out of the box in local mode.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (parent of server/) so we can import the shared arxiv_digest.py core.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIGEST_", env_file=".env", extra="ignore")

    mode: str = "local"  # "local" | "remote"
    database_url: str = "sqlite:///./digest.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    cors_origins: list[str] = ["*"]
    # Optional path to a JSON config file (e.g. a saved GUI profile) used as the
    # default config when a user has no stored config. Lets the mobile app score
    # with the same preferences as the web GUI out of the box.
    default_config_path: str = ""

    @property
    def is_remote(self) -> bool:
        return self.mode == "remote"


@lru_cache
def get_settings() -> Settings:
    return Settings()
