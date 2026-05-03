# Cross-Sectional Reactivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После любой мутации в Бэклоге, Сценариях, задачах или окончания синхронизации бэкенд публикует `entity_changed` через SSE → все подключённые браузеры тихо инвалидируют нужные кэши.

**Architecture:** Используем существующий `EventBroadcaster` (singleton, уже инжектируется через `get_event_bus()`). Каждый мутирующий endpoint получает `event_bus: EventBroadcaster = Depends(get_event_bus)` и вызывает `await event_bus.publish({"type": "entity_changed", "entities": [...]})` после `db.commit()`. Фронтенд уже слушает `entity_changed` в `useEventStream` — расширяем `invalidateForEntity()` под новые ключи.

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / React 19 / TanStack Query

---

## File Map

**Изменяются:**
- `frontend/src/api/events.ts` — тип `entity_changed` + новый вариант с `entities[]`
- `frontend/src/hooks/useEventStream.ts` — handler + `invalidateForEntity()` для `backlog`, `planning`, `capacity`, `analytics`
- `app/api/endpoints/planning.py` — 6 endpoints + импорт `get_event_bus`
- `app/api/endpoints/backlog.py` — 4 endpoints + импорт `get_event_bus`
- `app/api/endpoints/issue_config.py` — 1 endpoint (`batch_set_category`) + импорт `get_event_bus`
- `app/services/sync_pipeline.py` — `PipelineOrchestrator.run()` публикует `entity_changed` после `pipeline_done`

**Создаются:**
- `tests/test_api_entity_changed_planning.py` — тесты publish для planning endpoints
- `tests/test_api_entity_changed_backlog.py` — тесты publish для backlog endpoints
- `tests/test_api_entity_changed_issues.py` — тест publish для batch-category
- `tests/test_sync_pipeline_entity_changed.py` — тест entity_changed в pipeline

---

## Task 1: Frontend — обновить тип события entity_changed

**Files:**
- Modify: `frontend/src/api/events.ts`

- [ ] **Step 1: Обновить тип GlobalEvent**

Заменить строку `| { type: 'entity_changed'; entity: string };` на:

```typescript
| { type: 'entity_changed'; entity?: string; entities?: string[] };
```

Файл целиком после правки:

```typescript
import { BASE_URL } from './client';

export type GlobalEvent =
  | { type: 'sync_started'; run_id: string; mode: string }
  | { type: 'stage_start'; stage: string; run_id: string }
  | { type: 'stage_done'; stage: string; run_id: string; counts: Record<string, number> }
  | { type: 'stage_failed'; stage: string; run_id: string; error: string }
  | { type: 'pipeline_done'; run_id: string; status: string }
  | { type: 'entity_changed'; entity?: string; entities?: string[] };

/** URL глобального SSE-потока событий. */
export const EVENTS_STREAM_URL = `${BASE_URL}/events/stream`;
```

- [ ] **Step 2: Проверить TypeScript**

```bash
cd frontend && npm run lint
```

Ожидание: 0 ошибок по `events.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/events.ts
git commit -m "feat(frontend): extend entity_changed type to support entities array"
```

---

## Task 2: Frontend — расширить invalidateForEntity и handler

**Files:**
- Modify: `frontend/src/hooks/useEventStream.ts`

- [ ] **Step 1: Заменить содержимое файла**

```typescript
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { EVENTS_STREAM_URL, type GlobalEvent } from '../api/events';

/**
 * Подключается к SSE-потоку /events/stream и инвалидирует кэши TanStack Query
 * по entity_changed событиям. Подключается один раз при монтировании AppLayout.
 * При потере соединения переподключается через 5 секунд.
 */
export function useEventStream() {
  const qc = useQueryClient();
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      const es = new EventSource(EVENTS_STREAM_URL);
      esRef.current = es;

      es.onmessage = (e) => {
        if (!e.data || !e.data.trim()) return;
        try {
          const event = JSON.parse(e.data) as GlobalEvent;
          handleEvent(event, qc);
        } catch {
          /* ignore malformed */
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!destroyed) {
          retryRef.current = setTimeout(connect, 5000);
        }
      };
    }

    connect();

    return () => {
      destroyed = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [qc]);
}

function handleEvent(event: GlobalEvent, qc: ReturnType<typeof useQueryClient>) {
  switch (event.type) {
    case 'entity_changed': {
      const entities = event.entities ?? (event.entity ? [event.entity] : []);
      entities.forEach((e) => invalidateForEntity(e, qc));
      break;
    }
    case 'pipeline_done':
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
      break;
    case 'stage_done':
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
      break;
    default:
      break;
  }
}

function invalidateForEntity(entity: string, qc: ReturnType<typeof useQueryClient>) {
  switch (entity) {
    case 'issues':
      qc.invalidateQueries({ queryKey: ['issues'] });
      qc.invalidateQueries({ queryKey: ['analytics'] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      break;
    case 'backlog':
      qc.invalidateQueries({ queryKey: ['backlog'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
      break;
    case 'planning':
      qc.invalidateQueries({ queryKey: ['planning'] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      break;
    case 'worklogs':
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['analytics'] });
      break;
    case 'capacity':
      qc.invalidateQueries({ queryKey: ['capacity'] });
      break;
    case 'analytics':
      qc.invalidateQueries({ queryKey: ['analytics'] });
      break;
    case 'employees':
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      break;
    case 'projects':
      qc.invalidateQueries({ queryKey: ['scope', 'projects'] });
      break;
    default:
      break;
  }
}
```

