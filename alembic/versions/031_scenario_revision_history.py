"""Scenario revision history: revisions, revision items, capacity snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "031_scenario_revision_history"
down_revision = "030_work_types_all_subtract"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scenario_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column("approved_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "scenario_revision_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("backlog_item_id", sa.String(36),
                  sa.ForeignKey("backlog_items.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("backlog_item_name", sa.String(500), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "scenario_capacity_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("norm_hours", sa.Float, nullable=False),
        sa.Column("available_hours", sa.Float, nullable=False),
        sa.Column("snapshot_taken_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("scenario_capacity_snapshots")
    op.drop_table("scenario_revision_items")
    op.drop_table("scenario_revisions")
