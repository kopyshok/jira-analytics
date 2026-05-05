# Resource Planning Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Исправить логику исполнителей в ресурсном планировании, добавить ручное закрепление + UX-доработки на странице /resource-planning.

**Architecture:** Backend (assignment service + миграция + PATCH endpoint) + Frontend (dropdown, переносы, аватарки, контекстное меню назначения, удаление неиспользуемого тоггла).

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic batch migrations / React 19 + TS 6 + AntD 6 + TanStack Query.

---

## File Structure

**Backend:**
- Modify: `app/services/resource_planning_service.py` — переписать `_assign_employees`: analyst = assignee, ОПЭ split по `opo_analyst_ratio`, QA hours-only (employee_id=NULL), уважать `is_pinned`
- Modify: `app/models/resource_plan_assignment.py` — добавить `is_pinned: bool`
- Create: `alembic/versions/038_resource_plan_assignment_is_pinned.py` — миграция batch + index
- Modify: `app/api/endpoints/resource_planning.py` — PATCH assignment ставит `is_pinned=True`, расширить `AssignmentOut` полем `backlog_item_key` + `is_pinned`
- Test: `tests/test_resource_planning_assignment_logic.py` — покрытие новой логики ролей + pin-respect
- Test: `tests/test_resource_planning_endpoints.py` — расширить existing для нового поля key + PATCH семантики

**Frontend:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx` — удалить P50/P90 toggle, переключить «Связи» на visibility, метка копий в dropdown
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` — multi-line title + ключ задачи + аватарки на барах + контекстное меню (Popover) для смены сотрудника
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` — увеличить leftColWidth с 240 до 280
- Create: `frontend/src/components/resource-planning/EmployeeAvatar.tsx` — кружок с инициалами + цвет по роли + tooltip ФИО
- Create: `frontend/src/components/resource-planning/AssignEmployeePopover.tsx` — Popover с Select сотрудника + кнопкой пересчёта
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx` — кнопка «Показать скрытые» если есть hidden
- Modify: `frontend/src/api/resourcePlanning.ts` — расширить `AssignmentOut` (`backlog_item_key`, `is_pinned`) и `ResourcePlanOut` (label/parent_plan_id уже есть, проверить)

---

## Task 1: Backend — добавить колонку `is_pinned` в assignments

**Files:**
- Modify: `app/models/resource_plan_assignment.py`
- Create: `alembic/versions/038_resource_plan_assignment_is_pinned.py`

- [ ] **Step 1: Добавить поле в модель**

В `app/models/resource_plan_assignment.py` после `slack_days`:

```python
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", index=True
    )
```

- [ ] **Step 2: Создать миграцию**

Запустить: `py -3.10 -m alembic revision -m "resource_plan_assignment is_pinned"`
Найти файл миграции в `alembic/versions/` (новый) и заполнить:

```python
"""resource_plan_assignment is_pinned

Revision ID: 038_xxxxxxxx
Revises: 037_xxxxxxxx
"""
from alembic import op
import sqlalchemy as sa


revision = "038_xxxxxxxx"  # заменить на сгенерированный
down_revision = "037_xxxxxxxx"  # последняя head-ревизия
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("is_pinned", sa.Boolean(), server_default="0", nullable=False)
        )
        batch_op.create_index(
            "ix_resource_plan_assignments_is_pinned",
            ["is_pinned"],
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.drop_index("ix_resource_plan_assignments_is_pinned")
        batch_op.drop_column("is_pinned")
```

Replace placeholders `038_xxxxxxxx` / `037_xxxxxxxx` actual revision ids.

- [ ] **Step 3: Применить миграцию**

Run: `py -3.10 -m alembic upgrade head`
Expected: «migration 038... applied», table altered.

- [ ] **Step 4: Commit**

```bash
git add app/models/resource_plan_assignment.py alembic/versions/038*
git commit -m "feat(resource-planning): is_pinned column on assignments for manual lock"
```

---

## Task 2: Backend — логика _assign_employees: analyst from assignee, ОПЭ split, QA NULL, respect pin

**Files:**
- Modify: `app/services/resource_planning_service.py:368-420`
- Test: `tests/test_resource_planning_assignment_logic.py` (создать)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_resource_planning_assignment_logic.py`:

```python
"""Тесты ролевой логики назначения в ResourcePlanningService."""
import pytest
from datetime import date
from sqlalchemy.orm import Session

