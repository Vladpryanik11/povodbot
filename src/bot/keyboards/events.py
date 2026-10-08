from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services.directions.service import DirectionDTO
from src.services.events.service import PublicEventDTO


def directions_keyboard(directions: list[DirectionDTO]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=d.name, callback_data=f"direction:{d.id}")]
            for d in directions
        ]
        + [[InlineKeyboardButton(text="Все мероприятия", callback_data="events:all")]]
    )


def events_keyboard(events: list[PublicEventDTO]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=e.title, callback_data=f"event:{e.id}")] for e in events
        ]
        + [
            [InlineKeyboardButton(text="Направления", callback_data="events:directions")],
            [InlineKeyboardButton(text="Все мероприятия", callback_data="events:all")],
        ]
    )


def event_keyboard(event: PublicEventDTO) -> InlineKeyboardMarkup:
    rows = []
    if event.map_url:
        rows.append([InlineKeyboardButton(text="На карте", url=event.map_url)])
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="К направлению", callback_data=f"direction:{event.direction_id}"
                )
            ],
            [InlineKeyboardButton(text="Все мероприятия", callback_data="events:all")],
            [InlineKeyboardButton(text="Главное меню", callback_data="events:menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
