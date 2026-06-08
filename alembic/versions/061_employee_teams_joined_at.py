"""employee_teams.joined_at — дата вступления сотрудника в команду

Revision ID: 061_employee_teams_joined_at
Revises: 060_backlog_planning_mode
Create Date: 2026-06-08
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "061_employee_teams_joined_at"
down_revision: Union[str, None] = "060_backlog_planning_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch:
        batch.add_column(sa.Column("joined_at", sa.Date, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch:
        batch.drop_column("joined_at")
