"""add_resource_plan_assignments

Revision ID: 343432b88ce7
Revises: cf9f40700c14
Create Date: 2026-05-03 17:47:38.403579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '343432b88ce7'
down_revision: Union[str, None] = 'cf9f40700c14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_plan_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("backlog_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("part_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("hours_allocated", sa.Float, nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_on_critical_path", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("slack_days", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resource_plan_assignments")
