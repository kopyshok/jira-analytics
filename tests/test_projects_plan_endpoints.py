"""Эндпоинты вкладки «План и сроки» и сводки портфеля."""
import uuid
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.planning_scenario import PlanningScenario
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.scenario_allocation import ScenarioAllocation
from app.models.worklog import Worklog


def _uid() -> str:
    return str(uuid.uuid4())


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _seed_plan(db) -> None:
    """Проект EP-1: план 40ч аналитика (2026 Q3) + 10ч факта свой командой."""
    db.add(Project(id="ep", jira_project_id="ep", key="EP", name="Endpoint"))
    db.add(Issue(id="eproot", jira_issue_id="1", key="EP-1", summary="Проект",
                 issue_type="Epic", status="В работе", project_id="ep",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.commit()

    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Проект", issue_id="eproot"))
    db.commit()

    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.commit()
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=40.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 8, 15)))

    eid = _uid()
    db.add(Employee(id=eid, jira_account_id=eid, display_name="Аналитик", role="analyst"))
    db.add(EmployeeTeam(id=_uid(), employee_id=eid, team="T", is_primary=True))
    db.commit()
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="eproot",
                   employee_id=eid, hours=10.0, time_spent_seconds=int(10.0 * 3600),
                   started_at=datetime(2026, 7, 10)))
    db.commit()


def test_plan_endpoint_returns_work_types(db_session):
    _seed_plan(db_session)
    try:
        client = _client(db_session)
        resp = client.get("/api/v1/projects/EP-1/plan?year=2026&quarter=3")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_plan"] == 40.0
        assert body["total_fact"] == 10.0
        assert body["total_pct"] == 25
        assert [w["code"] for w in body["work_types"]] == ["analyst", "dev", "qa"]
        assert body["timeline"]["quarter_start"] == "2026-07-01"
    finally:
        app.dependency_overrides.clear()


def test_plan_endpoint_404_on_unknown_key(db_session):
    try:
        client = _client(db_session)
        resp = client.get("/api/v1/projects/NOPE-1/plan?year=2026&quarter=3")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_portfolio_endpoint_respects_quarter_filter(db_session):
    """/portfolio считает по тем же проектам, что список — членство через
    утверждённый сценарий (не через поле «Цели», см. §4 спеки/CLAUDE ремарку).
    """
    db = db_session
    db.add(Project(id="pf", jira_project_id="pf", key="PF", name="Portfolio"))
    epic_in = Issue(id="pf_in", jira_issue_id="500", key="PF-1", summary="In scenario",
                    issue_type="Epic", status="В работе", project_id="pf",
                    category="quarterly_tasks", include_in_analysis=True, team="T")
    epic_out = Issue(id="pf_out", jira_issue_id="501", key="PF-2", summary="Not in scenario",
                     issue_type="Epic", status="В работе", project_id="pf",
                     category="quarterly_tasks", include_in_analysis=True, team="T")
    db.add_all([epic_in, epic_out])
    db.commit()

    item_in = BacklogItem(id=_uid(), issue_id="pf_in", title="In")
    item_out = BacklogItem(id=_uid(), issue_id="pf_out", title="Out")
    db.add_all([item_in, item_out])
    db.commit()

    # Оба эпика имеют плановые назначения — чтобы тест реально проверял
    # ФИЛЬТРАЦИЮ по сценарию, а не просто пустой таймлайн у обоих.
    plan_in_id, plan_out_id = _uid(), _uid()
    db.add(ResourcePlan(id=plan_in_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlan(id=plan_out_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.commit()
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_in_id, backlog_item_id=item_in.id,
                                  phase="analyst", hours_allocated=10.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_out_id, backlog_item_id=item_out.id,
                                  phase="analyst", hours_allocated=10.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 20)))
    db.commit()

    # Только item_in утверждён в сценарии на 2026 Q3 — item_out нигде не аллоцирован.
    scenario = PlanningScenario(id=_uid(), name="S", year=2026, quarter="Q3",
                                 status="approved", team="T")
    db.add(scenario)
    db.commit()
    db.add(ScenarioAllocation(id=_uid(), scenario_id=scenario.id,
                                backlog_item_id=item_in.id, included_flag=True))
    db.commit()

    try:
        client = _client(db)
        resp = client.get("/api/v1/projects/portfolio?year=2026&quarter=3")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_count"] == 1
        assert [r["key"] for r in body["timeline"]["rows"]] == ["PF-1"]
    finally:
        app.dependency_overrides.clear()
