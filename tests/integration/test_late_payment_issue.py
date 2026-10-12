from dataclasses import dataclass
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from src.api.admin import payments as admin_payments
from src.api.app import create_app
from src.models.admin import AdminAuditLog, AdminUser
from src.models.commerce import Order, OrderStatus, Reservation, ReservationStatus
from src.models.outbox import Outbox
from src.models.payments import Payment, PaymentStatus
from src.models.tickets import Ticket
from src.repositories.payments import PaymentRepository
from src.repositories.users import UserRepository
from src.services.admin.permissions import AdminActor
from src.services.payments.admin import PaymentAdminService
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService, PaymentStateError
from src.services.reservations.service import CapacityExceeded, ReservationItem
from src.services.users.service import UserService
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


@dataclass
class Gateway:
    """GetState answers with what the operator would see in the bank's cabinet."""

    status: str = "CONFIRMED"
    amount: int = 15000

    async def create_payment(self, request):
        return CreatePaymentResponse(
            "late-payment", "https://pay/late", "NEW", request.amount_minor
        )

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, self.status, self.amount)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDED")

    async def aclose(self):
        return None


@dataclass
class Late:
    payment_id: object
    order_id: object
    event: object
    paid_at: object


async def late_payment(pg_factory, capacity=2) -> Late:
    """The guest paid after the reservation ran out; the seat went back on sale."""
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session, capacity=capacity)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, NOW
        )
        clock = FixedClock(NOW)
        payments = PaymentService(PaymentRepository(session), Gateway(), clock)
        checkout = await payments.start(pending.order_id)
        clock.value = pending.expires_at
        await payments.apply_webhook(
            PaymentWebhookDTO("late-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
        )
    return Late(checkout.payment_id, pending.order_id, event, pending.expires_at)


def admin(pg_factory, gateway, now):
    return PaymentAdminService(pg_factory, gateway, FixedClock(now))


async def state(pg_factory, late: Late):
    async with pg_factory() as session:
        payment = await session.get(Payment, late.payment_id)
        order = await session.get(Order, late.order_id)
        reservation = await session.scalar(
            select(Reservation).where(Reservation.order_id == late.order_id)
        )
        tickets = list(
            await session.scalars(select(Ticket).where(Ticket.order_id == late.order_id))
        )
        job = await session.scalar(
            select(Outbox).where(Outbox.deduplication_key == f"ticket:issued:{late.order_id}")
        )
    return payment, order, reservation, tickets, job


async def test_late_payment_issue_converts_order_and_issues_tickets(pg_factory):
    late = await late_payment(pg_factory)

    result = await admin(
        pg_factory, Gateway(), late.paid_at + timedelta(minutes=5)
    ).issue_late_payment(late.payment_id)

    payment, order, reservation, tickets, job = await state(pg_factory, late)
    assert result.status == PaymentStatus.CONFIRMED
    assert PaymentStatus(payment.status) == PaymentStatus.CONFIRMED
    assert payment.paid_at is not None
    assert OrderStatus(order.status) == OrderStatus.PAID
    assert ReservationStatus(reservation.status) == ReservationStatus.CONVERTED
    assert len(tickets) == 1
    assert job is not None


async def test_late_payment_issue_refuses_when_sold_out(pg_factory):
    late = await late_payment(pg_factory, capacity=1)
    async with pg_factory() as session, session.begin():
        other = await UserService(UserRepository(session)).upsert_telegram_user(
            200, None, None, None, None
        )
        await reservations(session).reserve(
            late.event.id,
            [ReservationItem(late.event.ticket_types[0].id, 1)],
            other.id,
            late.paid_at,
        )

    with pytest.raises(CapacityExceeded):
        await admin(pg_factory, Gateway(), late.paid_at + timedelta(minutes=1)).issue_late_payment(
            late.payment_id
        )

    payment, order, reservation, tickets, job = await state(pg_factory, late)
    assert OrderStatus(order.status) == OrderStatus.RECONCILIATION_REQUIRED
    assert PaymentStatus(payment.status) == PaymentStatus.RECONCILIATION_REQUIRED
    assert ReservationStatus(reservation.status) == ReservationStatus.RELEASED
    assert tickets == []
    assert job is None


async def test_late_payment_issue_requires_confirmed_provider_state(pg_factory):
    late = await late_payment(pg_factory)

    with pytest.raises(PaymentStateError):
        await admin(
            pg_factory, Gateway(status="REJECTED"), late.paid_at + timedelta(minutes=5)
        ).issue_late_payment(late.payment_id)

    _, order, _, tickets, _ = await state(pg_factory, late)
    assert OrderStatus(order.status) == OrderStatus.RECONCILIATION_REQUIRED
    assert tickets == []


async def test_late_payment_issue_rejects_amount_mismatch(pg_factory):
    late = await late_payment(pg_factory)

    with pytest.raises(PaymentStateError):
        await admin(
            pg_factory, Gateway(amount=10000), late.paid_at + timedelta(minutes=5)
        ).issue_late_payment(late.payment_id)

    _, order, _, tickets, _ = await state(pg_factory, late)
    assert OrderStatus(order.status) == OrderStatus.RECONCILIATION_REQUIRED
    assert tickets == []


async def test_late_payment_issue_refuses_after_event_ended(pg_factory):
    late = await late_payment(pg_factory)

    with pytest.raises(PaymentStateError):
        await admin(
            pg_factory, Gateway(), late.event.ends_at + timedelta(minutes=1)
        ).issue_late_payment(late.payment_id)

    _, order, _, tickets, _ = await state(pg_factory, late)
    assert OrderStatus(order.status) == OrderStatus.RECONCILIATION_REQUIRED
    assert tickets == []


async def test_admin_issue_endpoint_records_audit(pg_factory, monkeypatch):
    late = await late_payment(pg_factory)
    async with pg_factory() as session, session.begin():
        operator = AdminUser(login="operator", password_hash="x", role="administrator")
        session.add(operator)
    actor = AdminActor.from_model(operator)
    monkeypatch.setattr(admin_payments, "get_session_factory", lambda: pg_factory)
    monkeypatch.setattr(admin_payments, "_gateway", Gateway)
    monkeypatch.setattr(
        admin_payments,
        "PaymentAdminService",
        lambda factory, gateway: admin(factory, gateway, late.paid_at + timedelta(minutes=5)),
    )
    app = create_app()
    app.dependency_overrides[admin_payments.require_payment_admin] = lambda: actor

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/api/admin/payments/{late.payment_id}/issue")
        missing = await client.post(f"/api/admin/payments/{late.order_id}/issue")
        again = await client.post(f"/api/admin/payments/{late.payment_id}/issue")

    assert response.status_code == 200
    assert response.json()["status"] == PaymentStatus.CONFIRMED
    assert missing.status_code == 404
    assert again.status_code == 409
    assert again.json()["detail"] == "Payment cannot be issued"
    async with pg_factory() as session:
        actions = list(
            await session.scalars(
                select(AdminAuditLog.action).where(AdminAuditLog.object_id == late.payment_id)
            )
        )
    assert actions == ["payment.issue_late"]
