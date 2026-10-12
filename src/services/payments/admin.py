from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.payments import PaymentStatus
from src.repositories.payments import PaymentRepository
from src.services.commerce.clock import Clock
from src.services.payments.dtos import PaymentDTO, PaymentWebhookDTO
from src.services.payments.ports import PaymentGateway
from src.services.payments.service import PaymentService, PaymentStateError


def _provider_order_id(payload: dict[str, Any]) -> str | None:
    for key, value in payload.items():
        if str(key).lower().replace("_", "") == "orderid" and value is not None:
            return str(value)
    return None


class PaymentAdminService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
        clock: Clock | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.gateway = gateway
        self.clock = clock

    async def reconcile(self, payment_id: UUID) -> PaymentDTO:
        async with self.session_factory() as session, session.begin():
            payment = await PaymentRepository(session).by_id(payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            provider_payment_id = payment.provider_payment_id
            if not provider_payment_id:
                raise PaymentStateError("Payment has no provider identity")

        provider = await self.gateway.get_status(provider_payment_id)
        webhook = PaymentWebhookDTO(
            provider_payment_id=provider.provider_payment_id,
            provider_status=provider.provider_status,
            amount_minor=provider.amount_minor,
            order_id=_provider_order_id(provider.raw),
            success=provider.success,
            payload=provider.raw,
        )
        async with self.session_factory() as session, session.begin():
            service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
            applied = await service.apply_webhook(webhook)
            if applied.payment_id != payment_id:
                raise PaymentStateError("Payment changed during reconciliation")
            payment = await PaymentRepository(session).by_id(payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            return service._dto(payment)

    async def issue_late_payment(self, payment_id: UUID) -> PaymentDTO:
        """Asks the bank about a late payment, then keeps it and issues tickets if seats remain."""
        async with self.session_factory() as session, session.begin():
            payment = await PaymentRepository(session).by_id(payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            provider_payment_id = payment.provider_payment_id
            if not provider_payment_id:
                raise PaymentStateError("Payment has no provider identity")

        provider = await self.gateway.get_status(provider_payment_id)
        async with self.session_factory() as session, session.begin():
            service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
            return await service.issue_late_payment(payment_id, provider)

    async def bind_provider_payment(self, payment_id: UUID, provider_payment_id: str) -> PaymentDTO:
        provider_payment_id = provider_payment_id.strip()
        if not provider_payment_id or len(provider_payment_id) > 64:
            raise PaymentStateError("Provider payment id is invalid")

        async with self.session_factory() as session, session.begin():
            repository = PaymentRepository(session)
            payment = await repository.by_id(payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            if PaymentStatus(payment.status) != PaymentStatus.RECONCILIATION_REQUIRED:
                raise PaymentStateError("Only unresolved payments can be bound")
            other = await repository.by_provider_payment(provider_payment_id)
            if other is not None and other.id != payment_id:
                raise PaymentStateError("Provider payment id is already linked")

        provider = await self.gateway.get_status(provider_payment_id)
        if provider.provider_payment_id.strip() != provider_payment_id:
            raise PaymentStateError("Provider payment identity does not match")

        async with self.session_factory() as session, session.begin():
            service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
            return await service.bind_provider_snapshot(
                payment_id,
                provider,
                expected_provider_payment_id=provider_payment_id,
            )
