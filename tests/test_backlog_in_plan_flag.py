"""Галочка «В план» на уровне BacklogService.

Служебный эпик (Дискавери внутри RFA) создаётся выключенным и не попадает в
черновики; обычная задача — включённой. В режиме «RFA целиком» дети RFA
исключаются, но служебный эпик — нет (его часы сверх родителя).
"""
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import (
    BacklogService,
    mode_excluded_backlog_ids,
    not_in_plan_backlog_ids,
    service_epic_backlog_ids,
)


def _seed(db, *, rule_enabled: bool = True) -> None:
    db.add_all([
        HierarchyRule(
            priority=5, project_key="RFA", issue_type="Эпик",
            require_no_parent=False, require_parent=True,
            is_container=False, is_enabled=rule_enabled, description="svc",
        ),
        HierarchyRule(
            priority=10, project_key="RFA", issue_type=None,
            require_no_parent=False, require_parent=False,
            is_container=True, is_enabled=True,
        ),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-story", key="RFA-3", jira_issue_id="j3", summary="Часть RFA", issue_type="История",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        PlanningScenario(id="s-draft", name="draft", year=2026, quarter="Q4", status="draft", team="T1"),
    ])
    db.flush()


def _sync_all(db) -> dict[str, BacklogItem]:
    svc = BacklogService(db)
    for iid in ("i-rfa", "i-disc", "i-story"):
        svc.sync_from_issue(db.get(Issue, iid))
    db.flush()
    return {bi.issue_id: bi for bi in db.query(BacklogItem).all()}


def _draft_alloc_count(db, item_id: str) -> int:
    return db.query(ScenarioAllocation).filter_by(scenario_id="s-draft", backlog_item_id=item_id).count()


def test_new_service_epic_is_off_and_not_in_draft(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    assert items["i-disc"].included_in_planning is False
    assert items["i-rfa"].included_in_planning is True
    assert _draft_alloc_count(db_session, items["i-disc"].id) == 0
    assert _draft_alloc_count(db_session, items["i-rfa"].id) == 1


def test_disabled_rule_means_no_service_epic(db_session):
    _seed(db_session, rule_enabled=False)
    items = _sync_all(db_session)
    assert items["i-disc"].included_in_planning is True
    assert service_epic_backlog_ids(db_session) == set()


def test_service_epic_not_excluded_by_whole_mode(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    excluded = mode_excluded_backlog_ids(db_session)
    assert items["i-disc"].id not in excluded, "Дискавери идёт сверх RFA"
    assert items["i-story"].id in excluded, "обычный ребёнок RFA целиком — исключён"


def test_not_in_plan_set_and_ensure_skips_it(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    assert not_in_plan_backlog_ids(db_session) == {items["i-disc"].id}
    BacklogService(db_session)._ensure_draft_allocations(items["i-disc"].id)
    assert _draft_alloc_count(db_session, items["i-disc"].id) == 0
