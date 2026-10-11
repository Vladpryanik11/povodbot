from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.campaigns import Campaign, CampaignDelivery, CampaignStatus, DeliveryStatus
from src.models.identity import ConsentSource, ConsentType
from src.models.outbox import Outbox
from src.repositories.admin import AdminRepository
from src.repositories.consents import ConsentRepository
from src.repositories.users import UserRepository
from src.services.admin.auth import AdminAuthService
from src.services.campaigns.composer import CampaignService
from src.services.campaigns.delivery import CampaignDeliveryWorker
from src.services.campaigns.render import RenderedMessage
from src.services.campaigns.telegram import SentMessage
from src.services.consents.service import ConsentService
from src.services.crm.segments import SegmentService
from src.services.users.service import UserService
from src.workers.outbox import CampaignOutboxWorker


@dataclass
class Sender:
    calls: list[int]

    async def send(self, telegram_id: int, message: RenderedMessage) -> SentMessage:
        self.calls.append(telegram_id)
        return SentMessage(message_id="message-1", photo_file_id=None)


async def test_campaign_draft_schedule_requires_future_aware_utc(db_session):
    admin = await AdminAuthService(AdminRepository(db_session)).create_user(
        "schedule-admin", "password-123"
    )
    service = CampaignService(db_session)

    with pytest.raises(ValueError, match="timezone-aware"):
        await service.create_draft(
            admin.id, "Naive", "Hello", {}, scheduled_at=datetime(2026, 10, 9, 12)
        )

    with pytest.raises(ValueError, match="future"):
        await service.create_draft(
            admin.id,
            "Past",
            "Hello",
            {},
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    future = datetime.now(UTC) + timedelta(hours=1)
    campaign = await service.create_draft(
        admin.id,
        "Future",
        "Hello",
        {},
        scheduled_at=future.astimezone(timezone(timedelta(hours=3))),
    )
    assert campaign.scheduled_at == future.astimezone(UTC)
    assert campaign.status == CampaignStatus.DRAFT


def tomorrow_msk(hour: int, minute: int = 0) -> datetime:
    msk = timezone(timedelta(hours=3))
    day = datetime.now(msk).date() + timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=msk)


async def legacy_draft(db_session, body: str):
    admin = await AdminAuthService(AdminRepository(db_session)).create_user(
        "legacy-admin", "password-123"
    )
    service = CampaignService(db_session)
    return service, await service.create_draft(admin.id, "Legacy", body, {})


async def test_legacy_schedule_refuses_quiet_hours(db_session):
    service, campaign = await legacy_draft(db_session, "Hello")

    with pytest.raises(ValueError, match="quiet hours"):
        await service.schedule(campaign.id, tomorrow_msk(23, 30))

    scheduled = await service.schedule(campaign.id, tomorrow_msk(12))
    assert scheduled.status == CampaignStatus.SCHEDULED


async def test_legacy_schedule_refuses_text_telegram_cannot_parse_as_html(db_session):
    service, campaign = await legacy_draft(db_session, "Entry 2 < 3 & drinks")

    with pytest.raises(ValueError):
        await service.schedule(campaign.id, tomorrow_msk(12))


async def test_campaign_preview_and_delivery_require_current_marketing_consent(pg_factory):
    async with pg_factory() as session, session.begin():
        user = await UserService(UserRepository(session)).upsert_telegram_user(
            200, "Alice", None, None, "campaign"
        )
        await ConsentService(ConsentRepository(session)).record(
            user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
        )
        admin = await AdminAuthService(AdminRepository(session)).create_user(
            "campaign-admin", "password-123"
        )
        campaign = await CampaignService(session).create_draft(
            admin.id, "Test", "Hello", {"telegram_ids": [200]}
        )
        campaign_model = await session.get(Campaign, campaign.id)
        assert campaign_model is not None
        campaign_model.status = CampaignStatus.SCHEDULED
        preview = await CampaignService(session).preview(campaign.id)
        assert preview.eligible_count == 1
        assert await CampaignDeliveryWorker(session).deliver(campaign.id) == 1

    sender = Sender([])
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 1
    assert sender.calls == [200]

    # A second run is idempotent and does not send again.
    async with pg_factory() as session, session.begin():
        assert await CampaignDeliveryWorker(session).deliver(campaign.id) == 0
    assert sender.calls == [200]


