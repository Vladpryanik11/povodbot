from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from src.api.owner.campaigns import campaign_sender
from src.core.config import get_settings
from src.models.admin import AdminAuditLog
from src.models.campaigns import (
    Campaign,
    CampaignDelivery,
    CampaignLink,
    CampaignStatus,
    DeliveryStatus,
)
from src.models.events import Event, EventStatus
from src.models.outbox import Outbox
from src.services.campaigns.content import CampaignFieldError
from src.services.campaigns.delivery import CampaignDeliveryWorker
from src.services.campaigns.launch import CampaignLauncher, QuietHours, send_test
from src.services.campaigns.owner import CampaignLocked, OwnerCampaignService
from src.services.campaigns.render import RenderedMessage
from src.services.campaigns.telegram import SentMessage
from src.workers.outbox import CampaignOutboxWorker
from tests.campaign_fixtures import delivered, guest, scenario
from tests.owner_fixtures import make_admin, owner_app, owner_headers

# 15:00 in Moscow, a working afternoon.
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
NIGHT = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
MORNING = datetime(2026, 10, 13, 7, 0, tzinfo=UTC)
URL = "https://music.example/playlist"


def ready_settings():
    return get_settings().model_copy(
        update={
            "miniapp_link": "https://t.me/povodbot/app",
            "public_base_url": "https://povod.club",
        }
    )


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, RenderedMessage]] = []

    async def send(self, telegram_id: int, message: RenderedMessage) -> SentMessage:
        self.calls.append((telegram_id, message))
        return SentMessage(message_id=str(len(self.calls)), photo_file_id=None)


async def draft(session, **values: Any) -> Campaign:
    values.setdefault("body", "<b>Приходи</b> в субботу")
    return await OwnerCampaignService(session).create(None, values)


async def statuses(session, campaign_id) -> dict[int, str]:
    rows = await session.execute(
        select(CampaignDelivery.telegram_id, CampaignDelivery.status).where(
            CampaignDelivery.campaign_id == campaign_id
        )
    )
    return {telegram_id: status for telegram_id, status in rows.all()}


async def outbox_count(session, campaign_id) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(Outbox)
        .where(Outbox.deduplication_key.like(f"campaign:{campaign_id}:user:%"))
    )
    return total or 0


async def test_send_now_freezes_list(db_session):
    x, _, people = await scenario(db_session)
    for _ in range(2):
        await delivered(db_session, people["A"], NOW - timedelta(days=6))
    campaign = await draft(db_session)

    sent = await CampaignLauncher(db_session).send(campaign.id, None, NOW)

    assert sent.status == CampaignStatus.RUNNING
    assert sent.started_at == NOW
    assert sent.recipient_count == 5
    assert await statuses(db_session, campaign.id) == {
        1: DeliveryStatus.SKIPPED_LIMIT,
        2: DeliveryStatus.QUEUED,
        3: DeliveryStatus.QUEUED,
        5: DeliveryStatus.QUEUED,
        6: DeliveryStatus.QUEUED,
    }
    # Someone who likes the evening later is not added to a list already taken.
    await guest(db_session, 9, liked=[x])
    worker = CampaignDeliveryWorker(db_session)
    assert await worker.deliver(campaign.id, now=NOW) == 4
    assert await worker.deliver(campaign.id, now=NOW) == 0
    assert len(await statuses(db_session, campaign.id)) == 5
    assert await outbox_count(db_session, campaign.id) == 4


async def test_send_twice_is_rejected(db_session):
    await scenario(db_session)
    campaign = await draft(db_session)
    launcher = CampaignLauncher(db_session)
    await launcher.send(campaign.id, None, NOW)

    with pytest.raises(CampaignLocked):
        await launcher.send(campaign.id, None, NOW)
    assert len(await statuses(db_session, campaign.id)) == 5


async def test_send_at_night_suggests_morning(db_session):
    await scenario(db_session)
    campaign = await draft(db_session)

    with pytest.raises(QuietHours) as error:
        await CampaignLauncher(db_session).send(campaign.id, None, NIGHT)

    assert error.value.suggested_at == MORNING
    assert campaign.status == CampaignStatus.DRAFT
    assert await statuses(db_session, campaign.id) == {}


