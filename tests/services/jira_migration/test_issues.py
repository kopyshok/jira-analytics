"""Задачи при переезде: служебные данные сервиса и новые id по ключам."""
from datetime import datetime

import pytest

from app.models import (
    BacklogItem,
    CategoryOverride,
    IssueClassification,
    MandatoryWorkType,
    PlanAudit,
    PlanningScenario,
    ProjectAISummary,
    ScenarioAllocationSnapshot,
    ScenarioRevision,
    ScopeProject,
    ScopeRoot,
    Team,
    TeamDeskDailyRate,
    TeamDeskMark,
    TeamSubgroup,
)
from app.services.jira_migration.issues import (
    REASON_BACKLOG,
    REASON_CATEGORY_OVERRIDE,
    REASON_CLASSIFICATION,
    REASON_DAILY_RATE,
    REASON_HOURS_CHOICE,
    REASON_MANUAL_CATEGORY,
    REASON_MANUAL_HOURS,
    REASON_MANUAL_SUBGROUP,
    REASON_PLAN_AUDIT,
    REASON_SCENARIO,
    REASON_SCOPE_ROOT,
    REASON_TEAM_DESK_MARK,
    classify_missing,
    scan_issue_ids,
    service_data_reasons,
)
from tests.services.jira_migration.factory import make_issue, make_project
from tests.services.jira_migration.fake_jira import FakeJira

NOW = datetime(2026, 10, 14, 12, 0)


def _work_type(db):
    work_type = MandatoryWorkType(code="migration_test_wt", label="Тестовый вид работ")
    db.add(work_type)
    db.flush()
    return work_type


def test_defaults_and_automatic_rows_are_not_service_data(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1",
                       include_in_analysis=False, category_verified=False, parent_changed=True)
    work_type = _work_type(db_session)
    db_session.add_all([
        IssueClassification(issue_id=issue.id, work_type_id=work_type.id, input_hash="h",
                            dictionary_version=1, prompt_version="v3"),
        PlanAudit(issue_id=issue.id, role="dev", source="jira_sync", value_after=5.0),
        PlanAudit(issue_id=issue.id, role="dev", source="jira_sync_conflict", value_after=6.0),
        ProjectAISummary(issue_id=issue.id, goals_json="[]", result_checklist_json="[]",
                         status_text="", workload_summary="", generated_at=NOW, model_used="m"),
    ])
    db_session.commit()

    assert service_data_reasons(db_session, ["OS-1"]) == {}


def test_each_kind_of_service_data_is_found(db_session):
    project = make_project(db_session)
    keys = [f"OS-{n}" for n in range(1, 13)]
    issues = {key: make_issue(db_session, project, key, str(100 + n)) for n, key in enumerate(keys)}
    work_type = _work_type(db_session)
    team = Team(name="Команда для группы")
    db_session.add(team)
    db_session.flush()
    subgroup = TeamSubgroup(team_id=team.id, name="Группа 1")
    scenario = PlanningScenario(name="Q3", status="approved")
    db_session.add_all([subgroup, scenario])
    db_session.flush()
    revision = ScenarioRevision(scenario_id=scenario.id, revision_number=1, approved_at=NOW)
    db_session.add(revision)
    db_session.flush()
    db_session.add_all([
        BacklogItem(title="Идея", issue_id=issues["OS-1"].id),
        IssueClassification(issue_id=issues["OS-2"].id, work_type_id=work_type.id, input_hash="manual",
                            dictionary_version=1, prompt_version="manual"),
        PlanAudit(issue_id=issues["OS-3"].id, role="dev", source="manual_edit", value_after=8.0),
        TeamDeskMark(issue_id=issues["OS-4"].id, flag="stale", signature="s"),
        TeamDeskDailyRate(issue_id=issues["OS-5"].id, hours=2.0),
        ScenarioAllocationSnapshot(revision_id=revision.id, title="Инициатива", issue_id=issues["OS-6"].id),
        CategoryOverride(jira_issue_key="OS-7", category_code="dev"),
        ScopeRoot(category_code="dev", jira_issue_key="OS-8"),
    ])
    issues["OS-9"].assigned_category = "dev"
    issues["OS-10"].assigned_subgroup_id = subgroup.id
    issues["OS-11"].planned_qa_hours_manual = 12.0
    issues["OS-12"].planned_hours_choice = {"dev": {"source": "manual", "fingerprint": "x"}}
    db_session.commit()

    assert service_data_reasons(db_session, keys) == {
        "OS-1": [REASON_BACKLOG],
        "OS-2": [REASON_CLASSIFICATION],
        "OS-3": [REASON_PLAN_AUDIT],
        "OS-4": [REASON_TEAM_DESK_MARK],
        "OS-5": [REASON_DAILY_RATE],
        "OS-6": [REASON_SCENARIO],
        "OS-7": [REASON_CATEGORY_OVERRIDE],
        "OS-8": [REASON_SCOPE_ROOT],
        "OS-9": [REASON_MANUAL_CATEGORY],
        "OS-10": [REASON_MANUAL_SUBGROUP],
        "OS-11": [REASON_MANUAL_HOURS],
        "OS-12": [REASON_HOURS_CHOICE],
    }


def test_classify_missing_splits_and_gives_summaries(db_session):
    project = make_project(db_session)
    with_data = make_issue(db_session, project, "OS-1", "1")
    make_issue(db_session, project, "OS-2", "2")
    db_session.add(BacklogItem(title="Идея", issue_id=with_data.id))
    db_session.commit()

    deletable, rows = classify_missing(db_session, ["OS-1", "OS-2"])

    assert deletable == ["OS-2"]
    assert rows == [{"key": "OS-1", "summary": "Задача OS-1", "reasons": [REASON_BACKLOG]}]


