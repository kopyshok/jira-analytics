# Планирование Q4 — Часть 1 «Быстрые правки» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть шесть мелких правок планирования из спеки `docs/superpowers/specs/2026-09-23-planning-q4-design.md` (раздел «Часть 1», пп. 1.1–1.6) и подготовить заметки «Что нового».

**Architecture:** Бэкенд — две правки: (1.5) ручные часы задачи живут только в `Issue`, после каждой ручной правки копия в `BacklogItem` пересчитывается через `BacklogService.sync_from_issue`, инлайн-правка часов в строке бэклога идёт через `PlanEditService.edit`; (1.6) строка `employee_load` в ответе диаграммы получает `left_to` / `joined_from`. Фронт — точечные правки в хуке переключения распределения, модалке создания сценария, шапке сценария, модалке параметров планирования и тепловой карте загрузки.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (pytest, `py -3.10`), React 19 + TS + AntD 6 + TanStack Query. Во фронте нет vitest — проверка фронта = `npm run build` + `npx eslint <изменённые файлы>` + ручная проверка.

---

## Общие правила исполнения

- Ветка: `feature/planning-q4` (уже создана).
- Тесты: `py -3.10 -m pytest <путь> -v`. Полный прогон — `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py` (LLM-тесты висят без сети).
- Фронт: команды запускать из `D:\ClaudeDev\JiraAnalysis\frontend`. `npm run lint` по всему проекту уже красный по чужим файлам — проверяем только изменённые файлы через `npx eslint <файлы>`.
- Коммиты: добавлять в индекс только явно перечисленные пути (`git add <пути>`), затем `git commit -m "<заголовок>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`. Не использовать `git commit -- <пути>` (берёт рабочую копию, мимо индекса) и heredoc с пустой первой строкой.
- После правок кода — `graphify update .` (AST, без затрат).

## Карта файлов

| Файл | Что меняется | Пункт |
|---|---|---|
| `frontend/src/hooks/usePlanning.ts` | условие оптимистичного подъёма строки учитывает `lift` | 1.1 |
| `frontend/src/components/planning/ScenarioCreateModal.tsx` | авто-название, команда из глобального фильтра | 1.2, 1.3 |
| `frontend/src/pages/PlanningPage.tsx` | название сценария в шапке редактируется | 1.4 |
| `app/services/plan_edit_service.py` | после edit/revert/resolve_conflict — `sync_from_issue` | 1.5 |
| `app/api/endpoints/issue_config.py` | эндпоинты правки плана публикуют событие | 1.5 |
| `app/api/endpoints/backlog.py` | PATCH строки: часы через `PlanEditService`; в ответе — Jira-значения часов | 1.5 |
| `tests/test_plan_edit_backlog_sync.py` (новый) | тесты 1.5 | 1.5 |
| `frontend/src/types/api.ts` | 4 поля `estimate_<role>_hours_jira` | 1.5 |
| `frontend/src/components/backlog/BacklogPlanningParamsModal.tsx` | драуэр плана берёт свежую строку и Jira-значения | 1.5 |
| `app/api/endpoints/resource_planning.py` | `TeamMoveOut`, поля `left_to` / `joined_from` | 1.6 |
| `tests/api/test_resource_planning_gantt_employee_load.py` | тесты 1.6 | 1.6 |
| `frontend/src/api/resourcePlanning.ts` | тип `TeamMove`, поля в `EmployeeLoadOut` | 1.6 |
| `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx` | подпись под фамилией + подсказка дня | 1.6 |
| `release_notes/drafts.json` (создаётся CLI) | заметки «Что нового» | финал |

Порядок задач: сначала бэкенд с тестами (Task 1–4), потом фронт (Task 5–9), затем заметки (Task 10) и финальная проверка (Task 11).

---

### Task 1: 1.5 — ручная правка плана сразу пересчитывает копию часов в бэклоге

**Files:**
- Create: `tests/test_plan_edit_backlog_sync.py`
- Modify: `app/services/plan_edit_service.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_plan_edit_backlog_sync.py`:

