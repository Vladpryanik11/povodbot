import asyncio
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from src.api.owner import posters
from src.core.config import get_settings
from src.models.admin import AdminAuditLog
from src.models.base import utcnow
from src.models.events import Event, EventStatus
from src.repositories.events import EventRepository
from src.services.events.service import EventService
from src.services.media.posters import MAX_BYTES
from tests.integration.test_owner_events import POSTER_KEY, add_poster, client_for, create_event
from tests.owner_fixtures import make_admin, owner_headers

NOT_A_PHOTO = {"field": "poster", "message": "Это не фото — подойдут JPEG, PNG, WebP или HEIC"}
TEXT = b"just some text, not a picture"
BUSY = {"message": "Фото ещё загружается — подожди"}


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def jpeg(size):
    buffer = BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buffer, "JPEG")
    return buffer.getvalue()


async def upload(client, event_id, content, focus=("0.3", "0.7"), name="poster.jpg"):
    return await client.post(
        f"/api/owner/events/{event_id}/poster",
        files={"file": (name, content, "application/octet-stream")},
        data={"focus_x": focus[0], "focus_y": focus[1]},
        headers=owner_headers(42),
    )


async def fetch(client, event_id):
    response = await client.get(f"/api/owner/events/{event_id}", headers=owner_headers(42))
    assert response.status_code == 200, response.text
    return response.json()


async def test_upload_sets_poster(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        response = await upload(client, created["id"], jpeg((1200, 1500)))
        published = await client.post(
            f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42)
        )
    assert response.status_code == 200, response.text
    poster = response.json()["poster"]
    assert poster["url"].startswith("/media/posters/")
    assert poster["url"].endswith("-1080.webp")
    assert (media_root / poster["url"].removeprefix("/media/")).is_file()
    assert (poster["focusX"], poster["focusY"]) == (0.3, 0.7)
    assert (poster["width"], poster["height"]) == (1080, 1350)
    assert response.json()["id"] == created["id"]
    assert published.status_code == 200, published.text
    assert published.json()["poster"] == poster


