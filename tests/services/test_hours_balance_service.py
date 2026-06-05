"""Тесты HoursBalanceService."""

from datetime import date, datetime, timedelta

import pytest

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
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
