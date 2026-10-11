from uuid import uuid4

import httpx
from sqlalchemy import select

from src.models.identity import User
from tests.commerce_fixtures import catalog
from tests.owner_fixtures import owner_app, owner_headers
from tests.unit.services.test_events import draft, service

GUEST = 777


def client_for(factory):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app(factory)), base_url="http://test"
    )


async def evenings(factory):
    async with factory() as session, session.begin():
        published, _ = await catalog(session)
        hidden = await service(session).create_draft(draft())
        return str(published.id), str(hidden.id)


async def test_favorites_need_init_data(pg_factory, owner_env):
    async with client_for(pg_factory) as client:
        response = await client.get("/api/app/favorites")
    assert response.status_code == 401


async def test_put_is_idempotent_and_get_lists(pg_factory, owner_env):
    published, _ = await evenings(pg_factory)
    async with client_for(pg_factory) as client:
        first = await client.put(f"/api/app/favorites/{published}", headers=owner_headers(GUEST))
        second = await client.put(f"/api/app/favorites/{published}", headers=owner_headers(GUEST))
        listed = await client.get("/api/app/favorites", headers=owner_headers(GUEST))
    assert (first.status_code, second.status_code) == (204, 204)
    assert listed.json() == {"eventIds": [published]}
    async with pg_factory() as session:
        user = await session.scalar(select(User).where(User.telegram_id == GUEST))
    assert user is not None
    assert user.first_name == "Test"


async def test_put_unpublished_event_is_404(pg_factory, owner_env):
    _, hidden = await evenings(pg_factory)
    async with client_for(pg_factory) as client:
        draft_response = await client.put(
            f"/api/app/favorites/{hidden}", headers=owner_headers(GUEST)
        )
        unknown = await client.put(f"/api/app/favorites/{uuid4()}", headers=owner_headers(GUEST))
    assert draft_response.status_code == 404
    assert draft_response.json() == {"message": "Вечер не найден"}
    assert unknown.status_code == 404


async def test_delete_is_idempotent(pg_factory, owner_env):
    published, _ = await evenings(pg_factory)
    async with client_for(pg_factory) as client:
        await client.put(f"/api/app/favorites/{published}", headers=owner_headers(GUEST))
        removed = await client.delete(
            f"/api/app/favorites/{published}", headers=owner_headers(GUEST)
        )
        missing = await client.delete(f"/api/app/favorites/{uuid4()}", headers=owner_headers(GUEST))
        listed = await client.get("/api/app/favorites", headers=owner_headers(GUEST))
    assert (removed.status_code, missing.status_code) == (204, 204)
    assert listed.json() == {"eventIds": []}


async def test_import_skips_unknown_and_unpublished(pg_factory, owner_env):
    published, hidden = await evenings(pg_factory)
    async with client_for(pg_factory) as client:
        imported = await client.post(
            "/api/app/favorites/import",
            json={"eventIds": [published, hidden, str(uuid4())]},
            headers=owner_headers(GUEST),
        )
        again = await client.post(
            "/api/app/favorites/import",
            json={"eventIds": [published]},
            headers=owner_headers(GUEST),
        )
        too_many = await client.post(
            "/api/app/favorites/import",
            json={"eventIds": [str(uuid4()) for _ in range(201)]},
            headers=owner_headers(GUEST),
        )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"eventIds": [published]}
    assert again.json() == {"eventIds": [published]}
    assert too_many.status_code == 422
