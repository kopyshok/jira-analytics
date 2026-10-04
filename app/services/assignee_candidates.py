"""Кандидаты в исполнители — общая функция для фазы плана и строки сценария.

Кандидат — активный сотрудник, состоявший хоть в какой-то команде хотя бы
день квартала (боты и люди вне команд не попадают). Группы: «Из Jira» (кого
показать, решает вызывающий), «Моя команда» (состав команды за квартал),
«Другие команды». У каждого — загрузка за квартал по опорным планам всех
команд. Для фазы плана — честнее: загрузка с нормированными работами основной
команды и свободные часы в даты фазы, внутри группы — самые свободные сверху.
Пустые группы не возвращаются. Чистое чтение.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue
from app.services import cross_team_occupancy as cto
from app.services import normed_reserve as nr
from app.services import team_membership as tm


@dataclass
class Candidate:
    """Кандидат в исполнители."""

    employee_id: str
    display_name: str
    role: Optional[str]
    team: Optional[str]
    # Загрузка за квартал по всем опорным планам команд, %.
    load_pct: float
    # Границы участия в команде внутри квартала; None — край покрыт.
    member_from: Optional[date]
    member_to: Optional[date]
    # Свободно в даты фазы, ч; None — считается только для фазы плана.
    free_hours: Optional[float] = None


@dataclass
class CandidateGroup:
    """Группа кандидатов: key — "jira" | "team" | "other"."""

    key: str
    label: str
    employees: List[Candidate]


def candidate_groups(
    db: Session,
    *,
    team: Optional[str],
    start: date,
    end: date,
    year: Optional[int],
    quarter: Optional[int],
    jira_employee_id: Optional[str],
    phase_window: Optional[tuple[date, date]] = None,
    skip_booking: Optional[Callable[[cto.ExternalBooking], bool]] = None,
) -> List[CandidateGroup]:
    """Все, кто в квартале ``start`` — ``end`` состоит в какой-либо команде, группами.

    ``team`` — команда группы «Моя команда»; ``jira_employee_id`` — кого
    показать в группе «Из Jira» (если он среди кандидатов). Загрузка
    считается, только если известны год и квартал.

    ``phase_window`` — даты фазы плана: тогда загрузка — с нормированными
    работами (`free_load`), у кандидата — свободные часы в эти даты, и внутри
    группы самые свободные сверху. ``skip_booking`` — брони, которые не
    занимают кандидата (сама эта фаза).
    """
    employees = list(
        db.execute(
            select(Employee).where(
                Employee.is_active == True,  # noqa: E712
                exists().where(
                    EmployeeTeam.employee_id == Employee.id,
                    *tm.overlaps_clause(start, end),
                ),
            )
        )
        .scalars()
        .all()
    )
    by_id = {e.id: e for e in employees}
    member_iv = tm.member_intervals(db, [team], start, end) if team else {}
    jira_ids = [jira_employee_id] if jira_employee_id in by_id else []
    free: dict = {}
    if phase_window and year and quarter:
        load, free = free_load(db, year, quarter, employees, phase_window, skip_booking)
    else:
        load = cto.quarter_load_pct(db, year, quarter, employees) if year and quarter else {}

    def _out(e: Employee) -> Candidate:
        iv = member_iv.get(e.id) or []
        # Отрезки могут вкладываться — конец участия = самый поздний конец.
        iv_end = max((hi for _, hi in iv), default=None)
        return Candidate(
            employee_id=e.id,
            display_name=e.display_name,
            role=e.role,
            team=e.team,
            load_pct=load.get(e.id, 0.0),
            member_from=iv[0][0] if iv and iv[0][0] > start else None,
            member_to=iv_end if iv_end is not None and iv_end < end else None,
            free_hours=free.get(e.id),
        )

    rest = sorted(
        (e for e in employees if e.id not in jira_ids),
        key=lambda e: (-free.get(e.id, 0.0), (e.display_name or "").lower()),
    )
    groups = [
        CandidateGroup("jira", "Из Jira", [_out(by_id[i]) for i in jira_ids]),
        CandidateGroup("team", "Моя команда", [_out(e) for e in rest if e.id in member_iv]),
        CandidateGroup(
            "other", "Другие команды", [_out(e) for e in rest if e.id not in member_iv]
        ),
    ]
    return [g for g in groups if g.employees]


def free_load(
    db: Session,
    year: int,
    quarter: int,
    employees: List[Employee],
    window: tuple[date, date],
    skip_booking: Optional[Callable[[cto.ExternalBooking], bool]] = None,
) -> tuple[dict, dict]:
    """({сотрудник: загрузка квартала %}, {сотрудник: свободно в окне, ч}).

    Той же формулой, что «Загрузка по дням» (`normed_reserve.people_loads`):
    норма дня — календарь минус отсутствия; задачи — брони опорных планов
    всех команд (без ``skip_booking``); нормированные работы и заблокированные
    дни — основной команды. Свободно в день = норма − задачи − нормированные.
    Запросов — константа на любой объём: брони, ёмкость и запас раз на
    основную команду.
    """
    # Сервис планировщика сам импортирует cross_team_occupancy — отсюда лениво.
    from app.services.resource_planning_service import ResourcePlanningService

    q_start, q_end = nr.quarter_bounds(year, quarter)
    bookings = [
        b
        for b in cto.external_bookings(
            db, team=None, year=year, quarter=quarter,
            employee_ids=[e.id for e in employees], start=q_start, end=q_end,
        )
        if skip_booking is None or not skip_booking(b)
    ]
    loads, _reserves, _labels = nr.people_loads(
        db,
        employees,
        year,
        quarter,
        capacity=ResourcePlanningService(db).build_availability(employees, q_start, q_end),
        own={},
        other_teams=cto.daily_totals(bookings),
        residue_share=cto.other_work_share(
            (b.employee_id, b.involvement, b.daily_hours) for b in bookings
        ),
    )
    lo, hi = window
    pct = {eid: round(load.pct, 1) for eid, load in loads.items()}
    free = {
        eid: round(sum(h for d, h in load.free_by_day.items() if lo <= d <= hi), 1)
        for eid, load in loads.items()
    }
    return pct, free


def jira_assignee_id(db: Session, issue: Optional[Issue]) -> Optional[str]:
    """Сотрудник, стоящий исполнителем задачи в Jira (по учётной записи)."""
    account = issue.assignee_account_id if issue is not None else None
    if not account:
        return None
    return (
        db.execute(select(Employee.id).where(Employee.jira_account_id == account))
        .scalars()
        .first()
    )
