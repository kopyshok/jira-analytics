"""add_plan_conflicts

Revision ID: 86308219f1e6
Revises: da01ce72d0c5
Create Date: 2026-05-03 23:09:08.120528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86308219f1e6'
down_revision: Union[str, None] = 'da01ce72d0c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_conflicts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36),
            sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("backlog_item_id", sa.String(36), nullable=True),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("assignment_id", sa.String(36), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detection_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_conflicts_plan_id", "plan_conflicts", ["plan_id"])
    op.create_index("ix_plan_conflicts_detection_key", "plan_conflicts", ["detection_key"])


def downgrade() -> None:
    op.drop_index("ix_plan_conflicts_detection_key", table_name="plan_conflicts")
    op.drop_index("ix_plan_conflicts_plan_id", table_name="plan_conflicts")
    op.drop_table("plan_conflicts")
