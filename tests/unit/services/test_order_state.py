import itertools

import pytest

from src.models.commerce import OrderStatus, OrderTransition
from src.services.orders.service import InvalidOrderTransition, next_state

ALLOWED = {
    ("pending_payment", "confirm_payment"): "paid",
    ("pending_payment", "fail_payment"): "payment_failed",
    ("pending_payment", "expire"): "expired",
    ("pending_payment", "cancel"): "cancelled",
    ("pending_payment", "require_reconciliation"): "reconciliation_required",
    ("paid", "request_refund"): "refund_requested",
    ("paid", "require_reconciliation"): "reconciliation_required",
    ("payment_failed", "require_reconciliation"): "reconciliation_required",
    ("expired", "require_reconciliation"): "reconciliation_required",
    ("cancelled", "require_reconciliation"): "reconciliation_required",
    ("reconciliation_required", "request_refund"): "refund_requested",
    ("reconciliation_required", "resolve_payment"): "paid",
    ("refund_requested", "confirm_refund"): "refunded",
}
REPLAYS = {
    ("paid", "confirm_payment"),
    ("payment_failed", "fail_payment"),
    ("expired", "expire"),
    ("cancelled", "cancel"),
    ("refund_requested", "request_refund"),
    ("refunded", "confirm_refund"),
    ("reconciliation_required", "require_reconciliation"),
}


@pytest.mark.parametrize("state,action", list(itertools.product(OrderStatus, OrderTransition)))
def test_explicit_state_machine_never_reopens_terminal_orders(state, action):
    pair = (state.value, action.value)
    if pair in ALLOWED:
        assert next_state(state, action).value == ALLOWED[pair]
    elif pair in REPLAYS:
        assert next_state(state, action) == state
    else:
        with pytest.raises(InvalidOrderTransition):
            next_state(state, action)
