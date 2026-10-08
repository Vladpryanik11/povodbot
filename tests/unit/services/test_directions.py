import pytest
from sqlalchemy.exc import IntegrityError

from src.repositories.directions import DirectionRepository
from src.services.directions.service import CreateDirectionCommand, DirectionService


async def test_active_directions_have_stable_order_and_can_be_disabled(db_session):
    service = DirectionService(DirectionRepository(db_session))
    for seeded in await service.list_active():
        await service.set_active(seeded.id, False)
    a = await service.create(CreateDirectionCommand(slug="alpha", name="Alpha", sort_order=2))
    b = await service.create(CreateDirectionCommand(slug="beta", name="Beta", sort_order=1))
    await service.create(CreateDirectionCommand(slug="hidden", name="Hidden", active=False))
    c = await service.create(CreateDirectionCommand(slug="charlie", name="Charlie", sort_order=2))
    assert [d.id for d in await service.list_active()] == [b.id, a.id, c.id]
    changed = await service.set_active(a.id, False)
    assert not changed.active
    assert changed.updated_at.tzinfo is not None
    assert [d.slug for d in await service.list_active()] == ["beta", "charlie"]


async def test_direction_slug_is_database_unique(db_session):
    service = DirectionService(DirectionRepository(db_session))
    await service.create(CreateDirectionCommand(slug="new-direction", name="Кино"))
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await service.create(CreateDirectionCommand(slug="new-direction", name="Дубликат"))


@pytest.mark.parametrize("slug,name", [("", "Кино"), ("Bad Slug", "Кино"), ("ok", " ")])
async def test_invalid_direction_rejected(db_session, slug, name):
    with pytest.raises(ValueError):
        await DirectionService(DirectionRepository(db_session)).create(
            CreateDirectionCommand(slug=slug, name=name)
        )
