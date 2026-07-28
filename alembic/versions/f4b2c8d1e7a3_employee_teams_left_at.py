"""employee_teams.left_at — дата выбытия + периодизация участия

Снимает уникальность (employee_id, team): одна пара может иметь несколько
непересекающихся периодов участия (ушёл — вернулся). Непересечение
проверяется в EmployeeTeamService.

Revision ID: f4b2c8d1e7a3
Revises: f3a1b2c4d5e6
Create Date: 2026-07-28
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4b2c8d1e7a3"
down_revision: Union[str, None] = "f3a1b2c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch:
        batch.add_column(sa.Column("left_at", sa.Date, nullable=True))
        batch.drop_constraint("uq_employee_teams_employee_team", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch:
        batch.create_unique_constraint(
            "uq_employee_teams_employee_team", ["employee_id", "team"]
        )
        batch.drop_column("left_at")
