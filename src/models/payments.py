from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow
from src.models.commerce import Order


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    AUTHORIZED = "authorized"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDING = "refunding"
    REFUNDED = "refunded"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class Payment(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("provider = 'tbank'", name="provider"),
        CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'authorized', 'confirmed', 'failed', "
            "'cancelled', 'refunding', 'refunded', 'reconciliation_required')",
            name="status",
        ),
        Index("ix_payments_provider_payment_id", "provider", "provider_payment_id"),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="tbank")
    provider_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default=PaymentStatus.PENDING)
    provider_status: Mapped[str | None] = mapped_column(String(64))
    payment_url: Mapped[str | None] = mapped_column(String(2048))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order: Mapped["Order"] = relationship(back_populates="payment")
    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin"
    )


class PaymentEvent(UUIDPrimaryKey, Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        CheckConstraint("length(trim(provider)) > 0", name="provider_nonempty"),
        CheckConstraint("length(trim(deduplication_key)) > 0", name="deduplication_key_nonempty"),
        Index("ix_payment_events_payment_received", "payment_id", "received_at"),
        Index("ix_payment_events_provider_payment", "provider", "provider_payment_id"),
    )
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(32), default="tbank")
    provider_payment_id: Mapped[str] = mapped_column(String(64))
    deduplication_key: Mapped[str] = mapped_column(String(256), unique=True)
    provider_status: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ignored_reason: Mapped[str | None] = mapped_column(String(128))
    payment: Mapped["Payment | None"] = relationship(back_populates="events")


__all__ = ["Payment", "PaymentEvent", "PaymentStatus"]
