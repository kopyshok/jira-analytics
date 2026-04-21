"""When PM sets Issue.category=initiatives_rfa via API, BacklogItem is
auto-created (and removed when category moves away)."""

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def _seed_issue(db, key="RFA-1", category="development", **planned):
    from app.models import Category, Issue, Project

    cat = db.query(Category).filter_by(code="initiatives_rfa").first()
    if not cat:
        cat = Category(
            id="cat-ib",
            code="initiatives_rfa",
            label="Инициативы и RFA",
            color="#7F77DD",
            sort_order=22,
            is_system=True,
        )
        db.add(cat)
    proj = Project(
        id="p-ib",
        jira_project_id="p-ib-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i1",
        jira_issue_id="i1-jira",
        key=key,
        summary="Epic",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        **planned,
    )
    db.add_all([proj, issue])
    db.commit()
    return issue


def test_set_single_issue_category_triggers_backlog_sync(db_session):
    from app.models import BacklogItem

    issue = _seed_issue(
        db_session,
        planned_analyst_hours=10,
        planned_dev_hours=20,
    )

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.put(
            f"/api/v1/issues/{issue.id}/category",
            json={"category_code": "initiatives_rfa"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    item = db_session.query(BacklogItem).filter_by(issue_id=issue.id).first()
    assert item is not None
    assert item.estimate_analyst_hours == 10
    assert item.estimate_dev_hours == 20
    assert item.estimate_hours == 30


def test_set_single_issue_category_archives_backlog_item_when_away(db_session):
    """Если до этого задача была в initiatives_rfa и у неё был
    BacklogItem — при смене категории на другую BacklogItem архивируется
    (`archived_at` выставляется, связь с Jira и allocations сохраняются)."""
    from app.models import BacklogItem
    from app.services.backlog_service import BacklogService

    issue = _seed_issue(db_session, category="initiatives_rfa", planned_dev_hours=8)
    # Pre-create backlog item через сервис.
    BacklogService(db_session).sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 1

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.put(
            f"/api/v1/issues/{issue.id}/category",
            json={"category_code": "development"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    # Endpoint пересчитывает denormalized Issue.category через
    # CategoryResolver и зовёт BacklogService.sync_from_issue — для
    # «не-backlog» категории это выставляет archived_at; связь с Jira
    # (issue_id) и возможные ScenarioAllocation сохраняются нетронутыми.
    from app.models import Issue

    fresh = db_session.query(Issue).filter_by(id=issue.id).first()
    assert fresh.assigned_category == "development"

    item = (
        db_session.query(BacklogItem)
        .filter_by(issue_id=issue.id)
        .one()
    )
    assert item.archived_at is not None
    assert item.issue_id == issue.id


def test_batch_set_category_triggers_backlog_sync(db_session):
    """Batch category change triggers sync for each affected issue."""
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
        id="p-batch",
        jira_project_id="p-batch-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issues = [
        Issue(
            id=f"ib-{i}",
            jira_issue_id=f"ib-{i}-jira",
            key=f"RFA-{i}",
            summary=f"Epic {i}",
            issue_type="RFA",
            status="Open",
            project_id=proj.id,
            category="development",
            planned_dev_hours=float(i),
        )
        for i in range(1, 4)
    ]
    db_session.add_all([cat, proj, *issues])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.put(
            "/api/v1/issues/batch-category",
            json={
                "issue_ids": [i.id for i in issues],
                "category_code": "initiatives_rfa",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 3
    finally:
        app.dependency_overrides.clear()

    # 3 BacklogItem записи должны появиться.
    for i in issues:
        item = db_session.query(BacklogItem).filter_by(issue_id=i.id).first()
        assert item is not None, f"missing backlog item for {i.key}"
        assert item.estimate_dev_hours == float(int(i.key.split("-")[1]))
