# Resource Planning — Pin UX, Relay Persistence, QA Weekend Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Починить три бага раздела /resource-planning: (1) QA-фаза попадает на выходные после сдвига по предшественникам; (2) у ОПЭ нет связи с QA — детерминированно отсутствует ребро `qa → opo`; (3) ручная дата (pinned_start) выставляется при любом split-е и не отделяется от явной «фиксации» — связь с предшественниками молча игнорируется.

**Architecture:**
- Bug 1 — QA-фаза после `_shift_to_obey_predecessors` пересчитывает свою daily-раскладку через производственный календарь от нового `start_date`, а не сдвигает ключи `daily_hours_json` blind `+delta`.
- Bug 2 — связи между фазами становятся **данными**, а не дефолтом-по-требованию: при создании каждой фазы в `compute_schedule` сразу пишутся рёбра `PhasePredecessor` (`analyst→dev`, `dev→qa`, `qa→opo×2`). `_ensure_default_predecessors` переписывается на per-pair seeding — добавляет только отсутствующие пары, инициатива целиком больше не пропускается.
- Bug 3 — `split_assignment` больше **не** ставит `pinned_start` (только `pinned_split` как маркер N частей). PATCH с новой датой ставит `pinned_start=True` (drag = фиксация). Новый явный флаг `pinned_start: false` в PATCH — снять фиксацию. Существующим строкам `pinned_start` сбрасывается миграцией. Добавляется тип конфликта `PREDECESSOR_VIOLATED` — если зафиксированная фаза стартует раньше конца предшественника, фронт показывает конфликт-warning, а не молчит.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic (batch SQLite) / React 19 + AntD 6 / pytest

---

## File Structure

**Modify:**
- `app/services/resource_planning_service.py` — `_shift_to_obey_predecessors` (QA recalc), `_ensure_default_predecessors` (per-pair), `compute_schedule` (persist edges at creation time), `split_assignment` (no pinned_start), `_build_conflict_dicts` (PREDECESSOR_VIOLATED)
- `app/api/endpoints/resource_planning.py` — PATCH `/assignments/{id}` принимает `pinned_start: bool | None`
- `app/services/conflict_aggregator.py` — сообщение для `PREDECESSOR_VIOLATED`
- `frontend/src/components/resource-planning/AssignmentSidebar.tsx` (или эквивалент drawer-а) — кнопки «Зафиксировать дату» / «Снять фиксацию», переименование «Сбросить ручную дату»
- `frontend/src/components/resource-planning/ConflictPanel.tsx` — рендер PREDECESSOR_VIOLATED
- `frontend/src/api/resourcePlanning.ts` — payload с `pinned_start`

**Create:**
- `alembic/versions/<id>_reset_rp_assignment_pinned_start.py` — миграция: `UPDATE resource_plan_assignments SET pinned_start = false`
- `tests/services/test_rp_qa_shift_calendar.py`
- `tests/services/test_rp_relay_persisted.py`
- `tests/services/test_rp_predecessor_violated.py`
- `tests/test_rp_pinned_start_ux.py` — PATCH start ставит pin, PATCH pinned_start=false снимает, split не ставит

---

## Phase A — Backend

### Task 1: Reset migration для pinned_start

**Files:**
- Create: `alembic/versions/<id>_reset_rp_assignment_pinned_start.py`

- [ ] **Step 1: Сгенерировать пустой ревизион**

Run: `py -3.10 -m alembic revision -m "reset rp_assignment.pinned_start"`
Expected: новый файл в `alembic/versions/`

- [ ] **Step 2: Написать тело миграции**

```python
"""reset rp_assignment.pinned_start

Revision ID: <auto>
Revises: <prev>
"""
from alembic import op
import sqlalchemy as sa


revision = "<auto>"
down_revision = "<prev>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Существующие строки могли получить pinned_start=True от split'a
    # (теперь split не пинит даты) и от PATCH'ев до введения явной фиксации.
    # Сбрасываем флаг, чтобы пользователь явно выбирал что закреплять.
    op.execute(
        "UPDATE resource_plan_assignments SET pinned_start = false"
    )


def downgrade() -> None:
    # No-op: данные не восстанавливаются — рестор пина = ручная переустановка.
    pass
```

- [ ] **Step 3: Прогнать миграцию**

