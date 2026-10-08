from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.dependencies import require_permission
from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.payments import Payment
from src.repositories.admin import AdminRepository
from src.repositories.payments import PaymentRepository
from src.services.admin.permissions import AdminActor, Permission
from src.services.audit.service import AuditService
from src.services.payments.service import PaymentService
from src.services.payments.tbank_client import TBankPaymentGateway

router = APIRouter(prefix="/api/admin/payments", tags=["admin payments"])


async def require_payment_admin(
    actor: Annotated[AdminActor, Depends(require_permission(Permission.MANAGE_ORDERS))],
) -> AdminActor:
    return actor


class RefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


def _gateway() -> TBankPaymentGateway:
    settings = get_settings()
    return TBankPaymentGateway(
        settings.tbank_terminal_key,
        settings.tbank_password,
        api_token=settings.tbank_api_token,
        base_url=settings.tbank_api_base_url,
    )


async def _payment_or_404(session: AsyncSession, payment_id: UUID) -> Payment:
    payment = await session.scalar(select(Payment).where(Payment.id == payment_id))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.get("/{payment_id}")
async def get_payment(
    payment_id: UUID,
    actor: Annotated[AdminActor, Depends(require_payment_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    del actor
    payment = await _payment_or_404(session, payment_id)
    return {
        "id": str(payment.id),
        "order_id": str(payment.order_id),
        "provider_payment_id": payment.provider_payment_id,
        "status": payment.status,
        "provider_status": payment.provider_status,
        "amount_kopecks": payment.amount_kopecks,
        "payment_url": payment.payment_url,
        "paid_at": payment.paid_at,
        "refunded_at": payment.refunded_at,
    }


@router.post("/{payment_id}/reconcile")
async def reconcile_payment(
    payment_id: UUID,
    actor: Annotated[AdminActor, Depends(require_payment_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> object:
    await _payment_or_404(session, payment_id)
    gateway = _gateway()
    try:
        result = await PaymentService(PaymentRepository(session), gateway).reconcile(payment_id)
        await AuditService(AdminRepository(session)).record(
            actor.id, "payment.reconcile", "payment", payment_id
        )
        return result
    finally:
        await gateway.aclose()


@router.post("/{payment_id}/refund")
async def refund_payment(
    payment_id: UUID,
    payload: RefundInput,
    actor: Annotated[AdminActor, Depends(require_permission(Permission.REFUND_ORDERS))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> object:
    await _payment_or_404(session, payment_id)
    gateway = _gateway()
    try:
        result = await PaymentService(PaymentRepository(session), gateway).request_refund(
            payment_id, payload.reason
        )
        await AuditService(AdminRepository(session)).record(
            actor.id, "payment.refund", "payment", payment_id
        )
        return result
    finally:
        await gateway.aclose()
