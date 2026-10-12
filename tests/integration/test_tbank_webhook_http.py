from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from src.api.app import create_app
from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.commerce import Order, OrderStatus
from src.models.payments import PaymentEvent
from src.models.tickets import Ticket
from src.repositories.payments import PaymentRepository
from src.repositories.reservations import ReservationRepository
from src.services.commerce.clock import SystemClock
from src.services.payments.dtos import CreatePaymentResponse
from src.services.payments.service import PaymentService
from src.services.payments.tbank_client import TBankPaymentGateway
from src.services.reservations.service import ReservationItem, ReservationService
from tests.commerce_fixtures import catalog

TERMINAL_KEY = "TestTerminalDEMO"
PASSWORD = "test-password"
URL = "/api/webhooks/tbank/payment-status"


@dataclass
class StartGateway:
    provider_payment_id: str

    async def create_payment(self, request):
        return CreatePaymentResponse(
            self.provider_payment_id, "https://pay/http", "NEW", request.amount_minor
        )


@pytest.fixture
def tbank_env(monkeypatch):
    monkeypatch.setenv("TBANK_TERMINAL_KEY", TERMINAL_KEY)
    monkeypatch.setenv("TBANK_PASSWORD", PASSWORD)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def app_for(factory):
    app = create_app()

    async def session_dependency():
        async with factory() as session, session.begin():
            yield session

    app.dependency_overrides[get_async_session] = session_dependency
    return app


def client_for(factory):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(factory)), base_url="http://test"
    )


async def started_order(factory, provider_payment_id="http-payment"):
    async with factory() as session, session.begin():
        event, user = await catalog(session, capacity=2)
        pending = await ReservationService(ReservationRepository(session), SystemClock()).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, 1)], user.id, datetime.now(UTC)
        )
        await PaymentService(PaymentRepository(session), StartGateway(provider_payment_id)).start(
            pending.order_id
        )
    return pending.order_id


def signed(order_id, provider_payment_id="http-payment", password=PASSWORD, **changes):
    body = {
        "TerminalKey": TERMINAL_KEY,
        "OrderId": str(order_id),
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": provider_payment_id,
        "ErrorCode": "0",
        "Amount": 15000,
        "Pan": "430000******0777",
        "ExpDate": "1230",
        "Data": {"Source": "cards"},
    }
    body.update(changes)
    body["Token"] = TBankPaymentGateway.build_token(body, password)
    return body


async def order_state(factory, order_id):
    async with factory() as session:
        status = await session.scalar(select(Order.status).where(Order.id == order_id))
        tickets = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.order_id == order_id)
        )
    return status, tickets


async def test_signed_confirmed_notification_returns_plain_ok(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=signed(order_id))
    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["content-type"].startswith("text/plain")
    assert await order_state(pg_factory, order_id) == (OrderStatus.PAID, 1)


async def test_duplicate_notification_returns_plain_ok(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    body = signed(order_id)
    async with client_for(pg_factory) as client:
        first = await client.post(URL, json=body)
        second = await client.post(URL, json=body)
    assert (first.status_code, first.text) == (200, "OK")
    assert (second.status_code, second.text) == (200, "OK")
    assert await order_state(pg_factory, order_id) == (OrderStatus.PAID, 1)


async def test_unknown_payment_returns_plain_ok(pg_factory, tbank_env):
    body = signed("unknown-order", provider_payment_id="missing-payment")
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=body)
    assert (response.status_code, response.text) == (200, "OK")


async def test_bad_token_is_rejected(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    body = signed(order_id)
    body["Token"] = "0" * 64
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=body)
    assert response.status_code == 401
    assert await order_state(pg_factory, order_id) == (OrderStatus.PENDING_PAYMENT, 0)


async def test_non_ascii_token_is_rejected_not_crashed(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    body = signed(order_id)
    body["Token"] = "токен"
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=body)
    assert response.status_code == 401


async def test_foreign_terminal_key_is_rejected(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=signed(order_id, TerminalKey="OtherTerminal"))
    assert response.status_code == 401
    assert await order_state(pg_factory, order_id) == (OrderStatus.PENDING_PAYMENT, 0)


async def test_webhook_without_configured_password_is_unavailable(pg_factory, tbank_env):
    order_id = await started_order(pg_factory)
    tbank_env.setenv("TBANK_PASSWORD", "")
    get_settings.cache_clear()
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=signed(order_id, password=""))
    assert response.status_code == 503
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaymentEvent)) == 0
    assert await order_state(pg_factory, order_id) == (OrderStatus.PENDING_PAYMENT, 0)


async def test_header_secret_is_not_required(pg_factory, tbank_env):
    tbank_env.setenv("TBANK_WEBHOOK_SECRET", "legacy-header-secret")
    get_settings.cache_clear()
    order_id = await started_order(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.post(URL, json=signed(order_id))
    assert (response.status_code, response.text) == (200, "OK")
    assert await order_state(pg_factory, order_id) == (OrderStatus.PAID, 1)
