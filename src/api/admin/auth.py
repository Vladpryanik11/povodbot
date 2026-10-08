from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_async_session
from src.models.admin import AdminRole
from src.repositories.admin import AdminRepository
from src.services.admin.auth import AdminAuthService
from src.services.admin.permissions import AdminActor
from src.services.audit.service import AuditService

router = APIRouter(prefix="/api/admin/auth", tags=["admin auth"])
SESSION_COOKIE = "povod_admin_session"


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str
    password: SecretStr


class ActorDTO(BaseModel):
    id: str
    login: str
    role: AdminRole

    @classmethod
    def from_actor(cls, actor: AdminActor) -> ActorDTO:
        return cls(id=str(actor.id), login=actor.login, role=actor.role)


def _service(session: AsyncSession) -> AdminAuthService:
    return AdminAuthService(AdminRepository(session))


async def get_current_admin(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> AdminActor:
    if not token:
        # Preserve the existing admin API contract: unauthenticated admin
        # operations are denied without disclosing session details.
        raise HTTPException(status_code=403, detail="Admin authentication required")
    actor = await _service(session).actor_for_token(token)
    if actor is None:
        raise HTTPException(status_code=403, detail="Admin authentication required")
    return actor


@router.post("/login", response_model=ActorDTO)
async def login(
    payload: LoginInput,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ActorDTO:
    result = await _service(session).authenticate(payload.login, payload.password)
    if result is None:
        await AuditService(AdminRepository(session)).record(
            None,
            "admin.login_failed",
            "admin_session",
            metadata={"login": payload.login[:128]},
            success=False,
        )
        raise HTTPException(status_code=401, detail="Invalid login or password")
    await AuditService(AdminRepository(session)).record(
        result.actor.id, "admin.login", "admin_session"
    )
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=8 * 60 * 60,
        httponly=True,
        secure=get_settings().environment == "production",
        samesite="lax",
        path="/api/admin",
    )
    return ActorDTO.from_actor(result.actor)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    actor: Annotated[AdminActor, Depends(get_current_admin)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if token:
        await _service(session).logout(token)
    await AuditService(AdminRepository(session)).record(actor.id, "admin.logout", "admin_session")
    response.delete_cookie(SESSION_COOKIE, path="/api/admin")


@router.get("/me", response_model=ActorDTO)
async def me(actor: Annotated[AdminActor, Depends(get_current_admin)]) -> ActorDTO:
    return ActorDTO.from_actor(actor)
