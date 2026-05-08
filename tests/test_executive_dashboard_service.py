"""ExecutiveDashboardService — aggregation tests."""
from datetime import datetime

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.issue import Issue
from app.models.planning_scenario import PlanningScenario
from app.models.project import Project
from app.models.scenario_allocation import ScenarioAllocation
from app.models.worklog import Worklog
from app.services.executive_dashboard_service import (
    ExecutiveDashboardService,
    team_set_hash,
)


def _mk_project(db, project_id="p1", key="P"):
    proj = Project(
        id=project_id, jira_project_id=f"{project_id}-id",
        key=key, name=f"Project {key}",
    )
    db.add(proj)
    return proj


def _mk_employee(db, emp_id="e1", role="analyst", team="T1", name="X"):
    emp = Employee(
        id=emp_id,
        jira_account_id=f"jira-{emp_id}",
        display_name=name,
        team=team,
        role=role,
        is_active=True,
    )
    db.add(emp)
    return emp


def _mk_issue(
    db, issue_id, key, *, issue_type="Bug", priority="Critical",
    status="In Progress", team="T1", project_id="p1",
):
    iss = Issue(
        id=issue_id,
        jira_issue_id=f"jira-{issue_id}",
        key=key,
        summary=f"Issue {key}",
        issue_type=issue_type,
        status=status,
        priority=priority,
        project_id=project_id,
        team=team,
        created_at=datetime(2026, 4, 5),
        updated_at=datetime(2026, 4, 5),
    )
    db.add(iss)
    return iss


def _mk_worklog(db, wl_id, issue_id, employee_id, hours=2.0,
                started_at=datetime(2026, 4, 10)):
    wl = Worklog(
        id=wl_id,
        jira_worklog_id=f"jira-wl-{wl_id}",
        issue_id=issue_id,
        employee_id=employee_id,
        hours=hours,
        time_spent_seconds=int(hours * 3600),
        started_at=started_at,
    )
    db.add(wl)
    return wl


def test_team_set_hash_stable():
    h1 = team_set_hash(["A", "B"])
    h2 = team_set_hash(["B", "A"])
    assert h1 == h2 != "all"
    assert team_set_hash([]) == "all"


def test_kpi_zero_when_no_issues(db_session):
    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=[])
    assert f.kpi["critical_risks_count"] == 0
    assert f.kpi["scenario_plan_fact_pct"] == 0.0


def test_queue_buckets_count_open_issues_only(db_session):
    """Open critical bug → critical bucket. Done bug → не считается."""
    _mk_project(db_session)
    _mk_issue(db_session, "i-open", "P-1", status="In Progress")
    _mk_issue(db_session, "i-done", "P-2", status="Done")
    _mk_employee(db_session)
    _mk_worklog(db_session, "w1", "i-open", "e1")
    _mk_worklog(db_session, "w2", "i-done", "e1")
    db_session.commit()

    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=["T1"])
    incidents = next(b for b in f.queue if b["name"] == "Инциденты")
    assert incidents["critical"] == 1  # only open


def test_modules_health_red_when_critical_share_high(db_session):
    """Когда >=5% open critical — модуль красный."""
    _mk_project(db_session)
    # 1 critical open + 1 normal open = 50% critical share → red
    _mk_issue(db_session, "i1", "P-1", priority="Critical", status="In Progress")
    _mk_issue(db_session, "i2", "P-2", priority="Medium", status="In Progress")
    _mk_employee(db_session)
    _mk_worklog(db_session, "w1", "i1", "e1")
    _mk_worklog(db_session, "w2", "i2", "e1")
    db_session.commit()

    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=["T1"])
    mod = next(m for m in f.modules if m["name"] == "T1")
    assert mod["health"] == "red"
    assert mod["risk"] == "Высокий"


def test_plan_fact_by_role_uses_scenario_estimates(db_session):
    """План = backlog_item.estimate_*_hours, факт = worklog × Employee.role."""
    _mk_project(db_session)
    _mk_employee(db_session, "e1", role="analyst")
    _mk_employee(db_session, "e2", role="dev")
    _mk_issue(db_session, "i1", "P-1", status="In Progress")
    _mk_worklog(db_session, "w1", "i1", "e1", hours=10.0,
                started_at=datetime(2026, 4, 15))
    _mk_worklog(db_session, "w2", "i1", "e2", hours=5.0,
                started_at=datetime(2026, 4, 15))

    bi = BacklogItem(
        id="bi1", title="Item",
        estimate_analyst_hours=20.0,
        estimate_dev_hours=30.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(bi)
    scen = PlanningScenario(
        id="s1", name="Q2 plan", year=2026, quarter="Q2", status="approved",
    )
    db_session.add(scen)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        id="a1", scenario_id="s1", backlog_item_id="bi1",
        included_flag=True,
    ))
    db_session.commit()

    svc = ExecutiveDashboardService(db_session)
    f = svc.aggregate(year=2026, quarter=2, teams=["T1"])
    plan_fact = {row["role"]: row for row in f.plan_fact_by_role}
    assert plan_fact["Аналитики"]["plan"] == 20.0
    assert plan_fact["Аналитики"]["fact"] == 10.0
    assert plan_fact["Разработка"]["plan"] == 30.0
    assert plan_fact["Разработка"]["fact"] == 5.0
    assert plan_fact["QA"]["plan"] == 0.0
