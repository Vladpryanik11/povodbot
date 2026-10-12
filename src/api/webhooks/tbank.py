from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_async_session
from src.repositories.payments import PaymentRepository
from src.services.payments.dtos import PaymentWebhookDTO
from src.services.payments.service import PaymentService
from src.services.payments.tbank_client import TBankPaymentGateway

router = APIRouter(prefix="/api/webhooks/tbank", tags=["tbank webhooks"])


@router.post("/payment-status", response_class=PlainTextResponse)
async def payment_status(
    request: Request,
    # scope="function": commit before the response, so OK always means the payment is stored.
    session: Annotated[AsyncSession, Depends(get_async_session, scope="function")],
) -> PlainTextResponse:
    # T-Bank signs notifications only with the body Token and retries until it gets plain OK.
    settings = get_settings()
    if not settings.tbank_password.get_secret_value():
        raise HTTPException(status_code=503, detail="Payment notifications are not configured")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook payload must be an object")
    if payload.get("TerminalKey") != settings.tbank_terminal_key.get_secret_value():
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    gateway = TBankPaymentGateway(
        settings.tbank_terminal_key,
        settings.tbank_password,
        api_token=settings.tbank_api_token,
        base_url=settings.tbank_api_base_url,
    )
    try:
        if not gateway.verify_notification(payload):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        provider_payment_id = payload.get("PaymentId")
        provider_status = payload.get("Status")
        if provider_payment_id is None or not isinstance(provider_status, str):
            raise HTTPException(status_code=422, detail="Incomplete payment notification")
        amount = payload.get("Amount")
        amount_minor = (
            int(amount) if isinstance(amount, (int, str)) and str(amount).isdigit() else None
        )
        await PaymentService(PaymentRepository(session), gateway).apply_webhook(
            PaymentWebhookDTO(
                provider_payment_id=str(provider_payment_id),
                provider_status=provider_status,
                amount_minor=amount_minor,
                order_id=str(payload["OrderId"]) if payload.get("OrderId") is not None else None,
                success=payload.get("Success")
                if isinstance(payload.get("Success"), bool)
                else None,
                token=payload.get("Token") if isinstance(payload.get("Token"), str) else None,
                event_id=str(payload["EventId"]) if payload.get("EventId") is not None else None,
                payload=payload,
            )
        )
        return PlainTextResponse("OK")
    finally:
        await gateway.aclose()
