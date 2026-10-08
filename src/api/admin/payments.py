from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/admin/payments", tags=["admin payments"])


async def require_payment_admin() -> None:
    """Fail closed until Task 7 composes authenticated admin permissions."""
    raise HTTPException(403, "Payment administration requires authorization")


@router.get("/{payment_id}")
async def get_payment(payment_id: str) -> None:
    del payment_id
    await require_payment_admin()