- [ ] **Step 2: Проверить TypeScript**

```bash
cd frontend && npm run lint
```

Ожидание: 0 ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useEventStream.ts
git commit -m "feat(frontend): extend invalidateForEntity for backlog/planning/capacity/analytics"
```

---

## Task 3: Тесты для planning endpoints (сначала — упадут)

**Files:**
- Create: `tests/test_api_entity_changed_planning.py`

- [ ] **Step 1: Создать файл тестов**

```python
"""Проверяем, что мутирующие endpoints планирования публикуют entity_changed."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


# ── seed helpers ──────────────────────────────────────────────────────────────

def _seed_backlog_item(db):
    from app.models import BacklogItem, Category, Issue, Project
    cat = Category(id="cat-rfa", code="initiatives_rfa", label="RFA", color="#000",
                   sort_order=1, is_system=True)
    proj = Project(id="proj-1", jira_project_id="p1", key="P", name="P", is_active=True)
    issue = Issue(id="iss-1", jira_issue_id="i1", key="P-1", summary="S",
                  issue_type="Epic", status="Open", project_id="proj-1",
                  category="initiatives_rfa")
    item = BacklogItem(id="bi-1", title="Item 1", issue_id="iss-1",
                       estimate_hours=10, status="active")
    db.add_all([cat, proj, issue, item])
    db.commit()
    return item


def _seed_scenario_with_allocation(db, item_id):
    from app.models import PlanningScenario, ScenarioAllocation
    sc = PlanningScenario(id="sc-1", name="Q1", year=2026, quarter="Q1", status="draft")
    db.add(sc)
    db.flush()
    alloc = ScenarioAllocation(id="al-1", scenario_id="sc-1",
                                backlog_item_id=item_id, included_flag=False,
                                planned_hours=0, sort_order=1.0)
    db.add(alloc)
    db.commit()
    return sc, alloc


# ── tests ─────────────────────────────────────────────────────────────────────

def test_create_scenario_publishes_planning(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post("/api/v1/planning/scenarios",
                        json={"name": "Q1", "year": 2026, "quarter": 1})
        assert r.status_code == 201, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning"]}
    )


def test_patch_allocation_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(
            f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}",
            json={"included": True},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_patch_allocation_assignee_publishes_planning(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(
            f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}/assignee",
            json={"assignee_employee_id": None},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning"]}
    )


def test_approve_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve", json={})
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_revert_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    # Approve first so we can revert
    db_session.get(sc.__class__, sc.id).status = "approved"
    db_session.commit()
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/planning/scenarios/{sc.id}/revert-to-draft")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_delete_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.delete(f"/api/v1/planning/scenarios/{sc.id}")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )
```

- [ ] **Step 2: Запустить — убедиться что тесты падают**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_planning.py -v
```

Ожидание: все 6 тестов FAILED (AssertionError: `publish` not called).

---

## Task 4: Инструментировать planning.py

**Files:**
- Modify: `app/api/endpoints/planning.py`

- [ ] **Step 1: Добавить импорт event_bus в planning.py**

После строки `from app.services.resource_base_service import ResourceBaseService` добавить:

```python
from app.services.event_bus import EventBroadcaster, get_event_bus
```

- [ ] **Step 2: Обновить create_scenario**

Сигнатура (строка ~348):
```python
async def create_scenario(
    data: ScenarioCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~406), перед `db.refresh(scenario)`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    db.refresh(scenario)
```

- [ ] **Step 3: Обновить approve_scenario**

Сигнатура (строка ~412):
```python
async def approve_scenario(
    scenario_id: str,
    body: ApproveBody = ApproveBody(),
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~535), перед `db.refresh(scenario)`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    db.refresh(scenario)
```

- [ ] **Step 4: Обновить revert_scenario**

Сигнатура (строка ~543):
```python
async def revert_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~552), перед `db.refresh(scenario)`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    db.refresh(scenario)
```

- [ ] **Step 5: Обновить patch_allocation**

Сигнатура (строка ~777):
```python
async def patch_allocation(
    scenario_id: str,
    alloc_id: str,
    data: AllocationPatch,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~825), перед `# Re-load with issue join`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    # Re-load with issue join for response.
```

- [ ] **Step 6: Обновить patch_allocation_assignee**

Сигнатура (строка ~840):
```python
async def patch_allocation_assignee(
    scenario_id: str,
    alloc_id: str,
    data: AllocationAssigneePatch,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~878), перед `# Reload with relationships after commit`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    # Reload with relationships after commit.
```

- [ ] **Step 7: Обновить delete_scenario**

Сигнатура (строка ~1056):
```python
async def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~1069):
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    return {"status": "deleted", "id": scenario_id}
```

- [ ] **Step 8: Прогнать тесты**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_planning.py -v
```

Ожидание: все 6 PASSED.

- [ ] **Step 9: Убедиться что существующие тесты зелёные**

```bash
py -3.10 -m pytest tests/ -v --ignore=tests/test_api_entity_changed_backlog.py --ignore=tests/test_api_entity_changed_issues.py --ignore=tests/test_sync_pipeline_entity_changed.py -x
```

Ожидание: ≥498 тестов прошли (pre-existing failures не считаются новыми).

- [ ] **Step 10: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_entity_changed_planning.py
git commit -m "feat(planning): publish entity_changed after all mutating operations"
```

---

## Task 5: Тесты для backlog endpoints (сначала — упадут)

**Files:**
- Create: `tests/test_api_entity_changed_backlog.py`

- [ ] **Step 1: Создать файл тестов**

```python
"""Проверяем, что мутирующие backlog endpoints публикуют entity_changed."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed_category(db):
    from app.models import Category
    cat = db.query(Category).filter_by(code="initiatives_rfa").first()
    if not cat:
        cat = Category(id="cat-rfa2", code="initiatives_rfa", label="RFA",
                       color="#000", sort_order=1, is_system=True)
        db.add(cat)
        db.commit()
    return cat


