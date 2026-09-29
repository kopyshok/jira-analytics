"""employee_subgroup_shares: распределение сотрудника по группам с даты

Revision ID: sg01_subgroup_shares
Revises: pi01_personal_settings
Create Date: 2026-09-29

Переносит нынешнюю группу участия в запись «100% с начала участия».
Колонку группы у участия не трогает — её убирает sg02, когда все расчёты
читают доли. Самодостаточна: не импортирует код приложения. Локальная
dev-база может уже иметь таблицу от create_all в tests/conftest.py.
"""
from datetime import date, datetime
import uuid
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sg01_subgroup_shares"
down_revision: Union[str, None] = "pi01_personal_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "employee_subgroup_shares"


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "employee_id", sa.String(36),
                sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("team", sa.String(100), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column(
                "subgroup_id", sa.String(36),
                sa.ForeignKey("team_subgroups.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("percent", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_employee_subgroup_shares_emp_team", TABLE, ["employee_id", "team"]
        )
        op.create_index("ix_employee_subgroup_shares_subgroup_id", TABLE, ["subgroup_id"])

    if context.is_offline_mode():
        return
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("employee_teams")}
    if "subgroup_id" not in columns:
        return

    et = sa.table(
        "employee_teams",
        sa.column("employee_id", sa.String),
        sa.column("team", sa.String),
        sa.column("subgroup_id", sa.String),
        sa.column("joined_at", sa.Date),
    )
    sh = sa.table(
        TABLE,
        sa.column("id", sa.String),
        sa.column("employee_id", sa.String),
        sa.column("team", sa.String),
        sa.column("valid_from", sa.Date),
        sa.column("subgroup_id", sa.String),
        sa.column("percent", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    sg = sa.table(
        "team_subgroups", sa.column("id", sa.String), sa.column("team_id", sa.String)
    )
    tt = sa.table("teams", sa.column("id", sa.String), sa.column("name", sa.String))

    # Группа принадлежит команде — переносим её только туда, где сотрудник
    # состоит именно в этой команде (перенос группы в чужую команду исключён).
    group_team = {
        r[0]: r[1]
        for r in bind.execute(
            sa.select(sg.c.id, tt.c.name).select_from(sg.join(tt, sg.c.team_id == tt.c.id))
        )
    }
    done = {(r[0], r[1]) for r in bind.execute(sa.select(sh.c.employee_id, sh.c.team))}
    # Группа одна на пару сотрудник/команда; при расхождении периодов берём
    # группу самого позднего периода участия.
    latest: dict[tuple[str, str], tuple[str, date]] = {}
    for emp_id, team, subgroup_id, joined_at in bind.execute(
        sa.select(et.c.employee_id, et.c.team, et.c.subgroup_id, et.c.joined_at).where(
            et.c.subgroup_id.isnot(None)
        )
    ):
        key = (emp_id, team)
        if group_team.get(subgroup_id) != team or key in done:
            continue
        joined = joined_at or date.min
        if key not in latest or joined >= latest[key][1]:
            latest[key] = (subgroup_id, joined)

    now = datetime.utcnow()
    if latest:
        op.bulk_insert(sh, [
            {
                "id": str(uuid.uuid4()), "employee_id": emp_id, "team": team,
                "valid_from": None, "subgroup_id": subgroup_id, "percent": 100,
                "created_at": now, "updated_at": now,
            }
            for (emp_id, team), (subgroup_id, _) in latest.items()
        ])


def downgrade() -> None:
    op.drop_index("ix_employee_subgroup_shares_subgroup_id", table_name=TABLE)
    op.drop_index("ix_employee_subgroup_shares_emp_team", table_name=TABLE)
    op.drop_table(TABLE)
