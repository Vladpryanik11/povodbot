"""T-Bank payment records and idempotent provider events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(64)),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_status", sa.String(64)),
        sa.Column("payment_url", sa.String(2048)),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("refunded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_payments_order_id"),
        sa.UniqueConstraint("provider_payment_id", name="uq_payments_provider_payment_id"),
        sa.CheckConstraint("provider = 'tbank'", name="provider"),
        sa.CheckConstraint("amount_kopecks > 0", name="amount_positive"),
        sa.CheckConstraint("currency = 'RUB'", name="currency"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'authorized', 'confirmed', 'failed', "
            "'cancelled', 'refunding', 'refunded', 'reconciliation_required')",
            name="status",
        ),
    )
    op.create_index(
        "ix_payments_provider_payment_id", "payments", ["provider", "provider_payment_id"]
    )
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(64), nullable=False),
        sa.Column("deduplication_key", sa.String(256), nullable=False),
        sa.Column("provider_status", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("ignored_reason", sa.String(128)),
        sa.UniqueConstraint("deduplication_key", name="uq_payment_events_deduplication_key"),
        sa.CheckConstraint("length(trim(provider)) > 0", name="provider_nonempty"),
        sa.CheckConstraint(
            "length(trim(deduplication_key)) > 0", name="deduplication_key_nonempty"
        ),
    )
    op.create_index(
        "ix_payment_events_payment_received", "payment_events", ["payment_id", "received_at"]
    )
    op.create_index(
        "ix_payment_events_provider_payment",
        "payment_events",
        ["provider", "provider_payment_id"],
    )


def downgrade() -> None:
    op.drop_table("payment_events")
    op.drop_index("ix_payments_provider_payment_id", table_name="payments")
    op.drop_table("payments")