def _seed_item(db):
    _seed_category(db)
    from app.models import BacklogItem
    item = BacklogItem(id="bi-x", title="Test", estimate_hours=5, status="active")
    db.add(item)
    db.commit()
    return item


def test_create_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    _seed_category(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post("/api/v1/backlog", json={"title": "New item"})
        assert r.status_code == 201, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_update_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(f"/api/v1/backlog/{item.id}", json={"title": "Updated"})
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_archive_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/backlog/{item.id}/archive")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_restore_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    item.archived_at = __import__('datetime').datetime.utcnow()
    db_session.commit()
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )
```

- [ ] **Step 2: Запустить — убедиться что тесты падают**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_backlog.py -v
```

Ожидание: все 4 теста FAILED.

---

## Task 6: Инструментировать backlog.py

**Files:**
- Modify: `app/api/endpoints/backlog.py`

- [ ] **Step 1: Добавить импорт event_bus в backlog.py**

После строки `from app.services.sync_service import SyncService` добавить:

```python
from app.services.event_bus import EventBroadcaster, get_event_bus
```

- [ ] **Step 2: Обновить create_backlog_item**

Строка ~318. Добавить параметр:
```python
async def create_backlog_item(
    data: BacklogItemCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~326), перед `db.refresh(item)`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
    db.refresh(item)
```

- [ ] **Step 3: Обновить update_backlog_item**

Строка ~562. Добавить параметр:
```python
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~584), перед `db.refresh(item)`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
    db.refresh(item)
```

- [ ] **Step 4: Обновить archive_backlog_item**

Строка ~741. Добавить параметр:
```python
async def archive_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~784), перед `db.refresh(item)`:
```python
        db.commit()
        await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
        db.refresh(item)
```

- [ ] **Step 5: Обновить restore_backlog_item**

Строка ~790. Добавить параметр:
```python
async def restore_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~819), перед `db.refresh(item)`:
```python
        db.commit()
        await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
        db.refresh(item)
```

- [ ] **Step 6: Прогнать тесты**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_backlog.py -v
```

Ожидание: все 4 PASSED.

- [ ] **Step 7: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_entity_changed_backlog.py
git commit -m "feat(backlog): publish entity_changed after all mutating operations"
```

