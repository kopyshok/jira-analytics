"""sync_pipeline tables + default schedule seeds

Revision ID: 035_sync_pipeline
Revises: e97b35c021a7
Create Date: 2026-04-27 12:00:00
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "035_sync_pipeline"
down_revision = "e97b35c021a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_schedule",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("cron_expr", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_run_id", sa.String(36), nullable=True),
        sa.Column("next_run_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "sync_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("stages_json", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("error_text", sa.Text, nullable=True),
        sa.Column(
            "schedule_id",
            sa.String(36),
            sa.ForeignKey("sync_schedule.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_index("ix_sync_run_started_at", "sync_run", ["started_at"])
    op.create_index("ix_sync_run_status", "sync_run", ["status"])

    # Seed default schedule rules только если таблица пуста
    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM sync_schedule")).scalar()
    if existing == 0:
        seeds = [
            ("daily_incremental", "0 6 * * *", "normal"),
            ("worklogs_workhours", "0 8-20/2 * * 1-5", "quick"),
            ("weekly_full", "0 3 * * 0", "full"),
        ]
        for name, cron, mode in seeds:
            bind.execute(
                sa.text(
                    "INSERT INTO sync_schedule "
                    "(id, name, cron_expr, mode, enabled, created_at, updated_at) "
                    "VALUES (:id, :name, :cron, :mode, 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": str(uuid.uuid4()), "name": name, "cron": cron, "mode": mode},
            )


def downgrade() -> None:
    op.drop_index("ix_sync_run_status", table_name="sync_run")
    op.drop_index("ix_sync_run_started_at", table_name="sync_run")
    op.drop_table("sync_run")
    op.drop_table("sync_schedule")
