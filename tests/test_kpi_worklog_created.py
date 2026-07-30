"""Дата внесения записи о трудозатратах сохраняется при синке."""
from datetime import datetime

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog


def _make_issue_and_employee(db):
    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db.add(project)
    db.flush()
    issue = Issue(
        jira_issue_id="10001", key="OS-1", summary="Тест", issue_type="Задача",
        status="ГОТОВО", project_id=project.id,
    )
    employee = Employee(jira_account_id="acc-1", display_name="Иванов И.")
    db.add_all([issue, employee])
    db.flush()
    return issue, employee


def test_worklog_has_created_at(db_session):
    issue, employee = _make_issue_and_employee(db_session)
    wl = Worklog(
        jira_worklog_id="w-1",
        issue_id=issue.id,
        employee_id=employee.id,
        started_at=datetime(2026, 7, 24, 10, 0),
        jira_created_at=datetime(2026, 7, 27, 9, 30),
        hours=4.0,
        time_spent_seconds=14400,
    )
    db_session.add(wl)
    db_session.commit()

    loaded = db_session.query(Worklog).filter_by(jira_worklog_id="w-1").one()
    assert loaded.jira_created_at == datetime(2026, 7, 27, 9, 30)


def test_worklog_schema_parses_created_datetime():
    """JiraWorklogSchema.created_datetime разбирает строку created из ответа Jira.

    Это тест только разбора схемы, не синка — реальный проход через
    _upsert_worklog проверяет test_upsert_worklog_persists_jira_created_at ниже.
    """
    from app.connectors.schemas import JiraWorklogSchema

    payload = JiraWorklogSchema.model_validate({
        "id": "w-2",
        "issueId": "10001",
        "started": "2026-07-24T10:00:00.000+0300",
        "created": "2026-07-27T09:30:00.000+0300",
        "timeSpentSeconds": 14400,
        "author": {"accountId": "acc-1", "displayName": "Иванов И."},
    })
    assert payload.created_datetime is not None
    # app/connectors/schemas.py::_parse_jira_datetime не конвертирует в UTC
    # (в отличие от одноимённой функции в sync_service.py) — час остаётся как есть.
    assert payload.created_datetime.hour == 9


def test_upsert_worklog_persists_jira_created_at(db_session):
    """_upsert_worklog реально переносит дату внесения в колонку БД."""
    from unittest.mock import MagicMock

    from app.connectors.schemas import JiraWorklogSchema
    from app.services.sync_service import SyncService

    issue, employee = _make_issue_and_employee(db_session)
    svc = SyncService(db_session, jira_client=MagicMock())

    payload = JiraWorklogSchema.model_validate({
        "id": "w-3",
        "issueId": issue.jira_issue_id,
        "started": "2026-07-24T10:00:00.000+0300",
        "created": "2026-07-27T09:30:00.000+0300",
        "timeSpentSeconds": 14400,
        "author": {"accountId": employee.jira_account_id, "displayName": employee.display_name},
    })
    svc._upsert_worklog(payload, issue.id, employee.id)
    db_session.commit()

    loaded = db_session.query(Worklog).filter_by(jira_worklog_id="w-3").one()
    assert loaded.jira_created_at == datetime(2026, 7, 27, 9, 30)