Run: `py -3.10 -m alembic upgrade head`
Expected: миграция применена без ошибок.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat(rp): reset pinned_start on all assignments (pin UX rework)"
```

---

### Task 2: QA-shift — пересчитывать daily через производственный календарь

**Files:**
- Modify: `app/services/resource_planning_service.py` функция `_shift_to_obey_predecessors`
- Test: `tests/services/test_rp_qa_shift_calendar.py`

- [ ] **Step 1: Написать failing test**

```python
# tests/services/test_rp_qa_shift_calendar.py
"""После _shift_to_obey_predecessors QA не должен стоять на выходных.

Сценарий: dev заканчивается в пятницу, qa должен сдвинуться. Ключи
daily_hours_json у QA должны лежать только на буднях (по производственному
календарю), start_date/end_date — на рабочих днях.
"""
import json
from datetime import date

import pytest

from app.models import (
    BacklogItem, Employee, EmployeeTeam, ProductionCalendarDay,
    ResourcePlan, ResourcePlanAssignment, PhasePredecessor, PlanningScenario,
    ScenarioAllocation,
)
from app.services.resource_planning_service import ResourcePlanningService


@pytest.mark.usefixtures("db_clean")
def test_qa_shift_skips_weekend(db_session):
    # ... seed: команда, сотрудник-аналитик/дев, инициатива с estimate_qa_hours=14
    # сценарий с allocation included, ResourcePlan q=Q2 year=2026
    # ProductionCalendarDay: 2026-04-03 (Пт) hours=8, 04..05 Сб/Вс 0
    # Создать вручную dev-фазу с end_date = 2026-04-03 (пятница)
    # Создать QA с start = 2026-03-30 (Пн), end = 2026-04-01 (Ср), daily
    # для 30..01.
    # Поставить ребро dev → qa.
    # ---
    # call: ResourcePlanningService(db_session)._shift_to_obey_predecessors(
    #     [dev, qa], {qa.id: [dev.id]}, q_start, q_end)
    # ---
    # assert qa.start_date.weekday() < 5  # Не суббота/воскресенье
    # assert qa.end_date.weekday() < 5
    # daily = json.loads(qa.daily_hours_json)
    # for k in daily:
    #     assert date.fromisoformat(k).weekday() < 5
    ...
```

(Полный seed см. в `tests/conftest.py`/`tests/services/conftest.py` — переиспользовать `db_session`, `db_clean`, helpers создания плана.)

- [ ] **Step 2: Запустить — ожидать FAIL**

Run: `py -3.10 -m pytest tests/services/test_rp_qa_shift_calendar.py -v`
Expected: FAIL — текущий код сдвигает QA blind, попадает на Сб/Вс.

- [ ] **Step 3: Имплементация**

В `_shift_to_obey_predecessors` после блока с `new_start = max(ends) + timedelta(days=1)` и установкой `a.start_date = new_start`, добавить:

```python
# Для QA / OPO / dev — если фаза не имеет employee_id или мы знаем, что
# раскладка делается по календарю, нужно пересоздать daily_hours_json от
# нового start_date вместо blind-shift. Конкретный кейс: QA. Для employee-
# зависимых фаз остаётся старая логика (она опирается на per-employee avail).
if a.phase == "qa" and a.daily_hours_json:
    # Перераскладываем все часы из hours_allocated заново, начиная с new_start,
    # по производственному календарю + involvement_qa.
    from app.models import ProductionCalendarDay
    from app.services.resource_planning_service import (
        DEFAULT_HOURS_PER_DAY,
    )
    cal_rows = (
        self.db.execute(
            select(ProductionCalendarDay).where(
                ProductionCalendarDay.date >= new_start,
                ProductionCalendarDay.date <= q_end,
            )
        ).scalars().all()
    )
    cal_anomalies = {r.date: r.hours for r in cal_rows}

    def _daily_cal(d):
        h = cal_anomalies.get(d)
        if h is None:
            return DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0
        return h

    # involvement_qa из BacklogItem — нужно достать через item.
    item = self.db.get(BacklogItem, a.backlog_item_id)
    qa_inv = (
        self._involvement_for_phase(item, "qa") if item else 1.0
    ) or 1.0
    remaining_h = float(a.hours_allocated or 0.0)
    new_daily = {}
    cursor = new_start
    while remaining_h > 0.001 and cursor <= q_end:
        avail_h = _daily_cal(cursor) * qa_inv
        if avail_h > 0:
            take = min(remaining_h, avail_h)
            new_daily[cursor.isoformat()] = take
            remaining_h -= take
        cursor += timedelta(days=1)
    if new_daily:
        keys = [date.fromisoformat(k) for k in new_daily]
        a.start_date = min(keys)
        a.end_date = max(keys)
        a.daily_hours_json = json.dumps(new_daily)
    # Если ничего не влезло (квартал закончился) — старая защита (clamp
    # к q_end) уже отработала выше.
    continue  # пропустить дальнейший blind-shift блока ниже
