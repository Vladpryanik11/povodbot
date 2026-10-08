from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import BotResponse
from src.bot.keyboards.tickets import tickets_keyboard
from src.models.events import Event
from src.models.tickets import TicketStatus
from src.repositories.tickets import TicketRepository
from src.services.tickets.qr import QrTokenService


class TicketHandler:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.qr = QrTokenService()

    async def mine(self, user_id: UUID) -> BotResponse:
        tickets = await TicketRepository(self.session).list_for_user(user_id)
        if not tickets:
            return BotResponse("У вас пока нет билетов.", tickets_keyboard())
        event_ids = {ticket.event_id for ticket in tickets}
        events = {
            event.id: event
            for event in await self.session.scalars(select(Event).where(Event.id.in_(event_ids)))
        }
        lines = ["Ваши билеты:"]
        for ticket in tickets[:20]:
            event = events.get(ticket.event_id)
            if event is None:
                continue
            zone = ZoneInfo(event.timezone)
            starts_at = event.starts_at.astimezone(zone).strftime("%d.%m.%Y %H:%M")
            status = TicketStatus(ticket.status)
            lines.append(
                f"\n{event.title}\n{starts_at} ({event.timezone})\n"
                f"{ticket.label}, билет №{ticket.position}\nСтатус: {status.value}\n"
                f"QR-код: {self.qr.generate(ticket.id)}"
            )
        return BotResponse("\n".join(lines), tickets_keyboard())