from app.models import (
    BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment, Role,
)
from app.services.resource_planning_service import ResourcePlanningService


def _make_emp(db: Session, name: str, role: str, team: str = "T1") -> Employee:
    e = Employee(name=name, role=role, team=team, is_active=True)
    db.add(e); db.commit(); db.refresh(e)
    return e


def test_analyst_assigned_from_assignee(db_session: Session):
    """Аналитик берётся из исполнителя инициативы, не greedy."""
    analyst = _make_emp(db_session, "Иванов", "analyst")
    other_analyst = _make_emp(db_session, "Сидоров", "analyst")
    item = BacklogItem(
        title="Init1",
        estimate_analyst_hours=40, estimate_dev_hours=80,
        estimate_qa_hours=20, estimate_opo_hours=10,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item); db_session.commit(); db_session.refresh(item)

    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [analyst, other_analyst])
    assert result["analyst"][item.id] == analyst.id


def test_analyst_role_pm_or_consultant_also_accepted(db_session: Session):
    """Если assignee имеет роль 'РП' или 'Консультант' — тоже годится для analyst."""
    pm = _make_emp(db_session, "Петров", "rp")
    item = BacklogItem(
        title="Init",
        estimate_analyst_hours=10, estimate_dev_hours=0,
        estimate_qa_hours=0, estimate_opo_hours=0,
        assignee_employee_id=pm.id,
    )
    db_session.add(item); db_session.commit(); db_session.refresh(item)

    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [pm])
    assert result["analyst"][item.id] == pm.id


def test_qa_employee_id_is_none(db_session: Session):
    """QA — часы только, без сотрудника."""
    dev = _make_emp(db_session, "Разраб", "developer")
    item = BacklogItem(
        title="Init",
        estimate_analyst_hours=0, estimate_dev_hours=10,
        estimate_qa_hours=20, estimate_opo_hours=0,
        assignee_employee_id=dev.id,
    )
    db_session.add(item); db_session.commit(); db_session.refresh(item)

    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [dev])
    assert result["qa"].get(item.id) is None  # NULL employee_id


def test_opo_split_by_ratio(db_session: Session):
    """ОПЭ разбивается на 2 части: analyst-доля и dev-доля по opo_analyst_ratio."""
    analyst = _make_emp(db_session, "Иванов", "analyst")
    dev = _make_emp(db_session, "Петров", "developer")
    item = BacklogItem(
        title="Init",
        estimate_analyst_hours=10, estimate_dev_hours=20,
        estimate_qa_hours=0, estimate_opo_hours=20,
        opo_analyst_ratio=0.3,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item); db_session.commit(); db_session.refresh(item)

    svc = ResourcePlanningService(db_session)
    parts = svc._opo_split(item, analyst_id=analyst.id, dev_id=dev.id)
    assert len(parts) == 2
    assert parts[0] == (analyst.id, 6.0)  # 30% of 20
    assert parts[1] == (dev.id, 14.0)
```

Add fixture `db_session` if not present in conftest — use existing pattern.

- [ ] **Step 2: Запустить — упасть**

Run: `py -3.10 -m pytest tests/test_resource_planning_assignment_logic.py -v`
Expected: FAIL — `_opo_split` not defined / wrong analyst chosen.

- [ ] **Step 3: Переписать `_assign_employees` + добавить `_opo_split`**

Заменить `_assign_employees` в `app/services/resource_planning_service.py` (lines 368–420):

```python
ANALYST_ROLES = {"аналитик", "analyst", "an", "рп", "rp", "консультант", "consultant"}
DEV_ROLES = {"разработчик", "developer", "dev", "программист"}
QA_ROLES = {"qa", "тестировщик"}


