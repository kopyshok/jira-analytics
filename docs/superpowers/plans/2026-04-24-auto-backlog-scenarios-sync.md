# Автосинхронизация бэклога и черновых сценариев — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После назначения категории «Инициативы» задача автоматически появляется в Бэклоге и во всех черновых сценариях («Элементы бэклога»). Уход категории — автоматически снимает строку из черновых сценариев.

**Architecture:** Вся логика в `BacklogService.sync_from_issue` — единой точке синка, которая уже вызывается из `set_issue_category`, `batch_set_category` и `refresh-from-jira`. Добавляется работа с `ScenarioAllocation` для сценариев в статусе `draft` (approved не трогаем). Транзакция остаётся одна, commit — за вызывающим кодом.

**Tech Stack:** SQLAlchemy 2.0 ORM, pytest (backend). React 19 + TanStack Query (frontend cache invalidation).

**Spec:** [docs/superpowers/specs/2026-04-24-auto-backlog-scenarios-sync-design.md](../specs/2026-04-24-auto-backlog-scenarios-sync-design.md)

---

## Task 1: Обновить существующий тест `test_sync_archives_item_referenced_in_scenario`

Текущий тест утверждает, что после архивации элемента его allocation **сохраняется**. По новой логике allocation в черновых сценариях должен **удаляться**, а в утверждённых — сохраняться. Разнесём в два теста.

**Files:**
- Modify: `tests/test_backlog_sync.py:144-176`

- [ ] **Step 1: Заменить существующий тест на два разделённых**

Удалить целиком `test_sync_archives_item_referenced_in_scenario` (строки 144-176) и заменить на два теста:

```python
def test_sync_removes_draft_allocation_when_category_leaves(db_session, proj):
    """Архивная категория → allocation в черновом сценарии удаляется."""
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(
        id="s1", name="Q2 draft", year=2026, quarter="Q2", status="draft"
    )
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
    assert (
        db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count()
        == 0
    )


def test_sync_preserves_approved_allocation_when_category_leaves(db_session, proj):
    """Архивная категория → allocation в утверждённом сценарии не трогаем."""
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5A", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(
        id="s-appr", name="Q1 approved", year=2026, quarter="Q1", status="approved"
    )
    db_session.add(scenario)
    db_session.add(
        ScenarioAllocation(
            id="a-appr", scenario_id=scenario.id, backlog_item_id=item.id,
            included_flag=True, planned_hours=40,
        )
    )
    db_session.commit()

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(item)
    assert item.archived_at is not None
    assert (
        db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count()
        == 1
    )
```

- [ ] **Step 2: Запустить и убедиться, что эти два теста падают** (старая логика не удаляет allocation из draft, новая ещё не написана — один тест упадёт)

Run: `py -3.10 -m pytest tests/test_backlog_sync.py::test_sync_removes_draft_allocation_when_category_leaves tests/test_backlog_sync.py::test_sync_preserves_approved_allocation_when_category_leaves -v`
Expected: `test_sync_removes_draft_allocation_when_category_leaves` FAILS (текущая логика не удаляет), `test_sync_preserves_approved_allocation_when_category_leaves` PASSES (текущая логика и так не трогает).

---

## Task 2: Добавить тесты на автосоздание allocation в черновых сценариях

**Files:**
- Modify: `tests/test_backlog_sync.py` (дописать в конец)

- [ ] **Step 1: Дописать новые тесты в конец файла**

