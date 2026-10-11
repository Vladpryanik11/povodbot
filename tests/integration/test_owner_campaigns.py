from datetime import timedelta
from io import BytesIO
from uuid import UUID

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from src.core.config import get_settings
from src.models.admin import AdminAuditLog
from src.models.base import utcnow
from src.models.campaigns import Campaign, CampaignClick, CampaignDelivery, CampaignStatus
from tests.campaign_fixtures import delivered, evening, guest
from tests.owner_fixtures import make_admin, owner_app, owner_headers
from tests.unit.services.test_events import draft, service

API = "/api/owner"
STALE = {"message": "Рассылку уже изменили в другой вкладке. Обнови страницу"}
LOCKED = {"message": "Эту рассылку уже не изменить"}
BUILTIN = {"message": "Готовый шаблон не меняется. Скопируй его в свои"}
EVERYONE = {"event": None, "directionId": None, "purchases": "any"}


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def client_for(factory):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app(factory)), base_url="http://test"
    )


async def call(client, method, path, **kwargs):
    return await client.request(method, f"{API}{path}", headers=owner_headers(), **kwargs)


async def stored(factory, status, **values) -> str:
    async with factory() as session, session.begin():
        campaign = Campaign(
            title=values.pop("title", f"Рассылка {status}"),
            body=values.pop("body", "Текст"),
            audience=values.pop("audience", EVERYONE),
            status=status,
            **values,
        )
        session.add(campaign)
        await session.flush()
        return str(campaign.id)


def png(size):
    buffer = BytesIO()
    Image.new("RGB", size, (40, 80, 200)).save(buffer, "PNG")
    return buffer.getvalue()


async def test_campaigns_need_manage_campaigns(pg_factory, owner_env):
    await make_admin(pg_factory, role="entrance")
    async with client_for(pg_factory) as client:
        response = await call(client, "GET", "/campaigns")
    assert response.status_code == 403


