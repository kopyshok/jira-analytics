"""issues: кандидаты оценки из нескольких полей Jira и выбор при споре

Revision ID: pq03_issue_plan_sources
Revises: pq01_service_epic_off_plan
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "pq03_issue_plan_sources"
down_revision: Union[str, None] = "pq01_service_epic_off_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json() -> sa.types.TypeEngine:
    # На PostgreSQL — JSONB: у простого json нет оператора равенства,
    # и SELECT DISTINCT по строкам задач падает.
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("planned_hours_sources", _json(), nullable=True))
        batch.add_column(sa.Column("planned_hours_choice", _json(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("planned_hours_choice")
        batch.drop_column("planned_hours_sources")
