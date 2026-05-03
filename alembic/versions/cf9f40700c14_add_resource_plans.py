"""add_resource_plans

Revision ID: cf9f40700c14
Revises: aa0c8009a000
Create Date: 2026-05-03 17:47:27.600342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf9f40700c14'
down_revision: Union[str, None] = 'aa0c8009a000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("planning_scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("quarter", sa.String(10), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("computed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resource_plans")
