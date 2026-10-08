from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from src.models.commerce import (
    Order,
    OrderStatus,
    OrderTransition,
    Reservation,
    ReservationStatus,
)
from src.models.payments import Payment, PaymentEvent, PaymentStatus
from src.repositories.orders import OrderRepository
from src.repositories.payments import PaymentRepository
from src.services.commerce.clock import Clock, SystemClock
from src.services.orders.service import InvalidOrderTransition, OrderService
from src.services.payments.dtos import (
    CreatePaymentRequest,
    PaymentCheckoutDTO,
    PaymentDTO,
    PaymentWebhookDTO,
)
from src.services.payments.ports import PaymentGateway

CONFIRMED_STATUSES = {"CONFIRMED"}
AUTHORIZED_STATUSES = {"AUTHORIZED"}
FAILED_STATUSES = {"REJECTED", "DEADLINE_EXPIRED", "CANCELED", "REVERSED"}
REFUNDING_STATUSES = {"REFUNDING", "PARTIAL_REFUNDED"}
REFUNDED_STATUSES = {"REFUNDED"}
KNOWN_STATUSES = (
    CONFIRMED_STATUSES
    | AUTHORIZED_STATUSES
    | FAILED_STATUSES
    | REFUNDING_STATUSES
    | REFUNDED_STATUSES
    | {
        "NEW",
        "FORM_SHOWED",
        "3DS_CHECKING",
        "3DS_CHECKED",
        "AUTHORIZING",
        "CONFIRMING",
        "REVERSING",
    }
)


class PaymentStateError(ValueError):
    pass


@dataclass(frozen=True)
class PaymentApplicationResult:
    accepted: bool
    duplicate: bool
    payment_id: UUID | None
    payment_status: PaymentStatus | None
    order_status: OrderStatus | None
    reason: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _safe_payload(payload: dict[str, Any]) -> dict[str, object]:
    blocked = {"Token", "Password", "Pan", "CardId", "ExpDate", "RebillId"}
    result: dict[str, object] = {}
    for key, value in payload.items():
        if key in blocked or isinstance(value, (dict, list)):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
    return result


