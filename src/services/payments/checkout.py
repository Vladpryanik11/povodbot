from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.repositories.payments import PaymentRepository
from src.services.commerce.clock import Clock
from src.services.payments.dtos import PaymentCheckoutDTO
from src.services.payments.ports import PaymentGateway, PaymentGatewayError
from src.services.payments.service import PaymentService


class PaymentCheckoutService:
    """Run payment initialization across explicit transaction boundaries.

    The order/reservation and the local payment intent are committed before
    T-Bank ``Init`` is called. Provider results are then persisted in a fresh
    transaction. If the response is lost, a gateway that supports
    ``find_by_order`` can recover the provider identity by the stable merchant
    ``OrderId``; otherwise the local payment remains in reconciliation state.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
        clock: Clock | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.gateway = gateway
        self.clock = clock

    async def start(self, order_id: UUID) -> PaymentCheckoutDTO:
        async with self.session_factory() as session, session.begin():
            service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
            intent = await service.prepare(order_id)

        if intent.request is None:
            return intent.checkout

        try:
            response = await self.gateway.create_payment(intent.request)
        except PaymentGatewayError:
            finder = getattr(self.gateway, "find_by_order", None)
            recovered = None
            if callable(finder):
                try:
                    recovered = await finder(str(order_id))
                except PaymentGatewayError:
                    recovered = None
            async with self.session_factory() as session, session.begin():
                service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
                if recovered is not None:
                    return await service.attach_recovered_init(intent.payment_id, recovered)
                return await service.mark_init_unknown(intent.payment_id)

        async with self.session_factory() as session, session.begin():
            service = PaymentService(PaymentRepository(session), self.gateway, self.clock)
            return await service.complete_init(intent.payment_id, response)
