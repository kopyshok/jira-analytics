# Target Tasks Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the BacklogItem system to track both `initiatives_rfa` and `quarterly_tasks` categories, add a "quarterly" view, restructure the backlog page into three tabs (Активные / Бэклог / Архив), rename the nav section to "Целевые задачи", and show a source badge in the scenario allocation table.

**Architecture:** `BacklogService.sync_from_issue` checks against a set of tracked categories instead of a single constant; the list endpoint gains a `quarterly` view that filters by `quarterly_tasks` category; the `active` view is updated to exclude quarterly items; `AllocationResponse` gains a `source_category` field populated from the linked issue. Frontend gains a third tab and a nav rename with no data-flow changes.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, SQLite, React 19, TypeScript 6, Ant Design 6, TanStack Query.

---

### Task 1: BacklogService — поддержка `quarterly_tasks`

**Files:**
- Modify: `app/services/backlog_service.py`
- Test: `tests/test_backlog_sync.py`

- [ ] **Step 1: Написать падающий тест — quarterly_tasks создаёт BacklogItem**

  Добавить в конец `tests/test_backlog_sync.py`:

  ```python
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
  ```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

  ```
  py -3.10 -m pytest tests/test_backlog_sync.py::test_sync_creates_backlog_item_for_quarterly_tasks -v
  ```

  Ожидаемый результат: FAIL (`assert item is not None` — item будет None)

- [ ] **Step 3: Добавить константы и обновить `sync_from_issue`**

  В `app/services/backlog_service.py` заменить строку 26 и условие на строке 53:

  ```python
  BACKLOG_CATEGORY = "initiatives_rfa"
  QUARTERLY_TASKS_CATEGORY = "quarterly_tasks"
  TRACKED_CATEGORIES = {BACKLOG_CATEGORY, QUARTERLY_TASKS_CATEGORY}
  ```

  Строку 53 изменить:
  ```python
  # было:
  if issue.category == BACKLOG_CATEGORY:
  # стало:
  if issue.category in TRACKED_CATEGORIES:
  ```

- [ ] **Step 4: Запустить оба теста**

  ```
  py -3.10 -m pytest tests/test_backlog_sync.py::test_sync_creates_backlog_item_for_quarterly_tasks tests/test_backlog_sync.py::test_sync_archives_when_category_leaves_tracked_set -v
  ```

  Ожидаемый результат: оба PASS

- [ ] **Step 5: Прогнать весь test_backlog_sync.py — убедиться, что ничего не сломано**

  ```
  py -3.10 -m pytest tests/test_backlog_sync.py -v
  ```

  Ожидаемый результат: все тесты PASS

- [ ] **Step 6: Commit**

  ```
  git add app/services/backlog_service.py tests/test_backlog_sync.py
  git commit -m "feat(backlog): track quarterly_tasks alongside initiatives_rfa"
  ```

---

### Task 2: `refresh-from-jira` — расширить кандидатов

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Написать падающий тест**

  Найти блок вспомогательных функций в `tests/test_api_backlog_link.py` (около строки 30) и добавить новый тест после `test_refresh_from_jira_pulls_all_matching`:

  ```python
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
  ```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py::test_refresh_from_jira_picks_up_quarterly_tasks -v
  ```

  Ожидаемый результат: FAIL (`body["created"] == 0`)

- [ ] **Step 3: Обновить импорт и candidate_keys в `backlog.py`**

  В `app/api/endpoints/backlog.py` найти строку с импортом (≈ строка 20):
  ```python
  # было:
  from app.services.backlog_service import BACKLOG_CATEGORY, BacklogService
  # стало:
  from app.services.backlog_service import (
      BACKLOG_CATEGORY,
      QUARTERLY_TASKS_CATEGORY,
      BacklogService,
  )
  ```

  Заменить блок candidate_keys (строки 313–322):
  ```python
  candidate_keys = [
      key for (key,) in db.query(Issue.key)
      .filter(
          or_(
              Issue.assigned_category == BACKLOG_CATEGORY,
              Issue.category == BACKLOG_CATEGORY,
              Issue.assigned_category == QUARTERLY_TASKS_CATEGORY,
              Issue.category == QUARTERLY_TASKS_CATEGORY,
          )
      )
      .all()
  ]
  ```

- [ ] **Step 4: Запустить тест**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py::test_refresh_from_jira_picks_up_quarterly_tasks -v
  ```

  Ожидаемый результат: PASS

- [ ] **Step 5: Прогнать весь test_api_backlog_link.py**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py -v
  ```

  Ожидаемый результат: все PASS

- [ ] **Step 6: Commit**

  ```
  git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
  git commit -m "feat(backlog): refresh-from-jira discovers quarterly_tasks candidates"
  ```

---

### Task 3: Список бэклога — view `quarterly` и обновление `active`

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Test: `tests/test_api_backlog_link.py`

- [ ] **Step 1: Написать два падающих теста**

  Добавить в конец `tests/test_api_backlog_link.py`:

  ```python
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
  ```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py::test_backlog_list_quarterly_view_returns_quarterly_items tests/test_api_backlog_link.py::test_backlog_list_active_view_includes_manual_items -v
  ```

  Ожидаемый результат: FAIL (422 для `view=quarterly` — паттерн не допускает)

