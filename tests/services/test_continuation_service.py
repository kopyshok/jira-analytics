"""Тесты continuation_service: spent + is_continuation для allocations сценария.

Адаптация к реальной модели: Worklog не имеет ``assigned_category`` —
категория берётся с ``Issue.assigned_category`` (она же определяет роль).
"""
from datetime import datetime

import pytest

from app.models import (
    BacklogItem,
    Employee,
    Issue,
    PlanningScenario,
    Project,
    ScenarioAllocation,
    Worklog,
)
from app.services.continuation_service import ContinuationService


def _make_scenario(db, year=2026, quarter="Q2"):
    sc = PlanningScenario(name="Test", year=year, quarter=quarter, status="draft")
    db.add(sc)
    db.flush()
    return sc


def _make_project(db, key="ITL", jira_id="10000"):
    proj = Project(jira_project_id=jira_id, key=key, name=key)
    db.add(proj)
    db.flush()
    return proj


def _make_issue(db, project, key="ITL-299", jira_id="20000", category=None):
    issue = Issue(
        jira_issue_id=jira_id,
        key=key,
        project_id=project.id,
        summary="ERP",
        issue_type="Initiative",
        status="To Do",
        assigned_category=category,
    )
    db.add(issue)
    db.flush()
    return issue


def _make_employee(db, jira_id="acc-1"):
    emp = Employee(
        jira_account_id=jira_id,
        display_name="Test User",
        email="test@x",
        is_active=True,
    )
    db.add(emp)
    db.flush()
    return emp


def _make_worklog(db, issue, employee, when, hours, jira_id):
    wl = Worklog(
        jira_worklog_id=jira_id,
        issue_id=issue.id,
        employee_id=employee.id,
        started_at=when,
        hours=hours,
        time_spent_seconds=int(hours * 3600),
    )
    db.add(wl)
    return wl


def test_no_worklogs_returns_zero_spent(db_session):
    db = db_session
    sc = _make_scenario(db)
    proj = _make_project(db)
    issue = _make_issue(db, proj)
    bi = BacklogItem(
        title="ITL-299",
        issue_id=issue.id,
        estimate_analyst_hours=40,
        estimate_dev_hours=120,
        estimate_qa_hours=30,
        estimate_opo_hours=20,
    )
    db.add(bi)
    db.flush()
    alloc = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=True)
    db.add(alloc)
    db.commit()

    info = ContinuationService(db).compute_for_scenario(sc.id)
    row = info[alloc.id]
    assert row["spent"] == {"analyst": 0.0, "dev": 0.0, "qa": 0.0, "opo": 0.0}
    assert row["spent_total"] == 0.0
    assert row["is_continuation"] is False


def test_worklogs_before_quarter_aggregate_by_role(db_session):
    """Два issue, разные категории → spent распределяется по двум ролям."""
    db = db_session
    sc = _make_scenario(db, year=2026, quarter="Q2")  # quarter_start = 2026-04-01
    proj = _make_project(db)
    emp = _make_employee(db)

    # Issue 1 — analysis bucket
    issue_a = _make_issue(db, proj, key="ITL-300", jira_id="20001", category="analysis")
    _make_worklog(db, issue_a, emp, datetime(2026, 2, 15), 20.0, "wl-a")
    bi_a = BacklogItem(title="ITL-300", issue_id=issue_a.id)
    db.add(bi_a)
    db.flush()
    alloc_a = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi_a.id, included_flag=True)
    db.add(alloc_a)

    # Issue 2 — development bucket
    issue_d = _make_issue(db, proj, key="ITL-301", jira_id="20002", category="development")
    _make_worklog(db, issue_d, emp, datetime(2026, 2, 20), 60.0, "wl-d")
    bi_d = BacklogItem(title="ITL-301", issue_id=issue_d.id)
    db.add(bi_d)
    db.flush()
    alloc_d = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi_d.id, included_flag=True)
    db.add(alloc_d)
    db.commit()

    info = ContinuationService(db).compute_for_scenario(sc.id)

    row_a = info[alloc_a.id]
    assert row_a["spent"]["analyst"] == 20.0
    assert row_a["spent"]["dev"] == 0.0
    assert row_a["spent_total"] == 20.0
    assert row_a["is_continuation"] is True

    row_d = info[alloc_d.id]
    assert row_d["spent"]["dev"] == 60.0
    assert row_d["spent"]["analyst"] == 0.0
    assert row_d["spent_total"] == 60.0
    assert row_d["is_continuation"] is True


def test_worklogs_in_or_after_quarter_excluded(db_session):
    db = db_session
    sc = _make_scenario(db, year=2026, quarter="Q2")
    proj = _make_project(db)
    issue = _make_issue(db, proj, category="analysis")
    emp = _make_employee(db)
    # ровно начало Q2 — НЕ списано
    _make_worklog(db, issue, emp, datetime(2026, 4, 1), 10.0, "wl-q2")
    bi = BacklogItem(title="ITL-299", issue_id=issue.id)
    db.add(bi)
    db.flush()
    alloc = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=True)
    db.add(alloc)
    db.commit()

    info = ContinuationService(db).compute_for_scenario(sc.id)
    row = info[alloc.id]
    assert row["spent_total"] == 0.0
    assert row["is_continuation"] is False


def test_allocation_without_issue_id_no_continuation(db_session):
    """Ручной BacklogItem без issue_id — спент всегда 0."""
    db = db_session
    sc = _make_scenario(db)
    bi = BacklogItem(title="Manual", issue_id=None, estimate_analyst_hours=40)
    db.add(bi)
    db.flush()
    alloc = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=True)
    db.add(alloc)
    db.commit()

    info = ContinuationService(db).compute_for_scenario(sc.id)
    row = info[alloc.id]
    assert row["spent_total"] == 0.0
    assert row["is_continuation"] is False
