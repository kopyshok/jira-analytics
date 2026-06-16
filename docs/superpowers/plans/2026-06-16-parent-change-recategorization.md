# Переподтверждение категории при переезде задачи — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Когда у подтверждённой задачи сменился родитель и при этом сменилась категория, наследуемая от родителя, вернуть задачу в стопку «на подтверждение» с пометкой «сменился родитель» и историей переезда.

**Architecture:** Три новых признака на задаче (`parent_changed`, `category_context`, `category_context_key`). Обнаружение — в `MappingService.recalculate_issues` (бежит после каждого синка): сравниваем текущую «категорию от родителя» с зафиксированной точкой отсчёта. «Категория от родителя» = `CategoryResolver.resolve_for_issue(parent)` (переиспользуем резолвер на родителе, игнорируя свою категорию). Подтверждение в любой точке сбрасывает пометку и сдвигает точку отсчёта на текущую.

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic (batch) / pytest. Frontend: React 19 / TS / AntD 6 (`CategoriesEditorPage.tsx`).

> Windows: тесты гонять `py -3.10 -m pytest ...`. Бэкенд после правок перезапускать (kill PID на :8000).

---

## File Structure

- `app/models/issue.py` — 3 новых колонки.
- `alembic/versions/<hash>_add_parent_change_tracking.py` — миграция (autogenerate).
- `app/services/category_resolver.py` — метод `resolve_inherited_for_issue` + функция `reset_parent_context`.
- `app/services/mapping_service.py` — блок обнаружения в `recalculate_issues`.
- `app/api/endpoints/issue_config.py` — поля в схемах узлов + сериализация + сброс в точках подтверждения.
- `app/api/endpoints/issue_bulk.py` — фильтр `only_parent_changed` + поле в превью + сброс в bulk-подтверждениях.
- `frontend/src/pages/CategoriesEditorPage.tsx` (+ типы) — значок, подсказка, фильтр.
- Тесты: `tests/test_category_resolver.py`, `tests/test_mapping_service.py`, `tests/test_issue_bulk.py` (новый или существующий), `tests/test_api_issue_category_backlog_trigger.py` (или новый endpoint-тест на сброс).

---

## Task 1: Модель — три новых признака на задаче

**Files:**
- Modify: `app/models/issue.py:116-122` (рядом с `assigned_category` / `category_verified`)

- [ ] **Step 1: Добавить колонки**

В `app/models/issue.py` сразу после блока `require_child_verification` (после строки 122) вставить:

