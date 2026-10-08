from uuid import uuid4

import pytest

from src.services.tickets.qr import InvalidQrToken, QrTokenService


def test_qr_token_is_opaque_signed_and_verifies():
    ticket_id = uuid4()
    service = QrTokenService("test-secret")
    token = service.generate(ticket_id)
    assert str(ticket_id) not in token
    assert service.ticket_id(token) == ticket_id
    assert service.generate(uuid4()) != token

    with pytest.raises(InvalidQrToken):
        service.ticket_id(token[:-1] + ("A" if token[-1] != "A" else "B"))
