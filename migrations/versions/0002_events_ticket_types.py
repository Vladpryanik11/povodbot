"""Event catalog and ticket types; no commerce storage."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cover_ref", sa.String(2048)),
        sa.Column(
            "direction_id",
            sa.Uuid(),
            sa.ForeignKey("directions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(128), nullable=False),
        sa.Column("address", sa.String(1024), nullable=False),
        sa.Column("map_url", sa.String(2048)),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        sa.CheckConstraint("length(trim(description)) > 0", name="description_nonempty"),
        sa.CheckConstraint("length(trim(address)) > 0", name="address_nonempty"),
        sa.CheckConstraint("capacity > 0", name="capacity_positive"),
        sa.CheckConstraint("ends_at > starts_at", name="date_order"),
        sa.CheckConstraint("length(trim(timezone)) > 0", name="timezone_nonempty"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'cancelled', 'completed')", name="status"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND published_at IS NULL) OR "
            "(status <> 'draft' AND published_at IS NOT NULL)",
            name="publication",
        ),
    )
    op.create_index("ix_events_showcase", "events", ["status", "starts_at", "direction_id"])
    op.create_table(
        "ticket_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("price_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        sa.CheckConstraint("price_kopecks >= 0", name="price_nonnegative"),
        sa.CheckConstraint("currency = 'RUB'", name="currency"),
        sa.CheckConstraint('"limit" > 0', name="limit_positive"),
    )
    op.create_index("ix_ticket_types_event_id", "ticket_types", ["event_id"])
    op.execute("""
        CREATE FUNCTION protect_published_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'Published events cannot be deleted' USING ERRCODE = '55000';
            END IF;
            RETURN OLD;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER events_no_published_delete BEFORE DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION protect_published_event()
    """)


def downgrade() -> None:
    op.drop_table("ticket_types")
    op.drop_table("events")
    op.execute("DROP FUNCTION protect_published_event()")
