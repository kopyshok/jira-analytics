"""Служебные эпики (Дискавери внутри RFA) по умолчанию не в плане

Revision ID: pq01_service_epic_off_plan
Revises: td06a_issue_sprint_release
Create Date: 2026-09-23

Самодостаточна: не импортирует код приложения, только Core-SQL.
Правило first-match повторяет app/services/hierarchy_rules.py на дату миграции.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "pq01_service_epic_off_plan"
down_revision: Union[str, None] = "td06a_issue_sprint_release"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_rules = sa.table(
    "hierarchy_rule",
    sa.column("priority", sa.Integer),
    sa.column("created_at", sa.DateTime),
    sa.column("project_key", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("require_no_parent", sa.Boolean),
    sa.column("require_parent", sa.Boolean),
    sa.column("is_container", sa.Boolean),
    sa.column("is_enabled", sa.Boolean),
)
_items = sa.table(
    "backlog_items",
    sa.column("id", sa.String),
    sa.column("issue_id", sa.String),
    sa.column("included_in_planning", sa.Boolean),
)
_issues = sa.table(
    "issues",
    sa.column("id", sa.String),
    sa.column("project_id", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("parent_id", sa.String),
)
_projects = sa.table("projects", sa.column("id", sa.String), sa.column("key", sa.String))
_scenarios = sa.table("planning_scenarios", sa.column("id", sa.String), sa.column("status", sa.String))
_allocs = sa.table(
    "scenario_allocations",
    sa.column("scenario_id", sa.String),
    sa.column("backlog_item_id", sa.String),
)

_CHUNK = 500


def _first_match(rules, project_key: str, issue_type: str):
    """Первое подошедшее правило для задачи С родителем."""
    for r in rules:
        if r.project_key and r.project_key != project_key:
            continue
        if r.issue_type and r.issue_type != issue_type:
            continue
        if r.require_no_parent:
            continue
        return r
    return None


def upgrade() -> None:
    bind = op.get_bind()
    rules = bind.execute(
        sa.select(
            _rules.c.project_key,
            _rules.c.issue_type,
            _rules.c.require_no_parent,
            _rules.c.require_parent,
            _rules.c.is_container,
        )
        .where(_rules.c.is_enabled.is_(True))
        .order_by(_rules.c.priority.asc(), _rules.c.created_at.asc())
    ).fetchall()
    if not any(r.require_parent and not r.is_container for r in rules):
        return

    rows = bind.execute(
        sa.select(_items.c.id, _projects.c.key, _issues.c.issue_type)
        .select_from(
            _items.join(_issues, _items.c.issue_id == _issues.c.id)
            .outerjoin(_projects, _issues.c.project_id == _projects.c.id)
        )
        .where(_issues.c.parent_id.isnot(None))
    ).fetchall()
    ids = []
    for item_id, project_key, issue_type in rows:
        rule = _first_match(rules, project_key or "", issue_type or "")
        if rule is not None and rule.require_parent and not rule.is_container:
            ids.append(item_id)

    draft_ids = sa.select(_scenarios.c.id).where(_scenarios.c.status == "draft")
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        bind.execute(
            sa.update(_items).where(_items.c.id.in_(chunk)).values(included_in_planning=False)
        )
        bind.execute(
            sa.delete(_allocs).where(
                _allocs.c.backlog_item_id.in_(chunk),
                _allocs.c.scenario_id.in_(draft_ids),
            )
        )


def downgrade() -> None:
    # Прежнее значение галочки не сохранялось; «включено» вернёт Дискавери в
    # кандидаты сверх RFA, что хуже — оставляем как есть.
    pass
