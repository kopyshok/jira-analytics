"""employee_teams.subgroup_id удалена: группа сотрудника — в employee_subgroup_shares

Revision ID: sg02_drop_employee_team_subgroup
Revises: sg01_subgroup_shares
Create Date: 2026-09-29

Самодостаточна: не импортирует код приложения. Колонки может не быть
(dev-база от create_all). Безымянный внешний ключ (SQLite, таблица от
create_all) пересоздание таблицы в batch-режиме отбрасывает вместе с колонкой.
"""
from datetime import date
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sg02_drop_employee_team_subgroup"
down_revision: Union[str, None] = "sg01_subgroup_shares"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists() -> bool:
    if context.is_offline_mode():
        return True
    cols = sa.inspect(op.get_bind()).get_columns("employee_teams")
    return any(c["name"] == "subgroup_id" for c in cols)


def upgrade() -> None:
    if not _column_exists():
        return
    fk_names: list[str] = []
    index_names: list[str] = []
    if not context.is_offline_mode():
        insp = sa.inspect(op.get_bind())
        fk_names = [
            fk["name"] for fk in insp.get_foreign_keys("employee_teams")
            if fk.get("constrained_columns") == ["subgroup_id"] and fk.get("name")
        ]
        index_names = [
            ix["name"] for ix in insp.get_indexes("employee_teams")
            if ix.get("column_names") == ["subgroup_id"]
        ]
    with op.batch_alter_table("employee_teams", schema=None) as batch_op:
        for name in fk_names:
            batch_op.drop_constraint(name, type_="foreignkey")
        for name in index_names:
            batch_op.drop_index(name)
        batch_op.drop_column("subgroup_id")


def downgrade() -> None:
    with op.batch_alter_table("employee_teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subgroup_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_employee_teams_subgroup_id", ["subgroup_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_employee_teams_subgroup", "team_subgroups",
            ["subgroup_id"], ["id"], ondelete="SET NULL",
        )
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    sh = sa.table(
        "employee_subgroup_shares",
        sa.column("employee_id", sa.String), sa.column("team", sa.String),
        sa.column("valid_from", sa.Date), sa.column("subgroup_id", sa.String),
        sa.column("percent", sa.Integer),
    )
    et = sa.table(
        "employee_teams",
        sa.column("employee_id", sa.String), sa.column("team", sa.String),
        sa.column("subgroup_id", sa.String),
    )
    for (emp_id, team), subgroup_id in _groups_today(bind, sh).items():
        bind.execute(
            et.update()
            .where(et.c.employee_id == emp_id, et.c.team == team)
            .values(subgroup_id=subgroup_id)
        )


def _groups_today(bind, sh) -> dict:
    """(сотрудник, команда) → группа для колонки: та, что действует сегодня.

    Сегодня целиком в одной группе — она; поделён — группа с наибольшей долей
    в сегодняшней записи; сегодня записи ещё нет (все с будущих дат) —
    наибольшая доля первой записи. При равных долях — меньший id группы.
    Колонка держит одну группу, поэтому история переводов и деление теряются.
    """
    today = date.today()
    records: dict = {}  # (сотрудник, команда) → {valid_from: [(процент, группа)]}
    for emp_id, team, valid_from, subgroup_id, percent in bind.execute(
        sa.select(sh.c.employee_id, sh.c.team, sh.c.valid_from, sh.c.subgroup_id, sh.c.percent)
    ).all():
        if isinstance(valid_from, str):
            valid_from = date.fromisoformat(valid_from[:10])
        records.setdefault((emp_id, team), {}).setdefault(valid_from, []).append(
            (int(percent), subgroup_id)
        )
    out: dict = {}
    for key, by_date in records.items():
        starts = sorted(by_date, key=lambda d: d or date.min)
        started = [d for d in starts if d is None or d <= today]
        shares = by_date[started[-1] if started else starts[0]]
        out[key] = min(shares, key=lambda s: (-s[0], s[1]))[1]
    return out
