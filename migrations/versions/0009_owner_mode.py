"""Owner mode: Telegram link for admins, poster focus and accent, optional address."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("uq_admin_users_telegram_id", "admin_users", ["telegram_id"])

    for name in ("cover_focus_x", "cover_focus_y"):
        op.add_column(
            "events",
            sa.Column(
                name,
                sa.Numeric(4, 3),
                nullable=False,
                server_default=sa.text("0.5"),
            ),
        )
        op.create_check_constraint(f"{name}_range", "events", f"{name} BETWEEN 0 AND 1")
    op.add_column("events", sa.Column("cover_width", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("cover_height", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("accent_color", sa.String(7), nullable=True))
    op.create_check_constraint("accent_color_hex", "events", "accent_color ~ '^#[0-9A-Fa-f]{6}$'")
    op.alter_column("events", "address", existing_type=sa.String(1024), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE events SET address = 'Место уточняется' WHERE address IS NULL")
    op.alter_column("events", "address", existing_type=sa.String(1024), nullable=False)
    op.drop_constraint(op.f("ck_events_accent_color_hex"), "events", type_="check")
    op.drop_column("events", "accent_color")
    op.drop_column("events", "cover_height")
    op.drop_column("events", "cover_width")
    for name in ("cover_focus_y", "cover_focus_x"):
        op.drop_constraint(op.f(f"ck_events_{name}_range"), "events", type_="check")
        op.drop_column("events", name)
    op.drop_constraint("uq_admin_users_telegram_id", "admin_users", type_="unique")
    op.drop_column("admin_users", "telegram_id")
