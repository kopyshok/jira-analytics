"""Общий сотрудник виден в базе ресурса."""

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


def test_shared_employee_marked(db_session):
    """Сотрудник в двух командах помечен и несёт список чужих команд."""
    shared = Employee(
        jira_account_id="acc-1", display_name="Общий О.",
        is_active=True, role="dev",
    )
    solo = Employee(
        jira_account_id="acc-2", display_name="Только А.",
        is_active=True, role="dev",
    )
    db_session.add_all([shared, solo])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=shared.id, team="Альфа", is_primary=True),
        EmployeeTeam(employee_id=shared.id, team="Бета", is_primary=False),
        EmployeeTeam(employee_id=solo.id, team="Альфа", is_primary=True),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    by_name = {e.display_name: e for e in base.employees}

    assert by_name["Общий О."].shared_with == ["Бета"]
    assert by_name["Только А."].shared_with == []
    # Ресурс НЕ режется — часы у обоих одинаковые
    assert by_name["Общий О."].total_hours == by_name["Только А."].total_hours


def test_shared_hours_committed_elsewhere(db_session):
    """Показывается, сколько часов на общего заложено всеми командами."""
    shared = Employee(
        jira_account_id="acc-1", display_name="Общий О.",
        is_active=True, role="dev",
    )
    db_session.add(shared)
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=shared.id, team="Альфа", is_primary=True),
        EmployeeTeam(employee_id=shared.id, team="Бета", is_primary=False),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    # В двух командах на полную — суммарно вдвое больше календарной нормы
    assert emp.committed_hours_all_teams == pytest.approx(emp.total_hours * 2, rel=0.01)
    assert emp.is_overcommitted is True
