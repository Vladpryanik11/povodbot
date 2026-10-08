from datetime import datetime
from enum import StrEnum
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDPrimaryKey, utcnow


class TicketStatus(StrEnum):
    ISSUED = "issued"
    CHECKED_IN = "checked_in"
    VOIDED = "voided"


class Ticket(UUIDPrimaryKey, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        CheckConstraint("status IN ('issued', 'checked_in', 'voided')", name="status"),
        Index("ix_tickets_event_status", "event_id", "status"),
        Index("ix_tickets_order_item_position", "order_item_id", "position", unique=True),
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    ticket_type_id: Mapped[UUID] = mapped_column(ForeignKey("ticket_types.id", ondelete="RESTRICT"))
    # Validated by the migration trigger; a direct FK would make PostgreSQL
    # reject the required immutable TRUNCATE before our history trigger runs.
    order_item_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(256))
    price_kopecks: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.ISSUED)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_by: Mapped[UUID | None] = mapped_column()
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
    checkin: Mapped["Checkin | None"] = relationship(
        back_populates="ticket", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class Checkin(UUIDPrimaryKey, Base):
    __tablename__ = "checkins"
    __table_args__ = (Index("ix_checkins_ticket_checked_at", "ticket_id", "checked_at"),)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), unique=True
    )
    actor_id: Mapped[UUID] = mapped_column()
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(32), default="qr")
    ticket: Mapped[Ticket] = relationship(back_populates="checkin")


__all__ = ["Checkin", "Ticket", "TicketStatus"]
