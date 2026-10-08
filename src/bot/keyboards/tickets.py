from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def tickets_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="К афише", callback_data="events:all")],
            [InlineKeyboardButton(text="Главное меню", callback_data="events:menu")],
        ]
    )
