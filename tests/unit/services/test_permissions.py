from uuid import uuid4

import pytest

from src.models.admin import AdminRole
from src.services.admin.auth import hash_password, verify_password
from src.services.admin.permissions import (
    AdminActor,
    Permission,
    PermissionDenied,
    PermissionService,
)


def test_role_matrix_keeps_entrance_staff_narrow():
    entrance = AdminActor(uuid4(), "door", AdminRole.ENTRANCE)
    PermissionService.require(entrance, Permission.CHECKIN_TICKETS)
    with pytest.raises(PermissionDenied):
        PermissionService.require(entrance, Permission.REFUND_ORDERS)
    with pytest.raises(PermissionDenied):
        PermissionService.require(entrance, Permission.MANAGE_CAMPAIGNS)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong", first)