```python
"""Ручные часы задачи (Issue) сразу видны в строке бэклога.

Регресс: правка через /issues/{id}/plan писала только
Issue.planned_<role>_hours_manual, а список бэклога, сценарии и ресурсный план
читают копию BacklogItem.estimate_<role>_hours, которая обновлялась лишь при
синке. Спека: docs/superpowers/specs/2026-09-23-planning-q4-design.md, п. 1.5.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project
from app.services.backlog_service import BACKLOG_CATEGORY, BacklogService
from app.services.event_bus import get_event_bus


def _seed(db, key="PS-1", **issue_kwargs):
    """Jira-задача категории «Инициативы RFA» + её строка бэклога.

    Копия часов в строке совпадает с действующими часами задачи — как после синка.
    """
    p = Project(id=f"p-{key}", key=key.split("-")[0], jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    issue = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type="RFA", status="Open",
        project_id=p.id, category=BACKLOG_CATEGORY, **issue_kwargs,
    )
    db.add(issue)
    db.flush()
    item = BacklogItem(
        issue_id=issue.id, title=issue.summary, project_id=p.id,
        estimate_analyst_hours=issue.planned_analyst_hours,
        estimate_dev_hours=issue.planned_dev_hours,
        estimate_qa_hours=issue.planned_qa_hours,
        estimate_opo_hours=issue.planned_opo_hours,
    )
    item.estimate_hours = sum(
        v or 0 for v in (
            item.estimate_analyst_hours, item.estimate_dev_hours,
            item.estimate_qa_hours, item.estimate_opo_hours,
        )
    ) or None
    db.add(item)
    db.commit()
    return issue.id, item.id


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    def _override():
        yield testclient_db_session
    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_event_bus] = lambda: bus
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_event_bus, None)


def _item(db, item_id) -> BacklogItem:
    db.expire_all()
    return db.get(BacklogItem, item_id)


def test_plan_edit_updates_backlog_copy_and_total(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(db, planned_analyst_hours_jira=100, planned_dev_hours_jira=500)

    r = client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "уточнили"},
    )
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.estimate_dev_hours == 600
    assert item.estimate_analyst_hours == 100
    assert item.estimate_hours == 700


def test_plan_revert_restores_backlog_copy(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-2", planned_dev_hours_jira=500)
    client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )

    r = client.post(f"/api/v1/issues/{issue_id}/plan/revert", json={})
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.estimate_dev_hours == 500
    assert item.estimate_hours == 500


def test_conflict_accept_jira_updates_backlog_copy(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(
        db, key="PS-3", planned_dev_hours_jira=500, planned_dev_hours_manual=600,
    )
    assert _item(db, item_id).estimate_dev_hours == 600

    r = client.post(
        f"/api/v1/issues/{issue_id}/plan/conflict-resolve",
        json={"action": "accept_jira", "role": "dev"},
    )
    assert r.status_code == 200, r.text

    assert _item(db, item_id).estimate_dev_hours == 500


def test_plan_edit_publishes_backlog_event(client, testclient_db_session, bus):
    db = testclient_db_session
    issue_id, _ = _seed(db, key="PS-4", planned_dev_hours_jira=500)

    client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )
    client.post(f"/api/v1/issues/{issue_id}/plan/revert", json={})
    client.post(
        f"/api/v1/issues/{issue_id}/plan/conflict-resolve",
        json={"action": "ignore", "role": "dev"},
    )

    expected = {"type": "entity_changed", "entities": ["issues", "backlog"]}
    assert bus.publish.await_count == 3
    for call in bus.publish.await_args_list:
        assert call.args[0] == expected


def test_plan_edit_without_backlog_item_is_ok(client, testclient_db_session):
    """Задача вне бэклога (например, обычная задача в дереве) — правка работает,
    строк бэклога не появляется."""
    db = testclient_db_session
    p = Project(id="p-PS5", key="PS5", jira_project_id="jp-PS5", name="P5")
    db.add(p)
    db.flush()
    issue = Issue(
        id="i-PS5", key="PS5-1", jira_issue_id="j-PS5", summary="s",
        issue_type="Task", status="Open", project_id=p.id,
        category="development", planned_dev_hours_jira=10,
    )
    db.add(issue)
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 20}, "comment": "x"},
    )
    assert r.status_code == 200, r.text
    assert db.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0
```

- [ ] **Step 2: Запустить — тесты падают**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py -v`
Expected: FAIL — `test_plan_edit_updates_backlog_copy_and_total` (`500 != 600`), `test_plan_revert_restores_backlog_copy`, `test_conflict_accept_jira_updates_backlog_copy`, `test_plan_edit_publishes_backlog_event` (`await_count == 0`). `test_plan_edit_without_backlog_item_is_ok` проходит уже сейчас.

- [ ] **Step 3: Пересчёт копии в `PlanEditService`**

В `app/services/plan_edit_service.py`:

Импорт (после `from app.models import Issue, PlanAudit`):

```python
from app.services.backlog_service import BacklogService
```

Метод в классе (после `__init__`):

```python
    def _sync_backlog(self, issue: Issue) -> None:
        """Перенести действующие часы задачи в её строку бэклога.

        Строка списка, сценарии и ресурсный план читают копию часов в строке
        бэклога; без этого вызова ручная правка появлялась там только после
        следующего синка. Задача вне бэклога — ничего не создаём.
        """
        has_item = (
            self.db.query(BacklogItem.id).filter_by(issue_id=issue.id).first()
            is not None
        )
        if has_item:
            BacklogService(self.db).sync_from_issue(issue)
```

и дополнить импорт моделей: `from app.models import BacklogItem, Issue, PlanAudit`.

Вставить `self._sync_backlog(issue)` непосредственно перед каждым `self.db.commit()` в трёх методах:
- `edit` — перед `self.db.commit()` после цикла по ролям;
- `revert` — перед финальным `self.db.commit()` (после `if/else`);
- `resolve_conflict` — перед финальным `self.db.commit()` (после `if/else`).

Пример для `edit` (хвост метода):

```python
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=new_value,
                source="manual_edit", user_id=user_id, comment=comment,
                created_at=datetime.utcnow(),
            ))
        self._sync_backlog(issue)
        self.db.commit()
        return issue
```

- [ ] **Step 4: Прогнать тесты сервиса**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py -v -k "not publishes"`
Expected: 4 passed (тест события ещё падает — он для Task 2).

- [ ] **Step 5: Коммит**

```bash
git add app/services/plan_edit_service.py tests/test_plan_edit_backlog_sync.py
git commit -m "fix(planning): ручные часы сразу попадают в строку бэклога" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 1.5 — эндпоинты правки плана публикуют событие изменения

**Files:**
- Modify: `app/api/endpoints/issue_config.py` (функции `patch_plan`, `revert_plan`, `resolve_plan_conflict`, ~строки 1209–1274)
- Test: `tests/test_plan_edit_backlog_sync.py::test_plan_edit_publishes_backlog_event` (уже написан)

- [ ] **Step 1: Убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py::test_plan_edit_publishes_backlog_event -v`
Expected: FAIL — `assert 0 == 3`.

