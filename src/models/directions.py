from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, Timestamps, UUIDPrimaryKey


class Direction(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "directions"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