```python
    # Переезд задачи к другому родителю со сменой наследуемой категории.
    # parent_changed — пометка «сменился родитель» (значок + фильтр в стопке).
    # category_context — категория от родителя, зафиксированная на момент
    #   последнего подтверждения (точка отсчёта + значение «была» в подсказке).
    # category_context_key — ключ родителя-источника на тот же момент («из X»).
    parent_changed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True,
    )
    category_context: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category_context_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

`false` уже импортирован (`from sqlalchemy import ... false ...`, строка 7).

- [ ] **Step 2: Сгенерировать миграцию**

Run: `alembic revision --autogenerate -m "add parent change tracking to issue"`
Expected: создан файл в `alembic/versions/` с тремя `op.add_column` (batch для SQLite).

- [ ] **Step 3: Проверить и применить миграцию**

Открыть свежий файл, убедиться: внутри `with op.batch_alter_table("issues") as batch_op:` три `batch_op.add_column(...)` для `parent_changed`, `category_context`, `category_context_key`, и `create_index` на `parent_changed`. `downgrade` дропает их.
Run: `alembic upgrade head`
Expected: OK, без ошибок.

- [ ] **Step 4: Commit**

```bash
git add app/models/issue.py alembic/versions/
git commit -m "feat(issue): признаки переезда задачи (parent_changed + контекст)"
```

---

## Task 2: Резолвер — «категория от родителя» + сброс точки отсчёта

**Files:**
- Modify: `app/services/category_resolver.py` (метод в класс `CategoryResolver` + модульная функция в конце файла)
- Test: `tests/test_category_resolver.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_category_resolver.py` (проверить существующие фикстуры файла — `db_session`, helper создания issue; если нет helper, создавать `Issue(...)` напрямую как в `tests/test_mapping_service.py:38-50`):

```python
def test_resolve_inherited_ignores_own_assigned(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver

    project = Project(jira_project_id="p-inh", key="INH", name="Inh")
    db_session.add(project)
    db_session.flush()

    parent = Issue(jira_issue_id="j-par", key="INH-1", summary="par",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent)
    db_session.flush()
    child = Issue(jira_issue_id="j-ch", key="INH-2", summary="ch",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, assigned_category="meetings")
    db_session.add(child)
    db_session.flush()

    resolver = CategoryResolver(db_session)
    # своя категория child — meetings, но «от родителя» — tech_debt
    assert resolver.resolve_inherited_for_issue(child).category_code == "tech_debt"


def test_resolve_inherited_no_parent_is_fallback(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver
    from app.services.categories import UNFILLED_WORKLOG_CODE

    project = Project(jira_project_id="p-nf", key="NF", name="NF")
    db_session.add(project)
    db_session.flush()
    orphan = Issue(jira_issue_id="j-or", key="NF-1", summary="or",
                   issue_type="Task", status="Open", project_id=project.id,
                   assigned_category="meetings")
    db_session.add(orphan)
    db_session.flush()

    resolver = CategoryResolver(db_session)
    assert resolver.resolve_inherited_for_issue(orphan).category_code == UNFILLED_WORKLOG_CODE
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_category_resolver.py -k resolve_inherited -v`
Expected: FAIL — `AttributeError: 'CategoryResolver' object has no attribute 'resolve_inherited_for_issue'`.

- [ ] **Step 3: Реализовать метод**

В `app/services/category_resolver.py`, в класс `CategoryResolver` после `resolve_for_issue` (после строки 143) добавить:

```python
    def resolve_inherited_for_issue(self, issue: Issue) -> CategoryResolution:
        """Категория, которую задача получает ОТ РОДИТЕЛЯ — без учёта своей
        назначенной категории. Используется для детекта значимого переезда.

        Если родителя нет — fallback-код (стабильная точка отсчёта).
        """
        self._load_caches()
        if not issue.parent_id:
            return CategoryResolution(
                category_code=UNFILLED_WORKLOG_CODE,
                source=MappingSource.FALLBACK,
            )
        parent = self.db.get(Issue, issue.parent_id)
        if parent is None:
            return CategoryResolution(
                category_code=UNFILLED_WORKLOG_CODE,
                source=MappingSource.FALLBACK,
            )
        return self.resolve_for_issue(parent)
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `py -3.10 -m pytest tests/test_category_resolver.py -k resolve_inherited -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Написать падающий тест на сброс точки отсчёта**

Добавить в тот же файл:

```python
def test_reset_parent_context_sets_baseline_and_clears_flag(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver, reset_parent_context

    project = Project(jira_project_id="p-rs", key="RS", name="RS")
    db_session.add(project)
    db_session.flush()
    parent = Issue(jira_issue_id="j-rsp", key="RS-1", summary="p",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent)
    db_session.flush()
    child = Issue(jira_issue_id="j-rsc", key="RS-2", summary="c",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, parent_changed=True,
                  category_context="meetings", category_context_key="OLD-9")
    db_session.add(child)
    db_session.flush()

    resolver = CategoryResolver(db_session)
    reset_parent_context(db_session, child, resolver)

    assert child.parent_changed is False
    assert child.category_context == "tech_debt"
    assert child.category_context_key == "RS-1"
```

- [ ] **Step 6: Запустить — убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_category_resolver.py -k reset_parent_context -v`
Expected: FAIL — `ImportError: cannot import name 'reset_parent_context'`.

- [ ] **Step 7: Реализовать функцию**

В конец `app/services/category_resolver.py` добавить:

```python
def reset_parent_context(
    resolver_db,
    issue: "Issue",
    resolver: "CategoryResolver",
) -> None:
    """Сбросить пометку переезда и сдвинуть точку отсчёта на текущий контекст.

    Вызывается из всех точек подтверждения категории: после подтверждения
    «откуда/была» больше не актуально, новая база = текущая категория от
    родителя.
    """
    from app.models import Issue as _Issue

    issue.parent_changed = False
    issue.category_context = resolver.resolve_inherited_for_issue(issue).category_code
    parent = resolver_db.get(_Issue, issue.parent_id) if issue.parent_id else None
    issue.category_context_key = parent.key if parent else None
```

- [ ] **Step 8: Запустить — убедиться, что проходит**

Run: `py -3.10 -m pytest tests/test_category_resolver.py -v`
Expected: PASS (весь файл).

- [ ] **Step 9: Commit**

```bash
git add app/services/category_resolver.py tests/test_category_resolver.py
git commit -m "feat(categories): resolve_inherited_for_issue + reset_parent_context"
```

---

## Task 3: Обнаружение переезда в пересчёте категорий

**Files:**
- Modify: `app/services/mapping_service.py:106-168` (`recalculate_issues`)
- Test: `tests/test_mapping_service.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_mapping_service.py` (использует helper `_issue` из файла, строки 38-50; категории через `assigned_category`; запуск `MappingService(db_session).recalculate_issues()`):

```python
def test_parent_move_changes_inherited_flags_verified_issue(db_session, project):
    from app.services.mapping_service import MappingService

    old_parent = _issue(db_session, project, "MV-1")
    old_parent.assigned_category = "tech_debt"
    new_parent = _issue(db_session, project, "MV-2")
    new_parent.assigned_category = "meetings"
    child = _issue(db_session, project, "MV-3", parent=old_parent)
    child.category_verified = True
    db_session.flush()

    svc = MappingService(db_session)
    svc.recalculate_issues()                      # инициализация контекста = tech_debt
    assert child.category_context == "tech_debt"
    assert child.parent_changed is False

    child.parent_id = new_parent.id               # переезд
    db_session.flush()
    svc.recalculate_issues()

    assert child.parent_changed is True
    assert child.category_verified is False
    assert child.category_context == "tech_debt"  # «была» сохранена


def test_parent_move_same_category_no_flag(db_session, project):
    from app.services.mapping_service import MappingService

    a = _issue(db_session, project, "SM-1"); a.assigned_category = "tech_debt"
    b = _issue(db_session, project, "SM-2"); b.assigned_category = "tech_debt"
    child = _issue(db_session, project, "SM-3", parent=a)
    child.category_verified = True
    db_session.flush()

    svc = MappingService(db_session)
    svc.recalculate_issues()
    child.parent_id = b.id
    db_session.flush()
    svc.recalculate_issues()

    assert child.parent_changed is False
    assert child.category_verified is True


def test_parent_move_to_empty_category_flags(db_session, project):
    from app.services.mapping_service import MappingService

    a = _issue(db_session, project, "EM-1"); a.assigned_category = "tech_debt"
    b = _issue(db_session, project, "EM-2")   # без категории
    child = _issue(db_session, project, "EM-3", parent=a)
    child.category_verified = True
    db_session.flush()

    svc = MappingService(db_session)
    svc.recalculate_issues()
    child.parent_id = b.id
    db_session.flush()
    svc.recalculate_issues()

    assert child.parent_changed is True


def test_own_category_task_still_flagged(db_session, project):
    """Случай OS-82248: своя категория не меняется, родитель — меняется."""
    from app.services.mapping_service import MappingService

    a = _issue(db_session, project, "OW-1"); a.assigned_category = "tech_debt"
    b = _issue(db_session, project, "OW-2"); b.assigned_category = "meetings"
    child = _issue(db_session, project, "OW-3", parent=a)
    child.assigned_category = "tech_debt"   # руководитель проставил вручную
    child.category_verified = True
    db_session.flush()

    svc = MappingService(db_session)
    svc.recalculate_issues()
    child.parent_id = b.id
    db_session.flush()
    svc.recalculate_issues()

    assert child.parent_changed is True
    assert child.category_verified is False


def test_excluded_issue_not_flagged(db_session, project):
    from app.services.mapping_service import MappingService

    a = _issue(db_session, project, "EX-1"); a.assigned_category = "tech_debt"
    b = _issue(db_session, project, "EX-2"); b.assigned_category = "meetings"
    child = _issue(db_session, project, "EX-3", parent=a)
    child.category_verified = True
    child.include_in_analysis = False
    db_session.flush()

    svc = MappingService(db_session)
    svc.recalculate_issues()
    child.parent_id = b.id
    db_session.flush()
    svc.recalculate_issues()

    assert child.parent_changed is False
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_mapping_service.py -k "parent_move or own_category or excluded_issue" -v`
Expected: FAIL — `parent_changed` остаётся False / контекст не инициализируется.

- [ ] **Step 3: Реализовать блок обнаружения**

В `app/services/mapping_service.py`, `recalculate_issues`:

После строки 122 (`issues = self.db.query(Issue).all()`) добавить карту ключей:

```python
        key_by_id = {i.id: i.key for i in issues}
```

Внутри цикла `for issue in issues:` после блока Backlog(после строки 158, перед `count += 1`) добавить:

```python
            # Детект значимого переезда к другому родителю (смена категории
            # от родителя относительно зафиксированной точки отсчёта).
            inherited = self.resolver.resolve_inherited_for_issue(issue).category_code
            parent_key = key_by_id.get(issue.parent_id) if issue.parent_id else None
            excluded = not bool(issue.include_in_analysis)
            if excluded:
                issue.category_context = inherited
                issue.category_context_key = parent_key
                if issue.parent_changed:
                    issue.parent_changed = False
            elif issue.category_context is None:
                # Первая встреча — тихо инициализируем, без пометки.
                issue.category_context = inherited
                issue.category_context_key = parent_key
            elif issue.category_verified and inherited != issue.category_context:
                issue.parent_changed = True
                issue.category_verified = False
                # category_context / _key оставляем как «откуда / была».
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `py -3.10 -m pytest tests/test_mapping_service.py -v`
Expected: PASS (включая существующие тесты файла).

- [ ] **Step 5: Commit**

```bash
git add app/services/mapping_service.py tests/test_mapping_service.py
git commit -m "feat(categories): детект переезда задачи в пересчёте категорий"
```

---

## Task 4: Сброс пометки в точках подтверждения (issue_config)

**Files:**
- Modify: `app/api/endpoints/issue_config.py` — `set_issue_category` (~636-658), verify endpoint (~820-868), `batch-category` (найти `PUT /batch-category`, ~723-790, места установки `category_verified=True`)
- Test: `tests/test_api_issue_category_backlog_trigger.py` (или новый `tests/test_api_parent_change_reset.py`)

- [ ] **Step 1: Написать падающий endpoint-тест**

Создать `tests/test_api_parent_change_reset.py` по образцу существующих endpoint-тестов (TestClient + `client` фикстура из conftest; снять снимок до commit — ORM caveat). Тест: задача с `parent_changed=True`, `category_context="meetings"`; вызвать `PUT /api/v1/issues/{id}/category` с новой категорией; после — `parent_changed=False` и `category_context` пересчитан на текущий контекст.

```python
def test_set_category_clears_parent_changed(client, db_session):
    from app.models import Project, Issue

    project = Project(jira_project_id="p-pc", key="PC", name="PC")
    db_session.add(project); db_session.flush()
    parent = Issue(jira_issue_id="j-pcp", key="PC-1", summary="p",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent); db_session.flush()
    issue = Issue(jira_issue_id="j-pci", key="PC-2", summary="c",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, parent_changed=True,
                  category_verified=False, category_context="meetings",
                  category_context_key="OLD-1")
    db_session.add(issue); db_session.flush()
    iid = issue.id

    resp = client.put(f"/api/v1/issues/{iid}/category",
                      json={"category_code": "tech_debt"})
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Issue, iid)
    assert refreshed.parent_changed is False
    assert refreshed.category_context == "tech_debt"
    assert refreshed.category_context_key == "PC-1"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_api_parent_change_reset.py -v`
Expected: FAIL — `parent_changed` остаётся True.

- [ ] **Step 3: Подключить сброс в `set_issue_category`**

В `app/api/endpoints/issue_config.py`, импортировать `reset_parent_context` (рядом с импортом `CategoryResolver`). В `set_issue_category` после строки 646 (`issue.category = resolver.resolve_for_issue(issue).category_code`) добавить:

```python
    reset_parent_context(db, issue, resolver)
```

- [ ] **Step 4: Подключить сброс в verify endpoint**

В verify endpoint (где `issue.category_verified = True`, ~841, и для потомков ~857/863): создать `resolver = CategoryResolver(db)` в начале функции (если ещё нет) и для каждой задачи, которой ставится `category_verified=True`, вызвать `reset_parent_context(db, <issue>, resolver)`. Для потомков в циклах — внутри цикла после установки флага.

- [ ] **Step 5: Подключить сброс в `batch-category`**

Найти `PUT /batch-category` (поиск `batch-category` / `batch_category` в файле). Везде, где задаче ставится `assigned_category` и/или `category_verified=True`, после пересчёта `issue.category` вызвать `reset_parent_context(db, issue, resolver)` (использовать resolver, который endpoint уже создаёт; если нет — создать один на запрос).

- [ ] **Step 6: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_api_parent_change_reset.py tests/test_api_issue_category_backlog_trigger.py -v`
Expected: PASS.

- [ ] **Step 7: Перезапустить бэкенд и прогнать связанный suite**

Run: `py -3.10 -m pytest tests/test_issue_config*.py tests/test_api_issue*.py -v`
Expected: PASS (нет регрессий).

- [ ] **Step 8: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_api_parent_change_reset.py
git commit -m "feat(categories): сброс пометки переезда при подтверждении категории"
```

---

## Task 5: Поля переезда в дереве + bulk preview

**Files:**
- Modify: `app/api/endpoints/issue_config.py` — схемы узлов (строки 59-60, 80-81, 110-111) + сериализация (268-269, 551-552, 1229-1230, 1376-1377)
- Modify: `app/api/endpoints/issue_bulk.py` — `BulkFilter` (28-35), `_apply_filters` (59-88), `BulkPreviewItem` (42-51), сериализация (107-119)
- Test: `tests/test_issue_bulk.py` (если нет — создать) + проверка дерева в существующем tree-тесте

- [ ] **Step 1: Написать падающий тест на фильтр bulk**

Создать/дополнить `tests/test_issue_bulk.py`:

```python
def test_bulk_preview_only_parent_changed(client, db_session):
    from app.models import Project, Issue

    project = Project(jira_project_id="p-bp", key="BP", name="BP")
    db_session.add(project); db_session.flush()
    moved = Issue(jira_issue_id="j-bm", key="BP-1", summary="moved",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_changed=True, category_context="tech_debt",
                  category_context_key="OLD-1")
    plain = Issue(jira_issue_id="j-bp", key="BP-2", summary="plain",
                  issue_type="Task", status="Open", project_id=project.id)
    db_session.add_all([moved, plain]); db_session.flush()

    resp = client.post("/api/v1/issues/bulk/preview",
                       json={"filters": {"only_parent_changed": True}, "limit": 50})
    assert resp.status_code == 200
    data = resp.json()
    keys = {i["key"] for i in data["items"]}
    assert "BP-1" in keys and "BP-2" not in keys
    assert next(i for i in data["items"] if i["key"] == "BP-1")["parent_changed"] is True
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_issue_bulk.py -k only_parent_changed -v`
Expected: FAIL — фильтр не существует / поле отсутствует.

- [ ] **Step 3: Расширить bulk-эндпоинт**

В `app/api/endpoints/issue_bulk.py`:

`BulkFilter` (после строки 34) добавить:
```python
    only_parent_changed: bool = False
```

`_apply_filters` (после блока `only_no_assigned`, строка 86) добавить:
```python
    if filters.only_parent_changed:
        query = query.filter(Issue.parent_changed.is_(True))
```

`BulkPreviewItem` (после строки 49) добавить:
```python
    parent_changed: bool = False
    category_context: Optional[str] = None
    category_context_key: Optional[str] = None
```

В сериализации `bulk_preview` (внутри `BulkPreviewItem(...)`, после `assigned_category=r.assigned_category,`) добавить:
```python
            parent_changed=bool(r.parent_changed),
            category_context=r.category_context,
            category_context_key=r.category_context_key,
```

- [ ] **Step 4: Добавить поля в схемы узлов дерева**

В `app/api/endpoints/issue_config.py` в КАЖДУЮ pydantic-модель узла, где есть `category_verified` / `require_child_verification` (строки ~59-60, ~80-81, ~110-111), добавить три поля:
```python
    parent_changed: bool = False
    category_context: Optional[str] = None
    category_context_key: Optional[str] = None
```

В КАЖДОЙ точке сериализации узла (строки ~268-269, ~551-552, ~1229-1230, ~1376-1377), где задаются `category_verified=...`/`require_child_verification=...`, добавить:
```python
            parent_changed=bool(getattr(<row>, "parent_changed", False)),
            category_context=getattr(<row>, "category_context", None),
            category_context_key=getattr(<row>, "category_context_key", None),
```
где `<row>` — та же переменная (`issue` / `r` / `ch` / `node`), что используется рядом.

- [ ] **Step 5: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_issue_bulk.py tests/test_issue_config*.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/issue_bulk.py app/api/endpoints/issue_config.py tests/test_issue_bulk.py
git commit -m "feat(categories): признаки переезда в дереве задач и bulk preview"
```

---

## Task 6: Фронт — значок, подсказка, фильтр «только переехавшие»

**Files:**
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`
- Modify: тип узла дерева (искать в `frontend/src/` определение, где есть `category_verified` — `grep -r category_verified frontend/src`), добавить `parent_changed`, `category_context`, `category_context_key`.

- [ ] **Step 1: Расширить тип узла**

Найти TS-тип узла дерева (там, где `categoryVerified` / `category_verified`). Добавить:
```typescript
  parent_changed?: boolean;
  category_context?: string | null;
  category_context_key?: string | null;
```

- [ ] **Step 2: Значок + подсказка на узле**

В `CategoriesEditorPage.tsx` в рендере строки узла стопки, когда `node.parent_changed`, показать AntD `Tag` (цвет warning/orange) с текстом «сменился родитель» внутри `Tooltip`. Текст подсказки (использовать существующий маппер кодов категорий в подписи — найти в файле функцию вида `categoryLabel(code)` / словарь):

```
Переехала из {node.category_context_key} (была {label(node.category_context)})
→ текущий родитель {parentKey} ({label(currentInheritedCode)})
```

Если `currentInheritedCode` недоступен на узле — показать только «была {…}», текущая видна по положению в дереве. Не использовать технические коды в видимом тексте — только подписи категорий.

- [ ] **Step 3: Фильтр «только переехавшие»**

На вкладке стопки добавить переключатель (AntD `Switch` / `Checkbox`) «только переехавшие». Когда включён — фильтровать отображаемые узлы по `parent_changed === true` (клиентский фильтр по уже загруженному дереву стопки).

- [ ] **Step 4: Сборка фронта**

Run (из `frontend/`): `npm run build`
Expected: успешная сборка без TS-ошибок.

- [ ] **Step 5: Браузер-смок (Playwright MCP или ручной)**

Запустить бэкенд (`uvicorn`) + фронт (`npm run dev`), открыть «Категории задач». Убедиться: переключатель «только переехавшие» виден; при наличии помеченной задачи виден оранжевый значок с подсказкой. (Если нет данных с пометкой — достаточно проверить, что страница рендерится и переключатель работает на пустом наборе.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(categories): значок «сменился родитель» + фильтр переехавших"
```

---

## Task 7: Финальная проверка и заметка о релизе

- [ ] **Step 1: Полный backend suite**

Run: `py -3.10 -m pytest tests/ -q`
Expected: всё зелёное (кроме известных pre-existing падений — сверить с памятью `project_ci_red_pre_existing`).

- [ ] **Step 2: Линт**

Run: `ruff check app/ tests/`
Expected: чисто (или только pre-existing).

- [ ] **Step 3: Заметка о релизе**

Run:
```bash
py -3.10 scripts/release_note.py add --category Новое \
  --text "Задачи, переехавшие к другому родителю со сменой категории, автоматически возвращаются на переподтверждение с пометкой «сменился родитель» и историей переезда."
```

- [ ] **Step 4: Commit + push**

```bash
git add -A
git commit -m "chore(categories): release note — переподтверждение при переезде"
git push origin main
```

---

## Self-Review (заполнить при исполнении)

- Покрытие спеки: триггер (Task 3) / случай OS-82248 (Task 3) / пустая категория родителя (Task 3) / исключение архивных (Task 3) / одна стопка + значок + фильтр (Task 6) / история переезда (Task 5 поля + Task 6 подсказка) / гашение пометки (Task 4) / bulk-фильтр (Task 5). ✓
- Имена согласованы: `parent_changed`, `category_context`, `category_context_key`, `resolve_inherited_for_issue`, `reset_parent_context` — одинаковы во всех задачах. ✓
