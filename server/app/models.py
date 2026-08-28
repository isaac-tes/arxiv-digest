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
    lists: Mapped[list["SavedList"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Config(Base):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    # JSON blob matching Config.dump() / arxiv_config.json shape.
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="config")


class SavedList(Base):
    __tablename__ = "saved_lists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_list_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="lists")
    papers: Mapped[list["ListPaper"]] = relationship(back_populates="list", cascade="all, delete-orphan")


class ListPaper(Base):
    __tablename__ = "list_papers"
    __table_args__ = (UniqueConstraint("list_id", "arxiv_id", name="uq_list_paper"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("saved_lists.id"), index=True)
    arxiv_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    list: Mapped["SavedList"] = relationship(back_populates="papers")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    arxiv_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16))  # star | dismiss | penalize
    signal: Mapped[str] = mapped_column(String(32), default="keyword")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
