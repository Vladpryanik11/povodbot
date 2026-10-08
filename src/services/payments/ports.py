from typing import Protocol

from src.services.payments.dtos import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    ProviderOperationResult,
    ProviderPaymentStatus,
)


class PaymentGatewayError(RuntimeError):
    """Safe, provider-neutral payment integration error."""


class PaymentProviderRejected(PaymentGatewayError):
    pass


class PaymentProviderTimeout(PaymentGatewayError):
    pass


class PaymentGateway(Protocol):
    async def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResponse: ...

    async def get_status(self, provider_payment_id: str) -> ProviderPaymentStatus: ...

    async def cancel(
        self, provider_payment_id: str, amount_minor: int | None = None
    ) -> ProviderOperationResult: ...

    async def refund(
        self, provider_payment_id: str, amount_minor: int, reason: str
    ) -> ProviderOperationResult: ...
