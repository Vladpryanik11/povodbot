from datetime import UTC, datetime, timedelta

import pytest

from src.bot.handlers.events import EventHandler
from src.models.events import EventStatus
from src.repositories.directions import DirectionRepository
from src.services.directions.service import DirectionService
from src.services.events.service import (
    EventConflict,
    EventFieldError,
    UpdateEventCommand,
)
from src.services.reservations.service import ReservationItem
from tests.commerce_fixtures import NOW, catalog, reservations
from tests.unit.services.test_events import draft, service


async def test_draft_without_address_publishes(db_session):
    events = service(db_session)
    created = await events.create_draft(draft(address=None))
    assert created.address is None
    published = await events.publish(created.id)
    assert published.status == EventStatus.PUBLISHED
    assert published.address is None
    assert (await events.get_public(created.id)).address is None


async def test_blank_address_is_rejected_but_none_is_not(db_session):
    with pytest.raises(EventFieldError) as info:
        await service(db_session).create_draft(draft(address="  "))
    assert info.value.field == "address"
    assert info.value.message == "Укажи адрес или выбери «Место уточняется»"


async def test_publish_requires_poster(db_session):
    events = service(db_session)
    created = await events.create_draft(draft(cover_ref=None))
    with pytest.raises(EventFieldError) as info:
        await events.publish(created.id)
    assert info.value.field == "poster"
    assert info.value.message == "Без фото опубликовать нельзя"


async def test_publish_past_start_names_the_date_field(db_session):
    events = service(db_session)
    start = datetime.now(UTC) - timedelta(hours=3)
    started = await events.create_draft(draft(starts_at=start, ends_at=start + timedelta(hours=2)))
    with pytest.raises(EventFieldError) as info:
        await events.publish(started.id)
    assert info.value.field == "starts_at"
    assert info.value.message == "Вечер уже начался — поменяй дату"
    assert isinstance(info.value, ValueError)


async def test_field_error_names_field(db_session):
    with pytest.raises(EventFieldError) as info:
        await service(db_session).create_draft(draft(title=" "))
    assert info.value.field == "title"
    assert info.value.message == "Назови вечер"
    assert isinstance(info.value, ValueError)