```

Вставить блок перед существующим `if a.daily_hours_json and delta != 0:` (строка ~1606). Старый shift-блок остаётся для employee-фаз.

- [ ] **Step 4: Запустить тест — PASS**

Run: `py -3.10 -m pytest tests/services/test_rp_qa_shift_calendar.py -v`
Expected: PASS.

- [ ] **Step 5: Прогнать ВСЁ resource-planning-test множество**

Run: `py -3.10 -m pytest tests/services/ tests/test_resource_planning*.py -v`
Expected: regression-free (могут падать pre-existing — сверить с `project_ci_red_pre_existing`).

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_qa_shift_calendar.py
git commit -m "fix(rp): QA daily recomputed via prod calendar after predecessor shift"
```

---

### Task 3: Persist relay edges в compute_schedule

**Files:**
- Modify: `app/services/resource_planning_service.py` функция `compute_schedule` (после создания фаз)
- Test: `tests/services/test_rp_relay_persisted.py`

**Цель:** после создания всех `new_assignments`, для каждой инициативы пройти `PHASE_ORDER` и для каждой пары `(prev, next)` (где обе фазы существуют) убедиться, что ребро `PhasePredecessor(succ=next, pred=prev)` есть в БД. Для `opo` — на обе строки (analyst-piece и dev-piece). Это **дополняет** существующий `_ensure_default_predecessors`, но работает per-pair и не пропускает инициативу.

- [ ] **Step 1: Failing test**

```python
# tests/services/test_rp_relay_persisted.py
"""После compute_schedule у инициативы с 4 фазами должны быть все рёбра:
analyst→dev, dev→qa, qa→opo (на обе строки opo).

Регрессия: даже если у инициативы уже было ребро analyst→dev (например, от
прошлого compute), пересчёт должен достроить qa→opo, а не пропускать
инициативу.
"""
import pytest

from app.models import PhasePredecessor, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService


@pytest.mark.usefixtures("db_clean")
def test_relay_edges_persisted_for_full_chain(db_session, sample_plan_with_opo):
    plan_id = sample_plan_with_opo.id
    ResourcePlanningService(db_session).compute_schedule(plan_id)
    # Все фазы инициативы:
    asns = db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id
        )
    ).scalars().all()
    by_phase = {a.phase: a for a in asns if a.phase != "opo"}
    opo_rows = [a for a in asns if a.phase == "opo"]
    # Ребро analyst→dev
    assert _edge_exists(db_session, by_phase["dev"].id, by_phase["analyst"].id)
    # Ребро dev→qa
    assert _edge_exists(db_session, by_phase["qa"].id, by_phase["dev"].id)
    # Ребро qa→opo на ОБЕ строки opo
    for opo in opo_rows:
        assert _edge_exists(db_session, opo.id, by_phase["qa"].id)


def _edge_exists(db, succ_id, pred_id) -> bool:
    return db.execute(
        select(PhasePredecessor).where(
            PhasePredecessor.successor_assignment_id == succ_id,
            PhasePredecessor.predecessor_assignment_id == pred_id,
        )
    ).scalar_one_or_none() is not None
```

Fixture `sample_plan_with_opo` — инициатива со всеми 4 фазами estimate>0, команда с аналитиком+девом.

- [ ] **Step 2: Запустить — FAIL**

Run: `py -3.10 -m pytest tests/services/test_rp_relay_persisted.py -v`
Expected: FAIL (qa→opo может отсутствовать на одной из строк или вовсе).

- [ ] **Step 3: Переписать `_ensure_default_predecessors` per-pair**

В `resource_planning_service.py`, заменить тело функции (строки ~1397-1492). Удалить early-skip per item:

