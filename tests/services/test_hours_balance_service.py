"""Тесты HoursBalanceService."""

from datetime import date, datetime, timedelta

import pytest

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.services.hours_balance_service import HoursBalanceService


@pytest.fixture
def emp(db_session):
    e = Employee(
        id="emp-1",
        jira_account_id="jira-emp-1",
        display_name="Тестов Т.",
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def vacation_reason(db_session):
    r = AbsenceReason(
        id="r-vacation",
        code="vacation",
        label="Отпуск",
        is_planned=True,
        is_active=True,
    )
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def day_off_reason(db_session):
    r = AbsenceReason(
        id="r-day-off",
        code="day_off",
        label="Отгул",
        is_planned=False,
        is_active=True,
    )
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def issue(db_session):
    """Минимальный Issue для привязки Worklog."""
    p = Project(id="proj-1", jira_project_id="JP-1", key="P", name="P")
    db_session.add(p)
    i = Issue(
        id="iss-1",
        jira_issue_id="JI-1",
        key="P-1",
        summary="test issue",
        issue_type="Task",
        status="Open",
        project_id="proj-1",
    )
    db_session.add(i)
    db_session.commit()
    return i


# ---------------------------------------------------------------------------
# Task 3: compute_team
# ---------------------------------------------------------------------------


def test_empty_employees_returns_empty(db_session):
    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[],
        from_=date(2026, 1, 1),
        to_=date(2026, 1, 31),
    )
    assert result.employees == []
    assert result.team_summary_employees_count == 0
    assert result.team_summary_net_balance == 0


def test_employee_full_norm_balance_zero(db_session, emp, issue):
    """Сотрудник отработал ровно норму каждый рабочий день → баланс 0.

    Период 12-30 янв 2026 (пн-пт, 2 полных рабочих недели + 2 дня),
    без праздников — тест не зависит от производственного календаря.
    """
    for day_num in range(12, 31):
        d = date(2026, 1, day_num)
        if d.weekday() >= 5:
            continue
        wl = Worklog(
            id=f"wl-{day_num}",
            jira_worklog_id=f"j-{day_num}",
            issue_id=issue.id,
            employee_id=emp.id,
            hours=8.0,
            time_spent_seconds=int(8.0 * 3600),
            started_at=datetime(2026, 1, day_num, 10, 0),
        )
        db_session.add(wl)
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 30),
    )
    assert len(result.employees) == 1
    bal = result.employees[0]
    assert bal.balance_hours == pytest.approx(0, abs=0.01)
    assert bal.overtime_days == 0
    assert bal.skip_days == 0