- [ ] **Step 2: Сделать три эндпоинта асинхронными и публиковать событие**

`EventBroadcaster` и `get_event_bus` уже импортированы в файле. Заменить три функции целиком:

```python
@router.patch("/{issue_id}/plan")
async def patch_plan(
    issue_id: str,
    payload: PlanEditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    try:
        PlanEditService(db).edit(
            issue_id, payload.role_hours, payload.comment,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.refresh(issue)
    plan = {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return {"plan": plan}


@router.post("/{issue_id}/plan/revert")
async def revert_plan(
    issue_id: str,
    payload: PlanRevertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    PlanEditService(db).revert(
        issue_id, audit_id=payload.audit_id,
        user_id=current_user.id,
    )
    db.refresh(issue)
    plan = {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return {"plan": plan}
```

и

```python
@router.post("/{issue_id}/plan/conflict-resolve")
async def resolve_plan_conflict(
    issue_id: str,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    try:
        PlanEditService(db).resolve_conflict(
            issue_id, payload.role, payload.action,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return {"ok": True}
```

(Снимок `plan` берётся до `await` — после коммита сессия отдаёт атрибуты заново, см. `tests/CLAUDE.md`, «ORM caveat».)

- [ ] **Step 3: Прогнать тесты**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py tests/test_plan_edit_api.py -v`
Expected: все PASS.

- [ ] **Step 4: Коммит**

```bash
git add app/api/endpoints/issue_config.py
git commit -m "fix(planning): правка плана задачи обновляет бэклог и сценарии у всех" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 1.5 — инлайн-правка часов в строке бэклога пишет в задачу, отдаёт Jira-значения

**Files:**
- Modify: `app/api/endpoints/backlog.py` (`BacklogItemResponse` ~стр. 180, `_to_response` ~стр. 370, `update_backlog_item` ~стр. 1028)
- Test: `tests/test_plan_edit_backlog_sync.py` (дописать)

- [ ] **Step 1: Дописать падающие тесты** в конец `tests/test_plan_edit_backlog_sync.py`:

```python
def test_inline_estimate_goes_to_issue_and_survives_sync(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-6", planned_dev_hours_jira=500)

    r = client.patch(f"/api/v1/backlog/{item_id}", json={"estimate_dev_hours": 700})
    assert r.status_code == 200, r.text
    assert r.json()["estimate_dev_hours"] == 700

    db.expire_all()
    issue = db.get(Issue, issue_id)
    assert issue.planned_dev_hours_manual == 700
    assert issue.planned_dev_hours_jira == 500

    # Синк больше не затирает ручную правку копией из Jira.
    BacklogService(db).sync_from_issue(issue)
    db.commit()
    item = _item(db, item_id)
    assert item.estimate_dev_hours == 700
    assert item.estimate_hours == 700


def test_inline_estimate_null_returns_to_jira(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(
        db, key="PS-7", planned_dev_hours_jira=500, planned_dev_hours_manual=700,
    )

    r = client.patch(f"/api/v1/backlog/{item_id}", json={"estimate_dev_hours": None})
    assert r.status_code == 200, r.text
    assert r.json()["estimate_dev_hours"] == 500
    db.expire_all()
    assert db.get(Issue, issue_id).planned_dev_hours_manual is None


def test_inline_estimate_on_manual_idea_writes_directly(client, testclient_db_session):
    """Ручная идея без Jira-задачи — часы по-прежнему пишутся в саму строку."""
    db = testclient_db_session
    item = BacklogItem(title="Идея")
    db.add(item)
    db.commit()

    r = client.patch(f"/api/v1/backlog/{item.id}", json={"estimate_dev_hours": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimate_dev_hours"] == 10
    assert body["estimate_hours"] == 10


def test_backlog_response_carries_jira_hours(client, testclient_db_session):
    db = testclient_db_session
    _, item_id = _seed(
        db, key="PS-8", planned_dev_hours_jira=500, planned_dev_hours_manual=700,
    )
    body = client.get(f"/api/v1/backlog/{item_id}").json()
    assert body["estimate_dev_hours"] == 700
    assert body["estimate_dev_hours_jira"] == 500
    assert body["estimate_analyst_hours_jira"] is None
```

- [ ] **Step 2: Запустить — падают**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py -v -k "inline or jira_hours"`
Expected: FAIL — `planned_dev_hours_manual` равно `None` вместо 700; `KeyError: 'estimate_dev_hours_jira'`. `test_inline_estimate_on_manual_idea_writes_directly` проходит уже сейчас.

- [ ] **Step 3: Поля Jira-часов в ответе**

В `BacklogItemResponse` после блока `duration_launch_days_jira: Optional[float] = None` добавить:

```python
    # Часы по ролям из Jira (без ручной правки) — для «из Jira» в правке плана.
    estimate_analyst_hours_jira: Optional[float] = None
    estimate_dev_hours_jira: Optional[float] = None
    estimate_qa_hours_jira: Optional[float] = None
    estimate_opo_hours_jira: Optional[float] = None
```

В `_to_response` после `duration_launch_days_jira=issue.duration_launch_days if issue else None,` добавить:

```python
        estimate_analyst_hours_jira=issue.planned_analyst_hours_jira if issue else None,
        estimate_dev_hours_jira=issue.planned_dev_hours_jira if issue else None,
        estimate_qa_hours_jira=issue.planned_qa_hours_jira if issue else None,
        estimate_opo_hours_jira=issue.planned_opo_hours_jira if issue else None,
