from dataclasses import dataclass

from src.models.campaigns import Campaign, CampaignStatus
from src.models.identity import ConsentSource, ConsentType
from src.repositories.admin import AdminRepository
from src.repositories.consents import ConsentRepository
from src.repositories.users import UserRepository
from src.services.admin.auth import AdminAuthService
from src.services.campaigns.composer import CampaignService
from src.services.campaigns.delivery import CampaignDeliveryWorker
from src.services.consents.service import ConsentService
from src.services.crm.segments import SegmentService
from src.services.users.service import UserService
from src.workers.outbox import CampaignOutboxWorker


@dataclass
class Sender:
    calls: list[int]

    async def send_message(self, telegram_id: int, text: str) -> str:
        self.calls.append(telegram_id)
        return "message-1"


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
        assert await CampaignDeliveryWorker(session, sender).deliver(campaign.id) == 0
    assert sender.calls == [200]


async def test_segment_excludes_blocked_and_unconsented_users(db_session):
    first = await UserService(UserRepository(db_session)).upsert_telegram_user(
        201, "Granted", None, None, None
    )
    await UserService(UserRepository(db_session)).upsert_telegram_user(
        202, "Blocked", None, None, None
    )
    second_model = await UserRepository(db_session).by_telegram_id(202)
    assert second_model is not None
    second_model.is_blocked = True
    await ConsentService(ConsentRepository(db_session)).record(
        first.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
    )
    recipients = await SegmentService(db_session).resolve({})
    assert [recipient.telegram_id for recipient in recipients] == [201]


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
