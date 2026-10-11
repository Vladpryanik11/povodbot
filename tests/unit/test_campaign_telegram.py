from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import FSInputFile, InlineKeyboardMarkup

from src.services.campaigns.render import InlineButton, RenderedMessage
from src.services.campaigns.telegram import (
    AiogramCampaignSender,
    RecipientBlocked,
    RetryAfter,
    SentMessage,
)


class FakeBot:
    """Records what would go to Telegram; nothing leaves the test."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error = error

    async def send_photo(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("send_photo", kwargs))
        if self.error:
            raise self.error
        sizes = [
            SimpleNamespace(file_id="small", width=90, height=90),
            SimpleNamespace(file_id="large", width=1080, height=1080),
            SimpleNamespace(file_id="medium", width=320, height=320),
        ]
        return SimpleNamespace(message_id=41, photo=sizes)

    async def send_message(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("send_message", kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(message_id=42, photo=None)


BUTTONS = [InlineButton(label="Билет", url="https://t.me/povodbot/app?startapp=x")]


def text(body: str = "x", buttons: list[InlineButton] | None = None) -> RenderedMessage:
    return RenderedMessage(text=body, photo_path=None, photo_file_id=None, buttons=buttons or [])


async def test_text_message_is_html_without_link_preview() -> None:
    bot = FakeBot()

    sent = await AiogramCampaignSender(bot).send(777, text("<b>Привет</b>", BUTTONS))

    assert sent == SentMessage(message_id="42", photo_file_id=None)
    method, kwargs = bot.calls[0]
    assert method == "send_message"
    assert kwargs["chat_id"] == 777
    assert kwargs["text"] == "<b>Привет</b>"
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["link_preview_options"].is_disabled is True
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert [[(b.text, b.url) for b in row] for row in markup.inline_keyboard] == [
        [("Билет", "https://t.me/povodbot/app?startapp=x")]
    ]


async def test_photo_from_file_returns_the_largest_size(tmp_path: Path) -> None:
    bot = FakeBot()
    path = tmp_path / "campaigns/a-1080.webp"
    message = RenderedMessage(text="<i>Ок</i>", photo_path=path, photo_file_id=None, buttons=[])

    sent = await AiogramCampaignSender(bot).send(777, message)

    assert sent == SentMessage(message_id="41", photo_file_id="large")
    method, kwargs = bot.calls[0]
    assert method == "send_photo"
    assert kwargs["chat_id"] == 777
    assert isinstance(kwargs["photo"], FSInputFile)
    assert kwargs["photo"].path == path
    assert kwargs["caption"] == "<i>Ок</i>"
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["reply_markup"] is None


async def test_cached_photo_is_sent_by_file_id() -> None:
    bot = FakeBot()
    message = RenderedMessage(text="", photo_path=None, photo_file_id="AgAC", buttons=[])

    await AiogramCampaignSender(bot).send(777, message)

    assert bot.calls[0][1]["photo"] == "AgAC"


async def test_flood_wait_becomes_retry_after() -> None:
    method = SendMessage(chat_id=777, text="x")
    bot = FakeBot(TelegramRetryAfter(method=method, message="Flood", retry_after=3))

    with pytest.raises(RetryAfter) as error:
        await AiogramCampaignSender(bot).send(777, text())
    assert error.value.seconds == 3


async def test_blocked_bot_becomes_recipient_blocked() -> None:
    method = SendMessage(chat_id=777, text="x")
    bot = FakeBot(TelegramForbiddenError(method=method, message="bot was blocked by the user"))

    with pytest.raises(RecipientBlocked):
        await AiogramCampaignSender(bot).send(777, text())
