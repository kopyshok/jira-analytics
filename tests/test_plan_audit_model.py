"""Smoke test for PlanAudit model."""
from datetime import datetime

from app.models import PlanAudit, Issue, Project


def test_plan_audit_create(db_session):
    project = Project(
        id="p-test-audit", jira_project_id="PA-PROJ", key="PAP", name="Test Project",
    )
    db_session.add(project)
    db_session.flush()
    issue = Issue(
        id="i-test-audit", jira_issue_id="JIRA-TEST-AUDIT-1", key="TEST-1",
        summary="Test", issue_type="Task", status="Open", project_id=project.id,
    )
    db_session.add(issue)
    db_session.flush()
    audit = PlanAudit(
        issue_id=issue.id, role="analyst",
        value_before=100.0, value_after=150.0,
        source="manual_edit", comment="test",
        created_at=datetime.utcnow(),
    )
    db_session.add(audit)
    db_session.commit()
    assert audit.id is not None
    fetched = db_session.query(PlanAudit).filter_by(id=audit.id).one()
    assert fetched.role == "analyst"
    assert fetched.value_after == 150.0
    assert fetched.source == "manual_edit"
