"""Снять вовлечённость, вписанную в задачи при утверждении сценария

Revision ID: iv01_clear_frozen_involvement
Revises: ob01_onboarding
Create Date: 2026-09-30

Утверждение копировало процент справочника команды в задачу, и дальше он
перекрывал справочник: правка справочника до фаз не доходила. Теперь справочник
подставляется при расчёте, а записанные копии убираются — у включённых задач
утверждённых сценариев по ролям, для которых справочник команды действует на
квартал сценария. Значение из Jira не трогается. Ручная правка процента у этих
задач неотличима от копии и тоже снимается. Самодостаточна: не импортирует код
приложения.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "iv01_clear_frozen_involvement"
down_revision: Union[str, None] = "ob01_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Роль справочника → поле вовлечённости задачи (и задачи Jira).
ROLE_FIELD = {
    "analyst": "involvement_analyst",
    "dev": "involvement_dev",
    "qa": "involvement_qa",
    "opo": "involvement_launch",
}

defaults = sa.table(
    "involvement_defaults",
    sa.column("team"), sa.column("role"),
    sa.column("effective_year"), sa.column("effective_quarter"),
)
scenarios = sa.table(
    "planning_scenarios",
    sa.column("id"), sa.column("team"), sa.column("year"), sa.column("quarter"),
)
revisions = sa.table("scenario_revisions", sa.column("scenario_id"))
allocations = sa.table(
    "scenario_allocations",
    sa.column("scenario_id"), sa.column("backlog_item_id"),
    sa.column("included_flag", sa.Boolean),
)
items = sa.table(
    "backlog_items", sa.column("id"), sa.column("issue_id"),
    *(sa.column(f) for f in ROLE_FIELD.values()),
)
issues = sa.table("issues", sa.column("id"), *(sa.column(f) for f in ROLE_FIELD.values()))


def _quarter(value) -> Union[int, None]:
    try:
        q = int(str(value or "").strip().upper().lstrip("Q"))
    except ValueError:
        return None
    return q if 1 <= q <= 4 else None


def upgrade() -> None:
    bind = op.get_bind()
    refs = bind.execute(sa.select(
        defaults.c.team, defaults.c.role, defaults.c.effective_year, defaults.c.effective_quarter,
    )).all()
    approved = bind.execute(
        sa.select(scenarios.c.id, scenarios.c.team, scenarios.c.year, scenarios.c.quarter)
        .where(scenarios.c.id.in_(sa.select(revisions.c.scenario_id)))
    ).all()
    for sc_id, team, year, quarter in approved:
        q = _quarter(quarter)
        if not team or year is None or q is None:
            continue
        roles = {
            role for r_team, role, r_year, r_q in refs
            if r_team == team and role in ROLE_FIELD and (r_year, r_q) <= (year, q)
        }
        included = sa.select(allocations.c.backlog_item_id).where(
            allocations.c.scenario_id == sc_id,
            allocations.c.included_flag == sa.true(),
        )
        for role in roles:
            field = ROLE_FIELD[role]
            jira_value = (
                sa.select(issues.c[field])
                .where(issues.c.id == items.c.issue_id)
                .scalar_subquery()
            )
            bind.execute(
                items.update()
                .where(
                    items.c.id.in_(included),
                    items.c[field].is_not(None),
                    jira_value.is_(None),
                )
                .values({field: None})
            )


def downgrade() -> None:
    # Снятые копии не восстанавливаются: их значение и есть справочник.
    pass
