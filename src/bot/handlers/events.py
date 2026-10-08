from uuid import UUID
from zoneinfo import ZoneInfo

from src.bot.handlers.start import BotResponse
from src.bot.keyboards.events import directions_keyboard, event_keyboard, events_keyboard
from src.services.directions.service import DirectionService
from src.services.events.service import EventService


class EventHandler:
    def __init__(self, events: EventService, directions: DirectionService):
        self.events = events
        self.directions = directions

    async def read(self, data: str) -> BotResponse:
        if data == "events:directions":
            return BotResponse(
                "Выберите направление", directions_keyboard(await self.directions.list_active())
            )
        if data == "events:all":
            events = await self.events.list_public(None, None)
            return BotResponse(
                "Афиша Повода" if events else "Пока нет мероприятий", events_keyboard(events)
            )
        try:
            kind, identifier = data.split(":", 1)
            entity_id = UUID(identifier)
            if kind == "direction":
                events = await self.events.list_public(entity_id, None)
                return BotResponse(
                    "Выберите мероприятие" if events else "Пока нет мероприятий",
                    events_keyboard(events),
                )
            if kind != "event":
                raise ValueError("Unknown navigation")
            event = await self.events.get_public(entity_id)
        except (ValueError, LookupError):
            return BotResponse(
                "Мероприятие недоступно. Откройте актуальную афишу.", events_keyboard([])
            )
        zone = ZoneInfo(event.timezone)
        start = event.starts_at.astimezone(zone).strftime("%d.%m.%Y %H:%M")
        end = event.ends_at.astimezone(zone).strftime("%d.%m.%Y %H:%M")
        prices = "\n".join(
            f"{t.name[:120]}: {t.price_kopecks // 100}.{t.price_kopecks % 100:02d} {t.currency}"
            for t in event.ticket_types[:5]
        )
        if len(event.ticket_types) > 5:
            prices += f"\nЕщё типов билетов: {len(event.ticket_types) - 5}"
        details = (
            f"\n{start} — {end} ({event.timezone})\n{event.address}\n"
            f"Вместимость: {event.capacity}\n{prices}"
        )
        budget = 4000 - len(event.title) - len(details) - 1
        description = event.description
        if len(description) > budget:
            description = description[: budget - 1] + "…"
        return BotResponse(
            f"{event.title}\n{description}{details}",
            event_keyboard(event),
        )
