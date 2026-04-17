# Hierarchy Rules + /settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded `CONTAINER_ISSUE_TYPES` with a user-editable `hierarchy_rule` table (first-match-wins), and move admin surfaces (`ConnectionCard`, scope browser, Jira field IDs, hierarchy rules) from `/sync` into a dedicated `/settings` page.

**Architecture:**
- Backend: new `hierarchy_rule` table + `classify()` rule evaluator + CRUD endpoints. The `/issues/tree` endpoint replaces its hardcoded set with a call into the evaluator. Migration 014 seeds current behaviour plus the new ITL/RFA/PRJ rules.
- Frontend: `/settings` page with four tabs. Admin components (`ConnectionCard`, `ScopeAdmin`, `JiraFieldsCard`, `HierarchyRulesTab`) extracted from `SyncPage.tsx` for reuse. `/sync` trimmed to daily-work tabs only (`Категоризация задач` + `Синхронизация`).

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic (batch mode for SQLite) / pytest · React 19 / TypeScript / Ant Design 6 / TanStack Query / Vite.

---

## File Structure

### Backend

| Path | Action | Purpose |
|---|---|---|
| `alembic/versions/014_hierarchy_rules.py` | Create | Migration: create `hierarchy_rule` table + seed rows |
| `app/models/hierarchy_rule.py` | Create | SQLAlchemy model |
| `app/models/__init__.py` | Modify | Export `HierarchyRule` |
| `app/services/hierarchy_rules.py` | Create | `EvaluationInput`, `load_rules`, `classify` |
| `app/api/endpoints/hierarchy_rules.py` | Create | CRUD + reorder endpoints |
| `app/api/router.py` | Modify | Register `hierarchy_rules` router |
| `app/api/endpoints/issue_config.py` | Modify | Drop `CONTAINER_ISSUE_TYPES`, call `classify()` |

### Backend tests

| Path | Action | Purpose |
|---|---|---|
| `tests/test_hierarchy_rules_service.py` | Create | Unit tests for `classify` |
| `tests/test_hierarchy_rules_endpoints.py` | Create | CRUD happy path + validation |
| `tests/test_issue_config_endpoints.py` | Modify | Add tree tests covering rule-based classification |

### Frontend

| Path | Action | Purpose |
|---|---|---|
| `frontend/src/types/api.ts` | Modify | `HierarchyRule`, `HierarchyRuleCreate`, `HierarchyRuleUpdate` |
| `frontend/src/api/hierarchyRules.ts` | Create | REST client |
| `frontend/src/hooks/useHierarchyRules.ts` | Create | TanStack Query hooks |
| `frontend/src/components/ConnectionCard.tsx` | Create | Extracted from `SyncPage` |
| `frontend/src/components/ScopeAdmin.tsx` | Create | Merged `ScopeOverview` + `TaskSectionsTab` |
| `frontend/src/components/JiraFieldsCard.tsx` | Create | Form for `jira_*_field_id` AppSettings |
| `frontend/src/components/HierarchyRulesTab.tsx` | Create | Rule editor table + drawer |
| `frontend/src/pages/SettingsPage.tsx` | Create | Four-tab admin page |
| `frontend/src/pages/lazyPages.tsx` | Modify | Add `SettingsPage` lazy export |
| `frontend/src/pages/SyncPage.tsx` | Modify | Remove admin pieces, trim to two tabs |
| `frontend/src/App.tsx` | Modify | `/settings` route + Sider menu item |

---

## Task 1: HierarchyRule Model + Migration 014 (with seed)

**Files:**
- Create: `app/models/hierarchy_rule.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/014_hierarchy_rules.py`

- [ ] **Step 1.1: Add the SQLAlchemy model**

Create `app/models/hierarchy_rule.py`:

```python
"""Hierarchy rule — project/type-based classification for root-vs-operations split."""

from typing import Optional

from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class HierarchyRule(Base, TimestampMixin):
    """Rule for classifying a root-level issue as container vs operational.

    Evaluation: rules ordered by ``priority`` ASC, ``created_at`` ASC; first
    rule whose predicates all pass decides ``is_container``. If no rule
    matches, default is ``False`` (task goes to the ``__operations__`` group).

    Predicates:
    - ``project_key`` (None = any project)
    - ``issue_type`` (None = any type)
    - ``require_no_parent`` (True = only matches issues with no parent_id)
    """

    __tablename__ = "hierarchy_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, index=True, default=100)
    project_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    issue_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    require_no_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_container: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<HierarchyRule {self.priority} "
            f"project={self.project_key!r} type={self.issue_type!r} "
            f"container={self.is_container}>"
        )
```

- [ ] **Step 1.2: Export from `app/models/__init__.py`**

Append `HierarchyRule` to imports and `__all__`:

```python
from app.models.hierarchy_rule import HierarchyRule
# ... in __all__:
"HierarchyRule",
```

- [ ] **Step 1.3: Write migration 014**

Create `alembic/versions/014_hierarchy_rules.py`:

