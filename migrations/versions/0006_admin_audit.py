"""Administrative sessions, roles and redacted audit records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("login", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("login", name="uq_admin_users_login"),
        sa.CheckConstraint("length(trim(login)) >= 3", name="login_nonempty"),
        sa.CheckConstraint("role IN ('owner', 'administrator', 'entrance')", name="role"),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "admin_id",
            sa.Uuid(),
            sa.ForeignKey("admin_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index(
        "ix_admin_sessions_active",
        "admin_sessions",
        ["token_hash", "expires_at", "revoked_at"],
    )
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.Uuid()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(action)) > 0", name="action_nonempty"),
        sa.CheckConstraint("length(trim(object_type)) > 0", name="object_type_nonempty"),
    )
    op.create_index("ix_admin_audit_created", "admin_audit_logs", ["created_at", "action"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_admin_sessions_active", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")
