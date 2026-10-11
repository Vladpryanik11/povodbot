import time

import httpx
import pytest

from src.core.config import get_settings
from src.repositories.directions import DirectionRepository
from tests.owner_fixtures import make_admin, owner_app, owner_headers, sign_init_data

HOUR = 3600


def client_for(factory):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app(factory)), base_url="http://test"
    )


async def test_me_for_owner(pg_factory, owner_env):
    await make_admin(pg_factory, role="owner")
    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/me", headers=owner_headers(42))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "owner"
    assert "manage_events" in body["permissions"]


async def test_missing_or_bad_signature_401(pg_factory, owner_env):
    await make_admin(pg_factory, role="owner")
    foreign = {"Authorization": f"tma {sign_init_data(42, token='999:other')}"}
    async with client_for(pg_factory) as client:
        assert (await client.get("/api/owner/me")).status_code == 401
        assert (await client.get("/api/owner/me", headers=foreign)).status_code == 401


@pytest.mark.parametrize("header", ["", "tma", "tma ", "tma garbage", "Bearer abc", "abc"])
async def test_malformed_authorization_401(pg_factory, owner_env, header):
    await make_admin(pg_factory, role="owner")
    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/me", headers={"Authorization": header})
    assert response.status_code == 401


async def test_tampered_user_id_401(pg_factory, owner_env):
    await make_admin(pg_factory, role="owner", telegram_id=42)
    await make_admin(pg_factory, role="owner", telegram_id=43)
    tampered = sign_init_data(42).replace("%22id%22%3A42", "%22id%22%3A43")
    assert tampered != sign_init_data(42)
    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/me", headers={"Authorization": f"tma {tampered}"})
    assert response.status_code == 401


async def test_expired_auth_date_401(pg_factory, owner_env):
    await make_admin(pg_factory, role="owner")
    async with client_for(pg_factory) as client:
        stale = owner_headers(42, auth_date=int(time.time()) - 25 * HOUR)
        fresh = owner_headers(42, auth_date=int(time.time()) - 23 * HOUR)
        assert (await client.get("/api/owner/me", headers=stale)).status_code == 401
        assert (await client.get("/api/owner/me", headers=fresh)).status_code == 200


async def test_unknown_or_inactive_user_403(pg_factory, owner_env):
    await make_admin(pg_factory, role="owner", telegram_id=42, is_active=False)
    async with client_for(pg_factory) as client:
        unknown = await client.get("/api/owner/me", headers=owner_headers(999))
        inactive = await client.get("/api/owner/me", headers=owner_headers(42))
    assert unknown.status_code == 403
    assert inactive.status_code == 403


async def test_entrance_role_cannot_manage_events(pg_factory, owner_env):
    await make_admin(pg_factory, role="entrance")
    async with client_for(pg_factory) as client:
        me = await client.get("/api/owner/me", headers=owner_headers(42))
        directions = await client.get("/api/owner/directions", headers=owner_headers(42))
    assert me.status_code == 200
    assert "manage_events" not in me.json()["permissions"]
    assert directions.status_code == 403


async def test_directions_lists_active_only(pg_factory, owner_env):
    await make_admin(pg_factory, role="administrator")
    async with pg_factory() as session, session.begin():
        repository = DirectionRepository(session)
        second = await repository.create("kino", "Кино", None, 2, True)
        first = await repository.create("igry", "Игры", None, 1, True)
        hidden = await repository.create("hidden", "Скрыто", None, 0, False)
    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/directions", headers=owner_headers(42))
        anonymous = await client.get("/api/owner/directions")
    assert response.status_code == 200
    listed = response.json()
    assert all(set(item) == {"id", "name"} for item in listed)  # migrations seed directions too
    ids = [item["id"] for item in listed]
    assert str(hidden.id) not in ids
    assert {"id": str(first.id), "name": "Игры"} in listed
    assert {"id": str(second.id), "name": "Кино"} in listed
    assert ids.index(str(first.id)) < ids.index(str(second.id))  # ordered by sort_order
    assert anonymous.status_code == 401


async def test_unconfigured_telegram_token_fails_closed(pg_factory, owner_env, monkeypatch):
    # An empty bot token would make initData signable by anyone; refuse to authenticate.
    monkeypatch.delenv("TELEGRAM_TOKEN")
    get_settings.cache_clear()
    await make_admin(pg_factory, role="owner")
    forged = {"Authorization": f"tma {sign_init_data(42, token='')}"}
    async with client_for(pg_factory) as client:
        response = await client.get("/api/owner/me", headers=forged)
    assert response.status_code == 503