```python
def _ensure_default_predecessors(
    self,
    plan_id: str,
    assignments: List[ResourcePlanAssignment],
) -> None:
    """Дополнить недостающие рёбра дефолтной цепочки analyst→dev→qa→opo.

    Per-pair seeding: для каждой пары (prev, next) из PHASE_ORDER проверяем,
    что ребро в БД есть. Если нет — добавляем. Инициативы, где пользователь
    явно правил предшественников ХОТЯ БЫ ОДНОЙ ФАЗЫ (predecessors_user_set
    на этой фазе или флаг в snapshot), пропускаем целиком — пользователь
    мог удалить дефолтную связь намеренно.
    """
    from app.models import PhasePredecessor

    user_set_rows = (
        self.db.execute(
            select(ResourcePlanAssignment.backlog_item_id)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.predecessors_user_set == True,  # noqa: E712
            )
            .distinct()
        ).all()
    )
    items_user_touched: set[str] = {r[0] for r in user_set_rows}

    existing_pairs: set[Tuple[str, str]] = {
        (r[0], r[1])
        for r in self.db.execute(
            select(
                PhasePredecessor.successor_assignment_id,
                PhasePredecessor.predecessor_assignment_id,
            )
        ).all()
    }

    by_item: Dict[str, Dict[str, List[ResourcePlanAssignment]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for a in assignments:
        by_item[a.backlog_item_id][a.phase].append(a)

    for item_id, phases in by_item.items():
        if item_id in items_user_touched:
            continue
        # Идём по парам в PHASE_ORDER. На каждой паре связываем «последняя
        # строка предыдущей фазы» → «все строки следующей фазы» (важно для
        # split-разбитой dev → qa и для двух строк opo).
        prev_phase_rows: Optional[List[ResourcePlanAssignment]] = None
        for ph in PHASE_ORDER:
            cur_rows = phases.get(ph)
            if not cur_rows:
                continue
            if prev_phase_rows:
                # «Последняя» строка предыдущей фазы — с максимальным part_number.
                pred = max(prev_phase_rows, key=lambda x: x.part_number or 1)
                for succ in cur_rows:
                    if not succ.id or not pred.id:
                        continue
                    pair = (succ.id, pred.id)
                    if pair in existing_pairs:
                        continue
                    existing_pairs.add(pair)
                    self.db.add(
                        PhasePredecessor(
                            successor_assignment_id=succ.id,
                            predecessor_assignment_id=pred.id,
                        )
                    )
            prev_phase_rows = cur_rows
```

- [ ] **Step 4: Запустить тест — PASS**

Run: `py -3.10 -m pytest tests/services/test_rp_relay_persisted.py -v`
Expected: PASS.

- [ ] **Step 5: Прогнать резерв**

Run: `py -3.10 -m pytest tests/services/ tests/test_resource_planning*.py -v`
Expected: no regressions (кроме pre-existing).

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_relay_persisted.py
git commit -m "fix(rp): seed missing predecessor edges per-pair (relay survives partial graph)"
```

---

### Task 4: `split_assignment` больше не ставит pinned_start

**Files:**
- Modify: `app/services/resource_planning_service.py` функция `split_assignment` (строка ~1644)
- Test: расширить `tests/test_rp_pinned_start_ux.py` (создаётся в Task 5)

- [ ] **Step 1: Найти место с `pinned_split=True`**

Открыть [resource_planning_service.py](app/services/resource_planning_service.py) около строк 1772-1783. Сейчас при создании каждой `part`:

```python
p = ResourcePlanAssignment(
    ...
    pinned_split=True,
    manual_edit_at=datetime.utcnow(),
)
```

`pinned_split=True` сохраняем — это маркер «фаза разбита на части».
`pinned_start` остаётся **default False** — никаких изменений тут не нужно.

**Проверить вторичные пути:**
- `_cascade_split` (строка ~1831) — поиск `pinned_start` в этой функции.
- `split_assignment` cascade в `redistribute_pinned_split` пути — поиск.

Run: `grep -n pinned_start app/services/resource_planning_service.py`

- [ ] **Step 2: Удалить любую установку `pinned_start = True` из split-related путей**

Проверить функции: `split_assignment`, `_cascade_split`, `redistribute_pinned_split`. Если где-то ставится `pinned_start=True` неявно — удалить. (По текущему чтению — НЕ ставится; шаг превентивный аудит.)

- [ ] **Step 3: Запустить полные тесты split-логики**

Run: `py -3.10 -m pytest tests/test_resource_planning_split*.py tests/services/test_rp_split*.py -v`
Expected: PASS.

- [ ] **Step 4: Commit (если что-то правилось)**

```bash
git add app/services/resource_planning_service.py
git commit -m "fix(rp): split no longer implicitly pins start dates"
```

(Если изменений нет — пропустить, переходить к Task 5.)

---

### Task 5: PATCH `/assignments/{id}` принимает явный `pinned_start: bool | None`

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` — `AssignmentPatch` schema + `update_assignment` handler (строки ~342, ~1311+)
- Test: `tests/test_rp_pinned_start_ux.py`

