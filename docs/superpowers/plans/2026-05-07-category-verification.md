# Category Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verification step so newly synced issues land in "Стек задач к разбору" tab until a PM explicitly confirms their category.

**Architecture:** Two new boolean fields on `Issue` (`category_verified`, `require_child_verification`). Existing rows default to verified=TRUE (no disruption). Sync service sets verified=FALSE for new issues (unless parent auto-trusts). New `POST /issues/{id}/verify` endpoint sets verified=TRUE with optional cascade. Frontend tab routing checks verified flag; stack tab gets two new columns (toggle + confirm button).

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2 / Alembic (batch mode) / React 19 / AntD 6 / TanStack Query

---

## File Map

| File | Action | What changes |
|---|---|---|
| `alembic/versions/XXX_add_category_verification.py` | Create | Migration: 2 new columns on `issues` |
| `app/models/issue.py` | Modify | Add `category_verified`, `require_child_verification` fields |
| `app/api/endpoints/issue_config.py` | Modify | Add fields to `IssueTreeNode`; add `POST /{id}/verify` |
| `app/services/sync_service.py` | Modify | `_upsert_issue` sets `category_verified=False` for new issues |
| `tests/api/test_category_verify.py` | Create | Tests for verify endpoint |
| `tests/api/test_sync_category_verified.py` | Create | Tests for sync setting verified flag |
| `frontend/src/types/api.ts` | Modify | Add 2 fields to `IssueTreeNode` |
| `frontend/src/api/issues.ts` | Modify | Add `verifyIssue()` fn |
| `frontend/src/hooks/useIssueTree.ts` | Modify | Add `useVerifyIssue()` hook |
| `frontend/src/pages/SyncPage.tsx` | Modify | matchesTab, buildTabData, 2 new stack-only columns |

---

## Task 1: DB Migration + Issue Model Fields

**Files:**
- Create: `alembic/versions/XXX_add_category_verification.py`
- Modify: `app/models/issue.py`

- [ ] **Step 1: Generate migration file**

```bash
alembic revision -m "add_category_verification"
```

Expected output: `Generating .../alembic/versions/<hash>_add_category_verification.py`
Note the `<hash>` — you need it for step 2.

- [ ] **Step 2: Write migration content**

Open the generated file and replace its content with (substitute `<hash>` with the generated value and set `down_revision = 'e97b35c021a7'`):

```python
"""add category verification fields to issues

Revision ID: <hash>
Revises: e97b35c021a7
Create Date: 2026-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '<hash>'
down_revision: Union[str, None] = 'e97b35c021a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'category_verified',
            sa.Boolean(),
            nullable=False,
            server_default='1',
        ))
        batch_op.add_column(sa.Column(
            'require_child_verification',
            sa.Boolean(),
            nullable=False,
            server_default='0',
        ))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('require_child_verification')
        batch_op.drop_column('category_verified')
```

- [ ] **Step 3: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade e97b35c021a7 -> <hash>, add category verification fields to issues`

- [ ] **Step 4: Add fields to Issue model**

In `app/models/issue.py`, after line 90 (`assigned_category` field), add:

```python
    category_verified: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    require_child_verification: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
```

- [ ] **Step 5: Verify model import works**

```bash
py -3.10 -c "from app.models.issue import Issue; print(Issue.category_verified)"
```

Expected: `Issue.category_verified`

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ app/models/issue.py
git commit -m "feat(db): add category_verified + require_child_verification to issues"
```

---

## Task 2: Backend Verify Endpoint (TDD)

**Files:**
- Create: `tests/api/test_category_verify.py`
- Modify: `app/api/endpoints/issue_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_category_verify.py`:

