from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.admin.dependencies import require_permission
from src.services.admin.permissions import AdminActor, Permission

router = APIRouter(prefix="/api/admin/payments", tags=["admin payments"])


async def require_payment_admin(
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_ORDERS))],
) -> AdminActor:
    return actor


@router.get("/{payment_id}")
async def get_payment(
    payment_id: str,
    actor: Annotated[AdminActor, Depends(require_payment_admin)],
) -> None:
    del payment_id
    del actor
