from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.admin import AdminAuditLog, AdminSession, AdminUser


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def user_by_login(self, login: str) -> AdminUser | None:
        value = await self.session.scalar(
            select(AdminUser).where(AdminUser.login == login).with_for_update()
        )
        return value

    async def user_by_id(self, admin_id: UUID) -> AdminUser | None:
        result = await self.session.execute(select(AdminUser).where(AdminUser.id == admin_id))
        return result.scalar_one_or_none()

    async def session_by_hash(self, token_hash: str, now: datetime) -> AdminSession | None:
        result = await self.session.execute(
            select(AdminSession)
            .options(joinedload(AdminSession.admin))
            .join(AdminSession.admin)
            .where(
                AdminSession.token_hash == token_hash,
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > now,
                AdminUser.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def add_session(
        self, admin_id: UUID, token_hash: str, expires_at: datetime
    ) -> AdminSession:
        value = AdminSession(admin_id=admin_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(value)
        await self.session.flush()
        return value

    async def revoke_session(self, token_hash: str, now: datetime) -> None:
        session = await self.session.scalar(
            select(AdminSession).where(AdminSession.token_hash == token_hash).with_for_update()
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = now
            await self.session.flush()

    async def audit(
        self,
        actor_id: UUID | None,
        action: str,
        object_type: str,
        object_id: UUID | None = None,
        details: dict[str, object] | None = None,
        *,
        success: bool = True,
    ) -> AdminAuditLog:
        # Callers pass already-redacted bounded metadata; keep the stored shape small.
        blocked = (
            "token",
            "password",
            "secret",
            "credential",
            "payload",
            "pan",
            "api_key",
            "apikey",
            "authorization",
            "cookie",
            "cardid",
            "expdate",
            "rebillid",
            "cvv",
            "cvc",
        )
        safe_details = {
            str(key)[:64]: value
            for key, value in (details or {}).items()
            if not any(part in str(key).lower() for part in blocked)
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }
        record = AdminAuditLog(
            actor_id=actor_id,
            action=action[:128],
            object_type=object_type[:64],
            object_id=object_id,
            details=safe_details,
            success=success,
        )
        self.session.add(record)
        await self.session.flush()
        return record


def utc_now() -> datetime:
    return datetime.now(UTC)