- [ ] **Step 3: Обновить list_backlog_items в `backlog.py`**

  Строка 210 — расширить паттерн:
  ```python
  # было:
  view: str = Query("active", pattern="^(active|archived|in_work)$"),
  # стало:
  view: str = Query("active", pattern="^(active|archived|in_work|quarterly)$"),
  ```

  Заменить блок `if view == "active":` (строки 227–231):
  ```python
  if view == "active":
      quarterly_filter = or_(
          Issue.assigned_category == QUARTERLY_TASKS_CATEGORY,
          Issue.category == QUARTERLY_TASKS_CATEGORY,
      )
      query = query.filter(
          BacklogItem.archived_at.is_(None),
          func.coalesce(Issue.status_category, "") != "done",
          or_(
              BacklogItem.issue_id.is_(None),  # ручные записи всегда в бэклоге
              ~quarterly_filter,
          ),
      )
  ```

  После блока `elif view == "in_work":` добавить:
  ```python
  elif view == "quarterly":
      query = query.filter(
          BacklogItem.archived_at.is_(None),
          or_(
              Issue.assigned_category == QUARTERLY_TASKS_CATEGORY,
              Issue.category == QUARTERLY_TASKS_CATEGORY,
          ),
      )
  ```

- [ ] **Step 4: Запустить тесты**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py::test_backlog_list_quarterly_view_returns_quarterly_items tests/test_api_backlog_link.py::test_backlog_list_active_view_includes_manual_items -v
  ```

  Ожидаемый результат: оба PASS

- [ ] **Step 5: Прогнать все тесты бэклога**

  ```
  py -3.10 -m pytest tests/test_api_backlog_link.py tests/test_backlog_sync.py -v
  ```

  Ожидаемый результат: все PASS

- [ ] **Step 6: Commit**

  ```
  git add app/api/endpoints/backlog.py tests/test_api_backlog_link.py
  git commit -m "feat(backlog): add quarterly view, exclude quarterly from active view"
  ```

---

### Task 4: `AllocationResponse` — поле `source_category`

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Test: `tests/test_api_planning_archive_guard.py`

- [ ] **Step 1: Написать падающий тест**

  В `tests/test_api_planning_archive_guard.py`, в конец файла добавить:

  ```python
  def test_allocation_response_has_source_category(db_session):
      from app.models import BacklogItem, Issue, Project

      proj = Project(
          id="p-sc",
          jira_project_id="p-sc-jira",
          key="ITL",
          name="ITL",
          is_active=True,
      )
      issue = Issue(
          id="i-sc",
          jira_issue_id="i-sc-jira",
          key="ITL-SC1",
          summary="Quarterly",
          issue_type="ITL",
          status="Open",
          project_id=proj.id,
          category="quarterly_tasks",
      )
      item = BacklogItem(id="bi-sc", title="Quarterly", issue_id=issue.id)
      db_session.add_all([proj, issue, item])
      db_session.commit()

      _override(db_session)
      try:
          client = TestClient(app)
          r = client.post(
              "/api/v1/planning/scenarios",
              json={"name": "Test", "year": 2026, "quarter": 2},
          )
          assert r.status_code == 201, r.text
          scenario_id = r.json()["id"]

          r2 = client.get(f"/api/v1/planning/scenarios/{scenario_id}/allocations")
          assert r2.status_code == 200, r2.text
          allocs = r2.json()
          qt_alloc = next(a for a in allocs if a["backlog_item_id"] == "bi-sc")
          assert qt_alloc["source_category"] == "quarterly_tasks"
      finally:
          app.dependency_overrides.clear()
  ```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

  ```
  py -3.10 -m pytest tests/test_api_planning_archive_guard.py::test_allocation_response_has_source_category -v
  ```

  Ожидаемый результат: FAIL (`KeyError: 'source_category'` или validation error)

- [ ] **Step 3: Добавить поле в `AllocationResponse` и `_to_allocation_resp`**

  В `app/api/endpoints/planning.py`, в класс `AllocationResponse` (≈ строка 165) добавить поле после `cost_type`:

  ```python
  source_category: Optional[str] = None  # 'initiatives_rfa' | 'quarterly_tasks'
  ```

  В функции `_to_allocation_resp` (≈ строка 257), после `cost_type=item.cost_type,` добавить:

  ```python
  source_category=item.issue.category if item.issue else None,
  ```

- [ ] **Step 4: Запустить тест**

  ```
  py -3.10 -m pytest tests/test_api_planning_archive_guard.py::test_allocation_response_has_source_category -v
  ```

  Ожидаемый результат: PASS

- [ ] **Step 5: Прогнать все planning тесты**

  ```
  py -3.10 -m pytest tests/test_api_planning_archive_guard.py tests/test_api_planning_assignee.py tests/test_api_planning_resource.py tests/test_api_planning_summary.py tests/test_api_scenarios_team_rules.py tests/test_planning_service.py -v
  ```

  Ожидаемый результат: все PASS

- [ ] **Step 6: Commit**

  ```
  git add app/api/endpoints/planning.py tests/test_api_planning_archive_guard.py
  git commit -m "feat(planning): add source_category to allocation response"
  ```

---

### Task 5: Frontend — тип `BacklogView`, три вкладки в `BacklogPage`

**Files:**
- Modify: `frontend/src/types/api.ts` (строки 385, 488–509)
- Modify: `frontend/src/pages/BacklogPage.tsx`

- [ ] **Step 1: Обновить `BacklogView` и `AllocationResponse` в `api.ts`**

  Строка 385:
  ```typescript
  // было:
  export type BacklogView = 'active' | 'archived';
  // стало:
  export type BacklogView = 'active' | 'archived' | 'quarterly';
  ```

  В `AllocationResponse` (≈ строка 508), после `cost_type: string | null;`:
  ```typescript
  source_category: string | null;
  ```

- [ ] **Step 2: Добавить quarterly-запрос в `BacklogPage.tsx`**

  Найти строки с `const active = useBacklogItems('active');` и `const archived = useBacklogItems('archived');` и добавить после них:

  ```typescript
  const quarterly = useBacklogItems('quarterly');
  const quarterlyRows = sortByPriority(quarterly.data);
  ```

- [ ] **Step 3: Добавить `quarterlyTable` перед `activeTable` (≈ строка 499)**

  В `BacklogPage.tsx` добавить перед `const activeTable = (`:

  ```tsx
  const quarterlyTable = (
    <Table<BacklogItemResponse>
      dataSource={quarterlyRows}
      rowKey="id"
      loading={quarterly.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1400 }}
      columns={baseColumns(false)}
    />
  );
  ```

- [ ] **Step 4: Добавить третью вкладку и переименовать вторую + поправить PageHeader**

  Заменить блок `items={[` в `<Tabs>` (≈ строка 579):

  ```typescript
  items={[
    {
      key: 'quarterly',
      label: `Активные (${quarterlyRows?.length ?? 0})`,
      children: quarterlyTable,
    },
    {
      key: 'active',
      label: `Бэклог (${activeRows?.length ?? 0})`,
      children: activeTable,
    },
    {
      key: 'archived',
      label: `Архив (${archivedRows?.length ?? 0})`,
      children: archivedTable,
    },
  ]}
  ```

  В `<PageHeader>` (≈ строка 541) поменять заголовок:
  ```tsx
  // было:
  title="Бэклог инициатив"
  subtitle='Активные кандидаты — в основной вкладке; задачи в работе и архив — в отдельных'
  // стало:
  title="Целевые задачи"
  subtitle='Активные задачи текущего квартала и бэклог инициатив'
  ```

- [ ] **Step 5: Убедиться, что TypeScript не ругается**

  ```
  cd frontend && npm run build 2>&1 | tail -20
  ```

  Ожидаемый результат: сборка без TypeScript ошибок.

- [ ] **Step 6: Commit**

  ```
  git add frontend/src/types/api.ts frontend/src/pages/BacklogPage.tsx
  git commit -m "feat(frontend): add quarterly tab to target tasks page"
  ```

---

### Task 6: Frontend — переименование раздела + тег «Источник» в сценарии

**Files:**
- Modify: `frontend/src/components/Layout/SideMenu.tsx` (строка 30)
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Переименовать «Бэклог» → «Целевые задачи» в сайдбаре**

  В `frontend/src/components/Layout/SideMenu.tsx`, строка 30:
  ```typescript
  // было:
  { key: '/backlog', icon: <UnorderedListOutlined />, label: 'Бэклог' },
  // стало:
  { key: '/backlog', icon: <UnorderedListOutlined />, label: 'Целевые задачи' },
  ```

- [ ] **Step 2: Добавить тег «Источник» в ячейку с названием задачи в `PlanningPage.tsx`**

  В `PlanningPage.tsx`, найти блок с `{a.jira_key && (` (≈ строка 444). Непосредственно перед ним (или после, внутри той же `<div>`) добавить:

  ```tsx
  {a.source_category === 'quarterly_tasks' && (
    <span
      style={{
        display: 'inline-block',
        marginTop: 2,
        fontSize: 11,
        padding: '1px 6px',
        borderRadius: 3,
        background: 'rgba(29,158,117,0.15)',
        color: '#1D9E75',
      }}
    >
      В работе
    </span>
  )}
  ```

- [ ] **Step 3: Убедиться, что TypeScript не ругается**

  ```
  cd frontend && npm run build 2>&1 | tail -20
  ```

  Ожидаемый результат: сборка без ошибок.

- [ ] **Step 4: Прогнать все backend-тесты**

  ```
  py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -30
  ```

  Ожидаемый результат: все PASS (или только pre-existing failures).

- [ ] **Step 5: Final commit + push**

  ```
  git add frontend/src/components/Layout/SideMenu.tsx frontend/src/pages/PlanningPage.tsx
  git commit -m "feat(frontend): rename section to Целевые задачи, add source badge in scenario"
  git push
  ```
