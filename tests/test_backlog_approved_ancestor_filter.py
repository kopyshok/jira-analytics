"""Если предок-инициатива уже включён в утверждённый сценарий, его дети
не должны появляться как отдельные кандидаты в новых/черновых сценариях.

Корень проблемы: при approve у включённой инициативы переписывается
``assigned_category="quarterly_tasks"``. Резолвер наследует категорию на
детей через walk-up по ``parent_id`` — дети попадают в TRACKED_CATEGORIES,
BacklogService создаёт под них BacklogItem, и они начинают отображаться
наравне с самостоятельными инициативами.
"""

import pytest

from app.models import (
    BacklogItem,
    Issue,
    PlanningScenario,
    Project,
    ScenarioAllocation,
)
from app.services.backlog_service import (
    BacklogService,
    descendant_backlog_ids_of_included_ancestors,
    has_included_ancestor,
)


@pytest.fixture
def proj(db_session):
    p = Project(
        id="aa-p1",
        jira_project_id="aa-p1-jira",
        key="AA",
        name="AA",
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_issue(db, proj, key, parent_id=None, category="initiatives_rfa"):
    i = Issue(
        id=key,
        jira_issue_id=f"jira-{key}",
        key=key,
        summary=f"Issue {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        parent_id=parent_id,
    )
    db.add(i)
    db.commit()
    return i


def _approve_with_included(db, scenario_id, issue, ratio=0.5):
    """Создать BacklogItem для issue + allocation в approved-сценарии с галочкой."""
    bi = BacklogItem(
        id=f"bi-{issue.id}",
        title=issue.summary,
        issue_id=issue.id,
        opo_analyst_ratio=ratio,
    )
    db.add(bi)
    db.flush()
    db.add(
        ScenarioAllocation(
            scenario_id=scenario_id,
            backlog_item_id=bi.id,
            included_flag=True,
            planned_hours=10,
        )
    )
    db.commit()
    return bi


@pytest.fixture
def approved_scenario(db_session, proj):
    s = PlanningScenario(
        id="aa-approved",
        name="Approved",
        year=2026,
        quarter=2,
        status="approved",
    )
    db_session.add(s)
    db_session.commit()
    return s


def test_descendant_of_approved_ancestor_detected(db_session, proj, approved_scenario):
    parent = _make_issue(db_session, proj, "AA-PARENT")
    child = _make_issue(db_session, proj, "AA-CHILD", parent_id=parent.id)
    grand = _make_issue(db_session, proj, "AA-GRAND", parent_id=child.id)

    _approve_with_included(db_session, approved_scenario.id, parent)

    assert has_included_ancestor(db_session, child) is True
    assert has_included_ancestor(db_session, grand) is True
    assert has_included_ancestor(db_session, parent) is False


def test_no_ancestor_returns_empty(db_session, proj):
    issue = _make_issue(db_session, proj, "AA-LONE")
    assert has_included_ancestor(db_session, issue) is False


def test_ancestor_not_included_does_not_count(db_session, proj, approved_scenario):
    parent = _make_issue(db_session, proj, "AA-PARENT2")
    child = _make_issue(db_session, proj, "AA-CHILD2", parent_id=parent.id)
    bi = BacklogItem(id="bi-parent2", title=parent.summary, issue_id=parent.id)
    db_session.add(bi)
    db_session.add(
        ScenarioAllocation(
            scenario_id=approved_scenario.id,
            backlog_item_id=bi.id,
            included_flag=False,  # not included
            planned_hours=0,
        )
    )
    db_session.commit()
    assert has_included_ancestor(db_session, child) is False


def test_sync_skips_allocation_for_descendant_of_approved(
    db_session, proj, approved_scenario
):
    """sync_from_issue не должен доливать allocation для ребёнка утверждённой
    инициативы в существующем draft-сценарии."""
    parent = _make_issue(db_session, proj, "AA-P3")
    _approve_with_included(db_session, approved_scenario.id, parent)

    draft = PlanningScenario(
        id="aa-draft", name="Draft", year=2026, quarter=3, status="draft"
    )
    db_session.add(draft)
    db_session.commit()

    child = _make_issue(db_session, proj, "AA-C3", parent_id=parent.id)
    svc = BacklogService(db_session)
    bi = svc.sync_from_issue(child)
    db_session.commit()

    assert bi is not None  # BacklogItem всё равно создан
    allocs = (
        db_session.query(ScenarioAllocation)
        .filter_by(backlog_item_id=bi.id, scenario_id=draft.id)
        .all()
    )
    assert allocs == []


def test_descendant_set_excludes_self(db_session, proj, approved_scenario):
    parent = _make_issue(db_session, proj, "AA-P4")
    child = _make_issue(db_session, proj, "AA-C4", parent_id=parent.id)
    bi_parent = _approve_with_included(db_session, approved_scenario.id, parent)

    bi_child = BacklogItem(id="bi-child4", title=child.summary, issue_id=child.id)
    db_session.add(bi_child)
    db_session.commit()

    descendants = descendant_backlog_ids_of_included_ancestors(db_session)
    assert bi_child.id in descendants
    assert bi_parent.id not in descendants


def test_no_approved_no_descendants(db_session, proj):
    parent = _make_issue(db_session, proj, "AA-P5")
    child = _make_issue(db_session, proj, "AA-C5", parent_id=parent.id)
    bi_p = BacklogItem(id="bi-p5", title="p", issue_id=parent.id)
    bi_c = BacklogItem(id="bi-c5", title="c", issue_id=child.id)
    db_session.add_all([bi_p, bi_c])
    db_session.commit()
    assert descendant_backlog_ids_of_included_ancestors(db_session) == set()