```python
def test_sync_creates_allocations_in_draft_scenarios(db_session, proj):
    """Новый элемент бэклога → allocation в каждом draft-сценарии, в approved — нет."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add_all([
        PlanningScenario(id="d1", name="Draft 1", year=2026, quarter="Q2", status="draft"),
        PlanningScenario(id="d2", name="Draft 2", year=2026, quarter="Q3", status="draft"),
        PlanningScenario(id="a1", name="Approved 1", year=2026, quarter="Q1", status="approved"),
    ])
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N1", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    allocations = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).all()
    scenario_ids = {a.scenario_id for a in allocations}
    assert scenario_ids == {"d1", "d2"}
    for a in allocations:
        assert a.included_flag is False
        assert a.planned_hours == 0


def test_sync_preserves_existing_allocation_values(db_session, proj):
    """Если в черновике уже есть allocation с проставленными значениями —
    повторный sync_from_issue не перетирает."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-keep", name="Draft keep", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N2", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    # PM включил задачу в черновик и проставил часы.
    alloc = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).one()
    alloc.included_flag = True
    alloc.planned_hours = 120
    db_session.commit()

    # Повторный sync (например, обновление часов из Jira).
    issue.planned_dev_hours = 99
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()

    db_session.refresh(alloc)
    assert alloc.included_flag is True
    assert alloc.planned_hours == 120


def test_sync_readds_allocations_on_unarchive(db_session, proj):
    """Категория вернулась в initiatives_rfa → allocations восстановлены в черновиках."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    db_session.add(
        PlanningScenario(id="d-re", name="Draft re", year=2026, quarter="Q2", status="draft")
    )
    db_session.commit()

    issue = _make_issue(db_session, proj, "RFA-N3", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1

    issue.category = "archive"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 0

    issue.category = "initiatives_rfa"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 1


def test_sync_no_draft_scenarios_is_noop(db_session, proj):
    """Нет черновых сценариев → никаких allocations не создаётся, ошибки нет."""
    from app.models import ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-N4", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert db_session.query(ScenarioAllocation).filter_by(backlog_item_id=item.id).count() == 0
```

- [ ] **Step 2: Запустить, убедиться, что все 4 новых теста падают**

Run: `py -3.10 -m pytest tests/test_backlog_sync.py -v -k "creates_allocations_in_draft or preserves_existing_allocation or readds_allocations or no_draft_scenarios"`
Expected: `test_sync_creates_allocations_in_draft_scenarios` FAIL, `test_sync_preserves_existing_allocation_values` FAIL (на счётчике allocation == 1), `test_sync_readds_allocations_on_unarchive` FAIL, `test_sync_no_draft_scenarios_is_noop` PASS.

---

## Task 3: Реализовать синхронизацию draft-allocations в `BacklogService`

**Files:**
- Modify: `app/services/backlog_service.py`

- [ ] **Step 1: Полностью переписать `backlog_service.py`**

```python
"""BacklogService — auto-population of BacklogItem from Issue with category
`initiatives_rfa` («Инициативы и RFA»).

Бэклог — пул всех задач-инициатив без привязки к кварталу. Квартальный
план собирается в сценариях отметками по элементам бэклога.

Jira — источник истины для задач-инициатив; локально не трогаются только
поля, которые PM заводит вручную: ``priority``, ``opo_analyst_ratio``,
``id``, ``created_at``.

Автосинк черновых сценариев: при создании/разархивации BacklogItem
в каждом draft-сценарии появляется ScenarioAllocation с дефолтами
(``included_flag=False``, ``planned_hours=0``); при архивации
BacklogItem allocations в draft-сценариях удаляются. Утверждённые
сценарии не трогаются.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, PlanningScenario, ScenarioAllocation


BACKLOG_CATEGORY = "initiatives_rfa"


class BacklogService:
    """Sync BacklogItem records to Issue.category.

    Caller controls the transaction: ``sync_from_issue`` делает ``flush()``,
    но не коммитит — окончательный commit должен сделать вызвавший код.
    """

    def __init__(self, db: Session):
        self.db = db

    def sync_from_issue(self, issue: Issue) -> Optional[BacklogItem]:
        """Идемпотентно выравнивает BacklogItem с Issue по текущей категории.

        - ``category == 'initiatives_rfa'`` — create-or-update, перетягивает
          Jira-поля и сбрасывает ``archived_at`` (auto-restore). При создании
          или разархивации — допроставляет allocations в draft-сценариях.
        - Иначе: если BacklogItem существует — проставляем ``archived_at=now()``
          и удаляем allocations из draft-сценариев (утверждённые — не трогаем).
          Если BacklogItem нет — ничего не делаем.
        """
        existing = (
            self.db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )

        if issue.category == BACKLOG_CATEGORY:
            is_new = existing is None
            was_archived = existing is not None and existing.archived_at is not None
            if is_new:
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
            existing.archived_at = None
            self.db.flush()
            if is_new or was_archived:
                self._ensure_draft_allocations(existing.id)
            return existing

        # Category left backlog.
        if existing is None:
            return None
        if existing.archived_at is None:
            existing.archived_at = datetime.utcnow()
            self.db.flush()
            self._remove_draft_allocations(existing.id)
        return None

    def _ensure_draft_allocations(self, item_id: str) -> None:
        """В каждом draft-сценарии, где нет allocation на этот элемент — добить.

        Идемпотентно: существующие allocation (например, с проставленными PM
        ``included_flag`` и ``planned_hours``) не трогаем.
        """
        draft_scenario_ids = [
            sid
            for (sid,) in self.db.query(PlanningScenario.id)
            .filter(PlanningScenario.status == "draft")
            .all()
        ]
        if not draft_scenario_ids:
            return
        existing_scenario_ids = {
            sid
            for (sid,) in self.db.query(ScenarioAllocation.scenario_id)
            .filter(ScenarioAllocation.backlog_item_id == item_id)
            .all()
        }
        for sid in draft_scenario_ids:
            if sid in existing_scenario_ids:
                continue
            self.db.add(
                ScenarioAllocation(
                    scenario_id=sid,
                    backlog_item_id=item_id,
                    included_flag=False,
                    planned_hours=0,
                )
            )
        self.db.flush()

    def _remove_draft_allocations(self, item_id: str) -> None:
        """Удалить allocations на этот элемент из всех draft-сценариев.

        Утверждённые сценарии не трогаем — у них уже зафиксирован состав.
        """
        draft_scenario_ids = [
            sid
            for (sid,) in self.db.query(PlanningScenario.id)
            .filter(PlanningScenario.status == "draft")
            .all()
        ]
        if not draft_scenario_ids:
            return
        self.db.query(ScenarioAllocation).filter(
            ScenarioAllocation.backlog_item_id == item_id,
            ScenarioAllocation.scenario_id.in_(draft_scenario_ids),
        ).delete(synchronize_session=False)
        self.db.flush()
```

