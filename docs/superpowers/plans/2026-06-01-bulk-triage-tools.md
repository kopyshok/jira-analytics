# Bulk Triage Tools для разбора 6000+ задач — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать новому PM с 6000 нераскрытыми задачами в «Стеке» инструменты массового разбора без раскрытия дерева — авто-предложения категорий + bulk-операции (архивировать по фильтру / принять подсказки / каскад от эпика).

**Architecture:** Backend получает четыре новых endpoint'а под префиксом `/issues/bulk/` — preview (без записи), archive-by-filter, accept-suggestions, cascade-inherit. Все работают с серверной перечислением задач (не требуют id-листа из фронта), используют существующие `CategoryResolver` + `BacklogService.sync_from_issue` + `EventBroadcaster`. Фронт добавляет на `/categories` кнопку «Массовые операции» → Drawer с тремя секциями; каждая делает preview → подтверждение → apply. После apply инвалидируется кэш дерева, derived category уже видна как placeholder в существующем `CategoryCell`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 ORM (backend); pytest для тестов endpoint'ов; React 19 + AntD 6 + TanStack Query (frontend); хранение состояния Drawer'а локальное (useState), без global store.

---

## File Structure

**Backend:**
- Create: `app/api/endpoints/issue_bulk.py` — новый router с 4 endpoint'ами под `/issues/bulk/*`
- Modify: `app/api/router.py` — include нового router'а под префикс `/issues` (тот же, что у `issue_config.py`)
- Modify: `app/schemas/__init__.py` *(if exists; иначе встроить схемы в endpoint module)*
- Test: `tests/test_issue_bulk_endpoints.py` — pytest, по тесту на каждый endpoint + edge cases

**Frontend:**
- Create: `frontend/src/components/categories/BulkTriageDrawer.tsx` — главный Drawer
- Create: `frontend/src/components/categories/sections/BulkArchiveSection.tsx`
- Create: `frontend/src/components/categories/sections/BulkAcceptSuggestionsSection.tsx`
- Create: `frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx`
- Create: `frontend/src/hooks/useBulkTriage.ts` — TanStack Query mutations
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx` — добавить кнопку «Массовые операции» в `.category-toolbar`, подключить Drawer

**Принципы декомпозиции:**
- Каждая секция — один файл с одной зоной ответственности. Они не делят state между собой (только общий callback закрытия Drawer'а).
- Хук `useBulkTriage.ts` инкапсулирует 4 мутации с правильной инвалидацией `['issues', 'tree', ...]`. Это единое место для cache invalidation — не дублировать по компонентам.
- Backend endpoints — в отдельном модуле от `issue_config.py`, чтобы single-issue + tree эндпоинты не разрастались. Общий префикс `/issues/bulk/`.

---

## Task 1: Backend — Pydantic-схемы фильтра и preview

**Files:**
- Create: `app/api/endpoints/issue_bulk.py`
- Test: `tests/test_issue_bulk_endpoints.py`

- [ ] **Step 1: Создать тест pytest на shape preview-схемы (фиктивный вызов)**

`tests/test_issue_bulk_endpoints.py`:

```python
"""Тесты bulk-эндпоинтов для массового разбора задач."""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Issue, Project


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_project(db, key="BULK", name="Bulk Test"):
    p = Project(
        id=f"proj-{key}",
        key=key,
        name=name,
        jira_id=f"jira-{key}",
    )
    db.add(p)
    db.flush()
    return p


def _mk_issue(db, project, key, **overrides):
    defaults = dict(
        id=f"issue-{key}",
        key=key,
        summary=f"Summary {key}",
        issue_type="Task",
        status="Открыто",
        project_id=project.id,
        jira_id=f"jira-{key}",
        category_verified=False,
        include_in_analysis=True,
    )
    defaults.update(overrides)
    i = Issue(**defaults)
    db.add(i)
    db.flush()
    return i


