import secrets
import string
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow

SHORT_CODE_ALPHABET = string.ascii_letters + string.digits


def new_short_code() -> str:
    return "".join(secrets.choice(SHORT_CODE_ALPHABET) for _ in range(8))


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED_LIMIT = "skipped_limit"


class Campaign(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'running', 'completed', 'cancelled', 'stopped')",
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
    image: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: {"kind": "none"})
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_count: Mapped[int | None] = mapped_column(Integer)
    short_code: Mapped[str] = mapped_column(String(12), unique=True, default=new_short_code)
    telegram_photo_id: Mapped[str | None] = mapped_column(String(256))
    cancel_reason: Mapped[str | None] = mapped_column(String(64))


class CampaignDelivery(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'blocked', 'skipped_limit')", name="status"
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_campaign_deliveries_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_deliveries_user_sent", "user_id", "sent_at"),
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


class CampaignTemplate(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaign_templates"
    __table_args__ = (
        CheckConstraint("image_kind IN ('event', 'upload', 'none')", name="image_kind"),
    )
    name: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    image_kind: Mapped[str] = mapped_column(String(8), default="none")
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )


class CampaignLink(Base):
    __tablename__ = "campaign_links"
    __table_args__ = (UniqueConstraint("campaign_id", "button_index"),)
    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    button_index: Mapped[int] = mapped_column(SmallInteger)
    url: Mapped[str] = mapped_column(String(2048))


class CampaignClick(UUIDPrimaryKey, Base):
    __tablename__ = "campaign_clicks"
    __table_args__ = (Index("ix_campaign_clicks_campaign_user", "campaign_id", "user_id"),)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    button_index: Mapped[int] = mapped_column(SmallInteger)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    "CampaignClick",
    "CampaignDelivery",
    "CampaignLink",
    "CampaignStatus",
    "CampaignTemplate",
    "DeliveryStatus",
    "FunnelEvent",
    "new_short_code",
]