- [ ] **Step 2: Запустить все тесты файла — должны пройти**

Run: `py -3.10 -m pytest tests/test_backlog_sync.py -v`
Expected: все тесты PASS (включая 4 новых и 2 обновлённых).

- [ ] **Step 3: Запустить связанный endpoint-тест — должен остаться зелёным**

Run: `py -3.10 -m pytest tests/test_api_issue_category_backlog_trigger.py -v`
Expected: 3 теста PASS (они работают без сценариев, поэтому новая логика на них не влияет).

---

## Task 4: Добавить endpoint-тест, что batch-category создаёт allocations в черновиках

**Files:**
- Modify: `tests/test_api_issue_category_backlog_trigger.py` (дописать в конец)

- [ ] **Step 1: Дописать тест в конец файла**

```python
def test_batch_set_category_creates_allocations_in_draft_scenarios(db_session):
    """Назначение initiatives_rfa на задачи создаёт allocations в draft-сценариях."""
    from app.models import (
        BacklogItem, Category, Issue, PlanningScenario, Project, ScenarioAllocation,
    )

    cat = Category(
        id="cat-ib-alloc",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p-alloc",
        jira_project_id="p-alloc-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    draft = PlanningScenario(
        id="s-draft-alloc", name="Draft", year=2026, quarter="Q2", status="draft"
    )
    approved = PlanningScenario(
        id="s-appr-alloc", name="Approved", year=2026, quarter="Q1", status="approved"
    )
    issues = [
        Issue(
            id=f"ia-{i}",
            jira_issue_id=f"ia-{i}-jira",
            key=f"RFA-A{i}",
            summary=f"Epic A{i}",
            issue_type="RFA",
            status="Open",
            project_id=proj.id,
            category="development",
            planned_dev_hours=float(i),
        )
        for i in range(1, 3)
    ]
    db_session.add_all([cat, proj, draft, approved, *issues])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.put(
            "/api/v1/issues/batch-category",
            json={
                "issue_ids": [i.id for i in issues],
                "category_code": "initiatives_rfa",
            },
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    items = db_session.query(BacklogItem).filter(
        BacklogItem.issue_id.in_([i.id for i in issues])
    ).all()
    assert len(items) == 2
    item_ids = [it.id for it in items]

    draft_allocations = db_session.query(ScenarioAllocation).filter(
        ScenarioAllocation.scenario_id == draft.id,
        ScenarioAllocation.backlog_item_id.in_(item_ids),
    ).all()
    assert len(draft_allocations) == 2
    for a in draft_allocations:
        assert a.included_flag is False
        assert a.planned_hours == 0

    approved_allocations = db_session.query(ScenarioAllocation).filter(
        ScenarioAllocation.scenario_id == approved.id,
    ).count()
    assert approved_allocations == 0
```

