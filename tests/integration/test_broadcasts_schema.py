import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.campaigns import (
    Campaign,
    CampaignDelivery,
    CampaignStatus,
    CampaignTemplate,
    DeliveryStatus,
)
from src.models.favorites import Favorite
from tests.commerce_fixtures import catalog

BUILTIN_NAMES = {
    "Новый вечер в афише",
    "Осталось мало мест",
    "Завтра вечер",
    "Спасибо, что пришли",
    "Вечер перенесён",
}


async def test_favorite_primary_key(db_session):
    event, user = await catalog(db_session)
    db_session.add(Favorite(user_id=user.id, event_id=event.id))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Favorite(user_id=user.id, event_id=event.id))
            await db_session.flush()


async def test_campaign_defaults_and_short_code(db_session):
    campaign = Campaign(title="Черновик", body="", audience={})
    db_session.add(campaign)
    await db_session.flush()
    await db_session.refresh(campaign)
    assert campaign.image == {"kind": "none"}
    assert campaign.buttons == []
    assert len(campaign.short_code) == 8
    assert campaign.short_code.isalnum()

    campaign.status = CampaignStatus.STOPPED
    await db_session.flush()
    await db_session.refresh(campaign)
    assert campaign.status == "stopped"

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Campaign(title="Плохой", body="x", audience={}, status="bogus"))
            await db_session.flush()


async def test_delivery_accepts_skipped_limit(db_session):
    _, user = await catalog(db_session)
    campaign = Campaign(title="Лимит", body="x", audience={})
    db_session.add(campaign)
    await db_session.flush()
    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        user_id=user.id,
        telegram_id=user.telegram_id,
        idempotency_key=f"campaign:{campaign.id}:user:{user.id}",
        status=DeliveryStatus.SKIPPED_LIMIT,
        attempts=0,
    )
    db_session.add(delivery)
    await db_session.flush()
    await db_session.refresh(delivery)
    assert delivery.status == "skipped_limit"


async def test_builtin_templates_seeded(db_session):
    templates = list(
        await db_session.scalars(select(CampaignTemplate).where(CampaignTemplate.is_builtin))
    )
    assert {template.name for template in templates} == BUILTIN_NAMES
    thanks = next(t for t in templates if t.name == "Спасибо, что пришли")
    assert (thanks.image_kind, thanks.buttons) == ("none", [])
    fresh = next(t for t in templates if t.name == "Новый вечер в афише")
    assert fresh.buttons == [{"kind": "event", "label": "Открыть вечер"}]
