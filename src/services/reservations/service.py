from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from src.models.commerce import (
    OrderTransition,
    Reservation,
    ReservationStatus,
)
from src.repositories.events import EventRepository
from src.repositories.orders import OrderRepository
from src.repositories.reservations import ReservationRepository
from src.services.commerce.clock import Clock, SystemClock
from src.services.orders.service import OrderItemDTO, OrderItemInput, OrderService


class CapacityExceeded(ValueError):
    pass


@dataclass(frozen=True)
class ReservationItem:
    ticket_type_id: UUID
    quantity: int


@dataclass(frozen=True)
class ReservationResult:
    reservation_id: UUID
    order_id: UUID
    expires_at: datetime
    items: tuple[OrderItemDTO, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


class ReservationService:
    def __init__(self, repository: ReservationRepository, clock: Clock | None = None):
        self.repository = repository
        self.clock = clock or SystemClock()

    def _require_transaction(self) -> None:
        if not self.repository.session.in_transaction():
            raise RuntimeError("Reservation operations require a caller-owned transaction")

    async def reserve(
        self,
        event_id: UUID,
        items: list[ReservationItem],
        user_id: UUID,
        now: datetime,
    ) -> ReservationResult:
        self._require_transaction()
        if not items:
            raise ValueError("Cart cannot be empty")
        if len({item.ticket_type_id for item in items}) != len(items):
            raise ValueError("Cart contains a duplicate ticket type")
        pending = await OrderService(
            OrderRepository(self.repository.session), self.clock
        ).create_pending(
            user_id,
            event_id,
            [OrderItemInput(item.ticket_type_id, item.quantity) for item in items],
            now,
        )
        return ReservationResult(
            pending.reservation_id, pending.order_id, pending.expires_at, pending.items
        )

    async def release_expired(self, now: datetime, limit: int) -> int:
        self._require_transaction()
        now_utc = _utc(now)
        if type(limit) is not int or limit <= 0:
            raise ValueError("Expiry limit must be a positive integer")
        released = 0
        order_service = OrderService(OrderRepository(self.repository.session), self.clock)
        for event_id in await self.repository.due_event_ids(now_utc):
            if released >= limit:
                break
            event = await EventRepository(self.repository.session).get_for_update(
                event_id, skip_locked=True
            )
            if event is None:
                continue
            due_ids = await self.repository.due_ids_for_event(event_id, now_utc, limit - released)
            for reservation_id in due_ids:
                order_id = await self.repository.session.scalar(
                    select(Reservation.order_id).where(Reservation.id == reservation_id)
                )
                if order_id is None:
                    continue
                order = await order_service.repository.get_for_update(order_id, skip_locked=True)
                if order is None:
                    continue
                reservation = await self.repository.get_for_update(reservation_id, skip_locked=True)
                if reservation is None:
                    continue
                if (
                    order.status == "pending_payment"
                    and reservation.status == ReservationStatus.ACTIVE
                ):
                    order_service._apply_transition_locked(
                        order,
                        OrderTransition.EXPIRE,
                        "reservation_expired",
                        now_utc,
                        reservation,
                        enforce_deadline=False,
                    )
                    released += 1
        await order_service.repository.save()
        return released