```

- [ ] **Step 4: Инлайн-правка через `PlanEditService`**

Импорты в начале `app/api/endpoints/backlog.py`:

```python
from app.core.auth_deps import get_current_user
from app.services.plan_edit_service import PlanEditService, ROLES as PLAN_ROLES
```

(проверить, что `plan_edit_service` не импортирует `app.api.*` — не импортирует, цикла нет).

Заменить `update_backlog_item` целиком:

```python
@router.patch("/{item_id}", response_model=BacklogItemResponse)
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
    current_user=Depends(get_current_user),
):
    """Частичное обновление элемента бэклога.

    Часы по ролям у Jira-задачи — это её ручное значение (живёт в задаче):
    пишем через правку плана с записью в журнал, копия в строке пересчитается
    оттуда. Прямая запись в копию затиралась бы следующим синком.
    """
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    patch = data.model_dump(exclude_unset=True)
    if not patch:
        return _to_response(item, _approved_scenarios_for(db, item.id))

    role_hours = {
        role: patch.pop(f"estimate_{role}_hours")
        for role in PLAN_ROLES
        if f"estimate_{role}_hours" in patch
    }
    for key, value in patch.items():
        setattr(item, key, value)
    if role_hours and item.issue_id is not None:
        # Коммитит и сам выравнивает копию часов и итог в строке.
        PlanEditService(db).edit(
            item.issue_id, role_hours, "Правка в списке бэклога",
            user_id=current_user.id,
        )
    else:
        for role, value in role_hours.items():
            setattr(item, f"estimate_{role}_hours", value)
        _recompute_total(item)
        db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
    db.refresh(item)
    return _to_response(item, _approved_scenarios_for(db, item.id))
```

- [ ] **Step 5: Прогнать тесты бэклога и событий**

Run: `py -3.10 -m pytest tests/test_plan_edit_backlog_sync.py tests/test_api_entity_changed_backlog.py tests/test_backlog_endpoints.py tests/test_plan_edit_api.py -v`
Expected: все PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/api/endpoints/backlog.py tests/test_plan_edit_backlog_sync.py
git commit -m "fix(backlog): часы из строки бэклога не затираются синком" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 1.6 — «куда выбыл / откуда пришёл» в строке загрузки по дням

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`EmployeeLoadOut` ~стр. 483; сборка `employee_load` ~стр. 1004–1106)
- Test: `tests/api/test_resource_planning_gantt_employee_load.py`

- [ ] **Step 1: Дописать падающие тесты** в конец `tests/api/test_resource_planning_gantt_employee_load.py`:

```python
OTHER = "T_OTHER"


def _membership(db_session, emp_id) -> EmployeeTeam:
    return (
        db_session.query(EmployeeTeam)
        .filter(EmployeeTeam.employee_id == emp_id, EmployeeTeam.team == TEAM)
        .one()
    )


def _load_row(client, plan_id, emp_id) -> dict:
    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    return next(r for r in resp.json()["employee_load"] if r["employee_id"] == emp_id)


def test_leaver_reports_next_team(client, db_session):
    """Выбыл 20.07 и в тот же день пришёл в другую команду — подвал говорит куда."""
    plan_id, emp_id = _seed(db_session, None)
    _membership(db_session, emp_id).left_at = date(2026, 7, 20)
    db_session.add(EmployeeTeam(
        employee_id=emp_id, team=OTHER, is_primary=False, joined_at=date(2026, 7, 20),
    ))
    db_session.commit()

    load = _load_row(client, plan_id, emp_id)
    assert load["left_to"] == {"date": "2026-07-20", "team": OTHER}
    assert load["joined_from"] is None


def test_leaver_without_next_team(client, db_session):
    plan_id, emp_id = _seed(db_session, None)
    _membership(db_session, emp_id).left_at = date(2026, 7, 20)
    db_session.commit()

    load = _load_row(client, plan_id, emp_id)
    assert load["left_to"] == {"date": "2026-07-20", "team": None}


def test_joiner_reports_previous_team(client, db_session):
    """Пришёл 03.08 из другой команды — подвал говорит откуда."""
    plan_id, emp_id = _seed(db_session, None)
    _membership(db_session, emp_id).joined_at = date(2026, 8, 3)
    db_session.add(EmployeeTeam(
        employee_id=emp_id, team=OTHER, is_primary=False, left_at=date(2026, 8, 3),
    ))
    db_session.commit()

    load = _load_row(client, plan_id, emp_id)
    assert load["joined_from"] == {"date": "2026-08-03", "team": OTHER}
    assert load["left_to"] is None


def test_full_quarter_member_has_no_moves(client, db_session):
    plan_id, emp_id = _seed(db_session, None)
    load = _load_row(client, plan_id, emp_id)
    assert load["left_to"] is None
    assert load["joined_from"] is None
```

- [ ] **Step 2: Запустить — падают**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_gantt_employee_load.py -v`
Expected: 4 новых FAIL с `KeyError: 'left_to'` / `'joined_from'`; старые 3 PASS.

- [ ] **Step 3: Схема ответа**

В `app/api/endpoints/resource_planning.py` перед `class EmployeeLoadOut` добавить:

```python
class TeamMoveOut(BaseModel):
    """Переход сотрудника на границе участия в команде плана внутри квартала."""
    # Для выбывшего — первый день вне команды; для пришедшего — первый день в ней.
    date: date
    # Команда по ту сторону границы; None — ни в одной команде.
    team: Optional[str] = None
```

В `EmployeeLoadOut` после `member_to: Optional[date] = None` добавить:

```python
    # Куда выбыл (после последнего дня участия) / откуда пришёл (накануне
    # первого). None — участие покрывает этот край квартала.
    left_to: Optional[TeamMoveOut] = None
    joined_from: Optional[TeamMoveOut] = None
```

