from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDPrimaryKey, utcnow


class Outbox(UUIDPrimaryKey, Base):
    """Storage foundation only; delivery/worker behavior belongs to later tasks."""

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_outbox_pending", "processed_at", "available_at"),
    )
    event_type: Mapped[str] = mapped_column(String(128))
    deduplication_key: Mapped[str] = mapped_column(String(256), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