class PaymentService:
    def __init__(
        self,
        repository: PaymentRepository,
        gateway: PaymentGateway,
        clock: Clock | None = None,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.clock = clock or SystemClock()

    def _require_transaction(self) -> None:
        if not self.repository.session.in_transaction():
            raise RuntimeError("Payment operations require a caller-owned transaction")

    @staticmethod
    def _dto(payment: Payment) -> PaymentDTO:
        return PaymentDTO(
            id=payment.id,
            order_id=payment.order_id,
            provider_payment_id=payment.provider_payment_id,
            status=PaymentStatus(payment.status),
            provider_status=payment.provider_status,
            amount_minor=payment.amount_kopecks,
            payment_url=payment.payment_url,
        )

    @staticmethod
    def _local_initial_status(provider_status: str) -> PaymentStatus:
        normalized = provider_status.upper()
        if normalized in AUTHORIZED_STATUSES:
            return PaymentStatus.AUTHORIZED
        if normalized in CONFIRMED_STATUSES:
            # A create response is not payment proof; only a verified webhook or
            # reconciliation may move the order to paid.
            return PaymentStatus.PROCESSING
        if normalized in FAILED_STATUSES:
            return PaymentStatus.FAILED
        return PaymentStatus.PROCESSING

    async def start(self, order_id: UUID) -> PaymentCheckoutDTO:
        self._require_transaction()
        now = _utc(self.clock.now())
        order = await OrderRepository(self.repository.session).get_for_update(order_id)
        if OrderStatus(order.status) != OrderStatus.PENDING_PAYMENT:
            raise PaymentStateError("Only pending orders can start payment")
        reservation = order.reservation
        if reservation is None:
            reservation = await self.repository.session.scalar(
                select(Reservation).where(Reservation.order_id == order.id).with_for_update()
            )
        if (
            reservation is None
            or reservation.status != ReservationStatus.ACTIVE
            or now >= reservation.expires_at
        ):
            raise PaymentStateError("Order does not have an active reservation")

        existing = await self.repository.by_order_for_update(order.id)
        if existing is not None and existing.provider_payment_id and existing.payment_url:
            return PaymentCheckoutDTO(
                existing.id,
                existing.order_id,
                existing.provider_payment_id,
                existing.payment_url,
                PaymentStatus(existing.status),
            )

        response = await self.gateway.create_payment(
            CreatePaymentRequest(
                order_id=order.id,
                amount_minor=order.total_kopecks,
                description=f"Повод — заказ {order.id}",
                redirect_due_date=order.expires_at,
            )
        )
        if response.amount_minor is not None and response.amount_minor != order.total_kopecks:
            raise PaymentStateError("Provider amount does not match the order")
        if not response.provider_payment_id or not response.payment_url:
            raise PaymentStateError("Provider response is missing payment identity")

        if existing is None:
            payment = Payment(
                order_id=order.id,
                provider="tbank",
                provider_payment_id=response.provider_payment_id,
                amount_kopecks=order.total_kopecks,
                currency=order.currency,
                status=self._local_initial_status(response.provider_status),
                provider_status=response.provider_status,
                payment_url=response.payment_url,
            )
            self.repository.session.add(payment)
        else:
            payment = existing
            payment.provider_payment_id = response.provider_payment_id
            payment.provider_status = response.provider_status
            payment.payment_url = response.payment_url
            payment.status = self._local_initial_status(response.provider_status)
        await self.repository.save()
        return PaymentCheckoutDTO(
            payment.id,
            payment.order_id,
            response.provider_payment_id,
            response.payment_url,
            PaymentStatus(payment.status),
        )

    async def apply_webhook(self, event: PaymentWebhookDTO) -> PaymentApplicationResult:
        self._require_transaction()
        now = _utc(self.clock.now())
        normalized = event.provider_status.upper().strip()
        if not event.provider_payment_id:
            raise PaymentStateError("Webhook payment id is required")

        existing_event = await self.repository.event_by_key(event.deduplication_key)
        if existing_event is not None:
            payment = (
                await self.repository.by_provider_payment_for_update(event.provider_payment_id)
                if existing_event.payment_id
                else None
            )
            return PaymentApplicationResult(
                accepted=True,
                duplicate=True,
                payment_id=existing_event.payment_id,
                payment_status=PaymentStatus(payment.status) if payment else None,
                order_status=None,
                reason="duplicate_event",
            )

        payment = await self.repository.by_provider_payment_for_update(event.provider_payment_id)
        if payment is None:
            self.repository.session.add(
                PaymentEvent(
                    provider="tbank",
                    provider_payment_id=event.provider_payment_id,
                    deduplication_key=event.deduplication_key,
                    provider_status=normalized,
                    payload=_safe_payload(event.payload),
                    received_at=now,
                    applied_at=now,
                    ignored_reason="unknown_payment",
                )
            )
            await self.repository.save()
            return PaymentApplicationResult(True, False, None, None, None, "unknown_payment")

        # Re-check after the payment row lock so two concurrent deliveries of
        # the same provider event serialize without applying it twice.
        existing_event = await self.repository.event_by_key(event.deduplication_key)
        if existing_event is not None:
            return PaymentApplicationResult(
                True,
                True,
                payment.id,
                PaymentStatus(payment.status),
                None,
                "duplicate_event",
            )

        payment_event = PaymentEvent(
            payment_id=payment.id,
            provider="tbank",
            provider_payment_id=event.provider_payment_id,
            deduplication_key=event.deduplication_key,
            provider_status=normalized,
            payload=_safe_payload(event.payload),
            received_at=now,
        )
        self.repository.session.add(payment_event)
        payment.provider_status = normalized

        if event.amount_minor is not None and event.amount_minor != payment.amount_kopecks:
            payment.status = PaymentStatus.RECONCILIATION_REQUIRED
            payment_event.ignored_reason = "amount_mismatch"
            order_status = await self._require_reconciliation(
                payment.order_id, "payment_amount_mismatch"
            )
            payment_event.applied_at = now
            await self.repository.save()
            return PaymentApplicationResult(
                True,
                False,
                payment.id,
                PaymentStatus(payment.status),
                order_status,
                "amount_mismatch",
            )

        if normalized not in KNOWN_STATUSES:
            payment.status = PaymentStatus.RECONCILIATION_REQUIRED
            payment_event.ignored_reason = "unknown_provider_status"
            order_status = await self._require_reconciliation(payment.order_id, "provider_unknown")
            payment_event.applied_at = now
            await self.repository.save()
            return PaymentApplicationResult(
                True,
                False,
                payment.id,
                PaymentStatus(payment.status),
                order_status,
                "unknown_provider_status",
            )

        if normalized in CONFIRMED_STATUSES:
            order_status = await self._apply_confirmed(payment, now)
            payment.status = (
                PaymentStatus.CONFIRMED
                if order_status == OrderStatus.PAID
                else PaymentStatus.RECONCILIATION_REQUIRED
            )
            reason = "payment_confirmed" if order_status == OrderStatus.PAID else "late_payment"
        elif normalized in AUTHORIZED_STATUSES:
            payment.status = PaymentStatus.AUTHORIZED
            order_status = await self._order_status(payment.order_id)
            reason = "payment_authorized"
        elif normalized in FAILED_STATUSES:
            order_status = await self._apply_failed(payment, now)
            payment.status = (
                PaymentStatus.FAILED
                if order_status in {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_FAILED}
                else PaymentStatus.RECONCILIATION_REQUIRED
            )
            reason = "payment_failed"
        elif normalized in REFUNDING_STATUSES:
            payment.status = PaymentStatus.REFUNDING
            order_status = await self._order_status(payment.order_id)
            reason = "refund_started"
        else:
            order_status = await self._apply_refunded(payment, now)
            payment.status = (
                PaymentStatus.REFUNDED
                if order_status == OrderStatus.REFUNDED
                else PaymentStatus.RECONCILIATION_REQUIRED
            )
            reason = (
                "payment_refunded" if order_status == OrderStatus.REFUNDED else "refund_reconcile"
            )

        if payment.status == PaymentStatus.CONFIRMED:
            payment.paid_at = now
            from src.services.tickets.issuer import TicketIssuer

            await TicketIssuer(self.repository.session).issue_for_paid_order(payment.order_id)
        if payment.status == PaymentStatus.REFUNDED:
            payment.refunded_at = now
            from src.services.tickets.checkin import TicketService

            await TicketService(self.repository.session).void_for_order(payment.order_id)
        payment_event.applied_at = now
        await self.repository.save()
        return PaymentApplicationResult(
            True, False, payment.id, PaymentStatus(payment.status), order_status, reason
        )

    async def _order_status(self, order_id: UUID) -> OrderStatus:
        value = await self.repository.session.scalar(
            select(Order.status).where(Order.id == order_id)
        )
        if value is None:
            raise LookupError("Order not found")
        return OrderStatus(value)

    async def _transition(
        self, order_id: UUID, transition: OrderTransition, reason: str
    ) -> OrderStatus:
        order_service = OrderService(OrderRepository(self.repository.session), self.clock)
        try:
            dto = await order_service.transition(order_id, transition, reason)
        except InvalidOrderTransition:
            return await self._order_status(order_id)
        return dto.status

    async def _require_reconciliation(self, order_id: UUID, reason: str) -> OrderStatus:
        return await self._transition(order_id, OrderTransition.REQUIRE_RECONCILIATION, reason)

    async def _apply_confirmed(self, payment: Payment, now: datetime) -> OrderStatus:
        status = await self._order_status(payment.order_id)
        if status == OrderStatus.PAID:
            return status
        if status == OrderStatus.PENDING_PAYMENT:
            order = await OrderRepository(self.repository.session).get_for_update(payment.order_id)
            reservation = order.reservation
            if reservation is None:
                reservation = await self.repository.session.scalar(
                    select(Reservation).where(Reservation.order_id == order.id).with_for_update()
                )
            if (
                reservation is not None
                and reservation.status == ReservationStatus.ACTIVE
                and now < reservation.expires_at
            ):
                return await self._transition(
                    payment.order_id, OrderTransition.CONFIRM_PAYMENT, "payment_confirmed"
                )
        return await self._require_reconciliation(payment.order_id, "late_payment")

    async def _apply_failed(self, payment: Payment, now: datetime) -> OrderStatus:
        del now
        status = await self._order_status(payment.order_id)
        if status in {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_FAILED}:
            return await self._transition(
                payment.order_id, OrderTransition.FAIL_PAYMENT, "payment_failed"
            )
        return await self._require_reconciliation(payment.order_id, "payment_failed_late")

    async def _apply_refunded(self, payment: Payment, now: datetime) -> OrderStatus:
        del now
        status = await self._order_status(payment.order_id)
        if status == OrderStatus.REFUNDED:
            return status
        if status == OrderStatus.PAID:
            await self._transition(
                payment.order_id, OrderTransition.REQUEST_REFUND, "refund_requested"
            )
            status = OrderStatus.REFUND_REQUESTED
        if status == OrderStatus.REFUND_REQUESTED:
            return await self._transition(
                payment.order_id, OrderTransition.CONFIRM_REFUND, "refund_confirmed"
            )
        if status == OrderStatus.RECONCILIATION_REQUIRED:
            await self._transition(
                payment.order_id, OrderTransition.REQUEST_REFUND, "refund_requested"
            )
            return await self._transition(
                payment.order_id, OrderTransition.CONFIRM_REFUND, "refund_confirmed"
            )
        return await self._require_reconciliation(payment.order_id, "refund_late")

    async def reconcile(self, payment_id: UUID) -> PaymentDTO:
        self._require_transaction()
        payment = await self.repository.get_for_update(payment_id)
        if not payment.provider_payment_id:
            raise PaymentStateError("Payment has no provider identity")
        provider_status = await self.gateway.get_status(payment.provider_payment_id)
        await self.apply_webhook(
            PaymentWebhookDTO(
                provider_payment_id=provider_status.provider_payment_id,
                provider_status=provider_status.provider_status,
                amount_minor=provider_status.amount_minor,
                payload=provider_status.raw,
            )
        )
        return self._dto(payment)

    async def request_refund(self, payment_id: UUID, reason: str) -> PaymentDTO:
        self._require_transaction()
        if not reason or len(reason) > 64:
            raise ValueError("Refund reason is required")
        payment = await self.repository.get_for_update(payment_id)
        if not payment.provider_payment_id:
            raise PaymentStateError("Payment has no provider identity")
        if PaymentStatus(payment.status) == PaymentStatus.REFUNDED:
            return self._dto(payment)
        if PaymentStatus(payment.status) not in {PaymentStatus.CONFIRMED, PaymentStatus.REFUNDING}:
            raise PaymentStateError("Only confirmed payments can be refunded")
        result = await self.gateway.refund(
            payment.provider_payment_id, payment.amount_kopecks, reason
        )
        payment.provider_status = result.provider_status
        payment.status = PaymentStatus.REFUNDING
        await self._transition(payment.order_id, OrderTransition.REQUEST_REFUND, "refund_requested")
        await self.repository.save()
        return self._dto(payment)
