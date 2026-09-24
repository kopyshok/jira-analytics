"""Кандидаты в исполнители — общая функция для фазы плана и строки сценария.

Кандидат — активный сотрудник, состоявший хоть в какой-то команде хотя бы
день квартала (боты и люди вне команд не попадают). Группы: «Из Jira» (кого
показать, решает вызывающий), «Моя команда» (состав команды за квартал),
«Другие команды». У каждого — загрузка за квартал по опорным планам всех
команд. Пустые группы не возвращаются. Чистое чтение.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue
from app.services import cross_team_occupancy as cto
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
) -> List[CandidateGroup]:
    """Все, кто в квартале ``start`` — ``end`` состоит в какой-либо команде, группами.

    ``team`` — команда группы «Моя команда»; ``jira_employee_id`` — кого
    показать в группе «Из Jira» (если он среди кандидатов). Загрузка
    считается, только если известны год и квартал.
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
        )

    rest = sorted(
        (e for e in employees if e.id not in jira_ids),
        key=lambda e: (e.display_name or "").lower(),
    )
    groups = [
        CandidateGroup("jira", "Из Jira", [_out(by_id[i]) for i in jira_ids]),
        CandidateGroup("team", "Моя команда", [_out(e) for e in rest if e.id in member_iv]),
        CandidateGroup(
            "other", "Другие команды", [_out(e) for e in rest if e.id not in member_iv]
        ),
    ]
    return [g for g in groups if g.employees]


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
