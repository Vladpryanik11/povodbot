from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    ENTRANCE = "entrance"


class AdminUser(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint("length(trim(login)) >= 3", name="login_nonempty"),
        CheckConstraint("role IN ('owner', 'administrator', 'entrance')", name="role"),
    )
    login: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default=AdminRole.ADMINISTRATOR)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sessions: Mapped[list["AdminSession"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminSession(UUIDPrimaryKey, Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (Index("ix_admin_sessions_active", "token_hash", "expires_at", "revoked_at"),)
    admin_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin: Mapped[AdminUser] = relationship(back_populates="sessions")


class AdminAuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        CheckConstraint("length(trim(action)) > 0", name="action_nonempty"),
        CheckConstraint("length(trim(object_type)) > 0", name="object_type_nonempty"),
        Index("ix_admin_audit_created", "created_at", "action"),
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(128))
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[UUID | None]
    details: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = ["AdminAuditLog", "AdminRole", "AdminSession", "AdminUser"]
