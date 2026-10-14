"""Данные для тестов переезда на Jira DC."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Employee, Issue, Project, Worklog
from app.services.jira_migration import store


def make_project(db: Session, key: str = "OS", jira_id: str = "11029") -> Project:
    project = Project(jira_project_id=jira_id, key=key, name=key)
    db.add(project)
    db.flush()
    return project


def make_issue(
    db: Session,
    project: Project,
    key: str,
    jira_id: str,
    team: Optional[str] = "Команда А",
    **extra: Any,
) -> Issue:
    issue = Issue(
        jira_issue_id=jira_id, key=key, summary=f"Задача {key}", issue_type="Task",
        status="Открыта", project_id=project.id, team=team, **extra,
    )
    db.add(issue)
    db.flush()
    return issue


def make_employee(db: Session, account_id: str, name: str) -> Employee:
    employee = Employee(jira_account_id=account_id, display_name=name)
    db.add(employee)
    db.flush()
    return employee


def make_worklog(
    db: Session, issue: Issue, employee: Employee, started: datetime, seconds: int, worklog_id: str,
) -> Worklog:
    worklog = Worklog(
        jira_worklog_id=worklog_id, started_at=started, hours=seconds / 3600,
        time_spent_seconds=seconds, issue_id=issue.id, employee_id=employee.id,
    )
    db.add(worklog)
    db.flush()
    return worklog


def seed_report(db: Session, report: dict, maps: dict, finished_at: datetime) -> str:
    """Успешный отчёт пробного прогона, законченный в ``finished_at``."""
    report_id = store.start_report(db, finished_at)
    store.finish_report(db, report_id, report, maps, finished_at)
    return report_id
