"""HoursBreakdownService — 6-колоночный расчёт часов длинной RFA."""
from datetime import date, datetime, time

import pytest

from app.models import (
    Issue, Project, Employee, Worklog, BacklogItem, PlanningScenario, ScenarioAllocation,
)
from app.services.hours_breakdown_service import HoursBreakdownService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(db, key="TEST"):
    p = Project(id=f"p-{key}", jira_project_id=f"jp-{key}", key=key, name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _employee(db, key: str, role: str = "dev") -> Employee:
    e = Employee(
        id=f"e-{key}",
        jira_account_id=f"jira-{key}",
        display_name=f"Employee {key}",
        role=role,
    )
    db.add(e)
    db.flush()
    return e


def _issue(db, project, key, issue_type="Task", parent_id=None,
           a_jira=None, d_jira=None, q_jira=None, o_jira=None):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type=issue_type,
        status="Open", project_id=project.id, parent_id=parent_id,
        planned_analyst_hours_jira=a_jira,
        planned_dev_hours_jira=d_jira,
        planned_qa_hours_jira=q_jira,
        planned_opo_hours_jira=o_jira,
    )
    db.add(i)
    db.flush()
    return i


def _worklog(db, issue, started: date, hours: float, employee: Employee):
    """Создать worklog; роль берётся из employee.role."""
    started_dt = datetime.combine(started, time.min)
    w = Worklog(
        id=f"w-{issue.key}-{started}-{employee.id}",
        jira_worklog_id=f"jw-{issue.key}-{started}-{employee.id}",
        issue_id=issue.id,
        employee_id=employee.id,
        started_at=started_dt,
        hours=hours,
        time_spent_seconds=int(hours * 3600),
    )
    db.add(w)
    db.flush()
    return w


def _approve_in_scenario(db, issue, year, quarter):
    """Утвердить issue в сценарии (year, Qquarter) со статусом approved."""
    quarter_str = f"Q{quarter}"
    bi = BacklogItem(id=f"bi-{issue.key}", issue_id=issue.id, title=issue.summary)
    db.add(bi)
    sc = PlanningScenario(
        id=f"sc-{year}-{quarter_str}-{issue.key}",
        year=year, quarter=quarter_str, status="approved",
        name=f"S{year}{quarter_str} {issue.key}",
    )
    db.add(sc)
    db.flush()
    a = ScenarioAllocation(
        id=f"a-{sc.id}-{bi.id}",
        scenario_id=sc.id, backlog_item_id=bi.id,
        included_flag=True, planned_hours=0,
    )
    db.add(a)
    db.flush()
    return bi, sc, a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_simple_rfa_no_children(db_session):
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-1", "RFA", a_jira=100, d_jira=200, q_jira=50, o_jira=25)
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["plan"]["analyst"] == 100
    assert result["plan"]["dev"] == 200
    assert result["plan"]["total"] == 375
    assert result["fact_past"]["analyst"] == 0
    assert result["fact_current"]["analyst"] == 0
    assert result["approved"]["analyst"] == 0
    assert result["planable"]["analyst"] == 100
    assert result["planable"]["dev"] == 200
    assert result["draft"]["analyst"] == 0