def _assign_employees(
    self, items: List[BacklogItem], employees: List[Employee],
    pinned: Optional[Dict[Tuple[str, str, int], str]] = None,
) -> Dict[str, Dict[str, str]]:
    """{phase: {item_id: employee_id|None}} с учётом ролей и закреплений.

    - analyst: исполнитель задачи (если его роль ∈ analyst/РП/консультант)
    - dev:     greedy по dev pool с уважением pinned
    - qa:      employee_id=None (часы-only)
    - opo:     2 части: analyst-доля → assignee, dev-доля → выбранный dev
    pinned: {(item_id, phase, part_number): employee_id}
    """
    pinned = pinned or {}

    by_id: Dict[str, Employee] = {e.id: e for e in employees}
    dev_ids = [e.id for e in employees if (e.role or "").lower() in DEV_ROLES]
    if not dev_ids:
        dev_ids = [e.id for e in employees]

    load: Dict[str, float] = defaultdict(float)
    result: Dict[str, Dict[str, str]] = {p: {} for p in PHASE_ORDER}

    for item in items:
        # analyst — assignee если его роль годится
        analyst_id = None
        if item.assignee_employee_id:
            emp = by_id.get(item.assignee_employee_id)
            if emp and (emp.role or "").lower() in ANALYST_ROLES:
                analyst_id = emp.id
        # pin override для analyst
        pin_an = pinned.get((item.id, "analyst", 1))
        if pin_an:
            analyst_id = pin_an
        if analyst_id:
            load[analyst_id] += item.estimate_analyst_hours or 0.0
        result["analyst"][item.id] = analyst_id  # может остаться None

        # dev — greedy / pin
        dev_id = pinned.get((item.id, "dev", 1))
        if not dev_id and dev_ids:
            dev_id = min(dev_ids, key=lambda eid: load[eid])
        if dev_id:
            load[dev_id] += item.estimate_dev_hours or 0.0
        result["dev"][item.id] = dev_id

        # qa — без сотрудника
        result["qa"][item.id] = None

        # opo — две строки (см. _opo_split в _create_assignments)
        # маркируем item как obtaining opo для генератора
        result["opo"][item.id] = analyst_id or dev_id  # placeholder, реально создаём 2 строки

    return result


def _opo_split(
    self, item: BacklogItem, analyst_id: Optional[str], dev_id: Optional[str]
) -> List[Tuple[Optional[str], float]]:
    """Вернуть 2 куска ОПЭ: [(analyst_id, an_hours), (dev_id, dev_hours)].

    Доля аналитика = item.opo_analyst_ratio (default 0.5).
    """
    total = item.estimate_opo_hours or 0.0
    ratio = item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
    an_hours = round(total * ratio, 2)
    dev_hours = round(total - an_hours, 2)
    return [(analyst_id, an_hours), (dev_id, dev_hours)]
```

В местах где создаются `ResourcePlanAssignment` для phase='opo' (см. поиск `phase="opo"` в файле — обычно в `_create_assignments` или `compute`-методе) — генерировать **2 записи** с `part_number=1` (analyst) и `part_number=2` (dev), вместо одной. Hours_allocated брать из `_opo_split`.

Важно: убедиться что `_compute_dates`/`_compute_cpm` корректно работают с двумя opo-строками (часы суммируются по item+phase в одну фазу при cpm; либо обрабатываются параллельно).

- [ ] **Step 4: Запустить тесты — пройти**

Run: `py -3.10 -m pytest tests/test_resource_planning_assignment_logic.py -v`
Expected: PASS все 4 теста.

- [ ] **Step 5: Регрессия — все resource_planning тесты**

Run: `py -3.10 -m pytest tests/test_resource_planning*.py -v`
Expected: PASS (могут быть adjustments в test_resource_planning_service если они мокали старую логику — починить).

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py tests/test_resource_planning_assignment_logic.py
git commit -m "fix(resource-planning): analyst from assignee + ОПЭ split + QA hours-only"
```

---

## Task 3: Backend — PATCH assignment ставит is_pinned, расширить AssignmentOut

**Files:**
- Modify: `app/api/endpoints/resource_planning.py`
- Test: `tests/test_resource_planning_endpoints.py` (расширить)

- [ ] **Step 1: Расширить тест PATCH endpoint**

В `tests/test_resource_planning_endpoints.py` добавить:

