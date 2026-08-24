"""Выключенный сотрудник выпадает из состава команды во всех разрезах."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Employee, EmployeeTeam
from app.services.team_membership import members_overlapping


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


def test_inactive_employee_not_in_roster(db_session):
    active = Employee(jira_account_id="a1", display_name="Активный А.", is_active=True)
    off = Employee(jira_account_id="a2", display_name="Выключенный В.", is_active=False)
    db_session.add_all([active, off])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=active.id, team="Альфа", is_primary=True),
        EmployeeTeam(employee_id=off.id, team="Альфа", is_primary=True),
    ])
    db_session.commit()

    ids = members_overlapping(db_session, ["Альфа"], date(2026, 7, 1), date(2026, 9, 30))

    assert ids == {active.id}
