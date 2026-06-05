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


# ---------------------------------------------------------------------------
# Task 4: edge cases
# ---------------------------------------------------------------------------


def test_vacation_not_counted_as_skip(db_session, emp, vacation_reason):
    """Сотрудник в отпуске 12-16 января → ни отгулов, ни переработок."""
    db_session.add(Absence(
        id="a-1",
        employee_id=emp.id,
        start_date=date(2026, 1, 12),
        end_date=date(2026, 1, 16),
        reason_id=vacation_reason.id,
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 16),
    )
    bal = result.employees[0]
    assert bal.skip_days == 0
    assert bal.overtime_days == 0
    assert bal.balance_hours == 0


def test_day_off_reason_does_not_zero_norm(db_session, emp, day_off_reason, issue):
    """Absence с причиной day_off не обнуляет норму → отсутствие ворклога = скип."""
    db_session.add(Absence(
        id="a-d",
        employee_id=emp.id,
        start_date=date(2026, 1, 13),
        end_date=date(2026, 1, 13),
        reason_id=day_off_reason.id,
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 13),
        to_=date(2026, 1, 13),
    )
    bal = result.employees[0]
    # 13 янв 2026 — вторник, норма 8ч, факт 0 → -8ч скип
    assert bal.skip_days == 1
    assert bal.skip_hours == pytest.approx(-8.0)


def test_weekend_work_counted_as_overtime(db_session, emp, issue):
    """Работа в субботу (норма 0) → +часы переработки."""
    db_session.add(Worklog(
        id="wl-sat",
        jira_worklog_id="j-sat",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=4.0,
        time_spent_seconds=int(4.0 * 3600),
        started_at=datetime(2026, 1, 17, 12, 0),  # суббота
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 17),
        to_=date(2026, 1, 17),
    )
    bal = result.employees[0]
    assert bal.overtime_days == 1
    assert bal.overtime_hours == pytest.approx(4.0)
    assert bal.balance_hours == pytest.approx(4.0)


def test_small_deviation_within_threshold_is_norm(db_session, emp, issue):
    """Норма 8ч, факт 7.5ч → недодельта 0.5ч (6.25% < 10%) → не скип."""
    db_session.add(Worklog(
        id="wl-1",
        jira_worklog_id="j-1",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=7.5,
        time_spent_seconds=int(7.5 * 3600),
        started_at=datetime(2026, 1, 13, 10, 0),
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 13),
        to_=date(2026, 1, 13),
    )
    bal = result.employees[0]
    assert bal.skip_days == 0
    assert bal.overtime_days == 0
    # balance считается всё равно (это для KPI)
    assert bal.balance_hours == pytest.approx(-0.5)


def test_sparkline_is_cumulative(db_session, emp, issue):
    """Каждый рабочий день +1ч → спарклайн монотонно растёт."""
    for day_num in range(12, 17):
        d = date(2026, 1, day_num)
        if d.weekday() >= 5:
            continue
        db_session.add(Worklog(
            id=f"wl-{day_num}",
            jira_worklog_id=f"j-{day_num}",
            issue_id=issue.id,
            employee_id=emp.id,
            hours=9.0,  # +1ч сверх нормы
            time_spent_seconds=int(9.0 * 3600),
            started_at=datetime(2026, 1, day_num, 10, 0),
        ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    result = svc.compute_team(
        employee_ids=[emp.id],
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 16),
    )
    sp = result.employees[0].sparkline
    # 12-16 янв 2026 = пн-пт = 5 рабочих дней
    assert len(sp) == 5
    for i in range(1, len(sp)):
        assert sp[i] >= sp[i - 1]  # монотонность
    assert sp[-1] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Task 5: compute_employee (drill-in)
# ---------------------------------------------------------------------------


def test_compute_employee_returns_days_and_monthly(db_session, emp, issue):
    """Drill-in возвращает посуточный массив + помесячные сводки.

    Период — 4 рабочих дня (12-15 янв 2026 = пн-чт). Каждый день
    отрабатывает явно: 12 янв = 11ч (+3 переработка), 13 янв = 5ч (-3 отгул),
    14 янв и 15 янв по 8ч (норма). Итог: balance = 0, 1 переработка, 1 отгул.
    """
    db_session.add(Worklog(
        id="wl-1",
        jira_worklog_id="j-1",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=11.0,
        time_spent_seconds=int(11 * 3600),
        started_at=datetime(2026, 1, 12, 10, 0),  # пн +3
    ))
    db_session.add(Worklog(
        id="wl-2",
        jira_worklog_id="j-2",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=5.0,
        time_spent_seconds=int(5 * 3600),
        started_at=datetime(2026, 1, 13, 10, 0),  # вт -3
    ))
    db_session.add(Worklog(
        id="wl-3",
        jira_worklog_id="j-3",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=8.0,
        time_spent_seconds=int(8 * 3600),
        started_at=datetime(2026, 1, 14, 10, 0),  # ср norm
    ))
    db_session.add(Worklog(
        id="wl-4",
        jira_worklog_id="j-4",
        issue_id=issue.id,
        employee_id=emp.id,
        hours=8.0,
        time_spent_seconds=int(8 * 3600),
        started_at=datetime(2026, 1, 15, 10, 0),  # чт norm
    ))
    db_session.commit()

    svc = HoursBalanceService(db_session)
    detail = svc.compute_employee(
        employee_id=emp.id,
        from_=date(2026, 1, 12),
        to_=date(2026, 1, 15),
    )
    assert detail.employee_id == emp.id
    assert detail.balance_hours == pytest.approx(0.0, abs=0.1)
    assert detail.overtime_days == 1
    assert detail.skip_days == 1
    assert len(detail.monthly) == 1
    jan = detail.monthly[0]
    assert jan.month == 1
    assert jan.balance == pytest.approx(0.0, abs=0.1)
    assert jan.overtime_days == 1
    assert jan.skip_days == 1
    # days
    overtime_day = next(d for d in detail.days if d.day == date(2026, 1, 12))
    assert overtime_day.kind == "overtime"
    assert overtime_day.delta == pytest.approx(3.0)
    skip_day = next(d for d in detail.days if d.day == date(2026, 1, 13))
    assert skip_day.kind == "skip"
    assert skip_day.delta == pytest.approx(-3.0)
