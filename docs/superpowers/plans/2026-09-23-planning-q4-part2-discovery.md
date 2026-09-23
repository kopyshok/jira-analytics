# Планирование Q4 — Часть 2: Дискавери и галочка «В план» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `BacklogItem.included_in_planning` становится общей галочкой «В план» для любой целевой задачи; служебные эпики (Дискавери внутри RFA) по умолчанию не в плане, а по галочке идут в сценарий сверх родителя.

**Architecture:** В `hierarchy_rules.py` появляются два предиката поверх first-match: «служебный эпик» (первое подошедшее правило `require_parent=True, is_container=False`) и «лист планирования» (прочие явные листья). В `backlog_service.py` — множества «служебные эпики» и «не в плане», которые вычитаются во всех местах отбора кандидатов (создание сценария, досинк, self-heal раскладок, автодобавление в черновики). Переключатель — существующий `PATCH /backlog/{id}/included`, который теперь при выключении снимает задачу из черновиков. Миграция данных самодостаточна (Core-SQL, без импорта `app`).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (ORM + Core в миграции), Alembic (batch-режим не нужен — только UPDATE/DELETE), pytest; React 19 + AntD 6 + TanStack Query.

**Предпосылка:** Часть 1 (особенно 1.5 — `PlanEditService` вызывает `BacklogService.sync_from_issue`) уже влита. Часть 2 её не трогает: новое значение по умолчанию ставится только в ветке создания `BacklogItem`.

---

## Расхождения спеки с кодом (учтены в плане)

1. **Правило «Эпик внутри RFA» на реальных данных выключено.** В `data/jira_analytics.db` (копия прода) правило-сид из `hr01_rule_require_parent` имеет `is_enabled = 0`; служебных эпиков по действующим правилам сейчас нет, у 92 таких задач 9 черновых распределений. Утверждение спеки «у них сейчас нет распределений, т.к. они отфильтрованы как листья» верно только при включённом правиле. Следствия: миграция данных (Task 6) на проде сейчас ничего не изменит; при последующем включении правила задачи должны выключаться сами — добавлен Task 5 (правка правил иерархии выключает новые служебные эпики).
2. **Список целевых задач прячет явные листья целиком** (`backlog.py`, `_item_is_leaf`, около строк 576-589). При включённом правиле Дискавери не видны и дочерней строкой — «по-прежнему показываются дочерней строкой» неверно. Task 4 оставляет служебные эпики в списке только дочерней строкой видимой RFA.
3. **`RfaExpandedRow.tsx` нигде не используется** (мёртвый компонент). Дочерние строки рисует дерево таблицы в `BacklogPage.tsx` (`adaptChildren`). Колонка «В план» ставится в `BacklogPage`, `RfaExpandedRow` не трогаем (кандидат на удаление — отдельно).
4. **Спека пропускает два места отбора кандидатов:** `sync_backlog` (`planning.py` около 1323) и self-heal в `list_scenario_allocations` (около 1415) — оба через `_filter_leaf_backlog_ids`. Без правки служебный эпик с включённой галочкой не доедет до черновика, а выключенная задача вернётся self-heal'ом.
5. **Событие уже публикуется**: `set_included` шлёт `entity_changed` с `["backlog", "planning"]` и уже вызывает `_reconcile_mode`. Нужна только ветка «выключили → удалить из черновиков».
6. **Модалка «Параметры планирования»**: переключатель участия виден только у RFA с детьми в режиме «По Эпикам». Делаем его общим «В план» для любой задачи.
7. **Побочный эффект правила 1:** RFA в режиме «По Эпикам», у которой пропали все дочки, сохраняет `included_in_planning=False` и после изменения перестанет быть кандидатом (сейчас — кандидат). На текущих данных таких нет (все 3 строки с `False` — RFA с дочками), но PM увидит её приглушённой и сможет включить.

---

## File map

| Файл | Что меняется |
|---|---|
| `app/services/hierarchy_rules.py` | `_first_match`, `is_service_epic`, `is_planning_leaf` |
| `app/services/backlog_service.py` | `service_epic_backlog_ids`, `not_in_plan_backlog_ids`, `switch_off_new_service_epics`; `mode_excluded_backlog_ids` не исключает служебные эпики; `sync_from_issue` ставит `False` новым служебным эпикам; `_ensure_draft_allocations` пропускает «не в плане» |
| `app/api/endpoints/planning.py` | Листья через `is_planning_leaf`; вычитание «не в плане» в `create_scenario`, `sync_backlog`, self-heal |
| `app/api/endpoints/backlog.py` | `_reconcile_mode` снимает из черновиков выключенные; список показывает служебные эпики дочерней строкой |
| `app/api/endpoints/hierarchy_rules.py` | create/update/delete/reorder выключают задачи, ставшие служебными эпиками |
| `alembic/versions/pq01_service_epic_off_plan.py` | Новая миграция данных |
| `frontend/src/api/backlog.ts`, `frontend/src/hooks/useBacklog.ts` | `setBacklogIncluded`, `useSetBacklogIncluded` |
| `frontend/src/pages/BacklogPage.tsx`, `frontend/src/index.css` | Колонка «В план», приглушённая строка, метка-фильтр «Не в плане · N» |
| `frontend/src/components/backlog/BacklogPlanningParamsModal.tsx` | Общий переключатель «В план» |
| `docs/help/backlog.md` | Абзац про «В план» |
| `release_notes/drafts.json` | Черновики «Что нового» (через CLI) |
| Тесты | `tests/test_service_epic_rules.py`, `tests/test_backlog_in_plan_flag.py`, `tests/test_api_in_plan_candidates.py`, `tests/test_hierarchy_rules_switch_off.py`, `tests/test_migration_pq01_service_epic_off_plan.py` |

Все команды — из корня `D:\ClaudeDev\JiraAnalysis`. Полный прогон всегда с `--ignore=tests/api/test_llm.py` (висит без сети).

---

### Task 1: Предикаты «служебный эпик» и «лист планирования»

**Files:**
- Modify: `app/services/hierarchy_rules.py`
- Test: `tests/test_service_epic_rules.py` (create)

- [ ] **Step 1: Write the failing test**

`tests/test_service_epic_rules.py`:

```python
"""Служебный эпик = первое подошедшее правило «только с родителем» и «не контейнер».

Прочие явные листья (OS/PMD) — «листья планирования»: никогда не кандидаты.
Служебный эпик листом планирования НЕ считается — его решает галочка «В план».
"""
from app.models.hierarchy_rule import HierarchyRule
from app.services.hierarchy_rules import is_planning_leaf, is_service_epic


def _rule(**kw) -> HierarchyRule:
    base = dict(
        priority=10, project_key=None, issue_type=None,
        require_no_parent=False, require_parent=False,
        is_container=True, is_enabled=True,
    )
    base.update(kw)
    return HierarchyRule(**base)


SERVICE = _rule(priority=5, project_key="RFA", issue_type="Эпик", require_parent=True, is_container=False)
RFA_CONTAINER = _rule(priority=10, project_key="RFA", is_container=True)
OS_LEAF = _rule(priority=100, project_key="OS", is_container=False)
RULES = [SERVICE, RFA_CONTAINER, OS_LEAF]


def test_epic_inside_rfa_is_service_epic_not_planning_leaf():
    assert is_service_epic(RULES, "RFA", "Эпик", True) is True
    assert is_planning_leaf(RULES, "RFA", "Эпик", True) is False


def test_root_rfa_epic_is_not_service_epic():
    # Без родителя правило «только с родителем» не подходит — срабатывает контейнер RFA.
    assert is_service_epic(RULES, "RFA", "Эпик", False) is False
    assert is_planning_leaf(RULES, "RFA", "Эпик", False) is False


def test_os_task_is_planning_leaf_not_service_epic():
    assert is_planning_leaf(RULES, "OS", "Задача", True) is True
    assert is_service_epic(RULES, "OS", "Задача", True) is False


def test_first_match_wins_container_rule_with_higher_priority():
    rules = [_rule(priority=1, project_key="RFA", issue_type="Эпик", is_container=True), SERVICE]
    assert is_service_epic(rules, "RFA", "Эпик", True) is False


def test_no_rule_matched_is_neither():
    assert is_service_epic([], "X", "Y", True) is False
    assert is_planning_leaf([], "X", "Y", True) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_service_epic_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_planning_leaf'`

