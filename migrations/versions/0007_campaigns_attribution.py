"""Consent-gated campaigns, delivery state and attribution."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("users", "is_blocked", server_default=None)
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("audience", postgresql.JSONB(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        sa.CheckConstraint("length(trim(body)) > 0", name="body_nonempty"),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'running', 'completed', 'cancelled')",
            name="status",
        ),
    )
    op.create_table(
        "campaign_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("provider_message_id", sa.String(128)),
        sa.Column("error", sa.String(512)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_campaign_deliveries_idempotency_key"),
        sa.CheckConstraint("status IN ('queued', 'sent', 'failed', 'blocked')", name="status"),
        sa.CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
    )
    op.create_index(
        "ix_campaign_deliveries_campaign_status",
        "campaign_deliveries",
        ["campaign_id", "status"],
    )
    op.create_table(
        "attributions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("first_start_param", sa.String(64)),
        sa.Column("latest_start_param", sa.String(64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_purchase_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", name="uq_attributions_user_id"),
    )
    op.create_index("ix_attributions_latest_start", "attributions", ["latest_start_param"])
    op.create_table(
        "funnel_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("event_name", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_funnel_events_user_occurred", "funnel_events", ["user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_funnel_events_user_occurred", table_name="funnel_events")
    op.drop_table("funnel_events")
    op.drop_index("ix_attributions_latest_start", table_name="attributions")
    op.drop_table("attributions")
    op.drop_index("ix_campaign_deliveries_campaign_status", table_name="campaign_deliveries")
    op.drop_table("campaign_deliveries")
    op.drop_table("campaigns")
    op.drop_column("users", "is_blocked")