```python
"""Tests for POST /issues/{id}/verify endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.issue import Issue
from app.models.project import Project
import app.models  # noqa: F401


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    epic = Issue(
        id="epic1", jira_issue_id="100", key="PRJ-100",
        summary="Epic", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=False, require_child_verification=False,
    )
    child1 = Issue(
        id="ch1", jira_issue_id="101", key="PRJ-101",
        summary="Child 1", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=False,
    )
    child2 = Issue(
        id="ch2", jira_issue_id="102", key="PRJ-102",
        summary="Child 2", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=False,
    )
    grandchild = Issue(
        id="gc1", jira_issue_id="103", key="PRJ-103",
        summary="Grandchild", issue_type="Sub-task", status="To Do",
        project_id="p1", parent_id="ch1", category_verified=False,
    )
    already_verified = Issue(
        id="av1", jira_issue_id="104", key="PRJ-104",
        summary="Already verified", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=True,
    )
    db.add_all([epic, child1, child2, grandchild, already_verified])
    db.commit()


def test_verify_single_issue(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/ch1/verify", json={
        "cascade": False,
        "require_child_verification": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["verified_count"] == 1
    db.expire_all()
    assert db.get(Issue, "ch1").category_verified is True
    # ch2 and gc1 untouched
    assert db.get(Issue, "ch2").category_verified is False
    assert db.get(Issue, "gc1").category_verified is False


def test_verify_with_cascade(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/epic1/verify", json={
        "cascade": True,
        "require_child_verification": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # epic + ch1 + ch2 + gc1 = 4 (av1 was already verified, skipped)
    assert body["verified_count"] == 4
    db.expire_all()
    for issue_id in ["epic1", "ch1", "ch2", "gc1"]:
        assert db.get(Issue, issue_id).category_verified is True


def test_verify_sets_require_child_verification(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/epic1/verify", json={
        "cascade": False,
        "require_child_verification": True,
    })
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Issue, "epic1").require_child_verification is True


def test_verify_404_on_missing(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/nonexistent/verify", json={
        "cascade": False,
        "require_child_verification": False,
    })
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
py -3.10 -m pytest tests/api/test_category_verify.py -v
```

Expected: `FAILED` (ImportError or AttributeError — endpoint does not exist yet)

- [ ] **Step 3: Add `IssueTreeNode` fields to schema**

In `app/api/endpoints/issue_config.py`, add to `IssueTreeNode` class (after `is_container: bool = False`):

```python
    category_verified: bool = True
    require_child_verification: bool = False
```

- [ ] **Step 4: Add `VerifyRequest` schema**

In `app/api/endpoints/issue_config.py`, after the `BatchCategoryRequest` class:

```python
class VerifyRequest(BaseModel):
    cascade: bool = False
    require_child_verification: bool = False
```

- [ ] **Step 5: Add verify endpoint**

In `app/api/endpoints/issue_config.py`, after the `batch_set_category` endpoint (around line 376), add:

```python
def _collect_unverified_descendants(db: Session, parent_id: str) -> list[Issue]:
    """BFS — все потомки с category_verified=False."""
    result: list[Issue] = []
    frontier = [parent_id]
    while frontier:
        children = db.query(Issue).filter(Issue.parent_id.in_(frontier)).all()
        frontier = []
        for ch in children:
            if not ch.category_verified:
                result.append(ch)
            frontier.append(ch.id)
    return result


@router.post("/{issue_id}/verify")
async def verify_issue(
    issue_id: str,
    body: VerifyRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Подтвердить категорию задачи (переводит из «Стека к разбору» в нужную вкладку).

    cascade=True — рекурсивно подтверждает всех непроверенных потомков.
    require_child_verification сохраняется на задаче и управляет тем,
    попадут ли будущие новые дочерние задачи в стек автоматически.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    verified_count = 0
    if not issue.category_verified:
        issue.category_verified = True
        verified_count += 1
    issue.require_child_verification = body.require_child_verification

    if body.cascade:
        for descendant in _collect_unverified_descendants(db, issue_id):
            descendant.category_verified = True
            verified_count += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues"]})
    return {"ok": True, "verified_count": verified_count}
```

- [ ] **Step 6: Add `category_verified`/`require_child_verification` to tree endpoint**