async def test_unpublish_without_orders(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    published = await events.publish(created.id)
    assert published.published_at is not None
    assert published.updated_at > created.updated_at
    result = await events.unpublish(created.id)
    assert result.status == EventStatus.DRAFT
    assert result.published_at is None
    assert result.updated_at > published.updated_at
    assert await events.list_public(None, None) == []


async def test_unpublish_only_published_events(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    with pytest.raises(ValueError):
        await events.unpublish(created.id)


async def test_unpublish_blocked_by_any_order(db_session):
    event, user = await catalog(db_session, 1)
    cart = [ReservationItem(event.ticket_types[0].id, 1)]
    await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    # The reservation lapses: the order is expired, yet a late payment may still arrive for it.
    released = await reservations(db_session).release_expired(NOW + timedelta(seconds=600), 10)
    assert released == 1
    with pytest.raises(EventConflict) as info:
        await service(db_session).unpublish(event.id)
    assert info.value.message == "Уже есть брони — отменить можно будет через возвраты"
    assert (await service(db_session).get_public(event.id)).id == event.id


async def test_update_version_conflict(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    with pytest.raises(EventConflict) as info:
        await events.update(
            created.id,
            UpdateEventCommand(title="Чужая правка"),
            expected_updated_at=created.updated_at - timedelta(seconds=1),
        )
    assert info.value.message == "Событие уже изменили — обнови"
    unchanged = await events.update(created.id, UpdateEventCommand())
    assert unchanged.title == created.title
    updated = await events.update(
        created.id,
        UpdateEventCommand(title="Новое название"),
        expected_updated_at=unchanged.updated_at,
    )
    assert updated.title == "Новое название"
    assert updated.updated_at > unchanged.updated_at


async def test_set_poster_and_focus(db_session):
    events = service(db_session)
    created = await events.create_draft(draft(cover_ref=None))
    with_poster = await events.set_poster(created.id, "posters/abc", 1080, 1350, 0.3, 0.7)
    assert with_poster.cover_ref == "posters/abc"
    assert (with_poster.cover_width, with_poster.cover_height) == (1080, 1350)
    assert (with_poster.cover_focus_x, with_poster.cover_focus_y) == (0.3, 0.7)
    assert with_poster.updated_at > created.updated_at
    moved = await events.set_poster_focus(created.id, 0, 1)
    assert (moved.cover_focus_x, moved.cover_focus_y) == (0, 1)
    assert moved.cover_ref == "posters/abc"
    for x, y in [(1.2, 0.5), (0.5, -0.1), (float("nan"), 0.5), (True, 0.5)]:
        with pytest.raises(EventFieldError) as info:
            await events.set_poster_focus(created.id, x, y)
        assert info.value.field == "focus"
        assert info.value.message == "Точка фокуса вне фото"
    with pytest.raises(EventFieldError) as info:
        await events.set_poster(created.id, "posters/other", 100, 100, 3, 0.5)
    assert info.value.field == "focus"
    assert (await events.publish(created.id)).cover_ref == "posters/abc"
    published_focus = await events.set_poster_focus(created.id, 0.1, 0.2)
    assert published_focus.status == EventStatus.PUBLISHED
    assert published_focus.cover_focus_x == 0.1


async def test_poster_not_settable_on_terminal_event(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    await events.publish(created.id)
    await events.update(created.id, UpdateEventCommand(status=EventStatus.CANCELLED))
    with pytest.raises(ValueError):
        await events.set_poster(created.id, "posters/new", 100, 100, 0.5, 0.5)
    with pytest.raises(ValueError):
        await events.set_poster_focus(created.id, 0.5, 0.5)


async def test_accent_color_validated_and_clearable(db_session):
    events = service(db_session)
    created = await events.create_draft(draft(accent_color="#FF8800"))
    assert created.accent_color == "#FF8800"
    with pytest.raises(EventFieldError) as info:
        await events.update(created.id, UpdateEventCommand(accent_color="orange"))
    assert info.value.field == "accent_color"
    assert info.value.message == "Цвет в формате #RRGGBB"
    with pytest.raises(EventFieldError):
        await events.create_draft(draft(accent_color="#FF880"))
    recolored = await events.update(created.id, UpdateEventCommand(accent_color="#00aa11"))
    assert recolored.accent_color == "#00aa11"
    cleared = await events.update(created.id, UpdateEventCommand(clear_fields={"accent_color"}))
    assert cleared.accent_color is None


async def test_address_clearable_on_update(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    cleared = await events.update(created.id, UpdateEventCommand(clear_fields={"address"}))
    assert cleared.address is None
    with pytest.raises(ValueError):
        await events.update(created.id, UpdateEventCommand(clear_fields={"title"}))


async def test_published_event_keeps_its_poster(db_session):
    events = service(db_session)
    created = await events.create_draft(draft())
    await events.publish(created.id)
    with pytest.raises(EventFieldError) as info:
        await events.update(created.id, UpdateEventCommand(clear_fields={"cover_ref"}))
    assert info.value.field == "poster"


async def test_ticket_and_capacity_messages(db_session):
    from src.services.events.service import TicketTypeCommand

    events = service(db_session)
    cases = [
        (draft(capacity=0), "capacity", "Сколько мест?"),
        (draft(map_url="javascript:bad"), "map_url", "Ссылка на карту не открывается"),
        (draft(description=" "), "description", "Добавь пару слов о вечере"),
        (draft(ends_at=draft().starts_at - timedelta(hours=1)), "ends_at", None),
        (
            draft(ticket_types=[TicketTypeCommand("  ", 100, 10)]),
            "ticket_types",
            "У билета нет названия",
        ),
        (
            draft(ticket_types=[TicketTypeCommand("Ок", -1, 10)]),
            "ticket_types",
            "Проверь цену билета",
        ),
        (
            draft(ticket_types=[TicketTypeCommand("Ок", 100, 0)]),
            "ticket_types",
            "Проверь количество билетов",
        ),
    ]
    for command, field, message in cases:
        with pytest.raises(EventFieldError) as info:
            await events.create_draft(command)
        assert info.value.field == field
        assert message is None or info.value.message == message
    created = await events.create_draft(draft(ticket_types=[]))
    with pytest.raises(EventFieldError) as info:
        await events.publish(created.id)
    assert (info.value.field, info.value.message) == ("ticket_types", "Добавь хотя бы один билет")


async def test_occupied_seats_messages(db_session):
    from src.services.events.service import TicketTypeCommand

    events = service(db_session)
    event, user = await catalog(db_session, 2)
    ticket = event.ticket_types[0]
    cart = [ReservationItem(ticket.id, 2)]
    await reservations(db_session).reserve(event.id, cart, user.id, NOW)
    lowered = TicketTypeCommand(ticket.name, ticket.price_kopecks, 1, id=ticket.id)
    with pytest.raises(EventFieldError) as info:
        await events.update(event.id, UpdateEventCommand(capacity=1, ticket_types=[lowered]))
    assert (info.value.field, info.value.message) == ("capacity", "Уже занято больше мест")
    with pytest.raises(EventFieldError) as info:
        await events.update(event.id, UpdateEventCommand(ticket_types=[lowered]))
    assert (info.value.field, info.value.message) == (
        "ticket_types",
        "Уже продано больше билетов этого типа",
    )


async def test_bot_card_without_address_says_place_is_tbd(db_session):
    events = service(db_session)
    handler = EventHandler(events, DirectionService(DirectionRepository(db_session)))
    unknown = await events.create_draft(draft(address=None))
    known = await events.create_draft(draft(address="Клуб Повод"))
    await events.publish(unknown.id)
    await events.publish(known.id)
    assert "Место уточняется" in (await handler.read(f"event:{unknown.id}")).text
    card = (await handler.read(f"event:{known.id}")).text
    assert "Клуб Повод" in card
    assert "Место уточняется" not in card
    assert "None" not in card