- [ ] **Step 3: Write minimal implementation**

В `app/services/hierarchy_rules.py` заменить `from typing import List` на:

```python
from typing import List, Optional
```

В конец файла (после `is_explicit_leaf`, её не трогаем) добавить:

```python
def _first_match(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> Optional[HierarchyRule]:
    """Первое подошедшее правило (first-match-wins) или None."""
    inp = EvaluationInput(
        project_key=project_key or "",
        issue_type=issue_type or "",
        has_parent=has_parent,
    )
    for rule in rules:
        if matches(rule, inp):
            return rule
    return None


def is_service_epic(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> bool:
    """Служебный эпик: первое подошедшее правило — «только с родителем» и «не контейнер».

    Сейчас это авто-Discovery внутри RFA. Инициативой не считается, но в
    сценарий может пойти по галочке «В план» — его часы идут сверх родителя.
    """
    rule = _first_match(rules, project_key, issue_type, has_parent)
    return rule is not None and bool(rule.require_parent) and not rule.is_container


def is_planning_leaf(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> bool:
    """Явный лист, который никогда не кандидат в сценарий (OS/PMD и т.п.).

    Служебные эпики сюда не входят: их участие решает галочка «В план».
    """
    rule = _first_match(rules, project_key, issue_type, has_parent)
    return rule is not None and not rule.is_container and not rule.require_parent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/test_service_epic_rules.py tests/test_hierarchy_rules_service.py -v`
Expected: PASS (все)

- [ ] **Step 5: Commit**

```bash
git add app/services/hierarchy_rules.py tests/test_service_epic_rules.py
git commit -m "feat(planning): признак служебного эпика в правилах иерархии" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Бэклог-сервис — «не в плане», служебные эпики, значение по умолчанию

**Files:**
- Modify: `app/services/backlog_service.py` (импорты; `mode_excluded_backlog_ids` ~222-258; `sync_from_issue` ~301-387; `_ensure_draft_allocations` ~389-453)
- Test: `tests/test_backlog_in_plan_flag.py` (create)

- [ ] **Step 1: Write the failing test**

`tests/test_backlog_in_plan_flag.py`:

```python
"""Галочка «В план» на уровне BacklogService.

Служебный эпик (Дискавери внутри RFA) создаётся выключенным и не попадает в
черновики; обычная задача — включённой. В режиме «RFA целиком» дети RFA
исключаются, но служебный эпик — нет (его часы сверх родителя).
"""
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import (
    BacklogService,
    mode_excluded_backlog_ids,
    not_in_plan_backlog_ids,
    service_epic_backlog_ids,
)


def _seed(db, *, rule_enabled: bool = True) -> None:
    db.add_all([
        HierarchyRule(
            priority=5, project_key="RFA", issue_type="Эпик",
            require_no_parent=False, require_parent=True,
            is_container=False, is_enabled=rule_enabled, description="svc",
        ),
        HierarchyRule(
            priority=10, project_key="RFA", issue_type=None,
            require_no_parent=False, require_parent=False,
            is_container=True, is_enabled=True,
        ),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-story", key="RFA-3", jira_issue_id="j3", summary="Часть RFA", issue_type="История",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        PlanningScenario(id="s-draft", name="draft", year=2026, quarter="Q4", status="draft", team="T1"),
    ])
    db.flush()


def _sync_all(db) -> dict[str, BacklogItem]:
    svc = BacklogService(db)
    for iid in ("i-rfa", "i-disc", "i-story"):
        svc.sync_from_issue(db.get(Issue, iid))
    db.flush()
    return {bi.issue_id: bi for bi in db.query(BacklogItem).all()}


def _draft_alloc_count(db, item_id: str) -> int:
    return db.query(ScenarioAllocation).filter_by(scenario_id="s-draft", backlog_item_id=item_id).count()


