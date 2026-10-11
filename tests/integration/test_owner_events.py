from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from src.models.admin import AdminAuditLog
from src.models.base import utcnow
from src.models.events import Event, EventStatus
from src.repositories.events import EventRepository
from src.repositories.users import UserRepository
from src.services.events.service import EventService
from src.services.reservations.service import ReservationItem
from src.services.users.service import UserService
from tests.commerce_fixtures import reservations
from tests.owner_fixtures import make_admin, owner_app, owner_headers
from tests.unit.services.test_events import draft

POSTER_KEY = "posters/" + "a" * 64
CONFLICT = {"message": "Событие уже изменили — обнови"}


def client_for(factory):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app(factory)), base_url="http://test"
    )


def event_body(**changes):
    start = datetime.now(UTC) + timedelta(days=3)
    body = {
        "title": "Кино вечером",
        "description": "Обсуждение фильма",
        "directionId": str(UUID(int=1)),
        "startsAt": start.isoformat(),
        "endsAt": (start + timedelta(hours=2)).isoformat(),
        "timezone": "Europe/Moscow",
        "capacity": 20,
        "ticketTypes": [{"name": "Обычный", "priceKopecks": 15000, "limit": 20}],
    }
    body.update(changes)
    return body


async def create_event(client, **changes):
    response = await client.post(
        "/api/owner/events", json=event_body(**changes), headers=owner_headers(42)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_poster(factory, event_id, focus=(0.4, 0.6)):
    async with factory() as session, session.begin():
        await EventService(EventRepository(session)).set_poster(
            UUID(event_id), POSTER_KEY, 1080, 1350, *focus
        )


async def listed(client, which):
    response = await client.get(f"/api/owner/events?filter={which}", headers=owner_headers(42))
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_get_list(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        fetched = await client.get(f"/api/owner/events/{created['id']}", headers=owner_headers(42))
        drafts = await listed(client, "draft")
    assert created["address"] is None
    assert created["poster"] is None
    assert created["status"] == "draft"
    assert created["sold"] == 0
    assert created["accentColor"] is None
    assert fetched.status_code == 200
    assert fetched.json() == created
    item = next(row for row in drafts if row["id"] == created["id"])
    assert item["sold"] == 0
    assert item["poster"] is None
    assert set(item) == {"id", "title", "startsAt", "status", "capacity", "sold", "poster"}


async def test_owner_event_shape(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client, address="Клуб Повод", accentColor="#AA00FF")
        await add_poster(pg_factory, created["id"])
        fetched = (
            await client.get(f"/api/owner/events/{created['id']}", headers=owner_headers(42))
        ).json()
    assert set(fetched) == {
        "id",
        "title",
        "description",
        "directionId",
        "startsAt",
        "endsAt",
        "timezone",
        "address",
        "mapUrl",
        "capacity",
        "ticketTypes",
        "status",
        "publishedAt",
        "createdAt",
        "updatedAt",
        "accentColor",
        "poster",
        "sold",
    }
    assert fetched["address"] == "Клуб Повод"
    assert fetched["accentColor"] == "#AA00FF"
    assert fetched["publishedAt"] is None
    assert fetched["poster"] == {
        "url": f"/media/{POSTER_KEY}-1080.webp",
        "focusX": 0.4,
        "focusY": 0.6,
        "width": 1080,
        "height": 1350,
    }
    ticket = fetched["ticketTypes"][0]
    assert set(ticket) == {"id", "name", "priceKopecks", "currency", "limit", "active"}
    assert (ticket["priceKopecks"], ticket["limit"], ticket["active"]) == (15000, 20, True)
    assert isinstance(fetched["updatedAt"], str)


async def test_legacy_cover_ref_url_is_returned_as_is(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with pg_factory() as session, session.begin():
        legacy = await EventService(EventRepository(session)).create_draft(
            draft(cover_ref="https://cdn.example/old.jpg")
        )
    async with client_for(pg_factory) as client:
        fetched = await client.get(f"/api/owner/events/{legacy.id}", headers=owner_headers(42))
    assert fetched.json()["poster"] == {
        "url": "https://cdn.example/old.jpg",
        "focusX": 0.5,
        "focusY": 0.5,
        "width": 0,
        "height": 0,
    }


async def test_field_error_shape(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.post(
            "/api/owner/events", json=event_body(title=""), headers=owner_headers(42)
        )
        late = await client.post(
            "/api/owner/events",
            json=event_body(endsAt=(datetime.now(UTC) - timedelta(days=9)).isoformat()),
            headers=owner_headers(42),
        )
    assert response.status_code == 422
    assert response.json() == {"field": "title", "message": "Назови вечер"}
    # Field names reach the Mini App in the same camelCase as the request keys.
    assert late.status_code == 422
    assert late.json() == {"field": "endsAt", "message": "Конец должен быть позже начала"}


async def test_publish_needs_poster(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        response = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
    assert response.status_code == 422
    assert response.json() == {"field": "poster", "message": "Без фото опубликовать нельзя"}


async def test_publish_started_event_names_the_date(pg_factory, owner_env):
    await make_admin(pg_factory)
    start = datetime.now(UTC) - timedelta(hours=3)
    async with client_for(pg_factory) as client:
        created = await create_event(
            client, startsAt=start.isoformat(), endsAt=(start + timedelta(hours=2)).isoformat()
        )
        await add_poster(pg_factory, created["id"])
        response = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
    assert response.status_code == 422
    assert response.json() == {"field": "startsAt", "message": "Вечер уже начался — поменяй дату"}


async def test_publish_and_unpublish_roundtrip(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        await add_poster(pg_factory, created["id"])
        published = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
        again = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
        unpublished = await client.post(
            f"/api/owner/events/{created['id']}/unpublish", headers=owner_headers(42)
        )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["publishedAt"] is not None
    assert published.json()["poster"]["width"] == 1080
    assert again.status_code == 422
    assert "message" in again.json()
    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "draft"
    assert unpublished.json()["publishedAt"] is None


async def test_patch_version_conflict(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        version = created["updatedAt"]
        first = await client.patch(
            f"/api/owner/events/{created['id']}",
            json={"updatedAt": version, "title": "Первая правка"},
            headers=owner_headers(42),
        )
        second = await client.patch(
            f"/api/owner/events/{created['id']}",
            json={"updatedAt": version, "title": "Вторая правка"},
            headers=owner_headers(42),
        )
        # The token comes back from the server and is sent back untouched.
        third = await client.patch(
            f"/api/owner/events/{created['id']}",
            json={"updatedAt": first.json()["updatedAt"], "title": "Третья правка"},
            headers=owner_headers(42),
        )
        fetched = await client.get(f"/api/owner/events/{created['id']}", headers=owner_headers(42))
    assert first.status_code == 200
    assert first.json()["title"] == "Первая правка"
    assert first.json()["updatedAt"] != version
    assert second.status_code == 409
    assert second.json() == CONFLICT
    assert third.status_code == 200
    assert fetched.json()["title"] == "Третья правка"
    assert fetched.json()["updatedAt"] == third.json()["updatedAt"]


async def test_patch_needs_valid_version(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        url = f"/api/owner/events/{created['id']}"
        missing = await client.patch(url, json={"title": "Без версии"}, headers=owner_headers(42))
        garbage = await client.patch(
            url, json={"updatedAt": "вчера", "title": "Х"}, headers=owner_headers(42)
        )
        naive = await client.patch(
            url, json={"updatedAt": "2026-10-11T10:00:00", "title": "Х"}, headers=owner_headers(42)
        )
    assert missing.status_code == 422
    expected = {"field": "updatedAt", "message": "Обнови форму и попробуй ещё раз"}
    assert garbage.status_code == 422
    assert garbage.json() == expected
    assert naive.status_code == 422
    assert naive.json() == expected


async def test_patch_clears_optional_fields_only(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(
            client, address="Клуб Повод", mapUrl="https://maps.example/x", accentColor="#112233"
        )
        url = f"/api/owner/events/{created['id']}"
        cleared = await client.patch(
            url,
            json={
                "updatedAt": created["updatedAt"],
                "address": None,
                "mapUrl": None,
                "accentColor": None,
            },
            headers=owner_headers(42),
        )
        null_title = await client.patch(
            url,
            json={"updatedAt": cleared.json()["updatedAt"], "title": None},
            headers=owner_headers(42),
        )
        cover = await client.patch(
            url,
            json={"updatedAt": cleared.json()["updatedAt"], "coverRef": "posters/x"},
            headers=owner_headers(42),
        )
        status = await client.patch(
            url,
            json={"updatedAt": cleared.json()["updatedAt"], "status": "cancelled"},
            headers=owner_headers(42),
        )
    assert cleared.status_code == 200
    body = cleared.json()
    assert (body["address"], body["mapUrl"], body["accentColor"]) == (None, None, None)
    assert null_title.status_code == 422
    assert null_title.json()["field"] == "title"
    assert cover.status_code == 422  # posters change only through their own endpoints
    assert status.status_code == 422  # cancelling goes through refunds, not the form


async def test_unpublish_with_order_409(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        await add_poster(pg_factory, created["id"])
        published = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
        assert published.status_code == 200
        async with pg_factory() as session, session.begin():
            user = await UserService(UserRepository(session)).upsert_telegram_user(
                100, None, None, None, None
            )
            ticket_id = UUID(published.json()["ticketTypes"][0]["id"])
            await reservations(session).reserve(
                UUID(created["id"]), [ReservationItem(ticket_id, 1)], user.id, utcnow()
            )
        response = await client.post(
            f"/api/owner/events/{created['id']}/unpublish", headers=owner_headers(42)
        )
        fetched = await client.get(f"/api/owner/events/{created['id']}", headers=owner_headers(42))
    assert response.status_code == 409
    assert response.json() == {"message": "Уже есть брони — отменить можно будет через возвраты"}
    assert fetched.json()["status"] == "published"


async def test_past_filter_and_sold(pg_factory, owner_env):
    await make_admin(pg_factory)
    now = utcnow()
    async with pg_factory() as session, session.begin():
        for title, status, starts, published in (
            ("Прошлый", EventStatus.DRAFT, now - timedelta(days=5), None),
            ("Отменённый", EventStatus.CANCELLED, now - timedelta(days=4), now),
            ("Завершённый", EventStatus.COMPLETED, now - timedelta(days=9), now),
        ):
            session.add(
                Event(
                    title=title,
                    description="Было",
                    direction_id=UUID(int=1),
                    starts_at=starts,
                    ends_at=starts + timedelta(hours=2),
                    timezone="Europe/Moscow",
                    capacity=10,
                    status=status,
                    published_at=published,
                )
            )
    async with client_for(pg_factory) as client:
        later = await create_event(
            client,
            title="Скоро",
            capacity=5,
            ticketTypes=[{"name": "Обычный", "priceKopecks": 100, "limit": 5}],
        )
        sooner = await create_event(
            client,
            title="Ещё скорее",
            capacity=5,
            startsAt=(now + timedelta(days=1)).isoformat(),
            endsAt=(now + timedelta(days=1, hours=2)).isoformat(),
            ticketTypes=[{"name": "Обычный", "priceKopecks": 100, "limit": 5}],
        )
        await add_poster(pg_factory, sooner["id"])
        published = await client.post(
            f"/api/owner/events/{sooner['id']}/publish", headers=owner_headers(42)
        )
        assert published.status_code == 200
        async with pg_factory() as session, session.begin():
            user = await UserService(UserRepository(session)).upsert_telegram_user(
                100, None, None, None, None
            )
            ticket_id = UUID(published.json()["ticketTypes"][0]["id"])
            await reservations(session).reserve(
                UUID(sooner["id"]), [ReservationItem(ticket_id, 2)], user.id, now
            )
        everything = await listed(client, "all")
        drafts = await listed(client, "draft")
        past = await listed(client, "past")
        fetched = await client.get(f"/api/owner/events/{sooner['id']}", headers=owner_headers(42))
    by_id = {row["id"]: row for row in everything}
    assert by_id[sooner["id"]]["sold"] == 2
    assert by_id[later["id"]]["sold"] == 0
    assert fetched.json()["sold"] == 2
    upcoming = [row["id"] for row in everything]
    assert upcoming.index(sooner["id"]) < upcoming.index(later["id"])  # soonest first
    assert [row["id"] for row in drafts] == [later["id"]]
    assert [row["title"] for row in past] == [
        "Прошлый",
        "Завершённый",
    ]  # newest first, no cancelled
    assert all(row["title"] not in {"Прошлый", "Отменённый", "Завершённый"} for row in everything)


async def test_unknown_filter_and_missing_event(pg_factory, owner_env):
    await make_admin(pg_factory)
    missing = UUID(int=999)
    async with client_for(pg_factory) as client:
        bad_filter = await client.get(
            "/api/owner/events?filter=cancelled", headers=owner_headers(42)
        )
        responses = [
            await client.get(f"/api/owner/events/{missing}", headers=owner_headers(42)),
            await client.patch(
                f"/api/owner/events/{missing}",
                json={"updatedAt": utcnow().isoformat()},
                headers=owner_headers(42),
            ),
            await client.post(f"/api/owner/events/{missing}/publish", headers=owner_headers(42)),
            await client.post(f"/api/owner/events/{missing}/unpublish", headers=owner_headers(42)),
        ]
    assert bad_filter.status_code == 422
    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    assert all(response.json() == {"message": "Вечер не найден"} for response in responses)


async def test_events_need_manage_events_permission(pg_factory, owner_env):
    await make_admin(pg_factory, role="entrance")
    async with client_for(pg_factory) as client:
        anonymous = await client.get("/api/owner/events")
        forbidden = await client.get("/api/owner/events", headers=owner_headers(42))
        created = await client.post(
            "/api/owner/events", json=event_body(), headers=owner_headers(42)
        )
    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert created.status_code == 403


async def test_audit_written(pg_factory, owner_env):
    admin_id = await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        url = f"/api/owner/events/{created['id']}"
        patched = await client.patch(
            url,
            json={"updatedAt": created["updatedAt"], "title": "Другое имя"},
            headers=owner_headers(42),
        )
        await add_poster(pg_factory, created["id"])
        await client.post(f"{url}/publish", headers=owner_headers(42))
        await client.post(f"{url}/unpublish", headers=owner_headers(42))
    assert patched.status_code == 200
    async with pg_factory() as session:
        rows = list(await session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at)))
    assert [row.action for row in rows] == [
        "owner.event.create",
        "owner.event.update",
        "owner.event.publish",
        "owner.event.unpublish",
    ]
    assert all(row.actor_id == admin_id for row in rows)
    assert all(row.object_type == "event" for row in rows)
    assert all(str(row.object_id) == created["id"] for row in rows)


async def test_failed_request_writes_no_audit(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.post(
            "/api/owner/events", json=event_body(title=""), headers=owner_headers(42)
        )
    assert response.status_code == 422
    async with pg_factory() as session:
        assert list(await session.scalars(select(AdminAuditLog))) == []


@pytest.mark.parametrize("which", ["all", "draft", "past"])
async def test_empty_lists(pg_factory, owner_env, which):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        assert await listed(client, which) == []
