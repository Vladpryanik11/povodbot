from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def quantity_keyboard(ticket_type_id: str, maximum: int) -> InlineKeyboardMarkup:
    quantity_limit = min(maximum, 10)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{quantity} билет{'а' if quantity > 1 else ''}",
                callback_data=f"quantity:{ticket_type_id}:{quantity}",
            )
        ]
        for quantity in range(1, quantity_limit + 1)
    ]
    rows.append([InlineKeyboardButton(text="К афише", callback_data="events:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="К афише", callback_data="events:all")],
        ]
    )
