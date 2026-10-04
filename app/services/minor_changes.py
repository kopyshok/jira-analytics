"""Минорные изменения команд: сводка для «Целевых задач» (чистое чтение).

Минорная задача — задача, чья эффективная категория (своя или унаследованная
от родителей, как её определяет ``CategoryResolver``) относится к виду работ
«Минорные изменения» (``minor_change``). Считаем только открытые: не «Готово»
и не отменённые. Часы — только оценки задач по ролям (те же, что у целевых
задач); задача без оценки считается штуками, часы не додумываем.

Чтобы не задвоить, считаем «листья»: оценённые подзадачи заменяют родителя;
если оценка только у родителя — считается родитель.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Issue, MandatoryWorkType
from app.services.backlog_service import CANCEL_STATUSES
from app.services.category_resolver import CategoryResolver
from app.services.hierarchy_rules import _first_match, load_rules
from app.services.normed_reserve import team_reserve

MINOR_WORK_TYPE_CODE = "minor_change"
ROLES = ("analyst", "dev", "qa", "opo")
_EPIC_TYPES = frozenset({"epic", "эпик"})
_IN_CHUNK = 500


def _minor_category_codes(db: Session) -> set[str]:
    rows = db.execute(
        select(Category.code)
        .join(MandatoryWorkType, MandatoryWorkType.id == Category.work_type_id)
        .where(MandatoryWorkType.code == MINOR_WORK_TYPE_CODE)
    ).scalars()
    return set(rows)


def _prefetch_ancestors(db: Session, issues: Iterable[Issue]) -> None:
    """Подгрузить родителей пачками по уровням: резолвер ходит вверх через
    ``db.get`` и берёт их из сессии без запроса на каждый шаг."""
    seen = {i.id for i in issues}
    frontier = {i.parent_id for i in issues if i.parent_id} - seen
    while frontier:
        ids = sorted(frontier)
        loaded: list[Issue] = []
        for start in range(0, len(ids), _IN_CHUNK):
            loaded += db.execute(
                select(Issue).where(Issue.id.in_(ids[start : start + _IN_CHUNK]))
            ).scalars().all()
        seen |= frontier
        frontier = {i.parent_id for i in loaded if i.parent_id} - seen


def _is_container(rules: list, issue: Issue) -> bool:
    """Контейнер (эпик и т.п.) — не задача. Решают правила иерархии
    (проект + тип задачи); если ни одно не подошло — эпик Jira."""
    rule = _first_match(
        rules, issue.project.key if issue.project else "", issue.issue_type or "",
        issue.parent_id is not None,
    )
    if rule is not None:
        return bool(rule.is_container)
    return (issue.issue_type or "").lower() in _EPIC_TYPES


def _role_hours(issue: Issue) -> Dict[str, Optional[float]]:
    return {r: getattr(issue, f"planned_{r}_hours") for r in ROLES}


def _is_estimated(issue: Issue) -> bool:
    return any(v for v in _role_hours(issue).values())


def _units(issues: List[Issue]) -> List[Issue]:
    """Листья: единицы подсчёта без задвоения родителя и подзадач."""
    ids = {i.id for i in issues}
    children: Dict[str, List[Issue]] = defaultdict(list)
    for i in issues:
        if i.parent_id in ids:
            children[i.parent_id].append(i)
    memo: Dict[str, bool] = {}

    def has_estimated_descendant(node: Issue) -> bool:
        if node.id not in memo:
            memo[node.id] = False  # защита от петли в данных
            memo[node.id] = any(
                _is_estimated(c) or has_estimated_descendant(c) for c in children[node.id]
            )
        return memo[node.id]

    def units_of(node: Issue) -> List[Issue]:
        kids = children[node.id]
        if not kids:
            return [node]
        if not has_estimated_descendant(node) and _is_estimated(node):
            return [node]
        return [u for c in kids for u in units_of(c)]

    roots = [i for i in issues if i.parent_id not in ids]
    return [u for r in roots for u in units_of(r)]


def _epic_of(db: Session, issue: Issue) -> Optional[Issue]:
    """Ближайший предок-эпик."""
    current, hops = db.get(Issue, issue.parent_id) if issue.parent_id else None, 0
    while current is not None and hops < 20:
        if (current.issue_type or "").lower() in _EPIC_TYPES:
            return current
        current = db.get(Issue, current.parent_id) if current.parent_id else None
        hops += 1
    return None


def _reserve_hours(
    db: Session, team: str, year: int, quarter: int, wt_id: Optional[str]
) -> Optional[float]:
    """Заложено на квартал на минорные изменения; ``None`` — правил нет."""
    reserve = team_reserve(db, team, year, quarter)
    if reserve is None:
        return None
    total = sum(
        row.planned for rows in reserve.roles.values() for row in rows if row.work_type_id == wt_id
    )
    return round(total, 1) if total > 0 else None


def _block(
    db: Session, team: str, units: List[Issue], year: int, quarter: int, wt_id: Optional[str]
) -> Dict[str, Any]:
    totals = {r: 0.0 for r in ROLES}
    tasks = []
    estimated = 0
    for issue in sorted(units, key=lambda i: i.key):
        hours = _role_hours(issue)
        if _is_estimated(issue):
            estimated += 1
            for r in ROLES:
                totals[r] += hours[r] or 0.0
        epic = _epic_of(db, issue)
        tasks.append({
            "key": issue.key,
            "title": issue.summary,
            "status": issue.status,
            "assignee": issue.assignee_display_name,
            "hours": hours,
            "epic_key": epic.key if epic else None,
            "epic_summary": epic.summary if epic else None,
        })
    totals = {r: round(v, 2) for r, v in totals.items()}
    return {
        "team": team,
        "open_count": len(units),
        "estimated_count": estimated,
        "unestimated_count": len(units) - estimated,
        "hours": {**totals, "total": round(sum(totals.values()), 2)},
        "reserve_hours": _reserve_hours(db, team, year, quarter, wt_id),
        "tasks": tasks,
    }


def minor_changes_summary(
    db: Session, teams: Optional[List[str]], year: int, quarter: int
) -> List[Dict[str, Any]]:
    """Блок на каждую команду (``teams``; без списка — на каждую команду, где
    есть минорные задачи). ``year``/``quarter`` — квартал запаса."""
    codes = _minor_category_codes(db)
    by_team: Dict[str, List[Issue]] = defaultdict(list)
    if codes:
        query = select(Issue).where(
            func.coalesce(Issue.status_category, "") != "done",
            Issue.status.notin_(list(CANCEL_STATUSES)),
        )
        query = query.where(Issue.team.in_(teams)) if teams else query.where(Issue.team.isnot(None))
        candidates = db.execute(query).scalars().all()
        _prefetch_ancestors(db, candidates)
        resolver = CategoryResolver(db)
        rules = load_rules(db)
        for issue in candidates:
            if (
                resolver.resolve_for_issue(issue).category_code in codes
                and not _is_container(rules, issue)
            ):
                by_team[issue.team].append(issue)
    names = list(dict.fromkeys(teams)) if teams else sorted(by_team)
    wt_id = db.execute(
        select(MandatoryWorkType.id).where(MandatoryWorkType.code == MINOR_WORK_TYPE_CODE)
    ).scalar_one_or_none()
    return [_block(db, t, _units(by_team.get(t, [])), year, quarter, wt_id) for t in names]