async def test_create_draft_from_scratch_and_patch(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        created = await call(client, "POST", "/campaigns", json={})
        assert created.status_code == 201, created.text
        campaign = created.json()
        path = f"/campaigns/{campaign['id']}"
        patched = await call(
            client,
            "PATCH",
            path,
            json={"body": "<b>Привет</b>", "updatedAt": campaign["updatedAt"]},
        )
        stale = await call(
            client, "PATCH", path, json={"title": "Другое", "updatedAt": campaign["updatedAt"]}
        )
        fetched = await call(client, "GET", path)
    assert campaign["title"] == "Новая рассылка"
    assert (campaign["body"], campaign["status"]) == ("", "draft")
    assert campaign["image"]["kind"] == "none"
    assert campaign["buttons"] == []
    assert campaign["audience"] == EVERYONE
    assert patched.status_code == 200, patched.text
    assert patched.json()["body"] == "<b>Привет</b>"
    assert (stale.status_code, stale.json()) == (409, STALE)
    assert fetched.json()["title"] == "Новая рассылка"


async def test_patch_rejects_bad_body_with_field(pg_factory, owner_env):
    await make_admin(pg_factory)
    sent = await stored(pg_factory, CampaignStatus.COMPLETED)
    async with client_for(pg_factory) as client:
        campaign = (await call(client, "POST", "/campaigns", json={})).json()
        path = f"/campaigns/{campaign['id']}"
        version = campaign["updatedAt"]
        bad_body = await call(
            client, "PATCH", path, json={"body": "<u>x</u>", "updatedAt": version}
        )
        http_button = await call(
            client,
            "PATCH",
            path,
            json={
                "buttons": [{"kind": "url", "label": "Сайт", "url": "http://x.ru"}],
                "updatedAt": version,
            },
        )
        foreign_image = await call(
            client,
            "PATCH",
            path,
            json={"image": {"kind": "upload", "ref": "../secret"}, "updatedAt": version},
        )
        current = (await call(client, "GET", f"/campaigns/{sent}")).json()
        locked = await call(
            client,
            "PATCH",
            f"/campaigns/{sent}",
            json={"title": "Ещё раз", "updatedAt": current["updatedAt"]},
        )
    assert bad_body.status_code == 422
    assert bad_body.json() == {"field": "body", "message": "Можно только жирный, курсив и ссылку"}
    assert http_button.status_code == 422
    assert http_button.json()["field"] == "buttons"
    assert (foreign_image.status_code, foreign_image.json()["field"]) == (422, "image")
    assert (locked.status_code, locked.json()) == (422, LOCKED)


async def test_event_must_be_published(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with pg_factory() as session, session.begin():
        hidden = str((await service(session).create_draft(draft())).id)
        shown = str(await evening(session))
    async with client_for(pg_factory) as client:
        rejected = await call(client, "POST", "/campaigns", json={"eventId": hidden})
        accepted = await call(
            client,
            "POST",
            "/campaigns",
            json={
                "eventId": shown,
                "image": {"kind": "event"},
                "buttons": [{"kind": "event", "label": "Открыть вечер"}],
            },
        )
    assert rejected.status_code == 422
    assert rejected.json() == {"field": "eventId", "message": "Вечер не опубликован"}
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["eventId"] == shown
    assert accepted.json()["image"]["kind"] == "event"


async def test_list_filters(pg_factory, owner_env):
    await make_admin(pg_factory)
    in_draft = await stored(pg_factory, CampaignStatus.DRAFT)
    later = await stored(
        pg_factory, CampaignStatus.SCHEDULED, scheduled_at=utcnow() + timedelta(days=1)
    )
    done = await stored(pg_factory, CampaignStatus.COMPLETED, started_at=utcnow())
    async with pg_factory() as session, session.begin():
        reader = await guest(session, 11)
        session.add(
            CampaignDelivery(
                campaign_id=UUID(done),
                user_id=reader.id,
                telegram_id=reader.telegram_id,
                idempotency_key=f"campaign:{done}:user:{reader.id}",
                status="sent",
                attempts=1,
                sent_at=utcnow(),
            )
        )
        session.add(CampaignClick(campaign_id=UUID(done), user_id=reader.id, button_index=0))
        session.add(CampaignClick(campaign_id=UUID(done), user_id=reader.id, button_index=1))
    async with client_for(pg_factory) as client:
        lists = {
            which: (await call(client, "GET", f"/campaigns?filter={which}")).json()
            for which in ("draft", "scheduled", "sent")
        }
    assert [item["id"] for item in lists["draft"]] == [in_draft]
    assert [item["id"] for item in lists["scheduled"]] == [later]
    assert [item["id"] for item in lists["sent"]] == [done]
    assert (lists["sent"][0]["delivered"], lists["sent"][0]["clicked"]) == (1, 1)


async def test_duplicate_makes_draft_copy(pg_factory, owner_env):
    await make_admin(pg_factory)
    buttons = [{"kind": "url", "label": "Сайт", "url": "https://povod.club"}]
    original = await stored(
        pg_factory,
        CampaignStatus.COMPLETED,
        title="Летняя",
        image={"kind": "upload", "ref": "campaigns/abc"},
        buttons=buttons,
        audience={"event": None, "directionId": None, "purchases": "never"},
        telegram_photo_id="photo-1",
        started_at=utcnow(),
    )
    async with client_for(pg_factory) as client:
        response = await call(client, "POST", f"/campaigns/{original}/duplicate")
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != original
    assert (copy["title"], copy["status"], copy["body"]) == ("Летняя (копия)", "draft", "Текст")
    assert copy["image"]["ref"] == "campaigns/abc"
    assert copy["buttons"] == buttons
    assert copy["audience"]["purchases"] == "never"
    assert copy["startedAt"] is None
    async with pg_factory() as session:
        clone = await session.get(Campaign, UUID(copy["id"]))
        source = await session.get(Campaign, UUID(original))
    assert clone.short_code != source.short_code
    assert clone.telegram_photo_id is None


async def test_builtin_template_is_read_only(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        templates = (await call(client, "GET", "/campaign-templates")).json()
        builtin = templates[0]["id"]
        edit_builtin = await call(
            client, "PATCH", f"/campaign-templates/{builtin}", json={"name": "Моё"}
        )
        delete_builtin = await call(client, "DELETE", f"/campaign-templates/{builtin}")
        own = await call(
            client,
            "POST",
            "/campaign-templates",
            json={"name": "Мой", "body": "<i>Привет</i>", "imageKind": "none", "buttons": []},
        )
        renamed = await call(
            client, "PATCH", f"/campaign-templates/{own.json()['id']}", json={"name": "Мой 2"}
        )
        removed = await call(client, "DELETE", f"/campaign-templates/{own.json()['id']}")
        buttons = [{"kind": "url", "label": "Сайт", "url": "https://povod.club"}]
        campaign = (
            await call(
                client, "POST", "/campaigns", json={"body": "<b>Текст</b>", "buttons": buttons}
            )
        ).json()
        saved = await call(
            client,
            "POST",
            f"/campaigns/{campaign['id']}/save-as-template",
            json={"name": "Из рассылки"},
        )
        after = (await call(client, "GET", "/campaign-templates")).json()
    assert [t["isBuiltin"] for t in templates] == [True] * 5
    assert (edit_builtin.status_code, edit_builtin.json()) == (403, BUILTIN)
    assert (delete_builtin.status_code, delete_builtin.json()) == (403, BUILTIN)
    assert own.status_code == 201, own.text
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Мой 2")
    assert removed.status_code == 204
    assert saved.status_code == 201, saved.text
    assert (saved.json()["body"], saved.json()["imageKind"]) == ("<b>Текст</b>", "none")
    assert saved.json()["buttons"] == buttons
    assert [t["name"] for t in after][5:] == ["Из рассылки"]
    async with pg_factory() as session:
        actions = set(await session.scalars(select(AdminAuditLog.action)))
    assert {
        "owner.campaign.create",
        "owner.template.create",
        "owner.template.update",
        "owner.template.delete",
        "owner.template.from_campaign",
    } <= actions


async def test_audience_count(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with pg_factory() as session, session.begin():
        busy = await guest(session, 1)
        await guest(session, 2)
        await guest(session, 3, blocked=True)
        for _ in range(2):
            await delivered(session, busy, utcnow() - timedelta(days=1))
    async with client_for(pg_factory) as client:
        everyone = await call(client, "POST", "/campaigns/audience-count", json={})
        bought = await call(
            client, "POST", "/campaigns/audience-count", json={"purchases": "bought"}
        )
        unknown = await call(client, "POST", "/campaigns/audience-count", json={"segment": "x"})
    assert everyone.json() == {"count": 1, "overLimit": 1}
    assert bought.json() == {"count": 0, "overLimit": 0}
    assert unknown.status_code == 422


async def test_upload_campaign_image(pg_factory, owner_env, media_root):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        campaign = (await call(client, "POST", "/campaigns", json={})).json()
        path = f"/campaigns/{campaign['id']}/image"
        small = await call(client, "POST", path, files={"file": ("a.png", png((300, 300)))})
        uploaded = await call(client, "POST", path, files={"file": ("a.png", png((400, 400)))})
        cleared = await call(client, "DELETE", path)
    assert small.status_code == 422
    assert small.json() == {"field": "image", "message": "Фото маловато — нужно хотя бы 320×320"}
    assert uploaded.status_code == 200, uploaded.text
    image = uploaded.json()["image"]
    assert image["kind"] == "upload"
    assert image["ref"].startswith("campaigns/")
    assert image["url"] == f"/media/{image['ref']}-1080.webp"
    assert list((media_root / "campaigns").glob("*-1080.webp"))
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["image"] == {"kind": "none", "ref": None, "url": None}