```python
def test_patch_assignment_sets_is_pinned(client, ready_plan_with_assignment):
    plan_id, assignment_id, dev2_id = ready_plan_with_assignment
    r = client.patch(
        f"/api/v1/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"employee_id": dev2_id},
    )
    assert r.status_code == 200
    assert r.json()["is_pinned"] is True
    assert r.json()["employee_id"] == dev2_id


def test_recompute_respects_pinned(client, ready_plan_with_pinned_assignment):
    plan_id = ready_plan_with_pinned_assignment
    r = client.post(f"/api/v1/resource-plans/{plan_id}/compute")
    assert r.status_code == 200
    # после пересчёта pinned-сотрудник остался
    proj = client.get(f"/api/v1/resource-plans/{plan_id}/gantt").json()
    pinned = [a for a in proj["assignments"] if a.get("is_pinned")]
    assert len(pinned) >= 1


def test_assignment_response_includes_backlog_item_key(client, ready_plan_with_assignment):
    plan_id, _, _ = ready_plan_with_assignment
    proj = client.get(f"/api/v1/resource-plans/{plan_id}/gantt").json()
    assert all("backlog_item_key" in a for a in proj["assignments"])
```

Зависит от fixtures `ready_plan_with_assignment` и `ready_plan_with_pinned_assignment` — создать рядом если нет, посмотреть существующий conftest.

- [ ] **Step 2: Запустить — упасть**

Run: `py -3.10 -m pytest tests/test_resource_planning_endpoints.py -v -k "patch_assignment_sets_is_pinned or recompute_respects_pinned or backlog_item_key"`
Expected: FAIL.

- [ ] **Step 3: Исправить endpoint и схему**

В `app/api/endpoints/resource_planning.py`:

1. Найти класс `AssignmentOut` (схема ответа) — добавить поля:
```python
    backlog_item_key: Optional[str] = None
    is_pinned: bool = False
```

2. Найти builder, который создаёт `AssignmentOut` из `ResourcePlanAssignment` — расширить:
```python
    backlog_item_key=(a.backlog_item.issue.key if a.backlog_item.issue else None),
    is_pinned=a.is_pinned,
```
(нужен eager-load `joinedload(BacklogItem.issue)` в gantt-эндпоинте — добавить если нет.)

3. PATCH endpoint:
```python
@router.patch("/{plan_id}/assignments/{assignment_id}", response_model=AssignmentOut)
def patch_assignment(
    plan_id: str, assignment_id: str, payload: AssignmentPatch,
    db: Session = Depends(get_db),
) -> AssignmentOut:
    a = db.get(ResourcePlanAssignment, assignment_id)
    if not a or a.plan_id != plan_id:
        raise HTTPException(404, "assignment not found")
    if payload.employee_id is not None:
        a.employee_id = payload.employee_id
        a.is_pinned = True
    db.commit()
    db.refresh(a)
    return _to_assignment_out(a)
```

4. Сервис в `_assign_employees` нужно вызывать с `pinned`-словарём, который собирается из existing assignments перед пересчётом. В `compute_plan` (или как метод называется) перед вызовом `_assign_employees`:
```python
existing = db.query(ResourcePlanAssignment).filter(
    ResourcePlanAssignment.plan_id == plan_id,
    ResourcePlanAssignment.is_pinned == True,
).all()
pinned = {(a.backlog_item_id, a.phase, a.part_number): a.employee_id for a in existing}
```
И передать в `_assign_employees(items, employees, pinned=pinned)`.

- [ ] **Step 4: Запустить тесты — пройти**

Run: `py -3.10 -m pytest tests/test_resource_planning_endpoints.py -v`
Expected: PASS все.

- [ ] **Step 5: Kill backend + restart**

Per memory `feedback_windows_uvicorn_reload`:
```bash
# Win: kill PID listening on :8000, restart uvicorn app.main:app --port 8000
```

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/test_resource_planning_endpoints.py
git commit -m "feat(resource-planning): PATCH sets is_pinned + expose key in gantt"
```

---

## Task 4: Frontend — расширить типы AssignmentOut + ResourcePlanOut

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`

- [ ] **Step 1: Добавить поля в TS-интерфейс**

Найти `interface AssignmentOut` или `type AssignmentOut`. Добавить:
```ts
  backlog_item_key: string | null;
  is_pinned: boolean;
```

Проверить что `ResourcePlanOut` уже имеет `label` и `parent_plan_id` — судя по странице да.

- [ ] **Step 2: Type-check фронта**

Run (в `frontend/`): `npm run lint && npx tsc -b`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts
git commit -m "chore(frontend): add backlog_item_key + is_pinned to AssignmentOut"
```

---

## Task 5: Frontend — dropdown с пометкой копий + удаление дубликатов

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx:76-79`

- [ ] **Step 1: Переписать `planOptions`**

