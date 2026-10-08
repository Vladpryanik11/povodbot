from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class Campaign(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        CheckConstraint("length(trim(body)) > 0", name="body_nonempty"),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'running', 'completed', 'cancelled')",
            name="status",
        ),
    )
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=CampaignStatus.DRAFT)
    audience: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )


class CampaignDelivery(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed', 'blocked')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_campaign_deliveries_campaign_status", "campaign_id", "status"),
    )
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=DeliveryStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(256), unique=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(String(512))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attribution(UUIDPrimaryKey, Base):
    __tablename__ = "attributions"
    __table_args__ = (Index("ix_attributions_latest_start", "latest_start_param"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    first_start_param: Mapped[str | None] = mapped_column(String(64))
    latest_start_param: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    latest_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    first_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FunnelEvent(UUIDPrimaryKey, Base):
    __tablename__ = "funnel_events"
    __table_args__ = (Index("ix_funnel_events_user_occurred", "user_id", "occurred_at"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_name: Mapped[str] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "Attribution",
    "Campaign",
    "CampaignDelivery",
    "CampaignStatus",
    "DeliveryStatus",
    "FunnelEvent",
]
