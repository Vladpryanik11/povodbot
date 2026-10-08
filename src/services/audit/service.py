from uuid import UUID

from src.models.admin import AdminAuditLog
from src.repositories.admin import AdminRepository


class AuditService:
    def __init__(self, repository: AdminRepository):
        self.repository = repository

    async def record(
        self,
        actor_id: UUID | None,
        action: str,
        object_type: str,
        object_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
        *,
        success: bool = True,
    ) -> AdminAuditLog:
        return await self.repository.audit(
            actor_id, action, object_type, object_id, metadata, success=success
        )
