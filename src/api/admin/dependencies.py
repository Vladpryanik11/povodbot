from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException

from src.api.admin.auth import get_current_admin
from src.services.admin.permissions import AdminActor, Permission, PermissionService


def require_permission(permission: Permission) -> Callable[..., Awaitable[AdminActor]]:
    async def dependency(
        actor: Annotated[AdminActor, Depends(get_current_admin)],
    ) -> AdminActor:
        try:
            PermissionService.require(actor, permission)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Insufficient admin permissions") from exc
        return actor

    return dependency