In `get_issue_tree`, the `IssueTreeNode(...)` constructor call (around line 156). Add these two lines inside the call:

```python
            category_verified=issue.category_verified if issue.category_verified is not None else True,
            require_child_verification=issue.require_child_verification if issue.require_child_verification is not None else False,
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
py -3.10 -m pytest tests/api/test_category_verify.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 8: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/api/test_category_verify.py
git commit -m "feat(api): POST /issues/{id}/verify endpoint with cascade support"
```

---

## Task 3: Sync Service — Set `category_verified` for New Issues

**Files:**
- Create: `tests/api/test_sync_category_verified.py`
- Modify: `app/services/sync_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/test_sync_category_verified.py`:

```python
"""Tests for category_verified assignment in _upsert_issue."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.issue import Issue
from app.models.project import Project
import app.models  # noqa: F401


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_sync_service(db):
    """Minimal SyncService initialisation for unit testing _upsert_issue indirectly."""
    from unittest.mock import MagicMock, AsyncMock
    from app.services.sync_service import SyncService
    svc = SyncService.__new__(SyncService)
    svc.db = db
    from app.repositories.issue import IssueRepository
    svc.issue_repo = IssueRepository(db)
    # Stub everything else the constructor touches
    svc.connector = MagicMock()
    svc.project_repo = MagicMock()
    svc.worklog_repo = MagicMock()
    svc.employee_repo = MagicMock()
    svc._settings_cache = {}
    return svc


def _jira_issue(jira_id: str, key: str):
    from unittest.mock import MagicMock
    ji = MagicMock()
    ji.id = jira_id
    ji.key = key
    ji.fields.summary = "Test"
    ji.fields.description_text = None
    ji.fields.issuetype.name = "Task"
    ji.fields.status.name = "To Do"
    ji.fields.status.statusCategory = None
    ji.fields.priority = None
    ji.fields.statuscategorychangedate = None
    ji.fields.duedate = None
    ji.fields.assignee = None
    ji.fields._extra = {}
    return ji


def test_new_issue_no_parent_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id=None)
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_new_issue_parent_verified_no_flag_is_auto_verified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=True, require_child_verification=False,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is True


def test_new_issue_parent_verified_with_flag_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=True, require_child_verification=True,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_new_issue_parent_unverified_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=False, require_child_verification=False,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_existing_issue_verified_flag_not_changed(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    existing = Issue(
        id="ex1", jira_issue_id="100", key="PRJ-100",
        summary="Existing", issue_type="Task", status="To Do",
        project_id="p1", category_verified=True,
    )
    db.add(existing)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id=None)
    db.flush()
    assert created is False
    assert issue.category_verified is True  # unchanged
```

- [ ] **Step 2: Run to confirm failure**

```bash
py -3.10 -m pytest tests/api/test_sync_category_verified.py -v
```

Expected: `FAILED` — tests for new-issue pass `category_verified=True` (server default), not `False`.

- [ ] **Step 3: Modify `_upsert_issue` in sync_service.py**

In `app/services/sync_service.py`, the very end of `_upsert_issue` — replace the final `return` statement:

```python
        return self.issue_repo.upsert_by_field(
            "jira_issue_id",
            jira_issue.id,
            data,
        )
```

With:

```python
        issue, created = self.issue_repo.upsert_by_field(
            "jira_issue_id",
            jira_issue.id,
            data,
        )
        if created:
            auto_verify = False
            if parent_id:
                parent = self.db.get(Issue, parent_id)
                if (parent
                        and parent.category_verified
                        and not parent.require_child_verification):
                    auto_verify = True
            issue.category_verified = auto_verify
        return issue, created
```

Add the `Issue` import at the top of `sync_service.py` if not already present (it should be — check with `grep "from app.models" app/services/sync_service.py`).

- [ ] **Step 4: Run tests to confirm pass**

