"""Состояние «готово к применению»: база до переезда, свежий отчёт, все решения приняты.

OS-91030 получает в новой Jira id 258783 — в базе это старый id PMD-19591.
OS-1 исчез без данных сервиса (удалится сам), OS-2 исчез с бэклогом
(решение «удалить»), OS-3 исчез с отметкой стола тимлида (решение
«оставить»), OS-4 — подзадача OS-2, есть в новой Jira.
Иванов найден по списаниям, Петров привязан решением, Сидоров — без привязки.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    IssueLink,
    KpiApproval,
    ScopeProject,
    ScopeRoot,
    TeamDeskMark,
    User,
)
from app.services.jira_migration import store
from app.services.jira_migration.fields import build_field_rows, ensure_field_snapshot
from app.services.jira_migration.state import STATE_PENDING, set_migration_state
from app.services.plan_sources import Candidate, fingerprint
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
    seed_report,
)

DC_FIELDS = [
    {"id": "customfield_11092", "name": "Продуктовая команда", "custom": True},
    {"id": "customfield_11097", "name": "Разработка (ч)", "custom": True},
    {"id": "customfield_11034", "name": "Оценка 1С (ч)", "custom": True},
    {"id": "customfield_10109", "name": "Спринт", "custom": True},
]
PLANNED_DEV = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
], ensure_ascii=False, separators=(",", ":"))
OLD_CANDIDATES = [
    Candidate("customfield_12432", "Разработка (ч)", 40.0),
    Candidate("customfield_14648", "Оценка 1С (ч)", 56.0),
]
IVANOV_DC = {"key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван"}


def seed_ready(db: Session, finished_at: datetime) -> dict[str, str]:
    set_migration_state(db, STATE_PENDING)
    db.add_all([
        AppSetting(key="jira_team_field_id", value="customfield_11526"),
        AppSetting(key="jira_planned_dev_hours_field_id", value=PLANNED_DEV),
        AppSetting(key="jira_sprint_field_id", value="customfield_10019"),
        AppSetting(key="jira_epic_link_field_id", value="customfield_77777"),
    ])
    db.commit()
    snapshot = ensure_field_snapshot(db)

    os_project = make_project(db, "OS", "11029")
    pmd = make_project(db, "PMD", "11015")
    a = make_issue(db, os_project, "OS-91030", "683676")
    b = make_issue(db, pmd, "PMD-19591", "258783", team="Команда Б")
    os1 = make_issue(db, os_project, "OS-1", "500001")
    os2 = make_issue(db, os_project, "OS-2", "500002")
    os3 = make_issue(db, os_project, "OS-3", "500003")
    os4 = make_issue(db, os_project, "OS-4", "500004", parent_id=os2.id)
    a.planned_hours_sources = {"dev": [c.to_dict() for c in OLD_CANDIDATES]}
    a.planned_hours_choice = {
        "dev": {"source": "customfield_14648", "fingerprint": fingerprint(OLD_CANDIDATES)},
    }
    a.assignee_account_id = "cloud-ivanov"
    a.reporter_account_id = "cloud-petrov"
    a.developer_account_id = "cloud-sidorov"
    b.developer_account_id = "someone-else"

    ivanov = make_employee(db, "cloud-ivanov", "Иванов Иван")
    petrov = make_employee(db, "cloud-petrov", "Петров Пётр")
    sidorov = make_employee(db, "cloud-sidorov", "Сидоров Сидор")
    make_worklog(db, a, ivanov, datetime(2026, 9, 10, 10, 0), 3600, "850609")
    db.add_all([
        BacklogItem(title="Инициатива", issue_id=os2.id, assignee_jira_account_at_choice="cloud-ivanov"),
        TeamDeskMark(issue_id=os3.id, flag="stale", signature="s"),
        IssueLink(source_issue_id=os2.id, target_issue_id=a.id, link_type="Relates"),
        Comment(jira_comment_id="c1", issue_id=a.id, body="текст", author_id=ivanov.id),
        CategoryMapping(entity_type="worklog", entity_id="old-worklog", category="dev"),
        CategoryMapping(entity_type="issue", entity_id=os1.id, category="dev"),
        KpiApproval(
            team="Команда А", year=2026, quarter=3, approved_by="Админ", approved_at=finished_at,
            payload_json=json.dumps({"rows": [{"employee_id": ivanov.id, "account_id": "cloud-ivanov"}]}),
        ),
        ScopeProject(jira_project_key="OS", jira_project_id="11029"),
        ScopeRoot(category_code="dev", jira_issue_key="OS-91030", jira_issue_id="683676"),
    ])
    user = db.query(User).first()
    user.team_desk_filter = {"teams": ["Команда А"], "developers": ["cloud-sidorov", "unknown"]}
    ids = {
        "a": a.id, "b": b.id, "os1": os1.id, "os2": os2.id, "os3": os3.id, "os4": os4.id,
        "ivanov": ivanov.id, "petrov": petrov.id, "sidorov": sidorov.id, "user": user.id,
    }
    db.commit()

    not_found = {"worklogs": 0, "matched": 0, "status": "not_found", "candidates": [], "auto": None}
    report = {
        "probe": [],
        "fields": build_field_rows(snapshot, DC_FIELDS),
        "dc_fields": DC_FIELDS,
        "projects": [{"key": "OS", "found": True}, {"key": "PMD", "found": True}],
        "issues": {
            "db_total": 6, "matched": 3, "new_in_dc": 0, "missing": ["OS-1", "OS-2", "OS-3"],
            "project_not_found": [],
        },
        "offset_hours": 3,
        "offset_matches": 1,
        "offset_sample": 1,
        "offset_unexpected": False,
        "people": [
            {"employee_id": ids["ivanov"], "display_name": "Иванов Иван", "worklogs": 1, "matched": 5,
             "status": "by_hours", "candidates": [{**IVANOV_DC, "votes": 5}], "auto": IVANOV_DC},
            {"employee_id": ids["petrov"], "display_name": "Петров Пётр", **not_found},
            {"employee_id": ids["sidorov"], "display_name": "Сидоров Сидор", **not_found},
        ],
        "hours": {
            "rows": [{"team": "Команда А", "month": "2026-09", "db_hours": 1.0, "dc_hours": 1.0,
                      "diff_pct": 0.0, "flagged": False}],
            "db_worklogs": 1, "dc_worklogs": 1, "dc_worklogs_total": 1,
        },
        "db_worklogs_min_date": "2026-09-10",
    }
    maps = {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {"OS-91030": "258783", "PMD-19591": "999999", "OS-4": "500100"},
    }
    ids["report"] = seed_report(db, report, maps, finished_at)
    store.set_decision(db, store.KIND_ISSUE, "OS-2", {"action": "delete"}, "Админ")
    store.set_decision(db, store.KIND_ISSUE, "OS-3", {"action": "keep"}, "Админ")
    store.set_decision(db, store.KIND_PERSON, ids["petrov"],
                       {"action": "bind", "key": "JIRAUSER7", "name": "Petrov_P",
                        "display_name": "Петров Пётр"}, "Админ")
    store.set_decision(db, store.KIND_PERSON, ids["sidorov"], {"action": "unbind"}, "Админ")
    return ids
