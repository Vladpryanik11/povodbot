import asyncio
from typing import Annotated

from asyncpg import PostgresError
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_async_session)]) -> JSONResponse:
    try:
        async with asyncio.timeout(get_settings().database_timeout_seconds):
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        # The probe may have left an aborted transaction or invalidated connection.
        await session.rollback()
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependencies": {"database": "unavailable"}},
        )
    return JSONResponse(content={"status": "ready", "dependencies": {"database": "ok"}})
