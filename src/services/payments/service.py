from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from src.models.outbox import Outbox
from src.models.payments import Payment, PaymentEvent, PaymentStatus
from src.repositories.events import EventRepository
from src.repositories.orders import OrderRepository
from src.repositories.payments import PaymentRepository
from src.services.analytics.attribution import AttributionService, FunnelEventName
from src.services.commerce.clock import Clock, SystemClock
from src.services.orders.service import InvalidOrderTransition, OrderService
from src.services.payments.dtos import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentCheckoutDTO,
    PaymentDTO,
    PaymentWebhookDTO,
    ProviderPaymentStatus,
)
from src.services.payments.ports import PaymentGateway, PaymentGatewayError

CONFIRMED_STATUSES = {"CONFIRMED"}
AUTHORIZED_STATUSES = {"AUTHORIZED"}
FAILED_STATUSES = {"REJECTED", "DEADLINE_EXPIRED", "CANCELED", "REVERSED"}
REFUNDING_STATUSES = {"REFUNDING", "PARTIAL_REFUNDED"}
REFUNDED_STATUSES = {"REFUNDED"}
IN_PROGRESS_STATUSES = {
    "NEW",
    "FORM_SHOWED",
    "3DS_CHECKING",
    "3DS_CHECKED",
    "AUTHORIZING",
    "CONFIRMING",
}
KNOWN_STATUSES = (
    CONFIRMED_STATUSES
    | AUTHORIZED_STATUSES
    | FAILED_STATUSES
    | REFUNDING_STATUSES
    | REFUNDED_STATUSES
    | IN_PROGRESS_STATUSES
    | {"REVERSING"}
)
# Once the money is taken, the bank may still deliver earlier statuses out of order.
SETTLED_PROVIDER_STATUSES = CONFIRMED_STATUSES | REFUNDING_STATUSES | REFUNDED_STATUSES
SETTLED_LOCAL_STATUSES = {PaymentStatus.CONFIRMED, PaymentStatus.REFUNDING, PaymentStatus.REFUNDED}
PAYMENT_INIT_LEASE = timedelta(seconds=60)


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


