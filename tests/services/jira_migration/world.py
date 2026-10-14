"""Мир для пробного прогона: база с облачными id и новая Jira с теми же задачами.

OS-91030 в облаке был 683676, в новой Jira — 258783 (в базе это id
PMD-19591). Время ворклогов базы — московское, в новой Jira — UTC.
"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting, BacklogItem, ScopeProject
from app.services.jira_migration.state import STATE_PENDING, set_migration_state
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
)
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

NOW = datetime(2026, 10, 14, 12, 0)
IVANOV_DC = dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")
PETROV_DC = dc_user("JIRAUSER7", "Petrov_P", "Петров Пётр")
STRANGER_DC = dc_user("JIRAUSER9", "Stranger", "Посторонний")


def seed_world(db: Session) -> dict[str, str]:
    set_migration_state(db, STATE_PENDING)
    db.add(AppSetting(key="jira_team_field_id", value="customfield_11526"))
    db.add(ScopeProject(jira_project_key="OS", jira_project_id="11029"))
    os_project = make_project(db, "OS", "11029")
    pmd = make_project(db, "PMD", "11015")
    a = make_issue(db, os_project, "OS-91030", "683676")
    b = make_issue(db, pmd, "PMD-19591", "258783", team="Команда Б")
    gone = make_issue(db, os_project, "OS-1", "500001")
    make_issue(db, os_project, "OS-2", "500002")
    db.add(BacklogItem(title="Идея", issue_id=gone.id))
    ivanov = make_employee(db, "cloud-ivanov", "Иванов Иван")
    petrov = make_employee(db, "cloud-petrov", "Петров Пётр")
    for day in (10, 11, 12):
        make_worklog(db, a, ivanov, datetime(2026, 9, day, 10, 0), 3600, f"w{day}")
    make_worklog(db, b, ivanov, datetime(2026, 9, 1, 2, 30), 1800, "w1")
    ids = {"ivanov": ivanov.id, "petrov": petrov.id}
    db.commit()
    return ids


def dc_world(**overrides: Any) -> FakeJira:
    params: dict[str, Any] = {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {
            "OS": [("OS-91030", "258783"), ("OS-5", "300005")],
            "PMD": [("PMD-19591", "999999")],
        },
        "worklogs": [
            dc_worklog("9001", "258783", IVANOV_DC, "2026-09-10T07:00:00.000+0000", 3600),
            dc_worklog("9002", "258783", IVANOV_DC, "2026-09-11T07:00:00.000+0000", 3600),
            dc_worklog("9003", "258783", IVANOV_DC, "2026-09-12T07:00:00.000+0000", 3600),
            dc_worklog("9004", "999999", IVANOV_DC, "2026-08-31T23:30:00.000+0000", 1800),
            dc_worklog("9005", "777", STRANGER_DC, "2026-09-10T07:00:00.000+0000", 3600),
        ],
        "users": [IVANOV_DC, PETROV_DC],
        "fields": [{"id": "customfield_11092", "name": "Продуктовая команда", "custom": True}],
    }
    params.update(overrides)
    return FakeJira(**params)