def test_new_service_epic_is_off_and_not_in_draft(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    assert items["i-disc"].included_in_planning is False
    assert items["i-rfa"].included_in_planning is True
    assert _draft_alloc_count(db_session, items["i-disc"].id) == 0
    assert _draft_alloc_count(db_session, items["i-rfa"].id) == 1


def test_disabled_rule_means_no_service_epic(db_session):
    _seed(db_session, rule_enabled=False)
    items = _sync_all(db_session)
    assert items["i-disc"].included_in_planning is True
    assert service_epic_backlog_ids(db_session) == set()


def test_service_epic_not_excluded_by_whole_mode(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    excluded = mode_excluded_backlog_ids(db_session)
    assert items["i-disc"].id not in excluded, "Дискавери идёт сверх RFA"
    assert items["i-story"].id in excluded, "обычный ребёнок RFA целиком — исключён"


def test_not_in_plan_set_and_ensure_skips_it(db_session):
    _seed(db_session)
    items = _sync_all(db_session)
    assert not_in_plan_backlog_ids(db_session) == {items["i-disc"].id}
    BacklogService(db_session)._ensure_draft_allocations(items["i-disc"].id)
    assert _draft_alloc_count(db_session, items["i-disc"].id) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_backlog_in_plan_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'not_in_plan_backlog_ids'`

- [ ] **Step 3: Write minimal implementation**

3a. Импорты в `app/services/backlog_service.py`:

```python
from app.models import AppSetting, BacklogItem, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.hierarchy_rules import is_planning_leaf, is_service_epic, load_rules
```

(`is_explicit_leaf` в этом файле больше не используется — убрать из импорта.)

3b. Перед `def mode_excluded_backlog_ids` добавить:

```python
def service_epic_backlog_ids(db: Session) -> set[str]:
    """BacklogItem.id служебных эпиков (Дискавери внутри RFA) по действующим правилам."""
    rules = load_rules(db)
    if not any(r.require_parent and not r.is_container for r in rules):
        return set()
    rows = (
        db.query(BacklogItem.id, Project.key, Issue.issue_type)
        .join(Issue, BacklogItem.issue_id == Issue.id)
        .outerjoin(Project, Issue.project_id == Project.id)
        .filter(Issue.parent_id.isnot(None))
        .all()
    )
    return {
        bid
        for bid, project_key, issue_type in rows
        if is_service_epic(
            rules, project_key=project_key or "", issue_type=issue_type or "", has_parent=True
        )
    }


def not_in_plan_backlog_ids(db: Session) -> set[str]:
    """Элементы бэклога со снятой галочкой «В план» — не кандидаты ни в один сценарий."""
    return {
        bid
        for (bid,) in db.query(BacklogItem.id)
        .filter(BacklogItem.included_in_planning.is_(False))
        .all()
    }
```

3c. В `mode_excluded_backlog_ids` дополнить пункт 2 докстринга строкой
«Служебные эпики (Дискавери) не исключаются: их часы идут сверх родителя, участие решает галочка «В план».»
и заменить хвост функции:

```python
    if whole_parent_issue_ids:
        rows = (
            db.query(BacklogItem.id)
            .join(Issue, BacklogItem.issue_id == Issue.id)
            .filter(
                Issue.parent_id.in_(whole_parent_issue_ids),
                BacklogItem.archived_at.is_(None),
            )
            .all()
        )
        service_ids = service_epic_backlog_ids(db)
        excluded |= {bid for (bid,) in rows if bid not in service_ids}
    return excluded
```

3d. В `sync_from_issue`, ветка `if issue.category in TRACKED_CATEGORIES and not is_cancel_like(issue):` — заменить начало ветки до `existing.title = issue.summary`:

```python
            is_new = existing is None
            was_archived = existing is not None and existing.archived_at is not None
            # Правила иерархии нужны только когда задача появляется в бэклоге.
            # Считаем до db.add — чтобы запрос не зацепил недозаполненный элемент.
            rules: list = []
            project_key = ""
            has_parent = issue.parent_id is not None
            if is_new or was_archived:
                rules = load_rules(self.db)
                project_key = issue.project.key if issue.project else ""
            if is_new:
                existing = BacklogItem(issue_id=issue.id)
                self.db.add(existing)
                existing.opo_analyst_ratio = 0.5
                # Авто-маппинг приоритета из Jira только при создании.
                # Дальше PM управляет приоритетом вручную при планировании;
                # ресинки (approve / revert-to-draft / refresh) его не трогают.
                existing.priority = _jira_priority_to_int(issue.priority)
                # Служебный эпик (Дискавери внутри RFA) по умолчанию не в плане:
                # его часы идут сверх родителя, PM включает его сам.
                if is_service_epic(
                    rules,
                    project_key=project_key,
                    issue_type=issue.issue_type or "",
                    has_parent=has_parent,
                ):
                    existing.included_in_planning = False
```

и заменить блок после `self.db.flush()`:

```python
            if is_new or was_archived:
                # Leaf-типы (OS/PMD) не пускаем в сценарии. Служебные эпики —
                # не leaf: их отсекает галочка «В план» в _ensure_draft_allocations.
                is_leaf = is_planning_leaf(
                    rules,
                    project_key=project_key,
                    issue_type=issue.issue_type or "",
                    has_parent=has_parent,
                )
                if not is_leaf:
                    self._ensure_draft_allocations(existing.id)
            return existing
```

3e. В `_ensure_draft_allocations` — дополнить докстринг строкой «Не доливает, если у элемента снята галочка «В план».» и заменить начало тела до комментария `# Берём только draft-сценарии той же команды`:

```python
        item = self.db.query(BacklogItem).filter_by(id=item_id).one_or_none()
        # Галочка «В план» снята — задача не кандидат ни в один черновик.
        if item is not None and not item.included_in_planning:
            return
        # Skip if already included in approved scenario — нет смысла предлагать
        # уже зафиксированную в утверждённом плане инициативу повторно.
        if item_id in approved_included_backlog_ids(self.db):
            return
        # Skip RFA-родителей в режиме «по эпикам» (контекст, не кандидат).
        if item_id in mode_excluded_backlog_ids(self.db):
            return
        # Skip descendants of approved-included ancestors.
        if item is not None and item.issue_id is not None:
            issue = self.db.get(Issue, item.issue_id)
            if issue is not None and has_included_ancestor(self.db, issue):
                return
```

(Строка `item = self.db.query(BacklogItem).filter_by(id=item_id).one_or_none()` в старом месте удаляется — она переехала наверх.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_backlog_in_plan_flag.py tests/test_backlog_service.py tests/test_backlog_sync.py tests/test_backlog_child_skip.py tests/test_backlog_approved_ancestor_filter.py tests/test_planning_mode_candidates.py -v`
Expected: PASS (все)

- [ ] **Step 5: Commit**

```bash
git add app/services/backlog_service.py tests/test_backlog_in_plan_flag.py
git commit -m "feat(backlog): Дискавери создаётся вне плана и идёт сверх RFA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Кандидаты сценария — все места отбора

**Files:**
- Modify: `app/api/endpoints/planning.py` (импорты ~62-74; `_backlog_item_is_leaf` ~100-116; `_filter_leaf_backlog_ids` ~147-178; `create_scenario` ~622-633; `sync_backlog` ~1323-1356; self-heal в `list_scenario_allocations` ~1415-1440)
- Test: `tests/test_api_in_plan_candidates.py` (create)

- [ ] **Step 1: Write the failing test**

`tests/test_api_in_plan_candidates.py`:

```python
"""Галочка «В план» решает кандидатство во всех местах отбора сценария.

Покрывает тесты из спеки: служебный эпик не в черновике; включение добавляет
его сверх родителя в режиме «целиком»; выключение обычной задачи убирает её
из черновиков и не трогает утверждённые; дочки «по эпикам» с False — не кандидаты.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService
from app.services.event_bus import get_event_bus


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_rfa_with_discovery(db) -> dict[str, str]:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    db.commit()
    return {bi.issue_id: bi.id for bi in db.query(BacklogItem).all()}


def _create_scenario(client) -> str:
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q4", "year": 2026, "quarter": 4, "team": "T1"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _alloc_ids(client, sid: str) -> set[str]:
    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    return {a["backlog_item_id"] for a in r.json()}


def test_service_epic_off_is_not_candidate(client, testclient_db_session):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    sid = _create_scenario(client)
    got = _alloc_ids(client, sid)
    assert ids["i-rfa"] in got
    assert ids["i-disc"] not in got


def test_turning_service_epic_on_adds_it_on_top_of_whole_parent(client, testclient_db_session):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    sid = _create_scenario(client)
    r = client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": True})
    assert r.status_code == 200, r.text
    got = _alloc_ids(client, sid)
    assert ids["i-disc"] in got, "включённое Дискавери — в черновике"
    assert ids["i-rfa"] in got, "RFA целиком остаётся — Дискавери сверх неё"
    # Досинк сценария тоже не выкидывает его.
    r = client.post(f"/api/v1/planning/scenarios/{sid}/sync-backlog")
    assert r.status_code == 200, r.text
    assert ids["i-disc"] in {a["backlog_item_id"] for a in r.json()}


def test_turning_regular_item_off_removes_from_drafts_keeps_approved(client, testclient_db_session):
    db = testclient_db_session
    db.add(Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project"))
    db.flush()
    db.add(Issue(id="i-one", key="PRJ-1", jira_issue_id="jx", summary="Инициатива", issue_type="RFA",
                 status="Open", project_id="p1", category="initiatives_rfa", team="T1"))
    db.flush()
    BacklogService(db).sync_from_issue(db.get(Issue, "i-one"))
    db.commit()
    item_id = db.query(BacklogItem.id).filter_by(issue_id="i-one").scalar()
    sid = _create_scenario(client)
    db.add(PlanningScenario(id="s-appr", name="appr", year=2026, quarter="Q3", status="approved", team="T1"))
    db.flush()
    db.add(ScenarioAllocation(scenario_id="s-appr", backlog_item_id=item_id, included_flag=False,
                              planned_hours=0, sort_order=1.0))
    db.commit()

    r = client.patch(f"/api/v1/backlog/{item_id}/included", json={"included": False})
    assert r.status_code == 200, r.text

    assert item_id not in _alloc_ids(client, sid), "self-heal не возвращает выключенную"
    db.expire_all()
    assert db.query(ScenarioAllocation).filter_by(scenario_id="s-appr", backlog_item_id=item_id).count() == 1


def test_by_epics_child_off_is_not_candidate(client, testclient_db_session):
    db = testclient_db_session
    db.add(Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project"))
    db.flush()
    db.add_all([
        Issue(id="i-p", key="PRJ-1", jira_issue_id="jp", summary="RFA", issue_type="RFA",
              status="Open", project_id="p1", category="initiatives_rfa", team="T1"),
        Issue(id="i-c", key="PRJ-2", jira_issue_id="jc", summary="Эпик", issue_type="Epic",
              status="Open", project_id="p1", parent_id="i-p", category="initiatives_rfa", team="T1"),
    ])
    db.add_all([
        BacklogItem(id="bi-p", issue_id="i-p", title="RFA", priority=1),
        BacklogItem(id="bi-c", issue_id="i-c", title="Эпик", priority=2),
    ])
    db.commit()
    assert client.patch("/api/v1/backlog/bi-p/planning-mode", json={"mode": "by_epics"}).status_code == 200
    assert client.patch("/api/v1/backlog/bi-c/included", json={"included": False}).status_code == 200
    sid = _create_scenario(client)
    assert "bi-c" not in _alloc_ids(client, sid)


def test_toggle_publishes_backlog_and_planning(client, testclient_db_session, bus):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    bus.publish.reset_mock()
    client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": True})
    bus.publish.assert_called_once_with({"type": "entity_changed", "entities": ["backlog", "planning"]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_api_in_plan_candidates.py -v`
Expected: FAIL — минимум `test_turning_service_epic_on_adds_it_on_top_of_whole_parent` (Дискавери отсеян как лист), `test_turning_regular_item_off_removes_from_drafts_keeps_approved` (выключенная остаётся в черновике), `test_by_epics_child_off_is_not_candidate` (галочка дочки не учитывается). `test_toggle_publishes_backlog_and_planning` проходит уже сейчас — это страховка от регрессии.

- [ ] **Step 3: Write minimal implementation**

3a. Импорты в `app/api/endpoints/planning.py`:

```python
from app.services.backlog_service import (
    BACKLOG_CATEGORY,
    BacklogService,
    approved_included_backlog_ids,
    descendant_backlog_ids_of_included_ancestors,
    mode_excluded_backlog_ids,
    not_in_plan_backlog_ids,
)
```

```python
from app.services.hierarchy_rules import is_planning_leaf, load_rules
```

(Проверить `grep -n "is_explicit_leaf" app/api/endpoints/planning.py` — после 3b не должно остаться вхождений.)

3b. В `_backlog_item_is_leaf` и `_filter_leaf_backlog_ids` заменить вызов `is_explicit_leaf(` на `is_planning_leaf(` (аргументы те же). В докстринг `_backlog_item_is_leaf` добавить строку:
«Служебные эпики (Дискавери) листом не считаются — их решает галочка «В план».»

3c. `create_scenario` — после блока `mode_excluded`:

```python
    # RFA-родители в режиме «по эпикам» — контекст, не кандидаты.
    mode_excluded = mode_excluded_backlog_ids(db)
    items = [it for it in items if it.id not in mode_excluded]
    # Снятая галочка «В план» — не кандидат.
    not_in_plan = not_in_plan_backlog_ids(db)
    items = [it for it in items if it.id not in not_in_plan]
```

3d. `sync_backlog`:

```python
    mode_excluded = mode_excluded_backlog_ids(db)
    not_in_plan = not_in_plan_backlog_ids(db)
```

```python
    for item_id in ((((((current_ids - existing_ids) - leaf_ids) - descendant_ids) - approved_included_ids) - mode_excluded) - not_in_plan):
```

```python
    # Безусловный снос: потомки утверждённых, RFA-родители «по эпикам» и
    # задачи со снятой галочкой «В план» (даже если PM отметил — иначе
    # часы посчитаются дважды / задача вернётся вопреки галочке).
    stale_unconditional = existing_ids & (descendant_ids | mode_excluded | not_in_plan)
```

3e. Self-heal в `list_scenario_allocations` — то же:

```python
        # RFA-родители «по эпикам» — контекст, не кандидаты.
        mode_excluded = mode_excluded_backlog_ids(db)
        # Снятая галочка «В план» — не кандидат.
        not_in_plan = not_in_plan_backlog_ids(db)
        missing = ((((((current_ids - existing_ids) - leaf_ids) - descendant_ids) - approved_included_ids) - mode_excluded) - not_in_plan)
        # Безусловный stale: потомки утверждённых, RFA «по эпикам», «не в плане».
        stale_unconditional = existing_ids & (descendant_ids | mode_excluded | not_in_plan)
```

(Подпись self-heal `_alloc_heal_signature` уже включает `max(BacklogItem.updated_at)`, а смена галочки обновляет `updated_at` — кэш сбрасывается сам.)

- [ ] **Step 4: Run tests — they still fail on the off-toggle**

Run: `py -3.10 -m pytest tests/test_api_in_plan_candidates.py -v`
Expected: всё кроме, возможно, `test_turning_regular_item_off_removes_from_drafts_keeps_approved` — PASS. Если этот тест прошёл за счёт self-heal — всё равно выполнить Task 4 (выключение должно чистить черновики сразу, без чтения раскладок).

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_in_plan_candidates.py
git commit -m "feat(planning): галочка «В план» решает кандидатов сценария" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Переключатель и список целевых задач

**Files:**
- Modify: `app/api/endpoints/backlog.py` (импорт ~40; `list_backlog_items` ~576-589; `_reconcile_mode` ~1282-1293; `set_included` ~1335-1357)
- Test: `tests/test_api_in_plan_candidates.py` (append), `tests/test_backlog_in_plan_list.py` (create)

- [ ] **Step 1: Write the failing tests**

В конец `tests/test_api_in_plan_candidates.py`:

```python
def test_turning_off_removes_from_draft_immediately(client, testclient_db_session):
    """Без чтения раскладок: PATCH сам снимает задачу из черновиков."""
    ids = _seed_rfa_with_discovery(testclient_db_session)
    sid = _create_scenario(client)
    client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": True})
    client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": False})
    testclient_db_session.expire_all()
    assert (
        testclient_db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sid, backlog_item_id=ids["i-disc"])
        .count()
        == 0
    )
```

`tests/test_backlog_in_plan_list.py`:

```python
"""Служебный эпик в списке целевых задач — только дочерней строкой своей RFA."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, Project
from app.services.backlog_service import BacklogService


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db) -> dict[str, str]:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    db.commit()
    return {bi.issue_id: bi.id for bi in db.query(BacklogItem).all()}


def _all_ids(rows) -> set[str]:
    return {r["id"] for r in rows} | {c["id"] for r in rows for c in r.get("children", [])}


def test_service_epic_shown_as_child_row_off_plan(client, testclient_db_session):
    ids = _seed(testclient_db_session)
    rows = client.get("/api/v1/backlog", params={"view": "active"}).json()
    roots = {r["id"]: r for r in rows}
    assert ids["i-disc"] not in roots, "Дискавери — не инициатива, корнем не показывается"
    kids = {c["id"]: c for c in roots[ids["i-rfa"]]["children"]}
    assert kids[ids["i-disc"]]["included_in_planning"] is False


def test_service_epic_hidden_when_parent_not_listed(client, testclient_db_session):
    ids = _seed(testclient_db_session)
    parent = testclient_db_session.get(BacklogItem, ids["i-rfa"])
    parent.archived_at = datetime.utcnow()
    testclient_db_session.commit()
    rows = client.get("/api/v1/backlog", params={"view": "active"}).json()
    assert ids["i-disc"] not in _all_ids(rows)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/test_backlog_in_plan_list.py "tests/test_api_in_plan_candidates.py::test_turning_off_removes_from_draft_immediately" -v`
Expected: FAIL — `KeyError` на `kids[...]` (Дискавери спрятан как лист) и оставшееся распределение после выключения.

- [ ] **Step 3: Write minimal implementation**

3a. Импорт:

```python
from app.services.hierarchy_rules import is_explicit_leaf, is_service_epic, load_rules
```

3b. В `list_backlog_items` заменить блок от `# Скрываем явные leaf-типы` до `items = [it for it in items if not _item_is_leaf(it)]` включительно:

```python
    # Скрываем явные leaf-типы (HierarchyRule с is_container=False).
    # Служебные эпики (Дискавери внутри RFA) — не инициативы, но остаются
    # дочерней строкой своей RFA: у них есть галочка «В план».
    rules = load_rules(db)

    def _rule_args(it: BacklogItem) -> dict:
        issue = it.issue
        return {
            "project_key": issue.project.key if issue.project else "",
            "issue_type": issue.issue_type or "",
            "has_parent": issue.parent_id is not None,
        }

    def _item_is_leaf(it: BacklogItem) -> bool:
        if it.issue_id is None or it.issue is None:
            return False
        return is_explicit_leaf(rules, **_rule_args(it))

    service_ids = {
        it.id
        for it in items
        if it.issue_id is not None and it.issue is not None
        and is_service_epic(rules, **_rule_args(it))
    }
    items = [it for it in items if it.id in service_ids or not _item_is_leaf(it)]
    # Служебный эпик без родителя в этом же списке не показываем вовсе.
    listed_issue_ids = {
        it.issue_id for it in items if it.issue_id is not None and it.id not in service_ids
    }
    items = [
        it for it in items
        if it.id not in service_ids or it.issue.parent_id in listed_issue_ids
    ]
```

3c. `_reconcile_mode`:

```python
def _reconcile_mode(db: Session, item_id: str) -> None:
    """Синхронизировать draft-allocations элемента с режимом и галочкой «В план».

    RFA-родитель «по эпикам» (контекст) или задача со снятой галочкой — снять
    её allocations из черновиков (утверждённые не трогаем); иначе — добить
    (идемпотентно). Выравнивает существующие сценарии сразу, не дожидаясь
    self-heal при следующем открытии.
    """
    svc = BacklogService(db)
    bi = db.get(BacklogItem, item_id)
    if item_id in mode_excluded_backlog_ids(db) or (bi is not None and not bi.included_in_planning):
        svc._remove_draft_allocations(item_id)
    else:
        svc._ensure_draft_allocations(item_id)
```

3d. Докстринг `set_included`:

```python
    """Галочка «В план» для любой задачи бэклога.

    Выключили — задача не кандидат, её распределения уходят из черновых
    сценариев (утверждённые не трогаем). Включили — добавляется в черновики
    своей команды. Для RFA «по эпикам» это та же галочка «Включить саму RFA».
    """
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_backlog_in_plan_list.py tests/test_api_in_plan_candidates.py tests/test_backlog_planning_mode_api.py tests/test_backlog_hierarchy_flags.py tests/test_backlog_endpoints.py tests/test_backlog_active_view.py tests/test_api_entity_changed_backlog.py -v`
Expected: PASS (все)

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_api_in_plan_candidates.py tests/test_backlog_in_plan_list.py
git commit -m "feat(backlog): галочка «В план» снимает задачу из черновиков, Дискавери в составе RFA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Правка правил иерархии выключает новые служебные эпики

Причина: на реальных данных правило «Эпик внутри RFA» выключено (расхождение 1). Когда его включат, 60+ Дискавери с галочкой «включено» разом станут кандидатами сверх RFA. Правило: задача, которая **стала** служебным эпиком после правки правил, выключается; уже бывшие служебными не трогаются (их галочку мог поставить PM).

**Files:**
- Modify: `app/services/backlog_service.py` (новая функция в конце файла)
- Modify: `app/api/endpoints/hierarchy_rules.py` (create/update/delete/reorder)
- Test: `tests/test_hierarchy_rules_switch_off.py` (create)

- [ ] **Step 1: Write the failing test**

`tests/test_hierarchy_rules_switch_off.py`:

```python
"""Включение правила «Эпик внутри RFA» выключает галочку «В план» у ставших служебными."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db, *, rule_enabled: bool) -> tuple[str, str]:
    rule = HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                         require_parent=True, is_container=False, is_enabled=rule_enabled, description="svc")
    db.add_all([rule, Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA")])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        PlanningScenario(id="s-draft", name="draft", year=2026, quarter="Q4", status="draft", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    disc_id = db.query(BacklogItem.id).filter_by(issue_id="i-disc").scalar()
    db.commit()
    return rule.id, disc_id


def test_enabling_rule_switches_off_new_service_epics(client, testclient_db_session):
    db = testclient_db_session
    rule_id, disc_id = _seed(db, rule_enabled=False)
    db.add(ScenarioAllocation(scenario_id="s-draft", backlog_item_id=disc_id, included_flag=False,
                              planned_hours=0, sort_order=99.0))
    db.commit()
    assert db.get(BacklogItem, disc_id).included_in_planning is True

    r = client.patch(f"/api/v1/hierarchy-rules/{rule_id}", json={"is_enabled": True})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(BacklogItem, disc_id).included_in_planning is False
    assert db.query(ScenarioAllocation).filter_by(scenario_id="s-draft", backlog_item_id=disc_id).count() == 0


def test_rule_edit_keeps_pm_choice_on_existing_service_epic(client, testclient_db_session):
    db = testclient_db_session
    rule_id, disc_id = _seed(db, rule_enabled=True)
    db.get(BacklogItem, disc_id).included_in_planning = True  # PM включил сам
    db.commit()

    r = client.patch(f"/api/v1/hierarchy-rules/{rule_id}", json={"description": "Дискавери"})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(BacklogItem, disc_id).included_in_planning is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_switch_off.py -v`
Expected: FAIL в `test_enabling_rule_switches_off_new_service_epics` (`assert True is False`).

- [ ] **Step 3: Write minimal implementation**

3a. В конец `app/services/backlog_service.py` (после класса `BacklogService`):

```python
def switch_off_new_service_epics(db: Session, before: set[str]) -> set[str]:
    """Задачи, ставшие служебными эпиками после правки правил иерархии, —
    снять галочку «В план» и убрать из черновых сценариев.

    ``before`` — ``service_epic_backlog_ids`` до правки. Уже бывшие служебными
    не трогаем: их галочку PM мог поставить сам.
    """
    newly = service_epic_backlog_ids(db) - before
    if not newly:
        return newly
    svc = BacklogService(db)
    for bid in newly:
        item = db.get(BacklogItem, bid)
        if item is not None:
            item.included_in_planning = False
        svc._remove_draft_allocations(bid)
    db.flush()
    return newly
```

3b. В `app/api/endpoints/hierarchy_rules.py` импорт:

```python
from app.services.backlog_service import service_epic_backlog_ids, switch_off_new_service_epics
```

и четыре эндпоинта — снимок до правки, выключение после:

```python
@router.post("", response_model=HierarchyRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(body: HierarchyRuleCreate, db: Session = Depends(get_db)):
    _check_parent_predicates(body.require_no_parent, body.require_parent)
    before = service_epic_backlog_ids(db)
    repo = BaseRepository(HierarchyRule, db)
    rule = repo.create(body.model_dump())
    switch_off_new_service_epics(db, before)
    db.commit()
    return rule
```

```python
    before = service_epic_backlog_ids(db)
    for field, value in changes.items():
        setattr(rule, field, value)
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
    db.refresh(rule)
    return rule
```

```python
    before = service_epic_backlog_ids(db)
    db.delete(rule)
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
    return {"status": "deleted"}
```

```python
def reorder_rules(body: ReorderRequest, db: Session = Depends(get_db)):
    before = service_epic_backlog_ids(db)
    for index, rule_id in enumerate(body.ids):
        rule = db.get(HierarchyRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Правило {rule_id} не найдено")
        rule.priority = (index + 1) * 10
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
```

(в `update_rule` строка `before = ...` ставится после `_check_parent_predicates(...)`; в `delete_rule` — после проверки 404.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_hierarchy_rules_switch_off.py tests/test_hierarchy_rules_service.py -v`
Expected: PASS

(Не гонять здесь `tests/test_hierarchy_rules_endpoints.py` отдельно от полного прогона — у него своя фикстура БД; см. память о загрязнении dev-базы. Он пройдёт в полном прогоне Task 9.)

- [ ] **Step 5: Commit**

```bash
git add app/services/backlog_service.py app/api/endpoints/hierarchy_rules.py tests/test_hierarchy_rules_switch_off.py
git commit -m "feat(settings): включение правила «Эпик внутри RFA» выключает Дискавери из плана" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Миграция данных — существующие служебные эпики вне плана

**Files:**
- Create: `alembic/versions/pq01_service_epic_off_plan.py`
- Test: `tests/test_migration_pq01_service_epic_off_plan.py` (create)

- [ ] **Step 1: Проверить голову цепочки**

Run: `py -3.10 -m alembic heads`
Expected: `td06a_issue_sprint_release (head)`. Если Часть 1 добавила миграцию — взять её ревизию в `down_revision` ниже.

- [ ] **Step 2: Write the failing test**

`tests/test_migration_pq01_service_epic_off_plan.py`:

```python
"""pq01: существующие служебные эпики получают «не в плане» и уходят из черновиков."""
import importlib.util
from pathlib import Path

from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "pq01_service_epic_off_plan.py"
    spec = importlib.util.spec_from_file_location("migration_pq01", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _BindOp:
    """Подмена alembic.op: миграции нужен только get_bind()."""

    def __init__(self, connection):
        self._connection = connection

    def get_bind(self):
        return self._connection


def _seed(db, *, rule_enabled: bool) -> None:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=rule_enabled, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa"),
        Issue(id="i-story", key="RFA-3", jira_issue_id="j3", summary="История", issue_type="История",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa"),
        PlanningScenario(id="s-draft", name="d", year=2026, quarter="Q4", status="draft"),
        PlanningScenario(id="s-appr", name="a", year=2026, quarter="Q3", status="approved"),
    ])
    db.flush()
    db.add_all([
        BacklogItem(id="bi-rfa", issue_id="i-rfa", title="RFA"),
        BacklogItem(id="bi-disc", issue_id="i-disc", title="Дискавери"),
        BacklogItem(id="bi-story", issue_id="i-story", title="История"),
    ])
    db.flush()
    db.add_all([
        ScenarioAllocation(scenario_id="s-draft", backlog_item_id="bi-disc", included_flag=False,
                           planned_hours=0, sort_order=1.0),
        ScenarioAllocation(scenario_id="s-appr", backlog_item_id="bi-disc", included_flag=True,
                           planned_hours=0, sort_order=1.0),
    ])
    db.commit()


def _run_upgrade(db) -> None:
    module = _load_migration()
    module.op = _BindOp(db.connection())
    module.upgrade()
    db.commit()
    db.expire_all()


def test_upgrade_switches_off_service_epics_only(db_session):
    _seed(db_session, rule_enabled=True)
    _run_upgrade(db_session)
    assert db_session.get(BacklogItem, "bi-disc").included_in_planning is False
    assert db_session.get(BacklogItem, "bi-rfa").included_in_planning is True
    assert db_session.get(BacklogItem, "bi-story").included_in_planning is True
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 0
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-appr").count() == 1


def test_upgrade_noop_when_rule_disabled(db_session):
    _seed(db_session, rule_enabled=False)
    _run_upgrade(db_session)
    assert db_session.get(BacklogItem, "bi-disc").included_in_planning is True
    assert db_session.query(ScenarioAllocation).filter_by(scenario_id="s-draft").count() == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/test_migration_pq01_service_epic_off_plan.py -v`
Expected: FAIL — `FileNotFoundError` (файла миграции нет).

- [ ] **Step 4: Write the migration**

`alembic/versions/pq01_service_epic_off_plan.py`:

```python
"""Служебные эпики (Дискавери внутри RFA) по умолчанию не в плане

Revision ID: pq01_service_epic_off_plan
Revises: td06a_issue_sprint_release
Create Date: 2026-09-23

Самодостаточна: не импортирует код приложения, только Core-SQL.
Правило first-match повторяет app/services/hierarchy_rules.py на дату миграции.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "pq01_service_epic_off_plan"
down_revision: Union[str, None] = "td06a_issue_sprint_release"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_rules = sa.table(
    "hierarchy_rule",
    sa.column("priority", sa.Integer),
    sa.column("created_at", sa.DateTime),
    sa.column("project_key", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("require_no_parent", sa.Boolean),
    sa.column("require_parent", sa.Boolean),
    sa.column("is_container", sa.Boolean),
    sa.column("is_enabled", sa.Boolean),
)
_items = sa.table(
    "backlog_items",
    sa.column("id", sa.String),
    sa.column("issue_id", sa.String),
    sa.column("included_in_planning", sa.Boolean),
)
_issues = sa.table(
    "issues",
    sa.column("id", sa.String),
    sa.column("project_id", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("parent_id", sa.String),
)
_projects = sa.table("projects", sa.column("id", sa.String), sa.column("key", sa.String))
_scenarios = sa.table("planning_scenarios", sa.column("id", sa.String), sa.column("status", sa.String))
_allocs = sa.table(
    "scenario_allocations",
    sa.column("scenario_id", sa.String),
    sa.column("backlog_item_id", sa.String),
)

_CHUNK = 500


def _first_match(rules, project_key: str, issue_type: str):
    """Первое подошедшее правило для задачи С родителем."""
    for r in rules:
        if r.project_key and r.project_key != project_key:
            continue
        if r.issue_type and r.issue_type != issue_type:
            continue
        if r.require_no_parent:
            continue
        return r
    return None


def upgrade() -> None:
    bind = op.get_bind()
    rules = bind.execute(
        sa.select(
            _rules.c.project_key,
            _rules.c.issue_type,
            _rules.c.require_no_parent,
            _rules.c.require_parent,
            _rules.c.is_container,
        )
        .where(_rules.c.is_enabled.is_(True))
        .order_by(_rules.c.priority.asc(), _rules.c.created_at.asc())
    ).fetchall()
    if not any(r.require_parent and not r.is_container for r in rules):
        return

    rows = bind.execute(
        sa.select(_items.c.id, _projects.c.key, _issues.c.issue_type)
        .select_from(
            _items.join(_issues, _items.c.issue_id == _issues.c.id)
            .outerjoin(_projects, _issues.c.project_id == _projects.c.id)
        )
        .where(_issues.c.parent_id.isnot(None))
    ).fetchall()
    ids = []
    for item_id, project_key, issue_type in rows:
        rule = _first_match(rules, project_key or "", issue_type or "")
        if rule is not None and rule.require_parent and not rule.is_container:
            ids.append(item_id)

    draft_ids = sa.select(_scenarios.c.id).where(_scenarios.c.status == "draft")
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        bind.execute(
            sa.update(_items).where(_items.c.id.in_(chunk)).values(included_in_planning=False)
        )
        bind.execute(
            sa.delete(_allocs).where(
                _allocs.c.backlog_item_id.in_(chunk),
                _allocs.c.scenario_id.in_(draft_ids),
            )
        )


def downgrade() -> None:
    # Прежнее значение галочки не сохранялось; «включено» вернёт Дискавери в
    # кандидаты сверх RFA, что хуже — оставляем как есть.
    pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.10 -m pytest tests/test_migration_pq01_service_epic_off_plan.py tests/test_migrations_fresh_db.py -v`
Expected: PASS

- [ ] **Step 6: Прогон на копии рабочей базы (не на самой базе)**

```powershell
Copy-Item data\jira_analytics.db "$env:TEMP\pq01_check.db"
$env:DATABASE_URL = "sqlite:///$($env:TEMP -replace '\\','/')/pq01_check.db"
py -3.10 -m alembic upgrade head
py -3.10 -m alembic current
Remove-Item Env:DATABASE_URL
Remove-Item "$env:TEMP\pq01_check.db"
```

Expected: `pq01_service_epic_off_plan (head)`, без ошибок. (На текущей копии правило выключено — изменений в данных не будет, это ожидаемо.)

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/pq01_service_epic_off_plan.py tests/test_migration_pq01_service_epic_off_plan.py
git commit -m "feat(db): существующие Дискавери переводятся в «не в плане»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Интерфейс — колонка «В план», приглушённая строка, метка «Не в плане · N»

Во фронте нет vitest — проверка через `npm run lint` + `npm run build` и ручной просмотр.

**Files:**
- Modify: `frontend/src/api/backlog.ts`
- Modify: `frontend/src/hooks/useBacklog.ts`
- Modify: `frontend/src/pages/BacklogPage.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: API и хук**

`frontend/src/api/backlog.ts` — после `restoreBacklogItem`:

```ts
export const setBacklogIncluded = (id: string, included: boolean) =>
  api.patch<{ id: string; included_in_planning: boolean }>(`/backlog/${id}/included`, { included });
```

`frontend/src/hooks/useBacklog.ts` — добавить `setBacklogIncluded,` в импорт из `'../api/backlog'` и в конец файла:

```ts
/** Галочка «В план»: выключенная задача не попадает в сценарии. */
export const useSetBacklogIncluded = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, included }: { id: string; included: boolean }) =>
      setBacklogIncluded(id, included),
    onSuccess: () => {
      invalidateAllBacklog(qc);
      qc.invalidateQueries({ queryKey: ['planning'] });
    },
  });
};
```

- [ ] **Step 2: Функции фильтра в `BacklogPage.tsx`**

После `groupByQuarterLabel` (до `export default function BacklogPage`):

```tsx
/** Только строки «не в плане»: выключенный родитель — со всеми дочками,
 *  включённый — только с выключенными дочками. */
