"""scenario_norm_snapshot

Revision ID: 038
Revises: 037_user_selected_teams
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = '038'
down_revision = '037_user_selected_teams'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_norm_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("work_type_id", sa.String(36),
                  sa.ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("work_type_label", sa.String(255), nullable=False),
        sa.Column("norm_hours", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_scenario_norm_snapshots_revision_id",
                    "scenario_norm_snapshots", ["revision_id"])
    op.create_index("ix_scenario_norm_snapshots_employee_id",
                    "scenario_norm_snapshots", ["employee_id"])


def downgrade() -> None:
    op.drop_table("scenario_norm_snapshots")