async def test_rejected_upload_keeps_poster(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        await add_poster(pg_factory, created["id"])
        before = await fetch(client, created["id"])
        response = await upload(client, created["id"], TEXT)
        after = await fetch(client, created["id"])
    assert response.status_code == 415
    assert response.json() == NOT_A_PHOTO
    assert after["poster"] == before["poster"]
    assert after["poster"]["url"] == f"/media/{POSTER_KEY}-1080.webp"
    assert after["updatedAt"] == before["updatedAt"]
    assert not (media_root / "posters").exists()


async def test_upload_rejects_non_photo(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        response = await upload(client, created["id"], TEXT)
    assert response.status_code == 415
    assert response.json() == NOT_A_PHOTO


async def test_upload_rejects_oversize(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    big = b"\xff\xd8\xff" + bytes(MAX_BYTES)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        response = await upload(client, created["id"], big)
    assert response.status_code == 413
    assert response.json() == {"field": "poster", "message": "Фото больше 15 МБ"}
    assert not (media_root / "posters").exists()


async def test_upload_bad_focus_stores_nothing(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        response = await upload(client, created["id"], jpeg((1200, 1500)), focus=("2", "0.5"))
        after = await fetch(client, created["id"])
    assert response.status_code == 422
    assert response.json() == {"field": "focus", "message": "Точка фокуса вне фото"}
    assert after["poster"] is None
    assert not (media_root / "posters").exists()


async def test_upload_unknown_event(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        response = await upload(client, UUID(int=999), jpeg((1200, 1500)))
    assert response.status_code == 404
    assert response.json() == {"message": "Вечер не найден"}
    assert not (media_root / "posters").exists()


async def test_focus_only(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        await add_poster(pg_factory, created["id"])
        url = f"/api/owner/events/{created['id']}/poster-focus"
        moved = await client.patch(
            url, json={"focusX": 0.1, "focusY": 0.9}, headers=owner_headers(42)
        )
        outside = await client.patch(
            url, json={"focusX": 2, "focusY": 0.5}, headers=owner_headers(42)
        )
        after = await fetch(client, created["id"])
    assert moved.status_code == 200, moved.text
    assert (moved.json()["poster"]["focusX"], moved.json()["poster"]["focusY"]) == (0.1, 0.9)
    assert moved.json()["poster"]["url"] == f"/media/{POSTER_KEY}-1080.webp"
    assert outside.status_code == 422
    assert outside.json() == {"field": "focus", "message": "Точка фокуса вне фото"}
    assert (after["poster"]["focusX"], after["poster"]["focusY"]) == (0.1, 0.9)


async def test_focus_body_is_strict(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        url = f"/api/owner/events/{created['id']}/poster-focus"
        extra = await client.patch(
            url, json={"focusX": 0.1, "focusY": 0.9, "url": "x"}, headers=owner_headers(42)
        )
        text = await client.patch(
            url, json={"focusX": "0.1", "focusY": 0.9}, headers=owner_headers(42)
        )
        flag = await client.patch(
            url, json={"focusX": True, "focusY": 0.9}, headers=owner_headers(42)
        )
    assert extra.status_code == 422
    assert text.status_code == 422
    assert flag.status_code == 422


async def test_focus_unknown_event(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        response = await client.patch(
            f"/api/owner/events/{UUID(int=999)}/poster-focus",
            json={"focusX": 0.1, "focusY": 0.9},
            headers=owner_headers(42),
        )
    assert response.status_code == 404
    assert response.json() == {"message": "Вечер не найден"}


async def test_parallel_upload_429(pg_factory, owner_env, media_root, monkeypatch):
    admin_id = await make_admin(pg_factory)
    lock = asyncio.Lock()
    monkeypatch.setattr(posters, "_upload_locks", {admin_id: lock})
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        async with lock:
            # Without the 429 the handler would wait for this very lock: fail, don't hang.
            async with asyncio.timeout(10):
                busy = await upload(client, created["id"], jpeg((1200, 1500)))
        free = await upload(client, created["id"], jpeg((1200, 1500)))
    assert busy.status_code == 429
    assert busy.json() == BUSY
    assert not lock.locked()
    assert free.status_code == 200, free.text


async def test_failed_upload_releases_lock(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        rejected = await upload(client, created["id"], TEXT)
        accepted = await upload(client, created["id"], jpeg((1200, 1500)))
    assert rejected.status_code == 415
    assert accepted.status_code == 200, accepted.text


async def test_poster_audit(pg_factory, owner_env, media_root):
    admin_id = await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        uploaded = await upload(client, created["id"], jpeg((1200, 1500)))
        await upload(client, created["id"], TEXT)
        moved = await client.patch(
            f"/api/owner/events/{created['id']}/poster-focus",
            json={"focusX": 0.2, "focusY": 0.4},
            headers=owner_headers(42),
        )
        await client.patch(
            f"/api/owner/events/{created['id']}/poster-focus",
            json={"focusX": 5, "focusY": 0.4},
            headers=owner_headers(42),
        )
    key = uploaded.json()["poster"]["url"].removeprefix("/media/").removesuffix("-1080.webp")
    assert moved.status_code == 200
    async with pg_factory() as session:
        rows = list(await session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at)))
    assert [row.action for row in rows] == [
        "owner.event.create",
        "owner.event.poster",
        "owner.event.poster_focus",
    ]
    assert all(row.actor_id == admin_id for row in rows)
    assert all(str(row.object_id) == created["id"] for row in rows)
    assert rows[1].details == {"key": key}


async def test_poster_routes_need_events_permission(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    await make_admin(pg_factory, role="entrance", telegram_id=43)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        anonymous = await client.post(
            f"/api/owner/events/{created['id']}/poster",
            files={"file": ("a.jpg", jpeg((1200, 1500)), "image/jpeg")},
            data={"focus_x": "0.5", "focus_y": "0.5"},
        )
        forbidden = await client.patch(
            f"/api/owner/events/{created['id']}/poster-focus",
            json={"focusX": 0.5, "focusY": 0.5},
            headers=owner_headers(43),
        )
    assert anonymous.status_code == 401
    assert forbidden.status_code == 403


async def test_upload_replaces_poster_of_published_event(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        first = await upload(client, created["id"], jpeg((1200, 1500)))
        await client.post(f"/api/owner/events/{created['id']}/publish", headers=owner_headers(42))
        second = await upload(
            client, created["id"], jpeg((1000, 1250)), focus=("0.5", "0.5"), name="other.jpg"
        )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "published"
    assert second.json()["poster"]["url"] != first.json()["poster"]["url"]
    async with pg_factory() as session:
        event = await EventService(EventRepository(session)).get(UUID(created["id"]))
    assert event.cover_ref == second.json()["poster"]["url"].removeprefix("/media/").removesuffix(
        "-1080.webp"
    )


async def test_oversized_content_length_is_413_before_auth(pg_factory, owner_env, media_root):
    # FastAPI reads the whole multipart body before the auth dependency runs; the declared
    # length is the only thing to go on before that.
    async with client_for(pg_factory) as client:
        response = await client.post(
            f"/api/owner/events/{uuid4()}/poster",
            files={"file": ("a.jpg", b"tiny", "image/jpeg")},
            data={"focus_x": "0.5", "focus_y": "0.5"},
            headers={"Content-Length": "20000000"},
        )
    assert response.status_code == 413
    assert response.json() == {"message": "Файл больше 15 МБ"}
    assert not (media_root / "posters").exists()


@pytest.mark.parametrize("status", [EventStatus.CANCELLED, EventStatus.COMPLETED])
async def test_upload_to_finished_event_stores_nothing(pg_factory, owner_env, media_root, status):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await create_event(client)
        await add_poster(pg_factory, created["id"])
        before = await fetch(client, created["id"])
        async with pg_factory() as session, session.begin():
            event = await session.get(Event, UUID(created["id"]))
            event.status = status
            event.published_at = utcnow()
        response = await upload(client, created["id"], jpeg((1200, 1500)))
        after = await fetch(client, created["id"])
    assert response.status_code == 422
    assert response.json() == {"message": "Так изменить вечер нельзя"}
    assert not (media_root / "posters").exists()  # refused before the photo was decoded or kept
    assert after["poster"] == before["poster"]
