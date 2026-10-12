from dataclasses import dataclass
from uuid import UUID

from src.core.config import Settings, get_settings

NOTIFICATION_PATH = "/api/webhooks/tbank/payment-status"


@dataclass(frozen=True)
class PaymentUrls:
    notification_url: str | None
    success_url: str | None
    fail_url: str | None


def payment_urls(order_id: UUID, settings: Settings | None = None) -> PaymentUrls:
    """Per-order Init addresses, so the shared terminal's cabinet settings stay untouched."""
    settings = settings or get_settings()
    base = settings.public_base_url.strip().rstrip("/")
    miniapp = settings.miniapp_link.strip().rstrip("/")
    back = f"{miniapp}?startapp=order_{order_id.hex}" if miniapp else None
    return PaymentUrls(
        notification_url=f"{base}{NOTIFICATION_PATH}" if base else None,
        success_url=back,
        fail_url=back,
    )
