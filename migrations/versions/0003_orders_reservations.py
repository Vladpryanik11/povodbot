"""Orders, immutable price snapshots and atomic reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("total_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'paid', 'payment_failed', 'expired', 'cancelled', "
            "'refund_requested', 'refunded', 'reconciliation_required')",
            name="status",
        ),
        sa.CheckConstraint("total_kopecks >= 0", name="total_nonnegative"),
        sa.CheckConstraint("currency = 'RUB'", name="currency"),
    )
    op.create_index("ix_orders_event_status", "orders", ["event_id", "status"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "ticket_type_id",
            sa.Uuid(),
            sa.ForeignKey("ticket_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ticket_label", sa.String(256), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("line_total_kopecks", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("price_kopecks >= 0", name="price_nonnegative"),
        sa.CheckConstraint("line_total_kopecks >= 0", name="line_total_nonnegative"),
        sa.CheckConstraint("currency = 'RUB'", name="currency"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "order_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("previous_status", sa.String(32)),
        sa.Column("next_status", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sequence", name="uq_order_events_sequence"),
        sa.CheckConstraint("length(trim(action)) > 0", name="action_nonempty"),
        sa.CheckConstraint(
            "length(trim(reason)) > 0 AND length(reason) <= 64", name="reason_bounded"
        ),
    )
    op.create_index("ix_order_events_order_sequence", "order_events", ["order_id", "sequence"])
    op.create_table(
        "reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_reservations_order_id"),
        sa.CheckConstraint(
            "status IN ('active', 'converted', 'expired', 'released')", name="status"
        ),
    )
    op.create_index("ix_reservations_expiry", "reservations", ["event_id", "status", "expires_at"])
    op.create_table(
        "reservation_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "reservation_id",
            sa.Uuid(),
            sa.ForeignKey("reservations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_item_id", name="uq_reservation_items_order_item_id"),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    op.execute("""
        CREATE FUNCTION reject_commerce_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Commerce history and price snapshots are immutable'
                USING ERRCODE = '55000';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER order_events_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON order_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_commerce_mutation()
    """)
    op.execute("""
        CREATE TRIGGER order_items_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON order_items
        FOR EACH STATEMENT EXECUTE FUNCTION reject_commerce_mutation()
    """)


def downgrade() -> None:
    op.drop_table("reservation_items")
    op.drop_index("ix_reservations_expiry", table_name="reservations")
    op.drop_table("reservations")
    op.drop_index("ix_order_events_order_sequence", table_name="order_events")
    op.drop_table("order_events")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_event_status", table_name="orders")
    op.drop_table("orders")
    op.execute("DROP FUNCTION reject_commerce_mutation()")
