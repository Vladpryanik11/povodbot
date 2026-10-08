from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services.directions.service import DirectionDTO


def main_menu(
    directions: list[DirectionDTO],
    marketing_active: bool,
    marketing_version: str,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=d.name, callback_data=f"direction:{d.id}")] for d in directions
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="Мои билеты", callback_data="tickets:mine")],
            [InlineKeyboardButton(text="Поддержка", callback_data="support")],
            [
                InlineKeyboardButton(
                    text="Отписаться от рекламы" if marketing_active else "Настроить рекламу",
                    callback_data=f"consent:marketing:{'revoke' if marketing_active else 'show'}:"
                    f"{marketing_version}",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def consent_prompt(consent_type: str, version: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Согласен", callback_data=f"consent:{consent_type}:grant:{version}"
            )
        ]
    ]
    if consent_type == "marketing":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Без рекламы", callback_data=f"consent:marketing:skip:{version}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
