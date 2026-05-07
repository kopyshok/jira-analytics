# Scenario Approval Reclassify + Planning Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При утверждении сценария включённые задачи автоматически переводятся из «Инициатив и RFA» в «Квартальные задачи»; черновой сценарий показывает только корневые инициативы из бэклога.

**Architecture:** Три изменения в двух backend-файлах + два новых теста. BacklogService получает защиту от дочерних задач. Endpoint аллокаций фильтрует черновой сценарий через subquery. Approve endpoint добавляет цикл перекласификации с вызовом CategoryResolver + BacklogService.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, pytest, sqlite/:memory: + StaticPool

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `app/services/backlog_service.py` | Line 120 — guard `_ensure_draft_allocations` by `issue.parent_id is None` |
| Modify | `app/api/endpoints/planning.py` | Imports: add `Issue`, `or_`, `BacklogService`, `BACKLOG_CATEGORY`, `CategoryResolver`; `list_scenario_allocations`: draft filter via subquery; `approve_scenario`: reclassify loop after `scenario.status = "approved"` |
| Create | `tests/test_backlog_child_skip.py` | Unit tests for child-issue guard |
| Create | `tests/test_api_planning_approve_reclassify.py` | Endpoint tests: draft filter + approval reclassification |

---

## Task 1: BacklogService — guard child issues from draft scenarios

**Files:**
- Modify: `app/services/backlog_service.py:120`
- Create: `tests/test_backlog_child_skip.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_backlog_child_skip.py`:

```python
"""BacklogService: child issues (parent_id != NULL) must NOT be added to draft scenarios."""

import pytest

from app.models import BacklogItem, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService


@pytest.fixture
def proj(db_session):
    p = Project(id="bcs-p1", jira_project_id="bcs-p1-jira", key="BCS", name="BCS Test", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def draft_scenario(db_session):
    s = PlanningScenario(id="bcs-s1", name="Q3 Test", year=2026, quarter=3, status="draft")
    db_session.add(s)
    db_session.commit()
    return s


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


def test_child_issue_not_added_to_draft_scenario(db_session, proj, draft_scenario):
    parent = _make_issue(db_session, proj, "BCS-1")
    child = _make_issue(db_session, proj, "BCS-2", parent_id=parent.id)

    svc = BacklogService(db_session)
    result = svc.sync_from_issue(child)
    db_session.commit()

    assert result is not None  # BacklogItem created
    allocs = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=result.id).all()
    assert allocs == [], "child issue must not be allocated to any draft scenario"


def test_root_issue_added_to_draft_scenario(db_session, proj, draft_scenario):
    root = _make_issue(db_session, proj, "BCS-3")

    svc = BacklogService(db_session)
    result = svc.sync_from_issue(root)
    db_session.commit()

    assert result is not None
    allocs = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=result.id).all()
    assert len(allocs) == 1
    assert allocs[0].scenario_id == draft_scenario.id
```

- [ ] **Step 2: Run tests to verify they fail**

```
py -3.10 -m pytest tests/test_backlog_child_skip.py -v
```

Expected: `test_child_issue_not_added_to_draft_scenario` FAILS (child IS added), `test_root_issue_added_to_draft_scenario` PASSES.

- [ ] **Step 3: Add parent_id guard in BacklogService**

In `app/services/backlog_service.py`, locate line 120 (inside `sync_from_issue`):

```python
            self.db.flush()
            if is_new or was_archived:
                self._ensure_draft_allocations(existing.id)
            return existing
```

Replace with:

```python
            self.db.flush()
            if (is_new or was_archived) and issue.parent_id is None:
                self._ensure_draft_allocations(existing.id)
            return existing
```

- [ ] **Step 4: Run tests to verify they pass**

```
py -3.10 -m pytest tests/test_backlog_child_skip.py -v
```

Expected: both PASS.

- [ ] **Step 5: Run full suite to check no regressions**

