from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.models.campaigns import DeliveryStatus
from src.services.campaigns.audience import AudienceFilter, audience_count, limited_user_ids
from src.services.crm.segments import SegmentService
from tests.campaign_fixtures import D1, D2, delivered, evening, guest

NOW = datetime.now(UTC)


async def scenario(session):
    x = await evening(session, D1)
    y = await evening(session, D2, title="Книжный вечер")
    people = {
        "A": await guest(session, 1, going=[x]),
        "B": await guest(session, 2, attended=[x]),
        "C": await guest(session, 3, liked=[x]),
        "E": await guest(session, 5, liked=[x], going=[x]),
        "F": await guest(session, 6),
        "G": await guest(session, 7, liked=[x], blocked=True),
        "H": await guest(session, 8, liked=[x], revoked=True),
    }
    return x, y, people


async def picked(session, people, raw: dict) -> set[str]:
    definition = AudienceFilter.model_validate(raw).to_definition()
    names = {user.telegram_id: name for name, user in people.items()}
    recipients = await SegmentService(session).resolve(definition)
    assert await SegmentService(session).count(definition) == len(recipients)
    return {names[recipient.telegram_id] for recipient in recipients}


async def test_event_relations(db_session):
    x, _, people = await scenario(db_session)

    def on_x(relation):
        return {"event": {"id": str(x), "relation": relation}}

    assert await picked(db_session, people, on_x("going")) == {"A", "B", "E"}
    assert await picked(db_session, people, on_x("attended")) == {"B"}
    assert await picked(db_session, people, on_x("liked")) == {"C", "E"}
    assert await picked(db_session, people, on_x("liked_not_bought")) == {"C"}


async def test_direction_and_purchases(db_session):
    x, _, people = await scenario(db_session)
    assert await picked(db_session, people, {"directionId": str(D1)}) == {"A", "B", "C", "E"}
    assert await picked(db_session, people, {"directionId": str(D2)}) == set()
    assert await picked(db_session, people, {"purchases": "bought"}) == {"A", "B", "E"}
    assert await picked(db_session, people, {"purchases": "never"}) == {"C", "F"}
    liked_never = {"event": {"id": str(x), "relation": "liked"}, "purchases": "never"}
    assert await picked(db_session, people, liked_never) == {"C"}
    assert await picked(db_session, people, {}) == {"A", "B", "C", "E", "F"}


def test_audience_filter_rejects_unknown_relation():
    with pytest.raises(ValidationError):
        AudienceFilter.model_validate({"event": {"id": str(D1), "relation": "maybe"}})
    with pytest.raises(ValidationError):
        AudienceFilter.model_validate({"segment": "all"})


async def test_limit_counts_two_sent_in_seven_days(db_session):
    _, _, people = await scenario(db_session)
    a, b, c = people["A"], people["B"], people["C"]
    for _ in range(2):
        await delivered(db_session, a, NOW - timedelta(days=6))
        await delivered(db_session, c, NOW - timedelta(days=8))
    await delivered(db_session, b, NOW - timedelta(days=1))
    await delivered(db_session, b, NOW - timedelta(days=1), DeliveryStatus.FAILED)

    limited = await limited_user_ids(db_session, [a.id, b.id, c.id], NOW)
    assert limited == {a.id}
    assert await audience_count(db_session, {}, NOW) == (4, 1)
