"""Tests for BacklogService.sync_from_issue — auto-populate backlog from
Issue with category='initiatives_rfa' («Инициативы и RFA»)."""

import pytest

from app.models import BacklogItem, Issue, Project


@pytest.fixture
def proj(db_session):
    p = Project(
        id="p1",
        jira_project_id="p1-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_issue(db, proj, key, category, **planned):
    i = Issue(
        id=key,
        jira_issue_id=f"jira-{key}",
        key=key,
        summary=f"Epic {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        **planned,
    )
    db.add(i)
    db.commit()
    return i


def test_sync_creates_backlog_item_when_category_matches(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-1",
        "initiatives_rfa",
        planned_analyst_hours=40,
        planned_dev_hours=40,
        planned_qa_hours=20,
        planned_opo_hours=20,
        impact="high",
        risk="medium",
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.issue_id == issue.id
    assert item.title == "Epic RFA-1"
    assert item.project_id == proj.id
    assert item.estimate_analyst_hours == 40
    assert item.estimate_dev_hours == 40
    assert item.estimate_qa_hours == 20
    assert item.estimate_opo_hours == 20
    assert item.estimate_hours == 120  # sum
    assert item.impact == "high"
    assert item.risk == "medium"
    assert item.opo_analyst_ratio == 0.5  # default


def test_sync_updates_existing_backlog_item(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-2",
        "initiatives_rfa",
        planned_analyst_hours=10,
        planned_dev_hours=10,
        planned_qa_hours=0,
        planned_opo_hours=0,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item.estimate_hours == 20

    issue.planned_dev_hours = 50
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.estimate_dev_hours == 50
    assert item.estimate_hours == 60


def test_sync_preserves_opo_analyst_ratio(db_session, proj):
    """opo_analyst_ratio — local, Jira sync does not overwrite."""
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-3",
        "initiatives_rfa",
        planned_opo_hours=10,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    item.opo_analyst_ratio = 0.7
    db_session.commit()

    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.opo_analyst_ratio == 0.7


def test_sync_seeds_priority_only_on_create(db_session, proj):
    """priority — auto из Jira только при создании; PM правит вручную, ресинки не трогают."""
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-PR-1", "initiatives_rfa")
    issue.priority = "High"
    db_session.commit()

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item.priority == 2  # High → 2 при создании

    # PM выставил вручную — следующий синк сохраняет.
    item.priority = 99
    db_session.commit()
    issue.priority = "Lowest"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.priority == 99

    # Изменение Jira priority не затрагивает ручной приоритет.
    issue.priority = None
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.priority == 99


def test_sync_archives_item_when_category_leaves_backlog(db_session, proj):
    """Категория ушла с initiatives_rfa → archived_at проставлен, issue_id жив."""
    from app.services.backlog_service import BacklogService
    from app.models import BacklogItem

    issue = _make_issue(db_session, proj, "RFA-4", "initiatives_rfa")
    svc = BacklogService(db_session)
    svc.sync_from_issue(issue)
    db_session.commit()

    issue.category = "development"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    item = db_session.query(BacklogItem).filter_by(issue_id=issue.id).one()
    assert item.archived_at is not None
    assert item.issue_id == issue.id  # link preserved


def test_sync_removes_draft_allocation_when_category_leaves(db_session, proj):
    """Архивная категория → allocation в черновом сценарии удаляется."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(
        id="s1", name="Q2 draft", year=2026, quarter="Q2", status="draft"
    )
    db_session.add(scenario)
    db_session.add(
        ScenarioAllocation(
            id="a1", scenario_id=scenario.id, backlog_item_id=item.id,
            included_flag=True, planned_hours=0,
        )
    )
    db_session.commit()

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(item)
    assert item.archived_at is not None
    assert item.issue_id == issue.id
    assert (
        db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count()
        == 0
    )


def test_sync_preserves_approved_allocation_when_category_leaves(db_session, proj):
    """Архивная категория → allocation в утверждённом сценарии не трогаем."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5A", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(
        id="s-appr", name="Q1 approved", year=2026, quarter="Q1", status="approved"
    )
    db_session.add(scenario)
    db_session.add(
        ScenarioAllocation(
            id="a-appr", scenario_id=scenario.id, backlog_item_id=item.id,
            included_flag=True, planned_hours=40,
        )
    )
    db_session.commit()

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(item)
    assert item.archived_at is not None
    assert (
        db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count()
        == 1
    )


def test_sync_restores_item_when_category_returns(db_session, proj):
    """Категория снова initiatives_rfa → archived_at обнуляется."""
    from app.services.backlog_service import BacklogService
    from app.models import BacklogItem

    issue = _make_issue(db_session, proj, "RFA-R", "initiatives_rfa")
    svc = BacklogService(db_session)
    svc.sync_from_issue(issue)
    db_session.commit()

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    item = db_session.query(BacklogItem).filter_by(issue_id=issue.id).one()
    assert item.archived_at is not None

    issue.category = "initiatives_rfa"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.archived_at is None


def test_sync_ignores_issue_without_backlog_category(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-6", "development")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item is None
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0


def test_sync_creates_allocations_in_draft_scenarios(db_session, proj):
    """Новый элемент бэклога → allocation в каждом draft-сценарии, в approved — нет."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add_all([
        PlanningScenario(id="d1", name="Draft 1", year=2026, quarter="Q2", status="draft"),
        PlanningScenario(id="d2", name="Draft 2", year=2026, quarter="Q3", status="draft"),
        PlanningScenario(id="a1", name="Approved 1", year=2026, quarter="Q1", status="approved"),
    ])
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N1", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    allocations = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).all()
    scenario_ids = {a.scenario_id for a in allocations}
    assert scenario_ids == {"d1", "d2"}
    for a in allocations:
        assert a.included_flag is False
        assert a.planned_hours == 0


def test_sync_preserves_existing_allocation_values(db_session, proj):
    """Если в черновике уже есть allocation с проставленными значениями —
    повторный sync_from_issue не перетирает."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-keep", name="Draft keep", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N2", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    # PM включил задачу в черновик и проставил часы.
    alloc = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).one()
    alloc.included_flag = True
    alloc.planned_hours = 120
    db_session.commit()

    # Повторный sync (например, обновление часов из Jira).
    issue.planned_dev_hours = 99
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(alloc)
    assert alloc.included_flag is True
    assert alloc.planned_hours == 120


def test_sync_readds_allocations_on_unarchive(db_session, proj):
    """Категория вернулась в initiatives_rfa → allocations восстановлены в черновиках."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-re", name="Draft re", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N3", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 0

    issue.category = "initiatives_rfa"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1


def test_sync_no_draft_scenarios_is_noop(db_session, proj):
    """Нет черновых сценариев → никаких allocations не создаётся, ошибки нет."""
    from app.models import ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-N4", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 0


def test_sync_creates_backlog_item_for_quarterly_tasks(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "ITL-1", "quarterly_tasks",
                        planned_analyst_hours=40)
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.issue_id == issue.id
    assert item.archived_at is None
    assert item.title == issue.summary
    assert item.estimate_analyst_hours == 40
    assert item.estimate_hours == 40


def test_sync_archives_when_category_leaves_tracked_set(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "ITL-2", "quarterly_tasks")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    issue.category = "development"  # уходит из отслеживаемых
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(item)
    assert item.archived_at is not None


def test_sync_archives_item_on_cancel_like_status(db_session, proj):
    """Категория отслеживаемая, но статус «Отменена» → архив + draft allocations удалены."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-cx", name="Draft cancel", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "ITL-274", "quarterly_tasks")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item.archived_at is None
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1

    # Jira отменила задачу, категория не менялась.
    issue.status = "Отменена"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(item)
    assert item.archived_at is not None
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 0


def test_sync_unarchives_when_cancel_status_cleared(db_session, proj):
    """Status вернулся с «Отменена» в активный → архив снят, allocations восстановлены."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-cx2", name="Draft cancel back", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "ITL-275", "quarterly_tasks")
    issue.status = "Отменена"
    db_session.commit()

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    # cancel-like при создании → BacklogItem не создаётся вовсе (та же ветка archive)
    assert item is None
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0

    # Активная задача появляется → элемент бэклога создаётся.
    issue.status = "Open"
    db_session.commit()
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item is not None
    assert item.archived_at is None
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1


def test_sync_does_not_create_for_cancel_like_status(db_session, proj):
    """Категория tracked, но Jira уже отменила → BacklogItem не создаётся."""
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "ITL-CX", "initiatives_rfa")
    issue.status = "Rejected"
    db_session.commit()

    svc = BacklogService(db_session)
    result = svc.sync_from_issue(issue)
    db_session.commit()

    assert result is None
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0