async def test_schedule_rejects_past_and_quiet(db_session):
    await scenario(db_session)
    campaign = await draft(db_session)
    launcher = CampaignLauncher(db_session)

    with pytest.raises(CampaignFieldError) as past:
        await launcher.send(campaign.id, NOW - timedelta(minutes=1), NOW)
    with pytest.raises(CampaignFieldError) as quiet:
        await launcher.send(campaign.id, NIGHT + timedelta(days=1), NOW)
    assert (past.value.field, past.value.message) == ("at", "Это время уже прошло")
    assert (quiet.value.field, quiet.value.message) == (
        "at",
        "С 22:00 до 10:00 не отправляем. Выбери другое время",
    )

    at = NOW + timedelta(days=1)
    scheduled = await launcher.send(campaign.id, at, NOW)
    assert scheduled.status == CampaignStatus.SCHEDULED
    assert scheduled.scheduled_at == at
    assert await statuses(db_session, campaign.id) == {}


async def test_schedule_then_worker_freezes_when_due(db_session):
    await scenario(db_session)
    campaign = await draft(db_session)
    at = NOW + timedelta(hours=1)
    await CampaignLauncher(db_session).send(campaign.id, at, NOW)
    worker = CampaignDeliveryWorker(db_session)

    assert await worker.deliver(campaign.id, now=NOW) == 0
    assert campaign.status == CampaignStatus.SCHEDULED

    assert await worker.deliver(campaign.id, now=at) == 5
    assert campaign.status == CampaignStatus.RUNNING
    assert campaign.started_at == at
    assert campaign.recipient_count == 5


async def test_unpublished_event_cancels_scheduled(db_session):
    x, _, _ = await scenario(db_session)
    campaign = await draft(
        db_session, event_id=x, buttons=[{"kind": "event", "label": "Купить билет"}]
    )
    at = NOW + timedelta(hours=1)
    await CampaignLauncher(db_session, ready_settings()).send(campaign.id, at, NOW)
    event = await db_session.get(Event, x)
    event.status = EventStatus.CANCELLED

    assert await CampaignDeliveryWorker(db_session).deliver(campaign.id, now=at) == 0

    assert campaign.status == CampaignStatus.CANCELLED
    assert campaign.cancel_reason == "event_unpublished"
    assert campaign.finished_at == at
    assert await statuses(db_session, campaign.id) == {}


async def test_send_rejects_unpublished_event_in_spec_words(db_session):
    x, _, _ = await scenario(db_session)
    campaign = await draft(db_session, event_id=x)
    event = await db_session.get(Event, x)
    event.status = EventStatus.CANCELLED

    with pytest.raises(CampaignFieldError) as error:
        await CampaignLauncher(db_session, ready_settings()).send(campaign.id, None, NOW)

    assert (error.value.field, error.value.message) == ("event_id", "Вечер больше не опубликован")
    assert campaign.status == CampaignStatus.DRAFT


async def test_zero_recipients_rejected(db_session):
    campaign = await draft(db_session)

    with pytest.raises(CampaignFieldError) as error:
        await CampaignLauncher(db_session).send(campaign.id, None, NOW)

    assert error.value.message == "Получателей нет"
    assert campaign.status == CampaignStatus.DRAFT


async def test_send_checks_text_and_button_settings(db_session):
    x, _, _ = await scenario(db_session)
    empty = await draft(db_session, body="")
    with pytest.raises(CampaignFieldError) as error:
        await CampaignLauncher(db_session).send(empty.id, None, NOW)
    assert error.value.field == "body"

    button = await draft(db_session, event_id=x, buttons=[{"kind": "event", "label": "Билет"}])
    unset = get_settings().model_copy(update={"miniapp_link": ""})
    from src.services.campaigns.render import CampaignNotReady

    with pytest.raises(CampaignNotReady):
        await CampaignLauncher(db_session, unset).send(button.id, None, NOW)
    assert button.status == CampaignStatus.DRAFT


async def test_freeze_creates_click_links_for_url_buttons(db_session):
    await scenario(db_session)
    campaign = await draft(db_session, buttons=[{"kind": "url", "label": "Плейлист", "url": URL}])

    await CampaignLauncher(db_session, ready_settings()).send(campaign.id, None, NOW)

    links = list(
        await db_session.scalars(
            select(CampaignLink).where(CampaignLink.campaign_id == campaign.id)
        )
    )
    assert [(link.button_index, link.url) for link in links] == [(0, URL)]


