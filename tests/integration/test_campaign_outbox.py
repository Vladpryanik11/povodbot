from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from src.models.campaigns import Campaign, CampaignDelivery, CampaignStatus, DeliveryStatus
from src.models.identity import User
from src.models.outbox import Outbox
from src.services.campaigns.audience import AudienceFilter, audience_count
from src.services.campaigns.delivery import CampaignDeliveryWorker
from src.services.campaigns.launch import CampaignLauncher
from src.services.campaigns.owner import OwnerCampaignService
from src.services.campaigns.render import RenderedMessage
from src.services.campaigns.telegram import RecipientBlocked, RetryAfter, SentMessage
from src.workers.outbox import MAX_DELIVERY_ATTEMPTS, CampaignOutboxWorker
from tests.campaign_fixtures import scenario

# 15:00 in Moscow, a working afternoon.
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


class Sender:
    """Answers like Telegram would; `errors` lists what each guest gets before a success."""

    def __init__(
        self,
        errors: dict[int, list[Exception]] | None = None,
        on_send: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.errors = errors or {}
        self.on_send = on_send
        self.calls: list[tuple[int, RenderedMessage]] = []

    async def send(self, telegram_id: int, message: RenderedMessage) -> SentMessage:
        pending = self.errors.get(telegram_id)
        if pending:
            raise pending.pop(0)
        self.calls.append((telegram_id, message))
        if self.on_send is not None:
            await self.on_send()
        photo = "file-1" if message.photo_path is not None else None
        return SentMessage(message_id=f"m{len(self.calls)}", photo_file_id=photo)


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def worker(pg_factory, sender: Sender, sleep: Any = None) -> CampaignOutboxWorker:
    return CampaignOutboxWorker(pg_factory, sender, sleep=sleep or Sleeps())


async def launched(pg_factory, image: dict[str, str] | None = None) -> UUID:
    """Guests 1, 2, 3, 5 and 6 are queued and staged in the outbox."""
    async with pg_factory() as session, session.begin():
        await scenario(session)
        campaign = await OwnerCampaignService(session).create(
            None, {"body": "<b>Приходи</b> в субботу"}
        )
        if image is not None:
            campaign.image = image
        await CampaignLauncher(session).send(campaign.id, None, NOW)
        assert await CampaignDeliveryWorker(session).deliver(campaign.id, now=NOW) == 5
    return campaign.id


async def deliveries(pg_factory, campaign_id: UUID) -> dict[int, CampaignDelivery]:
    async with pg_factory() as session:
        rows = await session.scalars(
            select(CampaignDelivery).where(CampaignDelivery.campaign_id == campaign_id)
        )
        return {row.telegram_id: row for row in rows}


async def campaign_row(pg_factory, campaign_id: UUID) -> Campaign:
    async with pg_factory() as session:
        campaign = await session.get(Campaign, campaign_id)
        assert campaign is not None
        return campaign


async def make_due(pg_factory) -> None:
    async with pg_factory() as session, session.begin():
        await session.execute(
            update(Outbox)
            .where(Outbox.processed_at.is_(None))
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )


async def outbox_for(pg_factory, campaign_id: UUID, telegram_id: int) -> Outbox:
    async with pg_factory() as session:
        row = await session.scalar(
            select(Outbox)
            .join(CampaignDelivery, CampaignDelivery.idempotency_key == Outbox.deduplication_key)
            .where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.telegram_id == telegram_id,
            )
        )
        assert row is not None
        return row


async def test_success_records_sent(pg_factory):
    campaign_id = await launched(pg_factory)
    sender = Sender()

    assert await worker(pg_factory, sender).process_pending() == 5

    rows = await deliveries(pg_factory, campaign_id)
    assert {row.status for row in rows.values()} == {DeliveryStatus.SENT}
    assert all(row.sent_at is not None and row.provider_message_id for row in rows.values())
    campaign = await campaign_row(pg_factory, campaign_id)
    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.finished_at is not None


