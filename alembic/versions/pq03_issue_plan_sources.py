"""issues: кандидаты оценки из нескольких полей Jira и выбор при споре

Revision ID: pq03_issue_plan_sources
Revises: pq01_service_epic_off_plan
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq03_issue_plan_sources"
down_revision: Union[str, None] = "pq01_service_epic_off_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("planned_hours_sources", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("planned_hours_choice", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("planned_hours_choice")
        batch.drop_column("planned_hours_sources")
