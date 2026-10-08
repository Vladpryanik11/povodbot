import json
from datetime import UTC, datetime

import httpx
import pytest

from src.services.payments.dtos import CreatePaymentRequest
from src.services.payments.ports import PaymentProviderRejected, PaymentProviderTimeout
from src.services.payments.tbank_client import TBankPaymentGateway


async def test_tbank_token_uses_sorted_root_scalars_only():
    token = TBankPaymentGateway.build_token(
        {
            "TerminalKey": "demo",
            "Amount": 19200,
            "OrderId": "00000",
            "Description": "Подарочная карта",
            "DATA": {"Phone": "+70000000000"},
        },
        "password",
    )
    assert token == "6171df2eedbfa563ffc0c5bd00b20dd338b67db1239ec671870089c169cea370"


@pytest.mark.asyncio
async def test_create_payment_maps_payment_url_and_signed_payload():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "Success": True,
                "PaymentId": 12345,
                "Status": "NEW",
                "PaymentURL": "https://pay",
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = TBankPaymentGateway("terminal", "password", transport=transport)
    try:
        result = await gateway.create_payment(
            CreatePaymentRequest(
                order_id="order-1",
                amount_minor=15000,
                description="Повод",
                redirect_due_date=datetime(2026, 10, 8, 12, tzinfo=UTC),
            )
        )
    finally:
        await gateway.aclose()
    assert result.provider_payment_id == "12345"
    assert result.payment_url == "https://pay"
    assert seen["TerminalKey"] == "terminal"
    assert seen["Token"] == TBankPaymentGateway.build_token(seen, "password")


@pytest.mark.asyncio
async def test_check_order_recovers_provider_identity_after_lost_init_response():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "Success": True,
                "PaymentId": 9876,
                "OrderId": "order-1",
                "Amount": 15000,
                "Status": "NEW",
            },
        )

    gateway = TBankPaymentGateway("terminal", "password", transport=httpx.MockTransport(handler))
    try:
        result = await gateway.find_by_order("order-1")
    finally:
        await gateway.aclose()

    assert result.provider_payment_id == "9876"
    assert result.provider_status == "NEW"
    assert result.amount_minor == 15000
    assert seen["OrderId"] == "order-1"


@pytest.mark.asyncio
async def test_provider_rejection_and_timeout_are_typed_without_secret():
    async def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Success": False, "Message": "secret password"})

    gateway = TBankPaymentGateway(
        "terminal", "very-secret", transport=httpx.MockTransport(rejected)
    )
    try:
        with pytest.raises(PaymentProviderRejected) as error:
            await gateway.get_status("1")
        assert "very-secret" not in str(error.value)
    finally:
        await gateway.aclose()

    async def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private transport detail")

    gateway = TBankPaymentGateway("terminal", "very-secret", transport=httpx.MockTransport(timeout))
    try:
        with pytest.raises(PaymentProviderTimeout):
            await gateway.get_status("1")
    finally:
        await gateway.aclose()