Заменить lines 76–79:

```tsx
const planOptions = plans.map(p => {
  const isCopy = !!p.parent_plan_id;
  const labelText = p.label ? ` · ${p.label}` : '';
  const copyMark = isCopy ? ' (копия)' : '';
  return {
    label: `${p.quarter} ${p.year} — ${p.team ?? '—'}${copyMark}${labelText} [${p.status}]`,
    value: p.id,
  };
});
```

- [ ] **Step 2: Визуальная проверка**

Restart frontend if needed (`npm run dev` уже жив — vite hot-reload). Открыть /resource-planning. В выпадающем списке: оригинал без пометки, копии с «(копия)» и меткой.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "fix(resource-planning): mark forks in plan dropdown"
```

---

## Task 6: Frontend — удалить P50/P90 toggle, переключить «Связи» на visibility

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx:32-33,135-149`

- [ ] **Step 1: Удалить P50/P90 toggle и state**

Из `ResourcePlanningPage.tsx`:
- Удалить `const [showPert, setShowPert] = useState(false);` (line 33)
- Удалить блок Switch P50/P90 (lines 146–149):
  ```tsx
  <Space size={4}>
    <Switch checked={showPert} onChange={setShowPert} size="small" />
    <span style={{ fontSize: 12, color: '#8ab0d8' }}>P50/P90</span>
  </Space>
  ```
- В `<GanttChart ... showPert={showPert} />` (line 177) удалить пропс `showPert`. Default в `GanttChart` оставить false.

- [ ] **Step 2: «Связи» уже скрыт условием — оставить как есть**

Текущий блок (lines 136–145) уже условный `viewMode !== 'resource-track'`. Это и есть visibility-pattern. Ничего менять.

- [ ] **Step 3: Type-check + lint**

Run: `cd frontend && npm run lint && npx tsc -b`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "fix(resource-planning): remove P50/P90 toggle (no probabilistic data)"
```

---

## Task 7: Frontend — название многострочное + ключ задачи в Гантте

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx:11`
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (lines 57–60, 147, 289 — все места рендера title)

- [ ] **Step 1: Увеличить leftColWidth**

`GanttChart.tsx`:
```ts
const leftColWidth = 280;
```

- [ ] **Step 2: Убрать ellipsis + добавить wrap + ключ**

В `GanttRows.tsx` найти все места с `whiteSpace: 'nowrap', textOverflow: 'ellipsis'`. Заменить:

```tsx
<div style={{ width: leftColWidth, padding: '4px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
  {a.backlog_item_key && (
    <a
      href={`https://example.atlassian.net/browse/${a.backlog_item_key}`}
      target="_blank" rel="noreferrer"
      style={{ fontSize: 10, color: '#7a9ab8' }}
    >
      {a.backlog_item_key}
    </a>
  )}
  <div style={{ fontSize: 12, lineHeight: 1.3, whiteSpace: 'normal', wordBreak: 'break-word' }}>
    {a.backlog_item_title}
  </div>
</div>
```

Сделать в каждом из 3 view-режимов (portfolio / two-level / resource-track), сохраняя контекст конкретной view-функции.

- [ ] **Step 3: Авто-высота строк**

В контейнере строки убрать фиксированную `height`, оставить `minHeight: 32`. Если у фазы свои бары на отдельных подстроках (two-level), сделать `minHeight` каждой подстроки = 24, но контейнер инициативы — flex-column.

- [ ] **Step 4: Визуальная проверка**

Открыть страницу с инициативами с длинными названиями (как на скрине user'a). Убедиться что текст переносится, ключ виден слева вверху мелко, кликабелен.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/GanttChart.tsx frontend/src/components/resource-planning/GanttRows.tsx
git commit -m "fix(resource-planning): multi-line title + Jira key in Gantt left column"
```

---

## Task 8: Frontend — компонент EmployeeAvatar (инициалы + цвет роли)

