"""Broadcasts: server favorites, rich campaigns, templates, tracked links and clicks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

EVENT_BUTTON = [{"kind": "event", "label": "Открыть вечер"}]
BUILTIN_TEMPLATES = [
    (
        "Новый вечер в афише",
        "{date} у нас «{event}». Билеты уже можно взять.",
        "event",
        EVENT_BUTTON,
    ),
    (
        "Осталось мало мест",
        "На «{event}» осталось совсем немного мест. Если думаешь пойти, лучше не откладывать.",
        "event",
        EVENT_BUTTON,
    ),
    ("Завтра вечер", "Завтра «{event}». Если билета ещё нет, он тут.", "event", EVENT_BUTTON),
    (
        "Спасибо, что пришли",
        "Спасибо за «{event}», было здорово. Следующий вечер уже в афише.",
        "none",
        [],
    ),
    (
        "Вечер перенесён",
        "С «{event}» поменялись планы. Все подробности по кнопке.",
        "event",
        EVENT_BUTTON,
    ),
]

CAMPAIGN_STATUSES = "'draft', 'scheduled', 'running', 'completed', 'cancelled'"
DELIVERY_STATUSES = "'queued', 'sent', 'failed', 'blocked'"


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("user_id", "event_id", name="pk_favorites"),
    )
    op.create_index("ix_favorites_event", "favorites", ["event_id"])

    op.add_column(
        "campaigns",
        sa.Column(
            "image",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("""'{"kind": "none"}'::jsonb"""),
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "buttons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="RESTRICT")),
    )
    op.add_column("campaigns", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("campaigns", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column("campaigns", sa.Column("recipient_count", sa.Integer()))
    op.add_column("campaigns", sa.Column("short_code", sa.String(12)))
    op.execute("UPDATE campaigns SET short_code = substr(md5(id::text), 1, 8)")
    op.alter_column("campaigns", "short_code", existing_type=sa.String(12), nullable=False)
    op.create_unique_constraint("uq_campaigns_short_code", "campaigns", ["short_code"])
    op.add_column("campaigns", sa.Column("telegram_photo_id", sa.String(256)))
    op.add_column("campaigns", sa.Column("cancel_reason", sa.String(64)))
    # A draft started from a blank page has no text yet; launch checks the body.
    op.drop_constraint(op.f("ck_campaigns_body_nonempty"), "campaigns", type_="check")
    op.drop_constraint(op.f("ck_campaigns_status"), "campaigns", type_="check")
    op.create_check_constraint(
        "status", "campaigns", f"status IN ({CAMPAIGN_STATUSES}, 'stopped')"
    )

    op.drop_constraint(op.f("ck_campaign_deliveries_status"), "campaign_deliveries", type_="check")
    op.create_check_constraint(
        "status", "campaign_deliveries", f"status IN ({DELIVERY_STATUSES}, 'skipped_limit')"
    )
    op.create_index(
        "ix_campaign_deliveries_user_sent", "campaign_deliveries", ["user_id", "sent_at"]
    )

    templates = op.create_table(
        "campaign_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("image_kind", sa.String(8), nullable=False),
        sa.Column(
            "buttons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("image_kind IN ('event', 'upload', 'none')", name="image_kind"),
    )
    for name, body, image_kind, buttons in BUILTIN_TEMPLATES:
        op.execute(
            sa.insert(templates).values(
                id=sa.func.gen_random_uuid(),
                name=name,
                body=body,
                image_kind=image_kind,
                buttons=buttons,
                is_builtin=True,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )

    op.create_table(
        "campaign_links",
        sa.Column("code", sa.String(12), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("button_index", sa.SmallInteger(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.UniqueConstraint(
            "campaign_id", "button_index", name="uq_campaign_links_campaign_id"
        ),
    )
    op.create_table(
        "campaign_clicks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("button_index", sa.SmallInteger(), nullable=False),
        sa.Column(
            "clicked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_campaign_clicks_campaign_user", "campaign_clicks", ["campaign_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_clicks_campaign_user", table_name="campaign_clicks")
    op.drop_table("campaign_clicks")
    op.drop_table("campaign_links")
    op.drop_table("campaign_templates")

    op.drop_index("ix_campaign_deliveries_user_sent", table_name="campaign_deliveries")
    op.execute("DELETE FROM campaign_deliveries WHERE status = 'skipped_limit'")
    op.drop_constraint(op.f("ck_campaign_deliveries_status"), "campaign_deliveries", type_="check")
    op.create_check_constraint("status", "campaign_deliveries", f"status IN ({DELIVERY_STATUSES})")

    op.execute("UPDATE campaigns SET status = 'cancelled' WHERE status = 'stopped'")
    op.drop_constraint(op.f("ck_campaigns_status"), "campaigns", type_="check")
    op.create_check_constraint("status", "campaigns", f"status IN ({CAMPAIGN_STATUSES})")
    op.execute("UPDATE campaigns SET body = title WHERE length(trim(body)) = 0")
    op.create_check_constraint("body_nonempty", "campaigns", "length(trim(body)) > 0")
    for column in (
        "cancel_reason",
        "telegram_photo_id",
        "short_code",
        "recipient_count",
        "finished_at",
        "started_at",
        "event_id",
        "buttons",
        "image",
    ):
        op.drop_column("campaigns", column)

    op.drop_index("ix_favorites_event", table_name="favorites")
    op.drop_table("favorites")
