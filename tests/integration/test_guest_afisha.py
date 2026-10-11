from uuid import UUID

from tests.integration.test_owner_events import add_poster, client_for, create_event
from tests.owner_fixtures import make_admin, owner_headers


async def test_published_evening_reaches_the_guest_afisha(pg_factory, owner_env):
    await make_admin(pg_factory)
    async with client_for(pg_factory) as client:
        draft = await create_event(client, title="Черновик")
        published = await create_event(client, title="Кино вечером", accentColor="#AA3311")
        await add_poster(pg_factory, published["id"])
        response = await client.post(
            f"/api/owner/events/{published['id']}/publish", headers=owner_headers(42)
        )
        assert response.status_code == 200, response.text

        directions = (await client.get("/api/app/directions")).json()
        cards = (await client.get("/api/app/events")).json()
        cinema = (await client.get(f"/api/app/events?direction_id={UUID(int=1)}")).json()
        books = (await client.get(f"/api/app/events?direction_id={UUID(int=2)}")).json()
        detail = (await client.get(f"/api/app/events/{published['id']}")).json()
        hidden = await client.get(f"/api/app/events/{draft['id']}")

    assert {"id": str(UUID(int=1)), "title": "Кино", "icon": "film"} in directions
    assert [card["id"] for card in cards] == [published["id"]]
    assert [card["id"] for card in cinema] == [published["id"]]
    assert books == []
    card = cards[0]
    assert card["minPriceKopecks"] == 15000
    assert card["seatsLeft"] == 20
    assert card["soldOut"] is False
    assert card["accentColor"] == "#AA3311"
    assert card["poster"]["url"].endswith("-1080.webp")
    assert card["attendees"] == {"count": 0, "avatars": []}
    assert detail["description"] == "Обсуждение фильма"
    assert [(t["name"], t["priceKopecks"], t["seatsLeft"]) for t in detail["ticketTypes"]] == [
        ("Обычный", 15000, 20)
    ]
    assert detail["poll"] is None
    assert hidden.status_code == 404
