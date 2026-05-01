"""add user.selected_period and analytics_columns

Revision ID: 045_user_period_and_analytics_columns
Revises: 044_work_type_is_system
Create Date: 2026-05-01

"""
import sqlalchemy as sa
from alembic import op

revision = "045_user_period_and_analytics_columns"
down_revision = "044_work_type_is_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column(
            "selected_period", sa.Text(), nullable=False, server_default="{}"
        ))
        batch_op.add_column(sa.Column(
            "analytics_columns", sa.Text(), nullable=False, server_default="[]"
        ))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("analytics_columns")
        batch_op.drop_column("selected_period")