```bash
py -3.10 -m pytest tests/api/test_sync_category_verified.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: existing tests still pass (pre-existing failures unaffected).

- [ ] **Step 6: Commit**

```bash
git add app/services/sync_service.py tests/api/test_sync_category_verified.py
git commit -m "feat(sync): set category_verified=False for newly synced issues"
```

---

## Task 4: Frontend Types, API Function, Hook

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/issues.ts`
- Modify: `frontend/src/hooks/useIssueTree.ts`

- [ ] **Step 1: Add fields to `IssueTreeNode`**

In `frontend/src/types/api.ts`, in the `IssueTreeNode` interface (around line 140), add after `is_container: boolean;`:

```typescript
  category_verified: boolean;
  require_child_verification: boolean;
```

- [ ] **Step 2: Add `verifyIssue` to API module**

In `frontend/src/api/issues.ts`, add after the `batchSetCategory` export:

```typescript
export interface VerifyIssueResponse {
  ok: boolean;
  verified_count: number;
}

export const verifyIssue = (
  issueId: string,
  cascade: boolean,
  requireChildVerification: boolean,
) =>
  api.post<VerifyIssueResponse>(`/issues/${issueId}/verify`, {
    cascade,
    require_child_verification: requireChildVerification,
  });
```

Note: check that `api.post` exists in `frontend/src/api/client.ts`. If only `api.put` exists, use `api.put` and adjust the backend route to `PUT`. If `api.post` is missing, add it as:

```typescript
// In client.ts, alongside the existing put():
post: <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
```

- [ ] **Step 3: Add `useVerifyIssue` hook**

In `frontend/src/hooks/useIssueTree.ts`, add at the end of the file:

```typescript
export function useVerifyIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      issueId,
      cascade,
      requireChildVerification,
    }: {
      issueId: string;
      cascade: boolean;
      requireChildVerification: boolean;
    }) => verifyIssue(issueId, cascade, requireChildVerification),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
}
```

Also add `verifyIssue` to the import on line 2:

```typescript
import { getIssueTree, setIssueCategory, setIssueInclude, batchSetCategory, verifyIssue } from '../api/issues';
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds (or only pre-existing errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/issues.ts frontend/src/hooks/useIssueTree.ts frontend/src/api/client.ts
git commit -m "feat(frontend): IssueTreeNode verified fields + verifyIssue API + hook"
```

---

## Task 5: Frontend SyncPage — `matchesTab` + `buildTabData`

**Files:**
- Modify: `frontend/src/pages/SyncPage.tsx`

This task updates the routing logic so unverified issues always land in the stack tab.

- [ ] **Step 1: Update `matchesTab` signature and logic**

In `frontend/src/pages/SyncPage.tsx`, replace the `matchesTab` function (lines 78–91):

```typescript
function matchesTab(effective: string | null, verified: boolean, tab: InnerTab): boolean {
  if (!verified) return tab === 'stack';
  switch (tab) {
    case 'stack': return effective === null;
    case 'active':
      return (
        effective !== null
        && !ARCHIVE_CODES.has(effective)
        && effective !== INITIATIVES_CODE
      );
    case 'initiatives': return effective === INITIATIVES_CODE;
    case 'archive_target': return effective === 'archive_target';
    case 'archive': return effective === 'archive';
  }
}
```

- [ ] **Step 2: Update all `matchesTab` call sites**

There are two call sites inside `CategoryConfigTab`:

**In `buildTabData`** (the `filter` predicate, around line 254):
```typescript
        const selfMatches = matchesTab(effectiveFor(n), n.category_verified ?? true, tab);
```

**In `countTriage`** (around line 285):
```typescript
          if (matchesTab(effectiveFor(node), node.category_verified ?? true, tab)) n++;
```

- [ ] **Step 3: Add `category_verified` to `TreeNodeWithChildren`**

