"""KPI approvals switch from month to quarter

Заказчик решил (2026-08-06), что подписывается только целый квартал, а не
каждый месяц. Существующие месячные утверждения переводятся в квартал
арифметически; на момент миграции таблица пуста во всех известных базах,
поэтому схлопывания трёх месяцев одного квартала в одну строку здесь не
происходит — если бы строки были, уникальное ограничение по (team, year,
quarter) заставило бы разбираться руками, и это правильнее тихого выбора
«какой из трёх снимков считать кварталом».

Revision ID: kpq01_kpi_approval_quarter
Revises: td04a_user_team_desk_filter
"""
import sqlalchemy as sa
from alembic import op

revision = "kpq01_kpi_approval_quarter"
down_revision = "td04a_user_team_desk_filter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kpi_approvals") as batch:
        batch.alter_column("month", new_column_name="quarter", existing_type=sa.Integer())
    op.execute("UPDATE kpi_approvals SET quarter = (quarter + 2) / 3")


def downgrade() -> None:
    # Квартал разворачивается в его последний месяц — единственный месяц,
    # для которого утверждение квартала было бы верным и в старой схеме.
    op.execute("UPDATE kpi_approvals SET quarter = quarter * 3")
    with op.batch_alter_table("kpi_approvals") as batch:
        batch.alter_column("quarter", new_column_name="month", existing_type=sa.Integer())