**Семантика:**
- `pinned_start` отсутствует в payload + `start_date` отсутствует → ничего не меняем.
- `pinned_start` отсутствует, `start_date` передан и отличается от текущего → `pinned_start=True` (drag = фиксация — back-compat с текущим UI поведением, теперь зафиксировано как контракт).
- `pinned_start: false` явно в payload → снимаем фиксацию (плюс `start_date` опционально может прийти любым).
- `pinned_start: true` явно → ставим фиксацию.

- [ ] **Step 1: Failing test**

```python
# tests/test_rp_pinned_start_ux.py
"""PATCH /assignments/{id} — явная семантика pinned_start.

1. PATCH с новым start_date без pinned_start → pinned_start=True (drag = фиксация).
2. PATCH с pinned_start=false → снимает фиксацию.
3. PATCH с pinned_start=true (без start_date) → ставит фиксацию на текущей дате.
4. После split parts.pinned_start=False (дата НЕ зафиксирована).
"""
import pytest

from app.models import ResourcePlanAssignment


@pytest.mark.usefixtures("db_clean")
def test_patch_start_date_pins(client, sample_assignment):
    aid = sample_assignment.id
    resp = client.patch(
        f"/api/v1/resource-planning/plans/{sample_assignment.plan_id}/assignments/{aid}",
        json={"start_date": "2026-04-15"},
    )
    assert resp.status_code == 200
    # reload
    a = ... # db_session.get(ResourcePlanAssignment, aid)
    assert a.pinned_start is True


@pytest.mark.usefixtures("db_clean")
def test_patch_pinned_start_false_unpins(client, pinned_assignment):
    aid = pinned_assignment.id
    resp = client.patch(
        f"/api/v1/resource-planning/plans/{pinned_assignment.plan_id}/assignments/{aid}",
        json={"pinned_start": False},
    )
    assert resp.status_code == 200
    a = ...
    assert a.pinned_start is False


@pytest.mark.usefixtures("db_clean")
def test_split_does_not_pin_start(client, sample_assignment):
    # POST split на 3 части
    resp = client.post(
        f"/api/v1/resource-planning/plans/{sample_assignment.plan_id}/assignments/{sample_assignment.id}/split",
        json={"parts_hours": [10, 10, 10], "cascade": False},
    )
    assert resp.status_code == 200
    parts = resp.json()["parts"]
    for p in parts:
        assert p["pinned_split"] is True
        assert p["pinned_start"] is False
```

- [ ] **Step 2: FAIL**

Run: `py -3.10 -m pytest tests/test_rp_pinned_start_ux.py -v`
Expected: FAIL (схема не принимает pinned_start, либо PATCH ставит pinned_start всегда).

- [ ] **Step 3: Расширить `AssignmentPatch`**

