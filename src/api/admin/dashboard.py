from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.dependencies import require_permission
from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.commerce import Order
from src.models.events import Event
from src.models.tickets import Ticket
from src.repositories.admin import AdminRepository
from src.services.admin.permissions import AdminActor, Permission
from src.services.audit.service import AuditService
from src.services.tickets.checkin import CheckinService

router = APIRouter(tags=["admin dashboard"])


class DashboardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: int
    orders: int
    tickets: int
    checked_in: int


class CheckinInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    event_id: UUID | None = None


@router.get("/api/admin/dashboard", response_model=DashboardDTO)
async def dashboard(
    actor: Annotated[AdminActor, Depends(require_permission(Permission.VIEW_DASHBOARD))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DashboardDTO:
    del actor
    counts = []
    for model in (Event, Order, Ticket):
        counts.append(await session.scalar(select(func.count()).select_from(model)) or 0)
    checked_in = (
        await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == "checked_in")
        )
        or 0
    )
    return DashboardDTO(
        events=counts[0], orders=counts[1], tickets=counts[2], checked_in=checked_in
    )


@router.post("/api/admin/tickets/check-in")
async def check_in(
    payload: CheckinInput,
    actor: Annotated[AdminActor, Depends(require_permission(Permission.CHECKIN_TICKETS))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    try:
        result = await CheckinService(session).check(
            payload.token, actor.id, datetime.now(UTC), payload.event_id
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Ticket cannot be checked in") from exc
    await AuditService(AdminRepository(session)).record(
        actor.id, "ticket.check_in", "ticket", result.ticket.id
    )
    return {"ticket_id": str(result.ticket.id), "status": result.ticket.status}


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_shell() -> str:
    environment = get_settings().environment
    return f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'>
<title>Повод — админка</title><style>body{{font:16px system-ui;max-width:900px;margin:40px auto}}
nav a{{margin-right:16px}}code{{background:#eee;padding:2px 4px}}</style></head>
<body><h1>«Повод»</h1><p>Административная панель MVP ({environment}).</p>
<nav><a href='/docs'>API docs</a><a href='/api/admin/dashboard'>Dashboard API</a></nav>
<p>Вход выполняется через <code>POST /api/admin/auth/login</code>; cookie HttpOnly.</p>
</body></html>"""
