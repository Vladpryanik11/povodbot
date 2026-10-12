from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from src.services.payments.dtos import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.ports import (
    PaymentGatewayError,
    PaymentProviderRejected,
    PaymentProviderTimeout,
)


def _secret_value(value: str | SecretStr) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _scalar_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class TBankPaymentGateway:
    """Internet Acquiring adapter for the T-Bank v2 API.

    The adapter intentionally owns all provider-specific field names and token
    construction. Application services only see the PaymentGateway port.
    """

    def __init__(
        self,
        terminal_key: str | SecretStr,
        password: str | SecretStr,
        *,
        api_token: str | SecretStr | None = None,
        base_url: str = "https://securepay.tinkoff.ru/v2",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.terminal_key = _secret_value(terminal_key)
        self.password = _secret_value(password)
        self.api_token = _secret_value(api_token) if api_token is not None else ""
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(transport=transport, timeout=timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def build_token(payload: Mapping[str, object], password: str | SecretStr) -> str:
        values: dict[str, object] = {
            key: value
            for key, value in payload.items()
            if key != "Token" and value is not None and not isinstance(value, (dict, list))
        }
        values["Password"] = _secret_value(password)
        joined = "".join(_scalar_text(values[key]) for key in sorted(values))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def verify_notification(self, payload: Mapping[str, object]) -> bool:
        token = payload.get("Token")
        if not isinstance(token, str) or not token or not token.isascii():
            return False
        expected = self.build_token(payload, self.password)
        return hmac.compare_digest(expected, token)

    async def _post(self, method: str, payload: dict[str, object]) -> dict[str, Any]:
        body = dict(payload)
        body["TerminalKey"] = self.terminal_key
        body["Token"] = self.build_token(body, self.password)
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            response = await self.client.post(
                f"{self.base_url}/{method}", json=body, headers=headers
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PaymentProviderTimeout("T-Bank request timed out") from exc
        except httpx.HTTPError as exc:
            raise PaymentGatewayError("T-Bank request failed") from exc
        try:
            result = response.json()
        except ValueError as exc:
            raise PaymentGatewayError("T-Bank returned malformed JSON") from exc
        if not isinstance(result, dict):
            raise PaymentGatewayError("T-Bank returned an invalid response")
        if result.get("Success") is False:
            raise PaymentProviderRejected("T-Bank rejected the payment operation")
        return result

    @staticmethod
    def _required_string(result: Mapping[str, object], key: str) -> str:
        value = result.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
        raise PaymentGatewayError(f"T-Bank response misses {key}")

    async def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResponse:
        if type(request.amount_minor) is not int or request.amount_minor <= 0:
            raise ValueError("Payment amount must be a positive integer")
        if not str(request.order_id) or len(str(request.order_id)) > 50:
            raise ValueError("Order id is invalid for T-Bank")
        payload: dict[str, object] = {
            "Amount": request.amount_minor,
            "OrderId": str(request.order_id),
            "Description": request.description[:250],
            "Language": request.language,
        }
        for key, value in (
            ("NotificationURL", request.notification_url),
            ("SuccessURL", request.success_url),
            ("FailURL", request.fail_url),
        ):
            if value:
                payload[key] = value
        if request.redirect_due_date is not None:
            payload["RedirectDueDate"] = request.redirect_due_date.isoformat()
        result = await self._post("Init", payload)
        return CreatePaymentResponse(
            provider_payment_id=self._required_string(result, "PaymentId"),
            payment_url=self._required_string(result, "PaymentURL"),
            provider_status=self._required_string(result, "Status"),
            amount_minor=request.amount_minor,
            raw=result,
        )

    async def get_status(self, provider_payment_id: str) -> ProviderPaymentStatus:
        result = await self._post("GetState", {"PaymentId": provider_payment_id})
        return ProviderPaymentStatus(
            provider_payment_id=self._required_string(result, "PaymentId"),
            provider_status=self._required_string(result, "Status"),
            amount_minor=int(result["Amount"]) if result.get("Amount") is not None else None,
            success=result.get("Success") if isinstance(result.get("Success"), bool) else None,
            raw=result,
        )

    async def find_by_order(self, order_id: str) -> ProviderPaymentStatus:
        """Recover a payment when Init succeeded but its response was lost.

        T-Bank documents ``OrderId`` as the merchant-side identifier and exposes
        ``CheckOrder`` specifically for looking up an operation by that value.
        The caller must still validate the returned amount and merchant order
        before attaching the provider identity to a local payment.
        """
        if not order_id or len(order_id) > 50:
            raise ValueError("Order id is invalid for T-Bank")
        result = await self._post("CheckOrder", {"OrderId": order_id})
        payments = result.get("Payments")
        if not isinstance(payments, list) or not payments:
            raise PaymentGatewayError("CheckOrder found no payment")
        if len(payments) > 1:
            raise PaymentGatewayError("CheckOrder found several payments")
        entry = payments[0]
        if not isinstance(entry, dict):
            raise PaymentGatewayError("CheckOrder found no payment")
        raw = dict(entry)
        if result.get("OrderId") is not None:
            raw["OrderId"] = result["OrderId"]
        return ProviderPaymentStatus(
            provider_payment_id=self._required_string(entry, "PaymentId"),
            provider_status=self._required_string(entry, "Status"),
            amount_minor=int(entry["Amount"]) if entry.get("Amount") is not None else None,
            success=entry.get("Success") if isinstance(entry.get("Success"), bool) else None,
            raw=raw,
        )

    async def cancel(
        self, provider_payment_id: str, amount_minor: int | None = None
    ) -> ProviderOperationResult:
        payload: dict[str, object] = {"PaymentId": provider_payment_id}
        if amount_minor is not None:
            payload["Amount"] = amount_minor
        result = await self._post("Cancel", payload)
        return ProviderOperationResult(
            provider_payment_id=self._required_string(result, "PaymentId"),
            provider_status=self._required_string(result, "Status"),
            raw=result,
        )

    async def refund(
        self, provider_payment_id: str, amount_minor: int, reason: str
    ) -> ProviderOperationResult:
        if type(amount_minor) is not int or amount_minor <= 0:
            raise ValueError("Refund amount must be a positive integer")
        result = await self._post(
            "Cancel", {"PaymentId": provider_payment_id, "Amount": amount_minor}
        )
        return ProviderOperationResult(
            provider_payment_id=self._required_string(result, "PaymentId"),
            provider_status=self._required_string(result, "Status"),
            raw=result,
        )
