"""Identity, append-only consents, directions and outbox storage."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(256)),
        sa.Column("last_name", sa.String(256)),
        sa.Column("username", sa.String(256)),
        sa.Column("first_start_param", sa.String(64)),
        sa.Column("last_start_param", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        sa.CheckConstraint("telegram_id > 0", name="telegram_id_positive"),
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("consent_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("text_version", sa.String(128)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sequence", name="uq_consents_sequence"),
        sa.CheckConstraint("consent_type IN ('personal_data', 'marketing')", name="type"),
        sa.CheckConstraint("status IN ('granted', 'revoked')", name="status"),
        sa.CheckConstraint("source IN ('telegram', 'admin')", name="source"),
        sa.CheckConstraint(
            "(status = 'revoked' AND text_version IS NULL) OR "
            "(text_version IS NOT NULL AND length(trim(text_version)) > 0)",
            name="version",
        ),
    )
    op.create_index("ix_consents_effective", "consents", ["user_id", "consent_type", "sequence"])
    op.execute("""
        CREATE FUNCTION reject_consent_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Consent history is append-only' USING ERRCODE = '55000';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER consents_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON consents
        FOR EACH STATEMENT EXECUTE FUNCTION reject_consent_mutation()
    """)
    op.create_table(
        "directions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_directions_slug"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
    )
    directions = sa.table(
        "directions",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    # Explicit initial data, not an enum or an import side effect.
    for number, slug, name in [
        (1, "cinema", "Кино"),
        (2, "books", "Книги"),
        (3, "workshops", "Мастер-классы"),
    ]:
        op.execute(
            directions.insert().values(
                id=UUID(int=number),
                slug=slug,
                name=name,
                sort_order=number * 10,
                active=True,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("deduplication_key", sa.String(256), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("deduplication_key", name="uq_outbox_deduplication_key"),
        sa.CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
    )
    op.create_index("ix_outbox_pending", "outbox", ["processed_at", "available_at"])


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("directions")
    op.drop_table("consents")
    op.execute("DROP FUNCTION reject_consent_mutation()")
    op.drop_table("users")
