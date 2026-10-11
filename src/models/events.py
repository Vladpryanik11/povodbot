from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, Timestamps, UUIDPrimaryKey


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Event(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        CheckConstraint("length(trim(description)) > 0", name="description_nonempty"),
        CheckConstraint("length(trim(address)) > 0", name="address_nonempty"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint("ends_at > starts_at", name="date_order"),
        CheckConstraint("cover_focus_x BETWEEN 0 AND 1", name="cover_focus_x_range"),
        CheckConstraint("cover_focus_y BETWEEN 0 AND 1", name="cover_focus_y_range"),
        CheckConstraint("accent_color ~ '^#[0-9A-Fa-f]{6}$'", name="accent_color_hex"),
        CheckConstraint("length(trim(timezone)) > 0", name="timezone_nonempty"),
        CheckConstraint(
            "status IN ('draft', 'published', 'cancelled', 'completed')", name="status"
        ),
        CheckConstraint(
            "(status = 'draft' AND published_at IS NULL) OR "
            "(status <> 'draft' AND published_at IS NOT NULL)",
            name="publication",
        ),
        Index("ix_events_showcase", "status", "starts_at", "direction_id"),
    )
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    cover_ref: Mapped[str | None] = mapped_column(String(2048))
    direction_id: Mapped[UUID] = mapped_column(ForeignKey("directions.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(1024))
    map_url: Mapped[str | None] = mapped_column(String(2048))
    cover_focus_x: Mapped[float] = mapped_column(
        Numeric(4, 3, asdecimal=False), default=0.5, server_default=text("0.5")
    )
    cover_focus_y: Mapped[float] = mapped_column(
        Numeric(4, 3, asdecimal=False), default=0.5, server_default=text("0.5")
    )
    cover_width: Mapped[int | None]
    cover_height: Mapped[int | None]
    accent_color: Mapped[str | None] = mapped_column(String(7))
    capacity: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default=EventStatus.DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ticket_types: Mapped[list["TicketType"]] = relationship(lazy="raise", order_by="TicketType.id")


class TicketType(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ticket_types"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("price_kopecks >= 0", name="price_nonnegative"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        CheckConstraint('"limit" > 0', name="limit_positive"),
        Index("ix_ticket_types_event_id", "event_id"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(256))
    price_kopecks: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    limit: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)
