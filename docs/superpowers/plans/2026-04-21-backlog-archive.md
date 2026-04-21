# Backlog Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace current soft-unlink/auto-delete behaviour in the backlog with an explicit archive lifecycle (`archived_at` timestamp), add a new «В работе» + «Архив» view to the Backlog page, and stop treating items allocated to approved scenarios as backlog candidates.

**Architecture:** Add a single nullable `archived_at` timestamp on `BacklogItem`. Three UI views are derived server-side from `archived_at` + presence of approved allocations. `BacklogService.sync_from_issue` flips `archived_at` on Jira category transitions and never deletes / soft-unlinks.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic (batch mode for SQLite), React 19 + AntD 6 + TanStack Query.

Reference spec: [docs/superpowers/specs/2026-04-21-backlog-archive-design.md](../specs/2026-04-21-backlog-archive-design.md).

---

## File Structure

**Backend — modify:**
- `alembic/versions/029_backlog_archived_at.py` — new migration file
- `app/models/backlog_item.py` — add `archived_at` column + relationship import
- `app/services/backlog_service.py` — rewrite `sync_from_issue`, return action code
- `app/api/endpoints/backlog.py` — add `view` param, `archive` / `restore` endpoints, extend schema
- `app/api/endpoints/planning.py` — filter archived items in `create_scenario` and `sync_backlog`

**Backend — new tests:**
- extend `tests/test_backlog_sync.py` — new archive-related cases
- extend `tests/test_api_backlog_link.py` — new endpoints + view filters

**Frontend — modify:**
- `frontend/src/types/api.ts` — extend `BacklogItemResponse`, add `BacklogView`, extend `BacklogRefreshResult`
- `frontend/src/api/backlog.ts` — pass `view`, add `archiveBacklogItem` / `restoreBacklogItem`
- `frontend/src/hooks/useBacklog.ts` — view-param aware queries, archive/restore mutations
- `frontend/src/pages/BacklogPage.tsx` — Tabs (Активные / В работе / Архив), per-tab actions
- `frontend/e2e/crud-flows.spec.ts` — append archive/restore scenario

---

## Task 1: Alembic migration for `backlog_items.archived_at`

**Files:**
- Create: `alembic/versions/029_backlog_archived_at.py`

- [ ] **Step 1: Write migration**

```python
"""backlog_items.archived_at — explicit archive lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = "029_backlog_archived_at"
down_revision = "028_allocation_involvement"


def upgrade():
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("archived_at")
```

- [ ] **Step 2: Apply migration and verify schema**

Run: `alembic upgrade head`
Expected output: `Running upgrade 028_allocation_involvement -> 029_backlog_archived_at`.

Run: `py -3.10 -c "from app.database import engine; from sqlalchemy import inspect; print([c['name'] for c in inspect(engine).get_columns('backlog_items')])"`
Expected: list includes `'archived_at'`.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/029_backlog_archived_at.py
git commit -m "migration(backlog): add archived_at column"
```

---

## Task 2: Add `archived_at` to `BacklogItem` model

**Files:**
- Modify: `app/models/backlog_item.py`

- [ ] **Step 1: Add the mapped column**

In `app/models/backlog_item.py`, add `datetime` import and the column alongside existing ones:

```python
from datetime import datetime
# ...existing imports

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
```

Inside the class, after `risk`:

```python
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=False
    )
```

- [ ] **Step 2: Verify import smoke**

Run: `py -3.10 -c "from app.models import BacklogItem; print(BacklogItem.__table__.columns['archived_at'])"`
Expected: prints the column metadata without error.

- [ ] **Step 3: Commit**

```bash
git add app/models/backlog_item.py
git commit -m "model(backlog): add archived_at column"
```

---

## Task 3: Rewrite `BacklogService.sync_from_issue`

**Files:**
- Modify: `app/services/backlog_service.py`
- Test: `tests/test_backlog_sync.py`

- [ ] **Step 1: Rewrite failing tests first**

Open `tests/test_backlog_sync.py`. Replace `test_sync_deletes_item_when_category_changes_away` and `test_sync_soft_unlinks_item_referenced_in_scenario` with new archive-based assertions, and add two new cases. Full replacement block:

```python
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


def test_sync_archives_item_referenced_in_scenario(db_session, proj):
    """Архивная категория + allocation → archived_at, allocation не трогаем."""
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(id="s1", name="Q2 draft", year=2026, quarter="Q2")
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
    # Allocation intact.
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
```

Remove the two obsolete tests `test_sync_deletes_item_when_category_changes_away` and `test_sync_soft_unlinks_item_referenced_in_scenario` entirely.

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_backlog_sync.py -v`
Expected: 3 new tests fail because service still deletes/soft-unlinks and does not set `archived_at`.

- [ ] **Step 3: Rewrite the service**

Replace the tail of `app/services/backlog_service.py` (starting at `if issue.category == BACKLOG_CATEGORY:`) with:

```python
from datetime import datetime, timezone
# ensure this import at top of file if not present

# ...
        if issue.category == BACKLOG_CATEGORY:
            if existing is None:
                existing = BacklogItem(issue_id=issue.id)
                self.db.add(existing)
                existing.opo_analyst_ratio = 0.5
            existing.title = issue.summary
            existing.project_id = issue.project_id
            existing.estimate_analyst_hours = issue.planned_analyst_hours
            existing.estimate_dev_hours = issue.planned_dev_hours
            existing.estimate_qa_hours = issue.planned_qa_hours
            existing.estimate_opo_hours = issue.planned_opo_hours
            existing.impact = issue.impact
            existing.risk = issue.risk
            total = sum(
                v or 0
                for v in (
                    existing.estimate_analyst_hours,
                    existing.estimate_dev_hours,
                    existing.estimate_qa_hours,
                    existing.estimate_opo_hours,
                )
            )
            existing.estimate_hours = total or None
            # Jira — source of truth. Returning to initiatives_rfa auto-unarchives.
            existing.archived_at = None
            self.db.flush()
            return existing

        # Category left backlog. Archive the local row, keep issue_id + allocations.
        if existing is None:
            return None
        if existing.archived_at is None:
            existing.archived_at = datetime.now(timezone.utc)
            self.db.flush()
        return None
```