async def test_segment_excludes_blocked_and_stopped_users_but_not_silent_ones(db_session):
    users = UserService(UserRepository(db_session))
    consents = ConsentService(ConsentRepository(db_session))
    silent = await users.upsert_telegram_user(201, "NoRecord", None, None, None)
    granted = await users.upsert_telegram_user(202, "Granted", None, None, None)
    stopped = await users.upsert_telegram_user(203, "Stopped", None, None, None)
    await users.upsert_telegram_user(204, "Blocked", None, None, None)
    blocked_model = await UserRepository(db_session).by_telegram_id(204)
    assert blocked_model is not None
    blocked_model.is_blocked = True
    await consents.record(granted.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM)
    await consents.record(stopped.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM)
    await consents.revoke(stopped.id, ConsentType.MARKETING, ConsentSource.TELEGRAM)
    recipients = await SegmentService(db_session).resolve({})
    assert sorted(r.telegram_id for r in recipients) == [201, 202]
    assert silent.id in {r.user_id for r in recipients}
    # /stop is not final: a later grant brings the user back.
    await consents.record(stopped.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM)
    again = await SegmentService(db_session).resolve({})
    assert sorted(r.telegram_id for r in again) == [201, 202, 203]


async def test_campaign_delivery_continues_with_later_batches(pg_factory):
    users = []
    async with pg_factory() as session, session.begin():
        for telegram_id in (203, 204, 205):
            user = await UserService(UserRepository(session)).upsert_telegram_user(
                telegram_id, f"User {telegram_id}", None, None, None
            )
            await ConsentService(ConsentRepository(session)).record(
                user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
            )
            users.append(user)

        admin = await AdminAuthService(AdminRepository(session)).create_user(
            "batch-admin", "password-123"
        )
        campaign = await CampaignService(session).create_draft(
            admin.id, "Batch", "Hello", {"telegram_ids": [user.telegram_id for user in users]}
        )
        campaign_model = await session.get(Campaign, campaign.id)
        assert campaign_model is not None
        campaign_model.status = CampaignStatus.SCHEDULED
        worker = CampaignDeliveryWorker(session)
        assert await worker.deliver(campaign.id, batch_size=2) == 2

    sender = Sender([])
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 2
    async with pg_factory() as session, session.begin():
        assert await CampaignDeliveryWorker(session).deliver(campaign.id, batch_size=2) == 1
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 1
    assert len(sender.calls) == 3
    assert set(sender.calls) == {203, 204, 205}


async def test_campaign_outbox_rechecks_consent_before_telegram_send(pg_factory):
    async with pg_factory() as session, session.begin():
        user = await UserService(UserRepository(session)).upsert_telegram_user(
            206, "Revoked", None, None, None
        )
        await ConsentService(ConsentRepository(session)).record(
            user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
        )
        admin = await AdminAuthService(AdminRepository(session)).create_user(
            "revoked-campaign-admin", "password-123"
        )
        campaign = await CampaignService(session).create_draft(
            admin.id, "Revoked", "Hello", {"telegram_ids": [206]}
        )
        campaign_model = await session.get(Campaign, campaign.id)
        assert campaign_model is not None
        campaign_model.status = CampaignStatus.SCHEDULED
        assert await CampaignDeliveryWorker(session).deliver(campaign.id) == 1

    async with pg_factory() as session, session.begin():
        await ConsentService(ConsentRepository(session)).revoke(
            user.id, ConsentType.MARKETING, ConsentSource.TELEGRAM
        )

    sender = Sender([])
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 0
    assert sender.calls == []

    async with pg_factory() as session, session.begin():
        delivery = await session.scalar(
            select(CampaignDelivery).where(CampaignDelivery.campaign_id == campaign.id)
        )
        outbox = await session.scalar(
            select(Outbox).where(
                Outbox.deduplication_key == f"campaign:{campaign.id}:user:{user.id}"
            )
        )
        assert delivery is not None
        assert DeliveryStatus(delivery.status) == DeliveryStatus.BLOCKED
        assert outbox is not None
        assert outbox.processed_at is not None


async def test_campaign_completes_after_last_outbox_delivery(pg_factory):
    async with pg_factory() as session, session.begin():
        user = await UserService(UserRepository(session)).upsert_telegram_user(
            207, "Last", None, None, None
        )
        await ConsentService(ConsentRepository(session)).record(
            user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
        )
        admin = await AdminAuthService(AdminRepository(session)).create_user(
            "completed-campaign-admin", "password-123"
        )
        campaign = await CampaignService(session).create_draft(
            admin.id, "Last", "Hello", {"telegram_ids": [207]}
        )
        campaign_model = await session.get(Campaign, campaign.id)
        assert campaign_model is not None
        campaign_model.status = CampaignStatus.SCHEDULED
        assert await CampaignDeliveryWorker(session).deliver(campaign.id) == 1

    sender = Sender([])
    assert await CampaignOutboxWorker(pg_factory, sender).process_pending() == 1

    async with pg_factory() as session, session.begin():
        campaign_model = await session.get(Campaign, campaign.id)
        assert campaign_model is not None
        assert CampaignStatus(campaign_model.status) == CampaignStatus.COMPLETED
