import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.models.payments import Payment, PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.payments.checkout import PaymentCheckoutService
from src.services.payments.dtos import (
    CreatePaymentResponse,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService, PaymentStateError
from src.services.reservations.service import ReservationItem
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class BlockingGateway:
    calls: int = 0
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def create_payment(self, request):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            await self.release.wait()
        return CreatePaymentResponse(
            "blocking-payment",
            "https://pay/blocking",
            "NEW",
            request.amount_minor,
            {"OrderId": str(request.order_id)},
        )

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "NEW")

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


@dataclass
class RecoveryGateway(BlockingGateway):
    find_calls: int = 0

    async def create_payment(self, request):
        self.calls += 1
        raise AssertionError("expired Init lease must recover instead of calling Init")

    async def find_by_order(self, order_id: str):
        self.find_calls += 1
        return ProviderPaymentStatus(
            "recovered-payment",
            "NEW",
            15000,
            raw={"OrderId": order_id},
        )


async def _pending_order(session):
    event, user = await catalog(session)
    pending = await reservations(session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    return pending


def _total_kopecks(pending) -> int:
    return sum(item.line_total_kopecks for item in pending.items)


async def test_concurrent_checkout_claims_call_provider_init_once(pg_factory):
    async with pg_factory() as session, session.begin():
        pending = await _pending_order(session)

    gateway = BlockingGateway()
    clock = FixedClock(NOW)
    first_task = asyncio.create_task(
        PaymentCheckoutService(pg_factory, gateway, clock).start(pending.order_id)
    )
    await asyncio.wait_for(gateway.started.wait(), timeout=2)

    second = await asyncio.wait_for(
        PaymentCheckoutService(pg_factory, gateway, clock).start(pending.order_id), timeout=2
    )
    assert second.payment_url is None
    assert gateway.calls == 1

    gateway.release.set()
    first = await asyncio.wait_for(first_task, timeout=2)
    assert first.payment_url == "https://pay/blocking"


async def test_expired_init_lease_recovers_without_second_provider_init(pg_factory):
    async with pg_factory() as session, session.begin():
        pending = await _pending_order(session)
        intent = await PaymentService(
            PaymentRepository(session), BlockingGateway(), FixedClock(NOW)
        ).prepare(pending.order_id)
        payment_id = intent.payment_id

    clock = FixedClock(NOW + timedelta(seconds=61))
    gateway = RecoveryGateway()
    checkout = await PaymentCheckoutService(pg_factory, gateway, clock).start(pending.order_id)

    assert checkout.payment_id == payment_id
    assert checkout.provider_payment_id == "recovered-payment"
    assert checkout.payment_url is None
    assert gateway.calls == 0
    assert gateway.find_calls == 1

    async with pg_factory() as session, session.begin():
        payment = await session.scalar(select(Payment).where(Payment.id == payment_id))
        assert payment is not None
        assert payment.provider_payment_id == "recovered-payment"
        assert PaymentStatus(payment.status) == PaymentStatus.RECONCILIATION_REQUIRED


async def test_late_matching_init_response_is_attached_idempotently(db_session):
    pending = await _pending_order(db_session)
    clock = FixedClock(NOW)
    service = PaymentService(PaymentRepository(db_session), BlockingGateway(), clock)
    intent = await service.prepare(pending.order_id)
    payment = await PaymentRepository(db_session).get_for_update(intent.payment_id)
    payment.status = PaymentStatus.RECONCILIATION_REQUIRED
    payment.provider_status = "INIT_UNKNOWN"
    payment.init_lease_until = None
    await db_session.flush()

    response = CreatePaymentResponse(
        "late-payment",
        "https://pay/late",
        "NEW",
        _total_kopecks(pending),
        {"OrderId": str(pending.order_id)},
    )
    first = await service.complete_init(payment.id, response)
    second = await service.complete_init(payment.id, response)

    assert first.provider_payment_id == "late-payment"
    assert second.payment_url == "https://pay/late"
    assert payment.init_lease_until is None


async def test_init_rejects_provider_amount_mismatch_without_binding(db_session):
    pending = await _pending_order(db_session)
    service = PaymentService(PaymentRepository(db_session), BlockingGateway(), FixedClock(NOW))
    intent = await service.prepare(pending.order_id)

    with pytest.raises(PaymentStateError, match="amount"):
        await service.complete_init(
            intent.payment_id,
            CreatePaymentResponse(
                "wrong-amount",
                "https://pay/wrong",
                "NEW",
                _total_kopecks(pending) + 1,
                {"OrderId": str(pending.order_id)},
            ),
        )

    payment = await PaymentRepository(db_session).get_for_update(intent.payment_id)
    assert payment.provider_payment_id is None


async def test_init_rejects_provider_order_mismatch_without_binding(db_session):
    pending = await _pending_order(db_session)
    service = PaymentService(PaymentRepository(db_session), BlockingGateway(), FixedClock(NOW))
    intent = await service.prepare(pending.order_id)

    with pytest.raises(PaymentStateError, match="order"):
        await service.complete_init(
            intent.payment_id,
            CreatePaymentResponse(
                "wrong-order",
                "https://pay/wrong",
                "NEW",
                _total_kopecks(pending),
                {"OrderId": "another-order"},
            ),
        )

    payment = await PaymentRepository(db_session).get_for_update(intent.payment_id)
    assert payment.provider_payment_id is None
