from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.admin.auth import router as admin_auth_router
from src.api.admin.campaigns import router as admin_campaigns_router
from src.api.admin.dashboard import router as admin_dashboard_router
from src.api.admin.events import router as admin_events_router
from src.api.admin.payments import router as admin_payments_router
from src.api.guest.campaigns import router as guest_campaigns_router
from src.api.guest.favorites import router as guest_favorites_router
from src.api.guest.router import router as guest_router
from src.api.health import router
from src.api.metrics import router as metrics_router
from src.api.owner import router as owner_router
from src.api.public.events import router as public_events_router
from src.api.public.redirect import router as redirect_router
from src.api.webhooks.tbank import router as tbank_webhook_router
from src.core.config import get_settings
from src.core.observability import configure_observability
from src.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_observability(get_settings())
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Application factory; startup never migrates or contacts external services."""
    app = FastAPI(title="Повод", lifespan=lifespan)
    app.include_router(router)
    app.include_router(metrics_router)
    app.include_router(admin_auth_router)
    app.include_router(admin_dashboard_router)
    app.include_router(admin_campaigns_router)
    app.include_router(admin_events_router)
    app.include_router(admin_payments_router)
    app.include_router(owner_router)
    app.include_router(public_events_router)
    app.include_router(guest_router)
    app.include_router(guest_favorites_router)
    app.include_router(guest_campaigns_router)
    app.include_router(redirect_router)
    app.include_router(tbank_webhook_router)
    return app