- [ ] **Step 4: Заполнение в сборке `employee_load`**

Внутри `if plan_employees:` сразу после `avail = svc.build_availability(...)` добавить (одним запросом на всех, без N+1):

```python
            membership = tm.membership_rows(db, [e.id for e in plan_employees])
```

Заменить хвост цикла `for e in plan_employees:` — блок от `iv = member_iv.get(e.id) or []` до конца `employee_load.append(...)` — на:

```python
                iv = member_iv.get(e.id) or []
                member_from = iv[0][0] if iv and iv[0][0] > q_start else None
                member_to = iv[-1][1] if iv and iv[-1][1] < q_end else None
                emp_rows = membership.get(e.id, [])
                left_to = None
                if member_to is not None:
                    first_out = member_to + _td(days=1)
                    left_to = TeamMoveOut(
                        date=first_out, team=tm.team_on_day(emp_rows, first_out)
                    )
                joined_from = None
                if member_from is not None:
                    joined_from = TeamMoveOut(
                        date=member_from,
                        team=tm.team_on_day(emp_rows, member_from - _td(days=1)),
                    )
                employee_load.append(
                    EmployeeLoadOut(
                        employee_id=e.id,
                        employee_name=e.display_name,
                        employee_role=e.role,
                        days=days_out,
                        member_from=member_from,
                        member_to=member_to,
                        left_to=left_to,
                        joined_from=joined_from,
                    )
                )
```

(`_td` уже импортирован в этой функции: `from datetime import timedelta as _td`, ~стр. 895.)