@dataclass(frozen=True)
class PaymentInitIntent:
    payment_id: UUID
    order_id: UUID
    request: CreatePaymentRequest | None
    checkout: PaymentCheckoutDTO
    recovery_required: bool = False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _safe_payload(payload: dict[str, Any]) -> dict[str, object]:
    blocked = {
        "token",
        "password",
        "pan",
        "apikey",
        "authorization",
        "cookie",
        "cardid",
        "expdate",
        "rebillid",
        "cvv",
        "cvc",
    }

    def scrub(value: object, key: str = "") -> object | None:
        if key.lower().replace("_", "") in blocked:
            return None
        if isinstance(value, dict):
            return {
                str(child_key): scrub(child_value, str(child_key))
                for child_key, child_value in value.items()
                if str(child_key).lower().replace("_", "") not in blocked
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return None

    return {
        str(key): scrub(value, str(key))
        for key, value in payload.items()
        if str(key).lower().replace("_", "") not in blocked
    }


class PaymentService:
    def __init__(
        self,
        repository: PaymentRepository,
        gateway: PaymentGateway | None,
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

    @staticmethod
    def _validate_provider_snapshot(payment: Payment, provider: ProviderPaymentStatus) -> None:
        if (
            payment.provider_payment_id is not None
            and provider.provider_payment_id != payment.provider_payment_id
        ):
            raise PaymentStateError("Provider payment identity does not match")
        if provider.amount_minor is not None and provider.amount_minor != payment.amount_kopecks:
            raise PaymentStateError("Provider amount does not match the payment")
        raw_order_id = next(
            (
                value
                for key, value in provider.raw.items()
                if str(key).lower().replace("_", "") == "orderid"
            ),
            None,
        )
        if raw_order_id is not None and str(raw_order_id) != str(payment.order_id):
            raise PaymentStateError("Provider order does not match the payment")

    async def prepare(self, order_id: UUID) -> PaymentInitIntent:
        self._require_transaction()
        now = _utc(self.clock.now())
        order_repository = OrderRepository(self.repository.session)
        event_id = await order_repository.event_id(order_id)
        event = await EventRepository(self.repository.session).get_for_update(event_id)
        if event is None:
            raise LookupError("Event not found")
        order = await order_repository.get_for_update(order_id)
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
            checkout = PaymentCheckoutDTO(
                existing.id,
                existing.order_id,
                existing.provider_payment_id,
                existing.payment_url,
                PaymentStatus(existing.status),
            )
            return PaymentInitIntent(existing.id, existing.order_id, None, checkout)
        if (
            existing is not None
            and PaymentStatus(existing.status) == PaymentStatus.RECONCILIATION_REQUIRED
        ):
            raise PaymentStateError("Payment initialization requires reconciliation")
        if existing is not None and existing.provider_payment_id:
            checkout = PaymentCheckoutDTO(
                existing.id,
                existing.order_id,
                existing.provider_payment_id,
                existing.payment_url,
                PaymentStatus(existing.status),
            )
            return PaymentInitIntent(existing.id, existing.order_id, None, checkout)

        if existing is not None:
            existing_status = PaymentStatus(existing.status)
            lease_active = existing.init_lease_until is not None and now < _utc(
                existing.init_lease_until
            )
            if lease_active:
                checkout = PaymentCheckoutDTO(
                    existing.id,
                    existing.order_id,
                    None,
                    None,
                    existing_status,
                )
                return PaymentInitIntent(existing.id, existing.order_id, None, checkout)
            if existing_status == PaymentStatus.PROCESSING:
                existing.status = PaymentStatus.RECONCILIATION_REQUIRED
                existing.provider_status = "INIT_UNKNOWN"
                existing.init_lease_until = None
                await self.repository.save()
                checkout = PaymentCheckoutDTO(
                    existing.id,
                    existing.order_id,
                    None,
                    None,
                    PaymentStatus(existing.status),
                )
                return PaymentInitIntent(
                    existing.id,
                    existing.order_id,
                    None,
                    checkout,
                    recovery_required=True,
                )

        if existing is None:
            payment = Payment(
                order_id=order.id,
                provider="tbank",
                amount_kopecks=order.total_kopecks,
                currency=order.currency,
                status=PaymentStatus.PROCESSING,
                provider_status="INIT_IN_PROGRESS",
                init_lease_until=now + PAYMENT_INIT_LEASE,
            )
            self.repository.session.add(payment)
            await self.repository.save()
        else:
            payment = existing
            payment.status = PaymentStatus.PROCESSING
            payment.provider_status = "INIT_IN_PROGRESS"
            payment.init_lease_until = now + PAYMENT_INIT_LEASE
            await self.repository.save()

        request = CreatePaymentRequest(
            order_id=order.id,
            amount_minor=order.total_kopecks,
            description=f"Повод — заказ {order.id}",
            redirect_due_date=order.expires_at,
        )
        return PaymentInitIntent(
            payment.id,
            payment.order_id,
            request,
            PaymentCheckoutDTO(
                payment.id, payment.order_id, None, None, PaymentStatus(payment.status)
            ),
        )

    async def complete_init(
        self, payment_id: UUID, response: CreatePaymentResponse
    ) -> PaymentCheckoutDTO:
        self._require_transaction()
        payment = await self.repository.get_for_update(payment_id)
        if response.amount_minor is not None and response.amount_minor != payment.amount_kopecks:
            raise PaymentStateError("Provider amount does not match the order")
        if not response.provider_payment_id or not response.payment_url:
            raise PaymentStateError("Provider response is missing payment identity")
        raw_order_id = next(
            (
                value
                for key, value in response.raw.items()
                if str(key).lower().replace("_", "") == "orderid"
            ),
            None,
        )
        if raw_order_id is not None and str(raw_order_id) != str(payment.order_id):
            raise PaymentStateError("Provider order does not match the payment")
        if payment.provider_payment_id is not None:
            if payment.provider_payment_id != response.provider_payment_id:
                raise PaymentStateError("Provider payment identity is already linked")
            if payment.payment_url is None:
                payment.payment_url = response.payment_url
            payment.init_lease_until = None
        else:
            payment.provider_payment_id = response.provider_payment_id
            payment.provider_status = response.provider_status
            payment.payment_url = response.payment_url
            payment.status = self._local_initial_status(response.provider_status)
            payment.init_lease_until = None
        await self.repository.save()
        return PaymentCheckoutDTO(
            payment.id,
            payment.order_id,
            payment.provider_payment_id,
            payment.payment_url,
            PaymentStatus(payment.status),
        )

    async def mark_init_unknown(self, payment_id: UUID) -> PaymentCheckoutDTO:
        self._require_transaction()
        payment = await self.repository.get_for_update(payment_id)
        payment.status = PaymentStatus.RECONCILIATION_REQUIRED
        payment.provider_status = "INIT_UNKNOWN"
        payment.init_lease_until = None
        await self.repository.save()
        return PaymentCheckoutDTO(
            payment.id,
            payment.order_id,
            payment.provider_payment_id,
            payment.payment_url,
            PaymentStatus(payment.status),
        )

    async def attach_recovered_init(
        self, payment_id: UUID, recovered: ProviderPaymentStatus
    ) -> PaymentCheckoutDTO:
        self._require_transaction()
        payment = await self.repository.get_for_update(payment_id)
        if not recovered.provider_payment_id:
            raise PaymentStateError("Recovered provider payment identity is missing")
        if recovered.amount_minor is not None and recovered.amount_minor != payment.amount_kopecks:
            raise PaymentStateError("Recovered provider amount does not match the order")
        raw_order_id = next(
            (
                value
                for key, value in recovered.raw.items()
                if str(key).lower().replace("_", "") == "orderid"
            ),
            None,
        )
        if raw_order_id is not None and str(raw_order_id) != str(payment.order_id):
            raise PaymentStateError("Recovered provider order does not match the order")
        if (
            payment.provider_payment_id is not None
            and payment.provider_payment_id != recovered.provider_payment_id
        ):
            raise PaymentStateError("Provider payment identity is already linked")
        payment.provider_payment_id = recovered.provider_payment_id
        payment.provider_status = recovered.provider_status
        payment.status = PaymentStatus.RECONCILIATION_REQUIRED
        payment.init_lease_until = None
        await self.repository.save()
        return PaymentCheckoutDTO(
            payment.id,
            payment.order_id,
            payment.provider_payment_id,
            None,
            PaymentStatus(payment.status),
        )

    async def start(self, order_id: UUID) -> PaymentCheckoutDTO:
        """Legacy single-session helper retained for service-level callers.

        Production request handlers use :class:`PaymentCheckoutService`, which
        commits the local intent before calling T-Bank and stores the provider
        result in a second transaction. This helper keeps the original service
        contract for small in-process integrations and tests.
        """
        intent = await self.prepare(order_id)
        if intent.request is None:
            return intent.checkout
        gateway = self.gateway
        if gateway is None:
            raise RuntimeError("Payment gateway is required to start payment")

        try:
            response = await gateway.create_payment(intent.request)
        except PaymentGatewayError:
            # The provider may have accepted Init before the response was
            # lost. Persist an unresolved state and never issue Init twice
            # for the same local order without reconciliation.
            finder = getattr(gateway, "find_by_order", None)
            if callable(finder):
                try:
                    recovered = await finder(str(intent.order_id))
                except PaymentGatewayError:
                    recovered = None
                if recovered is not None:
                    return await self.attach_recovered_init(intent.payment_id, recovered)
            return await self.mark_init_unknown(intent.payment_id)
        return await self.complete_init(intent.payment_id, response)

    async def apply_webhook(self, event: PaymentWebhookDTO) -> PaymentApplicationResult:
        self._require_transaction()
        now = _utc(self.clock.now())
        normalized = event.provider_status.upper().strip()
        if not event.provider_payment_id:
            raise PaymentStateError("Webhook payment id is required")

        existing_event = await self.repository.event_by_key(event.deduplication_key)
        if existing_event is not None:
            payment = (
                await self.repository.by_id(existing_event.payment_id)
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

        unlocked_payment = await self.repository.by_provider_payment(event.provider_payment_id)
        requested_order_id: UUID | None = None
        if event.order_id:
            try:
                requested_order_id = UUID(event.order_id)
            except ValueError:
                requested_order_id = None

        order_id: UUID | None
        if unlocked_payment is not None:
            if requested_order_id is not None and requested_order_id != unlocked_payment.order_id:
                raise PaymentStateError("Webhook order does not match the payment")
            order_id = unlocked_payment.order_id
        else:
            order_id = requested_order_id

        payment = None
        if order_id is not None:
            order_repository = OrderRepository(self.repository.session)
            try:
                event_id = await order_repository.event_id(order_id)
            except LookupError:
                event_id = None
            if event_id is not None:
                await EventRepository(self.repository.session).get_for_update(event_id)
                await order_repository.get_for_update(order_id)
                if unlocked_payment is not None:
                    payment = await self.repository.by_provider_payment_for_update(
                        event.provider_payment_id
                    )
                else:
                    payment = await self.repository.by_order_for_update(order_id)

                existing_event = await self.repository.event_by_key(event.deduplication_key)
                if existing_event is not None:
                    duplicate_payment = (
                        await self.repository.by_id(existing_event.payment_id)
                        if existing_event.payment_id
                        else None
                    )
                    return PaymentApplicationResult(
                        accepted=True,
                        duplicate=True,
                        payment_id=existing_event.payment_id,
                        payment_status=(
                            PaymentStatus(duplicate_payment.status) if duplicate_payment else None
                        ),
                        order_status=None,
                        reason="duplicate_event",
                    )

        if payment is not None:
            if (
                payment.provider_payment_id is not None
                and payment.provider_payment_id != event.provider_payment_id
            ):
                raise PaymentStateError("Provider payment identity does not match")
            if payment.provider_payment_id is None:
                payment.provider_payment_id = event.provider_payment_id

        if payment is None:
            unknown_event = PaymentEvent(
                provider="tbank",
                provider_payment_id=event.provider_payment_id,
                deduplication_key=event.deduplication_key,
                provider_status=normalized,
                payload=_safe_payload(event.payload),
                received_at=now,
                applied_at=now,
                ignored_reason="unknown_payment",
            )
            inserted = await self.repository.insert_payment_event_if_absent(unknown_event)
            if not inserted:
                existing_event = await self.repository.event_by_key(event.deduplication_key)
                duplicate_payment = (
                    await self.repository.by_id(existing_event.payment_id)
                    if existing_event is not None and existing_event.payment_id
                    else None
                )
                return PaymentApplicationResult(
                    accepted=True,
                    duplicate=True,
                    payment_id=(existing_event.payment_id if existing_event else None),
                    payment_status=(
                        PaymentStatus(duplicate_payment.status) if duplicate_payment else None
                    ),
                    order_status=None,
                    reason="duplicate_event",
                )
            return PaymentApplicationResult(True, False, None, None, None, "unknown_payment")

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
        stale_reason = self._stale_reason(payment, normalized)
        if stale_reason is not None:
            payment_event.ignored_reason = stale_reason
            payment_event.applied_at = now
            await self.repository.save()
            return PaymentApplicationResult(
                True,
                False,
                payment.id,
                PaymentStatus(payment.status),
                await self._order_status(payment.order_id),
                stale_reason,
            )
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
        elif normalized in REFUNDED_STATUSES:
            order_status = await self._apply_refunded(payment, now)
            payment.status = (
                PaymentStatus.REFUNDED
                if order_status == OrderStatus.REFUNDED
                else PaymentStatus.RECONCILIATION_REQUIRED
            )
            reason = (
                "payment_refunded" if order_status == OrderStatus.REFUNDED else "refund_reconcile"
            )
        else:
            payment.status = PaymentStatus.PROCESSING
            order_status = await self._order_status(payment.order_id)
            reason = "payment_processing"

        if payment.status == PaymentStatus.CONFIRMED:
            payment.paid_at = now
            user_id = await self.repository.session.scalar(
                select(Order.user_id).where(Order.id == payment.order_id)
            )
            if user_id is not None:
                attribution = AttributionService(self.repository.session)
                await attribution.record_purchase(user_id, now)
                await attribution.record_funnel_event(
                    user_id, FunnelEventName.PURCHASE, occurred_at=now
                )
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

    @staticmethod
    def _stale_reason(payment: Payment, normalized: str) -> str | None:
        settled = (
            payment.provider_status in SETTLED_PROVIDER_STATUSES
            or payment.status in SETTLED_LOCAL_STATUSES
        )
        if normalized in AUTHORIZED_STATUSES | IN_PROGRESS_STATUSES and settled:
            return "stale_status"
        if normalized in REFUNDING_STATUSES and payment.status == PaymentStatus.REFUNDED:
            return "stale_status"
        if normalized not in KNOWN_STATUSES and settled:
            return "unknown_status"
        return None

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
            # OrderService.transition owns the canonical event -> order ->
            # reservation lock order. Do not pre-lock the order here: expiry
            # already holds the event lock before it reaches the order.
            result = await self._transition(
                payment.order_id, OrderTransition.CONFIRM_PAYMENT, "payment_confirmed"
            )
            if result == OrderStatus.PAID:
                return result
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
        payment = await self.repository.by_id(payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if not payment.provider_payment_id:
            raise PaymentStateError("Payment has no provider identity")
        gateway = self.gateway
        if gateway is None:
            raise RuntimeError("Payment gateway is required to reconcile payment")
        provider_status = await gateway.get_status(payment.provider_payment_id)
        await self.apply_webhook(
            PaymentWebhookDTO(
                provider_payment_id=provider_status.provider_payment_id,
                provider_status=provider_status.provider_status,
                amount_minor=provider_status.amount_minor,
                payload=provider_status.raw,
            )
        )
        updated = await self.repository.by_id(payment_id)
        if updated is None:
            raise LookupError("Payment not found")
        return self._dto(updated)

    async def bind_provider_payment(self, payment_id: UUID, provider_payment_id: str) -> PaymentDTO:
        self._require_transaction()
        provider_payment_id = provider_payment_id.strip()
        if not provider_payment_id or len(provider_payment_id) > 64:
            raise PaymentStateError("Provider payment id is invalid")
        payment = await self.repository.by_id(payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if PaymentStatus(payment.status) != PaymentStatus.RECONCILIATION_REQUIRED:
            raise PaymentStateError("Only unresolved payments can be bound")
        gateway = self.gateway
        if gateway is None:
            raise RuntimeError("Payment gateway is required to bind payment")
        provider = await gateway.get_status(provider_payment_id)
        return await self.bind_provider_snapshot(
            payment_id,
            provider,
            expected_provider_payment_id=provider_payment_id,
        )

    async def bind_provider_snapshot(
        self,
        payment_id: UUID,
        provider: ProviderPaymentStatus,
        *,
        expected_provider_payment_id: str | None = None,
    ) -> PaymentDTO:
        self._require_transaction()
        provider_payment_id = provider.provider_payment_id.strip()
        if not provider_payment_id or len(provider_payment_id) > 64:
            raise PaymentStateError("Provider payment id is invalid")
        if (
            expected_provider_payment_id is not None
            and provider_payment_id != expected_provider_payment_id
        ):
            raise PaymentStateError("Provider payment identity does not match")
        payment = await self.repository.get_for_update(payment_id)
        if PaymentStatus(payment.status) != PaymentStatus.RECONCILIATION_REQUIRED:
            raise PaymentStateError("Only unresolved payments can be bound")
        if (
            payment.provider_payment_id is not None
            and payment.provider_payment_id != provider_payment_id
        ):
            raise PaymentStateError("Provider payment id is already linked")
        other = await self.repository.by_provider_payment(provider_payment_id)
        if other is not None and other.id != payment.id:
            raise PaymentStateError("Provider payment id is already linked")
        self._validate_provider_snapshot(payment, provider)
        payment.provider_payment_id = provider_payment_id
        payment.provider_status = provider.provider_status
        payment.status = PaymentStatus.PROCESSING
        payment.init_lease_until = None
        await self.repository.save()
        return self._dto(payment)

    async def request_refund(self, payment_id: UUID, reason: str) -> PaymentDTO:
        """Persist a refund command; the provider call runs in the worker.

        Keeping the command in the same transaction as the local state change
        prevents an HTTP rollback from losing the fact that a refund was
        requested. The worker performs a provider status lookup before Cancel,
        so a retry after an ambiguous response does not blindly issue a second
        refund.
        """
        self._require_transaction()
        if not reason or len(reason) > 64:
            raise ValueError("Refund reason is required")
        payment = await self.repository.by_id(payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        order_repository = OrderRepository(self.repository.session)
        event_id = await order_repository.event_id(payment.order_id)
        await EventRepository(self.repository.session).get_for_update(event_id)
        await order_repository.get_for_update(payment.order_id)
        payment = await self.repository.get_for_update(payment_id)
        if not payment.provider_payment_id:
            raise PaymentStateError("Payment has no provider identity")
        if PaymentStatus(payment.status) == PaymentStatus.REFUNDED:
            return self._dto(payment)
        if PaymentStatus(payment.status) == PaymentStatus.REFUNDING:
            # The provider operation may already have been accepted while its
            # response was lost. Reconcile by webhook/status instead of
            # sending a second Cancel request.
            return self._dto(payment)
        if PaymentStatus(payment.status) != PaymentStatus.CONFIRMED:
            raise PaymentStateError("Only confirmed payments can be refunded")
        payment.status = PaymentStatus.REFUNDING
        await self._transition(payment.order_id, OrderTransition.REQUEST_REFUND, "refund_requested")
        existing_command = await self.repository.session.scalar(
            select(Outbox).where(Outbox.deduplication_key == f"payment:refund:{payment.id}")
        )
        if existing_command is None:
            self.repository.session.add(
                Outbox(
                    event_type="payment.refund",
                    deduplication_key=f"payment:refund:{payment.id}",
                    payload={
                        "payment_id": str(payment.id),
                        "provider_payment_id": payment.provider_payment_id,
                        "amount_minor": payment.amount_kopecks,
                        "reason": reason,
                    },
                )
            )
        payment.provider_status = "REFUND_QUEUED"
        await self.repository.save()
        return self._dto(payment)
