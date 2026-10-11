from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.bot import copy


def open_app_button(miniapp_url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=copy.BTN_OPEN, web_app=WebAppInfo(url=miniapp_url))


def main_menu(miniapp_url: str = "") -> InlineKeyboardMarkup:
    rows = []
    if miniapp_url:
        rows.append([open_app_button(miniapp_url)])
    rows.append(
        [
            InlineKeyboardButton(text=copy.BTN_TICKETS, callback_data="tickets:mine"),
            InlineKeyboardButton(text=copy.BTN_SUPPORT, callback_data="support"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu(miniapp_url: str = "", with_open: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if with_open and miniapp_url:
        rows.append([open_app_button(miniapp_url)])
    rows.append([InlineKeyboardButton(text=copy.BTN_MENU, callback_data="events:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
