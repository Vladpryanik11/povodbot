from src.api.app import create_app


def test_mvp_boundaries_are_registered():
    paths = {route.path for route in create_app().routes}
    assert "/health" in paths
    assert "/ready" in paths
    assert "/api/public/events" in paths
    assert "/api/webhooks/tbank/payment-status" in paths
    assert "/api/admin/auth/login" in paths
    assert "/api/admin/tickets/check-in" in paths
    assert "/api/admin/campaigns" in paths