function filterOffPlan(rows?: BacklogItemResponse[]): BacklogItemResponse[] | undefined {
  return rows?.flatMap((r) => {
    if (!r.included_in_planning) return [r];
    const kids = (r.children ?? []).filter((c) => !c.included_in_planning);
    return kids.length ? [{ ...r, children: kids }] : [];
  });
}

function countOffPlan(rows?: BacklogItemResponse[]): number {
  return (rows ?? []).reduce(
    (n, r) =>
      n + (r.included_in_planning ? 0 : 1)
      + (r.children ?? []).filter((c) => !c.included_in_planning).length,
    0,
  );
}

const offPlanRowClass = (r: BacklogItemResponse) =>
  r.included_in_planning === false ? 'backlog-row-off-plan' : '';
```

- [ ] **Step 3: Колонка, состояние фильтра, приглушение**

3a. В импорт `antd` добавить `Switch`; в импорт из `'../hooks/useBacklog'` добавить `useSetBacklogIncluded`.

3b. Рядом с `const restore = useRestoreBacklogItem();`:

```tsx
  const setIncluded = useSetBacklogIncluded();
  const [onlyOffPlan, setOnlyOffPlan] = useState(false);
```

3c. После `const quarterlyRows = useMemo(...)`:

```tsx
  const activeShown = onlyOffPlan ? filterOffPlan(activeRows) : activeRows;
  const quarterlyShown = onlyOffPlan ? filterOffPlan(quarterlyRows) : quarterlyRows;
  const offPlanCount = countOffPlan(
    view === 'quarterly' ? quarterlyRows : view === 'active' ? activeRows : undefined,
  );