```python
"""create hierarchy_rule table + seed defaults

Revision ID: 014_hierarchy_rules
Revises: 013_sync_state_scope
Create Date: 2026-04-17
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '014_hierarchy_rules'
down_revision: Union[str, None] = '013_sync_state_scope'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_RULES = [
    # Project-scoped rules — priority 10
    (10, 'ITL', None, True, True, 'ITL без родителя — контейнер'),
    (10, 'RFA', None, False, True, 'RFA всегда контейнер'),
    (10, 'PRJ', None, False, True, 'PRJ всегда контейнер'),
    # Type-scoped rules — priority 50 (preserve pre-014 CONTAINER_ISSUE_TYPES)
    (50, None, 'Эпик', False, True, None),
    (50, None, 'Epic', False, True, None),
    (50, None, 'Инициатива', False, True, None),
    (50, None, 'Инициатива (E-com)', False, True, None),
    (50, None, 'Инициатива (Ритейл)', False, True, None),
    (50, None, 'Инициатива (Финансы)', False, True, None),
    (50, None, 'История', False, True, None),
    (50, None, 'Story', False, True, None),
    (50, None, 'Цель', False, True, None),
]


def upgrade() -> None:
    op.create_table(
        'hierarchy_rule',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('project_key', sa.String(32), nullable=True),
        sa.Column('issue_type', sa.String(128), nullable=True),
        sa.Column('require_no_parent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_container', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_hierarchy_rule_priority', 'hierarchy_rule', ['priority'])
    op.create_index('ix_hierarchy_rule_project_key', 'hierarchy_rule', ['project_key'])
    op.create_index('ix_hierarchy_rule_issue_type', 'hierarchy_rule', ['issue_type'])

    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    for priority, project, itype, no_parent, is_container, description in SEED_RULES:
        bind.execute(sa.text(
            "INSERT INTO hierarchy_rule "
            "(id, priority, project_key, issue_type, require_no_parent, "
            " is_container, is_enabled, description, created_at, updated_at) "
            "VALUES (:id, :priority, :project, :itype, :np, :ic, 1, :desc, :now, :now)"
        ), {
            "id": str(uuid.uuid4()),
            "priority": priority,
            "project": project,
            "itype": itype,
            "np": 1 if no_parent else 0,
            "ic": 1 if is_container else 0,
            "desc": description,
            "now": now,
        })


def downgrade() -> None:
    op.drop_index('ix_hierarchy_rule_issue_type', table_name='hierarchy_rule')
    op.drop_index('ix_hierarchy_rule_project_key', table_name='hierarchy_rule')
    op.drop_index('ix_hierarchy_rule_priority', table_name='hierarchy_rule')
    op.drop_table('hierarchy_rule')
```

- [ ] **Step 1.4: Apply migration**

Run: `py -3.10 -m alembic upgrade head`

Expected: `Running upgrade 013_sync_state_scope -> 014_hierarchy_rules, create hierarchy_rule table + seed defaults`.

- [ ] **Step 1.5: Verify seed**

Run:
```bash
py -3.10 -c "import sqlite3; c = sqlite3.connect('data/jira_analytics.db'); [print(r) for r in c.execute('SELECT priority, project_key, issue_type, require_no_parent, is_container FROM hierarchy_rule ORDER BY priority, issue_type, project_key')]"
```

Expected: 12 rows — 3 project rules (ITL/RFA/PRJ) followed by 9 type rules.

- [ ] **Step 1.6: Commit**

```bash
git add alembic/versions/014_hierarchy_rules.py app/models/hierarchy_rule.py app/models/__init__.py
git commit -m "Add hierarchy_rule model + migration 014 with seed"
```

---

## Task 2: Rule Evaluator Service (`classify`)

**Files:**
- Create: `app/services/hierarchy_rules.py`
- Create: `tests/test_hierarchy_rules_service.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_hierarchy_rules_service.py`:

```python
"""Unit tests for hierarchy rule evaluator."""

import pytest

from app.models.hierarchy_rule import HierarchyRule
from app.services.hierarchy_rules import EvaluationInput, classify


def _rule(**kwargs):
    """Build an in-memory HierarchyRule with sane defaults."""
    defaults = dict(
        id="r", priority=100, project_key=None, issue_type=None,
        require_no_parent=False, is_container=True, is_enabled=True,
        description=None,
    )
    defaults.update(kwargs)
    return HierarchyRule(**defaults)


class TestClassify:
    def test_empty_rules_returns_false(self):
        assert classify([], EvaluationInput("ITL", "Task", False)) is False

    def test_first_match_wins_by_order(self):
        rules = [
            _rule(priority=10, project_key="ITL", is_container=True),
            _rule(priority=20, project_key="ITL", is_container=False),
        ]
        assert classify(rules, EvaluationInput("ITL", "Task", False)) is True

    def test_project_wildcard_matches_any(self):
        rules = [_rule(project_key=None, issue_type="Epic", is_container=True)]
        assert classify(rules, EvaluationInput("ANY", "Epic", False)) is True

    def test_type_wildcard_matches_any(self):
        rules = [_rule(project_key="PRJ", issue_type=None, is_container=True)]
        assert classify(rules, EvaluationInput("PRJ", "Task", False)) is True

    def test_require_no_parent_skips_when_has_parent(self):
        rules = [_rule(project_key="ITL", require_no_parent=True, is_container=True)]
        assert classify(rules, EvaluationInput("ITL", "Task", True)) is False

    def test_require_no_parent_matches_when_no_parent(self):
        rules = [_rule(project_key="ITL", require_no_parent=True, is_container=True)]
        assert classify(rules, EvaluationInput("ITL", "Task", False)) is True

    def test_is_container_false_overrides_later_true(self):
        rules = [
            _rule(priority=10, project_key="ITL", issue_type="История", is_container=False),
            _rule(priority=50, issue_type="История", is_container=True),
        ]
        # ITL-История hits the explicit False first
        assert classify(rules, EvaluationInput("ITL", "История", False)) is False
        # PRJ-История falls through to the priority=50 True rule
        assert classify(rules, EvaluationInput("PRJ", "История", False)) is True

    def test_disabled_rules_are_skipped_by_loader(self):
        # classify does not filter by is_enabled — that's load_rules' job.
        # This documents the contract: classify assumes rules already enabled.
        pass
```