- [ ] **Step 5: Прогнать тесты диаграммы**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_gantt_employee_load.py -v`
Expected: 7 passed.

Run: `py -3.10 -m pytest tests/ -q -k "resource_plan or gantt" --ignore=tests/api/test_llm.py`
Expected: без новых падений.

- [ ] **Step 6: Коммит**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_resource_planning_gantt_employee_load.py
git commit -m "feat(resource-planning): подвал знает, куда выбыл и откуда пришёл сотрудник" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 1.1 — выключенный «Поднимать наверх» не двигает строку

**Files:**
- Modify: `frontend/src/hooks/usePlanning.ts:156-166`

- [ ] **Step 1: Правка условия**

В `usePatchAllocation`, `onMutate`, заменить блок:

```ts
        // При включении (False → True) поднимаем строку в начало списка — backend
        // делает то же через sort_order = min−1, но optimistic update должен
        // отразить это мгновенно, иначе строка остаётся на месте до refetch'а.
        const wasIncluded = prev.find((a) => a.id === allocId)?.included ?? false;
        if (data.included === true && !wasIncluded) {
```

на:

```ts
        // При включении (False → True) поднимаем строку в начало списка — backend
        // делает то же через sort_order = min−1, но optimistic update должен
        // отразить это мгновенно, иначе строка остаётся на месте до refetch'а.
        // Тумблер «Поднимать наверх» выключен (lift=false) — сервер порядок не
        // меняет, и локальный подъём дал бы двойной прыжок: вверх и обратно.
        const wasIncluded = prev.find((a) => a.id === allocId)?.included ?? false;
        if (data.included === true && !wasIncluded && data.lift !== false) {
```

- [ ] **Step 2: Сборка и линтер**

Run (в `frontend/`): `npm run build` → Expected: успешная сборка без ошибок типов.
Run: `npx eslint src/hooks/usePlanning.ts` → Expected: без ошибок.

- [ ] **Step 3: Ручная проверка**

`uvicorn app.main:app --port 8000` + `npm run dev`; раздел «Сценарии», черновой сценарий. Тумблер «Поднимать наверх» выключить → включить галочку у строки в середине списка → строка остаётся на месте, без анимации прыжка. Тумблер включить → включить другую строку → уезжает наверх одним плавным движением.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/hooks/usePlanning.ts
git commit -m "fix(planning): при выключенном «Поднимать наверх» строка не прыгает" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 1.2 + 1.3 — авто-название сценария и команда из глобального фильтра

**Files:**
- Modify: `frontend/src/components/planning/ScenarioCreateModal.tsx`

- [ ] **Step 1: Импорты**

Заменить первую строку и добавить хук фильтра:

```ts
import { useEffect, useRef } from 'react';
import { App, Form, Input, InputNumber, Modal, Select } from 'antd';
import { useCreateScenario } from '../../hooks/usePlanning';
import { useQuarterYear } from '../../hooks/useQuarterYear';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { TeamSelector } from './TeamSelector';
import { trackAction } from '../../lib/usage/track';
```

- [ ] **Step 2: Функция имени** — после `TeamSelectorFormItem`:

```ts
/** Авто-название: «2026 Q4 Команда 1С (ERP - Товарный учет)»; без команды — «2026 Q4». */
function buildScenarioName(year?: number, quarter?: number, team?: string | null): string {
  const base = `${year ?? ''} Q${quarter ?? ''}`.trim();
  return team ? `${base} ${team}` : base;
}
```

- [ ] **Step 3: Состояние и эффект открытия**

В теле `ScenarioCreateModal` заменить блок `useEffect` на:

```ts
  const { selectedTeams } = useGlobalTeamFilter();
  // Ровно одна команда в глобальном фильтре — подставляем её в поле «Команда».
  const globalTeam = selectedTeams.length === 1 ? selectedTeams[0] : undefined;
  // Пользователь правил название руками — дальше не перезаписываем.
  // Ref, а не state: перерисовка не нужна, а setState в эффекте запрещён линтером.
  const nameTouchedRef = useRef(false);

  useEffect(() => {
    if (!open) return;
    nameTouchedRef.current = false;
    form.resetFields();
    const y = Number(year);
    const q = Number(quarter);
    form.setFieldsValue({
      year: y,
      quarter: q,
      team: globalTeam,
      name: buildScenarioName(y, q, globalTeam),
    });
  }, [open, year, quarter, globalTeam, form]);

  const handleValuesChange = (changed: Partial<FormValues>, all: FormValues) => {
    if ('name' in changed) {
      nameTouchedRef.current = true;
      return;
    }
    if (nameTouchedRef.current) return;
    if ('year' in changed || 'quarter' in changed || 'team' in changed) {
      form.setFieldValue('name', buildScenarioName(all.year, all.quarter, all.team));
    }
  };
```

(`setFieldsValue` / `setFieldValue` не вызывают `onValuesChange` — флаг «имя тронуто» ставится только от ввода пользователя.)

- [ ] **Step 4: Подключить обработчик и подсказку**

В `<Form ...>` добавить `onValuesChange={handleValuesChange}`:

```tsx
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        onValuesChange={handleValuesChange}
      >
```

Плейсхолдер поля «Название»: `<Input placeholder="Например: 2026 Q4 Команда" />`.

- [ ] **Step 5: Сборка и линтер**

Run (в `frontend/`): `npm run build` → Expected: OK.
Run: `npx eslint src/components/planning/ScenarioCreateModal.tsx` → Expected: без ошибок.

- [ ] **Step 6: Ручная проверка**

1. В шапке выбрана одна команда → «Новый сценарий»: команда подставлена, название «2026 Q4 <команда>».
2. Сменить квартал → название меняется на «2026 Q1 <команда>»; сменить команду → меняется.
3. Отредактировать название руками, затем сменить квартал → название не меняется.
4. Закрыть и открыть заново → снова авто-название.
5. В шапке ноль или несколько команд → поле «Команда» пустое, название «2026 Q4».

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/components/planning/ScenarioCreateModal.tsx
git commit -m "feat(planning): авто-название сценария и команда из фильтра шапки" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 1.4 — переименование сценария в шапке

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx` (импорт antd стр. 6–8; обработчик рядом с `handleTeamChange` ~стр. 613; шапка ~стр. 713–715)

- [ ] **Step 1: Импорт `Typography`**

```ts
import {
  Alert, App, Badge, Button, Card, Popconfirm, Select, Space, Switch, Tooltip, Typography,
} from 'antd';
```

- [ ] **Step 2: Обработчик** — сразу после `handleTeamChange`:

```ts
  // Enter/потеря фокуса — сохранить; Esc AntD отменяет сам. Пустое и
  // неизменённое имя не отправляем. Разрешено и для утверждённого сценария.
  const handleRename = (next: string) => {
    const name = next.trim();
    if (!scenarioId || !name || name === scenario?.name) return;
    updateScenario.mutate(
      { id: scenarioId, data: { name } },
      { onError: (e) => notification.error({ title: 'Не удалось переименовать', description: (e as Error).message }) },
    );
  };
```

- [ ] **Step 3: Шапка**

Заменить:

```tsx
                <span style={{ fontSize: 18, fontWeight: 600, color: DARK_THEME.textPrimary }}>
                  {scenario.name}
                </span>
```

на:

```tsx
                <Typography.Text
                  editable={{
                    onChange: handleRename,
                    tooltip: 'Переименовать',
                    maxLength: 200,
                  }}
                  style={{ fontSize: 18, fontWeight: 600, color: DARK_THEME.textPrimary, margin: 0 }}
                >
                  {scenario.name}
                </Typography.Text>
```

Список сценариев в выпадающем выборе обновится сам: `useUpdateScenario` инвалидирует `['planning', 'scenarios']`.

- [ ] **Step 4: Сборка и линтер**

Run (в `frontend/`): `npm run build` → OK. `npx eslint src/pages/PlanningPage.tsx` → без новых ошибок.

- [ ] **Step 5: Ручная проверка**

Карандаш рядом с названием → ввести новое имя → Enter: имя в шапке и в выпадающем списке сценариев обновилось. Esc — старое имя. Стереть всё и Enter — имя не меняется, запрос не уходит (вкладка «Сеть»). Утверждённый сценарий переименовывается так же.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): переименование сценария прямо в шапке" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 1.5 (фронт) — правка плана из «Параметров планирования» видит свежие и Jira-значения

**Files:**
- Modify: `frontend/src/types/api.ts` (интерфейс ответа бэклога, после `duration_launch_days_jira`, ~стр. 531)
- Modify: `frontend/src/components/backlog/BacklogPlanningParamsModal.tsx`

- [ ] **Step 1: Тип**

В `frontend/src/types/api.ts` после `duration_launch_days_jira: number | null;` добавить:

```ts
  // Часы по ролям из Jira без ручной правки (для «из Jira» в правке плана).
  estimate_analyst_hours_jira: number | null;
  estimate_dev_hours_jira: number | null;
  estimate_qa_hours_jira: number | null;
  estimate_opo_hours_jira: number | null;
```

- [ ] **Step 2: Свежая строка в модалке**

В `BacklogPlanningParamsModal.tsx`:
- импорт: `import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';`
- в теле компонента после `const backlogItemId = item?.id ?? '';`:

```ts
  // Проп item — снимок строки на момент открытия. Часы для правки плана берём
  // из свежего запроса: после сохранения драуэр инвалидирует ['backlog'], и
  // повторное открытие показывает уже новые значения, а не снимок.
  const { data: freshItem } = useQuery({
    queryKey: ['backlog', 'item', backlogItemId],
    queryFn: () => api.get<BacklogItemResponse>(`/backlog/${backlogItemId}`),
    enabled: open && !!backlogItemId,
  });
  const planSrc = freshItem ?? item;
```

- заменить пропсы `PlanEditDrawer`:

```tsx
          jiraValues={{
            analyst: planSrc?.estimate_analyst_hours_jira ?? null,
            dev: planSrc?.estimate_dev_hours_jira ?? null,
            qa: planSrc?.estimate_qa_hours_jira ?? null,
            opo: planSrc?.estimate_opo_hours_jira ?? null,
          }}
          effectiveValues={{
            analyst: planSrc?.estimate_analyst_hours ?? null,
            dev: planSrc?.estimate_dev_hours ?? null,
            qa: planSrc?.estimate_qa_hours ?? null,
            opo: planSrc?.estimate_opo_hours ?? null,
          }}
```

(Форму вовлечённости/длительностей оставляем на пропе `item` — иначе фоновое обновление стирало бы несохранённый ввод.)

- [ ] **Step 3: Сборка и линтер**

Run (в `frontend/`): `npm run build` → OK. `npx eslint src/components/backlog/BacklogPlanningParamsModal.tsx src/types/api.ts` → без ошибок.

- [ ] **Step 4: Ручная проверка**

Бэклог → строка инициативы с Jira-часами → «Параметры планирования» → «Редактировать план»: в колонке «из Jira» — значения Jira, «действующее» — текущие. Поменять часы разработки, сохранить: в строке списка часы и итог обновились сразу; открыть «Редактировать план» снова — видно новое значение. В «Сценариях» для этой задачи — новые часы без синка. Поправить часы прямо в ячейке строки бэклога → запустить синк задачи → значение сохранилось.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/types/api.ts frontend/src/components/backlog/BacklogPlanningParamsModal.tsx
git commit -m "fix(backlog): правка плана показывает значения из Jira и свежие часы" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 1.6 (фронт) — подпись «выбыл / пришёл» в подвале загрузки

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts` (~стр. 141–150)
- Modify: `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`

- [ ] **Step 1: Типы**

В `frontend/src/api/resourcePlanning.ts` перед `export interface EmployeeLoadOut` добавить:

```ts
/** Переход сотрудника на границе участия в команде плана внутри квартала. */
export interface TeamMove {
  /** Выбыл — первый день вне команды; пришёл — первый день в команде. */
  date: string;
  /** Команда по ту сторону границы; null — ни в одной команде. */
  team: string | null;
}
```

и в `EmployeeLoadOut` после `member_to?: string | null;`:

```ts
  left_to?: TeamMove | null;
  joined_from?: TeamMove | null;
```

- [ ] **Step 2: Форматирование** — в `EmployeeLoadHeatmap.tsx` после `isoDate`:

```ts
/** «2026-08-11» → «11.08». */
function fmtDM(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** Подпись под фамилией: откуда пришёл / куда выбыл в этом квартале. */
function moveNote(row: EmployeeLoadOut): string {
  const parts: string[] = [];
  if (row.joined_from) {
    const d = fmtDM(row.joined_from.date);
    parts.push(row.joined_from.team ? `пришёл ${d} из ${row.joined_from.team}` : `пришёл ${d}`);
  }
  if (row.left_to) {
    const d = fmtDM(row.left_to.date);
    parts.push(`выбыл ${d} → ${row.left_to.team ?? 'не в командах'}`);
  }
  return parts.join(' · ');
}

/** Текст подсказки для дня вне команды. */
function outOfTeamText(row: EmployeeLoadOut, date: string): string {
  if (row.left_to && date >= row.left_to.date) {
    return `не в команде · с ${fmtDM(row.left_to.date)} — ${row.left_to.team ?? 'не в командах'}`;
  }
  if (row.joined_from && date < row.joined_from.date) {
    return `не в команде · до ${fmtDM(row.joined_from.date)} — ${row.joined_from.team ?? 'не в командах'}`;
  }
  return 'вне команды';
}
```

- [ ] **Step 3: Подсказка дня**

`showTip` принимает строку сотрудника:

```ts
  const showTip = (e: React.MouseEvent, row: EmployeeLoadOut, date: string, off: Off, pct: number) => {
    const dt = isoDate(date);
    const head = `${RU_WD[dt.getDay()]}, ${dt.getDate()} ${RU_MONTHS_SHORT[dt.getMonth()]}`;
    let body: string;
    if (off === 'out_of_team') body = outOfTeamText(row, date);
    else if (off === 'absence') body = 'отпуск / отсутствие';
    else if (off === 'holiday') body = 'праздник';
    else body = pct > 0 ? `${Math.round(pct)}%` : 'нет загрузки';
    setTip({ x: e.clientX, y: e.clientY, text: `${head} · ${body}` });
  };
```

и в клетке дня: `onMouseEnter={(e) => showTip(e, row, cell.date, off, pct)}`.

- [ ] **Step 4: Подпись под фамилией**

В `orderedRows.map(({ row, byDate, avg, allEmpty }, ri) => {` после `const avgColor = loadColor(avg);` добавить `const note = moveNote(row);`.

Высота строки: в контейнере строки `height: ROW_H` → `height: note ? ROW_H + 12 : ROW_H`.

Заменить `<span>` с фамилией:

```tsx
                  <span
                    style={{
                      fontSize: 12,
                      color: '#fff',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {row.employee_name ?? row.employee_id}
                  </span>
```

на:

```tsx
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span
                      style={{
                        fontSize: 12,
                        color: '#fff',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {row.employee_name ?? row.employee_id}
                    </span>
                    {note && (
                      <span
                        title={note}
                        style={{
                          fontSize: 10,
                          color: '#e0a84a',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {note}
                      </span>
                    )}
                  </div>
```

(Цвет подписи — янтарный, как штриховка «вне команды».)

- [ ] **Step 5: Сборка и линтер**

Run (в `frontend/`): `npm run build` → OK. `npx eslint src/components/resource-planning/EmployeeLoadHeatmap.tsx src/api/resourcePlanning.ts` → без ошибок.

- [ ] **Step 6: Ручная проверка**

«Ресурсный план» команды, где сотрудник выбыл в середине квартала (или временно поставить ему дату выбытия в «Сотрудниках»): под фамилией в подвале мелко «выбыл 11.08 → <команда>»; наведение на штрихованный день после выбытия — «… · не в команде · с 11.08 — <команда>». Сотрудник с полным кварталом — без подписи, высота строки прежняя.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx
git commit -m "feat(resource-planning): в подвале видно, куда выбыл и откуда пришёл сотрудник" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Заметки «Что нового»

Источник правды — `release_notes/drafts.json` (сейчас файла нет — все черновики привязаны к v1.10.0; CLI создаст его). Категории в порядке: Новое → Улучшение → Исправление. Разделы: `scenarios`, `backlog`, `resources`.

**Files:**
- Create (через CLI): `release_notes/drafts.json`

- [ ] **Step 1: Добавить записи (именно в этом порядке)**

```bash
py -3.10 scripts/release_note.py add --type new --section scenarios --title "Сценарий можно переименовать" --description "Нажмите на карандаш рядом с названием сценария в шапке, введите новое имя и нажмите Enter. Esc отменяет правку. Работает и для утверждённых сценариев; список сценариев обновляется сразу."

py -3.10 scripts/release_note.py add --type improvement --section scenarios --title "Название нового сценария заполняется само" --description "При создании сценария название складывается из года, квартала и команды, например «2026 Q4 Команда 1С (ERP - Товарный учет)», и меняется вместе с ними, пока вы не отредактируете его вручную. Если в шапке выбрана одна команда, она сразу подставляется в поле «Команда»."

py -3.10 scripts/release_note.py add --type improvement --section resources --title "Видно, куда ушёл и откуда пришёл сотрудник" --description "В блоке «Загрузка сотрудников по дням» под фамилией человека, который сменил команду в этом квартале, появилась подпись: «выбыл 11.08 → Команда 1С (Бухгалтерия)» или «пришёл 01.10 из …». Подсказка по дню вне команды тоже показывает, где он в это время."

py -3.10 scripts/release_note.py add --type fix --section scenarios --title "Строка не прыгает при выключенном «Поднимать наверх»" --description "Если настройка «Поднимать наверх» выключена, отмеченная задача в сценарии остаётся на своём месте. Раньше она на мгновение улетала наверх и возвращалась обратно."

py -3.10 scripts/release_note.py add --type fix --section backlog --title "Ручные часы сразу видны везде" --description "Часы, исправленные вручную в «Параметрах планирования» или прямо в строке бэклога, сразу показываются в списке, в сценариях и в ресурсном плане — без ожидания синхронизации с Jira. Правка в строке больше не пропадает после синхронизации и попадает в историю изменений плана. В окне правки плана колонка «из Jira» показывает именно значения из Jira."
```

Expected: пять строк «OK: черновик добавлен в release_notes\drafts.json».

- [ ] **Step 2: Проверить файл**

Run: `py -3.10 -c "import json;d=json.load(open('release_notes/drafts.json',encoding='utf-8'));print([n['type'] for n in d['notes']])"`
Expected: `['new', 'improvement', 'improvement', 'fix', 'fix']`

- [ ] **Step 3: Коммит**

```bash
git add release_notes/drafts.json
git commit -m "docs(release-notes): заметки о быстрых правках планирования" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Финальная проверка

- [ ] **Step 1: Полный прогон бэкенда**

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: без новых падений относительно `main`.

- [ ] **Step 2: Линтеры бэкенда**

Run: `ruff check app/ tests/` и `mypy app/`
Expected: без новых ошибок в изменённых файлах.

- [ ] **Step 3: Фронт**

Run (в `frontend/`): `npm run build`
Expected: OK.

- [ ] **Step 4: Граф знаний**

Run: `graphify update .`

- [ ] **Step 5: Push**

Run: `git push origin feature/planning-q4`

---

## Самопроверка по спеке

| Пункт спеки | Задача |
|---|---|
| 1.1 условие подъёма с `lift` | Task 5 |
| 1.2 авто-название, флаг «имя тронуто», сброс при открытии, без команды — `${year} Q${quarter}` | Task 6 |
| 1.3 одна команда в глобальном фильтре → в поле | Task 6 |
| 1.4 редактируемое название, Enter/Esc, пустое не сохранять, и для утверждённых | Task 7 |
| 1.5 sync_from_issue после edit/revert/resolve_conflict + событие | Task 1, 2 |
| 1.5 инлайн-правка через PlanEditService | Task 3 |
| 1.5 модалка: «из Jira»/«действующее» из задачи, перечитывание после сохранения | Task 3 (поля), Task 8 |
| 1.5 тесты: правка через /plan меняет копию и итог; инлайн переживает синк | Task 1, 3 |
| 1.6 `left_to` / `joined_from` на бэке | Task 4 |
| 1.6 подпись под фамилией + подсказка дня | Task 9 |
| Заметки «Что нового» | Task 10 |
