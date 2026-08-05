"""kpi: дни простоя задачи в статусе паузы

Revision ID: k15a_kpi_issue_paused_days
Revises: k14a_kpi_person_assignee
Create Date: 2026-08-05
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k15a_kpi_issue_paused_days"
down_revision: Union[str, None] = "k14a_kpi_person_assignee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("paused_days", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("paused_days")
