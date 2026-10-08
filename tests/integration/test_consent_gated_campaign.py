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


@dataclass
class Sender:
    calls: list[int]

    async def send_message(self, telegram_id: int, text: str) -> str:
        self.calls.append(telegram_id)
        return "message-1"


async def test_campaign_preview_and_delivery_require_current_marketing_consent(db_session):
    user = await UserService(UserRepository(db_session)).upsert_telegram_user(
        200, "Alice", None, None, "campaign"
    )
    await ConsentService(ConsentRepository(db_session)).record(
        user.id, ConsentType.MARKETING, "v1", ConsentSource.TELEGRAM
    )
    admin = await AdminAuthService(AdminRepository(db_session)).create_user(
        "campaign-admin", "password-123"
    )
    campaign = await CampaignService(db_session).create_draft(
        admin.id, "Test", "Hello", {"telegram_ids": [200]}
    )
    campaign_model = await db_session.get(Campaign, campaign.id)
    assert campaign_model is not None
    campaign_model.status = CampaignStatus.SCHEDULED
    preview = await CampaignService(db_session).preview(campaign.id)
    assert preview.eligible_count == 1
    sender = Sender([])
    assert await CampaignDeliveryWorker(db_session, sender).deliver(campaign.id) == 1
    assert sender.calls == [200]

    # A second run is idempotent and does not send again.
    assert await CampaignDeliveryWorker(db_session, sender).deliver(campaign.id) == 0
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