async def test_cancel_and_stop(pg_factory):
    async with pg_factory() as session, session.begin():
        await scenario(session)
        later = await draft(session)
        running = await draft(session)
        launcher = CampaignLauncher(session)
        await launcher.send(later.id, NOW + timedelta(hours=1), NOW)
        await launcher.send(running.id, None, NOW)
        assert await CampaignDeliveryWorker(session).deliver(running.id, now=NOW) == 5

    async with pg_factory() as session, session.begin():
        launcher = CampaignLauncher(session)
        cancelled = await launcher.cancel(later.id)
        assert cancelled.status == CampaignStatus.CANCELLED
        with pytest.raises(CampaignLocked) as not_scheduled:
            await launcher.cancel(running.id)
        assert not_scheduled.value.message == "Отменить можно только запланированную рассылку"

        stopped = await launcher.stop(running.id, NOW)
        assert stopped.status == CampaignStatus.STOPPED
        assert stopped.finished_at == NOW
        with pytest.raises(CampaignLocked) as not_running:
            await launcher.stop(later.id, NOW)
        assert not_running.value.message == "Остановить можно только идущую рассылку"

    sender = FakeSender()
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 0
    assert sender.calls == []
    async with pg_factory() as session:
        left = await session.scalar(
            select(func.count())
            .select_from(Outbox)
            .where(
                Outbox.deduplication_key.like(f"campaign:{running.id}:user:%"),
                Outbox.processed_at.is_(None),
            )
        )
        assert left == 0


async def test_send_test_uses_direct_urls_and_writes_nothing(db_session):
    await scenario(db_session)
    campaign = await draft(db_session, buttons=[{"kind": "url", "label": "Плейлист", "url": URL}])
    sender = FakeSender()

    await send_test(db_session, campaign.id, 42, sender, ready_settings())

    assert len(sender.calls) == 1
    telegram_id, message = sender.calls[0]
    assert telegram_id == 42
    assert message.buttons[0].url == URL
    assert await statuses(db_session, campaign.id) == {}
    assert campaign.status == CampaignStatus.DRAFT


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_launch_api(pg_factory, owner_env, monkeypatch):
    await make_admin(pg_factory)
    async with pg_factory() as session, session.begin():
        await scenario(session)
        night = await draft(session)
        now = await draft(session)
        later = await draft(session)
    app = owner_app(pg_factory)
    sender = FakeSender()
    app.dependency_overrides[campaign_sender] = lambda: sender
    headers = owner_headers()
    api = "/api/owner/campaigns"

    async with client_for(app) as client:
        monkeypatch.setattr("src.api.owner.campaigns.utcnow", lambda: NIGHT)
        response = await client.post(f"{api}/{night.id}/send", json={}, headers=headers)
        assert response.status_code == 422
        assert response.json() == {
            "field": "at",
            "message": "Ночью не отправляем. Отправить в 10:00?",
            "suggestedAt": MORNING.isoformat(),
        }

        monkeypatch.setattr("src.api.owner.campaigns.utcnow", lambda: NOW)
        started = await client.post(f"{api}/{now.id}/send", json={}, headers=headers)
        assert started.status_code == 200
        assert started.json()["status"] == "running"
        assert started.json()["recipientCount"] == 5

        at = (NOW + timedelta(days=1)).isoformat()
        scheduled = await client.post(f"{api}/{later.id}/send", json={"at": at}, headers=headers)
        assert scheduled.json()["status"] == "scheduled"
        past = await client.post(
            f"{api}/{later.id}/send", json={"at": NOW.isoformat()}, headers=headers
        )
        assert past.status_code == 422

        test = await client.post(f"{api}/{later.id}/test", headers=headers)
        assert test.status_code == 204
        assert [telegram_id for telegram_id, _ in sender.calls] == [42]

        cancelled = await client.post(f"{api}/{later.id}/cancel", headers=headers)
        assert cancelled.json()["status"] == "cancelled"
        stopped = await client.post(f"{api}/{now.id}/stop", headers=headers)
        assert stopped.json()["status"] == "stopped"
        again = await client.post(f"{api}/{now.id}/stop", headers=headers)
        assert again.status_code == 422
        assert again.json() == {"message": "Остановить можно только идущую рассылку"}

    async with pg_factory() as session:
        actions = list(
            await session.scalars(
                select(AdminAuditLog.action)
                .where(AdminAuditLog.action.like("owner.campaign.%"))
                .order_by(AdminAuditLog.created_at)
            )
        )
    assert actions[-5:] == [
        "owner.campaign.start",
        "owner.campaign.schedule",
        "owner.campaign.test",
        "owner.campaign.cancel",
        "owner.campaign.stop",
    ]
