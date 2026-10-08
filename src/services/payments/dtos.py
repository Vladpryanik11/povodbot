from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.models.payments import PaymentStatus


@dataclass(frozen=True)
class CreatePaymentRequest:
    order_id: UUID | str
    amount_minor: int
    description: str
    notification_url: str | None = None
    success_url: str | None = None
    fail_url: str | None = None
    redirect_due_date: datetime | None = None
    language: str = "ru"

    @property
    def amount_kopecks(self) -> int:
        return self.amount_minor


@dataclass(frozen=True)
class CreatePaymentResponse:
    provider_payment_id: str
    payment_url: str
    provider_status: str
    amount_minor: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProviderPaymentStatus:
    provider_payment_id: str
    provider_status: str
    amount_minor: int | None = None
    success: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProviderOperationResult:
    provider_payment_id: str
    provider_status: str
    success: bool = True
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class PaymentCheckoutDTO:
    payment_id: UUID
    order_id: UUID
    provider_payment_id: str | None
    payment_url: str | None
    status: PaymentStatus


@dataclass(frozen=True)
class PaymentDTO:
    id: UUID
    order_id: UUID
    provider_payment_id: str | None
    status: PaymentStatus
    provider_status: str | None
    amount_minor: int
    payment_url: str | None


@dataclass(frozen=True)
class PaymentWebhookDTO:
    provider_payment_id: str
    provider_status: str
    amount_minor: int | None = None
    order_id: str | None = None
    success: bool | None = None
    token: str | None = None
    event_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def deduplication_key(self) -> str:
        if self.event_id:
            return f"tbank:event:{self.event_id}"
        return f"tbank:payment:{self.provider_payment_id}:status:{self.provider_status}"
