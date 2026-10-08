from datetime import UTC, datetime

from src.models.admin import AdminRole
from src.repositories.admin import AdminRepository
from src.services.admin.auth import AdminAuthService


async def test_admin_session_is_hashed_expiring_and_revocable(db_session):
    service = AdminAuthService(AdminRepository(db_session))
    user = await service.create_user("Owner", "a-long-test-password", AdminRole.OWNER)
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    result = await service.authenticate("owner", "a-long-test-password", now)
    assert result is not None
    assert result.actor.id == user.id
    assert result.token not in user.password_hash
    assert await service.actor_for_token(result.token, now) == result.actor
    user.is_active = False
    assert await service.actor_for_token(result.token, now) is None
    user.is_active = True
    await service.logout(result.token, now)
    assert await service.actor_for_token(result.token, now) is None
