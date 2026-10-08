"""SQLAlchemy engine/session setup.

Uses SQLite in local mode and Postgres in remote mode (ADR 0003). The ORM models
are shared; only the engine URL changes.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


def _engine_url() -> str:
    # Local mode defaults to a SQLite file next to the server package.
    return get_settings().database_url


engine = create_engine(_engine_url(), connect_args={"check_same_thread": False} if "sqlite" in _engine_url() else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Import models so they register on Base.metadata."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