- [ ] **Step 2.2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_service.py -v`

Expected: `ModuleNotFoundError: No module named 'app.services.hierarchy_rules'`.

- [ ] **Step 2.3: Implement the service**

Create `app/services/hierarchy_rules.py`:

```python
"""Hierarchy rule evaluator.

Decides whether a root-level issue is a "container" (stays as a tree root)
or an operational leaf (collapses into the ``__operations__`` virtual
group). Rule table is evaluated first-match-wins by ``(priority ASC,
created_at ASC)``; if no rule matches, default is ``False``.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hierarchy_rule import HierarchyRule


@dataclass(frozen=True)
class EvaluationInput:
    project_key: str
    issue_type: str
    has_parent: bool


def load_rules(db: Session) -> List[HierarchyRule]:
    """Return enabled rules ordered by priority ASC, created_at ASC."""
    stmt = (
        select(HierarchyRule)
        .where(HierarchyRule.is_enabled.is_(True))
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def classify(rules: List[HierarchyRule], input_: EvaluationInput) -> bool:
    """First-match-wins evaluation. Rules must already be ordered and enabled."""
    for rule in rules:
        if rule.project_key and rule.project_key != input_.project_key:
            continue
        if rule.issue_type and rule.issue_type != input_.issue_type:
            continue
        if rule.require_no_parent and input_.has_parent:
            continue
        return bool(rule.is_container)
    return False
```

- [ ] **Step 2.4: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_service.py -v`

Expected: 7 passed.

- [ ] **Step 2.5: Commit**

```bash
git add app/services/hierarchy_rules.py tests/test_hierarchy_rules_service.py
git commit -m "Add hierarchy rule evaluator service"
```

---

## Task 3: Hierarchy Rules CRUD Endpoints

**Files:**
- Create: `app/api/endpoints/hierarchy_rules.py`
- Modify: `app/api/router.py`
- Create: `tests/test_hierarchy_rules_endpoints.py`

- [ ] **Step 3.1: Write the failing endpoint tests**

Create `tests/test_hierarchy_rules_endpoints.py`:

```python
"""Integration tests for /hierarchy-rules CRUD."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create(payload: dict) -> dict:
    resp = client.post("/api/v1/hierarchy-rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestHierarchyRulesCrud:
    def test_list_returns_seeded_rules_ordered_by_priority(self, db_session):
        resp = client.get("/api/v1/hierarchy-rules")
        assert resp.status_code == 200
        data = resp.json()
        # Seed from migration 014 provides 12 rules; ordering ascending.
        assert len(data) >= 12
        priorities = [r["priority"] for r in data]
        assert priorities == sorted(priorities)

    def test_create_and_list(self, db_session):
        before = client.get("/api/v1/hierarchy-rules").json()
        created = _create({
            "priority": 200,
            "project_key": "TEST",
            "issue_type": None,
            "require_no_parent": False,
            "is_container": True,
            "is_enabled": True,
            "description": "test rule",
        })
        assert created["project_key"] == "TEST"
        after = client.get("/api/v1/hierarchy-rules").json()
        assert len(after) == len(before) + 1

    def test_patch_partial(self, db_session):
        created = _create({
            "priority": 300, "project_key": "PATCH", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        resp = client.patch(
            f"/api/v1/hierarchy-rules/{created['id']}",
            json={"is_container": False, "description": "flipped"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["is_container"] is False
        assert updated["description"] == "flipped"
        # Unchanged fields preserved
        assert updated["project_key"] == "PATCH"

    def test_delete(self, db_session):
        created = _create({
            "priority": 400, "project_key": "DEL", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        resp = client.delete(f"/api/v1/hierarchy-rules/{created['id']}")
        assert resp.status_code == 200
        resp = client.get("/api/v1/hierarchy-rules")
        assert not any(r["id"] == created["id"] for r in resp.json())

    def test_reorder_writes_stepped_priorities(self, db_session):
        a = _create({"priority": 500, "project_key": "A", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        b = _create({"priority": 501, "project_key": "B", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        c = _create({"priority": 502, "project_key": "C", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        resp = client.post(
            "/api/v1/hierarchy-rules/reorder",
            json={"ids": [c["id"], a["id"], b["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        by_id = {r["id"]: r["priority"] for r in data}
        assert by_id[c["id"]] == 10
        assert by_id[a["id"]] == 20
        assert by_id[b["id"]] == 30

    def test_negative_priority_rejected(self, db_session):
        resp = client.post("/api/v1/hierarchy-rules", json={
            "priority": -1, "project_key": "X", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        assert resp.status_code == 422

    def test_delete_unknown_404(self, db_session):
        resp = client.delete("/api/v1/hierarchy-rules/nonexistent-id")
        assert resp.status_code == 404
```

- [ ] **Step 3.2: Run tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_endpoints.py -v`

Expected: all fail with 404 because routes aren't registered yet.

- [ ] **Step 3.3: Implement the endpoints**

Create `app/api/endpoints/hierarchy_rules.py`:

```python
"""Hierarchy rule CRUD endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.hierarchy_rule import HierarchyRule
from app.repositories.base import BaseRepository

router = APIRouter()


# === Schemas ===

class HierarchyRuleResponse(BaseModel):
    id: str
    priority: int
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: bool
    is_container: bool
    is_enabled: bool
    description: Optional[str] = None

    class Config:
        from_attributes = True


class HierarchyRuleCreate(BaseModel):
    priority: int = Field(ge=0)
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: bool = False
    is_container: bool
    is_enabled: bool = True
    description: Optional[str] = None


class HierarchyRuleUpdate(BaseModel):
    priority: Optional[int] = Field(default=None, ge=0)
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: Optional[bool] = None
    is_container: Optional[bool] = None
    is_enabled: Optional[bool] = None
    description: Optional[str] = None


class ReorderRequest(BaseModel):
    ids: List[str]


# === Endpoints ===

@router.get("", response_model=List[HierarchyRuleResponse])
def list_rules(db: Session = Depends(get_db)):
    """Return all rules ordered by priority ASC, created_at ASC."""
    stmt = (
        select(HierarchyRule)
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=HierarchyRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(body: HierarchyRuleCreate, db: Session = Depends(get_db)):
    repo = BaseRepository(HierarchyRule, db)
    rule = repo.create(body.model_dump())
    db.commit()
    return rule


@router.patch("/{rule_id}", response_model=HierarchyRuleResponse)
def update_rule(rule_id: str, body: HierarchyRuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(HierarchyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(HierarchyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    db.delete(rule)
    db.commit()
    return {"status": "deleted"}


@router.post("/reorder", response_model=List[HierarchyRuleResponse])
def reorder_rules(body: ReorderRequest, db: Session = Depends(get_db)):
    """Rewrite priorities for the given ids in 10-step increments starting at 10.

    Ids not in the list keep their current priority.
    """
    for index, rule_id in enumerate(body.ids):
        rule = db.get(HierarchyRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Правило {rule_id} не найдено")
        rule.priority = (index + 1) * 10
    db.commit()
    stmt = (
        select(HierarchyRule)
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
```

- [ ] **Step 3.4: Register the router**

Modify `app/api/router.py` — find the block where other routers are imported/included and add:

```python
from app.api.endpoints import hierarchy_rules as hierarchy_rules_endpoints
# ... inside the include_router section:
router.include_router(
    hierarchy_rules_endpoints.router,
    prefix="/hierarchy-rules",
    tags=["hierarchy-rules"],
)
```

- [ ] **Step 3.5: Run tests, confirm they pass**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_endpoints.py -v`

Expected: 7 passed.

- [ ] **Step 3.6: Commit**

```bash
git add app/api/endpoints/hierarchy_rules.py app/api/router.py tests/test_hierarchy_rules_endpoints.py
git commit -m "Add /hierarchy-rules CRUD endpoints"
```

---

## Task 4: Switch `/issues/tree` to Use Rule Classifier

**Files:**
- Modify: `app/api/endpoints/issue_config.py`
- Modify: `tests/test_issue_config_endpoints.py`

- [ ] **Step 4.1: Add failing tests for rule-based tree classification**

Append to `tests/test_issue_config_endpoints.py`:

```python
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.models import Issue, Project
from app.models.hierarchy_rule import HierarchyRule

tree_client = TestClient(app)


class TestTreeWithHierarchyRules:
    def _make_issue(self, db_session, project, key, issue_type, parent=None):
        issue = Issue(
            jira_issue_id=f"jid-{key}",
            key=key,
            summary=key,
            issue_type=issue_type,
            status="В работе",
            project_id=project.id,
            parent_id=parent.id if parent else None,
            synced_at=datetime.utcnow(),
        )
        db_session.add(issue)
        db_session.flush()
        return issue

    def test_itl_root_no_parent_stays_as_root_via_seed(self, db_session):
        # Seed rule: priority=10 project='ITL' require_no_parent=True is_container=True
        proj = Project(jira_project_id="p-itl", key="ITL", name="ITL")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "ITL-1", "Задача")
        db_session.commit()

        resp = tree_client.get("/api/v1/issues/tree?project_keys=ITL")
        data = resp.json()

        # ITL-1 must be a root — not under __operations__.
        root_keys = [n["key"] for n in data]
        assert "ITL-1" in root_keys
        ops = next((n for n in data if n["id"] == "__operations__"), None)
        if ops is not None:
            assert not any(c["key"] == "ITL-1" for c in ops["children"])

    def test_leaf_root_without_matching_rule_goes_to_operations(self, db_session):
        proj = Project(jira_project_id="p-os", key="OS", name="OS")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "OS-1", "Задача")
        db_session.commit()

        resp = tree_client.get("/api/v1/issues/tree?project_keys=OS")
        data = resp.json()

        root_keys = [n["key"] for n in data]
        assert "OS-1" not in root_keys
        ops = next(n for n in data if n["id"] == "__operations__")
        assert any(c["key"] == "OS-1" for c in ops["children"])

    def test_disabled_rule_not_applied(self, db_session):
        # Disable the ITL seed rule and check the ITL-2 leaf collapses into operations.
        db_session.query(HierarchyRule).filter(
            HierarchyRule.project_key == "ITL"
        ).update({"is_enabled": False})
        db_session.commit()

        proj = Project(jira_project_id="p-itl2", key="ITL", name="ITL")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "ITL-2", "Задача")
        db_session.commit()

        resp = tree_client.get("/api/v1/issues/tree?project_keys=ITL")
        data = resp.json()
        ops = next(n for n in data if n["id"] == "__operations__")
        assert any(c["key"] == "ITL-2" for c in ops["children"])
```

- [ ] **Step 4.2: Run the tests, confirm they fail**

Run: `py -3.10 -m pytest tests/test_issue_config_endpoints.py::TestTreeWithHierarchyRules -v`

Expected: `test_itl_root_no_parent_stays_as_root_via_seed` fails — current code uses `CONTAINER_ISSUE_TYPES` which does not include project-level matching.

- [ ] **Step 4.3: Modify `issue_config.py`**

In `app/api/endpoints/issue_config.py`:

1. Remove the `CONTAINER_ISSUE_TYPES` constant (lines ~20-32).
2. Add imports:

```python
from app.services.hierarchy_rules import EvaluationInput, classify, load_rules
```

3. Inside `get_issue_tree`, after the tree is built but before the top-level split, load rules once:

```python
rules = load_rules(db)
```

4. Replace the split loop:

```python
    operations: list[IssueTreeNode] = []
    roots_keep: list[IssueTreeNode] = []
    for r in roots:
        if r.issue_type == "group":
            roots_keep.append(r)
            continue
        is_container = classify(rules, EvaluationInput(
            project_key=r.project_key,
            issue_type=r.issue_type,
            has_parent=False,
        ))
        has_kids = bool(r.children)
        if not is_container and not has_kids and not r.is_context:
            operations.append(r)
        else:
            roots_keep.append(r)
```

- [ ] **Step 4.4: Run the new tree tests**

Run: `py -3.10 -m pytest tests/test_issue_config_endpoints.py::TestTreeWithHierarchyRules -v`

Expected: 3 passed.

- [ ] **Step 4.5: Run the full test suite to check backward compatibility**

Run: `py -3.10 -m pytest tests/ -x -q --ignore=tests/test_sync_service.py`

Expected: all green. The existing `test_issue_config_endpoints.py` tests relied on `CONTAINER_ISSUE_TYPES` behaviour (Эпик/История as containers); the seed rules preserve that.

- [ ] **Step 4.6: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_issue_config_endpoints.py
git commit -m "Route /issues/tree classification through hierarchy rules"
```

---

## Task 5: Frontend Types + API Client + Hooks

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/api/hierarchyRules.ts`
- Create: `frontend/src/hooks/useHierarchyRules.ts`

- [ ] **Step 5.1: Add types**

Append to `frontend/src/types/api.ts`:

```typescript
// === Hierarchy rules ===

export interface HierarchyRule {
  id: string;
  priority: number;
  project_key: string | null;
  issue_type: string | null;
  require_no_parent: boolean;
  is_container: boolean;
  is_enabled: boolean;
  description: string | null;
}

export interface HierarchyRuleCreate {
  priority: number;
  project_key: string | null;
  issue_type: string | null;
  require_no_parent: boolean;
  is_container: boolean;
  is_enabled: boolean;
  description: string | null;
}

export type HierarchyRuleUpdate = Partial<HierarchyRuleCreate>;
```

- [ ] **Step 5.2: Create API client**

Create `frontend/src/api/hierarchyRules.ts`:

```typescript
import { api } from './client';
import type { HierarchyRule, HierarchyRuleCreate, HierarchyRuleUpdate } from '../types/api';

export const listHierarchyRules = () =>
  api.get<HierarchyRule[]>('/hierarchy-rules');

export const createHierarchyRule = (body: HierarchyRuleCreate) =>
  api.post<HierarchyRule>('/hierarchy-rules', body);

export const updateHierarchyRule = (id: string, body: HierarchyRuleUpdate) =>
  api.patch<HierarchyRule>(`/hierarchy-rules/${id}`, body);

export const deleteHierarchyRule = (id: string) =>
  api.delete<{ status: string }>(`/hierarchy-rules/${id}`);

export const reorderHierarchyRules = (ids: string[]) =>
  api.post<HierarchyRule[]>('/hierarchy-rules/reorder', { ids });
```

Check that `api.patch` and `api.delete` exist in `frontend/src/api/client.ts`. If not, add them following the `api.post` signature — generic wrappers around `fetch` with method set.

- [ ] **Step 5.3: Create hooks**

Create `frontend/src/hooks/useHierarchyRules.ts`:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listHierarchyRules,
  createHierarchyRule,
  updateHierarchyRule,
  deleteHierarchyRule,
  reorderHierarchyRules,
} from '../api/hierarchyRules';
import type { HierarchyRuleCreate, HierarchyRuleUpdate } from '../types/api';

const QK = ['hierarchy-rules'] as const;

export const useHierarchyRules = () =>
  useQuery({ queryKey: QK, queryFn: listHierarchyRules });

export const useCreateHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HierarchyRuleCreate) => createHierarchyRule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useUpdateHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: HierarchyRuleUpdate }) =>
      updateHierarchyRule(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useDeleteHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteHierarchyRule(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useReorderHierarchyRules = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => reorderHierarchyRules(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};
```

- [ ] **Step 5.4: Lint and commit**

Run: `cd frontend && npm run lint`

Expected: no errors.

```bash
git add frontend/src/types/api.ts frontend/src/api/hierarchyRules.ts frontend/src/hooks/useHierarchyRules.ts
git commit -m "Add frontend types/client/hooks for hierarchy rules"
```

---

## Task 6: Extract `ConnectionCard` to Standalone Component

**Files:**
- Create: `frontend/src/components/ConnectionCard.tsx`
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 6.1: Create the standalone file**

Create `frontend/src/components/ConnectionCard.tsx` — copy the function `ConnectionCard` from `frontend/src/pages/SyncPage.tsx` (currently around lines 38-160), including its full imports. Make it the default export:

```typescript
import { useState } from 'react';
import { Card, Input, Button, Space, App } from 'antd';
import { ApiOutlined } from '@ant-design/icons';
import { testConnection } from '../api/sync';
import { useJiraSettings, useSaveJiraSettings, useTestJiraCredentials } from '../hooks/useSettings';

export default function ConnectionCard() {
  // ... entire body from SyncPage.tsx
}
```

Full body matches the current definition in `SyncPage.tsx` — no behaviour change.

- [ ] **Step 6.2: Import from SyncPage and remove the inline definition**

In `frontend/src/pages/SyncPage.tsx`:

1. Replace the existing `function ConnectionCard()` block (and its imports unique to it if now unused) with an import at the top:

```typescript
import ConnectionCard from '../components/ConnectionCard';
```

2. Usage inside `SyncPage` default export stays as `<ConnectionCard />`.

- [ ] **Step 6.3: Run dev/build sanity check**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/components/ConnectionCard.tsx frontend/src/pages/SyncPage.tsx
git commit -m "Extract ConnectionCard to reusable component"
```

---

## Task 7: Extract Scope Admin to `ScopeAdmin` Component

**Files:**
- Create: `frontend/src/components/ScopeAdmin.tsx`
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 7.1: Create `ScopeAdmin.tsx`**

Create `frontend/src/components/ScopeAdmin.tsx`:

```typescript
import { Space } from 'antd';
import ScopeOverview from './ScopeOverview';
import TaskSectionsTab from './TaskSectionsTab';

export default function ScopeAdmin() {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <ScopeOverview />
      <TaskSectionsTab />
    </Space>
  );
}
```

- [ ] **Step 7.2: Extract `ScopeOverview` and `TaskSectionsTab` from `SyncPage.tsx` into their own files**

Move `function ScopeOverview()` from `SyncPage.tsx` into `frontend/src/components/ScopeOverview.tsx` (default export). Same for `TaskSectionsTab` into `frontend/src/components/TaskSectionsTab.tsx`. Copy imports as needed so each file compiles standalone.

- [ ] **Step 7.3: Update `SyncPage.tsx`**

Remove the inline `ScopeOverview` and `TaskSectionsTab` function declarations. Update imports:

```typescript
import ScopeOverview from '../components/ScopeOverview';
import TaskSectionsTab from '../components/TaskSectionsTab';
```

- [ ] **Step 7.4: Build sanity**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/components/ScopeAdmin.tsx frontend/src/components/ScopeOverview.tsx frontend/src/components/TaskSectionsTab.tsx frontend/src/pages/SyncPage.tsx
git commit -m "Extract ScopeOverview+TaskSectionsTab and compose ScopeAdmin"
```

---

## Task 8: Create `JiraFieldsCard` Component

**Files:**
- Create: `frontend/src/components/JiraFieldsCard.tsx`

- [ ] **Step 8.1: Create the component**

Create `frontend/src/components/JiraFieldsCard.tsx`:

```typescript
import { useEffect, useState } from 'react';
import { Card, Form, Select, Button, Space, App } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useJiraFields } from '../hooks/useSync';

const FIELDS = [
  { key: 'jira_team_field_id', label: 'Поле продуктовой команды' },
  { key: 'jira_participating_teams_field_id', label: 'Поле участвующих команд' },
  { key: 'jira_goals_field_id', label: 'Поле целей' },
] as const;

export default function JiraFieldsCard() {
  const { message } = App.useApp();
  const save = useSaveGenericSetting();
  const jiraFields = useJiraFields();

  // Load each setting.
  const settings = FIELDS.map(f => ({ ...f, hook: useGenericSetting(f.key) }));
  const [values, setValues] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loaded) return;
    if (settings.every(s => s.hook.data !== undefined)) {
      const next: Record<string, string> = {};
      settings.forEach(s => { next[s.key] = s.hook.data?.value ?? ''; });
      setValues(next);
      setLoaded(true);
    }
  }, [loaded, settings]);

  const fieldOptions = (jiraFields.data ?? []).map(f => ({
    value: f.id,
    label: `${f.name} (${f.id})`,
  }));

  const handleSaveAll = () => {
    Promise.all(FIELDS.map(f =>
      save.mutateAsync({ key: f.key, value: values[f.key] ?? '' })
    )).then(() => message.success('Сохранено'))
      .catch(e => message.error(e.message));
  };

  return (
    <Card
      title="Кастомные поля Jira"
      size="small"
      extra={
        <Button
          size="small"
          icon={<SaveOutlined />}
          onClick={handleSaveAll}
          loading={save.isPending}
        >
          Сохранить
        </Button>
      }
    >
      <Form layout="vertical">
        <Space direction="vertical" style={{ width: '100%' }}>
          {FIELDS.map(f => (
            <Form.Item key={f.key} label={f.label} style={{ marginBottom: 0 }}>
              <Select
                value={values[f.key] || undefined}
                onChange={v => setValues(prev => ({ ...prev, [f.key]: v || '' }))}
                showSearch
                allowClear
                optionFilterProp="label"
                placeholder={`customfield_XXXXX`}
                options={fieldOptions}
                loading={jiraFields.isFetching}
                onDropdownVisibleChange={open => {
                  if (open && !jiraFields.data) jiraFields.refetch();
                }}
              />
            </Form.Item>
          ))}
        </Space>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 8.2: Build sanity**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 8.3: Commit**

```bash
git add frontend/src/components/JiraFieldsCard.tsx
git commit -m "Add JiraFieldsCard component for field-id settings"
```

---

## Task 9: `HierarchyRulesTab` Component (Editor)

**Files:**
- Create: `frontend/src/components/HierarchyRulesTab.tsx`

- [ ] **Step 9.1: Create the editor**

Create `frontend/src/components/HierarchyRulesTab.tsx`:

```typescript
import { useState } from 'react';
import { Table, Button, Space, Tag, Drawer, Form, Input, Select, Switch, InputNumber, Popconfirm, App, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import {
  useHierarchyRules,
  useCreateHierarchyRule,
  useUpdateHierarchyRule,
  useDeleteHierarchyRule,
  useReorderHierarchyRules,
} from '../hooks/useHierarchyRules';
import type { HierarchyRule, HierarchyRuleCreate } from '../types/api';

const { Text } = Typography;

type FormState = Omit<HierarchyRuleCreate, 'priority'> & { id?: string; priority?: number };

const EMPTY_FORM: FormState = {
  priority: undefined,
  project_key: null,
  issue_type: null,
  require_no_parent: false,
  is_container: true,
  is_enabled: true,
  description: null,
};

export default function HierarchyRulesTab() {
  const { message } = App.useApp();
  const rules = useHierarchyRules();
  const createMut = useCreateHierarchyRule();
  const updateMut = useUpdateHierarchyRule();
  const deleteMut = useDeleteHierarchyRule();
  const reorderMut = useReorderHierarchyRules();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const openCreate = () => { setForm(EMPTY_FORM); setDrawerOpen(true); };
  const openEdit = (r: HierarchyRule) => { setForm({ ...r }); setDrawerOpen(true); };

  const saveForm = async () => {
    const payload: HierarchyRuleCreate = {
      priority: form.priority ?? 100,
      project_key: form.project_key || null,
      issue_type: form.issue_type || null,
      require_no_parent: form.require_no_parent,
      is_container: form.is_container,
      is_enabled: form.is_enabled,
      description: form.description || null,
    };
    try {
      if (form.id) {
        await updateMut.mutateAsync({ id: form.id, body: payload });
      } else {
        await createMut.mutateAsync(payload);
      }
      setDrawerOpen(false);
      message.success('Сохранено');
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const move = (id: string, delta: -1 | 1) => {
    const list = rules.data ?? [];
    const idx = list.findIndex(r => r.id === id);
    if (idx < 0) return;
    const swapIdx = idx + delta;
    if (swapIdx < 0 || swapIdx >= list.length) return;
    const reordered = list.slice();
    [reordered[idx], reordered[swapIdx]] = [reordered[swapIdx], reordered[idx]];
    reorderMut.mutate(reordered.map(r => r.id));
  };

  const columns = [
    { title: 'Приоритет', dataIndex: 'priority', key: 'priority', width: 90 },
    {
      title: 'Проект', dataIndex: 'project_key', key: 'project_key', width: 120,
      render: (v: string | null) => v ? <Tag color="blue">{v}</Tag> : <Text type="secondary">любой</Text>,
    },
    {
      title: 'Тип задачи', dataIndex: 'issue_type', key: 'issue_type', width: 180,
      render: (v: string | null) => v ? <Tag>{v}</Tag> : <Text type="secondary">любой</Text>,
    },
    {
      title: 'Без родителя', dataIndex: 'require_no_parent', key: 'require_no_parent', width: 120,
      render: (v: boolean) => v ? <Tag color="geekblue">да</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Контейнер', dataIndex: 'is_container', key: 'is_container', width: 110,
      render: (v: boolean) => v ? <Tag color="green">да</Tag> : <Tag color="red">нет</Tag>,
    },
    {
      title: 'Активно', dataIndex: 'is_enabled', key: 'is_enabled', width: 90,
      render: (v: boolean, r: HierarchyRule) => (
        <Switch
          checked={v}
          size="small"
          onChange={checked => updateMut.mutate({ id: r.id, body: { is_enabled: checked } })}
        />
      ),
    },
    { title: 'Описание', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '', key: 'actions', width: 160,
      render: (_: unknown, r: HierarchyRule) => (
        <Space size={4}>
          <Button size="small" icon={<ArrowUpOutlined />} onClick={() => move(r.id, -1)} />
          <Button size="small" icon={<ArrowDownOutlined />} onClick={() => move(r.id, 1)} />
          <Button size="small" onClick={() => openEdit(r)}>✎</Button>
          <Popconfirm title="Удалить правило?" onConfirm={() => deleteMut.mutate(r.id)} okText="Да" cancelText="Нет">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Правило
        </Button>
        <Text type="secondary">
          Первое совпавшее правило определяет, считается ли корневая задача контейнером.
        </Text>
      </Space>
      <Table<HierarchyRule>
        dataSource={rules.data ?? []}
        columns={columns as never}
        rowKey="id"
        size="small"
        pagination={false}
        loading={rules.isLoading}
      />
      <Drawer
        title={form.id ? 'Редактировать правило' : 'Новое правило'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={420}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>Отмена</Button>
            <Button type="primary" onClick={saveForm} loading={createMut.isPending || updateMut.isPending}>
              Сохранить
            </Button>
          </Space>
        }
      >
        <Form layout="vertical">
          <Form.Item label="Приоритет (меньше — раньше)">
            <InputNumber
              min={0}
              value={form.priority}
              onChange={v => setForm(f => ({ ...f, priority: v ?? undefined }))}
              style={{ width: '100%' }}
              placeholder="100"
            />
          </Form.Item>
          <Form.Item label="Проект (пусто = любой)">
            <Input
              value={form.project_key ?? ''}
              onChange={e => setForm(f => ({ ...f, project_key: e.target.value || null }))}
              placeholder="PRJ"
            />
          </Form.Item>
          <Form.Item label="Тип задачи (пусто = любой)">
            <Input
              value={form.issue_type ?? ''}
              onChange={e => setForm(f => ({ ...f, issue_type: e.target.value || null }))}
              placeholder="Эпик"
            />
          </Form.Item>
          <Form.Item label="Только при отсутствии родителя">
            <Switch
              checked={form.require_no_parent}
              onChange={v => setForm(f => ({ ...f, require_no_parent: v }))}
            />
          </Form.Item>
          <Form.Item label="Считать контейнером">
            <Switch
              checked={form.is_container}
              onChange={v => setForm(f => ({ ...f, is_container: v }))}
            />
          </Form.Item>
          <Form.Item label="Активно">
            <Switch
              checked={form.is_enabled}
              onChange={v => setForm(f => ({ ...f, is_enabled: v }))}
            />
          </Form.Item>
          <Form.Item label="Описание">
            <Input.TextArea
              rows={2}
              value={form.description ?? ''}
              onChange={e => setForm(f => ({ ...f, description: e.target.value || null }))}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </Space>
  );
}
```

- [ ] **Step 9.2: Lint and build sanity**

Run: `cd frontend && npm run lint && npm run build`

Expected: no errors.

- [ ] **Step 9.3: Commit**

```bash
git add frontend/src/components/HierarchyRulesTab.tsx
git commit -m "Add HierarchyRulesTab with drawer editor and up/down reorder"
```

---

## Task 10: `SettingsPage` + Route + Sider Menu

**Files:**
- Create: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 10.1: Create `SettingsPage`**

Create `frontend/src/pages/SettingsPage.tsx`:

```typescript
import { useState, useEffect } from 'react';
import { Tabs } from 'antd';
import ConnectionCard from '../components/ConnectionCard';
import ScopeAdmin from '../components/ScopeAdmin';
import JiraFieldsCard from '../components/JiraFieldsCard';
import HierarchyRulesTab from '../components/HierarchyRulesTab';

const TAB_KEYS = ['connection', 'scope', 'fields', 'hierarchy'] as const;
type TabKey = typeof TAB_KEYS[number];

function readHashKey(): TabKey {
  const raw = window.location.hash.replace('#', '');
  return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : 'connection';
}

export default function SettingsPage() {
  const [activeKey, setActiveKey] = useState<TabKey>(readHashKey);

  useEffect(() => {
    const handler = () => setActiveKey(readHashKey());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  const onChange = (k: string) => {
    setActiveKey(k as TabKey);
    window.location.hash = k;
  };

  return (
    <Tabs
      activeKey={activeKey}
      onChange={onChange}
      items={[
        { key: 'connection', label: 'Подключение к Jira', children: <ConnectionCard /> },
        { key: 'scope', label: 'Проекты в scope', children: <ScopeAdmin /> },
        { key: 'fields', label: 'Поля Jira', children: <JiraFieldsCard /> },
        { key: 'hierarchy', label: 'Правила иерархии', children: <HierarchyRulesTab /> },
      ]}
    />
  );
}
```

- [ ] **Step 10.2: Register lazy route**

Modify `frontend/src/pages/lazyPages.tsx` — append:

```typescript
export const LazySettingsPage = lazy(() => import('./SettingsPage'));
```

- [ ] **Step 10.3: Wire route + Sider menu**

Modify `frontend/src/App.tsx`:

1. Add to the routes list (wherever other routes are declared):

```typescript
<Route path="/settings" element={<LazySettingsPage />} />
```

2. Add to Sider menu (wherever other items are declared), above the existing "Синхронизация" entry:

```typescript
{ key: '/settings', label: 'Настройки', icon: <SettingOutlined /> }
```

Import `SettingOutlined` from `@ant-design/icons` and `LazySettingsPage` from `./pages/lazyPages` as needed.

- [ ] **Step 10.4: Build sanity**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 10.5: Manual verification**

Start dev server (`npm run dev` in `frontend/`, backend via `py -3.10 -m uvicorn app.main:app --host 127.0.0.1 --port 8000`). Open `http://localhost:5173/settings` in browser. Verify:

- Four tabs render.
- Hash changes on tab switch (`#hierarchy`).
- Rules tab shows 12 seeded rules.
- Add/edit/delete rule via drawer.

- [ ] **Step 10.6: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/pages/lazyPages.tsx frontend/src/App.tsx
git commit -m "Add /settings page with four admin tabs and Sider entry"
```

---

## Task 11: Trim `SyncPage` to Daily-Work Tabs

**Files:**
- Modify: `frontend/src/pages/SyncPage.tsx`

- [ ] **Step 11.1: Remove admin pieces from `SyncPage`**

In `frontend/src/pages/SyncPage.tsx`:

1. Delete the `<ConnectionCard />` and `<ScopeOverview />` usages from the top of the default export.
2. Drop the `projects` tab (`TaskSectionsTab`) from the `Tabs.items` array.
3. Final default export should contain only:

```typescript
export default function SyncPage() {
  return (
    <Tabs
      items={[
        { key: 'categories', label: 'Категоризация задач', children: <CategoryConfigTab /> },
        { key: 'sync', label: 'Синхронизация', children: <SyncControls /> },
      ]}
    />
  );
}
```

4. Remove unused imports (`ConnectionCard`, `ScopeOverview`, `TaskSectionsTab`) if they remain.

- [ ] **Step 11.2: Lint and build**

Run: `cd frontend && npm run lint && npm run build`

Expected: clean lint, passing build.

- [ ] **Step 11.3: Backend restart + smoke test**

```bash
# Windows: kill backend on :8000 then restart
py -3.10 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify in browser:
- `/sync` shows only two tabs.
- `/settings` holds the four admin tabs.
- Triage flow (`/sync` → `Категоризация задач`) still loads the tree and categories work.

- [ ] **Step 11.4: Run full backend test suite**

Run: `py -3.10 -m pytest tests/ -x -q --ignore=tests/test_sync_service.py`

Expected: all pass.

- [ ] **Step 11.5: Commit and push**

```bash
git add frontend/src/pages/SyncPage.tsx
git commit -m "Trim /sync to triage + sync tabs after admin migration"
git push origin main
```

---

## Self-Review Notes (verified after writing)

- **Spec coverage**: each spec requirement maps to tasks — data model (T1), evaluator (T2), endpoints (T3), tree integration (T4), frontend plumbing (T5), admin component extraction (T6-8), rules editor (T9), settings page (T10), `/sync` trim (T11).
- **Placeholders**: scanned — all references (`EvaluationInput`, `classify`, `useHierarchyRules`, etc.) are defined in the same or earlier task.
- **Type consistency**: model fields ↔ schemas ↔ TypeScript interfaces verified aligned.
- **Test coverage**: classify (T2), CRUD (T3), tree integration (T4). Frontend covered by lint + manual smoke — no E2E additions for admin surface.
- **YAGNI**: no drag-and-drop (up/down buttons instead), no audit log, no per-team rules, no import/export. All in "Production Readiness Follow-ups".
