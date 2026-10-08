from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow

if TYPE_CHECKING:
    from src.models.payments import Payment


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class OrderTransition(StrEnum):
    CONFIRM_PAYMENT = "confirm_payment"
    FAIL_PAYMENT = "fail_payment"
    EXPIRE = "expire"
    CANCEL = "cancel"
    REQUEST_REFUND = "request_refund"
    CONFIRM_REFUND = "confirm_refund"
    REQUIRE_RECONCILIATION = "require_reconciliation"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"
    RELEASED = "released"


class Order(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'paid', 'payment_failed', 'expired', "
            "'cancelled', 'refund_requested', 'refunded', 'reconciliation_required')",
            name="status",
        ),
        CheckConstraint("total_kopecks >= 0", name="total_nonnegative"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        Index("ix_orders_event_status", "event_id", "status"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PENDING_PAYMENT)
    total_kopecks: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    reservation: Mapped["Reservation | None"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderEvent.sequence",
        lazy="selectin",
    )
    payment: Mapped["Payment | None"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(UUIDPrimaryKey, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price_kopecks >= 0", name="price_nonnegative"),
        CheckConstraint("line_total_kopecks >= 0", name="line_total_nonnegative"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        Index("ix_order_items_order_id", "order_id"),
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    ticket_type_id: Mapped[UUID] = mapped_column(ForeignKey("ticket_types.id", ondelete="RESTRICT"))
    ticket_label: Mapped[str] = mapped_column(String(256))
    quantity: Mapped[int] = mapped_column(Integer)
    price_kopecks: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    line_total_kopecks: Mapped[int] = mapped_column(BigInteger)
    order: Mapped[Order] = relationship(back_populates="items")


class Reservation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_reservations_order_id"),
        CheckConstraint("status IN ('active', 'converted', 'expired', 'released')", name="status"),
        Index("ix_reservations_expiry", "event_id", "status", "expires_at"),
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default=ReservationStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order: Mapped[Order] = relationship(back_populates="reservation")
    items: Mapped[list["ReservationItem"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", lazy="selectin"
    )


class ReservationItem(UUIDPrimaryKey, Base):
    __tablename__ = "reservation_items"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_reservation_items_order_item_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey("reservations.id", ondelete="RESTRICT"))
    # Migration 0003 uses a validating trigger instead of an FK: PostgreSQL
    # checks TRUNCATE references before the immutable history trigger can run.
    order_item_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[int] = mapped_column(Integer)
    reservation: Mapped[Reservation] = relationship(back_populates="items")


class OrderEvent(UUIDPrimaryKey, Base):
    __tablename__ = "order_events"
    __table_args__ = (
        UniqueConstraint("sequence", name="uq_order_events_sequence"),
        CheckConstraint("length(trim(action)) > 0", name="action_nonempty"),
        CheckConstraint("length(trim(reason)) > 0 AND length(reason) <= 64", name="reason_bounded"),
        Index("ix_order_events_order_sequence", "order_id", "sequence"),
    )
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    previous_status: Mapped[str | None] = mapped_column(String(32))
    next_status: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    order: Mapped[Order] = relationship(back_populates="events")
