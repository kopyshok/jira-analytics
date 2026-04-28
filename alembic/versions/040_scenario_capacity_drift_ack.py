"""scenario_capacity_drift_ack

Revision ID: 040
Revises: 039
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("planning_scenarios") as batch_op:
        batch_op.add_column(
            sa.Column("capacity_drift_acknowledged_at", sa.DateTime, nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("planning_scenarios") as batch_op:
        batch_op.drop_column("capacity_drift_acknowledged_at")
