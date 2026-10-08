from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.commerce import Order
from src.models.tickets import Ticket

if TYPE_CHECKING:
    from src.services.tickets.checkin import TicketLookupQuery


class TicketRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, ticket_id: UUID) -> Ticket:
        ticket = await self.session.scalar(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.checkin))
            .with_for_update()
        )
        if ticket is None:
            raise LookupError("Ticket not found")
        return ticket

    async def list_for_order(self, order_id: UUID) -> list[Ticket]:
        return list(
            await self.session.scalars(
                select(Ticket)
                .where(Ticket.order_id == order_id)
                .order_by(Ticket.order_item_id, Ticket.position, Ticket.id)
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[Ticket]:
        return list(
            await self.session.scalars(
                select(Ticket)
                .join(Order, Order.id == Ticket.order_id)
                .where(Order.user_id == user_id)
                .order_by(Ticket.issued_at.desc(), Ticket.id)
            )
        )

    async def search(self, query: "TicketLookupQuery") -> list[Ticket]:
        statement = select(Ticket).order_by(Ticket.issued_at, Ticket.id)
        if query.ticket_id is not None:
            statement = statement.where(Ticket.id == query.ticket_id)
        if query.order_id is not None:
            statement = statement.where(Ticket.order_id == query.order_id)
        if query.event_id is not None:
            statement = statement.where(Ticket.event_id == query.event_id)
        if query.status is not None:
            statement = statement.where(Ticket.status == query.status)
        return list(await self.session.scalars(statement.limit(query.limit)))

    async def save(self) -> None:
        await self.session.flush()