**Files:**
- Create: `frontend/src/components/resource-planning/EmployeeAvatar.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
import { Tooltip } from 'antd';

interface Props {
  name: string | null;
  role?: string | null;
  size?: number;
}

const ROLE_COLORS: Record<string, string> = {
  analyst: '#00c9c8',
  аналитик: '#00c9c8',
  rp: '#5470ff',
  рп: '#5470ff',
  consultant: '#a070ff',
  консультант: '#a070ff',
  developer: '#3a7bff',
  разработчик: '#3a7bff',
  qa: '#f59e0b',
  тестировщик: '#f59e0b',
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function EmployeeAvatar({ name, role, size = 22 }: Props) {
  if (!name) return null;
  const color = ROLE_COLORS[(role ?? '').toLowerCase()] ?? '#6b7280';
  return (
    <Tooltip title={name}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: size, height: size,
          borderRadius: '50%',
          background: color,
          color: '#fff',
          fontSize: Math.round(size * 0.45),
          fontWeight: 600,
          letterSpacing: 0.3,
          flexShrink: 0,
        }}
      >
        {initials(name)}
      </span>
    </Tooltip>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/EmployeeAvatar.tsx
git commit -m "feat(resource-planning): EmployeeAvatar component with role colors"
```

---

## Task 9: Frontend — Popover «Назначить сотрудника» на бар фазы

**Files:**
- Create: `frontend/src/components/resource-planning/AssignEmployeePopover.tsx`
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (обернуть бары)

- [ ] **Step 1: Создать Popover-компонент**

```tsx
import { Button, Popover, Select, Space } from 'antd';
import { useState } from 'react';
import { usePatchAssignment, useComputeResourcePlan } from '../../hooks/useResourcePlanning';
import type { Employee } from '../../api/resourcePlanning';

interface Props {
  assignmentId: string;
  planId: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  currentEmployeeId: string | null;
  employees: Employee[];
  isPinned: boolean;
  children: React.ReactNode;
}

export default function AssignEmployeePopover({
  assignmentId, planId, phase, currentEmployeeId, employees, isPinned, children,
}: Props) {
  const [open, setOpen] = useState(false);
  const [empId, setEmpId] = useState<string | null>(currentEmployeeId);
  const patch = usePatchAssignment();
  const compute = useComputeResourcePlan();

  if (phase === 'qa') return <>{children}</>;  // QA — без сотрудника

  const handleSave = async () => {
    if (empId && empId !== currentEmployeeId) {
      await patch.mutateAsync({ planId, assignmentId, employee_id: empId });
      await compute.mutateAsync(planId);
    }
    setOpen(false);
  };

  const content = (
    <Space direction="vertical" style={{ minWidth: 240 }}>
      <Select
        value={empId}
        onChange={setEmpId}
        showSearch optionFilterProp="label"
        style={{ width: '100%' }}
        options={employees.map(e => ({ label: `${e.name} (${e.role ?? '—'})`, value: e.id }))}
      />
      <Space>
        <Button size="small" type="primary" onClick={handleSave}
                loading={patch.isPending || compute.isPending}>
          Закрепить + пересчитать
        </Button>
        <Button size="small" onClick={() => setOpen(false)}>Отмена</Button>
      </Space>
      {isPinned && <span style={{ fontSize: 11, color: '#00c9c8' }}>● закреплено</span>}
    </Space>
  );

  return (
    <Popover content={content} title="Назначить сотрудника" trigger="click"
             open={open} onOpenChange={setOpen}>
      {children}
    </Popover>
  );
}
```

- [ ] **Step 2: Подключить в GanttRows вокруг каждого бара**

В `GanttRows.tsx` обернуть каждый бар (`<div className="gantt-bar">`) в `<AssignEmployeePopover>` со значениями. Добавить `cursor: pointer` на бар. Передать список сотрудников как пропс из родителя — добавить хук `useEmployees(team)` если ещё нет.

- [ ] **Step 3: Маркер закрепления на баре**

На баре с `is_pinned=true` рисовать тонкую обводку:
```tsx
style={{
  ...,
  outline: a.is_pinned ? '1px solid #00c9c8' : 'none',
}}
```

- [ ] **Step 4: Визуальная проверка**

