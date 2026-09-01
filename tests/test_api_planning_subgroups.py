"""Группа внутри команды в выдаче сценария: идеи и сотрудники."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    ProductionCalendarDay,
    Project,
    ScenarioAllocation,
    Team,
    TeamSubgroup,
)

TEAM = "Команда 1С (Бухгалтерия)"


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


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db, *, has_subgroups: bool) -> str:
    """Команда с двумя группами, сотрудник, задача и идея в сценарии."""
    db.add(Team(id="t-1", name=TEAM, has_subgroups=has_subgroups))
    db.flush()
    db.add_all(
        [
            TeamSubgroup(id="sg-1", team_id="t-1", name="Расчёты", sort_order=1),
            TeamSubgroup(id="sg-2", team_id="t-1", name="Интеграции", sort_order=2),
        ]
    )
    db.add(
        ProductionCalendarDay(
            date=date(2026, 1, 5), is_workday=True, kind="workday", hours=8.0,
            source="manual",
        )
    )
    db.add(
        Employee(
            id="e-1", jira_account_id="acc-1", display_name="Иванов Иван",
            role="dev", is_active=True,
        )
    )
    db.add(
        EmployeeTeam(
            employee_id="e-1", team=TEAM, is_primary=True,
            subgroup_id="sg-1" if has_subgroups else None,
        )
    )
    db.add(Project(id="p-1", jira_project_id="1", key="RFA", name="RFA"))
    db.add(
        Issue(
            id="i-1", jira_issue_id="10001", key="RFA-1", summary="Идея", issue_type="Task", status="Открыта", project_id="p-1", team=TEAM,
            category="initiatives_rfa",
            effective_subgroup_id="sg-2" if has_subgroups else None,
        )
    )
    db.add(
        BacklogItem(
            id="b-1", title="Идея", issue_id="i-1", assignee_employee_id="e-1",
        )
    )
    scenario = PlanningScenario(
        id="sc-1", name="План", quarter="Q1", year=2026, team=TEAM, status="draft",
    )
    db.add(scenario)
    db.flush()
    db.add(
        ScenarioAllocation(
            id="al-1", scenario_id="sc-1", backlog_item_id="b-1", included_flag=True,
        )
    )
    db.commit()
    return "sc-1"


def test_allocations_carry_subgroup(client, db_session):
    """Группа идеи берётся с задачи."""
    sid = _seed(db_session, has_subgroups=True)

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")

    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["subgroup_id"] for row in rows] == ["sg-2"]


def test_allocation_falls_back_to_assignee_group(client, db_session):
    """Идея без группы на задаче опирается на группу исполнителя."""
    sid = _seed(db_session, has_subgroups=True)
    issue = db_session.get(Issue, "i-1")
    issue.effective_subgroup_id = None
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")

    assert r.status_code == 200, r.text
    assert r.json()[0]["subgroup_id"] == "sg-1"


def test_resource_employees_carry_subgroup(client, db_session):
    sid = _seed(db_session, has_subgroups=True)

    r = client.get(f"/api/v1/planning/scenarios/{sid}/resource")

    assert r.status_code == 200, r.text
    assert r.json()["employees"][0]["subgroup_id"] == "sg-1"


def test_team_without_subgroups_stays_empty(client, db_session):
    """Признак деления выключен — раздел ведёт себя как до правки."""
    sid = _seed(db_session, has_subgroups=False)

    allocs = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    resource = client.get(f"/api/v1/planning/scenarios/{sid}/resource")

    assert allocs.json()[0]["subgroup_id"] is None
    assert resource.json()["employees"][0]["subgroup_id"] is None
