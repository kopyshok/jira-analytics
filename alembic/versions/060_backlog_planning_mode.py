"""backlog_items.planning_mode + included_in_planning

Revision ID: 060_backlog_planning_mode
Revises: 059_plan_audit
Create Date: 2026-06-03
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "060_backlog_planning_mode"
down_revision: Union[str, None] = "059_plan_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column("planning_mode", sa.String(16), nullable=False, server_default="whole"))
        batch.add_column(sa.Column("included_in_planning", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("included_in_planning")
        batch.drop_column("planning_mode")