async def test_retry_after_waits_and_does_not_burn_attempt(pg_factory):
    campaign_id = await launched(pg_factory)
    sender = Sender(errors={2: [RetryAfter(3)]})
    sleeps = Sleeps()

    assert await worker(pg_factory, sender, sleeps).process_pending() == 4

    assert sleeps.calls == [3]
    rows = await deliveries(pg_factory, campaign_id)
    assert rows[2].status == DeliveryStatus.QUEUED
    assert rows[2].attempts == 0
    assert (await outbox_for(pg_factory, campaign_id, 2)).attempts == 0
    assert (await campaign_row(pg_factory, campaign_id)).status == CampaignStatus.RUNNING

    await make_due(pg_factory)
    assert await worker(pg_factory, sender).process_pending() == 1
    assert (await deliveries(pg_factory, campaign_id))[2].status == DeliveryStatus.SENT
    assert (await campaign_row(pg_factory, campaign_id)).status == CampaignStatus.COMPLETED


async def test_forbidden_marks_user_blocked(pg_factory):
    campaign_id = await launched(pg_factory)
    sender = Sender(errors={3: [RecipientBlocked()]})

    assert await worker(pg_factory, sender).process_pending() == 4

    rows = await deliveries(pg_factory, campaign_id)
    assert rows[3].status == DeliveryStatus.BLOCKED
    assert rows[3].error == "bot_blocked"
    async with pg_factory() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 3))
        assert user is not None and user.is_blocked
        sendable, _ = await audience_count(session, AudienceFilter().to_definition(), NOW)
    assert sendable == 4
    assert (await campaign_row(pg_factory, campaign_id)).status == CampaignStatus.COMPLETED


async def test_failure_retries_then_fails(pg_factory):
    campaign_id = await launched(pg_factory)
    sender = Sender(errors={5: [RuntimeError("boom")] * MAX_DELIVERY_ATTEMPTS})

    before = datetime.now(UTC)
    assert await worker(pg_factory, sender).process_pending() == 4
    rows = await deliveries(pg_factory, campaign_id)
    assert rows[5].status == DeliveryStatus.QUEUED
    assert rows[5].error == "boom"
    assert (await outbox_for(pg_factory, campaign_id, 5)).available_at >= before + timedelta(
        seconds=30
    )

    for _ in range(MAX_DELIVERY_ATTEMPTS - 1):
        await make_due(pg_factory)
        assert await worker(pg_factory, sender).process_pending() == 0

    rows = await deliveries(pg_factory, campaign_id)
    assert rows[5].status == DeliveryStatus.FAILED
    assert (await outbox_for(pg_factory, campaign_id, 5)).processed_at is not None
    campaign = await campaign_row(pg_factory, campaign_id)
    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.finished_at is not None


async def test_photo_file_id_is_cached(pg_factory):
    campaign_id = await launched(pg_factory, image={"kind": "upload", "ref": "campaigns/abc"})
    sender = Sender()

    assert await worker(pg_factory, sender).process_pending() == 5

    first, *rest = [message for _, message in sender.calls]
    assert first.photo_path is not None and first.photo_file_id is None
    assert rest and all(m.photo_file_id == "file-1" and m.photo_path is None for m in rest)
    assert (await campaign_row(pg_factory, campaign_id)).telegram_photo_id == "file-1"


async def test_stopped_campaign_sends_nothing(pg_factory):
    campaign_id = await launched(pg_factory)
    # The worker already holds these jobs when the owner presses «Остановить».
    async with pg_factory() as session, session.begin():
        campaign = await session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.status = CampaignStatus.STOPPED
    sender = Sender()

    assert await worker(pg_factory, sender).process_pending() == 0

    assert sender.calls == []
    rows = await deliveries(pg_factory, campaign_id)
    assert {row.status for row in rows.values()} == {DeliveryStatus.QUEUED}
    async with pg_factory() as session:
        left = await session.scalar(select(Outbox).where(Outbox.processed_at.is_(None)))
    assert left is None
    assert (await campaign_row(pg_factory, campaign_id)).status == CampaignStatus.STOPPED


async def test_message_in_flight_when_stopped_counts_as_sent(pg_factory):
    campaign_id = await launched(pg_factory)

    sender = Sender()

    async def stop_once() -> None:
        sender.on_send = None
        async with pg_factory() as session, session.begin():
            await CampaignLauncher(session).stop(campaign_id, NOW)

    sender.on_send = stop_once

    assert await worker(pg_factory, sender).process_pending() == 1

    rows = await deliveries(pg_factory, campaign_id)
    sent = [row for row in rows.values() if row.status == DeliveryStatus.SENT]
    assert [row.telegram_id for row in sent] == [sender.calls[0][0]]
    assert sum(row.status == DeliveryStatus.QUEUED for row in rows.values()) == 4
    assert (await campaign_row(pg_factory, campaign_id)).status == CampaignStatus.STOPPED
