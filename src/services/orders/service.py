import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from src.models.commerce import (
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    OrderTransition,
    Reservation,
    ReservationItem,
    ReservationStatus,
)
from src.models.directions import Direction
from src.models.events import EventStatus, TicketType
from src.repositories.events import EventRepository
from src.repositories.orders import OrderRepository
from src.repositories.reservations import ReservationRepository
from src.services.commerce.clock import Clock, SystemClock


class InvalidOrderTransition(ValueError):
    pass


class _Missing:
    pass


_ALLOWED: dict[tuple[OrderStatus, OrderTransition], OrderStatus] = {
    (OrderStatus.PENDING_PAYMENT, OrderTransition.CONFIRM_PAYMENT): OrderStatus.PAID,
    (OrderStatus.PENDING_PAYMENT, OrderTransition.FAIL_PAYMENT): OrderStatus.PAYMENT_FAILED,
    (OrderStatus.PENDING_PAYMENT, OrderTransition.EXPIRE): OrderStatus.EXPIRED,
    (OrderStatus.PENDING_PAYMENT, OrderTransition.CANCEL): OrderStatus.CANCELLED,
    (
        OrderStatus.PENDING_PAYMENT,
        OrderTransition.REQUIRE_RECONCILIATION,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (OrderStatus.PAID, OrderTransition.REQUEST_REFUND): OrderStatus.REFUND_REQUESTED,
    (
        OrderStatus.PAID,
        OrderTransition.REQUIRE_RECONCILIATION,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (
        OrderStatus.PAYMENT_FAILED,
        OrderTransition.REQUIRE_RECONCILIATION,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (
        OrderStatus.EXPIRED,
        OrderTransition.REQUIRE_RECONCILIATION,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (
        OrderStatus.CANCELLED,
        OrderTransition.REQUIRE_RECONCILIATION,
    ): OrderStatus.RECONCILIATION_REQUIRED,
    (
        OrderStatus.RECONCILIATION_REQUIRED,
        OrderTransition.REQUEST_REFUND,
    ): OrderStatus.REFUND_REQUESTED,
    (OrderStatus.REFUND_REQUESTED, OrderTransition.CONFIRM_REFUND): OrderStatus.REFUNDED,
}

_REPLAYS = {
    (OrderStatus.PAID, OrderTransition.CONFIRM_PAYMENT),
    (OrderStatus.PAYMENT_FAILED, OrderTransition.FAIL_PAYMENT),
    (OrderStatus.EXPIRED, OrderTransition.EXPIRE),
    (OrderStatus.CANCELLED, OrderTransition.CANCEL),
    (OrderStatus.REFUND_REQUESTED, OrderTransition.REQUEST_REFUND),
    (OrderStatus.REFUNDED, OrderTransition.CONFIRM_REFUND),
    (OrderStatus.RECONCILIATION_REQUIRED, OrderTransition.REQUIRE_RECONCILIATION),
}


def next_state(state: OrderStatus | str, action: OrderTransition | str) -> OrderStatus:
    current = OrderStatus(state)
    transition = OrderTransition(action)
    if (current, transition) in _REPLAYS:
        return current
    try:
        return _ALLOWED[(current, transition)]
    except KeyError as exc:
        raise InvalidOrderTransition(
            f"Transition {transition.value} is not allowed from {current.value}"
        ) from exc


@dataclass(frozen=True)
class OrderItemInput:
    ticket_type_id: UUID
    quantity: int


@dataclass(frozen=True)
class OrderItemDTO:
    id: UUID
    ticket_type_id: UUID
    ticket_label: str
    quantity: int
    price_kopecks: int
    currency: str
    line_total_kopecks: int


@dataclass(frozen=True)
class PendingOrderDTO:
    order_id: UUID
    reservation_id: UUID
    status: OrderStatus
    expires_at: datetime
    total_kopecks: int
    currency: str
    items: tuple[OrderItemDTO, ...]


@dataclass(frozen=True)
class OrderDTO:
    id: UUID
    user_id: UUID
    event_id: UUID
    status: OrderStatus
    expires_at: datetime
    total_kopecks: int
    currency: str
    items: tuple[OrderItemDTO, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _validate_reason(reason: str) -> None:
    if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", reason):
        raise ValueError("Reason must be a bounded machine code")


class OrderService:
    def __init__(self, repository: OrderRepository, clock: Clock | None = None):
        self.repository = repository
        self.clock = clock or SystemClock()

    def _require_transaction(self) -> None:
        if not self.repository.session.in_transaction():
            raise RuntimeError("Order operations require a caller-owned transaction")

    @staticmethod
    def _item_dto(item: OrderItem) -> OrderItemDTO:
        return OrderItemDTO(
            item.id,
            item.ticket_type_id,
            item.ticket_label,
            item.quantity,
            item.price_kopecks,
            item.currency,
            item.line_total_kopecks,
        )

    @classmethod
    def _pending_dto(cls, order: Order) -> PendingOrderDTO:
        if order.reservation is None:
            raise RuntimeError("Pending order has no reservation")
        return PendingOrderDTO(
            order.id,
            order.reservation.id,
            OrderStatus(order.status),
            order.expires_at,
            order.total_kopecks,
            order.currency,
            tuple(cls._item_dto(item) for item in order.items),
        )

    @classmethod
    def _dto(cls, order: Order) -> OrderDTO:
        return OrderDTO(
            order.id,
            order.user_id,
            order.event_id,
            OrderStatus(order.status),
            order.expires_at,
            order.total_kopecks,
            order.currency,
            tuple(cls._item_dto(item) for item in order.items),
        )

    async def create_pending(
        self,
        user_id: UUID,
        event_id: UUID,
        items: list[OrderItemInput],
        now: datetime,
    ) -> PendingOrderDTO:
        self._require_transaction()
        now_utc = _utc(now)
        if not items:
            raise ValueError("Cart cannot be empty")
        if len({item.ticket_type_id for item in items}) != len(items):
            raise ValueError("Cart contains a duplicate ticket type")
        for item in items:
            if type(item.quantity) is not int or not 1 <= item.quantity <= 2_147_483_647:
                raise ValueError("Invalid ticket quantity")

        event = await EventRepository(self.repository.session).get_for_update(event_id)
        if event is None:
            raise LookupError("Event not found")
        if event.status != EventStatus.PUBLISHED:
            raise ValueError("Event is not available for checkout")
        direction_active = await self.repository.session.scalar(
            select(Direction.active).where(Direction.id == event.direction_id)
        )
        if not direction_active or event.starts_at <= now_utc or event.ends_at <= now_utc:
            raise ValueError("Event is not available for checkout")

        reservation_repository = ReservationRepository(self.repository.session)
        await self._release_expired_for_event(event.id, now_utc, reservation_repository)
        tickets = {ticket.id: ticket for ticket in event.ticket_types if ticket.active}
        if any(item.ticket_type_id not in tickets for item in items):
            raise ValueError("Unknown or inactive ticket type")
        occupied = await reservation_repository.occupied_by_ticket(event.id)
        total_quantity = sum(item.quantity for item in items)
        if sum(occupied.values()) + total_quantity > event.capacity:
            from src.services.reservations.service import CapacityExceeded

            raise CapacityExceeded("Event capacity exceeded")
        for item in items:
            if (
                occupied.get(item.ticket_type_id, 0) + item.quantity
                > tickets[item.ticket_type_id].limit
            ):
                from src.services.reservations.service import CapacityExceeded

                raise CapacityExceeded("Ticket type capacity exceeded")

        line_values: list[tuple[OrderItemInput, TicketType, int]] = []
        total = 0
        for item in items:
            ticket = tickets[item.ticket_type_id]
            line_total = ticket.price_kopecks * item.quantity
            if line_total > 9_223_372_036_854_775_807:
                raise ValueError("Order total is too large")
            total += line_total
            if total > 9_223_372_036_854_775_807:
                raise ValueError("Order total is too large")
            line_values.append((item, ticket, line_total))

        expires_at = now_utc + timedelta(seconds=600)
        order = Order(
            user_id=user_id,
            event_id=event.id,
            status=OrderStatus.PENDING_PAYMENT,
            total_kopecks=total,
            currency="RUB",
            expires_at=expires_at,
            created_at=now_utc,
            updated_at=now_utc,
        )
        for item_input, ticket, line_total in line_values:
            order.items.append(
                OrderItem(
                    ticket_type_id=item_input.ticket_type_id,
                    ticket_label=ticket.name,
                    quantity=item_input.quantity,
                    price_kopecks=ticket.price_kopecks,
                    currency=ticket.currency,
                    line_total_kopecks=line_total,
                )
            )
        self.repository.session.add(order)
        await self.repository.session.flush()
        reservation = Reservation(
            order_id=order.id,
            event_id=event.id,
            status=ReservationStatus.ACTIVE,
            expires_at=expires_at,
            created_at=now_utc,
            updated_at=now_utc,
        )
        order.reservation = reservation
        self.repository.session.add(reservation)
        await self.repository.session.flush()
        self.repository.session.add_all(
            [
                ReservationItem(
                    reservation_id=reservation.id,
                    order_item_id=item.id,
                    quantity=item.quantity,
                )
                for item in order.items
            ]
        )
        await self.repository.session.flush()
        await self.repository.add_event(
            order, None, OrderStatus.PENDING_PAYMENT.value, "create", "checkout_created", now_utc
        )
        return self._pending_dto(order)

    async def _release_expired_for_event(
        self,
        event_id: UUID,
        now: datetime,
        reservation_repository: ReservationRepository,
    ) -> int:
        due_ids = await reservation_repository.due_ids_for_event(event_id, now, 1_000_000)
        released = 0
        for reservation_id in due_ids:
            order_id = await self.repository.session.scalar(
                select(Reservation.order_id).where(Reservation.id == reservation_id)
            )
            if order_id is None:
                continue
            order = await self.repository.get_for_update(order_id)
            reservation = await reservation_repository.get_for_update(reservation_id)
            if reservation is None:
                continue
            if OrderStatus(order.status) == OrderStatus.PENDING_PAYMENT:
                self._apply_transition_locked(
                    order,
                    OrderTransition.EXPIRE,
                    "reservation_expired",
                    now,
                    reservation,
                    enforce_deadline=False,
                )
                released += 1
        return released

    async def transition(
        self, order_id: UUID, transition: OrderTransition, reason: str
    ) -> OrderDTO:
        self._require_transaction()
        _validate_reason(reason)
        now = _utc(self.clock.now())
        event_id = await self.repository.event_id(order_id)
        event = await EventRepository(self.repository.session).get_for_update(event_id)
        if event is None:
            raise LookupError("Event not found")
        order = await self.repository.get_for_update(order_id)
        reservation = order.reservation
        self._apply_transition_locked(order, transition, reason, now, reservation)
        await self.repository.save()
        return self._dto(order)

    def _apply_transition_locked(
        self,
        order: Order,
        transition: OrderTransition,
        reason: str,
        now: datetime,
        reservation: Reservation | None,
        *,
        enforce_deadline: bool = True,
    ) -> None:
        current = OrderStatus(order.status)
        transition = OrderTransition(transition)
        target = next_state(current, transition)
        if target == current:
            return
        if enforce_deadline and current == OrderStatus.PENDING_PAYMENT:
            if transition == OrderTransition.EXPIRE and now < order.expires_at:
                raise InvalidOrderTransition("Reservation has not expired")
            if transition == OrderTransition.CONFIRM_PAYMENT and now >= order.expires_at:
                raise InvalidOrderTransition("Payment confirmation arrived after expiry")
        if transition == OrderTransition.CONFIRM_PAYMENT:
            if reservation is None or reservation.status != ReservationStatus.ACTIVE:
                raise InvalidOrderTransition("Payment requires an active reservation")
            reservation.status = ReservationStatus.CONVERTED
            reservation.updated_at = now
        elif transition == OrderTransition.EXPIRE:
            if reservation is not None and reservation.status == ReservationStatus.ACTIVE:
                reservation.status = ReservationStatus.EXPIRED
                reservation.updated_at = now
        elif current == OrderStatus.PENDING_PAYMENT and transition in {
            OrderTransition.FAIL_PAYMENT,
            OrderTransition.CANCEL,
            OrderTransition.REQUIRE_RECONCILIATION,
        }:
            if reservation is not None and reservation.status == ReservationStatus.ACTIVE:
                reservation.status = ReservationStatus.RELEASED
                reservation.updated_at = now
        elif transition == OrderTransition.CONFIRM_REFUND:
            if reservation is not None and reservation.status == ReservationStatus.CONVERTED:
                reservation.status = ReservationStatus.RELEASED
                reservation.updated_at = now
        order.status = target
        order.updated_at = now
        self.repository.session.add(
            OrderEvent(
                order_id=order.id,
                previous_status=current.value,
                next_status=target.value,
                action=transition.value,
                reason=reason,
                created_at=now,
            )
        )
