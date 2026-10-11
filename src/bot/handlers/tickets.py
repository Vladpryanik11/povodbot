from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import copy
from src.bot.handlers.start import BotResponse
from src.bot.keyboards.tickets import tickets_keyboard
from src.models.events import Event
from src.repositories.tickets import TicketRepository
from src.services.tickets.qr import QrTokenService


class TicketHandler:
    def __init__(self, session: AsyncSession, miniapp_url: str = ""):
        self.session = session
        self.miniapp_url = miniapp_url
        self.qr = QrTokenService()

    async def mine(self, user_id: UUID) -> BotResponse:
        tickets = await TicketRepository(self.session).list_for_user(user_id)
        if not tickets:
            return BotResponse(copy.TICKETS_EMPTY, tickets_keyboard(self.miniapp_url, empty=True))
        event_ids = {ticket.event_id for ticket in tickets}
        events = {
            event.id: event
            for event in await self.session.scalars(select(Event).where(Event.id.in_(event_ids)))
        }
        lines = [copy.TICKETS_TITLE]
        for ticket in tickets[:20]:
            event = events.get(ticket.event_id)
            if event is None:
                continue
            local = event.starts_at.astimezone(ZoneInfo(event.timezone))
            status = copy.TICKET_STATUS.get(str(ticket.status), copy.TICKET_STATUS["issued"])
            line = copy.TICKET_LINE.format(
                title=event.title,
                date=local.strftime("%d.%m.%Y"),
                time=local.strftime("%H:%M"),
                status=status,
            )
            lines.append(f"\n{line}\nQR-код: {self.qr.generate(ticket.id)}")
        return BotResponse("\n".join(lines), tickets_keyboard(self.miniapp_url))