Also update the docstring above `sync_from_issue` to describe archive behaviour instead of the old delete/soft-unlink:

```python
        """Идемпотентно выравнивает BacklogItem с Issue по текущей категории.

        - ``category == 'initiatives_rfa'`` — create-or-update, перетягивает
          Jira-поля и сбрасывает ``archived_at`` (auto-restore).
        - Иначе: если BacklogItem существует — проставляем ``archived_at=now()``
          и сохраняем связь с Jira (``issue_id``) + allocations нетронуты.
          Если BacklogItem нет — ничего не делаем.
        """
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_backlog_sync.py -v`
Expected: all tests pass, including the 3 new ones.

- [ ] **Step 5: Commit**

```bash
git add app/services/backlog_service.py tests/test_backlog_sync.py
git commit -m "service(backlog): archive on category flip instead of delete/soft-unlink"
```

---

## Task 4: Extend `/backlog/refresh-from-jira` response with archived/restored counters

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Write failing test for new counters**

Append to `tests/test_api_backlog_link.py`:

```python
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
```

Also update `test_refresh_from_jira_removes_stale_items` — remove `assert body["removed"] >= 1` and replace with `assert body["archived"] == 1`. Keep the `.filter_by(id="m-stale").count() == 1` assertion (item is now archived, not deleted). Replace the trailing assertion with:

```python
    item = db_session.query(BacklogItem).filter_by(id="m-stale").one()
    assert item.archived_at is not None
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py::test_refresh_from_jira_reports_archived_and_restored tests/test_api_backlog_link.py::test_refresh_from_jira_removes_stale_items -v`
Expected: both fail — no `archived` / `restored` keys in response; `removed` check drops row count.

- [ ] **Step 3: Update RefreshResponse + refresh_from_jira logic**

In `app/api/endpoints/backlog.py`, replace the `RefreshResponse` schema:

```python
class RefreshResponse(BaseModel):
    created: int
    updated: int
    removed: int = 0  # kept at 0 for backward compat — no more auto-delete
    archived: int = 0
    restored: int = 0
    jira_refreshed: int = 0
```

Replace the body of `refresh_from_jira` (the candidate/stale loops) with the archive-aware version. Find the block starting at `for issue in candidates:` and ending at the `return RefreshResponse(...)` line, and replace with:

```python
    created = 0
    updated = 0
    archived = 0
    restored = 0

    for issue in candidates:
        resolved = resolver.resolve_for_issue(issue).category_code
        if issue.category != resolved:
            issue.category = resolved
        if resolved != BACKLOG_CATEGORY:
            continue
        existing = (
            db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )
        was_archived = existing is not None and existing.archived_at is not None
        was_present = existing is not None
        svc.sync_from_issue(issue)
        if was_present:
            updated += 1
            if was_archived:
                restored += 1
        else:
            created += 1

    # Items that used to be backlog but Jira category moved away → archive.
    stale_items = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.issue_id.isnot(None))
        .all()
    )
    for item in stale_items:
        if item.issue is None:
            continue
        resolved = resolver.resolve_for_issue(item.issue).category_code
        if resolved == BACKLOG_CATEGORY:
            continue
        if item.archived_at is None:
            svc.sync_from_issue(item.issue)
            archived += 1

    db.commit()
    return RefreshResponse(
        created=created,
        updated=updated,
        archived=archived,
        restored=restored,
        jira_refreshed=jira_refreshed,
    )
```

Note: the local variable shadowing `removed` is removed — the schema default of `0` handles it.

- [ ] **Step 4: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
git commit -m "api(backlog): report archived/restored counters on refresh-from-jira"
```

---

## Task 5: Add `view` query parameter to `GET /backlog`

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Write failing tests for 3 views**

Append to `tests/test_api_backlog_link.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v -k "view"`
Expected: failures — the endpoint does not accept `view` and the response schema lacks `archived_at` / `in_work` / `approved_scenarios`.

- [ ] **Step 3: Extend the response schema**

In `app/api/endpoints/backlog.py`, extend `BacklogItemResponse`:

```python
from datetime import datetime
# (ensure import)

class ScenarioRef(BaseModel):
    id: str
    name: str