В [resource_planning.py:342](app/api/endpoints/resource_planning.py#L342) (`class AssignmentPatch(BaseModel):`) добавить:

```python
class AssignmentPatch(BaseModel):
    # ... существующие поля
    pinned_start: Optional[bool] = None
    # ... rest
```

- [ ] **Step 4: Переписать обработку pinned_start в handler**

В `update_assignment` (строка ~1349-1356), заменить:

```python
# OLD
if "start_date" in patch:
    a.pinned_start = True
    a.manual_edit_at = datetime.utcnow()
```

на:

```python
# Явный pinned_start в payload имеет приоритет.
explicit_pin = patch.pop("pinned_start", None)
if explicit_pin is not None:
    a.pinned_start = bool(explicit_pin)
    a.manual_edit_at = datetime.utcnow()
elif "start_date" in patch:
    # Drag / любое изменение даты без явного pinned_start = фиксация
    # (UI ставит pin неявно через перемещение бара).
    a.pinned_start = True
    a.manual_edit_at = datetime.utcnow()
```

- [ ] **Step 5: PASS**

Run: `py -3.10 -m pytest tests/test_rp_pinned_start_ux.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/test_rp_pinned_start_ux.py
git commit -m "feat(rp): explicit pinned_start flag in PATCH (drag still implicitly pins)"
```

---

### Task 6: `PREDECESSOR_VIOLATED` conflict detector

**Files:**
- Modify: `app/services/resource_planning_service.py` функция `_build_conflict_dicts`
- Modify: `app/services/conflict_aggregator.py` функция `_build_message`
- Test: `tests/services/test_rp_predecessor_violated.py`

- [ ] **Step 1: Failing test**

```python
# tests/services/test_rp_predecessor_violated.py
"""Если зафиксированная фаза стартует раньше конца предшественника —
получаем конфликт PREDECESSOR_VIOLATED.
"""
import pytest

from app.services.resource_planning_service import ResourcePlanningService


@pytest.mark.usefixtures("db_clean")
def test_predecessor_violated_emits_conflict(db_session, sample_plan_with_pin):
    # sample_plan_with_pin: dev pinned_start=True на 2026-04-13 при том, что
    # его предшественник analyst end_date = 2026-04-20.
    plan_id = sample_plan_with_pin.id
    ResourcePlanningService(db_session).compute_schedule(plan_id)
    # Прочитать конфликты из ResourcePlanConflict (модель).
    from app.models import ResourcePlanConflict
    conflicts = db_session.execute(
        select(ResourcePlanConflict).where(
            ResourcePlanConflict.plan_id == plan_id,
            ResourcePlanConflict.type == "PREDECESSOR_VIOLATED",
        )
    ).scalars().all()
    assert len(conflicts) == 1
    c = conflicts[0]
    assert "стартует до окончания" in c.message.lower() or "до завершения" in c.message.lower()
```

- [ ] **Step 2: FAIL**

Run: `py -3.10 -m pytest tests/services/test_rp_predecessor_violated.py -v`
Expected: FAIL — `PREDECESSOR_VIOLATED` не существует.

- [ ] **Step 3: Добавить детектор в `_build_conflict_dicts`**

В [resource_planning_service.py:2176](app/services/resource_planning_service.py#L2176) (`_build_conflict_dicts`), после блока LATE_START добавить:

```python
# PREDECESSOR_VIOLATED — succ.start_date < max(pred.end_date) + 1 day.
# Включает кейс «pinned_start выигрывает над связью» — иначе пользователь
# не видит, что закреплённая дата нарушает граф.
preds_map = self._load_predecessors(plan.id)
by_id = {a.id: a for a in assignments}
for a in assignments:
    if not a.start_date:
        continue
    pred_ids = preds_map.get(a.id, [])
    if not pred_ids:
        continue
    pred_ends = [
        by_id[pid].end_date
        for pid in pred_ids
        if pid in by_id and by_id[pid].end_date
    ]
    if not pred_ends:
        continue
    latest_pred_end = max(pred_ends)
    # Допустимое начало = latest_pred_end + 1 день (по календарю).
    if a.start_date <= latest_pred_end:
        result.append(
            {
                "type": "PREDECESSOR_VIOLATED",
                "severity": "warning",
                "detection_key": f"PREDECESSOR_VIOLATED:{a.id}",
                "backlog_item_id": a.backlog_item_id,
                "assignment_id": a.id,
                "employee_id": a.employee_id,
                # message сгенерит conflict_aggregator
            }
        )
```

- [ ] **Step 4: Шаблон сообщения в `conflict_aggregator.py`**

В `_build_message`, перед фолбэком, добавить:

```python
if t == "PREDECESSOR_VIOLATED":
    return (
        f"{item_label}: фаза стартует до завершения предшественника — "
        f"снимите ручную фиксацию даты или измените связь"
        if item_label
        else "Фаза стартует до завершения предшественника"
    )
```

- [ ] **Step 5: PASS**

Run: `py -3.10 -m pytest tests/services/test_rp_predecessor_violated.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_planning_service.py app/services/conflict_aggregator.py tests/services/test_rp_predecessor_violated.py
git commit -m "feat(rp): PREDECESSOR_VIOLATED conflict when pinned start ignores graph"
```

---

## Phase B — Frontend

### Task 7: Кнопки «Зафиксировать дату» / «Снять фиксацию» в сайдбаре фазы

**Files:**
- Modify: `frontend/src/components/resource-planning/AssignmentSidebar.tsx` (точное имя файла найти через `grep "Сбросить ручную дату" frontend/src`)
- Modify: `frontend/src/api/resourcePlanning.ts` — добавить `pinned_start?: boolean` в типе `UpdateAssignmentPayload`

- [ ] **Step 1: Найти файл и текущую кнопку**

Run: `grep -rn "Сбросить ручную дату\|pinned_start" frontend/src`
Expected: путь к компоненту сайдбара.

- [ ] **Step 2: Обновить API payload**

В `frontend/src/api/resourcePlanning.ts` (или эквивалент) — расширить тип PATCH:

```ts
export interface UpdateAssignmentPayload {
  // ... существующие
  pinned_start?: boolean;
}
```

- [ ] **Step 3: Заменить кнопку**

В сайдбаре фазы — секция «Действия». Текущая «Сбросить ручную дату» (danger, видна когда `assignment.pinned_start === true`). Заменить на пару:

```tsx
{assignment.pinned_start ? (
  <Button
    danger
    block
    onClick={() => updateAssignment({ pinned_start: false })}
  >
    Снять фиксацию даты
  </Button>
) : (
  <Button
    block
    onClick={() => updateAssignment({ pinned_start: true })}
  >
    Зафиксировать дату
  </Button>
)}
```

В детализации (где сейчас рендерится бэйдж «Закреплено») оставить как есть; pinned_start теперь меняется этой кнопкой.

- [ ] **Step 4: Браузер-смок**

Run: `.\scripts\e2e-local.ps1` (одноразово) или ручной запуск `frontend npm run dev` + переход на /resource-planning, проверка:
- Зафиксированная фаза: кнопка «Снять фиксацию даты» (danger).
- Незафиксированная: «Зафиксировать дату» (нейтральная).
- Тап «Зафиксировать» → бэйдж «Закреплено» появляется, кнопка меняется.
- Тап «Снять» → бэйдж пропадает, при следующем пересчёте фаза двигается.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat(rp): explicit pin/unpin button replaces 'reset manual date'"
```

---

### Task 8: ConflictPanel — рендер PREDECESSOR_VIOLATED

**Files:**
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx` (или эквивалент — найти через grep)
- Modify: соответствующий тип конфликта в TS (например, `frontend/src/types/resourcePlanning.ts`)

- [ ] **Step 1: Расширить type union**

```ts
export type ConflictType =
  | "OVERLOAD_LIGHT" | "OVERLOAD_MED" | "OVERLOAD_HIGH"
  | "QUARTER_OVERFLOW" | "SPLIT_REQUIRED" | "NO_ANALYST" | "NO_DEV"
  | "LATE_START" | "LEVELING_DELAY" | "LEVELING_REASSIGN"
  | "PREDECESSOR_VIOLATED";
```

- [ ] **Step 2: Добавить иконку/цвет**

В switch-блоке мапы типа → стиль:
```ts
case "PREDECESSOR_VIOLATED":
  return { color: "warning", icon: <DisconnectOutlined /> };
```

- [ ] **Step 3: Браузер-смок**

Создать сценарий: зафиксировать дату dev на день РАНЬШЕ окончания анализа → запустить пересчёт → в ConflictPanel появилась warning-плашка.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(rp): render PREDECESSOR_VIOLATED conflict in panel"
```

---

## Phase C — Финальный регресс

### Task 9: Full pytest + frontend lint/build

- [ ] **Step 1: Backend**

Run: `py -3.10 -m pytest tests/ -v`
Expected: количество passed = baseline (см. memory `project_ci_red_pre_existing`). Все новые тесты PASS.

- [ ] **Step 2: Frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errors. Warnings допустимы по существующему baseline.

- [ ] **Step 3: Финальный push**

```bash
git push origin main
```

---

## Self-Review Checklist

- [ ] Bug 1 (QA выходные) — покрыт Task 2 + test `test_rp_qa_shift_calendar.py`.
- [ ] Bug 2 (нет qa→opo) — покрыт Task 3 (per-pair seeder) + test `test_rp_relay_persisted.py`.
- [ ] Bug 3 (pinned UX) — покрыт Task 1 (миграция-сброс) + Task 4 (split не пинит) + Task 5 (PATCH явный флаг) + Task 6 (детектор) + Task 7 (UI кнопка) + Task 8 (UI конфликт).
- [ ] Все «delete» / «удалить» подтверждены конкретным кодом, не «adjust as needed».
- [ ] Все названия функций, полей, conflict-типов согласованы между задачами.
- [ ] Каждый шаг содержит запускаемую команду или конкретный код-блок.
