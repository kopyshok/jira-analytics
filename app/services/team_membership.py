"""Состав команды на дату — единая точка расчёта.

Участие сотрудника в команде периодизовано: ``joined_at`` — первый день
в команде (``None`` = «был всегда»), ``left_at`` — первый день ВНЕ команды
(``None`` = «состоит сейчас»). Полуинтервал ``[joined_at, left_at)``.

Одна пара сотрудник/команда может иметь несколько непересекающихся
периодов (ушёл — вернулся).

Все функции — чистое чтение, без commit. Любой код, которому нужен состав
команды, обязан идти сюда, а не запрашивать ``EmployeeTeam`` напрямую:
иначе выбывшие снова начнут попадать в расчёты задним числом.
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable, Optional, Sequence

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models import EmployeeTeam


def active_on_clause(day: date):
    """SQLAlchemy-условие «участие активно в этот день»."""
    return (
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= day),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > day),
    )


def overlaps_clause(start: date, end: date):
    """SQLAlchemy-условие «участие пересекается с периодом [start, end]»."""
    return (
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= end),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > start),
    )


def members_on(db: Session, teams: Sequence[str], day: date) -> set[str]:
    """ID сотрудников, состоящих в любой из команд в указанный день."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)), *active_on_clause(day))
        .all()
    )
    return {r[0] for r in rows}


def members_overlapping(
    db: Session, teams: Sequence[str], start: date, end: date
) -> set[str]:
    """ID сотрудников, состоявших в командах хотя бы один день периода."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)), *overlaps_clause(start, end))
        .all()
    )
    return {r[0] for r in rows}


def members_ever(db: Session, teams: Sequence[str]) -> set[str]:
    """ID всех, кто когда-либо состоял в командах (включая выбывших)."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)))
        .all()
    )
    return {r[0] for r in rows}


def member_intervals(
    db: Session, teams: Sequence[str], start: date, end: date
) -> dict[str, list[tuple[date, date]]]:
    """Отрезки участия внутри периода, обрезанные его границами.

    Обе границы возвращаемых отрезков ВКЛЮЧИТЕЛЬНЫЕ — так удобнее для
    посуточных циклов. Отрезки одного сотрудника отсортированы по началу.
    """
    if not teams:
        return {}
    rows = (
        db.query(EmployeeTeam.employee_id, EmployeeTeam.joined_at, EmployeeTeam.left_at)
        .filter(EmployeeTeam.team.in_(list(teams)), *overlaps_clause(start, end))
        .all()
    )
    out: dict[str, list[tuple[date, date]]] = {}
    for emp_id, joined, left in rows:
        lo = max(joined, start) if joined else start
        hi = min(left - timedelta(days=1), end) if left else end
        if lo > hi:
            continue
        out.setdefault(emp_id, []).append((lo, hi))
    for intervals in out.values():
        intervals.sort()
    return out


def intervals_by_team(
    db: Session, teams: Sequence[str], start: date, end: date
) -> dict[str, dict[str, list[tuple[date, date]]]]:
    """То же, что ``member_intervals``, но отрезки разложены по командам.

    Нужно там, где в одном расчёте участвуют несколько команд со своим
    составом каждая (сводка портфеля проектов): общий словарь склеил бы
    участие в разных командах в один отрезок.
    """
    if not teams:
        return {}
    rows = (
        db.query(
            EmployeeTeam.team,
            EmployeeTeam.employee_id,
            EmployeeTeam.joined_at,
            EmployeeTeam.left_at,
        )
        .filter(EmployeeTeam.team.in_(list(teams)), *overlaps_clause(start, end))
        .all()
    )
    out: dict[str, dict[str, list[tuple[date, date]]]] = {}
    for team, emp_id, joined, left in rows:
        lo = max(joined, start) if joined else start
        hi = min(left - timedelta(days=1), end) if left else end
        if lo > hi:
            continue
        out.setdefault(team, {}).setdefault(emp_id, []).append((lo, hi))
    for per_emp in out.values():
        for intervals in per_emp.values():
            intervals.sort()
    return out


def day_in_intervals(day: date, intervals: Iterable[tuple[date, date]]) -> bool:
    """Попадает ли день в один из отрезков (границы включительно)."""
    return any(lo <= day <= hi for lo, hi in intervals)


def membership_rows(
    db: Session, employee_ids: Sequence[str]
) -> dict[str, list[tuple[str, Optional[date], Optional[date], bool]]]:
    """Все периоды участия перечисленных сотрудников — одним запросом.

    Нужно там, где у каждого сотрудника своя дата (например, подпись команды
    на день последнего списания): ходить в БД на каждого — N+1.
    """
    if not employee_ids:
        return {}
    rows = (
        db.query(
            EmployeeTeam.employee_id,
            EmployeeTeam.team,
            EmployeeTeam.joined_at,
            EmployeeTeam.left_at,
            EmployeeTeam.is_primary,
        )
        .filter(EmployeeTeam.employee_id.in_(list(employee_ids)))
        .all()
    )
    out: dict[str, list[tuple[str, Optional[date], Optional[date], bool]]] = {}
    for emp_id, team, joined, left, is_primary in rows:
        out.setdefault(emp_id, []).append((team, joined, left, bool(is_primary)))
    return out