Открыть /resource-planning, кликнуть на бар разработчика → выбрать другого сотрудника → нажать «Закрепить + пересчитать». Бар должен обновиться, обводка появиться. Повторный пересчёт через кнопку «Пересчитать» — закреплённого не трогает.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/AssignEmployeePopover.tsx frontend/src/components/resource-planning/GanttRows.tsx
git commit -m "feat(resource-planning): inline reassign popover with pin + recompute"
```

---

## Task 10: Frontend — аватарки на барах фаз (two-level + resource-track)

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (two-level + resource-track view)

- [ ] **Step 1: Импорт + вставка**

В `GanttRows.tsx`:
```tsx
import EmployeeAvatar from './EmployeeAvatar';
```

В two-level view (~line 200) вместо текста ФИО мелким серым:
```tsx
<EmployeeAvatar name={a.employee_name} role={a.employee_role} size={20} />
```
(нужно в `AssignmentOut` добавить `employee_role` — если ещё нет, расширить backend схему `AssignmentOut`. Если нагрузка — оставить ФИО только в tooltip аватарки.)

- [ ] **Step 2: На портфельной view бар тоже получает аватарку**

В portfolio view (~line 60–70) рядом с подписью фазы поставить аватарку:
```tsx
<div style={{ position: 'absolute', left: 4, top: '50%', transform: 'translateY(-50%)' }}>
  <EmployeeAvatar name={a.employee_name} role={a.employee_role} size={18} />
</div>
```

- [ ] **Step 3: Backend — добавить employee_role в AssignmentOut**

В `app/api/endpoints/resource_planning.py` `AssignmentOut`:
```python
    employee_role: Optional[str] = None
```
В builder:
```python
    employee_role=(a.employee.role if a.employee else None),
```
И в TS в `frontend/src/api/resourcePlanning.ts` добавить.

- [ ] **Step 4: Визуальная проверка**

Phases view: кружочки с инициалами на каждой подстроке вместо текста ФИО. Hover — full ФИО.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py frontend/src/components/resource-planning/GanttRows.tsx frontend/src/api/resourcePlanning.ts
git commit -m "feat(resource-planning): avatar initials on phase rows"
```

---

## Task 11: Frontend — ConflictPanel «Показать скрытые»

**Files:**
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx`

- [ ] **Step 1: Найти место рендеринга hidden count**

Открыть файл, найти где выводится «N скрыто». Добавить кнопку:
```tsx
{hiddenCount > 0 && (
  <Button size="small" type="link" onClick={() => setShowHidden(!showHidden)}>
    {showHidden ? 'Скрыть погашенные' : `Показать ${hiddenCount} скрытых`}
  </Button>
)}
```

И в фильтре конфликтов: `if (!showHidden && c.is_resolved) return null;`

- [ ] **Step 2: Визуальная проверка**

Если конфликты погашены — кнопка появляется, по клику разворачиваются.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/ConflictPanel.tsx
git commit -m "fix(resource-planning): show resolved conflicts on demand"
```

---

## Task 12: Финальная проверка + push

- [ ] **Step 1: Полный backend test pass**

Run: `py -3.10 -m pytest tests/ -v`
Expected: PASS (или те же pre-existing failures из memory `project_ci_red_pre_existing` — не трогать).

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: PASS, нет TS-ошибок.

- [ ] **Step 3: Ручной smoke на /resource-planning**

1. Выбрать план — в выпадайке копии помечены.
2. Длинное название инициативы — переносится, ключ виден.
3. Кликнуть на dev-бар → Popover → выбрать другого → закрепить → бар обновился, обводка цианом.
4. Phases view — аватарки на каждой фазе.
5. P50/P90 toggle нет.
6. Кнопка-резюме «Сделать копию» (текст уже корректный).
7. Конфликты с скрытыми — кнопка «Показать N скрытых».

- [ ] **Step 4: Push на main**

Per memory `feedback_commit_push_after_batch`:
```bash
git push origin main
```

---

## Self-Review Notes

- **Coverage:** 5 user-bug + 7 extra-issues — все покрыты задачами 2–11.
- **Placeholder scan:** ОК, везде код.
- **Type consistency:** `is_pinned` / `backlog_item_key` / `employee_role` — единые имена backend↔frontend. `AssignEmployeePopover` импортирует `Employee` тип — должен быть в `api/resourcePlanning.ts` (если нет — расширить отдельно мини-задачей).
- **ОПЭ split:** интерпретация — две assignment-строки на phase=opo с разным `part_number`. Если в существующей схеме `part_number` уже используется для split-фаз с конфликтами (см. модель: «split-фаз (частичная сдача)»), убедиться что не конфликтует — иначе добавить `role_marker: 'analyst'|'dev'` колонку. **Решение:** на этапе implementation разработчик проверит и при необходимости добавит маркер.
