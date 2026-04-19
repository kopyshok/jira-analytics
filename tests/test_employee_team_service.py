"""Тесты авто-определения команды сотрудника из ворклогов."""

from datetime import date, datetime, timedelta
import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.employee_team_service import EmployeeTeamService


@pytest.fixture
def seed(db_session):
    p = Project(id="p1", jira_project_id="100", key="PRJ", name="PRJ")
    db_session.add(p)
    # Issues with team set
    i_alpha = Issue(id="i_a", jira_issue_id="1", key="PRJ-1", summary="x",
                    project_id="p1", issue_type="Task", status="Готово", team="Alpha")
    i_beta = Issue(id="i_b", jira_issue_id="2", key="PRJ-2", summary="x",
                   project_id="p1", issue_type="Task", status="Готово", team="Beta")
    i_none = Issue(id="i_n", jira_issue_id="3", key="PRJ-3", summary="x",
                   project_id="p1", issue_type="Task", status="Готово", team=None)
    emp = Employee(id="e1", jira_account_id="a1", display_name="Иванов",
                   is_active=True, team=None)
    db_session.add_all([i_alpha, i_beta, i_none, emp])
    db_session.flush()
    db_session.commit()
    return {"emp": emp, "i_alpha": i_alpha, "i_beta": i_beta, "i_none": i_none}


def _log(db, emp, issue, hours, days_ago):
    w = Worklog(
        id=f"w-{emp.id}-{issue.id}-{days_ago}",
        jira_worklog_id=f"j-{emp.id}-{issue.id}-{days_ago}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime.utcnow() - timedelta(days=days_ago),
        hours=hours, time_spent_seconds=int(hours * 3600),
    )
    db.add(w)


def test_mode_picks_dominant_team(db_session, seed):
    # Alpha: 3 logs × 2h = 6h ; Beta: 1 log × 8h = 8h  → Beta wins on total time
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 5)
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 10)
    _log(db_session, seed["emp"], seed["i_alpha"], 2, 15)
    _log(db_session, seed["emp"], seed["i_beta"], 8, 20)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) == "Beta"


def test_ignores_worklogs_outside_lookback(db_session, seed):
    _log(db_session, seed["emp"], seed["i_alpha"], 10, 200)  # outside 180 d
    _log(db_session, seed["emp"], seed["i_beta"], 2, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) == "Beta"


def test_returns_none_when_no_teamed_logs(db_session, seed):
    _log(db_session, seed["emp"], seed["i_none"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    assert svc.auto_detect_team(seed["emp"].id) is None


def test_bulk_auto_detect_all_missing(db_session, seed):
    _log(db_session, seed["emp"], seed["i_alpha"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    summary = svc.auto_detect_all_missing()
    assert summary.assigned == 1
    assert summary.skipped == 0
    db_session.expire_all()
    assert db_session.get(Employee, seed["emp"].id).team == "Alpha"


def test_bulk_skips_employees_with_existing_team(db_session, seed):
    seed["emp"].team = "Preserved"
    db_session.commit()
    _log(db_session, seed["emp"], seed["i_alpha"], 5, 10)
    db_session.commit()

    svc = EmployeeTeamService(db_session)
    summary = svc.auto_detect_all_missing()
    assert summary.assigned == 0
    assert summary.skipped == 1
    db_session.expire_all()
    assert db_session.get(Employee, seed["emp"].id).team == "Preserved"
