from pathlib import Path
from uuid import uuid4

import pytest

from src.models.campaigns import Campaign
from src.models.events import Event
from src.services.campaigns.render import CampaignNotReady, InlineButton, render

LINK = "https://t.me/povodbot/app"
BASE = "https://povod.club"


def campaign(**changes: object) -> Campaign:
    values: dict[str, object] = {
        "id": uuid4(),
        "title": "Вечер",
        "body": "<b>Приходи</b>",
        "image": {"kind": "none"},
        "buttons": [],
        "short_code": "Ab3dE6gH",
        "telegram_photo_id": None,
    }
    values.update(changes)
    return Campaign(**values)


def settings(media_root: Path, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "media_root": media_root,
        "miniapp_link": LINK,
        "public_base_url": BASE,
    }
    values.update(changes)
    return values


def test_event_button_opens_the_evening_in_the_mini_app(tmp_path: Path) -> None:
    event = Event(id=uuid4(), cover_ref=None)
    message = render(
        campaign(buttons=[{"kind": "event", "label": "Купить билет"}], event_id=event.id),
        event,
        {},
        **settings(tmp_path),
    )
    url = f"{LINK}?startapp=event_{event.id}_cAb3dE6gH"
    assert message.buttons == [InlineButton(label="Купить билет", url=url)]
    assert len(url.split("startapp=")[1]) <= 64
    assert message.text == "<b>Приходи</b>"


def test_url_button_goes_through_the_click_counter(tmp_path: Path) -> None:
    button = {"kind": "url", "label": "Плейлист", "url": "https://music.example/x"}
    source = campaign(buttons=[{"kind": "event", "label": "Билет"}, button])
    event = Event(id=uuid4(), cover_ref=None)

    counted = render(source, event, {1: "k7Lm9pQr"}, **settings(tmp_path))
    direct = render(source, event, {}, **settings(tmp_path), direct_urls=True)

    assert counted.buttons[1] == InlineButton(label="Плейлист", url=f"{BASE}/r/k7Lm9pQr")
    assert direct.buttons[1] == InlineButton(label="Плейлист", url="https://music.example/x")


def test_event_picture_is_the_poster_file(tmp_path: Path) -> None:
    event = Event(id=uuid4(), cover_ref="posters/abc123")
    message = render(campaign(image={"kind": "event"}), event, {}, **settings(tmp_path))
    assert message.photo_path == tmp_path / "posters/abc123-1080.webp"
    assert message.photo_file_id is None


def test_uploaded_picture_is_the_campaign_file(tmp_path: Path) -> None:
    source = campaign(image={"kind": "upload", "ref": "campaigns/def456"})
    message = render(source, None, {}, **settings(tmp_path))
    assert message.photo_path == tmp_path / "campaigns/def456-1080.webp"


def test_cached_telegram_photo_wins_over_the_file(tmp_path: Path) -> None:
    source = campaign(
        image={"kind": "upload", "ref": "campaigns/def456"}, telegram_photo_id="AgACAgIAAx"
    )
    message = render(source, None, {}, **settings(tmp_path))
    assert message.photo_file_id == "AgACAgIAAx"
    assert message.photo_path is None


def test_no_picture_sends_text_only(tmp_path: Path) -> None:
    message = render(campaign(), None, {}, **settings(tmp_path))
    assert message.photo_path is None and message.photo_file_id is None


def test_evening_without_poster_sends_text_only(tmp_path: Path) -> None:
    event = Event(id=uuid4(), cover_ref=None)
    message = render(campaign(image={"kind": "event"}), event, {}, **settings(tmp_path))
    assert message.photo_path is None and message.photo_file_id is None


def test_event_button_without_mini_app_link_is_not_ready(tmp_path: Path) -> None:
    event = Event(id=uuid4(), cover_ref=None)
    source = campaign(buttons=[{"kind": "event", "label": "Билет"}])
    with pytest.raises(CampaignNotReady) as error:
        render(source, event, {}, **settings(tmp_path, miniapp_link=""))
    assert error.value.message == "Кнопки пока не настроены. Напиши разработчику"


def test_url_button_without_public_address_is_not_ready(tmp_path: Path) -> None:
    source = campaign(buttons=[{"kind": "url", "label": "Сайт", "url": "https://x.example"}])
    with pytest.raises(CampaignNotReady):
        render(source, None, {0: "k7Lm9pQr"}, **settings(tmp_path, public_base_url=""))
    # Sending to oneself uses the address as is, so the counter is not needed.
    direct = render(source, None, {}, **settings(tmp_path, public_base_url=""), direct_urls=True)
    assert direct.buttons == [InlineButton(label="Сайт", url="https://x.example")]