def team_on_day(
    rows: Iterable[tuple[str, Optional[date], Optional[date], bool]], day: date
) -> Optional[str]:
    """Команда сотрудника на указанный день: основная, иначе первая по алфавиту."""
    active = [
        (team, is_primary)
        for team, joined, left, is_primary in rows
        if (joined is None or joined <= day) and (left is None or left > day)
    ]
    if not active:
        return None
    primary = [t for t, is_primary in active if is_primary]
    if primary:
        return sorted(primary)[0]
    return sorted(t for t, _ in active)[0]


def primary_team_on(db: Session, employee_id: str, day: date) -> Optional[str]:
    """Основная команда сотрудника на указанный день."""
    row = (
        db.query(EmployeeTeam.team)
        .filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.is_primary == True,  # noqa: E712
            *active_on_clause(day),
        )
        .first()
    )
    return row[0] if row else None


def shared_members(
    db: Session, teams: Sequence[str], start: date, end: date
) -> dict[str, list[str]]:
    """Кто из состава команд пересекается с ДРУГИМИ командами за период.

    Возвращает ``employee_id -> отсортированный список чужих команд``.
    Сотрудники без пересечений в результат не попадают.
    """
    emp_ids = members_overlapping(db, teams, start, end)
    if not emp_ids:
        return {}
    rows = (
        db.query(EmployeeTeam.employee_id, EmployeeTeam.team)
        .filter(
            EmployeeTeam.employee_id.in_(list(emp_ids)),
            EmployeeTeam.team.notin_(list(teams)),
            *overlaps_clause(start, end),
        )
        .all()
    )
    out: dict[str, set[str]] = {}
    for emp_id, team in rows:
        out.setdefault(emp_id, set()).add(team)
    return {k: sorted(v) for k, v in out.items()}


def month_membership_share(
    db: Session, teams: Sequence[str], employee_id: str, year: int, month: int
) -> float:
    """Доля нормо-часов месяца, приходящаяся на дни участия в командах.

    1.0 — состоял весь месяц, 0.0 — ни дня. Используется там, где помесячные
    часы считаются сервисом без знания о командах (снимок утверждения и
    сравнение с ним) — чтобы обе стороны сравнения резались одинаково.

    Норма дня берётся из производственного календаря; если записи нет —
    8 ч Пн–Пт, 0 в выходные (тот же фолбэк, что в остальных расчётах).
    """
    from app.models import ProductionCalendarDay

    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    cal = {
        row.date: float(row.hours)
        for row in db.query(ProductionCalendarDay).filter(
            ProductionCalendarDay.date >= month_start,
            ProductionCalendarDay.date <= month_end,
        ).all()
    }

    def day_norm(d: date) -> float:
        if d in cal:
            return cal[d]
        return 8.0 if d.weekday() < 5 else 0.0

    intervals = member_intervals(db, teams, month_start, month_end).get(employee_id, [])
    total = 0.0
    inside = 0.0
    cur = month_start
    while cur <= month_end:
        norm = day_norm(cur)
        total += norm
        if norm > 0 and day_in_intervals(cur, intervals):
            inside += norm
        cur += timedelta(days=1)

    if total <= 0:
        return 1.0
    return min(1.0, inside / total)


def membership_on_column_exists(teams: Sequence[str], employee_col, date_col):
    """EXISTS-условие «сотрудник был в одной из команд на дату строки».

    ``employee_col`` — колонка с id сотрудника (например ``Worklog.employee_id``),
    ``date_col`` — колонка с датой события (``Worklog.started_at``).

    Сравнение Date с DateTime корректно и в SQLite (лексикографически по ISO),
    и в PostgreSQL (неявный каст даты к полуночи): день ``left_at`` уже НЕ
    засчитывается, потому что ``left_at > started_at`` ложно для любого времени
    внутри этого дня.
    """
    return exists().where(
        EmployeeTeam.employee_id == employee_col,
        EmployeeTeam.team.in_(list(teams)),
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= date_col),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > date_col),
    )


def has_any_membership_on(employee_col, date_col):
    """EXISTS-условие «на эту дату сотрудник состоял хоть в какой-то команде».

    Нужно для ветки «Без команды»: без даты выбывший задним числом становился бы
    «без команды» за всю историю.
    """
    return exists().where(
        EmployeeTeam.employee_id == employee_col,
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= date_col),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > date_col),
    )
