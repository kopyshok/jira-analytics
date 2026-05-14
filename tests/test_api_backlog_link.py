"""Tests for /backlog/{id}/link-jira, /unlink-jira, /refresh-from-jira."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite with StaticPool for TestClient compatibility."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def test_link_jira_pulls_estimates_from_issue(db_session):
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-ib",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p1",
        jira_project_id="p1-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i1",
        jira_issue_id="i1-jira",
        key="RFA-42",
        summary="Real epic",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
        planned_analyst_hours=8,
        planned_dev_hours=16,
        planned_qa_hours=4,
        planned_opo_hours=2,
    )
    manual = BacklogItem(
        id="m1",
        title="Manual idea",
        estimate_analyst_hours=1,
        estimate_hours=1,
        priority=3,
    )
    db_session.add_all([cat, proj, issue, manual])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{manual.id}/link-jira",
            json={"jira_key": "RFA-42"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(manual)
    assert manual.issue_id == issue.id
    assert manual.estimate_analyst_hours == 8
    assert manual.estimate_dev_hours == 16
    assert manual.estimate_qa_hours == 4
    assert manual.estimate_opo_hours == 2
    assert manual.estimate_hours == 30


def test_link_jira_unknown_key_returns_404(db_session):
    from app.models import BacklogItem

    manual = BacklogItem(id="m2", title="Idea")
    db_session.add(manual)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{manual.id}/link-jira",
            json={"jira_key": "NOPE-999"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_link_jira_already_linked_returns_409(db_session):
    """Если Issue уже привязана к другому BacklogItem, вторая привязка — 409."""
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p-409",
        jira_project_id="p-409-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i-409",
        jira_issue_id="i-409-jira",
        key="RFA-409",
        summary="X",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
    )
    first = BacklogItem(id="m-first", title="First", issue_id=issue.id)
    second = BacklogItem(id="m-second", title="Second")
    db_session.add_all([proj, issue, first, second])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{second.id}/link-jira",
            json={"jira_key": "RFA-409"},
        )
        assert r.status_code == 409, r.text
    finally:
        app.dependency_overrides.clear()


def test_unlink_jira_nulls_issue_id(db_session):
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p2",
        jira_project_id="p2-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i2",
        jira_issue_id="i2-jira",
        key="RFA-100",
        summary="X",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
    )
    item = BacklogItem(
        id="m3",
        title="X",
        issue_id=issue.id,
        estimate_analyst_hours=10,
        estimate_hours=10,
    )
    db_session.add_all([proj, issue, item])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/unlink-jira")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.issue_id is None
    # estimates retained (user may want to edit afterwards)
    assert item.estimate_analyst_hours == 10


def test_refresh_from_jira_pulls_all_matching(db_session):
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-ib2",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p3",
        jira_project_id="p3-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    db_session.add_all([cat, proj])
    for idx, (k, h) in enumerate([("RFA-1", 10), ("RFA-2", 20)]):
        db_session.add(
            Issue(
                id=f"i-refresh-{idx}",
                jira_issue_id=f"i-refresh-{idx}-jira",
                key=k,
                summary=k,
                issue_type="RFA",
                status="Open",
                project_id=proj.id,
                assigned_category="initiatives_rfa",
                category="initiatives_rfa",
                planned_analyst_hours=h,
            )
        )
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 2
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).count() == 2


def test_refresh_from_jira_removes_stale_items(db_session):
    """Если Issue потерял категорию — refresh убирает BacklogItem (или soft-unlinks)."""
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p-stale",
        jira_project_id="p-stale-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i-stale",
        jira_issue_id="i-stale-jira",
        key="RFA-STALE",
        summary="was backlog",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="development",  # already moved away
    )
    # Old BacklogItem linked to issue that no longer matches.
    stale = BacklogItem(id="m-stale", title="stale", issue_id=issue.id)
    db_session.add_all([proj, issue, stale])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["archived"] == 1
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).filter_by(id="m-stale").count() == 1
    item = db_session.query(BacklogItem).filter_by(id="m-stale").one()
    assert item.archived_at is not None


def test_refresh_from_jira_heals_legacy_drift(db_session):
    """Легаси-данные: assigned_category='initiatives_rfa', а category — устарела.

    Batch-category pre-f08bd70 не обновлял denormalized Issue.category. Refresh
    обязан подобрать такие задачи через резолвер и заодно вылечить расхождение.
    """
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-drift",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p-drift",
        jira_project_id="p-drift-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i-drift",
        jira_issue_id="i-drift-jira",
        key="RFA-77",
        summary="drifted",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        assigned_category="initiatives_rfa",
        category="unfilled_worklog",  # stale denormalized column
        planned_analyst_hours=5,
    )
    db_session.add_all([cat, proj, issue])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).filter_by(issue_id="i-drift").count() == 1
    db_session.refresh(issue)
    assert issue.category == "initiatives_rfa"  # drift healed


def test_refresh_from_jira_picks_up_quarterly_tasks(db_session):
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-qt",
        code="quarterly_tasks",
        label="Квартальные задачи",
        color="#1D9E75",
        sort_order=2,
        is_system=False,
    )
    proj = Project(
        id="p-qt",
        jira_project_id="p-qt-jira",
        key="ITL",
        name="ITL",
        is_active=True,
    )
    db_session.add_all([cat, proj])
    db_session.add(
        Issue(
            id="i-qt-1",
            jira_issue_id="i-qt-1-jira",
            key="ITL-100",
            summary="Quarterly initiative",
            issue_type="ITL",
            status="In Progress",
            project_id=proj.id,
            assigned_category="quarterly_tasks",
            category="quarterly_tasks",
        )
    )
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 1
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).filter_by(issue_id="i-qt-1").count() == 1


def _seed_scenario(db, scenario_id, name, status, backlog_item_id):
    from app.models import PlanningScenario, ScenarioAllocation

    db.add(
        PlanningScenario(
            id=scenario_id,
            name=name,
            year=2026,
            quarter="Q1",
            status=status,
        )
    )
    db.add(
        ScenarioAllocation(
            id=f"alloc-{scenario_id}",
            scenario_id=scenario_id,
            backlog_item_id=backlog_item_id,
            planned_hours=10,
            included_flag=True,
        )
    )


def test_delete_backlog_cascades_through_draft_scenarios(db_session):
    """Delete возвращает 200 и чистит ScenarioAllocation у draft-сценариев."""
    from app.models import BacklogItem, ScenarioAllocation

    item = BacklogItem(id="bi-del", title="to delete")
    db_session.add(item)
    _seed_scenario(db_session, "scn-d1", "Draft A", "draft", item.id)
    _seed_scenario(db_session, "scn-d2", "Draft B", "draft", item.id)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.delete(f"/api/v1/backlog/{item.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["allocations_removed"] == 2
        names = sorted(s["name"] for s in body["affected_scenarios"])
        assert names == ["Draft A", "Draft B"]
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).filter_by(id=item.id).count() == 0
    assert (
        db_session.query(ScenarioAllocation)
        .filter_by(backlog_item_id=item.id)
        .count()
        == 0
    )


def test_delete_backlog_blocked_by_approved_scenario(db_session):
    """Approved-сценарий блокирует удаление — 409 с именем сценария."""
    from app.models import BacklogItem, ScenarioAllocation

    item = BacklogItem(id="bi-blk", title="blocked")
    db_session.add(item)
    _seed_scenario(db_session, "scn-a", "Approved Plan", "approved", item.id)
    _seed_scenario(db_session, "scn-d", "Draft Plan", "draft", item.id)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.delete(f"/api/v1/backlog/{item.id}")
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["blocking_scenarios"][0]["name"] == "Approved Plan"
        assert len(detail["blocking_scenarios"]) == 1
    finally:
        app.dependency_overrides.clear()

    # Nothing removed on 409 — item + both allocations intact.
    assert db_session.query(BacklogItem).filter_by(id=item.id).count() == 1
    assert (
        db_session.query(ScenarioAllocation)
        .filter_by(backlog_item_id=item.id)
        .count()
        == 2
    )


def test_refresh_from_jira_reports_archived_and_restored(db_session):
    """Refresh считает archived/restored на сменах категории."""
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-arch", code="initiatives_rfa", label="Инициативы и RFA",
        color="#7F77DD", sort_order=22, is_system=True,
    )
    proj = Project(
        id="p-arch", jira_project_id="p-arch-jira", key="RFA", name="RFA", is_active=True,
    )
    # Issue A: in Jira now ARCHIVE but currently has BacklogItem → should archive.
    issue_a = Issue(
        id="i-a", jira_issue_id="i-a-jira", key="RFA-A", summary="to-archive",
        issue_type="RFA", status="Open", project_id=proj.id,
        assigned_category="archive", category="archive",
    )
    item_a = BacklogItem(id="ba", title="to-archive", issue_id=issue_a.id)
    # Issue B: was archived locally; Jira now says initiatives_rfa → should restore.
    from datetime import datetime, timezone
    issue_b = Issue(
        id="i-b", jira_issue_id="i-b-jira", key="RFA-B", summary="to-restore",
        issue_type="RFA", status="Open", project_id=proj.id,
        assigned_category="initiatives_rfa", category="initiatives_rfa",
    )
    item_b = BacklogItem(
        id="bb", title="to-restore", issue_id=issue_b.id,
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add_all([cat, proj, issue_a, issue_b, item_a, item_b])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["archived"] == 1
        assert body["restored"] == 1
    finally:
        app.dependency_overrides.clear()


def _seed_view_fixture(db):
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
    from datetime import datetime, timezone

    active = BacklogItem(id="bv-a", title="active")
    archived = BacklogItem(
        id="bv-arch", title="archived", archived_at=datetime.now(timezone.utc)
    )
    in_work = BacklogItem(id="bv-iw", title="in-work")
    db.add_all([active, archived, in_work])

    db.add(PlanningScenario(id="bv-scn", name="Approved Q", year=2026, quarter="Q2", status="approved"))
    db.add(ScenarioAllocation(
        id="bv-alloc", scenario_id="bv-scn", backlog_item_id=in_work.id,
        planned_hours=10, included_flag=True,
    ))
    db.commit()


def test_get_backlog_view_active_excludes_archived_and_in_work(db_session):
    _seed_view_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=active")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert ids == {"bv-a"}
    finally:
        app.dependency_overrides.clear()


def test_get_backlog_view_archived_returns_only_archived(db_session):
    _seed_view_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=archived")
        assert r.status_code == 200
        rows = r.json()
        ids = {row["id"] for row in rows}
        assert ids == {"bv-arch"}
        assert rows[0]["archived_at"] is not None
    finally:
        app.dependency_overrides.clear()


def test_get_backlog_view_in_work_returns_only_in_work_with_scenarios(db_session):
    _seed_view_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=in_work")
        assert r.status_code == 200
        rows = r.json()
        assert [row["id"] for row in rows] == ["bv-iw"]
        assert rows[0]["in_work"] is True
        scenarios = rows[0]["approved_scenarios"]
        assert len(scenarios) == 1
        assert scenarios[0]["name"] == "Approved Q"
    finally:
        app.dependency_overrides.clear()


def test_get_backlog_default_view_is_active(db_session):
    _seed_view_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert ids == {"bv-a"}
    finally:
        app.dependency_overrides.clear()


def _seed_jira_status_fixture(db):
    """Three linked items: new / indeterminate / done in Jira; no scenarios."""
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="js-p", jira_project_id="js-pj", key="RFA", name="RFA", is_active=True,
    )
    i_new = Issue(
        id="js-i-new", jira_issue_id="js-in", key="RFA-N", summary="new",
        issue_type="RFA", status="Open", status_category="new", project_id=proj.id,
    )
    i_in = Issue(
        id="js-i-ind", jira_issue_id="js-ii", key="RFA-I", summary="in progress",
        issue_type="RFA", status="В работе", status_category="indeterminate",
        project_id=proj.id,
    )
    i_done = Issue(
        id="js-i-done", jira_issue_id="js-id", key="RFA-D", summary="done",
        issue_type="RFA", status="Готово", status_category="done",
        project_id=proj.id,
    )
    db.add_all([proj, i_new, i_in, i_done])
    db.add_all([
        BacklogItem(id="js-new", title="Jira-new", issue_id=i_new.id),
        BacklogItem(id="js-ind", title="Jira-in-progress", issue_id=i_in.id),
        BacklogItem(id="js-done", title="Jira-done", issue_id=i_done.id),
    ])
    db.commit()


def test_view_active_excludes_jira_done_includes_indeterminate(db_session):
    # 'done' items must be excluded; 'indeterminate' items must stay in active
    # (they are only moved to in_work once allocated to an approved scenario).
    _seed_jira_status_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=active")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert "js-new" in ids
        assert "js-ind" in ids   # indeterminate stays in active until in approved scenario
        assert "js-done" not in ids
    finally:
        app.dependency_overrides.clear()


def test_view_in_work_includes_jira_indeterminate_without_scenario(db_session):
    _seed_jira_status_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=in_work")
        assert r.status_code == 200
        rows = r.json()
        ids = {row["id"] for row in rows}
        assert ids == {"js-ind"}
        # No approved scenario, but in_work is still true via Jira status.
        assert rows[0]["in_work"] is True
        assert rows[0]["approved_scenarios"] == []
    finally:
        app.dependency_overrides.clear()


def test_view_archived_includes_jira_done_without_archived_at(db_session):
    _seed_jira_status_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=archived")
        assert r.status_code == 200
        rows = r.json()
        ids = {row["id"] for row in rows}
        assert ids == {"js-done"}
        # archived_at still NULL — virtual archive via Jira status only.
        assert rows[0]["archived_at"] is None
        assert rows[0]["jira_status_category"] == "done"
    finally:
        app.dependency_overrides.clear()


def test_response_exposes_jira_status_fields(db_session):
    _seed_jira_status_fixture(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog/js-ind")
        assert r.status_code == 200
        body = r.json()
        assert body["jira_status"] == "В работе"
        assert body["jira_status_category"] == "indeterminate"
    finally:
        app.dependency_overrides.clear()


def test_manual_item_without_issue_survives_active_filter(db_session):
    """Item with issue_id=NULL must flow through into 'active' view."""
    from app.models import BacklogItem

    db_session.add(BacklogItem(id="manual-1", title="manual"))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backlog?view=active")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert "manual-1" in ids
    finally:
        app.dependency_overrides.clear()


def test_get_backlog_item_includes_approved_scenarios(db_session):
    """Single-item GET reflects approved-scenario membership."""
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation

    item = BacklogItem(id="gs-1", title="in work via single get")
    db_session.add(item)
    db_session.add(PlanningScenario(
        id="gs-scn", name="GS Approved", year=2026, quarter="Q2", status="approved",
    ))
    db_session.add(ScenarioAllocation(
        id="gs-alloc", scenario_id="gs-scn", backlog_item_id=item.id,
        planned_hours=5, included_flag=True,
    ))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.get(f"/api/v1/backlog/{item.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["in_work"] is True
        assert len(body["approved_scenarios"]) == 1
        assert body["approved_scenarios"][0]["name"] == "GS Approved"
    finally:
        app.dependency_overrides.clear()


def test_archive_active_item_sets_archived_at(db_session):
    from app.models import BacklogItem

    item = BacklogItem(id="arch-1", title="to archive")
    db_session.add(item)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/archive")
        assert r.status_code == 200, r.text
        assert r.json()["archived_at"] is not None
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.archived_at is not None


def test_archive_in_work_item_returns_422(db_session):
    from app.models import BacklogItem

    item = BacklogItem(id="arch-iw", title="in work")
    db_session.add(item)
    _seed_scenario(db_session, "scn-iw-appr", "Approved Plan", "approved", item.id)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/archive")
        assert r.status_code == 422
        detail = r.json()["detail"]
        # Сообщение должно упомянуть имя блокирующего сценария.
        assert "Approved Plan" in str(detail)
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.archived_at is None


def test_archive_already_archived_is_idempotent(db_session):
    from app.models import BacklogItem
    from datetime import datetime, timezone

    item = BacklogItem(
        id="arch-dup", title="already archived",
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add(item)
    db_session.commit()
    first_ts = item.archived_at

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/archive")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    # No timestamp churn.
    assert item.archived_at == first_ts


def test_archive_unknown_returns_404(db_session):
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/does-not-exist/archive")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_restore_archived_manual_item_clears_archived_at(db_session):
    from app.models import BacklogItem
    from datetime import datetime, timezone

    item = BacklogItem(
        id="rst-1", title="archived manual",
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add(item)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 200
        assert r.json()["archived_at"] is None
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.archived_at is None


def test_restore_linked_item_with_archive_category_returns_409(db_session):
    from app.models import BacklogItem, Issue, Project
    from datetime import datetime, timezone

    proj = Project(
        id="p-rst", jira_project_id="p-rst-jira", key="RFA", name="RFA", is_active=True,
    )
    issue = Issue(
        id="i-rst", jira_issue_id="i-rst-jira", key="RFA-RST", summary="x",
        issue_type="RFA", status="Open", project_id=proj.id,
        category="archive",
    )
    item = BacklogItem(
        id="rst-blocked", title="blocked", issue_id=issue.id,
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add_all([proj, issue, item])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 409
        # User should see the Jira-category message.
        assert "Jira" in str(r.json()["detail"]) or "category" in str(r.json()["detail"]).lower()
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.archived_at is not None


def test_restore_linked_item_with_cancel_like_status_returns_409(db_session):
    """Restore блокируется если Jira-статус cancel-like, даже при tracked-категории."""
    from app.models import BacklogItem, Issue, Project
    from datetime import datetime, timezone

    proj = Project(
        id="p-rst-cx", jira_project_id="p-rst-cx-jira", key="ITL", name="ITL", is_active=True,
    )
    issue = Issue(
        id="i-rst-cx", jira_issue_id="i-rst-cx-jira", key="ITL-CX", summary="x",
        issue_type="Task", status="Отменена", project_id=proj.id,
        category="quarterly_tasks",
    )
    item = BacklogItem(
        id="rst-cancelled", title="cancelled", issue_id=issue.id,
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add_all([proj, issue, item])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 409
        detail = str(r.json()["detail"])
        assert "отмен" in detail.lower() or "отклон" in detail.lower()
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.archived_at is not None


def test_restore_already_active_is_idempotent(db_session):
    from app.models import BacklogItem

    item = BacklogItem(id="rst-noop", title="active")
    db_session.add(item)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 200
        assert r.json()["archived_at"] is None
    finally:
        app.dependency_overrides.clear()


def test_restore_unknown_returns_404(db_session):
    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/does-not-exist/restore")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_backlog_list_quarterly_view_returns_quarterly_items(db_session):
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p-qv",
        jira_project_id="p-qv-jira",
        key="ITL",
        name="ITL",
        is_active=True,
    )
    issue_qt = Issue(
        id="i-qv-qt",
        jira_issue_id="i-qv-qt-jira",
        key="ITL-QV1",
        summary="Quarterly item",
        issue_type="ITL",
        status="Open",
        project_id=proj.id,
        category="quarterly_tasks",
    )
    issue_rfa = Issue(
        id="i-qv-rfa",
        jira_issue_id="i-qv-rfa-jira",
        key="RFA-QV1",
        summary="RFA item",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
    )
    item_qt = BacklogItem(id="bi-qv-qt", title="Quarterly item", issue_id=issue_qt.id)
    item_rfa = BacklogItem(id="bi-qv-rfa", title="RFA item", issue_id=issue_rfa.id)
    db_session.add_all([proj, issue_qt, issue_rfa, item_qt, item_rfa])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r_q = client.get("/api/v1/backlog?view=quarterly")
        assert r_q.status_code == 200, r_q.text
        ids_q = {i["id"] for i in r_q.json()}
        assert "bi-qv-qt" in ids_q
        assert "bi-qv-rfa" not in ids_q

        r_a = client.get("/api/v1/backlog?view=active")
        assert r_a.status_code == 200, r_a.text
        ids_a = {i["id"] for i in r_a.json()}
        assert "bi-qv-rfa" in ids_a
        assert "bi-qv-qt" not in ids_a
    finally:
        app.dependency_overrides.clear()


def test_backlog_list_active_view_includes_manual_items(db_session):
    """Ручные записи без issue_id всегда показываются в active, не в quarterly."""
    from app.models import BacklogItem

    db_session.add(BacklogItem(id="bi-manual", title="Manual item"))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r_a = client.get("/api/v1/backlog?view=active")
        assert r_a.status_code == 200, r_a.text
        ids_a = {i["id"] for i in r_a.json()}
        assert "bi-manual" in ids_a

        r_q = client.get("/api/v1/backlog?view=quarterly")
        assert r_q.status_code == 200, r_q.text
        ids_q = {i["id"] for i in r_q.json()}
        assert "bi-manual" not in ids_q
    finally:
        app.dependency_overrides.clear()
