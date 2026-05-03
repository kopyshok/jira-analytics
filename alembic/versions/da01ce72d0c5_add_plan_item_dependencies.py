"""add_plan_item_dependencies

Revision ID: da01ce72d0c5
Revises: 343432b88ce7
Create Date: 2026-05-03 20:31:39.140179

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da01ce72d0c5'
down_revision: Union[str, None] = '343432b88ce7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_item_dependencies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_item_id", sa.String(36), sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dep_type", sa.String(4), nullable=False, server_default="FS"),
        sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_item_dependencies_plan_id", "plan_item_dependencies", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_item_dependencies_plan_id", table_name="plan_item_dependencies")
    op.drop_table("plan_item_dependencies")
