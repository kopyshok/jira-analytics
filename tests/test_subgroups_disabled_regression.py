"""Команда без включённого признака деления ведёт себя как до правки.

Главный тест выпуска: правка сквозная, а обязана быть незаметной для всех
команд, кроме тех, где группы включили руками.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    ProductionCalendarDay,
    Project,
    Team,
)
from app.services.capacity_service import CapacityService
from app.services.resource_base_service import ResourceBaseService
from app.services.subgroup_resolver import SubgroupResolver

TEAM = "Команда без групп"


@pytest.fixture
def plain_team(db_session):
    db_session.add(Team(id="t-plain", name=TEAM, has_subgroups=False))
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(
        Employee(
            id="e-1",
            jira_account_id="acc-1",
            display_name="Иванов",
            role="dev",
            is_active=True,
        )
    )
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id="e-1", team=TEAM, is_primary=True))
    for d in (date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19)):
        db_session.add(
            ProductionCalendarDay(
                date=d, is_workday=True, kind="workday", hours=8.0, source="manual"
            )
        )
    db_session.commit()


def test_capacity_identical_without_subgroups(db_session, plain_team):
    svc = CapacityService(db_session)
    before = svc.team_role_capacity(2026, 1, team_filter=[TEAM])

    assert svc.team_role_capacity_by_subgroup(2026, 1, TEAM) == {}
    assert svc.team_role_capacity(2026, 1, team_filter=[TEAM]) == before


def test_resource_summary_has_empty_breakdown(db_session, plain_team):
    scenario = PlanningScenario(
        id="sc-plain", name="Q1", quarter="Q1", year=2026, team=TEAM, status="draft"
    )
    db_session.add(scenario)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert summary.subgroups == []
    assert summary.gross_by_subgroup_role == {}
    assert summary.available_by_subgroup_role == {}


def test_resolver_silent_without_subgroups(db_session, plain_team):
    issue = Issue(
        id="i-1",
        jira_issue_id="10001",
        key="OS-1",
        summary="x",
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=TEAM,
        assignee_account_id="acc-1",
    )
    db_session.add(issue)
    db_session.commit()

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == "none"


def test_plain_team_endpoint_unchanged(testclient_db_session):
    """Плоский список команд — на нём висит фильтр в шапке."""
    db = testclient_db_session
    db.add(
        Employee(
            id="e-2", jira_account_id="acc-2", display_name="Петров", is_active=True
        )
    )
    db.flush()
    db.add(EmployeeTeam(employee_id="e-2", team=TEAM, is_primary=True))
    db.commit()

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        resp = TestClient(app).get("/api/v1/teams")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json() == [TEAM]
