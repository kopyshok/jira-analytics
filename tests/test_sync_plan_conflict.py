"""Sync должен записывать в plan_audit при изменении planned_<role>_hours_jira."""
from app.models import PlanAudit, Issue, Project
from app.services.sync_service import _record_plan_changes


def _project(db, key="SYC"):
    p = Project(id=f"p-{key}", key=key, jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _issue(db, project, key, **kwargs):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type="Task",
        status="Open", project_id=project.id, **kwargs,
    )
    db.add(i)
    db.flush()
    return i


def test_sync_logs_jira_change_no_manual(db_session):
    """_jira меняется, _manual пуст → source='jira_sync'."""
    p = _project(db_session)
    issue = _issue(db_session, p, "SC-1", planned_dev_hours_jira=500)
    db_session.flush()

    _record_plan_changes(db_session, issue, {
        "analyst": None, "dev": 550, "qa": None, "opo": None,
    })
    db_session.commit()

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 1
    assert rows[0].role == "dev"
    assert rows[0].value_before == 500
    assert rows[0].value_after == 550
    assert rows[0].source == "jira_sync"
    # _jira обновлено
    db_session.refresh(issue)
    assert issue.planned_dev_hours_jira == 550


def test_sync_conflict_when_manual_set(db_session):
    """Если _manual задан и новое Jira ≠ старому _jira → source='jira_sync_conflict'.
    _jira обновляется, _manual остаётся."""
    p = _project(db_session)
    issue = _issue(db_session, p, "SC-2",
                   planned_dev_hours_jira=500,
                   planned_dev_hours_manual=600)
    db_session.flush()

    _record_plan_changes(db_session, issue, {
        "analyst": None, "dev": 550, "qa": None, "opo": None,
    })
    db_session.commit()

    db_session.refresh(issue)
    # _manual не тронут
    assert issue.planned_dev_hours_manual == 600
    # _jira обновлено
    assert issue.planned_dev_hours_jira == 550
    # effective = manual ?? jira = 600
    assert issue.planned_dev_hours == 600

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert any(r.source == "jira_sync_conflict" for r in rows)


def test_sync_noop_when_unchanged(db_session):
    """Если значение Jira не меняется — нет audit-записей."""
    p = _project(db_session)
    issue = _issue(db_session, p, "SC-3", planned_dev_hours_jira=500)
    db_session.flush()

    _record_plan_changes(db_session, issue, {
        "analyst": None, "dev": 500, "qa": None, "opo": None,
    })
    db_session.commit()

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 0


def test_sync_initial_creation_logs_audit(db_session):
    """Новое issue (старое _jira == None) с пришедшим значением — audit jira_sync."""
    p = _project(db_session)
    issue = _issue(db_session, p, "SC-4")  # без planned_*
    db_session.flush()

    _record_plan_changes(db_session, issue, {
        "analyst": 100, "dev": None, "qa": None, "opo": None,
    })
    db_session.commit()

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 1
    assert rows[0].role == "analyst"
    assert rows[0].value_before is None
    assert rows[0].value_after == 100
    assert rows[0].source == "jira_sync"
