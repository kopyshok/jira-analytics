"""Срез задач рабочего стола тимлида."""
import uuid

import pytest

from app.models import Issue, Project


def _project(db_session) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=f"OS{uuid.uuid4().hex[:4]}",
        name="OS",
    )
    db_session.add(project)
    db_session.flush()
    return project


def test_issue_has_developer_and_dev_estimate(db_session):
    project = _project(db_session)
    issue = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=str(uuid.uuid4()),
        key="OS-1",
        summary="Тестовая задача",
        issue_type="Задача",
        status="В РАБОТЕ",
        project_id=project.id,
        developer_account_id="acc-1",
        developer_display_name="Шутов Сергей",
        dev_est_hours=16.0,
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).filter_by(key="OS-1").one()
    assert loaded.developer_display_name == "Шутов Сергей"
    assert loaded.developer_account_id == "acc-1"
    assert loaded.dev_est_hours == 16.0