def test_long_rfa_with_approved_q1_epic_viewing_q2(db_session):
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-77", "RFA",
                 a_jira=200, d_jira=500, q_jira=200, o_jira=100)
    epic_q1 = _issue(db_session, p, "PRJ-1", "Epic", parent_id=rfa.id,
                     a_jira=100, d_jira=250, q_jira=25, o_jira=25)

    emp_a = _employee(db_session, "e-a77", role="analyst")
    emp_d = _employee(db_session, "e-d77", role="dev")
    emp_q = _employee(db_session, "e-q77", role="qa")
    emp_o = _employee(db_session, "e-o77", role="opo")

    # факт в Q1 на эпике, разные роли
    _worklog(db_session, epic_q1, date(2026, 1, 15), 80, emp_a)
    _worklog(db_session, epic_q1, date(2026, 2, 10), 150, emp_d)
    _worklog(db_session, epic_q1, date(2026, 3, 5), 50, emp_q)
    _worklog(db_session, epic_q1, date(2026, 3, 20), 20, emp_o)
    _approve_in_scenario(db_session, epic_q1, 2026, 1)
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    # Факт прошлых Q (Q1) — вся работа, по всему поддереву
    assert result["fact_past"]["analyst"] == 80
    assert result["fact_past"]["dev"] == 150
    assert result["fact_past"]["qa"] == 50
    assert result["fact_past"]["opo"] == 20
    # Факт текущий в Q2 = 0 (нет approved-эпиков на Q2)
    assert result["fact_current"]["analyst"] == 0
    # Утверждено в Q2 = 0 (нет утв. эпиков на Q2)
    assert result["approved"]["analyst"] == 0
    # Запланировать = 200 - 80 - 0 = 120
    assert result["planable"]["analyst"] == 120
    assert result["planable"]["dev"] == 350
    # Эпик Q1 имеет ворклоги — не попадает в Черновик
    assert result["draft"]["analyst"] == 0


def test_draft_epic_in_count(db_session):
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-2", "RFA", d_jira=500)
    _issue(db_session, p, "PRJ-2", "Epic", parent_id=rfa.id, d_jira=100)
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["draft"]["dev"] == 100


def test_manual_override_used_in_plan(db_session):
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-3", "RFA", d_jira=500)
    rfa.planned_dev_hours_manual = 600
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["plan"]["dev"] == 600


def test_planable_negative_marked(db_session):
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-4", "RFA", d_jira=100)
    emp = _employee(db_session, "e-rfa4", role="dev")
    _worklog(db_session, rfa, date(2026, 1, 15), 150, emp)
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["planable"]["dev"] == -50
    assert result["flags"]["overrun"] is True


def test_cancelled_descendants_excluded_from_draft(db_session):
    """Отменённые потомки (Эпик/ITL в статусе «Отменено») не должны падать в Черновик."""
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-6C", "RFA", d_jira=500)
    cancelled_epic = _issue(
        db_session, p, "PRJ-6C", "Epic", parent_id=rfa.id, d_jira=100
    )
    cancelled_epic.status = "Отменено"
    cancelled_itl = _issue(
        db_session, p, "PRJ-6D", "ITL", parent_id=rfa.id, d_jira=50, a_jira=20
    )
    cancelled_itl.status = "Rejected"
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["draft"]["dev"] == 0
    assert result["draft"]["analyst"] == 0
    assert result["draft"]["total"] == 0


def test_current_fact_only_in_approved_epics(db_session):
    """Факт текущий считает worklog ТОЛЬКО для утв. эпиков, не для всего поддерева."""
    p = _project(db_session)
    rfa = _issue(db_session, p, "RFA-5", "RFA", d_jira=500)
    epic_approved = _issue(db_session, p, "PRJ-5A", "Epic", parent_id=rfa.id, d_jira=200)
    epic_unapproved = _issue(db_session, p, "PRJ-5B", "Epic", parent_id=rfa.id, d_jira=100)

    emp = _employee(db_session, "e-rfa5", role="dev")

    # факт в Q2 на обоих эпиках
    _worklog(db_session, epic_approved, date(2026, 4, 10), 40, emp)
    _worklog(db_session, epic_unapproved, date(2026, 5, 10), 25, emp)
    _approve_in_scenario(db_session, epic_approved, 2026, 2)
    db_session.commit()

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    # Факт текущий — только worklog approved-эпика
    assert result["fact_current"]["dev"] == 40
    # Утверждено = план approved-эпика
    assert result["approved"]["dev"] == 200
    # Запланировать = 500 - 0 - 200 = 300 (нет фактов прошлых)
    assert result["planable"]["dev"] == 300
    # epic_unapproved имеет ворклоги → НЕ в Черновике
    assert result["draft"]["dev"] == 0
