"""scenario_absence_snapshot

Revision ID: 039
Revises: 038
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_absence_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("original_absence_id", sa.String(36), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("reason_id", sa.String(36), nullable=True),
        sa.Column("reason_label", sa.String(255), nullable=True),
        sa.Column("hours_total", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_scenario_absence_snapshots_revision_id",
                    "scenario_absence_snapshots", ["revision_id"])
    op.create_index("ix_scenario_absence_snapshots_employee_id",
                    "scenario_absence_snapshots", ["employee_id"])


def downgrade() -> None:
    op.drop_table("scenario_absence_snapshots")
