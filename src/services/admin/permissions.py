from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from src.models.admin import AdminRole, AdminUser


class Permission(StrEnum):
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_EVENTS = "manage_events"
    MANAGE_ORDERS = "manage_orders"
    REFUND_ORDERS = "refund_orders"
    LOOKUP_TICKETS = "lookup_tickets"
    CHECKIN_TICKETS = "checkin_tickets"
    MANAGE_CRM = "manage_crm"
    MANAGE_CAMPAIGNS = "manage_campaigns"
    MANAGE_ROLES = "manage_roles"


ROLE_PERMISSIONS: dict[AdminRole, frozenset[Permission]] = {
    AdminRole.OWNER: frozenset(Permission),
    AdminRole.ADMINISTRATOR: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.MANAGE_EVENTS,
            Permission.MANAGE_ORDERS,
            Permission.REFUND_ORDERS,
            Permission.LOOKUP_TICKETS,
            Permission.CHECKIN_TICKETS,
            Permission.MANAGE_CRM,
            Permission.MANAGE_CAMPAIGNS,
        }
    ),
    AdminRole.ENTRANCE: frozenset(
        {Permission.VIEW_DASHBOARD, Permission.LOOKUP_TICKETS, Permission.CHECKIN_TICKETS}
    ),
}


@dataclass(frozen=True)
class AdminActor:
    id: UUID
    login: str
    role: AdminRole

    @classmethod
    def from_model(cls, user: AdminUser) -> "AdminActor":
        return cls(user.id, user.login, AdminRole(user.role))


class PermissionDenied(PermissionError):
    pass


class PermissionService:
    @staticmethod
    def require(actor: AdminActor, permission: Permission) -> None:
        if permission not in ROLE_PERMISSIONS[actor.role]:
            raise PermissionDenied(f"Permission required: {permission.value}")

    @staticmethod
    def allows(actor: AdminActor, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[actor.role]