class BacklogItemResponse(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    issue_id: Optional[str] = None
    jira_key: Optional[str] = None
    priority: Optional[int] = None
    estimate_hours: Optional[float] = None
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = None
    impact: Optional[str] = None
    risk: Optional[str] = None
    archived_at: Optional[datetime] = None
    in_work: bool = False
    approved_scenarios: List[ScenarioRef] = []

    class Config:
        from_attributes = True
```

Replace `_to_response` with a version that accepts `approved_scenarios`:

```python
def _to_response(
    item: BacklogItem,
    approved_scenarios: Optional[List[ScenarioRef]] = None,
) -> BacklogItemResponse:
    scenarios = approved_scenarios or []
    return BacklogItemResponse(
        id=item.id,
        title=item.title,
        project_id=item.project_id,
        issue_id=item.issue_id,
        jira_key=item.issue.key if item.issue else None,
        priority=item.priority,
        estimate_hours=item.estimate_hours,
        estimate_analyst_hours=item.estimate_analyst_hours,
        estimate_dev_hours=item.estimate_dev_hours,
        estimate_qa_hours=item.estimate_qa_hours,
        estimate_opo_hours=item.estimate_opo_hours,
        opo_analyst_ratio=item.opo_analyst_ratio,
        impact=item.impact,
        risk=item.risk,
        archived_at=item.archived_at,
        in_work=bool(scenarios),
        approved_scenarios=scenarios,
    )
```

- [ ] **Step 4: Rewrite `list_backlog_items` with views**

Replace the `list_backlog_items` function body:

```python
@router.get("", response_model=List[BacklogItemResponse])
async def list_backlog_items(
    project_id: Optional[str] = Query(None),
    view: str = Query("active", pattern="^(active|archived|in_work)$"),
    db: Session = Depends(get_db),
):
    """Список бэклога с фильтром по виду.

    - ``active`` (default): не архивные и не в утверждённых сценариях.
    - ``archived``: только ``archived_at IS NOT NULL``.
    - ``in_work``: не архивные, есть ≥1 allocation в approved-сценарии;
      каждый элемент получает список ссылок на эти сценарии.
    """
    approved_alloc_ids = (
        db.query(ScenarioAllocation.backlog_item_id)
        .join(PlanningScenario, ScenarioAllocation.scenario_id == PlanningScenario.id)
        .filter(PlanningScenario.status == "approved")
        .distinct()
        .subquery()
    )

    query = db.query(BacklogItem).options(joinedload(BacklogItem.issue))
    if project_id is not None:
        query = query.filter(BacklogItem.project_id == project_id)

    if view == "active":
        query = query.filter(BacklogItem.archived_at.is_(None))
        query = query.filter(~BacklogItem.id.in_(approved_alloc_ids))
    elif view == "archived":
        query = query.filter(BacklogItem.archived_at.isnot(None))
    elif view == "in_work":
        query = query.filter(BacklogItem.archived_at.is_(None))
        query = query.filter(BacklogItem.id.in_(approved_alloc_ids))

    items = query.all()
    items.sort(
        key=lambda i: (
            i.priority is None,
            i.priority if i.priority is not None else 0,
            i.title or "",
        )
    )

    # For in_work, join back approved scenarios per item.
    scenarios_by_item: dict[str, List[ScenarioRef]] = {}
    if view == "in_work" and items:
        item_ids = [i.id for i in items]
        rows = (
            db.query(ScenarioAllocation.backlog_item_id, PlanningScenario.id, PlanningScenario.name)
            .join(PlanningScenario, ScenarioAllocation.scenario_id == PlanningScenario.id)
            .filter(PlanningScenario.status == "approved")
            .filter(ScenarioAllocation.backlog_item_id.in_(item_ids))
            .all()
        )
        for bi_id, scn_id, scn_name in rows:
            scenarios_by_item.setdefault(bi_id, []).append(
                ScenarioRef(id=scn_id, name=scn_name)
            )

    return [_to_response(i, scenarios_by_item.get(i.id)) for i in items]
```

Note: need to add `PlanningScenario` to imports at top of file:

```python
from app.models import AppSetting, BacklogItem, Issue, PlanningScenario, ScenarioAllocation
```

(confirm `List` is imported from `typing` — it already is).

- [ ] **Step 5: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v`
Expected: all tests pass, including the new 4.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
git commit -m "api(backlog): add ?view=active|archived|in_work filter with approved_scenarios"
```

---

## Task 6: `POST /backlog/{id}/archive`

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_backlog_link.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v -k "archive"`
Expected: all 4 fail (endpoint 404).

- [ ] **Step 3: Implement the endpoint**

Add to `app/api/endpoints/backlog.py`, near the other CRUD endpoints:

```python
@router.post("/{item_id}/archive", response_model=BacklogItemResponse)
async def archive_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Архивировать инициативу — скрыть из активного бэклога.

    422, если элемент в ≥1 утверждённом сценарии. Идемпотентно: повторный
    вызов не меняет ``archived_at``.
    """
    from datetime import datetime, timezone

    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    if item.archived_at is None:
        blocking = (
            db.query(PlanningScenario)
            .join(ScenarioAllocation, ScenarioAllocation.scenario_id == PlanningScenario.id)
            .filter(
                ScenarioAllocation.backlog_item_id == item_id,
                PlanningScenario.status == "approved",
            )
            .distinct()
            .all()
        )
        if blocking:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        "Initiative is allocated to an approved scenario — "
                        "remove the allocation first."
                    ),
                    "blocking_scenarios": [
                        {"id": s.id, "name": s.name} for s in blocking
                    ],
                },
            )
        item.archived_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
    return _to_response(item)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v -k "archive"`
Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
git commit -m "api(backlog): POST /archive with 422 guard for in-work items"
```

---

## Task 7: `POST /backlog/{id}/restore`

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
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
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v -k "restore"`
Expected: all 4 fail (endpoint 404).

- [ ] **Step 3: Implement the endpoint**

Add to `app/api/endpoints/backlog.py`:

```python
@router.post("/{item_id}/restore", response_model=BacklogItemResponse)
async def restore_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Восстановить инициативу из архива в активный бэклог.

    Если инициатива привязана к Jira-задаче, а в Jira категория сейчас
    архивная — 409: Jira source-of-truth, сначала смените категорию там.
    Идемпотентно: уже активный элемент — no-op.
    """
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    if item.archived_at is not None:
        if item.issue is not None and item.issue.category != BACKLOG_CATEGORY:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Linked Jira issue has a non-backlog category — change the "
                    "category in Jira (CategoryConfigTab) first."
                ),
            )
        item.archived_at = None
        db.commit()
        db.refresh(item)
    return _to_response(item)
```

Need to import `BACKLOG_CATEGORY` — already present at top of file.

- [ ] **Step 4: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_api_backlog_link.py -v -k "restore"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
git commit -m "api(backlog): POST /restore with 409 guard on linked archived category"
```

---

## Task 8: Skip archived items when creating / syncing scenario allocations

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Test: new `tests/test_api_planning_archive_guard.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_api_planning_archive_guard.py`:

```python
"""Archived backlog items must not be pulled into scenarios."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
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


def test_create_scenario_excludes_archived_items(db_session):
    from app.models import BacklogItem, ScenarioAllocation

    db_session.add(BacklogItem(id="pa-active", title="active"))
    db_session.add(BacklogItem(
        id="pa-arch", title="archived",
        archived_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/planning/scenarios",
            json={"name": "Q2 draft", "year": 2026, "quarter": 2},
        )
        assert r.status_code == 201, r.text
        scenario_id = r.json()["id"]
    finally:
        app.dependency_overrides.clear()

    allocs = (
        db_session.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .all()
    )
    item_ids = {a.backlog_item_id for a in allocs}
    assert "pa-active" in item_ids
    assert "pa-arch" not in item_ids


def test_sync_backlog_excludes_archived_items(db_session):
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation

    # Pre-existing draft scenario with zero allocations.
    scenario = PlanningScenario(
        id="sc-pa", name="Q2", year=2026, quarter="Q2", status="draft",
    )
    db_session.add(scenario)
    db_session.add(BacklogItem(id="pa2-active", title="active2"))
    db_session.add(BacklogItem(
        id="pa2-arch", title="archived2",
        archived_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/planning/scenarios/{scenario.id}/sync-backlog")
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    allocs = (
        db_session.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario.id)
        .all()
    )
    item_ids = {a.backlog_item_id for a in allocs}
    assert "pa2-active" in item_ids
    assert "pa2-arch" not in item_ids
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_api_planning_archive_guard.py -v`
Expected: both fail — archived items currently get pulled in.

- [ ] **Step 3: Filter archived in create_scenario**

In `app/api/endpoints/planning.py`, inside `create_scenario`, locate:

```python
    items = db.query(BacklogItem).all()
```

Replace with:

```python
    items = db.query(BacklogItem).filter(BacklogItem.archived_at.is_(None)).all()
```

- [ ] **Step 4: Filter archived in sync_backlog**

In the same file, inside `sync_backlog`, locate:

```python
    current_ids = {i.id for i in db.query(BacklogItem.id).all()}
```

Replace with:

```python
    current_ids = {
        i.id for i in db.query(BacklogItem.id)
        .filter(BacklogItem.archived_at.is_(None))
        .all()
    }
```

- [ ] **Step 5: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_api_planning_archive_guard.py -v`
Expected: both pass.

Also run full backend suite to catch regressions:

Run: `py -3.10 -m pytest tests/ -q`
Expected: everything green.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_planning_archive_guard.py
git commit -m "api(planning): skip archived backlog items when seeding allocations"
```

---

## Task 9: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/backlog.ts`

- [ ] **Step 1: Extend the types**

In `frontend/src/types/api.ts`, inside the `// === Backlog ===` section, replace `BacklogItemResponse` with:

```typescript
export type BacklogView = 'active' | 'archived' | 'in_work';

export interface BacklogItemScenarioRef {
  id: string;
  name: string;
}

export interface BacklogItemResponse {
  id: string;
  title: string;
  project_id: string | null;
  issue_id: string | null;
  jira_key: string | null;
  priority: number | null;
  estimate_hours: number | null;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
  estimate_opo_hours: number | null;
  opo_analyst_ratio: number | null;
  impact: BacklogImpactRisk | null;
  risk: BacklogImpactRisk | null;
  archived_at: string | null;
  in_work: boolean;
  approved_scenarios: BacklogItemScenarioRef[];
}
```

Replace `BacklogRefreshResult` with:

```typescript
export interface BacklogRefreshResult {
  created: number;
  updated: number;
  removed: number;
  archived: number;
  restored: number;
  jira_refreshed: number;
}
```

- [ ] **Step 2: Extend the API client**

In `frontend/src/api/backlog.ts`:

Replace `getBacklogItems`:

```typescript
export const getBacklogItems = (
  view: BacklogView = 'active',
  projectId?: string,
) =>
  api.get<BacklogItemResponse[]>('/backlog', { view, project_id: projectId });
```

Append:

```typescript
export const archiveBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/archive`);

export const restoreBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/restore`);
```

Update imports at top to include `BacklogView`:

```typescript
import type {
  BacklogItemResponse,
  BacklogImpactRisk,
  BacklogRefreshResult,
  BacklogView,
} from '../types/api';
```

- [ ] **Step 3: Verify type-check**

Run: `cd frontend && npm run lint`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/backlog.ts
git commit -m "fe(backlog): types + api client for views, archive, restore"
```

---

## Task 10: Frontend hooks — view-aware queries, archive/restore mutations

**Files:**
- Modify: `frontend/src/hooks/useBacklog.ts`

- [ ] **Step 1: Rewrite hooks**

Replace the whole content of `frontend/src/hooks/useBacklog.ts` with:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBacklogItems,
  createBacklogItem,
  updateBacklogItem,
  deleteBacklogItem,
  linkJira,
  unlinkJira,
  refreshFromJira,
  archiveBacklogItem,
  restoreBacklogItem,
} from '../api/backlog';
import { getProjects } from '../api/projects';
import type { BacklogView } from '../types/api';

export const useProjects = () =>
  useQuery({ queryKey: ['projects'], queryFn: getProjects });

export const useBacklogItems = (view: BacklogView = 'active') =>
  useQuery({
    queryKey: ['backlog', view],
    queryFn: () => getBacklogItems(view),
  });

function invalidateAllBacklog(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['backlog'] });
}

export const useCreateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useUpdateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateBacklogItem>[1] }) =>
      updateBacklogItem(id, data),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useDeleteBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteBacklogItem,
    onSuccess: () => {
      invalidateAllBacklog(qc);
      qc.invalidateQueries({ queryKey: ['planning', 'scenarios'] });
    },
  });
};

export const useLinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, jira_key }: { id: string; jira_key: string }) =>
      linkJira(id, jira_key),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useUnlinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unlinkJira(id),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useRefreshFromJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshFromJira,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useArchiveBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: archiveBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useRestoreBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: restoreBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};
```

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useBacklog.ts
git commit -m "fe(backlog): view-aware hooks + archive/restore mutations"
```

---

## Task 11: Refactor `BacklogPage` into tabs (Активные / В работе / Архив)

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`

- [ ] **Step 1: Replace page top — imports + hooks**

At the top of `frontend/src/pages/BacklogPage.tsx`, replace the imports block with:

```typescript
import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  App, Button, InputNumber, Popconfirm, Select, Space, Table, Tabs, Tag, Tooltip, Typography,
} from 'antd';
import {
  DeleteOutlined, DisconnectOutlined, EditOutlined, HolderOutlined,
  InboxOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, UndoOutlined,
} from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import PageHeader from '../components/shared/PageHeader';
import BacklogManualModal from '../components/backlog/BacklogManualModal';
import BacklogLinkJiraModal from '../components/backlog/BacklogLinkJiraModal';
import {
  useBacklogItems, useUpdateBacklogItem, useDeleteBacklogItem, useProjects,
  useUnlinkJira, useRefreshFromJira, useArchiveBacklogItem, useRestoreBacklogItem,
} from '../hooks/useBacklog';
import { useJiraSettings } from '../hooks/useSettings';
import type {
  BacklogItemResponse, BacklogImpactRisk, BacklogView,
} from '../types/api';

const IMPACT_RISK_OPTIONS: { value: BacklogImpactRisk; label: string }[] = [
  { value: 'low',    label: 'Низкий' },
  { value: 'medium', label: 'Средний' },
  { value: 'high',   label: 'Высокий' },
];

const IMPACT_RISK_COLOR: Record<BacklogImpactRisk, string> = {
  low: 'default',
  medium: 'gold',
  high: 'red',
};

const IMPACT_RISK_LABEL: Record<BacklogImpactRisk, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
};

function DragHandle({ id }: { id: string }) {
  const { attributes, listeners } = useSortable({ id });
  return (
    <HolderOutlined
      style={{ cursor: 'grab', color: '#8faec8' }}
      {...attributes}
      {...listeners}
    />
  );
}

function SortableRow(props: React.HTMLAttributes<HTMLTableRowElement> & { 'data-row-key'?: string }) {
  const id = props['data-row-key'] ?? '';
  const { setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <tr
      {...props}
      ref={setNodeRef}
      style={{
        ...props.style,
        transform: CSS.Translate.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
      }}
    />
  );
}
```

- [ ] **Step 2: Replace the component body**

Replace the whole `export default function BacklogPage()` with:

```typescript
export default function BacklogPage() {
  const { notification } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get('view');
  const view: BacklogView =
    rawView === 'archived' || rawView === 'in_work' ? rawView : 'active';

  const active = useBacklogItems('active');
  const inWork = useBacklogItems('in_work');
  const archived = useBacklogItems('archived');

  const { data: projects } = useProjects();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';

  const update = useUpdateBacklogItem();
  const del = useDeleteBacklogItem();
  const unlink = useUnlinkJira();
  const refreshFromJira = useRefreshFromJira();
  const archive = useArchiveBacklogItem();
  const restore = useRestoreBacklogItem();

  const [manualOpen, setManualOpen] = useState(false);
  const [editing, setEditing] = useState<BacklogItemResponse | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkTarget, setLinkTarget] = useState<BacklogItemResponse | null>(null);

  const projectMap = useMemo(
    () => new Map(projects?.map((p) => [p.id, p]) ?? []),
    [projects],
  );

  const sortByPriority = (rows?: BacklogItemResponse[]) =>
    rows?.slice().sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));

  const activeRows = useMemo(() => sortByPriority(active.data), [active.data]);
  const inWorkRows = useMemo(() => sortByPriority(inWork.data), [inWork.data]);
  const archivedRows = useMemo(() => sortByPriority(archived.data), [archived.data]);

  const handleDragEnd = useCallback(
    ({ active: draggingActive, over }: DragEndEvent) => {
      if (!over || draggingActive.id === over.id || !activeRows) return;
      const oldIndex = activeRows.findIndex((i) => i.id === draggingActive.id);
      const newIndex = activeRows.findIndex((i) => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;
      const newPriority = newIndex + 1;
      update.mutate({ id: String(draggingActive.id), data: { priority: newPriority } });
    },
    [activeRows, update],
  );

  const openCreate = () => { setEditing(null); setManualOpen(true); };
  const openEdit = (item: BacklogItemResponse) => { setEditing(item); setManualOpen(true); };
  const openLink = (item: BacklogItemResponse) => { setLinkTarget(item); setLinkOpen(true); };

  const patch = (id: string, data: Parameters<typeof update.mutate>[0]['data']) => {
    update.mutate(
      { id, data },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  const handleRefreshFromJira = () => {
    refreshFromJira.mutate(undefined, {
      onSuccess: (res) => {
        notification.success({
          title: 'Обновлено из Jira',
          description:
            `Перечитано: ${res.jira_refreshed} · ` +
            `Создано: ${res.created} · Обновлено: ${res.updated} · ` +
            `Архивировано: ${res.archived} · Восстановлено: ${res.restored}`,
        });
      },
      onError: (e) =>
        notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const renderRoleEstimate = (
    field: 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours',
    editable: boolean,
  ) => (v: number | null, r: BacklogItemResponse) => {
    if (!editable || r.issue_id) return <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>;
    return (
      <InputNumber
        size="small"
        min={0}
        value={v ?? undefined}
        variant="borderless"
        style={{ width: 70 }}
        onBlur={(e) => {
          const raw = e.currentTarget.value.trim();
          const next = raw === '' ? null : Number(raw);
          if (next === v) return;
          patch(r.id, { [field]: next as number } as Parameters<typeof update.mutate>[0]['data']);
        }}
      />
    );
  };

  const renderImpactRisk = (field: 'impact' | 'risk', editable: boolean) =>
    (v: BacklogImpactRisk | null, r: BacklogItemResponse) => {
      if (!editable || r.issue_id) {
        return v ? <Tag color={IMPACT_RISK_COLOR[v]}>{IMPACT_RISK_LABEL[v]}</Tag> : <span>—</span>;
      }
      return (
        <Select
          size="small"
          allowClear
          variant="borderless"
          value={v ?? undefined}
          style={{ width: 100 }}
          options={IMPACT_RISK_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={(next) => patch(r.id, { [field]: next as BacklogImpactRisk } as Parameters<typeof update.mutate>[0]['data'])}
        />
      );
    };

  const baseColumns = (editable: boolean) => [
    {
      title: 'Prio', dataIndex: 'priority', width: 70, fixed: 'left' as const,
      render: (v: number | null, r: BacklogItemResponse) =>
        editable ? (
          <InputNumber
            size="small"
            min={1}
            value={v ?? undefined}
            variant="borderless"
            style={{ width: 55 }}
            onBlur={(e) => {
              const raw = e.currentTarget.value.trim();
              const next = raw === '' ? null : Number(raw);
              if (next === v) return;
              patch(r.id, { priority: next as number });
            }}
          />
        ) : (
          <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>
        ),
    },
    {
      title: 'Идея', dataIndex: 'title',
      render: (v: string, r: BacklogItemResponse) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{v}</Typography.Text>
          {r.jira_key && (
            jiraBaseUrl
              ? (
                <Typography.Link
                  href={`${jiraBaseUrl}/browse/${r.jira_key}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: 12 }}
                >
                  {r.jira_key}
                </Typography.Link>
              )
              : <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.jira_key}</Typography.Text>
          )}
        </Space>
      ),
    },
    { title: 'АН ч', dataIndex: 'estimate_analyst_hours', width: 80,
      render: renderRoleEstimate('estimate_analyst_hours', editable) },
    { title: 'ПР ч', dataIndex: 'estimate_dev_hours', width: 80,
      render: renderRoleEstimate('estimate_dev_hours', editable) },
    { title: 'ТС ч', dataIndex: 'estimate_qa_hours', width: 80,
      render: renderRoleEstimate('estimate_qa_hours', editable) },
    { title: 'ОПЭ ч', dataIndex: 'estimate_opo_hours', width: 80,
      render: renderRoleEstimate('estimate_opo_hours', editable) },
    { title: 'Impact', dataIndex: 'impact', width: 110,
      render: renderImpactRisk('impact', editable) },
    { title: 'Risk', dataIndex: 'risk', width: 110,
      render: renderImpactRisk('risk', editable) },
    {
      title: 'Проект', dataIndex: 'project_id', width: 110,
      render: (id: string | null) => {
        if (!id) return <span>—</span>;
        const p = projectMap.get(id);
        return p ? <Tooltip title={p.name}><span>{p.key}</span></Tooltip> : id;
      },
    },
  ];

  const actionsActive = (r: BacklogItemResponse) => (
    <Space size={4}>
      {r.issue_id ? (
        <Popconfirm
          title="Отвязать от Jira?"
          description="Идея останется в бэклоге, но потеряет связь с задачей."
          onConfirm={() => unlink.mutate(r.id, {
            onSuccess: () => notification.success({ title: 'Отвязано' }),
            onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
          })}
        >
          <Tooltip title="Отвязать от Jira">
            <Button icon={<DisconnectOutlined />} size="small" />
          </Tooltip>
        </Popconfirm>
      ) : (
        <>
          <Tooltip title="Связать с Jira">
            <Button icon={<LinkOutlined />} size="small" onClick={() => openLink(r)} />
          </Tooltip>
          <Tooltip title="Редактировать">
            <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(r)} />
          </Tooltip>
        </>
      )}
      <Popconfirm
        title="Убрать из активного бэклога?"
        description="Инициатива попадёт в раздел «Архив». Связь с Jira сохраняется."
        onConfirm={() => archive.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Архивировано' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Tooltip title="Архивировать">
          <Button icon={<InboxOutlined />} size="small" />
        </Tooltip>
      </Popconfirm>
      <Popconfirm
        title="Удалить идею?"
        description="Элемент будет убран из всех черновиков сценариев."
        onConfirm={() => del.mutate(r.id, {
          onSuccess: (res) => {
            if (res.affected_scenarios.length > 0) {
              notification.success({
                title: 'Удалено',
                description:
                  `Убрано из ${res.affected_scenarios.length} сценариев: ` +
                  res.affected_scenarios.map((s) => s.name).join(', '),
              });
            }
          },
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Button icon={<DeleteOutlined />} size="small" danger />
      </Popconfirm>
    </Space>
  );

  const actionsArchived = (r: BacklogItemResponse) => (
    <Space size={4}>
      <Popconfirm
        title="Вернуть в активный бэклог?"
        onConfirm={() => restore.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Восстановлено' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Tooltip title="Восстановить">
          <Button icon={<UndoOutlined />} size="small" />
        </Tooltip>
      </Popconfirm>
      {!r.issue_id && (
        <Tooltip title="Редактировать">
          <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(r)} />
        </Tooltip>
      )}
      <Popconfirm
        title="Удалить идею?"
        onConfirm={() => del.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Удалено' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Button icon={<DeleteOutlined />} size="small" danger />
      </Popconfirm>
    </Space>
  );

  const scenariosColumn = {
    title: 'Сценарий', dataIndex: 'approved_scenarios', width: 200,
    render: (s: BacklogItemResponse['approved_scenarios']) => (
      <Space size={4} wrap>
        {s.map((x) => <Tag key={x.id} color="blue">{x.name}</Tag>)}
      </Space>
    ),
  };

  const activeTable = (
    <DndContext
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis]}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={activeRows?.map((i) => i.id) ?? []} strategy={verticalListSortingStrategy}>
        <Table<BacklogItemResponse>
          dataSource={activeRows}
          rowKey="id"
          loading={active.isLoading}
          pagination={false}
          size="small"
          scroll={{ x: 1200 }}
          components={{ body: { row: SortableRow } }}
          columns={[
            { title: '', width: 32, fixed: 'left' as const, render: (_, r) => <DragHandle id={r.id} /> },
            ...baseColumns(true),
            { title: 'Действия', width: 210, fixed: 'right' as const, render: (_, r) => actionsActive(r) },
          ]}
        />
      </SortableContext>
    </DndContext>
  );

  const inWorkTable = (
    <Table<BacklogItemResponse>
      dataSource={inWorkRows}
      rowKey="id"
      loading={inWork.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1200 }}
      columns={[
        ...baseColumns(false),
        scenariosColumn,
      ]}
    />
  );

  const archivedTable = (
    <Table<BacklogItemResponse>
      dataSource={archivedRows}
      rowKey="id"
      loading={archived.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1200 }}
      columns={[
        ...baseColumns(false),
        { title: 'Действия', width: 160, fixed: 'right' as const, render: (_, r) => actionsArchived(r) },
      ]}
    />
  );

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Бэклог инициатив"
        subtitle='Активные кандидаты — в основной вкладке; задачи в работе и архив — в отдельных'
        actions={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshFromJira}
              loading={refreshFromJira.isPending}
            >
              Обновить с Jira
            </Button>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>
              Идея вручную
            </Button>
          </Space>
        }
      />

      <BacklogManualModal
        open={manualOpen}
        item={editing}
        onClose={() => { setManualOpen(false); setEditing(null); }}
      />
      <BacklogLinkJiraModal
        open={linkOpen}
        item={linkTarget}
        onClose={() => { setLinkOpen(false); setLinkTarget(null); }}
      />

      <Tabs
        activeKey={view}
        onChange={(k) => {
          const next = new URLSearchParams(searchParams);
          next.set('view', k);
          setSearchParams(next, { replace: true });
        }}
        items={[
          {
            key: 'active',
            label: `Активные (${activeRows?.length ?? 0})`,
            children: activeTable,
          },
          {
            key: 'in_work',
            label: `В работе (${inWorkRows?.length ?? 0})`,
            children: inWorkTable,
          },
          {
            key: 'archived',
            label: `Архив (${archivedRows?.length ?? 0})`,
            children: archivedTable,
          },
        ]}
      />
    </Space>
  );
}
```

- [ ] **Step 3: Lint / type-check**

Run: `cd frontend && npm run lint`
Expected: no errors.

- [ ] **Step 4: Smoke test manually**

In one terminal: `py -3.10 scripts/local_smoke.py`
Open the backlog page: three tabs, counts match DB state, «Архивировать» moves a row to «Архив», «Восстановить» returns it.

Document findings in chat. If a widget is broken, fix inline and rerun lint.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx
git commit -m "fe(backlog): tabs for active/in-work/archived + archive & restore actions"
```

---

## Task 12: Playwright E2E — archive & restore flow

**Files:**
- Modify: `frontend/e2e/crud-flows.spec.ts`

- [ ] **Step 1: Inspect existing backlog coverage**

Read the full file to find the backlog test block. The patterns to reuse: `apiPost`, `apiGet`, `expectVisible`, `trackBrowserErrors`, and the `E2E` project key. Follow the style used by adjacent specs (`capacity-v2.spec.ts` uses tabs navigation similarly).

- [ ] **Step 2: Append archive/restore scenario**

Append the following test block at the bottom of `frontend/e2e/crud-flows.spec.ts` (inside the existing `test.describe` for CRUD, or as a top-level `test` — match whatever pattern already exists in the file):

```typescript
test('backlog: archive + restore move initiative between tabs', async ({ page, request }) => {
  trackBrowserErrors(page);

  // Create a manual idea through the API to avoid relying on UI-only creation.
  const created = await (await request.post(`${apiBaseUrl}/backlog`, {
    data: { title: 'E2E idea to archive', priority: 77 },
  })).json();

  await page.goto('/backlog?view=active');
  await expect(page.getByText('E2E idea to archive')).toBeVisible();

  // Archive from the Active tab.
  const row = page.locator('tr').filter({ hasText: 'E2E idea to archive' });
  await row.getByRole('button', { name: /Архивировать/i }).click();
  await page.getByRole('button', { name: 'OK' }).click();

  await expect(page.getByText('E2E idea to archive')).toHaveCount(0, { timeout: 5000 });

  // Switch to Archive tab, confirm presence.
  await page.getByRole('tab', { name: /Архив/i }).click();
  await expect(page.getByText('E2E idea to archive')).toBeVisible();

  // Restore.
  const archivedRow = page.locator('tr').filter({ hasText: 'E2E idea to archive' });
  await archivedRow.getByRole('button', { name: /Восстановить/i }).click();
  await page.getByRole('button', { name: 'OK' }).click();

  await expect(page.getByText('E2E idea to archive')).toHaveCount(0, { timeout: 5000 });

  // Back on Active.
  await page.getByRole('tab', { name: /Активные/i }).click();
  await expect(page.getByText('E2E idea to archive')).toBeVisible();

  // Cleanup.
  await request.delete(`${apiBaseUrl}/backlog/${created.id}`);

  await expectNoBrowserErrors(page);
});
```

If the tooltip text differs (`getByRole('button', { name: ... })` won't match icon-only buttons), fall back to locating by `title=` selector:

```typescript
await row.locator('[aria-label="Архивировать"], [title="Архивировать"]').first().click();
```

Same for «Восстановить».

- [ ] **Step 3: Run the suite**

Run: `cd frontend && npm run e2e -- crud-flows.spec.ts`
Expected: new test passes alongside existing crud tests.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/crud-flows.spec.ts
git commit -m "e2e(backlog): archive + restore flow between tabs"
```

---

## Task 13: Full-stack verification and push

- [ ] **Step 1: Re-run backend suite**

Run: `py -3.10 -m pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 2: Frontend build + lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: build succeeds, no new lint errors.

- [ ] **Step 3: Full E2E**

Run: `cd frontend && npm run e2e`
Expected: all specs pass.

- [ ] **Step 4: Push**

```bash
git push origin main
```

- [ ] **Step 5: Update memory entry**

Append a new memory note to `C:\Users\akim2\.claude\projects\d--ClaudeDev-JiraAnalysis\memory\MEMORY.md` pointing to a new file `project_backlog_archive_shipped.md` summarising what was delivered and when.

File `project_backlog_archive_shipped.md` content:

```markdown
---
name: Backlog archive lifecycle shipped
description: 2026-04-21 — archive/restore flow for backlog initiatives replaces soft-unlink
type: project
---

2026-04-21: backlog_items.archived_at column + POST /backlog/{id}/archive · /restore + GET /backlog?view=active|archived|in_work + filter archived out of new scenario allocations + BacklogPage tabs (Активные/В работе/Архив). BacklogService.sync_from_issue now archives on Jira category flip instead of delete/soft-unlink. Auto-unarchive when Jira category returns to initiatives_rfa.

**Why:** PM reported that re-categorising an initiative to «Архив» in CategoryConfigTab only unlinked it from Jira — row stayed as a «ручная идея». Root cause was soft-unlink path in BacklogService when allocations existed.

**How to apply:** When working on the backlog or planning paths, treat `archived_at` as the source of truth for local archive state and linked `Issue.category` as Jira override (auto-reflected on refresh-from-jira or category flip). Never re-introduce soft-unlink — archive instead.
```

Index line (append to `MEMORY.md`):

```
- [Backlog archive shipped](project_backlog_archive_shipped.md) — 2026-04-21: archived_at lifecycle + tabs, replaces soft-unlink
```

---

## Self-Review (Spec coverage check)

Spec sections → tasks:
- Domain model (3 states) → Task 5 (view filter), Task 11 (tabs).
- Transitions «Активная ↔ В работе» (auto) → Task 5 (view filter by approved allocations).
- «Активная → Архивная» via button → Task 6.
- «Активная → Архивная» via Jira category → Task 3.
- «Архивная → Активная» via button → Task 7.
- «Архивная → Активная» via Jira category → Task 3 + Task 4.
- «В работе → Архивная» blocked (422) → Task 6.
- Alembic migration → Task 1.
- `BacklogService.sync_from_issue` rewrite → Task 3.
- `GET /backlog?view=` → Task 5.
- `POST /backlog/{id}/archive` → Task 6.
- `POST /backlog/{id}/restore` → Task 7.
- `RefreshResponse.archived/restored` → Task 4.
- `PlanningService` skip archived → Task 8.
- Frontend types & API client → Task 9.
- Hooks → Task 10.
- `BacklogPage` tabs + actions → Task 11.
- Refresh notification wording → Task 11 (notification message).
- E2E test → Task 12.
- Backward compat (default view=active, old fields preserved) → Task 5, Task 4.

No gaps detected. All sections of the spec map to at least one task.

Type consistency:
- `BacklogView` = `'active' | 'archived' | 'in_work'` — consistent between backend regex, api.ts, hooks, page.
- `archived_at` = ISO string on frontend (serialized by FastAPI from `datetime`), Date column on backend — consistent.
- `approved_scenarios: ScenarioRef[]` — same shape in backend schema and TS type (`BacklogItemScenarioRef`).
- `archiveBacklogItem` / `restoreBacklogItem` — consistent between api, hooks, page.
