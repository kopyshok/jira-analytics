"""norm_snapshot_indexes

Revision ID: 041
Revises: 040
Create Date: 2026-04-28
"""
from alembic import op

revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_scenario_norm_snapshots_work_type_id",
        "scenario_norm_snapshots", ["work_type_id"]
    )
    op.create_index(
        "ix_scenario_norm_snapshots_revision_year_month",
        "scenario_norm_snapshots", ["revision_id", "year", "month"]
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_norm_snapshots_revision_year_month",
                  table_name="scenario_norm_snapshots")
    op.drop_index("ix_scenario_norm_snapshots_work_type_id",
                  table_name="scenario_norm_snapshots")