- [ ] **Step 2: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/test_api_issue_category_backlog_trigger.py::test_batch_set_category_creates_allocations_in_draft_scenarios -v`
Expected: PASS.

- [ ] **Step 3: Прогнать весь бэкенд-тестсьют, чтобы ничего не сломалось**

Run: `py -3.10 -m pytest tests/ -v`
Expected: все существующие тесты PASS (ранее падавший `test_sync_service` остаётся красным — это pre-existing, см. memory `project_capacity_overhaul_followups`).

- [ ] **Step 4: Коммит бэкенда**

```bash
git add app/services/backlog_service.py tests/test_backlog_sync.py tests/test_api_issue_category_backlog_trigger.py
git commit -m "feat(backlog): auto-sync draft scenarios on Initiatives category change"
```

---

## Task 5: Инвалидация кэшей на фронте после смены категории

**Files:**
- Modify: `frontend/src/hooks/useIssueTree.ts`

- [ ] **Step 1: Дописать инвалидацию в `useSetIssueCategory` и `useBatchSetCategory`**

Заменить содержимое файла:

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getIssueTree, setIssueCategory, setIssueInclude, batchSetCategory } from '../api/issues';

export function useIssueTree(params?: { project_keys?: string; teams?: string }) {
  return useQuery({
    queryKey: ['issues', 'tree', params],
    queryFn: ({ signal }) => getIssueTree(params, signal),
    enabled: false,
    retry: false,
  });
}

function invalidateCategoryDependents(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
  // Backlog page and any allocation/scenario view update after
  // BacklogService.sync_from_issue on the backend runs.
  qc.invalidateQueries({ queryKey: ['backlog'] });
  qc.invalidateQueries({ queryKey: ['planning'] });
}

export function useSetIssueCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, categoryCode }: { issueId: string; categoryCode: string | null }) =>
      setIssueCategory(issueId, categoryCode),
    onSuccess: () => invalidateCategoryDependents(qc),
  });
}

export function useSetIssueInclude() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, include, recursive }: { issueId: string; include: boolean; recursive?: boolean }) =>
      setIssueInclude(issueId, include, recursive),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['issues', 'tree'] }),
  });
}

export function useBatchSetCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueIds, categoryCode }: { issueIds: string[]; categoryCode: string | null }) =>
      batchSetCategory(issueIds, categoryCode),
    onSuccess: () => invalidateCategoryDependents(qc),
  });
}
```

- [ ] **Step 2: Проверить сборку и линт**

Run: `cd frontend && npm run lint && npm run build`
Expected: lint и build проходят без ошибок.

- [ ] **Step 3: Коммит фронта**

```bash
git add frontend/src/hooks/useIssueTree.ts
git commit -m "feat(frontend): refresh backlog and planning caches after category change"
```

---

## Task 6: Ручная проверка в UI

- [ ] **Step 1: Перезапустить бэкенд**

Windows PowerShell, uvicorn на :8000 иногда висит — сперва убить PID на порту, затем стартовать (см. memory `feedback_windows_uvicorn_reload`):

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
py -3.10 -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Поднять фронт**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Smoke-сценарий**

1. Открыть `/planning` — создать черновой сценарий (если ещё нет).
2. Открыть `/sync` → вкладка «Настройка категорий».
3. Загрузить задачи, выбрать одну без категории, через Select поставить «Инициативы и RFA», нажать «Сохранить».
4. Перейти на `/backlog` → задача должна появиться во вкладке «Активные» **без ручного обновления страницы**.
5. Вернуться на `/planning` → открыть черновой сценарий → секция «Элементы бэклога» → задача присутствует с непроставленной галочкой и `0` часов.
6. Если есть утверждённый сценарий — в нём задача отсутствовать (она попала туда только если была в нём заранее; новая автоматика approved не трогает).
7. Вернуться в `/sync`, поменять категорию той же задачи на «Архив» → сохранить.
8. `/backlog` — задача уходит из «Активные».
9. `/planning` черновой сценарий — задача исчезла из «Элементов бэклога».
10. Снова поставить «Инициативы и RFA» → задача возвращается в бэклог и в черновик.

- [ ] **Step 4: Запушить изменения**

```bash
git push origin main
```

---

## Out of scope (напоминание)

- Toast-уведомление «задача ушла в бэклог» — не запрошено.
- Подчистка allocations в утверждённых сценариях — явно исключено.
- UI-индикация в SyncPage, что задача помимо категории получила запись в бэклоге — не запрошено.