def test_bulk_preview_returns_filtered_issues(client, db):
    p = _mk_project(db)
    old_dt = datetime.now(timezone.utc) - timedelta(days=400)
    _mk_issue(db, p, "BULK-1", status="Закрыто", status_changed_at=old_dt.replace(tzinfo=None))
    _mk_issue(db, p, "BULK-2", status="Открыто")
    db.commit()

    try:
        resp = client.post("/api/v1/issues/bulk/preview", json={
            "filters": {
                "project_keys": ["BULK"],
                "statuses": ["Закрыто"],
            },
            "limit": 100,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["truncated"] is False
        assert len(data["items"]) == 1
        assert data["items"][0]["key"] == "BULK-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Запустить тест — должен упасть с 404 на /issues/bulk/preview**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py::test_bulk_preview_returns_filtered_issues -v`
Expected: FAIL — endpoint не зарегистрирован (404 либо коллекция роутеров пуста).

- [ ] **Step 3: Создать `app/api/endpoints/issue_bulk.py` со схемами и preview-стабом**

```python
"""Bulk-эндпоинты массового разбора задач (`/issues/bulk/*`).

Используются на странице «Категории задач» для PM-онбординга, когда в
стеке 1000+ задач и ручной разбор по дереву не масштабируется.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project
from app.services.backlog_service import BacklogService
from app.services.category_resolver import CategoryResolver
from app.services.event_bus import EventBroadcaster, get_event_bus

router = APIRouter()

ARCHIVE_CATEGORY_CODES = {"archive", "archive_target"}
MAX_BULK_LIMIT = 500


class BulkFilter(BaseModel):
    project_keys: Optional[List[str]] = None
    teams: Optional[List[str]] = None
    statuses: Optional[List[str]] = None
    status_changed_before: Optional[datetime] = None
    only_unverified: bool = False
    only_no_assigned: bool = False


class BulkPreviewRequest(BaseModel):
    filters: BulkFilter
    limit: int = Field(default=200, ge=1, le=MAX_BULK_LIMIT)


class BulkPreviewItem(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_changed_at: Optional[str] = None
    category: Optional[str] = None  # derived
    assigned_category: Optional[str] = None
    project_key: str


class BulkPreviewResponse(BaseModel):
    total: int
    truncated: bool
    items: List[BulkPreviewItem]


def _apply_filters(query, filters: BulkFilter, db: Session):
    """Применить фильтры к запросу Issue. Общий код preview + apply-эндпоинтов."""
    query = query.join(Project, Issue.project_id == Project.id)

    if filters.project_keys:
        query = query.filter(Project.key.in_(filters.project_keys))

    if filters.teams:
        clauses = []
        for t in filters.teams:
            t_json = json.dumps(t, ensure_ascii=False)
            clauses.append(Issue.team == t)
            clauses.append(Issue.participating_teams.like(f"%{t_json}%"))
        query = query.filter(or_(*clauses))

    if filters.statuses:
        query = query.filter(Issue.status.in_(filters.statuses))

    if filters.status_changed_before:
        cutoff = filters.status_changed_before
        if cutoff.tzinfo is not None:
            cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(Issue.status_changed_at < cutoff)

    if filters.only_unverified:
        query = query.filter(Issue.category_verified.is_(False))

    if filters.only_no_assigned:
        query = query.filter(Issue.assigned_category.is_(None))

    return query


@router.post("/bulk/preview", response_model=BulkPreviewResponse)
def bulk_preview(
    body: BulkPreviewRequest,
    db: Session = Depends(get_db),
):
    """Превью задач, попадающих под фильтр. Без модификаций."""
    base = _apply_filters(db.query(Issue), body.filters, db)
    total = base.count()
    rows = base.order_by(Issue.key).limit(body.limit).all()

    project_ids = {r.project_id for r in rows if r.project_id}
    pkey_by_id = {
        p.id: p.key
        for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
    } if project_ids else {}

    items = [
        BulkPreviewItem(
            id=r.id,
            key=r.key,
            summary=r.summary,
            status=r.status,
            status_changed_at=r.status_changed_at.isoformat() if r.status_changed_at else None,
            category=r.category,
            assigned_category=r.assigned_category,
            project_key=pkey_by_id.get(r.project_id, ""),
        )
        for r in rows
    ]
    return BulkPreviewResponse(
        total=total,
        truncated=total > body.limit,
        items=items,
    )
```

- [ ] **Step 4: Зарегистрировать router в `app/api/router.py`**

Modify: `app/api/router.py` — найти include секцию для `/issues` и добавить рядом:

```python
from app.api.endpoints import issue_bulk  # type: ignore

api_router.include_router(
    issue_bulk.router,
    prefix="/issues",
    tags=["issues"],
    dependencies=[Depends(get_current_user)],
)
```

(Точное место — рядом с existing `issue_config.router` include. Проверить, что `get_current_user` уже импортирован в файле.)

- [ ] **Step 5: Запустить тест preview — должен пройти**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py::test_bulk_preview_returns_filtered_issues -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/issue_bulk.py app/api/router.py tests/test_issue_bulk_endpoints.py
git commit -m "feat(issues): bulk preview endpoint для массового разбора"
```

---

## Task 2: Backend — bulk archive по фильтру

**Files:**
- Modify: `app/api/endpoints/issue_bulk.py` (добавить endpoint)
- Test: `tests/test_issue_bulk_endpoints.py` (добавить тесты)

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_issue_bulk_endpoints.py`:

```python
def test_bulk_archive_applies_to_matching(client, db):
    p = _mk_project(db, key="ARC")
    _mk_issue(db, p, "ARC-1", status="Закрыто", include_in_analysis=True)
    _mk_issue(db, p, "ARC-2", status="Закрыто", include_in_analysis=True)
    _mk_issue(db, p, "ARC-3", status="Открыто", include_in_analysis=True)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/archive", json={
            "filters": {"project_keys": ["ARC"], "statuses": ["Закрыто"]},
            "category_code": "archive",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["updated"] == 2
        assert sorted(data["archived_ids"]) == sorted(["issue-ARC-1", "issue-ARC-2"])

        db.expire_all()
        i1 = db.get(Issue, "issue-ARC-1")
        i3 = db.get(Issue, "issue-ARC-3")
        assert i1.assigned_category == "archive"
        assert i1.include_in_analysis is False
        assert i3.assigned_category is None
        assert i3.include_in_analysis is True
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_bulk_archive_rejects_non_archive_code(client, db):
    resp = client.post("/api/v1/issues/bulk/archive", json={
        "filters": {"project_keys": ["ARC"]},
        "category_code": "support",
    })
    assert resp.status_code == 400
    assert "архивн" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Запустить — должны упасть (404 на /bulk/archive)**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k bulk_archive`
Expected: FAIL.

- [ ] **Step 3: Добавить endpoint в `app/api/endpoints/issue_bulk.py`**

```python
class BulkArchiveRequest(BaseModel):
    filters: BulkFilter
    category_code: str  # должен быть archive | archive_target


class BulkApplyResponse(BaseModel):
    updated: int
    archived_ids: List[str]


@router.post("/bulk/archive", response_model=BulkApplyResponse)
async def bulk_archive(
    body: BulkArchiveRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Массовая архивация по фильтру.

    Принимает фильтр (как у preview) и архивный category_code. Применяет
    категорию ко всем матчащим задачам, снимает include_in_analysis.
    Запрещены не-архивные коды — для них используется существующий
    `/issues/batch-category` с явным списком id.
    """
    if body.category_code not in ARCHIVE_CATEGORY_CODES:
        raise HTTPException(
            status_code=400,
            detail="Эндпоинт принимает только архивные категории",
        )

    rows = _apply_filters(db.query(Issue), body.filters, db).all()
    resolver = CategoryResolver(db)
    backlog = BacklogService(db)
    archived_ids: list[str] = []
    for issue in rows:
        issue.assigned_category = body.category_code
        if issue.include_in_analysis:
            issue.include_in_analysis = False
            archived_ids.append(issue.id)
        issue.category = resolver.resolve_for_issue(issue).category_code
        backlog.sync_from_issue(issue)

    updated = len(rows)
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkApplyResponse(updated=updated, archived_ids=archived_ids)
```

- [ ] **Step 4: Запустить тесты — должны пройти**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k bulk_archive`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_bulk.py tests/test_issue_bulk_endpoints.py
git commit -m "feat(issues): bulk archive по фильтру (только archive_codes)"
```

---

## Task 3: Backend — bulk accept-suggestions

**Files:**
- Modify: `app/api/endpoints/issue_bulk.py`
- Test: `tests/test_issue_bulk_endpoints.py`

- [ ] **Step 1: Падающий тест**

```python
def test_bulk_accept_suggestions_writes_derived_into_assigned(client, db):
    p = _mk_project(db, key="SUG")
    # Issue с уже заполненным derived category (например, через worklog_quality_rules
    # или предков); для теста сетим прямо.
    _mk_issue(db, p, "SUG-1",
              category="support",
              assigned_category=None,
              category_verified=False)
    _mk_issue(db, p, "SUG-2",
              category=None,  # нет подсказки — должен быть skip
              assigned_category=None,
              category_verified=False)
    _mk_issue(db, p, "SUG-3",
              category="support",
              assigned_category="dev",  # уже своя — должен skip
              category_verified=True)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/accept-suggestions", json={
            "filters": {"project_keys": ["SUG"], "only_no_assigned": True},
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["applied"] == 1
        assert data["skipped_no_suggestion"] == 1

        db.expire_all()
        assert db.get(Issue, "issue-SUG-1").assigned_category == "support"
        assert db.get(Issue, "issue-SUG-1").category_verified is True
        assert db.get(Issue, "issue-SUG-2").assigned_category is None
        assert db.get(Issue, "issue-SUG-3").assigned_category == "dev"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Запустить — упадёт (404)**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k accept_suggestions`
Expected: FAIL.

- [ ] **Step 3: Добавить endpoint**

```python
class BulkAcceptSuggestionsRequest(BaseModel):
    filters: BulkFilter


class BulkAcceptResponse(BaseModel):
    applied: int
    skipped_no_suggestion: int


@router.post("/bulk/accept-suggestions", response_model=BulkAcceptResponse)
async def bulk_accept_suggestions(
    body: BulkAcceptSuggestionsRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Перенести derived category (Issue.category) в assigned_category
    для задач без своей категории. Подтверждает (category_verified=True).

    Задачи без derived подсказки (Issue.category=NULL) пропускаются.
    """
    rows = _apply_filters(db.query(Issue), body.filters, db).all()
    backlog = BacklogService(db)
    applied = 0
    skipped = 0
    archived_ids: list[str] = []
    for issue in rows:
        if issue.assigned_category is not None:
            # Безопасная страховка — обычно фильтр уже отсёк через only_no_assigned.
            continue
        if not issue.category:
            skipped += 1
            continue
        issue.assigned_category = issue.category
        issue.category_verified = True
        if issue.category in ARCHIVE_CATEGORY_CODES and issue.include_in_analysis:
            issue.include_in_analysis = False
            archived_ids.append(issue.id)
        backlog.sync_from_issue(issue)
        applied += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkAcceptResponse(applied=applied, skipped_no_suggestion=skipped)
```

- [ ] **Step 4: Запустить — пройдут**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k accept_suggestions`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_bulk.py tests/test_issue_bulk_endpoints.py
git commit -m "feat(issues): bulk accept-suggestions — derived → assigned"
```

---

## Task 4: Backend — bulk cascade-inherit от эпиков

**Files:**
- Modify: `app/api/endpoints/issue_bulk.py`
- Test: `tests/test_issue_bulk_endpoints.py`

- [ ] **Step 1: Падающий тест**

```python
def test_bulk_cascade_inherit_pushes_assigned_to_descendants(client, db):
    p = _mk_project(db, key="CAS")
    epic = _mk_issue(db, p, "CAS-1",
                     issue_type="Epic",
                     assigned_category="support",
                     category_verified=True)
    child1 = _mk_issue(db, p, "CAS-2",
                       parent_id=epic.id,
                       assigned_category=None,
                       category_verified=False)
    # Уже с собственной категорией — НЕ трогаем
    child2 = _mk_issue(db, p, "CAS-3",
                       parent_id=epic.id,
                       assigned_category="dev",
                       category_verified=True)
    grandchild = _mk_issue(db, p, "CAS-4",
                           parent_id=child1.id,
                           assigned_category=None,
                           category_verified=False)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/cascade-inherit", json={
            "ancestor_ids": [epic.id],
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["applied"] == 2

        db.expire_all()
        assert db.get(Issue, child1.id).assigned_category == "support"
        assert db.get(Issue, child1.id).category_verified is True
        assert db.get(Issue, child2.id).assigned_category == "dev"  # сохранилась
        assert db.get(Issue, grandchild.id).assigned_category == "support"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_bulk_cascade_inherit_rejects_ancestor_without_assigned(client, db):
    p = _mk_project(db, key="CAS2")
    epic = _mk_issue(db, p, "CAS2-1",
                     issue_type="Epic",
                     assigned_category=None)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/cascade-inherit", json={
            "ancestor_ids": [epic.id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] == 0
        assert data["skipped_ancestors"] == 1
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k cascade_inherit`
Expected: FAIL.

- [ ] **Step 3: Добавить endpoint**

```python
class BulkCascadeRequest(BaseModel):
    ancestor_ids: List[str]


class BulkCascadeResponse(BaseModel):
    applied: int
    skipped_ancestors: int


def _walk_subtree_no_assigned(db: Session, root_id: str) -> list[Issue]:
    """BFS вниз от root_id, останавливаемся на потомках с собственной
    assigned_category (граница). Сам root в результат не входит.
    """
    out: list[Issue] = []
    frontier = [root_id]
    visited: set[str] = {root_id}
    while frontier:
        children = db.query(Issue).filter(Issue.parent_id.in_(frontier)).all()
        next_frontier: list[str] = []
        for ch in children:
            if ch.id in visited:
                continue
            visited.add(ch.id)
            if ch.assigned_category is not None:
                # Граница каскада — ручной выбор PM. Поддерево под этой задачей
                # унаследует уже её код через CategoryResolver, не root'овый.
                continue
            out.append(ch)
            next_frontier.append(ch.id)
        frontier = next_frontier
    return out


@router.post("/bulk/cascade-inherit", response_model=BulkCascadeResponse)
async def bulk_cascade_inherit(
    body: BulkCascadeRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Протолкнуть assigned_category эпика/контейнера на всех потомков
    без своей категории. Останавливается на ручных решениях PM.
    """
    ancestors = db.query(Issue).filter(Issue.id.in_(body.ancestor_ids)).all()
    backlog = BacklogService(db)
    applied = 0
    skipped_ancestors = 0
    archived_ids: list[str] = []
    for anc in ancestors:
        if not anc.assigned_category:
            skipped_ancestors += 1
            continue
        descendants = _walk_subtree_no_assigned(db, anc.id)
        for d in descendants:
            d.assigned_category = anc.assigned_category
            d.category = anc.assigned_category
            d.category_verified = True
            if anc.assigned_category in ARCHIVE_CATEGORY_CODES and d.include_in_analysis:
                d.include_in_analysis = False
                archived_ids.append(d.id)
            backlog.sync_from_issue(d)
            applied += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkCascadeResponse(applied=applied, skipped_ancestors=skipped_ancestors)
```

- [ ] **Step 4: Запустить — пройдут**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v -k cascade_inherit`
Expected: PASS.

- [ ] **Step 5: Прогнать весь модуль — должны пройти 4 endpoint'а + edge cases**

Run: `py -3.10 -m pytest tests/test_issue_bulk_endpoints.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/issue_bulk.py tests/test_issue_bulk_endpoints.py
git commit -m "feat(issues): bulk cascade-inherit от эпика к поддереву"
```

---

## Task 5: Frontend — типы + хук useBulkTriage

**Files:**
- Create: `frontend/src/hooks/useBulkTriage.ts`
- Modify: `frontend/src/types/api.ts` (или соседний файл с API-типами; проверить структуру)

- [ ] **Step 1: Добавить типы в `frontend/src/types/api.ts`**

Найти место рядом с существующими IssueTreeNode types и добавить:

```typescript
export type BulkFilter = {
  project_keys?: string[];
  teams?: string[];
  statuses?: string[];
  status_changed_before?: string;
  only_unverified?: boolean;
  only_no_assigned?: boolean;
};

export type BulkPreviewItem = {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_changed_at: string | null;
  category: string | null;
  assigned_category: string | null;
  project_key: string;
};

export type BulkPreviewResponse = {
  total: number;
  truncated: boolean;
  items: BulkPreviewItem[];
};

export type BulkApplyResponse = { updated: number; archived_ids: string[] };
export type BulkAcceptResponse = { applied: number; skipped_no_suggestion: number };
export type BulkCascadeResponse = { applied: number; skipped_ancestors: number };
```

- [ ] **Step 2: Создать `frontend/src/hooks/useBulkTriage.ts`**

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type {
  BulkFilter,
  BulkPreviewResponse,
  BulkApplyResponse,
  BulkAcceptResponse,
  BulkCascadeResponse,
} from '../types/api';

function invalidateIssueCaches(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['issues'] });
  qc.invalidateQueries({ queryKey: ['analytics'] });
  qc.invalidateQueries({ queryKey: ['backlog'] });
}

export function useBulkPreview() {
  return useMutation({
    mutationFn: async (vars: { filters: BulkFilter; limit?: number }) =>
      api.post<BulkPreviewResponse>('/issues/bulk/preview', vars),
  });
}

export function useBulkArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { filters: BulkFilter; category_code: 'archive' | 'archive_target' }) =>
      api.post<BulkApplyResponse>('/issues/bulk/archive', vars),
    onSuccess: () => invalidateIssueCaches(qc),
  });
}

export function useBulkAcceptSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { filters: BulkFilter }) =>
      api.post<BulkAcceptResponse>('/issues/bulk/accept-suggestions', vars),
    onSuccess: () => invalidateIssueCaches(qc),
  });
}

export function useBulkCascadeInherit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { ancestor_ids: string[] }) =>
      api.post<BulkCascadeResponse>('/issues/bulk/cascade-inherit', vars),
    onSuccess: () => invalidateIssueCaches(qc),
  });
}
```

> **Caveat:** проверить, что `api.post<T>(path, body)` — существующая сигнатура клиента. Если нет — посмотреть `frontend/src/api/client.ts` и подогнать (например, `api('POST', path, body)`).

- [ ] **Step 3: Проверить компиляцию TypeScript**

Run: `cd frontend && npm run lint`
Expected: 0 ошибок в `useBulkTriage.ts` и `types/api.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useBulkTriage.ts frontend/src/types/api.ts
git commit -m "feat(categories): хук + типы для bulk-операций"
```

---

## Task 6: Frontend — BulkTriageDrawer skeleton

**Files:**
- Create: `frontend/src/components/categories/BulkTriageDrawer.tsx`
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`

- [ ] **Step 1: Создать скелет Drawer'а**

```tsx
import { useState } from 'react';
import { Drawer, Tabs, Typography } from 'antd';

const { Title, Text } = Typography;

type Props = {
  open: boolean;
  onClose: () => void;
  selectedTeams: string[];
  scopeProjectKeys: string[];
};

type Section = 'archive' | 'accept' | 'cascade';

export default function BulkTriageDrawer({
  open, onClose, selectedTeams, scopeProjectKeys,
}: Props) {
  const [active, setActive] = useState<Section>('archive');

  return (
    <Drawer
      title="Массовые операции"
      placement="right"
      width={680}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      <Title level={5} style={{ marginTop: 0 }}>
        Инструменты массового разбора
      </Title>
      <Text type="secondary">
        Для онбординга PM с большим стеком: архив по фильтру, применение
        подсказок резолвера, протяжка категории эпика на потомков.
      </Text>
      <Tabs
        activeKey={active}
        onChange={(k) => setActive(k as Section)}
        style={{ marginTop: 16 }}
        items={[
          { key: 'archive', label: 'Архив по фильтру', children: <Text type="secondary">См. Task 7</Text> },
          { key: 'accept', label: 'Принять подсказки', children: <Text type="secondary">См. Task 8</Text> },
          { key: 'cascade', label: 'Каскад от эпика', children: <Text type="secondary">См. Task 9</Text> },
        ]}
      />
    </Drawer>
  );
}
```

- [ ] **Step 2: Подключить Drawer в `CategoriesEditorPage.tsx`**

Найти `.category-toolbar` блок (примерно строка 971) и добавить state + кнопку + Drawer. Делается двумя edit'ами:

Edit 1 — добавить state и импорт сверху рядом с другими `useState`:

```typescript
import BulkTriageDrawer from '../components/categories/BulkTriageDrawer';
// ...
const [bulkDrawerOpen, setBulkDrawerOpen] = useState(false);
```

Edit 2 — добавить кнопку в правую часть `.category-toolbar` рядом с «Категория для отмеченных»:

```tsx
<Button
  icon={<ToolOutlined />}
  onClick={() => setBulkDrawerOpen(true)}
>
  Массовые операции
</Button>
```

(`ToolOutlined` — добавить в импорт из `@ant-design/icons`.)

Edit 3 — добавить сам Drawer перед закрывающим `</Space>` корневого fragment'а (примерно строка 1086, перед последним `</Space>`):

```tsx
<BulkTriageDrawer
  open={bulkDrawerOpen}
  onClose={() => setBulkDrawerOpen(false)}
  selectedTeams={selectedTeams}
  scopeProjectKeys={(scopeProjects.data ?? []).map(p => p.jira_project_key)}
/>
```

- [ ] **Step 3: Запустить dev — кнопка открывает Drawer с тремя пустыми вкладками**

Run: `cd frontend && npm run dev`
Expected: на `/categories` появилась кнопка «Массовые операции», Drawer открывается, в нём три вкладки с placeholder-текстом.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/categories/BulkTriageDrawer.tsx frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(categories): drawer-каркас для массовых операций"
```

---

## Task 7: Frontend — секция «Архив по фильтру»

**Files:**
- Create: `frontend/src/components/categories/sections/BulkArchiveSection.tsx`
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx`

- [ ] **Step 1: Создать BulkArchiveSection**

```tsx
import { useState } from 'react';
import { App, Button, DatePicker, Radio, Select, Space, Statistic, Typography, List, Tag } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useBulkPreview, useBulkArchive } from '../../../hooks/useBulkTriage';
import type { BulkFilter, BulkPreviewItem } from '../../../types/api';

const { Text } = Typography;

type Props = {
  selectedTeams: string[];
  scopeProjectKeys: string[];
  onApplied: () => void;
};

export default function BulkArchiveSection({ selectedTeams, scopeProjectKeys, onApplied }: Props) {
  const { message, modal } = App.useApp();
  const [statuses, setStatuses] = useState<string[]>(['Закрыто', 'Отменено']);
  const [olderThan, setOlderThan] = useState<Dayjs | null>(dayjs().subtract(365, 'day'));
  const [categoryCode, setCategoryCode] = useState<'archive' | 'archive_target'>('archive');
  const [preview, setPreview] = useState<{ total: number; truncated: boolean; items: BulkPreviewItem[] } | null>(null);

  const previewMut = useBulkPreview();
  const archiveMut = useBulkArchive();

  const buildFilters = (): BulkFilter => ({
    project_keys: scopeProjectKeys.length > 0 ? scopeProjectKeys : undefined,
    teams: selectedTeams.length > 0 ? selectedTeams : undefined,
    statuses: statuses.length > 0 ? statuses : undefined,
    status_changed_before: olderThan ? olderThan.toISOString() : undefined,
  });

  const runPreview = async () => {
    const filters = buildFilters();
    const res = await previewMut.mutateAsync({ filters, limit: 200 });
    setPreview(res);
  };

  const runArchive = () => {
    if (!preview || preview.total === 0) return;
    modal.confirm({
      title: `Архивировать ${preview.total} задач?`,
      content: 'Им проставится архивная категория, флаг «В анализ» снимется. Откатить можно только вручную.',
      okText: 'Архивировать',
      okType: 'danger',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await archiveMut.mutateAsync({
          filters: buildFilters(),
          category_code: categoryCode,
        });
        message.success(`Архивировано: ${res.updated}, исключено из анализа: ${res.archived_ids.length}`);
        setPreview(null);
        onApplied();
      },
    });
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Фильтр запускается на стороне сервера. По командным фильтрам учитывается
        глобальная выборка команды.
      </Text>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Архивная категория</Text>
        <Radio.Group value={categoryCode} onChange={(e) => setCategoryCode(e.target.value)}>
          <Radio value="archive">Архив неактуальных задач</Radio>
          <Radio value="archive_target">Архив квартальных целей</Radio>
        </Radio.Group>
      </Space>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Статусы</Text>
        <Select
          mode="tags"
          value={statuses}
          onChange={setStatuses}
          style={{ width: '100%' }}
          placeholder="Например, Закрыто, Отменено"
        />
      </Space>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Статус не менялся с</Text>
        <DatePicker
          value={olderThan}
          onChange={setOlderThan}
          style={{ width: '100%' }}
          placeholder="Дата отсечки"
        />
      </Space>
      <Space>
        <Button type="primary" onClick={runPreview} loading={previewMut.isPending}>
          Предпросмотр
        </Button>
        <Button
          danger
          type="primary"
          disabled={!preview || preview.total === 0}
          loading={archiveMut.isPending}
          onClick={runArchive}
        >
          Архивировать {preview ? `(${preview.total})` : ''}
        </Button>
      </Space>
      {preview && (
        <>
          <Statistic title="Найдено задач" value={preview.total} suffix={preview.truncated ? '(показано первых 200)' : ''} />
          <List
            size="small"
            bordered
            dataSource={preview.items}
            renderItem={(it) => (
              <List.Item>
                <Tag>{it.project_key}</Tag>
                <Text strong style={{ marginRight: 8 }}>{it.key}</Text>
                <Text ellipsis style={{ flex: 1 }}>{it.summary}</Text>
                <Tag>{it.status}</Tag>
              </List.Item>
            )}
            style={{ maxHeight: 320, overflow: 'auto' }}
          />
        </>
      )}
    </Space>
  );
}
```

- [ ] **Step 2: Подключить в BulkTriageDrawer**

Заменить placeholder для tab `archive`:

```tsx
import BulkArchiveSection from './sections/BulkArchiveSection';
// ...
{ key: 'archive', label: 'Архив по фильтру', children: (
  <BulkArchiveSection
    selectedTeams={selectedTeams}
    scopeProjectKeys={scopeProjectKeys}
    onApplied={onClose}
  />
) },
```

- [ ] **Step 3: Smoke-проверка в браузере**

Run: `cd frontend && npm run dev`
Expected: на `/categories` → «Массовые операции» → вкладка «Архив по фильтру». Preview возвращает счётчик, кнопка «Архивировать» с подтверждением. После apply дерево перерисовывается (cache invalidated).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/categories/sections/BulkArchiveSection.tsx frontend/src/components/categories/BulkTriageDrawer.tsx
git commit -m "feat(categories): секция «Архив по фильтру» в bulk drawer"
```

---

## Task 8: Frontend — секция «Принять подсказки»

**Files:**
- Create: `frontend/src/components/categories/sections/BulkAcceptSuggestionsSection.tsx`
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx`

- [ ] **Step 1: Создать секцию**

```tsx
import { useState } from 'react';
import { App, Button, Checkbox, List, Space, Statistic, Tag, Typography } from 'antd';
import { useBulkPreview, useBulkAcceptSuggestions } from '../../../hooks/useBulkTriage';
import { useCategories } from '../../../hooks/useCategories';
import type { BulkFilter, BulkPreviewItem } from '../../../types/api';

const { Text } = Typography;

type Props = {
  selectedTeams: string[];
  scopeProjectKeys: string[];
  onApplied: () => void;
};

export default function BulkAcceptSuggestionsSection({
  selectedTeams, scopeProjectKeys, onApplied,
}: Props) {
  const { message, modal } = App.useApp();
  const { labels: categoryLabels } = useCategories();
  const [onlyUnverified, setOnlyUnverified] = useState(true);
  const [preview, setPreview] = useState<{ total: number; truncated: boolean; items: BulkPreviewItem[] } | null>(null);
  const previewMut = useBulkPreview();
  const acceptMut = useBulkAcceptSuggestions();

  const buildFilters = (): BulkFilter => ({
    project_keys: scopeProjectKeys.length > 0 ? scopeProjectKeys : undefined,
    teams: selectedTeams.length > 0 ? selectedTeams : undefined,
    only_no_assigned: true,
    only_unverified: onlyUnverified,
  });

  const runPreview = async () => {
    const res = await previewMut.mutateAsync({ filters: buildFilters(), limit: 200 });
    setPreview(res);
  };

  const withSuggestion = preview?.items.filter(i => !!i.category) ?? [];

  const runAccept = () => {
    if (!preview) return;
    modal.confirm({
      title: `Принять ${withSuggestion.length} подсказок?`,
      content: 'Системная подсказка станет назначенной категорией и пометится подтверждённой. Задачи без подсказки пропустятся.',
      okText: 'Принять',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await acceptMut.mutateAsync({ filters: buildFilters() });
        message.success(`Принято: ${res.applied}, пропущено без подсказки: ${res.skipped_no_suggestion}`);
        setPreview(null);
        onApplied();
      },
    });
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Применяет подсказки резолвера (правила и предки) к задачам без
        собственной категории. Используется на старте, чтобы не разбирать
        вручную задачи, которые система уже классифицировала автоматически.
      </Text>
      <Checkbox checked={onlyUnverified} onChange={(e) => setOnlyUnverified(e.target.checked)}>
        Только непроверенные («К разбору»)
      </Checkbox>
      <Space>
        <Button type="primary" onClick={runPreview} loading={previewMut.isPending}>
          Предпросмотр
        </Button>
        <Button
          type="primary"
          disabled={!preview || withSuggestion.length === 0}
          loading={acceptMut.isPending}
          onClick={runAccept}
        >
          Принять ({withSuggestion.length})
        </Button>
      </Space>
      {preview && (
        <>
          <Space size={32}>
            <Statistic title="Кандидатов всего" value={preview.total} />
            <Statistic title="С подсказкой" value={withSuggestion.length} />
            <Statistic title="Без подсказки" value={preview.items.length - withSuggestion.length} />
          </Space>
          <List
            size="small"
            bordered
            dataSource={preview.items}
            renderItem={(it) => (
              <List.Item>
                <Tag>{it.project_key}</Tag>
                <Text strong style={{ marginRight: 8 }}>{it.key}</Text>
                <Text ellipsis style={{ flex: 1 }}>{it.summary}</Text>
                {it.category
                  ? <Tag color="cyan">{categoryLabels[it.category] || it.category}</Tag>
                  : <Tag>нет подсказки</Tag>}
              </List.Item>
            )}
            style={{ maxHeight: 320, overflow: 'auto' }}
          />
        </>
      )}
    </Space>
  );
}
```

- [ ] **Step 2: Подключить в BulkTriageDrawer**

Заменить placeholder для tab `accept`:

```tsx
import BulkAcceptSuggestionsSection from './sections/BulkAcceptSuggestionsSection';
// ...
{ key: 'accept', label: 'Принять подсказки', children: (
  <BulkAcceptSuggestionsSection
    selectedTeams={selectedTeams}
    scopeProjectKeys={scopeProjectKeys}
    onApplied={onClose}
  />
) },
```

- [ ] **Step 3: Smoke-проверка**

Run: dev server, открыть Drawer → «Принять подсказки» → Preview → видно total + with-suggestion + список. Apply → счётчик в стеке падает, дерево обновляется.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/categories/sections/BulkAcceptSuggestionsSection.tsx frontend/src/components/categories/BulkTriageDrawer.tsx
git commit -m "feat(categories): секция «Принять подсказки»"
```

---

## Task 9: Frontend — секция «Каскад от эпика»

**Files:**
- Create: `frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx`
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx`

- [ ] **Step 1: Создать секцию**

Эпиков с `assigned_category` берём из уже загруженного `useIssueTree` через render-prop / контекст. Проще — пробросить готовый список из родительского `BulkTriageDrawer`, который, в свою очередь, получает его из `CategoriesEditorPage` (там есть `nodeById` индекс).

Создать секцию:

```tsx
import { useMemo, useState } from 'react';
import { App, Button, List, Space, Tag, Transfer, Typography } from 'antd';
import type { TransferProps } from 'antd/es/transfer';
import { useBulkCascadeInherit } from '../../../hooks/useBulkTriage';
import { useCategories } from '../../../hooks/useCategories';

const { Text } = Typography;

export type EpicCandidate = {
  id: string;
  key: string;
  summary: string;
  assigned_category: string;  // гарантируем non-null до передачи
};

type Props = {
  candidates: EpicCandidate[];
  onApplied: () => void;
};

export default function BulkCascadeInheritSection({ candidates, onApplied }: Props) {
  const { message, modal } = App.useApp();
  const { labels: categoryLabels } = useCategories();
  const [targetKeys, setTargetKeys] = useState<string[]>([]);
  const cascadeMut = useBulkCascadeInherit();

  const dataSource = useMemo(
    () => candidates.map(c => ({
      key: c.id,
      title: `${c.key} — ${c.summary}`,
      description: categoryLabels[c.assigned_category] || c.assigned_category,
    })),
    [candidates, categoryLabels],
  );

  const onChange: TransferProps['onChange'] = (nextTargetKeys) => {
    setTargetKeys(nextTargetKeys.map(String));
  };

  const runCascade = () => {
    if (targetKeys.length === 0) return;
    modal.confirm({
      title: `Протянуть категорию ${targetKeys.length} эпиков на потомков?`,
      content: 'Категория эпика проставится всем его потомкам без своей категории. Ручные решения PM не трогаются.',
      okText: 'Применить',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await cascadeMut.mutateAsync({ ancestor_ids: targetKeys });
        message.success(`Применено к ${res.applied} задачам, пропущено эпиков без категории: ${res.skipped_ancestors}`);
        setTargetKeys([]);
        onApplied();
      },
    });
  };

  if (candidates.length === 0) {
    return (
      <Text type="secondary">
        Нет эпиков с назначенной категорией в текущей выборке команды. Сначала
        присвойте категорию хотя бы одному эпику — затем протяните её на потомков.
      </Text>
    );
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Выберите эпики (или контейнеры) с уже назначенной категорией.
        Категория протянется ко всем потомкам без собственной.
      </Text>
      <Transfer
        dataSource={dataSource}
        titles={['Доступные эпики', 'К применению']}
        targetKeys={targetKeys}
        onChange={onChange}
        render={(item) => `${item.title} [${item.description}]`}
        listStyle={{ width: 280, height: 320 }}
      />
      <Button
        type="primary"
        disabled={targetKeys.length === 0}
        loading={cascadeMut.isPending}
        onClick={runCascade}
      >
        Протянуть ({targetKeys.length})
      </Button>
    </Space>
  );
}
```

- [ ] **Step 2: Собрать список эпиков-кандидатов в `CategoriesEditorPage` и пробросить через Drawer**

В `CategoriesEditorPage.tsx` после блока `nodeById` (около строки 537) добавить:

```typescript
const epicCandidates = useMemo(() => {
  const out: { id: string; key: string; summary: string; assigned_category: string }[] = [];
  const walk = (nodes: IssueTreeNode[]) => {
    for (const n of nodes) {
      if (n.assigned_category && (n.children?.length ?? 0) > 0) {
        out.push({
          id: n.id,
          key: n.key,
          summary: n.summary,
          assigned_category: n.assigned_category,
        });
      }
      if (n.children?.length) walk(n.children);
    }
  };
  walk(issueTree.data ?? []);
  return out;
}, [issueTree.data]);
```

И пробросить пропсом в `BulkTriageDrawer`:

```tsx
<BulkTriageDrawer
  // ...existing props
  epicCandidates={epicCandidates}
/>
```

- [ ] **Step 3: Принять prop в Drawer + подключить третью вкладку**

В `BulkTriageDrawer.tsx`:

```tsx
import BulkCascadeInheritSection, { type EpicCandidate } from './sections/BulkCascadeInheritSection';

type Props = {
  open: boolean;
  onClose: () => void;
  selectedTeams: string[];
  scopeProjectKeys: string[];
  epicCandidates: EpicCandidate[];
};
// ...
{ key: 'cascade', label: 'Каскад от эпика', children: (
  <BulkCascadeInheritSection
    candidates={epicCandidates}
    onApplied={onClose}
  />
) },
```

- [ ] **Step 4: Smoke в браузере**

Run: dev server. Сначала на дереве вручную проставить категорию любому эпику (одним кликом, без сохранения — потом сохранить). Открыть Drawer → «Каскад от эпика» → выбрать эпик → Apply. Проверить, что у потомков без своих категорий проставилась категория эпика.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/categories/sections/BulkCascadeInheritSection.tsx frontend/src/components/categories/BulkTriageDrawer.tsx frontend/src/pages/CategoriesEditorPage.tsx
git commit -m "feat(categories): секция «Каскад от эпика»"
```

---

## Task 10: Финальная проверка + документация

**Files:**
- Modify: `docs/help/categories.md` — добавить секцию о массовых операциях
- Modify: `frontend/CLAUDE.md` — упомянуть `BulkTriageDrawer`

- [ ] **Step 1: Запустить полный backend test suite**

Run: `py -3.10 -m pytest tests/ -v`
Expected: All PASS, без регрессий.

- [ ] **Step 2: Запустить frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 ошибок, build успешный.

- [ ] **Step 3: Browser smoke золотых сценариев**

Сценарии (вручную в браузере):
1. Залогиниться, выбрать команду с >500 задач в стеке.
2. Открыть «Массовые операции».
3. Архив: отфильтровать «Отменено + статус не менялся >365 дн» → preview → apply. Счётчик стека упал.
4. Подсказки: «Только непроверенные» → preview → видно with-suggestion > 0 → apply. Счётчик стека упал ещё.
5. Каскад: вручную проставить категорию одному эпику + Save → открыть Drawer → выбрать эпик → apply. Все потомки без своих категорий получили эту же.

Если что-то не работает — фиксить в этом же таске, не плодить новый.

- [ ] **Step 4: Обновить `docs/help/categories.md`**

Добавить в конец файла секцию:

```markdown
## Массовые операции

Для онбординга нового руководителя проектов с большим количеством задач
(сотни и тысячи) есть кнопка «Массовые операции» в верхней панели:

- **Архив по фильтру** — массово отправить в архив старые задачи с
  завершёнными статусами (например, «Отменено», статус не менялся
  больше года). Предпросмотр перед применением.
- **Принять подсказки** — для задач без собственной категории система
  уже подобрала вариант по правилам и иерархии предков. Эта секция
  принимает все эти подсказки одним действием.
- **Каскад от эпика** — выбранные эпики проталкивают свою категорию
  на всех потомков, у которых нет собственной. Ручные решения не
  затрагиваются — они являются границей каскада.
```

- [ ] **Step 5: Дополнить `frontend/CLAUDE.md` раздел про CategoriesEditorPage**

Найти раздел «## CategoriesEditorPage» и добавить параграф:

```markdown
**Bulk drawer:** кнопка «Массовые операции» в тулбаре открывает
`BulkTriageDrawer` ([`components/categories/BulkTriageDrawer.tsx`]) с
тремя секциями — архив по фильтру, принять подсказки, каскад от эпика.
Бэк: `/issues/bulk/{preview,archive,accept-suggestions,cascade-inherit}`.
Используется на онбординге PM с большим стеком задач.
```

- [ ] **Step 6: Commit + push**

```bash
git add docs/help/categories.md frontend/CLAUDE.md
git commit -m "docs: bulk-операции на странице «Категории задач»"
git push origin main
```

---

## Self-Review Notes

- Все 4 backend endpoint'а закрыты тестами с реальной БД (через `SessionLocal`, не моки) и cleanup в `finally` — соответствует tests/CLAUDE.md.
- `BulkArchiveSection` всегда требует подтверждение (modal.confirm) — массовая архивация необратима, страховка обязательна.
- `cascade-inherit` останавливается на потомках с `assigned_category != NULL` — это и есть граница ручных решений PM, повторяет логику `setPendingCategory` cascade.
- `accept-suggestions` помечает задачи `category_verified=True` — иначе они вернутся в «Стек» при следующем заходе.
- Cache invalidation — единое место в `useBulkTriage.ts`, не дублируется по секциям.
- Все три секции получают одинаковые `selectedTeams + scopeProjectKeys` пропсы — фильтр команды учитывается серверно (через `_apply_filters`), как и в основном `/issues/tree`.
- Не трогается виртуализация Table и lazy children — это Этап 2/3 отдельным планом. Текущий план решает реальную пользовательскую боль PM-онбординга: 6000 задач не разбираются руками вручную в принципе, а не «тормозят».
