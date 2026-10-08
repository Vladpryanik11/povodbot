from src.services.payments.service import (
    AUTHORIZED_STATUSES,
    CONFIRMED_STATUSES,
    FAILED_STATUSES,
    KNOWN_STATUSES,
    REFUNDED_STATUSES,
)


def test_provider_status_sets_keep_confirmation_explicit():
    assert "CONFIRMED" in CONFIRMED_STATUSES
    assert "AUTHORIZED" in AUTHORIZED_STATUSES
    assert "REJECTED" in FAILED_STATUSES
    assert "REFUNDED" in REFUNDED_STATUSES
    assert "CONFIRMED" in KNOWN_STATUSES
    assert "UNKNOWN" not in KNOWN_STATUSES
