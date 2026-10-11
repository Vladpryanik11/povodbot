"""A broadcast as one Telegram message: HTML text, an optional picture and link buttons."""

from dataclasses import dataclass
from pathlib import Path

from src.models.campaigns import Campaign
from src.models.events import Event

NOT_CONFIGURED = "Кнопки пока не настроены. Напиши разработчику"
NO_EVENING = "Сначала выбери вечер"
POSTER_PREFIX = "posters/"


class CampaignNotReady(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class InlineButton:
    label: str
    url: str


@dataclass(frozen=True)
class RenderedMessage:
    text: str
    photo_path: Path | None
    photo_file_id: str | None
    buttons: list[InlineButton]


def render(
    campaign: Campaign,
    event: Event | None,
    links: dict[int, str],
    *,
    media_root: Path,
    miniapp_link: str,
    public_base_url: str,
    direct_urls: bool = False,
) -> RenderedMessage:
    """`links` maps a url button's position to its click-counter code."""
    buttons = []
    for index, button in enumerate(campaign.buttons):
        if button["kind"] == "event":
            if not miniapp_link:
                raise CampaignNotReady(NOT_CONFIGURED)
            if event is None:
                raise CampaignNotReady(NO_EVENING)
            # Telegram allows 64 characters after startapp=; this takes 52.
            start = f"event_{event.id}_c{campaign.short_code}"
            url = f"{miniapp_link.rstrip('/')}?startapp={start}"
        elif direct_urls:
            url = button["url"]
        else:
            if not public_base_url:
                raise CampaignNotReady(NOT_CONFIGURED)
            url = f"{public_base_url.rstrip('/')}/r/{links[index]}"
        buttons.append(InlineButton(label=button["label"], url=url))
    photo_path = None if campaign.telegram_photo_id else _photo_path(campaign, event, media_root)
    return RenderedMessage(
        text=campaign.body,
        photo_path=photo_path,
        photo_file_id=campaign.telegram_photo_id,
        buttons=buttons,
    )


def _photo_path(campaign: Campaign, event: Event | None, media_root: Path) -> Path | None:
    kind = campaign.image.get("kind")
    if kind == "upload":
        return media_root / f"{campaign.image['ref']}-1080.webp"
    # Only an uploaded poster has a file; an evening without one goes out as text.
    if kind == "event" and event is not None and (event.cover_ref or "").startswith(POSTER_PREFIX):
        return media_root / f"{event.cover_ref}-1080.webp"
    return None