```
py -3.10 -m pytest tests/ -v --tb=short -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```
git add app/services/backlog_service.py tests/test_backlog_child_skip.py
git commit -m "fix(backlog): skip child issues when adding to draft scenarios"
```

---

## Task 2: Allocations endpoint — draft scenario filter

**Files:**
- Modify: `app/api/endpoints/planning.py:25,29-44,974-1007`
- Create: `tests/test_api_planning_approve_reclassify.py` (partial — filter tests only)

- [ ] **Step 1: Write failing test**

Create `tests/test_api_planning_approve_reclassify.py`:

```python
"""Tests: draft scenario allocation filter + approval category reclassification."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded(testclient_db_session):
    """Seed: project + 3 issues (root rfa, already-quarterly, child rfa) + backlog items."""
    from app.models import BacklogItem, Issue, Project
    db = testclient_db_session

    proj = Project(id="p1", jira_project_id="j-p1", key="PRJ", name="Test", is_active=True)
    db.add(proj)

    issue_rfa = Issue(
        id="i-rfa", jira_issue_id="j-rfa", key="PRJ-1", summary="Root RFA",
        issue_type="RFA", status="Open", project_id="p1",
        category="initiatives_rfa", assigned_category="initiatives_rfa", parent_id=None,
    )
    issue_qrt = Issue(
        id="i-qrt", jira_issue_id="j-qrt", key="PRJ-2", summary="Already Quarterly",
        issue_type="Task", status="Open", project_id="p1",
        category="quarterly_tasks", assigned_category="quarterly_tasks", parent_id=None,
    )
    issue_child = Issue(
        id="i-child", jira_issue_id="j-child", key="PRJ-3", summary="Child Task",
        issue_type="Task", status="Open", project_id="p1",
        category="initiatives_rfa", assigned_category=None, parent_id="i-rfa",
    )
    db.add_all([issue_rfa, issue_qrt, issue_child])

    item_rfa = BacklogItem(id="b-rfa", title="Root RFA", issue_id="i-rfa")
    item_qrt = BacklogItem(id="b-qrt", title="Already Quarterly", issue_id="i-qrt")
    item_child = BacklogItem(id="b-child", title="Child Task", issue_id="i-child")
    db.add_all([item_rfa, item_qrt, item_child])
    db.commit()


def test_draft_scenario_filters_non_rfa_and_children(client, seeded):
    """Draft scenario allocations must only include root initiatives_rfa items."""
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    allocs = r.json()

    item_ids = [a["backlog_item_id"] for a in allocs]
    assert "b-rfa" in item_ids, "root initiatives_rfa must be shown"
    assert "b-qrt" not in item_ids, "already-quarterly must be excluded"
    assert "b-child" not in item_ids, "child issue must be excluded"
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.10 -m pytest tests/test_api_planning_approve_reclassify.py::test_draft_scenario_filters_non_rfa_and_children -v
```

Expected: FAIL — all 3 items appear in allocations.

- [ ] **Step 3: Add imports to planning.py**

In `app/api/endpoints/planning.py`, update the sqlalchemy import on line 25:

```python
from sqlalchemy import func, or_
```

Add `Issue` to the `app.models` import block (line 29-44):

```python
from app.models import (
    Absence,
    AbsenceReason,
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    RoleCapacityRule,
    ScenarioAbsenceSnapshot,
    ScenarioAllocation,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioRevision,
    ScenarioRevisionItem,
    ScenarioRule,
)
```

Add service imports after line 53 (`from app.services.snapshot_writer import SnapshotWriter`):

```python
from app.services.backlog_service import BacklogService, BACKLOG_CATEGORY
from app.services.category_resolver import CategoryResolver
```

- [ ] **Step 4: Add draft filter in list_scenario_allocations**

In `app/api/endpoints/planning.py`, replace the `list_scenario_allocations` function body (lines 986-1007):

```python
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    query = (
        db.query(ScenarioAllocation, BacklogItem)
        .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(ScenarioAllocation.scenario_id == scenario_id)
    )

    if scenario.status == "draft":
        allowed_issue_ids = (
            db.query(Issue.id)
            .filter(
                Issue.category == BACKLOG_CATEGORY,
                Issue.parent_id.is_(None),
            )
            .subquery()
        )
        query = query.filter(
            or_(
                BacklogItem.issue_id.is_(None),
                BacklogItem.issue_id.in_(allowed_issue_ids),
            )
        )

    rows = (
        query.order_by(
            ScenarioAllocation.sort_order.is_(None),
            ScenarioAllocation.sort_order,
            BacklogItem.title,
        )
        .all()
    )
    active_employees = db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712
    emp_role_by_name = {e.display_name: e.role for e in active_employees if e.role}
    return [_to_allocation_resp(alloc, item, emp_role_by_name) for alloc, item in rows]
```

- [ ] **Step 5: Run test to verify it passes**

```
py -3.10 -m pytest tests/test_api_planning_approve_reclassify.py::test_draft_scenario_filters_non_rfa_and_children -v
```

Expected: PASS.

- [ ] **Step 6: Verify approved scenario still returns all items**

Add this test to `tests/test_api_planning_approve_reclassify.py` and run it:

```python
def test_approved_scenario_shows_all_items(client, seeded, testclient_db_session):
    """Approved scenario must return all allocations — no filter applied."""
    from app.models import PlanningScenario, ScenarioAllocation
    db = testclient_db_session

    # Create scenario and manually set it to approved with allocations for all 3 items
    from app.models.base import generate_uuid
    sid = generate_uuid()
    scenario = PlanningScenario(id=sid, name="Q2 Approved", year=2026, quarter=2, status="approved")
    db.add(scenario)
    db.add_all([
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-rfa", included_flag=True, planned_hours=0),
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-qrt", included_flag=True, planned_hours=0),
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-child", included_flag=False, planned_hours=0),
    ])
    db.commit()

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    allocs = r.json()
    item_ids = [a["backlog_item_id"] for a in allocs]
    assert "b-rfa" in item_ids
    assert "b-qrt" in item_ids
    assert "b-child" in item_ids
```

```
py -3.10 -m pytest tests/test_api_planning_approve_reclassify.py::test_approved_scenario_shows_all_items -v
```

Expected: PASS.

- [ ] **Step 7: Run full suite**

```
py -3.10 -m pytest tests/ -v --tb=short -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 8: Commit**

```
git add app/api/endpoints/planning.py tests/test_api_planning_approve_reclassify.py
git commit -m "fix(planning): filter draft scenario allocations to root initiatives_rfa only"
```

---

## Task 3: Approve endpoint — reclassify included issues

**Files:**
- Modify: `app/api/endpoints/planning.py:636-652`
- Modify: `tests/test_api_planning_approve_reclassify.py` (add tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api_planning_approve_reclassify.py`:

```python
def test_approve_reclassifies_included_issues(client, seeded, testclient_db_session):
    """Approving a scenario reclassifies included initiatives_rfa → quarterly_tasks."""
    db = testclient_db_session
    from app.models import ScenarioAllocation

    # Create draft scenario — auto-adds b-rfa (only rfa item after filter)
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    # Mark b-rfa as included
    allocs_r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    alloc_id = next(a["id"] for a in allocs_r.json() if a["backlog_item_id"] == "b-rfa")
    r = client.patch(f"/api/v1/planning/scenarios/{sid}/allocations/{alloc_id}", json={"included": True})
    assert r.status_code == 200, r.text

    # Approve
    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    # Check issue category changed
    from app.models import Issue
    db.expire_all()
    issue = db.query(Issue).filter_by(id="i-rfa").one()
    assert issue.assigned_category == "quarterly_tasks"
    assert issue.category == "quarterly_tasks"


def test_approve_does_not_reclassify_excluded_issues(client, seeded, testclient_db_session):
    """Issues not included (included_flag=False) must NOT be reclassified on approve."""
    db = testclient_db_session

    # Create draft scenario — b-rfa auto-added with included_flag=False
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3 B", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    # Approve WITHOUT marking b-rfa as included
    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    from app.models import Issue
    db.expire_all()
    issue = db.query(Issue).filter_by(id="i-rfa").one()
    assert issue.category == "initiatives_rfa", "excluded issue must not be reclassified"


def test_approve_removes_included_from_other_drafts(client, seeded, testclient_db_session):
    """After approval, reclassified items must be removed from other draft scenarios."""
    db = testclient_db_session
    from app.models import ScenarioAllocation

    # Create two draft scenarios
    r1 = client.post("/api/v1/planning/scenarios", json={"name": "Q3 A", "year": 2026, "quarter": 3})
    sid1 = r1.json()["id"]
    r2 = client.post("/api/v1/planning/scenarios", json={"name": "Q3 B", "year": 2026, "quarter": 3})
    sid2 = r2.json()["id"]

    # Mark b-rfa as included in scenario 1
    allocs_r = client.get(f"/api/v1/planning/scenarios/{sid1}/allocations")
    alloc_id = next(a["id"] for a in allocs_r.json() if a["backlog_item_id"] == "b-rfa")
    client.patch(f"/api/v1/planning/scenarios/{sid1}/allocations/{alloc_id}", json={"included": True})

    # Approve scenario 1
    r = client.post(f"/api/v1/planning/scenarios/{sid1}/approve")
    assert r.status_code == 200, r.text

    # b-rfa must no longer be in scenario 2's allocations
    db.expire_all()
    alloc_in_s2 = (
        db.query(ScenarioAllocation)
        .filter_by(scenario_id=sid2, backlog_item_id="b-rfa")
        .one_or_none()
    )
    assert alloc_in_s2 is None, "reclassified item must be removed from other draft scenarios"
```

- [ ] **Step 2: Run tests to verify they fail**

```
py -3.10 -m pytest tests/test_api_planning_approve_reclassify.py::test_approve_reclassifies_included_issues tests/test_api_planning_approve_reclassify.py::test_approve_does_not_reclassify_excluded_issues tests/test_api_planning_approve_reclassify.py::test_approve_removes_included_from_other_drafts -v
```

Expected: all three FAIL.

- [ ] **Step 3: Add reclassification logic in approve_scenario**

In `app/api/endpoints/planning.py`, after line 646 (the ResourcePlan stale loop `for p in plans_to_stale: p.status = "stale"`) and before line 648 (`db.commit()`), insert:

```python
    # Reclassify included initiatives_rfa issues → quarterly_tasks
    resolver = CategoryResolver(db)
    backlog_svc = BacklogService(db)
    reclassified_item_ids: list[str] = []
    for alloc, item in included_rows:
        if item.issue_id is None:
            continue
        issue = db.get(Issue, item.issue_id)
        if issue is None or issue.category != BACKLOG_CATEGORY:
            continue
        issue.assigned_category = "quarterly_tasks"
        issue.category = resolver.resolve_for_issue(issue).category_code
        backlog_svc.sync_from_issue(issue)
        reclassified_item_ids.append(item.id)

    for item_id in reclassified_item_ids:
        backlog_svc._remove_draft_allocations(item_id)
```

Also update the `entities` list (lines 649-651) to include `"issues"` when reclassification happened:

```python
    entities = ["planning", "backlog"]
    if plans_to_stale:
        entities.append("resource_planning")
    if reclassified_item_ids:
        entities.append("issues")
```

- [ ] **Step 4: Run tests to verify they pass**

```
py -3.10 -m pytest tests/test_api_planning_approve_reclassify.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full suite**

```
py -3.10 -m pytest tests/ -v --tb=short -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```
git add app/api/endpoints/planning.py tests/test_api_planning_approve_reclassify.py
git commit -m "feat(planning): reclassify included issues to quarterly_tasks on scenario approval"
```

---

## Task 4: Push to origin

- [ ] **Push all commits**

```
git push origin main
```

---

## Verification Checklist

After all tasks complete, manually verify in the browser:

1. Open «Сценарии» → Q3 2026 draft → список задач не содержит OS-* задач и задач с категорией «Квартальные задачи» (ITL-304 не виден).
2. Создай тестовый черновой сценарий → включи одну задачу → утверди → проверь в разделе «Категории задачи» что задача перешла из «Бэклог инициатив» в «Активный стек».
3. Убедись, что утверждённые сценарии (Q2 2026) по-прежнему показывают весь свой исторический состав без фильтрации.
