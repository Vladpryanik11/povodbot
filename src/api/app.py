from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.admin.events import router as admin_events_router
from src.api.admin.payments import router as admin_payments_router
from src.api.health import router
from src.api.public.events import router as public_events_router
from src.api.webhooks.tbank import router as tbank_webhook_router
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings())
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Application factory; startup never migrates or contacts external services."""
    app = FastAPI(title="Повод", lifespan=lifespan)
    app.include_router(router)
    app.include_router(admin_events_router)
    app.include_router(admin_payments_router)
    app.include_router(public_events_router)
    app.include_router(tbank_webhook_router)
    return app
