"""Резолюция задачи и дата резолюции сохраняются отдельно от статуса."""
from datetime import datetime

from app.models.issue import Issue
from app.models.project import Project


def _make_project(db):
    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db.add(project)
    db.flush()
    return project


def test_issue_resolution_fields(db_session):
    project = _make_project(db_session)
    issue = Issue(
        jira_issue_id="10001",
        key="OS-1",
        summary="Тест",
        issue_type="Задача",
        status="ГОТОВО",
        status_category="done",
        resolution="Готово",
        resolved_at=datetime(2026, 7, 20, 12, 0),
        project_id=project.id,
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).filter_by(key="OS-1").one()
    assert loaded.resolution == "Готово"
    assert loaded.resolved_at == datetime(2026, 7, 20, 12, 0)
