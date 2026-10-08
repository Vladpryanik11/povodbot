from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class ConsentType(StrEnum):
    PERSONAL_DATA = "personal_data"
    MARKETING = "marketing"


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    REVOKED = "revoked"


class ConsentSource(StrEnum):
    TELEGRAM = "telegram"
    ADMIN = "admin"


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("telegram_id > 0", name="telegram_id_positive"),)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    is_blocked: Mapped[bool] = mapped_column(default=False)
    first_name: Mapped[str | None] = mapped_column(String(256))
    last_name: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(256))
    first_start_param: Mapped[str | None] = mapped_column(String(64))
    last_start_param: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Consent(UUIDPrimaryKey, Base):
    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint("consent_type IN ('personal_data', 'marketing')", name="type"),
        CheckConstraint("status IN ('granted', 'revoked')", name="status"),
        CheckConstraint("source IN ('telegram', 'admin')", name="source"),
        CheckConstraint(
            "(status = 'revoked' AND text_version IS NULL) OR "
            "(text_version IS NOT NULL AND length(trim(text_version)) > 0)",
            name="version",
        ),
        Index("ix_consents_effective", "user_id", "consent_type", "sequence"),
    )
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    consent_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    text_version: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
