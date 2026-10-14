"""Иерархия Jira DC: подзадача → parent, задача → «Ссылка на эпик», эпик → «Parent Link»."""
import logging
from unittest.mock import AsyncMock, MagicMock

from app.connectors.schemas import JiraIssueSchema
from app.models import AppSetting, Issue, Project
from app.services.sync_service import SyncService, _extract_sprints, _parent_key_of
from tests.dc_fixtures import load_dc

IDS = {
    "jira_epic_link_field_id": "customfield_10107",
    "jira_parent_link_field_id": "customfield_10100",
}


def _fields(name: str):
    return JiraIssueSchema.model_validate(load_dc(name)).fields


def test_parent_from_epic_link():
    assert _parent_key_of(_fields("issue_OS-91030.json"), IDS) == "OS-84096"


def test_parent_from_parent_link():
    assert _parent_key_of(_fields("issue_OS-89194.json"), IDS) == "RFA-4599"
    assert _parent_key_of(_fields("issue_RFA-5020.json"), IDS) == "RFA-4832"


def test_subtask_parent_wins():
    raw = load_dc("issue_OS-91030.json")
    raw["fields"]["parent"] = {"id": "1", "key": "OS-1"}
    assert _parent_key_of(JiraIssueSchema.model_validate(raw).fields, IDS) == "OS-1"


def test_no_configured_fields_no_parent():
    assert _parent_key_of(_fields("issue_OS-91030.json"), {}) is None


def test_sprint_parsed_from_dc_string():
    fields = load_dc("issue_OS-91030.json")["fields"]
    assert _extract_sprints(fields, "customfield_10109") == (
        "OS 20 SKLAD 16/10/2026", ["OS 20 SKLAD 16/10/2026"],
    )


async def test_auto_field_ids_found_by_type(db_session):
    db_session.add(AppSetting(key="jira_sprint_field_id", value="customfield_99999"))
    db_session.commit()
    jira = MagicMock()
    jira.get_fields = AsyncMock(return_value=load_dc("fields.json"))

    await SyncService(db_session, jira)._ensure_auto_field_ids()

    settings = {r.key: r.value for r in db_session.query(AppSetting).all()}
    assert settings["jira_sprint_field_id"] == "customfield_99999", "ручное значение не трогаем"
    assert settings["jira_epic_link_field_id"] == "customfield_10107"
    assert settings["jira_parent_link_field_id"] == "customfield_10100"


async def test_auto_field_ids_skip_jira_when_all_set(db_session):
    for key, value in {**IDS, "jira_sprint_field_id": "customfield_10109"}.items():
        db_session.add(AppSetting(key=key, value=value))
    db_session.commit()
    jira = MagicMock()
    jira.get_fields = AsyncMock(return_value=[])

    await SyncService(db_session, jira)._ensure_auto_field_ids()
    jira.get_fields.assert_not_called()


async def test_auto_field_ids_warn_on_failure_and_missing_epic_link(db_session, caplog):
    jira = MagicMock()
    jira.get_fields = AsyncMock(side_effect=RuntimeError("нет связи"))
    svc = SyncService(db_session, jira)

    with caplog.at_level(logging.WARNING, logger="jira_analytics.sync"):
        await svc._ensure_auto_field_ids()
        await svc._ensure_auto_field_ids()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert sum("нет связи" in m for m in warnings) == 2
    assert sum("Ссылка на эпик" in m for m in warnings) == 1, "раз за проход"


async def test_epic_parent_link_pending_not_flagged_as_parent_change(db_session):
    """Эпик уже с родителем; «Parent Link» указывает на инициативу, которой ещё
    нет в базе (достроится вторым проходом) — это не потеря родителя."""
    raw = load_dc("issue_OS-89194.json")
    db_session.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    db_session.flush()
    db_session.add_all([
        Issue(id="i-old", key="RFA-1", jira_issue_id="j-old", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-os"),
        Issue(id="i-epic", key=raw["key"], jira_issue_id=raw["id"], summary="Эпик",
              issue_type=raw["fields"]["issuetype"]["name"], status="Open",
              project_id="p-os", parent_id="i-old"),
    ])
    db_session.commit()
    svc = SyncService(db_session, MagicMock())
    svc._switch_off_new_service_epic = MagicMock()

    svc._upsert_issue(
        JiraIssueSchema.model_validate(raw), "p-os", parent_id=None, planned_field_ids=IDS,
    )

    svc._switch_off_new_service_epic.assert_not_called()


async def test_sync_links_story_to_epic_by_epic_link(db_session):
    db_session.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    for key, value in IDS.items():
        db_session.add(AppSetting(key=key, value=value))
    db_session.commit()
    requested: list[str] = []

    async def fake_iter_issues(jql, max_results, fields, expand=None):
        requested.extend(fields)
        # История раньше эпика: родитель достраивается вторым проходом.
        yield JiraIssueSchema.model_validate(load_dc("issue_OS-92392.json"))  # → эпик OS-89194
        yield JiraIssueSchema.model_validate(load_dc("issue_OS-89194.json"))  # → RFA-4599, его нет

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_fields = AsyncMock(return_value=load_dc("fields.json"))
    jira.get_statuses = AsyncMock(return_value=[])
    await SyncService(db_session, jira).sync_issues(project_keys=["OS"], incremental=False)

    story = db_session.query(Issue).filter_by(key="OS-92392").one()
    epic = db_session.query(Issue).filter_by(key="OS-89194").one()
    assert story.parent_id == epic.id
    assert epic.parent_id is None
    assert "customfield_10107" in requested
    assert "customfield_10100" in requested