The `TreeNodeWithChildren` type is defined at the top of `CategoryConfigTab`. Add the inherited fields (they come from `IssueTreeNode` which already has them now — no change needed since it's `Omit<IssueTreeNode, 'children'> & {...}`). Confirm the type already picks up `category_verified` and `require_child_verification` from `IssueTreeNode`. If `TreeNodeWithChildren` uses `Omit<IssueTreeNode, 'children'>`, the new fields are automatically included.

- [ ] **Step 4: Check TypeScript**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|warning" | head -20
```

Expected: no new errors from the `matchesTab` changes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SyncPage.tsx
git commit -m "feat(frontend): matchesTab routes unverified issues to stack tab"
```

---

## Task 6: Frontend — Stack-Only Columns (Toggle + Confirm Button)

**Files:**
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 1: Add state for pending verify flags and verify mutation**

Inside `CategoryConfigTab`, after the existing state declarations (around line 184):

```typescript
  const [pendingVerifyFlags, setPendingVerifyFlags] = useState<Map<string, boolean>>(new Map());
  const verifyMut = useVerifyIssue();
```

Import `useVerifyIssue` at the top where hooks are imported:

```typescript
import { useIssueTree, useSetIssueInclude, useBatchSetCategory, useVerifyIssue } from '../hooks/useIssueTree';
```

Also import `Switch` from antd (add to existing AntD import):

```typescript
import {
  Button, Card, Space, Table, Tag, App,
  Tabs, Select, Typography, Modal, Checkbox, Popconfirm, DatePicker, Progress, Switch,
} from 'antd';
```

- [ ] **Step 2: Add `handleVerify` callback**

After the `toggleInclude` callback (around line 408), add:

```typescript
  const handleVerify = useCallback((
    issueId: string,
    cascade: boolean,
    hasChildren: boolean,
  ) => {
    const requireChildVerification = pendingVerifyFlags.get(issueId) ?? false;
    verifyMut.mutate(
      { issueId, cascade, requireChildVerification },
      {
        onError: (err) => {
          notification.error({ message: 'Ошибка верификации', description: (err as Error).message });
        },
      },
    );
  }, [pendingVerifyFlags, verifyMut, notification]);
```

- [ ] **Step 3: Add helper to count unverified descendants in stackData**

After `descendantCounts` memo (around line 278), add a helper function (outside the component, near `matchesTab`):

```typescript
function countUnverifiedBelow(node: TreeNodeWithChildren): number {
  let count = 0;
  for (const child of node.children ?? []) {
    if (!child.category_verified) count++;
    count += countUnverifiedBelow(child);
  }
  return count;
}
```

- [ ] **Step 4: Add stack-only columns**

The current `columns` are used for all tabs. We need two extra columns only in the stack tab. Replace the `columns` memo and its usage.

**Step 4a** — keep the existing `columns` memo unchanged (it becomes `baseColumns`). Rename the variable to `baseColumns`:

```typescript
  const baseColumns = useMemo(() => {
    // ... (all existing column definitions, unchanged)
    return base.map(col => ({
      ...col,
      onHeaderCell: () => ({ width: col.width, onResize: handleResize(col.key) }),
    }));
  }, [
    widths, jiraBaseUrl,
    pendingCats, categoryOptions, categoryLabels, descendantCounts,
    setPendingCategory, toggleInclude, handleResize,
  ]);
```

**Step 4b** — add stack columns memo after `baseColumns`:

```typescript
  const stackExtraColumns = useMemo(() => [
    {
      title: 'Верифиц. детей',
      key: 'requireChildVerification',
      width: 120,
      onHeaderCell: () => ({ width: 120, onResize: handleResize('requireChildVerification') }),
      render: (_: unknown, record: TreeNodeWithChildren) => {
        if (record.issue_type === 'group' || record.is_context) return null;
        const hasChildren = (record.children?.length ?? 0) > 0;
        if (!hasChildren) return <span style={{ color: '#595959' }}>—</span>;
        const checked = pendingVerifyFlags.get(record.id) ?? record.require_child_verification ?? false;
        return (
          <Switch
            size="small"
            checked={checked}
            onChange={(val) => {
              setPendingVerifyFlags(prev => {
                const next = new Map(prev);
                next.set(record.id, val);
                return next;
              });
            }}
          />
        );
      },
    },
    {
      title: 'Действие',
      key: 'verify',
      width: 160,
      onHeaderCell: () => ({ width: 160, onResize: handleResize('verify') }),
      render: (_: unknown, record: TreeNodeWithChildren) => {
        if (record.issue_type === 'group' || record.is_context) return null;
        const hasChildren = (record.children?.length ?? 0) > 0;
        const unverifiedBelow = hasChildren ? countUnverifiedBelow(record) : 0;
        if (hasChildren) {
          return (
            <Button
              type="primary"
              size="small"
              loading={verifyMut.isPending}
              onClick={() => handleVerify(record.id, true, true)}
            >
              Подтвердить{unverifiedBelow > 0 ? ` +${unverifiedBelow}` : ''}
            </Button>
          );
        }
        return (
          <Button
            size="small"
            loading={verifyMut.isPending}
            onClick={() => handleVerify(record.id, false, false)}
          >
            Подтвердить
          </Button>
        );
      },
    },
  ], [pendingVerifyFlags, verifyMut.isPending, handleVerify, handleResize]);
```

**Step 4c** — combine columns based on active tab:

```typescript
  const columns = innerTab === 'stack'
    ? [...baseColumns, ...stackExtraColumns]
    : baseColumns;
```

Also update `widths` initial state to include the new columns:

```typescript
  const [widths, setWidths] = useState<Record<string, number>>({
    key: 110, summary: 380, status: 140, statusChanged: 150, goals: 110,
    category: 260, include: 80,
    requireChildVerification: 120, verify: 160,
  });
```

- [ ] **Step 5: Update table to use `columns` (not `baseColumns`)**

The `<Table>` component uses `columns={columns as never}` — this already references `columns` which is now the combined or base array. No change needed to the JSX.

- [ ] **Step 6: Verify TypeScript and build**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds.

- [ ] **Step 7: Manual smoke test**

Start backend and frontend:
```bash
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173/sync`. Navigate to the Категоризация задач tab. Verify:
1. Stack tab shows unverified issues (if any new ones synced) 
2. "Верифиц. детей" and "Действие" columns appear only in Stack tab, not in other tabs
3. "Подтвердить" button on a parent shows "+N дочерних" count
4. Clicking "Подтвердить" on a leaf moves it out of stack tab after reload

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/SyncPage.tsx
git commit -m "feat(frontend): stack tab verify columns — toggle + confirm button"
```

---

## Task 7: Push and Done

- [ ] **Step 1: Run full test suite one more time**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: new tests pass; no regressions in existing tests (pre-existing failures unchanged).

- [ ] **Step 2: Push to origin**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ `category_verified` + `require_child_verification` fields — Task 1
- ✅ Migration DEFAULT TRUE for existing — Task 1 migration
- ✅ Sync sets FALSE for new issues — Task 3
- ✅ Auto-trust logic (parent verified + flag OFF) — Task 3
- ✅ POST /verify endpoint with cascade — Task 2
- ✅ `IssueTreeNode` fields exposed in API — Task 2
- ✅ matchesTab uses verified flag — Task 5
- ✅ "Верифиц. детей" toggle column — Task 6
- ✅ "Подтвердить" button column (parent = cascade, leaf = single) — Task 6
- ✅ Existing tasks verified=TRUE — handled by migration server_default
- ✅ No change to other tabs — stack-only columns via `innerTab === 'stack'` conditional

**Placeholder scan:** None. All code blocks are complete.

**Type consistency:**
- `verifyIssue(issueId, cascade, requireChildVerification)` in api matches hook params `{ issueId, cascade, requireChildVerification }`
- `require_child_verification: bool` snake_case in Python matches `requireChildVerification` camelCase in TS (serialized as `require_child_verification` in JSON body)
- `IssueTreeNode.category_verified: boolean` used as `n.category_verified ?? true` throughout — consistent
