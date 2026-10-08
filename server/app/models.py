"""ORM models for the digest service.

Multi-tenant-ready (ADR 0003): every user-owned record is scoped by ``user_id``.
Config is stored as a JSON blob (the same shape as ``arxiv_config.json`` /
``Config.dump``) so the mobile app and the CLI/GUI share one serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    config: Mapped["Config"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Config(Base):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    # JSON blob matching Config.dump() / arxiv_config.json shape.
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="config")


class RemovedPaper(Base):
    """A paper the user hid from the digest (ADR 0008). Not a score change."""

    __tablename__ = "removed_papers"
    __table_args__ = (UniqueConstraint("user_id", "arxiv_id", name="uq_removed_paper"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    arxiv_id: Mapped[str] = mapped_column(String(64))
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
