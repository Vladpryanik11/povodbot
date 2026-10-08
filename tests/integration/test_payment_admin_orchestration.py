import asyncio
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from src.models.payments import Payment, PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.payments.admin import PaymentAdminService
from src.services.payments.dtos import (
    CreatePaymentResponse,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService, PaymentStateError
from src.services.reservations.service import ReservationItem
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class BlockingStatusGateway:
    order_id: str
    status_started: asyncio.Event = field(default_factory=asyncio.Event)
    status_release: asyncio.Event = field(default_factory=asyncio.Event)

    async def create_payment(self, request):
        return CreatePaymentResponse("unused", "https://pay/unused", "NEW", request.amount_minor)

    async def get_status(self, provider_payment_id: str):
        self.status_started.set()
        await self.status_release.wait()
        return ProviderPaymentStatus(
            provider_payment_id,
            "CONFIRMED",
            15000,
            raw={"OrderId": self.order_id},
        )

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


async def _unresolved_payment(session, *, provider_payment_id: str | None):
    event, user = await catalog(session)
    pending = await reservations(session).reserve(
        event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
    )
    payment_service = PaymentService(
        PaymentRepository(session), BlockingStatusGateway(str(pending.order_id)), FixedClock(NOW)
    )
    intent = await payment_service.prepare(pending.order_id)
    payment = await PaymentRepository(session).get_for_update(intent.payment_id)
    payment.status = PaymentStatus.RECONCILIATION_REQUIRED
    payment.provider_status = "INIT_UNKNOWN"
    payment.init_lease_until = None
    payment.provider_payment_id = provider_payment_id
    await session.flush()
    return payment.id, pending.order_id


async def test_reconcile_get_state_does_not_hold_payment_lock(pg_factory):
    async with pg_factory() as session, session.begin():
        payment_id, order_id = await _unresolved_payment(
            session, provider_payment_id="admin-reconcile-payment"
        )

    gateway = BlockingStatusGateway(str(order_id))
    admin = PaymentAdminService(pg_factory, gateway, FixedClock(NOW))
    reconcile_task = asyncio.create_task(admin.reconcile(payment_id))
    await asyncio.wait_for(gateway.status_started.wait(), timeout=2)

    async def acquire_payment_lock():
        async with pg_factory() as session, session.begin():
            payment = await session.scalar(
                select(Payment).where(Payment.id == payment_id).with_for_update()
            )
            assert payment is not None

    await asyncio.wait_for(acquire_payment_lock(), timeout=2)
    gateway.status_release.set()
    result = await asyncio.wait_for(reconcile_task, timeout=3)

    assert result.provider_payment_id == "admin-reconcile-payment"
    assert result.status == PaymentStatus.CONFIRMED


async def test_bind_rejects_provider_snapshot_before_persistence(pg_factory):
    async with pg_factory() as session, session.begin():
        payment_id, order_id = await _unresolved_payment(session, provider_payment_id=None)

    class WrongSnapshotGateway(BlockingStatusGateway):
        async def get_status(self, provider_payment_id: str):
            return ProviderPaymentStatus(
                provider_payment_id,
                "CONFIRMED",
                1,
                raw={"OrderId": str(order_id)},
            )

    admin = PaymentAdminService(pg_factory, WrongSnapshotGateway(str(order_id)), FixedClock(NOW))
    with pytest.raises(PaymentStateError, match="amount"):
        await admin.bind_provider_payment(payment_id, "bound-payment")

    async with pg_factory() as session:
        payment = await session.scalar(select(Payment).where(Payment.id == payment_id))
        assert payment is not None
        assert payment.provider_payment_id is None
