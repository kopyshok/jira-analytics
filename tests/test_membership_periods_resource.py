"""Ресурс квартала при выбытии/входе в середине квартала."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Employee, EmployeeTeam, PlanningScenario
from app.services.resource_base_service import ResourceBaseService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _setup(db, joined=None, left=None, account="acc-1"):
    emp = Employee(
        jira_account_id=account, display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(
        employee_id=emp.id, team="Альфа", is_primary=True,
        joined_at=joined, left_at=left,
    ))
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db.add(scenario)
    db.commit()
    return emp, scenario


def test_full_quarter_baseline(db_session):
    """Без дат — полный квартал (рабочие дни × 8ч)."""
    emp, scenario = _setup(db_session)
    base = ResourceBaseService(db_session).compute(scenario)
    assert base.role_totals["dev"] > 0


def test_departure_mid_quarter_reduces_hours(db_session):
    """Выбытие 15 февраля срезает часы с 15 февраля включительно."""
    emp, scenario = _setup(db_session, left=date(2026, 2, 15))
    base = ResourceBaseService(db_session).compute(scenario)

    days = {d.date for d in base.employees[0].days}
    assert date(2026, 2, 13) in days       # пятница до выбытия
    assert date(2026, 2, 16) not in days   # понедельник после
    assert all(d < date(2026, 2, 15) for d in days)


def test_join_mid_quarter(db_session):
    """Вход 15 февраля — до этой даты часов нет."""
    emp, scenario = _setup(db_session, joined=date(2026, 2, 15))
    base = ResourceBaseService(db_session).compute(scenario)

    days = {d.date for d in base.employees[0].days}
    assert all(d >= date(2026, 2, 15) for d in days)
    assert date(2026, 1, 20) not in days


def test_two_periods_with_gap(db_session):
    """Два периода: считаются оба, разрыв — нет."""
    emp = Employee(
        jira_account_id="acc-2", display_name="Петров П.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True,
                     joined_at=date(2026, 1, 1), left_at=date(2026, 2, 1)),
        EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=False,
                     joined_at=date(2026, 3, 1), left_at=None),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    days = {d.date for d in base.employees[0].days}
    assert date(2026, 1, 15) in days
    assert date(2026, 2, 10) not in days   # разрыв
    assert date(2026, 3, 10) in days


def test_summary_gross_respects_membership(db_session):
    """Сводка: брутто и календарные часы тоже режутся датами.

    Сравниваем один и тот же сотрудник в двух командах: в «Альфа» он выбыл
    15 февраля, в «Бета» состоит весь квартал. Разные сценарии — разные
    команды, поэтому измеряется ровно эффект даты выбытия.
    """
    emp = Employee(
        jira_account_id="acc-solo", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True,
                     left_at=date(2026, 2, 15)),
        EmployeeTeam(employee_id=emp.id, team="Бета", is_primary=False),
    ])
    cut = PlanningScenario(
        name="Q1 Альфа", year=2026, quarter=1, team="Альфа", status="draft",
    )
    full = PlanningScenario(
        name="Q1 Бета", year=2026, quarter=1, team="Бета", status="draft",
    )
    db_session.add_all([cut, full])
    db_session.commit()

    svc = ResourceBaseService(db_session)
    cut_summary = svc.compute_summary(cut)
    full_summary = svc.compute_summary(full)

    assert cut_summary.gross_by_role["dev"] < full_summary.gross_by_role["dev"]
    assert (
        cut_summary.calendar_gross_by_role["dev"]
        < full_summary.calendar_gross_by_role["dev"]
    )
