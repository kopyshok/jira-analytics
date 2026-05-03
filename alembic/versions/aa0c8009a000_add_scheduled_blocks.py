"""add_scheduled_blocks

Revision ID: aa0c8009a000
Revises: 046_add_work_breakdown_to_project_ai_summary
Create Date: 2026-05-03 17:47:12.777080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa0c8009a000'
down_revision: Union[str, None] = '046_add_work_breakdown_to_project_ai_summary'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scheduled_blocks")
