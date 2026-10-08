"""Electronic tickets, opaque QR tokens and atomic check-ins."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "ticket_type_id",
            sa.Uuid(),
            sa.ForeignKey("ticket_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True)),
        sa.Column("checked_in_by", sa.Uuid()),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.Text()),
        sa.UniqueConstraint("token_hash", name="uq_tickets_token_hash"),
        sa.CheckConstraint("position > 0", name="position_positive"),
        sa.CheckConstraint("currency = 'RUB'", name="currency"),
        sa.CheckConstraint("status IN ('issued', 'checked_in', 'voided')", name="status"),
    )
    op.create_index("ix_tickets_event_status", "tickets", ["event_id", "status"])
    op.create_index(
        "ix_tickets_order_item_position", "tickets", ["order_item_id", "position"], unique=True
    )
    op.create_table(
        "checkins",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.UniqueConstraint("ticket_id", name="uq_checkins_ticket_id"),
    )
    op.create_index("ix_checkins_ticket_checked_at", "checkins", ["ticket_id", "checked_at"])
    op.execute("""
        CREATE FUNCTION validate_ticket_order_item_reference()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            ticket_event UUID;
            item_order UUID;
            item_event UUID;
        BEGIN
            SELECT event_id INTO ticket_event FROM orders WHERE id = NEW.order_id;
            SELECT oi.order_id, o.event_id
              INTO item_order, item_event
              FROM order_items oi
              JOIN orders o ON o.id = oi.order_id
             WHERE oi.id = NEW.order_item_id;
            IF item_order IS NULL OR item_order <> NEW.order_id OR ticket_event <> item_event THEN
                RAISE EXCEPTION 'Ticket must reference its own order item'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tickets_validate_order_item
        BEFORE INSERT OR UPDATE ON tickets
        FOR EACH ROW EXECUTE FUNCTION validate_ticket_order_item_reference()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tickets_validate_order_item ON tickets")
    op.execute("DROP FUNCTION validate_ticket_order_item_reference()")
    op.drop_index("ix_checkins_ticket_checked_at", table_name="checkins")
    op.drop_table("checkins")
    op.drop_index("ix_tickets_order_item_position", table_name="tickets")
    op.drop_index("ix_tickets_event_status", table_name="tickets")
    op.drop_table("tickets")