```

3d. Перед `const quarterlyColumns = [`:

```tsx
  const inPlanColumn = {
    title: 'В план',
    key: 'in_plan',
    width: 80,
    align: 'center' as const,
    className: 'backlog-in-plan-cell',
    render: (_: unknown, r: BacklogItemResponse) => (
      <Tooltip title={r.included_in_planning ? 'Попадает в сценарии' : 'Не попадает в сценарии'}>
        <Switch
          size="small"
          checked={r.included_in_planning}
          loading={setIncluded.isPending && setIncluded.variables?.id === r.id}
          disabled={!!r.planning_mode_locked && !r.included_in_planning}
          onChange={(val) =>
            setIncluded.mutate(
              { id: r.id, included: val },
              { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
            )}
        />
      </Tooltip>
    ),
  };
```

3e. `quarterlyColumns`: вставить `inPlanColumn,` непосредственно перед объектом `{ title: 'Действия', key: 'actions', ... }`.

3f. `activeTable`:

```tsx
  const activeTable = (
    <Table<BacklogItemResponse>
      dataSource={activeShown}
      rowKey="id"
      loading={active.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1400 }}
      rowClassName={offPlanRowClass}
      columns={[
        ...baseColumns(true),
        inPlanColumn,
        { title: 'Действия', width: 210, fixed: 'right' as const, render: (_, r) => actionsActive(r) },
      ]}
      expandable={nestedExpandable}
    />
  );
```

3g. `quarterlyTable`: заменить `groupByQuarterLabel(quarterlyRows ?? [])` на `groupByQuarterLabel(quarterlyShown ?? [])`, `dataSource={quarterlyRows}` (таблица без группировки) на `dataSource={quarterlyShown}`, и всем трём `<Table<BacklogItemResponse>` внутри `quarterlyTable` добавить `rowClassName={offPlanRowClass}`.

3h. У `<Tabs activeKey={view} ...>` добавить проп (метка-фильтр справа от вкладок; в архиве её нет):

```tsx
        tabBarExtraContent={
          view !== 'archived' && (offPlanCount > 0 || onlyOffPlan) ? (
            <Tag.CheckableTag checked={onlyOffPlan} onChange={setOnlyOffPlan}>
              Не в плане · {offPlanCount}
            </Tag.CheckableTag>
          ) : null
        }
```

Счётчики во вкладках (`Бэклог (N)`, `Активные (N)`) остаются по полному списку — не трогать.

- [ ] **Step 4: Стиль приглушённой строки**

`frontend/src/index.css` — после блока `.capacity-team-row td { ... }`:

```css
/* Целевые задачи: задача не в плане — содержимое строки приглушено,
   переключатель «В план» остаётся ярким. Прозрачность на содержимом,
   а не на ячейке: у закреплённых колонок фон ячейки должен остаться плотным. */
.backlog-row-off-plan > td:not(.backlog-in-plan-cell) > * {
  opacity: 0.45;
}
```

- [ ] **Step 5: Lint + build**

```powershell
cd frontend
npm run lint
npm run build
cd ..
```

Expected: оба без ошибок.

- [ ] **Step 6: Ручная проверка**

Запустить бэкенд (`uvicorn app.main:app --port 8000`) и фронт (`cd frontend; npm run dev`), открыть «Целевые задачи»:
- у каждой строки и у дочерних строк RFA есть переключатель «В план»;
- выключение приглушает строку, но оставляет её в списке; справа от вкладок появляется «Не в плане · N»;
- клик по метке оставляет только такие строки; повторный — возвращает всё;
- в черновом сценарии той же команды выключенная задача пропала, включённая — появилась.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/backlog.ts frontend/src/hooks/useBacklog.ts frontend/src/pages/BacklogPage.tsx frontend/src/index.css
git commit -m "feat(backlog): колонка «В план» и фильтр «Не в плане» в целевых задачах" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Модалка «Параметры планирования» и справка

**Files:**
- Modify: `frontend/src/components/backlog/BacklogPlanningParamsModal.tsx`
- Modify: `docs/help/backlog.md`

- [ ] **Step 1: Общий переключатель в модалке**

Импорт `antd`: убрать `Checkbox`, добавить `Switch`:

```tsx
import { App, Button, Col, Divider, InputNumber, Modal, Radio, Row, Space, Switch, Tag, Typography } from 'antd';
```

Удалить блок (внутри `{hasChildren && (...)}`):

```tsx
                {mode === 'by_epics' && !modeLocked && (
                  <Checkbox
                    checked={included}
                    onChange={(e) => changeIncluded(e.target.checked)}
                  >
                    Включить саму RFA (для непокрытых кварталов)
                  </Checkbox>
                )}
```

Сразу после вводного `<Typography.Paragraph type="secondary" ...>...</Typography.Paragraph>` (перед первым `<Divider style={{ margin: '8px 0 16px' }} />`) вставить:

```tsx
        <Space style={{ marginBottom: 8 }}>
          <Switch
            checked={included}
            loading={incMut.isPending}
            disabled={modeLocked && !included}
            onChange={changeIncluded}
          />
          <Typography.Text strong>В план</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {hasChildren && mode === 'by_epics'
              ? 'Включить саму RFA — для кварталов, не покрытых Эпиками'
              : 'Выключено — задача не попадает в сценарии'}
          </Typography.Text>
        </Space>
```

- [ ] **Step 2: Справка**

В `docs/help/backlog.md` перед строкой `### Мультикомандные RFA` вставить:

```markdown
### Галочка «В план»

У каждой задачи в списке — и у RFA, и у её дочерних строк — есть переключатель **«В план»**. Выключенная задача остаётся в списке (строка приглушена), но в сценарии не попадает: из черновых сценариев она сразу уходит, утверждённые не меняются. Включили обратно — задача появляется в черновых сценариях своей команды.

**Дискавери** (служебный эпик внутри RFA) по умолчанию выключен. Если его включить, его часы идут в сценарий **сверх** RFA — даже когда RFA планируется целиком.

Метка **«Не в плане · N»** справа от вкладок оставляет в списке только выключенные задачи. Тот же переключатель есть в «Параметрах планирования» (шестерёнка); для RFA «по Эпикам» он означает «включить саму RFA».
```

- [ ] **Step 3: Lint + build**

```powershell
cd frontend
npm run lint
npm run build
cd ..
```

Expected: без ошибок.

- [ ] **Step 4: Ручная проверка**

Шестерёнка у обычной инициативы — переключатель «В план» виден, выключение приглушает строку в списке. У мультикомандной RFA «по Эпикам» переключатель выключен и неактивен.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backlog/BacklogPlanningParamsModal.tsx docs/help/backlog.md
git commit -m "feat(backlog): «В план» в параметрах планирования и справке" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Полная проверка

- [ ] **Step 1: Бэкенд целиком**

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: все зелёные (или только ранее известные падения — сравнить с `git stash`-прогоном на базовом коммите, если что-то красное).

- [ ] **Step 2: Линтеры**

Run: `ruff check app/ tests/` и `mypy app/`
Expected: без новых ошибок.

- [ ] **Step 3: Postgres (память: SQLite не ловит типы и внешние ключи)**

Run: `.\scripts\run_tests_postgres.ps1 -k "in_plan or service_epic or pq01 or planning_mode or hierarchy_rules_switch"`
Expected: PASS. Особое внимание — `included_in_planning.is_(False)` и `is_enabled.is_(True)` в миграции.

- [ ] **Step 4: Граф знаний**

Run: `graphify update .`

- [ ] **Step 5: Commit** — нечего коммитить, если шаги 1-3 зелёные (граф — локальный артефакт, в git не идёт).

---

### Task 10: Черновики «Что нового»

Черновики лежат в `release_notes/drafts.json`, добавляются CLI (он сам создаст файл, если его нет). Порядок добавления = порядок показа: Новое → Улучшение → Исправление.

- [ ] **Step 1: Добавить записи**

```powershell
py -3.10 scripts/release_note.py add --type new --section backlog --title "Переключатель «В план» у каждой задачи" --description "В списке целевых задач появилась колонка «В план» — и у RFA, и у её дочерних строк. Выключенная задача остаётся в списке приглушённой, но в сценарии не попадает: из черновых сценариев она уходит сразу, утверждённые не меняются. Метка «Не в плане» справа от вкладок показывает только такие задачи."

py -3.10 scripts/release_note.py add --type improvement --section scenarios --title "Дискавери можно взять в план сверх RFA" --description "Дискавери внутри RFA теперь виден дочерней строкой и по умолчанию не в плане. Если включить его переключателем «В план», его часы попадут в сценарий в дополнение к RFA — даже когда RFA планируется целиком."

py -3.10 scripts/release_note.py add --type fix --section scenarios --title "Снятый Эпик больше не попадает в сценарий" --description "Для RFA, которую планируют по Эпикам, снятая у дочернего Эпика отметка раньше не учитывалась — Эпик всё равно оказывался в сценарии. Теперь такой Эпик в сценарий не попадает."
```

- [ ] **Step 2: Проверить файл**

Run: `py -3.10 -c "import json; d=json.load(open('release_notes/drafts.json', encoding='utf-8')); print([(n['type'], n['title']) for n in d['notes']][-3:])"`
Expected: три записи в порядке `new`, `improvement`, `fix`.

- [ ] **Step 3: Commit**

```bash
git add release_notes/drafts.json
git commit -m "docs(release-notes): заметки о переключателе «В план» и Дискавери" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review (сверка со спекой)

| Требование спеки | Задача |
|---|---|
| Правило 1: `False` → не кандидат | Task 2 (`not_in_plan_backlog_ids`, `_ensure_draft_allocations`), Task 3 (все места отбора) |
| Правило 2: служебный эпик — кандидат по галочке, сверх родителя | Task 1 (`is_service_epic`, `is_planning_leaf`), Task 2 (`mode_excluded_backlog_ids`), Task 3 |
| Правило 3: прочие явные листья — не кандидаты | Task 1 (`is_planning_leaf`), Task 3 |
| Правило 4: дети «по эпикам» с `False` не кандидаты | Task 3 (`test_by_epics_child_off_is_not_candidate`) |
| По умолчанию `False` для служебных эпиков при создании | Task 2 (`sync_from_issue`) |
| Миграция данных для существующих | Task 6 (+ Task 5 на случай позднего включения правила) |
| `set_planning_mode` без изменений | Не трогается; `tests/test_backlog_planning_mode_api.py` и `tests/test_planning_mode_candidates.py` в прогоне Task 2/4 |
| Выключили → удалить из черновых; включили → добавить; событие | Task 4 (`_reconcile_mode`), событие уже есть — тест в Task 3 |
| Дашборды/аналитика не считают служебные эпики инициативами | Не трогаются (галочка там не используется); список целевых задач — Task 4 |
| UI: колонка, приглушение, «Не в плане · N», модалка | Task 7, Task 8 |
| Тесты из спеки | Task 2, Task 3 |
