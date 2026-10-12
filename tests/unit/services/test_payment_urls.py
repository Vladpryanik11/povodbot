from uuid import UUID

from src.core.config import Settings
from src.services.payments.urls import PaymentUrls, payment_urls

ORDER_ID = UUID("12345678-1234-5678-1234-567812345678")


def settings(**values):
    return Settings(environment="test", _env_file=None, **values)


def test_payment_urls_from_settings():
    urls = payment_urls(
        ORDER_ID,
        settings(
            public_base_url="https://144-31-76-55.sslip.io/",
            miniapp_link="https://t.me/povod_bot/app",
        ),
    )
    back = f"https://t.me/povod_bot/app?startapp=order_{ORDER_ID.hex}"
    assert urls == PaymentUrls(
        notification_url="https://144-31-76-55.sslip.io/api/webhooks/tbank/payment-status",
        success_url=back,
        fail_url=back,
    )


def test_payment_urls_are_omitted_without_settings():
    assert payment_urls(ORDER_ID, settings()) == PaymentUrls(None, None, None)
