"""Фактическая вовлечённость аналитиков и разработчиков команды.

Факт = часы списаний на задачах вида работ «Проекты и развитие» ÷ все
списанные часы человека за период. Рядом — «списано от нормы» = все списанные
÷ норма (календарь минус отсутствия): если списано мало, факту верить нельзя.

- Вид работ задачи — по её категории (``Issue.category`` уже с наследованием
  от родителя) через общую карту ``categories.get_category_work_types`` — та же,
  что у дашборда нормированных работ. Задачи, исключённые из анализа, не
  учитываются вовсе, как во всей аналитике.
- Команда — по участию на дату списания (``team_membership``); норма — за дни
  участия в команде (``CapacityService.team_quarter_capacity``).
- Роли — аналитик и разработчик по роли сотрудника; без роли не показываем.
- Итог роли — Σ проектных ÷ Σ всех, не среднее процентов людей.

Чистое чтение. Списания читаются одним запросом на все команды; норма —
константа запросов на команду.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models import Employee, Issue, MandatoryWorkType, Worklog
from app.services import team_membership as tm
from app.services.capacity_service import QUARTER_MONTHS, CapacityService
from app.services.categories import get_category_work_types
from app.services.plan_common import quarter_bounds

# Роли сотрудника в порядке показа; коды совпадают с ролями справочника
# вовлечённости («Анализ», «Разработка»).
FACT_ROLES: tuple[str, ...] = ("analyst", "dev")
PROJECT_WORK_TYPE = "project"


@dataclass
class FactCell:
    """Часы за период: проектные, все списанные и норма."""

    project_hours: float = 0.0
    logged_hours: float = 0.0
    norm_hours: float = 0.0

    @property
    def fact(self) -> Optional[float]:
        """Доля проектных часов в списанных; нет списаний — нет факта."""
        return self.project_hours / self.logged_hours if self.logged_hours > 0 else None

    @property
    def logged_of_norm(self) -> Optional[float]:
        """Доля списанного от нормы; нормы нет — нет значения."""
        return self.logged_hours / self.norm_hours if self.norm_hours > 0 else None

    def add(self, other: "FactCell") -> None:
        self.project_hours += other.project_hours
        self.logged_hours += other.logged_hours
        self.norm_hours += other.norm_hours


def _empty_months(months: Sequence[int]) -> dict[int, FactCell]:
    return {m: FactCell() for m in months}


@dataclass
class PersonFact:
    employee_id: str
    name: str
    role: str
    months: dict[int, FactCell]
    total: FactCell = field(default_factory=FactCell)


@dataclass
class RoleFact:
    role: str
    people: int
    months: dict[int, FactCell]
    total: FactCell = field(default_factory=FactCell)


@dataclass
class TeamFact:
    team: str
    people: list[PersonFact] = field(default_factory=list)
    roles: list[RoleFact] = field(default_factory=list)


def last_completed_quarter(today: date) -> tuple[int, int]:
    """Последний завершённый квартал относительно ``today``."""
    quarter = (today.month - 1) // 3 + 1
    return (today.year, quarter - 1) if quarter > 1 else (today.year - 1, 4)


def team_facts(
    db: Session, teams: Sequence[str], year: int, quarter: int,
) -> list[TeamFact]:
    """Фактическая вовлечённость по командам за квартал: люди и итог по ролям."""
    teams = list(dict.fromkeys(teams))
    months = QUARTER_MONTHS[quarter]
    start, end = quarter_bounds(year, quarter)

    intervals = tm.intervals_by_team(db, teams, start, end)
    candidate_ids = {eid for by_emp in intervals.values() for eid in by_emp}
    employees = (
        db.query(Employee).filter(Employee.id.in_(candidate_ids)).all()
        if candidate_ids else []
    )
    role_of = {
        e.id: role
        for e in employees
        if (role := (e.role or "").strip().lower()) in FACT_ROLES
    }
    by_id = {e.id: e for e in employees if e.id in role_of}
    if not role_of:
        return [TeamFact(team=t) for t in teams]

    # Часы по (команда, сотрудник, месяц) — один проход по списаниям квартала.
    project_wt_ids = {
        wt_id for (wt_id,) in db.query(MandatoryWorkType.id)
        .filter(MandatoryWorkType.code == PROJECT_WORK_TYPE)
    }
    project_categories = {
        code for code, wt_id in get_category_work_types(db).items()
        if wt_id in project_wt_ids
    }
    cells: dict[str, dict[str, dict[int, FactCell]]] = {t: {} for t in teams}
    rows = (
        db.query(Worklog.employee_id, Worklog.started_at, Worklog.hours, Issue.category)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(
            Worklog.employee_id.in_(list(role_of)),
            Worklog.started_at >= datetime.combine(start, time.min),
            Worklog.started_at < datetime.combine(end + timedelta(days=1), time.min),
            Issue.include_in_analysis.is_(True),
        )
        .all()
    )
    for emp_id, started_at, hours, category in rows:
        day = started_at.date()
        is_project = category in project_categories
        for team in teams:
            spans = intervals.get(team, {}).get(emp_id)
            if not spans or not tm.day_in_intervals(day, spans):
                continue
            cell = cells[team].setdefault(emp_id, _empty_months(months))[started_at.month]
            cell.logged_hours += hours
            if is_project:
                cell.project_hours += hours

    capacity = CapacityService(db)
    out: list[TeamFact] = []
    for team in teams:
        member_ids = [eid for eid in intervals.get(team, {}) if eid in role_of]
        if not member_ids:
            out.append(TeamFact(team=team))
            continue
        # Норма — за дни участия в этой команде, минус отсутствия.
        norm = {
            qc.employee_id: {mc.month: mc.available_hours for mc in qc.months}
            for qc in capacity.team_quarter_capacity(
                year, quarter, employee_ids=member_ids, teams_filter=[team],
            )
        }
        people: list[PersonFact] = []
        for eid in member_ids:
            by_month = cells[team].get(eid) or _empty_months(months)
            for m in months:
                by_month[m].norm_hours = norm.get(eid, {}).get(m, 0.0)
            person = PersonFact(
                employee_id=eid, name=by_id[eid].display_name, role=role_of[eid],
                months=by_month,
            )
            for c in by_month.values():
                person.total.add(c)
            # Ушедший из компании без единого списания — не строка отчёта.
            if person.total.logged_hours <= 0 and not (
                by_id[eid].is_active and person.total.norm_hours > 0
            ):
                continue
            people.append(person)
        people.sort(key=lambda p: (FACT_ROLES.index(p.role), p.name))

        roles: list[RoleFact] = []
        for role in FACT_ROLES:
            group = [p for p in people if p.role == role]
            if not group:
                continue
            agg = RoleFact(role=role, people=len(group), months=_empty_months(months))
            for p in group:
                for m in months:
                    agg.months[m].add(p.months[m])
                agg.total.add(p.total)
            roles.append(agg)
        out.append(TeamFact(team=team, people=people, roles=roles))
    return out
