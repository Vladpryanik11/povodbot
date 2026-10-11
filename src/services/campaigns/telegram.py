"""Sends a rendered broadcast through aiogram and turns its failures into sender errors."""

from dataclasses import dataclass
from typing import Any, Protocol

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)

from src.services.campaigns.render import RenderedMessage


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    # Telegram's id for the uploaded picture, so the next guests get it without a re-upload.
    photo_file_id: str | None


class RetryAfter(Exception):
    def __init__(self, seconds: float):
        super().__init__(seconds)
        self.seconds = seconds


class RecipientBlocked(Exception):
    pass


class CampaignSender(Protocol):
    async def send(self, telegram_id: int, message: RenderedMessage) -> SentMessage: ...


class AiogramCampaignSender:
    def __init__(self, bot: Any):
        self.bot = bot

    async def send(self, telegram_id: int, message: RenderedMessage) -> SentMessage:
        markup = (
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=button.label, url=button.url)]
                    for button in message.buttons
                ]
            )
            if message.buttons
            else None
        )
        try:
            if message.photo_file_id or message.photo_path:
                photo = message.photo_file_id or FSInputFile(message.photo_path)  # type: ignore[arg-type]
                result = await self.bot.send_photo(
                    chat_id=telegram_id,
                    photo=photo,
                    caption=message.text or None,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                largest = max(result.photo, key=lambda size: size.width * size.height)
                return SentMessage(str(result.message_id), largest.file_id)
            result = await self.bot.send_message(
                chat_id=telegram_id,
                text=message.text,
                parse_mode="HTML",
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramRetryAfter as error:
            raise RetryAfter(error.retry_after) from error
        except TelegramForbiddenError as error:
            raise RecipientBlocked() from error
        return SentMessage(str(result.message_id), None)
