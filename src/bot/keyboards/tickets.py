from aiogram.types import InlineKeyboardMarkup

from src.bot.keyboards.main_menu import back_to_menu


def tickets_keyboard(miniapp_url: str = "", empty: bool = False) -> InlineKeyboardMarkup:
    return back_to_menu(miniapp_url, with_open=empty)
