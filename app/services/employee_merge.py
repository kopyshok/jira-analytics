"""Объединение двух карточек одного человека.

После переезда на новую Jira часть людей списывает часы под другой учёткой,
чем та, к которой привязана их карточка: синк заводит вторую карточку без
команды и роли, и часы с неё выпадают из всех разрезов команды.

Объединение переносит на правильную карточку всё, что висит на лишней:
списания, комментарии, отсутствия, участие в командах и группах, личные
настройки, назначения и наблюдение в ресурсном планировании, снимки
сценариев, бэклог, учётку в задачах, отборе стола тимлида и утверждённых KPI.
Учётка лишней карточки запоминается (``EmployeeAccountAlias``) — синк
подставляет по ней правильного сотрудника и двойник больше не появляется.

Где у правильной карточки уже есть своя запись на тот же квартал, план или
блок (личные настройки, правки ёмкости, наблюдение, блоки графика), остаётся
её запись. Участие в командах не сливается молча: пересечение периодов в
одной команде или двух основных команд на одни даты — отказ с объяснением.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    Issue,
    KpiApproval,
    BacklogItem,
    Comment,
    Employee,
    EmployeeAccountAlias,
    EmployeeCapacityOverride,
    EmployeePersonalSetting,
    EmployeeSubgroupShare,
    EmployeeTeam,
    PlanConflict,
    ResourcePlanAssignment,
    ResourcePlanWatch,
    ScenarioAbsenceSnapshot,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioAllocationSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioNormSnapshot,
    ScenarioTeamSnapshot,
    ScheduledBlockEmployee,
    WorkDesk,
    Worklog,
)
from app.services import team_membership as tm
from app.services.subgroup_resolver import SubgroupResolver

# ponytail: переписывание учёток в задачах, бэклоге, отборе стола и снимках KPI
# уже написано для переезда на новую Jira — берём его, а не копию.
from app.services.jira_migration.apply import _rewrite_people_refs, _rowcount


logger = logging.getLogger(__name__)


class MergeError(ValueError):
    """Объединение невозможно — текст для пользователя."""


#: Колонки «id сотрудника» без ограничений уникальности: переносятся как есть.
_PLAIN_COLUMNS: list[tuple[Any, str, str]] = [
    (Worklog, "employee_id", "Списания"),
    (Comment, "author_id", "Комментарии"),
    (WorkDesk, "employee_id", "Ссылки «Стол аналитика»"),
    (BacklogItem, "assignee_employee_id", "Целевые задачи — исполнитель"),
    (BacklogItem, "developer_employee_id", "Целевые задачи — разработчик"),
    (ResourcePlanAssignment, "employee_id", "Назначения в ресурсном планировании"),
    (PlanConflict, "employee_id", "Конфликты ресурсного плана"),
    (ScenarioTeamSnapshot, "employee_id", "Снимки сценариев — состав"),
    (ScenarioCapacitySnapshot, "employee_id", "Снимки сценариев — ёмкость"),
    (ScenarioNormSnapshot, "employee_id", "Снимки сценариев — нормы"),
    (ScenarioAbsenceSnapshot, "employee_id", "Снимки сценариев — отсутствия"),
    (ScenarioAllocationSnapshot, "assignee_employee_id", "Снимки сценариев — исполнитель"),
    (ScenarioAllocationSnapshot, "developer_employee_id", "Снимки сценариев — разработчик"),
    (ScenarioAllocationBreakdownSnapshot, "employee_id", "Снимки сценариев — разбивка"),
]

#: Записи «на сотрудника в рамках X»: у правильной карточки своя запись главнее.
_SCOPED: list[tuple[Any, tuple[str, ...], str]] = [
    # Одно и то же отсутствие на обеих карточках вычлось бы из ёмкости дважды.
    (Absence, ("start_date", "end_date", "reason_id"), "Отсутствия"),
    (EmployeePersonalSetting, ("effective_year", "effective_quarter"), "Личные настройки по кварталам"),
    (EmployeeCapacityOverride, ("year", "quarter", "work_type_id"), "Правки ёмкости"),
    (ResourcePlanWatch, ("plan_id",), "Наблюдение за планами"),
    (ScheduledBlockEmployee, ("block_id",), "Блоки графика работ"),
]


def _overlaps(a: EmployeeTeam, b: EmployeeTeam) -> bool:
    return (a.joined_at or date.min) < (b.left_at or date.max) and (
        b.joined_at or date.min
    ) < (a.left_at or date.max)


def _period(row: EmployeeTeam) -> str:
    lo = row.joined_at.strftime("%d.%m.%Y") if row.joined_at else "начала"
    hi = row.left_at.strftime("%d.%m.%Y") if row.left_at else "сейчас"
    return f"с {lo} по {hi}"


def _team_blockers(db: Session, keep_id: str, drop_id: str) -> list[str]:
    keep_rows = db.query(EmployeeTeam).filter(EmployeeTeam.employee_id == keep_id).all()
    drop_rows = db.query(EmployeeTeam).filter(EmployeeTeam.employee_id == drop_id).all()
    blockers = []
    # Деление между группами считается от даты к дате на сотрудника: две истории
    # одной команды на одной карточке сложились бы в 200 % или перекрыли друг друга.
    shares: dict[str, set[str]] = defaultdict(set)
    for emp, team in db.query(EmployeeSubgroupShare.employee_id, EmployeeSubgroupShare.team).filter(
        EmployeeSubgroupShare.employee_id.in_([keep_id, drop_id])
    ):
        shares[team].add(emp)
    for team in sorted(t for t, emps in shares.items() if len(emps) == 2):
        blockers.append(
            f"У обеих карточек есть деление между группами команды «{team}». "
            "Оставьте его только у одной."
        )
    for d in drop_rows:
        for k in keep_rows:
            if k.team == d.team and _overlaps(k, d):
                blockers.append(
                    f"Обе карточки состоят в команде «{d.team}» на одни даты "
                    f"({_period(k)} и {_period(d)}). Оставьте участие только у одной."
                )
            elif k.team != d.team and k.is_primary and d.is_primary and _overlaps(k, d):
                blockers.append(
                    f"На одни даты основные команды разные: «{k.team}» и «{d.team}». "
                    "Оставьте основной только одну."
                )
    return blockers


def _load_pair(db: Session, keep_id: str, drop_id: str) -> tuple[Employee, Employee]:
    if keep_id == drop_id:
        raise MergeError("Выберите две разные карточки.")
    keep = db.get(Employee, keep_id)
    drop = db.get(Employee, drop_id)
    if keep is None or drop is None:
        raise MergeError("Карточка сотрудника не найдена — обновите страницу.")
    return keep, drop


def _count(db: Session, model: Any, column: str, employee_id: str) -> int:
    return db.query(func.count()).select_from(model).filter(
        getattr(model, column) == employee_id
    ).scalar() or 0


def _scoped_split(
    db: Session, model: Any, scope: tuple[str, ...], keep_id: str, drop_id: str,
) -> tuple[list[Any], list[Any]]:
    """Записи лишней карточки: (переезжают, уступают своей записи правильной)."""
    taken = {
        tuple(getattr(r, c) for c in scope)
        for r in db.query(model).filter(model.employee_id == keep_id)
    }
    move: list[Any] = []
    skip: list[Any] = []
    for row in db.query(model).filter(model.employee_id == drop_id).all():
        (skip if tuple(getattr(row, c) for c in scope) in taken else move).append(row)
    return move, skip


def _issue_refs(db: Session, account: str) -> int:
    return db.query(func.count(Issue.id)).filter(
        (Issue.assignee_account_id == account)
        | (Issue.reporter_account_id == account)
        | (Issue.developer_account_id == account)
    ).scalar() or 0


def _replace_employee_ids(node: Any, old: str, new: str) -> bool:
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "employee_id" and value == old:
                node[key] = new
                changed = True
            elif isinstance(value, (dict, list)):
                changed = _replace_employee_ids(value, old, new) or changed
    elif isinstance(node, list):
        for item in node:
            changed = _replace_employee_ids(item, old, new) or changed
    return changed


def _rewrite_kpi_employee_ids(db: Session, old: str, new: str) -> None:
    """Утверждённые KPI хранят id сотрудника рядом с учёткой — переписать и его."""
    for approval in db.query(KpiApproval).all():
        try:
            payload = json.loads(approval.payload_json)
        except (TypeError, ValueError):
            continue
        if _replace_employee_ids(payload, old, new):
            approval.payload_json = json.dumps(payload, ensure_ascii=False)


def card(db: Session, employee: Employee) -> dict[str, Any]:
    """Карточка для сравнения: по ней человек решает, какую оставить."""
    count, hours, first, last = db.query(
        func.count(Worklog.id), func.sum(Worklog.hours),
        func.min(Worklog.started_at), func.max(Worklog.started_at),
    ).filter(Worklog.employee_id == employee.id).one()
    today = date.today()
    teams = [
        r.team for r in db.query(EmployeeTeam).filter(EmployeeTeam.employee_id == employee.id)
        if (r.left_at is None or r.left_at > today)
    ]
    return {
        "id": employee.id,
        "display_name": employee.display_name,
        "jira_username": employee.jira_username,
        "email": employee.email,
        "is_active": bool(employee.is_active),
        "role": employee.role,
        "teams": sorted(set(teams)),
        "worklogs": int(count or 0),
        "hours": round(float(hours or 0), 1),
        "first_worklog": first.date().isoformat() if first else None,
        "last_worklog": last.date().isoformat() if last else None,
    }


def preview(db: Session, keep_id: str, drop_id: str) -> dict[str, Any]:
    """Что переедет и что мешает — без изменений в базе."""
    keep, drop = _load_pair(db, keep_id, drop_id)
    moves = []
    for model, column, label in _PLAIN_COLUMNS:
        n = _count(db, model, column, drop.id)
        if n:
            moves.append({"label": label, "count": n})
    for model, scope, label in _SCOPED:
        move, _ = _scoped_split(db, model, scope, keep.id, drop.id)
        if move:
            moves.append({"label": label, "count": len(move)})
    for model, label in (
        (EmployeeTeam, "Участие в командах"), (EmployeeSubgroupShare, "Группы внутри команд"),
    ):
        n = _count(db, model, "employee_id", drop.id)
        if n:
            moves.append({"label": label, "count": n})
    issues = _issue_refs(db, drop.jira_account_id)
    if issues:
        moves.append({"label": "Задачи Jira (исполнитель, автор, разработчик)", "count": issues})
    return {
        "keep": card(db, keep),
        "drop": card(db, drop),
        "moves": moves,
        "blockers": _team_blockers(db, keep.id, drop.id),
    }


def merge(db: Session, keep_id: str, drop_id: str) -> dict[str, Any]:
    """Влить карточку ``drop_id`` в ``keep_id`` и удалить её.

    Коммит — за вызывающим; пересчёт групп задач в конце может зафиксировать раньше.
    """
    keep, drop = _load_pair(db, keep_id, drop_id)
    blockers = _team_blockers(db, keep.id, drop.id)
    if blockers:
        raise MergeError(" ".join(blockers))

    moves: list[dict[str, Any]] = []

    def note(label: str, n: int) -> None:
        if n:
            moves.append({"label": label, "count": n})

    for model, column, label in _PLAIN_COLUMNS:
        col = getattr(model, column)
        note(label, _rowcount(db.execute(
            update(model).where(col == drop.id).values({column: keep.id})
        )))

    for model, scope, label in _SCOPED:
        move, skip = _scoped_split(db, model, scope, keep.id, drop.id)
        for row in skip:
            db.delete(row)
        for row in move:
            row.employee_id = keep.id
        note(label, len(move))

    drop_teams = {
        t for (t,) in db.query(EmployeeTeam.team).filter(EmployeeTeam.employee_id == drop.id)
    }

    note("Участие в командах", _rowcount(db.execute(
        update(EmployeeTeam).where(EmployeeTeam.employee_id == drop.id).values(employee_id=keep.id)
    )))
    note("Группы внутри команд", _rowcount(db.execute(
        update(EmployeeSubgroupShare)
        .where(EmployeeSubgroupShare.employee_id == drop.id)
        .values(employee_id=keep.id)
    )))

    refs, _ = _rewrite_people_refs(db, {drop.jira_account_id: keep.jira_account_id})
    note("Задачи Jira (исполнитель, автор, разработчик)", sum(
        refs.get(k, 0) for k in ("issues_assignee", "issues_reporter", "issues_developer")
    ))
    note("Отбор «Стола тимлида» у пользователей", refs.get("users_team_desk_filter", 0))
    note("Утверждённые KPI", refs.get("kpi_approvals", 0))
    _rewrite_kpi_employee_ids(db, drop.id, keep.id)

    # Карточку, слитую раньше в лишнюю, ведём сразу в правильную.
    db.execute(
        update(EmployeeAccountAlias)
        .where(EmployeeAccountAlias.employee_id == drop.id)
        .values(employee_id=keep.id)
    )
    alias = db.query(EmployeeAccountAlias).filter(
        EmployeeAccountAlias.jira_account_id == drop.jira_account_id
    ).one_or_none()
    if alias is None:
        db.add(EmployeeAccountAlias(jira_account_id=drop.jira_account_id, employee_id=keep.id))
    else:
        alias.employee_id = keep.id

    # ponytail: логин слитой учётки не хранится — второй проход синка ищет
    # списания по логину оставшейся; хватит, пока человек не пишет под старой.
    keep.jira_username = keep.jira_username or drop.jira_username
    keep.role = keep.role or drop.role
    keep.department = keep.department or drop.department
    keep.is_active = bool(keep.is_active or drop.is_active)
    db.flush()
    keep.team = tm.primary_team_on(db, keep.id, date.today())

    db.expunge(drop)
    db.execute(delete(Employee).where(Employee.id == drop.id))
    db.flush()
    # Группа задачи считается от её исполнителя — пересчитать команды лишней карточки.
    # Пересчёт сам фиксирует свои правки, поэтому он последний шаг объединения.
    resolver = SubgroupResolver(db)
    for team in sorted(drop_teams):
        resolver.recompute_effective(team)
    db.flush()
    logger.info(
        "Объединение сотрудников: %s (%s) влит в %s (%s): %s",
        drop.display_name, drop.jira_account_id, keep.display_name, keep.jira_account_id, moves,
    )
    return {"keep": card(db, keep), "moves": moves}


_WORD = re.compile(r"[^\wё-]+", re.IGNORECASE)


def _name_key(name: Optional[str]) -> Optional[str]:
    """Фамилия и имя без отчества и приписок, в любом порядке: «Медведева Надежда
    Владимировна» и «Надежда Медведева» дают один ключ. Для подсказки, не для
    решения — его принимает человек."""
    words = [w for w in _WORD.split((name or "").lower().replace("ё", "е")) if w]
    return " ".join(sorted(words[:2])) if len(words) >= 2 else None


def suggestions(db: Session) -> list[dict[str, Any]]:
    """Похожие карточки: одинаковые фамилия и имя, у двух и более есть данные.

    Первой в группе идёт карточка с самым свежим списанием (при равенстве — с
    большим числом часов): под ней человек работает сейчас, её разумно оставить.
    """
    groups: dict[str, list[Employee]] = defaultdict(list)
    for emp in db.query(Employee).all():
        key = _name_key(emp.display_name)
        if key:
            groups[key].append(emp)
    result = []
    for emps in groups.values():
        if len(emps) < 2:
            continue
        cards = [card(db, e) for e in emps]
        if sum(1 for c in cards if c["worklogs"] or c["teams"]) < 2:
            continue
        cards.sort(key=lambda c: (c["last_worklog"] or "", c["hours"]), reverse=True)
        result.append({"cards": cards})
    result.sort(key=lambda g: g["cards"][0]["display_name"])
    return result
