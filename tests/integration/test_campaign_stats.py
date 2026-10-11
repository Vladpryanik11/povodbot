from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select

from src.models.campaigns import (
    Campaign,
    CampaignClick,
    CampaignDelivery,
    CampaignLink,
    CampaignStatus,
    DeliveryStatus,
)
from src.models.commerce import OrderEvent, OrderStatus
from src.models.identity import User
from src.services.campaigns.stats import campaign_stats
from tests.campaign_fixtures import evening, guest, paid_order
from tests.owner_fixtures import make_admin, owner_app, owner_headers

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
URL = "https://music.example/playlist"
URL_BUTTON = {"kind": "url", "label": "Плейлист", "url": URL}
EVENT_BUTTON = {"kind": "event", "label": "Открыть вечер"}


def client_for(factory) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app(factory)), base_url="http://test"
    )


async def sent_campaign(
    session, event_id: UUID | None = None, buttons: list[dict[str, Any]] | None = None
) -> Campaign:
    campaign = Campaign(
        title="Суббота",
        body="Приходи",
        audience={},
        status=CampaignStatus.COMPLETED,
        event_id=event_id,
        buttons=buttons or [],
        started_at=NOW,
        finished_at=NOW,
        recipient_count=0,
    )
    session.add(campaign)
    await session.flush()
    return campaign


async def recipient(
    session, campaign: Campaign, user: User, status: str, error: str | None = None
) -> None:
    session.add(
        CampaignDelivery(
            campaign_id=campaign.id,
            user_id=user.id,
            telegram_id=user.telegram_id,
            idempotency_key=f"campaign:{campaign.id}:user:{user.id}",
            status=status,
            error=error,
            sent_at=NOW if status == DeliveryStatus.SENT else None,
        )
    )
    await session.flush()


async def paid_at(session, user: User, event_id: UUID, when: datetime) -> None:
    order = await paid_order(session, user, event_id)
    session.add(
        OrderEvent(
            order_id=order.id,
            previous_status=OrderStatus.PENDING_PAYMENT,
            next_status=OrderStatus.PAID,
            action="pay",
            reason="test",
            created_at=when,
        )
    )
    await session.flush()


async def clicks(factory) -> list[tuple[UUID, UUID | None, int]]:
    async with factory() as session:
        rows = await session.scalars(select(CampaignClick).order_by(CampaignClick.clicked_at))
        return [(row.campaign_id, row.user_id, row.button_index) for row in rows]


async def test_redirect_records_click(pg_factory, owner_env):
    async with pg_factory() as session, session.begin():
        campaign = await sent_campaign(session, buttons=[URL_BUTTON])
        session.add(CampaignLink(code="abc123", campaign_id=campaign.id, button_index=0, url=URL))

    async with client_for(pg_factory) as client:
        found = await client.get("/r/abc123")
        missing = await client.get("/r/nope")

    assert found.status_code == 302
    assert found.headers["location"] == URL
    assert missing.status_code == 404
    assert await clicks(pg_factory) == [(campaign.id, None, 0)]


async def test_campaign_open_records_event_button(pg_factory, owner_env):
    async with pg_factory() as session, session.begin():
        x = await evening(session)
        campaign = await sent_campaign(session, x, [URL_BUTTON, EVENT_BUTTON])

    async with client_for(pg_factory) as client:
        opened = await client.post(
            "/api/app/campaign-open",
            json={"campaign": campaign.short_code},
            headers=owner_headers(501),
        )
        unknown = await client.post(
            "/api/app/campaign-open", json={"campaign": "nope"}, headers=owner_headers(501)
        )
        stranger = await client.post(
            "/api/app/campaign-open", json={"campaign": campaign.short_code}
        )

    assert (opened.status_code, unknown.status_code) == (204, 204)
    assert stranger.status_code == 401
    async with pg_factory() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 501))
    assert user is not None
    assert await clicks(pg_factory) == [(campaign.id, user.id, 1)]


async def seed_stats(session) -> Campaign:
    """Four recipients: two got it, one blocked the bot, one hit the weekly limit."""
    x = await evening(session)
    campaign = await sent_campaign(session, x, [URL_BUTTON, EVENT_BUTTON])
    soon, late, blocked, limited = [await guest(session, n) for n in (11, 12, 13, 14)]
    await recipient(session, campaign, soon, DeliveryStatus.SENT)
    await recipient(session, campaign, late, DeliveryStatus.SENT)
    await recipient(session, campaign, blocked, DeliveryStatus.BLOCKED, "bot_blocked")
    await recipient(session, campaign, limited, DeliveryStatus.SKIPPED_LIMIT)
    for index in (0, 1):
        session.add(CampaignClick(campaign_id=campaign.id, user_id=soon.id, button_index=index))
    session.add(CampaignClick(campaign_id=campaign.id, user_id=None, button_index=0))
    await paid_at(session, soon, x, NOW + timedelta(days=2))
    await paid_at(session, late, x, NOW + timedelta(days=8))
    await session.flush()
    return campaign


async def test_stats(pg_factory, owner_env):
    async with pg_factory() as session, session.begin():
        campaign = await seed_stats(session)
        stats = await campaign_stats(session, campaign.id)
    await make_admin(pg_factory)

    assert stats.bought == 1
    async with client_for(pg_factory) as client:
        response = await client.get(
            f"/api/owner/campaigns/{campaign.id}/stats", headers=owner_headers()
        )

    assert response.status_code == 200
    assert response.json() == {
        "recipients": 4,
        "delivered": 2,
        "failed": 1,
        "failedReasons": {"bot_blocked": 1},
        "skippedLimit": 1,
        "clicked": 1,
        "anonymousClicks": 1,
        "bought": 1,
    }


async def test_stats_without_evening_has_no_bought(pg_factory, owner_env):
    async with pg_factory() as session, session.begin():
        campaign = await sent_campaign(session, buttons=[URL_BUTTON])
        stats = await campaign_stats(session, campaign.id)
    assert stats.bought is None
    assert stats.recipients == 0


async def test_list_card_summary(pg_factory, owner_env):
    async with pg_factory() as session, session.begin():
        campaign = await seed_stats(session)
    await make_admin(pg_factory)

    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/campaigns?filter=sent", headers=owner_headers())

    assert response.status_code == 200
    card = next(item for item in response.json() if item["id"] == str(campaign.id))
    assert (card["delivered"], card["clicked"]) == (2, 1)