---

## Task 7: Тесты и инструментирование issue_config.py

**Files:**
- Create: `tests/test_api_entity_changed_issues.py`
- Modify: `app/api/endpoints/issue_config.py`

- [ ] **Step 1: Создать файл тестов**

```python
"""Проверяем, что batch-category публикует entity_changed."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed_issue(db):
    from app.models import Category, Issue, Project
    cat = Category(id="cat-dev", code="development", label="Dev",
                   color="#000", sort_order=1, is_system=True)
    proj = Project(id="p-ic", jira_project_id="p-ic-j", key="IC",
                   name="IC", is_active=True)
    issue = Issue(id="i-ic", jira_issue_id="i-ic-j", key="IC-1",
                  summary="S", issue_type="Task", status="Open",
                  project_id="p-ic", category="development")
    db.add_all([cat, proj, issue])
    db.commit()
    return issue


def test_batch_category_publishes_issues_and_backlog(db_session):
    mock_bus = AsyncMock()
    issue = _seed_issue(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.put(
            "/api/v1/issues/batch-category",
            json={"issue_ids": [issue.id], "category_code": "development"},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["issues", "backlog"]}
    )
```

- [ ] **Step 2: Запустить — убедиться что тест падает**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_issues.py -v
```

Ожидание: FAILED.

- [ ] **Step 3: Добавить импорт в issue_config.py**

Найти блок импортов (начало файла, после `from app.services.category_resolver import CategoryResolver`).

Добавить:
```python
from app.services.event_bus import EventBroadcaster, get_event_bus
```

- [ ] **Step 4: Обновить batch_set_category**

Строка ~321. Добавить параметр:
```python
async def batch_set_category(
    body: BatchCategoryRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
```

После `db.commit()` (строка ~356), перед `return`:
```python
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return {
```

- [ ] **Step 5: Прогнать тест**

```bash
py -3.10 -m pytest tests/test_api_entity_changed_issues.py -v
```

Ожидание: PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_api_entity_changed_issues.py
git commit -m "feat(issues): publish entity_changed after batch-category"
```

---

## Task 8: Sync pipeline — entity_changed при pipeline_done

**Files:**
- Create: `tests/test_sync_pipeline_entity_changed.py`
- Modify: `app/services/sync_pipeline.py`

- [ ] **Step 1: Создать тест**

```python
"""PipelineOrchestrator публикует entity_changed после pipeline_done."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import PipelineOrchestrator, Stage


class _DummyStage(Stage):
    name = "test"
    critical = True

    def __init__(self, inv):
        self._inv = inv

    async def run(self, ctx):
        return {"count": 1}

    def invalidates(self):
        return self._inv


@pytest.mark.asyncio
async def test_pipeline_publishes_entity_changed_on_success():
    bus = AsyncMock()
    db = MagicMock()
    stages = [
        _DummyStage(["issues", "tree", "backlog"]),
        _DummyStage(["worklogs", "capacity"]),
    ]
    orch = PipelineOrchestrator(stages=stages, db=db, bus=bus)
    result = await orch.run(mode="full", trigger="manual", run_id="r1")

    assert result["status"] == "ok"

    # Найти вызов entity_changed
    entity_changed_calls = [
        call for call in bus.publish.call_args_list
        if call.args[0].get("type") == "entity_changed"
    ]
    assert len(entity_changed_calls) == 1

    published_entities = set(entity_changed_calls[0].args[0]["entities"])
    # "tree" маппится к "issues"
    assert "issues" in published_entities
    assert "backlog" in published_entities
    assert "worklogs" in published_entities
    assert "capacity" in published_entities


@pytest.mark.asyncio
async def test_pipeline_publishes_entity_changed_on_partial():
    bus = AsyncMock()
    db = MagicMock()

    class _FailStage(Stage):
        name = "fail"
        critical = False

        async def run(self, ctx):
            raise RuntimeError("oops")

        def invalidates(self):
            return []

    stages = [_DummyStage(["issues"]), _FailStage()]
    orch = PipelineOrchestrator(stages=stages, db=db, bus=bus)
    result = await orch.run(mode="full", trigger="manual", run_id="r2")

    assert result["status"] == "partial"
    entity_changed_calls = [
        call for call in bus.publish.call_args_list
        if call.args[0].get("type") == "entity_changed"
    ]
    assert len(entity_changed_calls) == 1
    assert "issues" in entity_changed_calls[0].args[0]["entities"]
```

- [ ] **Step 2: Запустить — убедиться что тест падает**

```bash
py -3.10 -m pytest tests/test_sync_pipeline_entity_changed.py -v
```

Ожидание: FAILED.

- [ ] **Step 3: Обновить PipelineOrchestrator.run()**

В `app/services/sync_pipeline.py` найти метод `run()`.

Перед строкой `status = "partial" if had_non_critical_failure else "ok"` добавить:

```python
        # Маппинг stage.invalidates() значений → entity-ключи для frontend
        _STAGE_INVALIDATES_MAP = {
            "issues": "issues",
            "tree": "issues",
            "backlog": "backlog",
            "planning": "planning",
            "worklogs": "worklogs",
            "capacity": "capacity",
            "analytics": "analytics",
            "projects": "projects",
            "production-calendar": "capacity",
            "employees": "employees",
        }
        all_entities = list({
            _STAGE_INVALIDATES_MAP[key]
            for stage in self.stages
            for key in stage.invalidates()
            if key in _STAGE_INVALIDATES_MAP
        })
```

Заменить последний блок `pipeline_done` (строка ~101-103):

```python
        status = "partial" if had_non_critical_failure else "ok"
        await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": status})
        if all_entities:
            await self.bus.publish({"type": "entity_changed", "entities": all_entities})
        return {"status": status, "stages": stages_report}
```

Важно: `_STAGE_INVALIDATES_MAP` объявить как локальную переменную внутри `run()` непосредственно перед использованием (как показано выше), либо вынести на уровень модуля. Для читаемости — на уровне модуля, после `logger = logging.getLogger(__name__)`:

```python
_STAGE_INVALIDATES_MAP: dict[str, str] = {
    "issues": "issues",
    "tree": "issues",
    "backlog": "backlog",
    "planning": "planning",
    "worklogs": "worklogs",
    "capacity": "capacity",
    "analytics": "analytics",
    "projects": "projects",
    "production-calendar": "capacity",
    "employees": "employees",
}
```

И в `run()` перед `status = ...`:

```python
        all_entities = list({
            _STAGE_INVALIDATES_MAP[key]
            for stage in self.stages
            for key in stage.invalidates()
            if key in _STAGE_INVALIDATES_MAP
        })
        status = "partial" if had_non_critical_failure else "ok"
        await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": status})
        if all_entities:
            await self.bus.publish({"type": "entity_changed", "entities": all_entities})
        return {"status": status, "stages": stages_report}
```

- [ ] **Step 4: Прогнать тесты**

```bash
py -3.10 -m pytest tests/test_sync_pipeline_entity_changed.py -v
```

Ожидание: оба PASSED.

- [ ] **Step 5: Полный прогон тестов**

```bash
py -3.10 -m pytest tests/ -v -x
```

Ожидание: ≥498 тестов PASSED (pre-existing failures остаются).

- [ ] **Step 6: Frontend build**

```bash
cd frontend && npm run build
```

Ожидание: Build succeeded без ошибок.

- [ ] **Step 7: Commit и push**

```bash
git add app/services/sync_pipeline.py tests/test_sync_pipeline_entity_changed.py
git commit -m "feat(sync): publish entity_changed with affected entities after pipeline_done"
git push origin main
```

---

## Self-Review Checklist

- [x] **create_scenario** → `["planning"]` ✓
- [x] **approve_scenario** → `["planning", "backlog"]` ✓ (approved сценарии влияют на in_work в Бэклоге)
- [x] **revert_scenario** → `["planning", "backlog"]` ✓
- [x] **patch_allocation** → `["planning", "backlog"]` ✓ (included_flag меняет in_work)
- [x] **patch_allocation_assignee** → `["planning"]` ✓ (assignee не влияет на Бэклог)
- [x] **delete_scenario** → `["planning", "backlog"]` ✓
- [x] **create/update/archive/restore backlog** → `["backlog"]` ✓
- [x] **batch_set_category** → `["issues", "backlog"]` ✓ (category change может создать/архивировать BacklogItem через BacklogService.sync_from_issue)
- [x] **pipeline_done** → `entity_changed` из всех `stage.invalidates()` ✓
- [x] Frontend: `entity_changed` handler поддерживает массив `entities` и одиночный `entity` ✓
- [x] Frontend: `invalidateForEntity` добавлены `backlog`, `planning`, `capacity`, `analytics` ✓
- [x] Публикация только после `db.commit()` — исключения до commit не публикуют событие ✓
- [x] Нет лишних зависимостей (event_bus inject через FastAPI Depends) ✓