async def test_scan_maps_db_keys_and_counts(db_session):
    os_project = make_project(db_session, "OS", "11029")
    pmd = make_project(db_session, "PMD", "11015")
    make_project(db_session, "OLD", "11999")
    gone = make_project(db_session, "GONE", "12000")
    make_issue(db_session, os_project, "OS-91030", "683676")
    make_issue(db_session, os_project, "OS-1", "500001")
    make_issue(db_session, pmd, "PMD-19591", "258783")
    make_issue(db_session, gone, "GONE-1", "600001")
    db_session.add(ScopeProject(jira_project_key="OS", jira_project_id="11029"))
    db_session.commit()
    dc_projects = {"OS": "10901", "PMD": "10902", "OLD": "10903"}
    jira = FakeJira(projects=dc_projects, issues={
        "OS": [("OS-91030", "258783"), ("OS-5", "300005")],
        "PMD": [("PMD-19591", "999999"), ("PMD-2", "999998")],
    })
    seen: list[int] = []

    scan = await scan_issue_ids(db_session, jira, dc_projects, on_progress=seen.append)

    assert scan.key_to_id == {"OS-91030": "258783", "PMD-19591": "999999"}
    assert (scan.db_total, scan.matched, scan.new_in_dc) == (4, 2, 1)
    assert scan.missing == ["OS-1"]
    assert scan.project_not_found == [{"key": "GONE", "issues": 1}]
    assert scan.projects == [
        {"key": "GONE", "found": False}, {"key": "OLD", "found": True},
        {"key": "OS", "found": True}, {"key": "PMD", "found": True},
    ]
    assert [c for c in jira.calls if c[0] == "iter_issue_keys"] == [
        ("iter_issue_keys", 'project = "OS"'), ("iter_issue_keys", 'project = "PMD"'),
    ]
    assert seen[-1] == 4


def test_classify_missing_lists_each_key_once(db_session):
    project = make_project(db_session)
    with_data = make_issue(db_session, project, "OS-1", "1")
    make_issue(db_session, project, "OS-2", "2")
    db_session.add(BacklogItem(title="Идея", issue_id=with_data.id))
    db_session.commit()

    deletable, rows = classify_missing(db_session, ["OS-2", "OS-1", "OS-2", "OS-1"])

    assert deletable == ["OS-2"]
    assert [row["key"] for row in rows] == ["OS-1"]


async def test_issues_of_project_absent_in_dc_are_never_deleted(db_session):
    os_project = make_project(db_session, "OS", "11029")
    renamed = make_project(db_session, "REN", "11500")
    make_issue(db_session, os_project, "OS-1", "500001")
    make_issue(db_session, renamed, "REN-1", "700001")
    make_issue(db_session, renamed, "REN-2", "700002")
    db_session.add(ScopeProject(jira_project_key="REN", jira_project_id="11500"))
    db_session.commit()
    dc_projects = {"OS": "10901"}
    jira = FakeJira(projects=dc_projects, issues={"OS": []})

    scan = await scan_issue_ids(db_session, jira, dc_projects)
    deletable, rows = classify_missing(db_session, scan.missing)

    assert scan.missing == ["OS-1"]
    assert scan.project_not_found == [{"key": "REN", "issues": 2}]
    assert deletable == ["OS-1"] and rows == []
    assert {"key": "REN", "found": False} in scan.projects
    assert [c for c in jira.calls if c[0] == "iter_issue_keys"] == [("iter_issue_keys", 'project = "OS"')]


async def test_out_of_scope_project_in_dc_is_mapped(db_session):
    old = make_project(db_session, "OLD", "11999")
    make_issue(db_session, old, "OLD-7", "800007")
    db_session.add(ScopeProject(jira_project_key="OS", jira_project_id="11029"))
    db_session.commit()
    dc_projects = {"OS": "10901", "OLD": "10903"}
    jira = FakeJira(projects=dc_projects, issues={"OLD": [("OLD-7", "400007"), ("OLD-8", "400008")]})

    scan = await scan_issue_ids(db_session, jira, dc_projects)

    assert scan.key_to_id == {"OLD-7": "400007"}
    assert scan.missing == [] and scan.project_not_found == []
    assert scan.new_in_dc == 0


class _FailingOnSecondProject(FakeJira):
    """Первый проект читается целиком, на втором Jira обрывает выдачу."""

    async def iter_issue_keys(self, jql: str, page_size: int = 1000):
        if "PMD" in jql:
            yield "PMD-1", "900001"
            raise RuntimeError("Jira оборвала выдачу")
        async for pair in super().iter_issue_keys(jql, page_size):
            yield pair


async def test_scan_failure_mid_way_propagates(db_session):
    os_project = make_project(db_session, "OS", "11029")
    pmd = make_project(db_session, "PMD", "11015")
    make_issue(db_session, os_project, "OS-1", "500001")
    make_issue(db_session, pmd, "PMD-1", "600001")
    db_session.commit()
    dc_projects = {"OS": "10901", "PMD": "10902"}
    jira = _FailingOnSecondProject(projects=dc_projects, issues={"OS": [("OS-1", "100001")]})

    with pytest.raises(RuntimeError, match="оборвала"):
        await scan_issue_ids(db_session, jira, dc_projects)
