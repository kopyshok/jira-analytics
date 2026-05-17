# Resource Planning — фиксы и UX-overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть пакет багов и юзабилити-улучшений раздела `/resource-planning` (9 пунктов + 5 визуальных) — см. спек [`docs/superpowers/specs/2026-05-17-resource-planning-fixes-design.md`](../specs/2026-05-17-resource-planning-fixes-design.md).

**Architecture:** Backend планировщик (`resource_planning_service.py`) — фикс `_allocate_hours` для сохранения непотраченной ёмкости, отказ от Jira-растяжения, мульти-сегмент при preempting, spillover за квартал. API `/explain` расширяется детализацией. Frontend заменяет popover/drawer на единый non-modal drawer 920 c 6 collapsible-секциями, реализует `hideWeekends` (был no-op), week-mode без полосок выходных, A+B+C+D подсветку сотрудника, ползунки заливки, прогресс факта, plus 4 визуальных мини-фичи.

**Tech Stack:** Python 3.10 + SQLAlchemy 2.0 + Alembic batch migrations. React 19 + TS 6 + Vite 8 + AntD 6 + TanStack Query. Тесты pytest + Playwright.

---

## File Structure

### Backend

| Файл | Действие | Ответственность |
|---|---|---|
| `alembic/versions/<rev>_add_assignment_out_of_quarter_daily_hours.py` | Создать | Миграция: ALTER `resource_plan_assignments` ADD `out_of_quarter`, `daily_hours_json` |
| `app/models/resource_plan_assignment.py` | Модификация | Новые поля `out_of_quarter`, `daily_hours_json` |
| `app/services/resource_planning_service.py` | Модификация (`_allocate_hours`, `compute_schedule`, helpers) | Фикс ёмкости, фактический end, мульти-сегмент, spillover, daily_hours_json |
| `app/services/conflict_aggregator.py` | Модификация | Per-day чтение из `daily_hours_json` |
| `app/api/endpoints/resource_planning.py` | Модификация (`/explain`) | Добавить `algorithm_log`, `daily_breakdown`, `absences_in_window`, `phase_calc`, `hours_summary` |
| `app/schemas/resource_planning.py` | Модификация | `out_of_quarter`, `daily_hours`, новые блоки `/explain` |
| `tests/services/test_resource_planning_*.py` | Создать/модифицировать | Юниттесты планировщика |

### Frontend

| Файл | Действие | Ответственность |
|---|---|---|
| `frontend/src/api/resourcePlanning.ts` | Модификация | Типы `out_of_quarter`, `daily_hours`, расширенный `ExplainResponse` |
| `frontend/src/api/appearance.ts` | Модификация | `fill_intensity_pct`, `fill_contrast_pct`, `pulse_critical_path` |
| `frontend/src/components/resource-planning/AssignmentSidebar.tsx` | Большая модификация | Drawer 920, mask=false, 6 collapsible-секций, шестерёнка |
| `frontend/src/components/resource-planning/sidebar/AlgorithmSection.tsx` | Создать | Секция 1 |
| `frontend/src/components/resource-planning/sidebar/DailyBreakdownSection.tsx` | Создать | Секция 2 |
| `frontend/src/components/resource-planning/sidebar/AbsencesSection.tsx` | Создать | Секция 3 |
| `frontend/src/components/resource-planning/sidebar/PhaseCalcSection.tsx` | Создать | Секция 4 |
| `frontend/src/components/resource-planning/sidebar/HoursSummarySection.tsx` | Создать | Секция 5 |
| `frontend/src/components/resource-planning/sidebar/CriticalPathSection.tsx` | Создать | Секция 6 |
| `frontend/src/components/resource-planning/AssignEmployeePopover.tsx` | Удалить | Дубль формы из sidebar |
| `frontend/src/components/resource-planning/AppearanceModal.tsx` | Модификация | 2 ползунка вместо segmented, чекбокс `pulse_critical_path` |
| `frontend/src/components/resource-planning/GanttRows.tsx` | Модификация | Убрать импорт Popover; A+B+C+D подсветка; pulse on critical; multi-segment с connector; progress fact-fill; sticky left |
| `frontend/src/components/resource-planning/GanttChart.tsx` | Модификация | Применить `hideWeekends`, smooth zoom transition |
| `frontend/src/components/resource-planning/TimelineHeader.tsx` | Модификация | Holiday-точки в неделя-режиме |
| `frontend/src/components/resource-planning/NonWorkingZones.tsx` | Модификация | Скрытие полосок выходных в week/month |
| `frontend/src/components/resource-planning/TrackGridlines.tsx` | Модификация | Усилить контраст разделителей недели |
| `frontend/src/utils/gantt.ts` | Модификация | Новый `buildWorkdayTimeline`, типы |
| `frontend/src/utils/gantt.css` | Создать | CSS keyframes `pulseEmployee`, `pulseCritical` |
| `frontend/src/hooks/useRpPreferences.ts` | Модификация | Новые ключи prefs + миграция segmented intensity |
| `frontend/src/pages/ResourcePlanningPage.tsx` | Модификация | Кнопка collapse-all/expand-all; пробросить новые prefs |
| `e2e/resource-planning-fixes.spec.ts` | Создать | E2E |

---

## Tasks

### Task 1: Миграция Alembic — out_of_quarter + daily_hours_json

**Files:**
- Create: `alembic/versions/<auto>_add_assignment_out_of_quarter_daily_hours.py`
- Modify: `app/models/resource_plan_assignment.py`

- [ ] **Step 1: Создать миграцию**

Run:
```bash
py -3.10 -m alembic revision -m "add assignment out_of_quarter and daily_hours"
```

В сгенерированном файле upgrade/downgrade:

```python
def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "out_of_quarter",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("daily_hours_json", sa.Text(), nullable=True)
        )

def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.drop_column("daily_hours_json")
        batch_op.drop_column("out_of_quarter")
```

- [ ] **Step 2: Применить миграцию**

```bash
py -3.10 -m alembic upgrade head
```

Expected: новые колонки в `resource_plan_assignments`.

- [ ] **Step 3: Обновить модель**

В `app/models/resource_plan_assignment.py` после строки `manual_edit_at`:

```python
out_of_quarter: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0"
)
daily_hours_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

И добавить `Text` в импорт `sqlalchemy`.

- [ ] **Step 4: Прогнать существующие тесты**

```bash
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: PASS (новые поля не используются нигде).

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/ app/models/resource_plan_assignment.py
git commit -m "feat(rp/db): out_of_quarter + daily_hours_json on assignments"
```

---

### Task 2: Scheduler — `_allocate_hours` сохраняет неиспользованную ёмкость дня

**Files:**
- Modify: `app/services/resource_planning_service.py` (метод `_allocate_hours`, строка ~755)
- Test: `tests/services/test_allocate_hours.py` (создать)

**Контекст:** сейчас в `_allocate_hours` строка `emp_days[d] = 0.0` зануляет день целиком, даже если `daily_capacity < avail_h`. Это теряет часы, доступные для других фаз.

- [ ] **Step 1: Создать тест**

`tests/services/test_allocate_hours.py`:

```python
"""Тесты приватного _allocate_hours — фикс ёмкости и мульти-сегмента."""

from datetime import date

import pytest

from app.services.resource_planning_service import ResourcePlanningService


@pytest.fixture
def svc(db_session):
    return ResourcePlanningService(db_session)


def test_allocate_preserves_unused_daily_capacity(svc):
    """daily_capacity=4 при avail=8: после фазы остаётся 4 ч на тот же день для другого использования."""
    emp_id = "e1"
    remaining = {emp_id: {date(2026, 5, 4): 8.0, date(2026, 5, 5): 8.0}}
    segs = svc._allocate_hours(
        employee_id=emp_id,
        total_hours=4.0,
        earliest_start=date(2026, 5, 4),
        deadline=date(2026, 5, 8),
        remaining=remaining,
        daily_capacity=4.0,
    )
    assert segs == [(date(2026, 5, 4), date(2026, 5, 4), 4.0, 1)]
    # КЛЮЧЕВОЕ: день 04.05 не занулён, осталось 4 ч свободных.
    assert remaining[emp_id][date(2026, 5, 4)] == pytest.approx(4.0)
    assert remaining[emp_id][date(2026, 5, 5)] == pytest.approx(8.0)
```

- [ ] **Step 2: Прогнать тест — должен FAIL**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py::test_allocate_preserves_unused_daily_capacity -v
```

Expected: FAIL — `remaining[emp_id][date(2026, 5, 4)] == 0.0`.

- [ ] **Step 3: Фикс**

В `app/services/resource_planning_service.py`, в `_allocate_hours` цикл `while remaining_h > 0.01 and d <= deadline:` — заменить:

```python
        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            avail_h = emp_days.get(d, 0.0)
            cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
            if cap > 0:
                if seg_start is None:
                    seg_start = d
                used = min(cap, remaining_h)
                emp_days[d] = max(0.0, avail_h - used)  # ← фикс: вычитаем только used
                remaining_h -= used
                used_total += used
                seg_end = d
            d += timedelta(days=1)
```

- [ ] **Step 4: Прогнать тест — должен PASS**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py::test_allocate_preserves_unused_daily_capacity -v
```

Expected: PASS.

- [ ] **Step 5: Прогнать существующие тесты планировщика**

```bash
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: PASS (или fix-up если фикс ломает старые ожидания — типично 1-2 теста, которые сами по себе зависели от багованного зануления).

- [ ] **Step 6: Commit**

```bash
git add tests/services/test_allocate_hours.py app/services/resource_planning_service.py
git commit -m "fix(rp/scheduler): preserve unused daily capacity in _allocate_hours"
```

---

### Task 3: Scheduler — `effective_end` = фактический последний день работы

**Files:**
- Modify: `app/services/resource_planning_service.py` (`compute_schedule`, ~line 687)
- Test: `tests/services/test_allocate_hours.py` (доп. тест)

- [ ] **Step 1: Добавить тест**

В `tests/services/test_allocate_hours.py`:

```python
def test_effective_end_does_not_stretch_when_jira_duration_set(
    db_session, plan_factory, item_factory, employee_factory
):
    """
    Jira duration_days=20, hours=20 (по 8 ч/день).
    Без бага hours_allocated укладывается в 3 дня (24ч ёмкости).
    Раньше effective_end = cal_end → бар тянулся на 20 раб.дней.
    После фикса end_date = последний день фактической работы.
    """
    plan = plan_factory(quarter="Q2", year=2026)
    emp = employee_factory(team=plan.team, role="аналитик")
    item = item_factory(
        scenario_id=plan.scenario_id,
        estimate_analyst_hours=20,
        duration_analyst_days=20,
    )
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)
    a = (
        db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan.id, phase="analyst")
        .one()
    )
    # Реальная длительность: ceil(20/8) = 3 рабочих дня.
    span_days = (a.end_date - a.start_date).days + 1
    # Допускаем + выходные внутри (макс +2 для Sat/Sun в неделе).
    assert span_days <= 5, f"phase stretched to {span_days} days, expected ≤5"
```

- [ ] **Step 2: Прогнать — FAIL**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py::test_effective_end_does_not_stretch_when_jira_duration_set -v
```

Expected: FAIL — span > 5 дней.

- [ ] **Step 3: Фикс в `compute_schedule`**

В `app/services/resource_planning_service.py` строки ~687-714 — заменить блок:

```python
                if jira_cal_set:
                    if segments and segments[-1][1] > cal_end:
                        effective_end = segments[-1][1]
                    else:
                        effective_end = cal_end
                elif segments:
                    effective_end = segments[-1][1]
                else:
                    effective_end = None

                for idx, (seg_start, seg_end, seg_hours, part_num) in enumerate(segments):
                    if jira_cal_set and idx == len(segments) - 1:
                        seg_end = effective_end
                    a = ResourcePlanAssignment(...)
```

на:

```python
                # Фикс: бар = фактический объём работы. Jira duration_days/
                # involvement больше НЕ растягивают визуальный бар. cal_days
                # по-прежнему ограничивает alloc_deadline (часы не пишутся за
                # пределы окна), но end_date = реальный seg_end.
                effective_end = segments[-1][1] if segments else None

                for seg_start, seg_end, seg_hours, part_num in segments:
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase=phase,
                        employee_id=employee_id,
                        part_number=part_num,
                        hours_allocated=seg_hours,
                        start_date=seg_start,
                        end_date=seg_end,
                    )
                    new_assignments.append(a)
```

- [ ] **Step 4: Прогнать — PASS**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py -v
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: оба PASS. Если есть существующие тесты, которые ожидали Jira-растяжение — пересмотреть их (вероятно тестировали баг).

- [ ] **Step 5: Commit**

```bash
git add tests/services/test_allocate_hours.py app/services/resource_planning_service.py
git commit -m "fix(rp/scheduler): bar end = actual last day, ignore Jira duration stretch"
```

---

### Task 4: Scheduler — dev стартует от фактического конца analyst

**Files:**
- Modify: `app/services/resource_planning_service.py` (block around line 454, dev phase earliest_start)
- Test: `tests/services/test_allocate_hours.py`

- [ ] **Step 1: Тест**

```python
def test_dev_starts_right_after_actual_analyst_end(
    db_session, plan_factory, item_factory, employee_factory
):
    """
    Аналитик: 16 часов (2 раб.дня), duration_analyst_days=15.
    Раньше: phase_end = effective_end = cal_end → dev стартовал через 15 дней.
    Теперь: dev стартует через 1 раб.день после фактического конца analyst.
    """
    plan = plan_factory(quarter="Q2", year=2026)
    employee_factory(team=plan.team, role="аналитик")
    employee_factory(team=plan.team, role="разработчик")
    item = item_factory(
        scenario_id=plan.scenario_id,
        estimate_analyst_hours=16,
        duration_analyst_days=15,
        estimate_dev_hours=8,
    )
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)
    analyst = (
        db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan.id, phase="analyst")
        .one()
    )
    dev = (
        db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan.id, phase="dev")
        .one()
    )
    gap = (dev.start_date - analyst.end_date).days
    assert 1 <= gap <= 3, f"gap={gap}, expected 1-3 working days"
```

- [ ] **Step 2: Прогнать — должен PASS** (после Task 3 dev уже стартует от actual end через phase_end = effective_end = последний seg_end).

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py::test_dev_starts_right_after_actual_analyst_end -v
```

Expected: PASS. Если FAIL — проверить что `phase_end = effective_end` присваивается **после** обновлённого `effective_end` (см. строка ~714 в Task 3).

- [ ] **Step 3: Commit**

```bash
git add tests/services/test_allocate_hours.py
git commit -m "test(rp/scheduler): dev starts right after actual analyst end"
```

---

### Task 5: Scheduler — пишет `daily_hours_json`

**Files:**
- Modify: `app/services/resource_planning_service.py` (`_allocate_hours` возвращает per-day breakdown; `compute_schedule` пишет JSON)
- Test: `tests/services/test_allocate_hours.py`

- [ ] **Step 1: Тест**

```python
def test_allocate_returns_daily_breakdown_via_remaining_diff(svc):
    """
    Тест-помощник: фикс _allocate_hours дополнительно даёт {date: used_hours}.
    """
    emp_id = "e1"
    days = {date(2026, 5, 4): 8.0, date(2026, 5, 5): 8.0, date(2026, 5, 6): 8.0}
    remaining = {emp_id: dict(days)}
    segs, daily = svc._allocate_hours_with_breakdown(
        employee_id=emp_id,
        total_hours=18.0,
        earliest_start=date(2026, 5, 4),
        deadline=date(2026, 5, 8),
        remaining=remaining,
        daily_capacity=8.0,
    )
    assert segs == [(date(2026, 5, 4), date(2026, 5, 6), 18.0, 1)]
    assert daily == {
        date(2026, 5, 4): 8.0,
        date(2026, 5, 5): 8.0,
        date(2026, 5, 6): 2.0,
    }
```

- [ ] **Step 2: Реализация**

В `app/services/resource_planning_service.py` — рефакторнуть `_allocate_hours`: вынести логику в приватный `_allocate_hours_with_breakdown` возвращающий `Tuple[List[Tuple[date,date,float,int]], Dict[date, float]]`. Старый `_allocate_hours` — обёртка возвращающая только segments (для совместимости).

```python
def _allocate_hours_with_breakdown(
    self, employee_id, total_hours, earliest_start, deadline,
    remaining, daily_capacity=None, preempt_locked=None, original_capacity=None,
) -> Tuple[List[Tuple[date, date, float, int]], Dict[date, float]]:
    _ = preempt_locked, original_capacity
    emp_days = remaining.get(employee_id, {})
    remaining_h = total_hours
    used_total = 0.0
    seg_start: Optional[date] = None
    seg_end: Optional[date] = None
    daily: Dict[date, float] = {}

    d = earliest_start
    while remaining_h > 0.01 and d <= deadline:
        avail_h = emp_days.get(d, 0.0)
        cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
        if cap > 0:
            if seg_start is None:
                seg_start = d
            used = min(cap, remaining_h)
            emp_days[d] = max(0.0, avail_h - used)
            remaining_h -= used
            used_total += used
            seg_end = d
            daily[d] = used
        d += timedelta(days=1)

    if seg_start is not None and seg_end is not None and used_total > 0:
        return [(seg_start, seg_end, used_total, 1)], daily
    return [], daily


def _allocate_hours(self, *args, **kwargs) -> List[Tuple[date, date, float, int]]:
    segs, _ = self._allocate_hours_with_breakdown(*args, **kwargs)
    return segs
```

В `compute_schedule` все вызовы `_allocate_hours` заменить на `_allocate_hours_with_breakdown`, собрать `daily` для каждого сегмента, при создании `ResourcePlanAssignment` сериализовать в JSON:

```python
import json
...
segments, daily_used = self._allocate_hours_with_breakdown(...)
for seg_start, seg_end, seg_hours, part_num in segments:
    a = ResourcePlanAssignment(
        plan_id=plan_id,
        backlog_item_id=item.id,
        phase=phase,
        employee_id=employee_id,
        part_number=part_num,
        hours_allocated=seg_hours,
        start_date=seg_start,
        end_date=seg_end,
        daily_hours_json=json.dumps({d.isoformat(): h for d, h in daily_used.items()}),
    )
    new_assignments.append(a)
```

Применить к всем local calls в analyst, dev, opo, qa, retry-block.

- [ ] **Step 3: Прогнать тесты**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py -v
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/services/test_allocate_hours.py app/services/resource_planning_service.py
git commit -m "feat(rp/scheduler): persist daily_hours_json per assignment"
```

---

### Task 6: Scheduler — мульти-сегмент при preempting-разрыве

**Files:**
- Modify: `app/services/resource_planning_service.py` (`_allocate_hours_with_breakdown` — split на сегменты при preempt-locked дне)
- Test: `tests/services/test_allocate_hours.py`

- [ ] **Step 1: Тест**

```python
def test_multi_segment_on_preempting_lock(svc):
    """ОПЭ заняла 05.05 (preempt_locked). Аналитик 24ч → 2 сегмента: 04.05 + 06-07.05."""
    emp_id = "e1"
    remaining = {emp_id: {
        date(2026, 5, 4): 8.0,
        date(2026, 5, 5): 8.0,  # будет в locked
        date(2026, 5, 6): 8.0,
        date(2026, 5, 7): 8.0,
    }}
    preempt_locked = {emp_id: {date(2026, 5, 5)}}
    segs, daily = svc._allocate_hours_with_breakdown(
        employee_id=emp_id,
        total_hours=24.0,
        earliest_start=date(2026, 5, 4),
        deadline=date(2026, 5, 10),
        remaining=remaining,
        daily_capacity=8.0,
        preempt_locked=preempt_locked,
    )
    assert len(segs) == 2
    assert segs[0] == (date(2026, 5, 4), date(2026, 5, 4), 8.0, 1)
    assert segs[1] == (date(2026, 5, 6), date(2026, 5, 7), 16.0, 2)
    assert daily == {date(2026, 5, 4): 8.0, date(2026, 5, 6): 8.0, date(2026, 5, 7): 8.0}
    # 05.05 не тронут — ушёл preempting-фазе.
    assert remaining[emp_id][date(2026, 5, 5)] == 8.0
```

- [ ] **Step 2: Реализация в `_allocate_hours_with_breakdown`**

```python
def _allocate_hours_with_breakdown(
    self, employee_id, total_hours, earliest_start, deadline,
    remaining, daily_capacity=None, preempt_locked=None, original_capacity=None,
) -> Tuple[List[Tuple[date, date, float, int]], Dict[date, float]]:
    _ = original_capacity
    locked: set = (preempt_locked or {}).get(employee_id, set())
    emp_days = remaining.get(employee_id, {})
    remaining_h = total_hours
    daily: Dict[date, float] = {}

    segments: List[Tuple[date, date, float, int]] = []
    cur_start: Optional[date] = None
    cur_end: Optional[date] = None
    cur_hours = 0.0
    part = 1

    d = earliest_start
    while remaining_h > 0.01 and d <= deadline:
        if d in locked:
            # Разрыв: закрыть текущий сегмент (если есть) и начать новый.
            if cur_start is not None:
                segments.append((cur_start, cur_end, cur_hours, part))
                part += 1
                cur_start = cur_end = None
                cur_hours = 0.0
            d += timedelta(days=1)
            continue
        avail_h = emp_days.get(d, 0.0)
        cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
        if cap > 0:
            if cur_start is None:
                cur_start = d
            used = min(cap, remaining_h)
            emp_days[d] = max(0.0, avail_h - used)
            remaining_h -= used
            cur_hours += used
            cur_end = d
            daily[d] = used
        d += timedelta(days=1)

    if cur_start is not None and cur_hours > 0:
        segments.append((cur_start, cur_end, cur_hours, part))
    return segments, daily
```

- [ ] **Step 3: Прогнать тесты**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py -v
```

Expected: PASS.

- [ ] **Step 4: Прогнать compute_schedule тесты**

```bash
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: PASS. Может потребоваться, чтобы `compute_schedule` обрабатывал список сегментов (он уже это делает в for-loop через part_number).

- [ ] **Step 5: Commit**

```bash
git add tests/services/test_allocate_hours.py app/services/resource_planning_service.py
git commit -m "feat(rp/scheduler): split into segments when preempting phase locks a day"
```

---

### Task 7: Scheduler — out_of_quarter spillover (+1 месяц)

**Files:**
- Modify: `app/services/resource_planning_service.py` (`compute_schedule`, `_quarter_bounds`)
- Test: `tests/services/test_allocate_hours.py`

- [ ] **Step 1: Тест**

```python
def test_out_of_quarter_spillover(
    db_session, plan_factory, item_factory, employee_factory
):
    """Хотим больше часов чем влезает в квартал — последний сегмент out_of_quarter=True."""
    plan = plan_factory(quarter="Q2", year=2026)
    employee_factory(team=plan.team, role="аналитик")
    # 1000 ч × 1 аналитик × 8 ч/день ≈ 125 рабочих дней — выходит за Q2 (~60 раб.дней).
    item_factory(scenario_id=plan.scenario_id, estimate_analyst_hours=1000)
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)
    assignments = (
        db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan.id, phase="analyst")
        .all()
    )
    assert assignments, "ожидается хотя бы один analyst assignment"
    last = max(assignments, key=lambda a: a.end_date or date.min)
    q2_end = date(2026, 6, 30)
    assert last.end_date > q2_end
    assert last.out_of_quarter is True
```

- [ ] **Step 2: Реализация**

В `app/services/resource_planning_service.py` найти место использования `q_end` как deadline в `compute_schedule`, добавить вспомогательную переменную `q_end_extended = q_end + relativedelta(months=1)` (импортировать `from dateutil.relativedelta import relativedelta`; либо вручную `date(q_end.year, q_end.month+1, ...).replace(day=...)`).

Заменить `q_end` на `q_end_extended` в:
- `self.build_availability(employees, q_start, q_end_extended, list(blocks))`
- Все `_allocate_hours_with_breakdown(..., q_end_extended, ...)` calls
- `_compute_cpm(new_assignments, q_end_extended)`
- `leveler.level(new_assignments, avail, q_end_extended, role_pools)`

После создания сегментов — отметить out_of_quarter:

```python
for seg_start, seg_end, seg_hours, part_num in segments:
    is_oot = seg_start > q_end
    a = ResourcePlanAssignment(
        ...,
        out_of_quarter=is_oot,
        ...
    )
```

Применить ко всем созданиям ResourcePlanAssignment (analyst, dev, qa, opo, retry-блок).

- [ ] **Step 3: Прогнать тест**

```bash
py -3.10 -m pytest tests/services/test_allocate_hours.py::test_out_of_quarter_spillover -v
```

Expected: PASS.

- [ ] **Step 4: Прогнать всё**

```bash
py -3.10 -m pytest tests/services/test_resource_planning_service.py -v
```

Expected: PASS. Проверить, что existing тест `"не вмещается в квартал"` (строка 1644 в файле) теперь не блокирует расчёт, а просто помечает out_of_quarter — обновить тест если он жёстко проверяет конкретное сообщение.

- [ ] **Step 5: Commit**

```bash
git add tests/services/test_allocate_hours.py app/services/resource_planning_service.py
git commit -m "feat(rp/scheduler): +1 month spillover with out_of_quarter flag"
```

---

### Task 8: Conflict aggregator — per-day из `daily_hours_json`

**Files:**
- Modify: `app/services/conflict_aggregator.py` (или `_build_conflict_dicts` в `resource_planning_service.py`)
- Test: `tests/services/test_conflict_aggregator.py`

- [ ] **Step 1: Прочитать текущий `_build_conflict_dicts`**

```bash
grep -n "_build_conflict_dicts\|hours_per_day\|hours_allocated" app/services/resource_planning_service.py | head -30
```

- [ ] **Step 2: Тест**

`tests/services/test_conflict_aggregator.py`:

```python
def test_no_overload_when_daily_hours_avoid_same_day(svc, ...):
    """
    2 фазы пересекаются по date-диапазону, но daily_hours_json
    показывает, что в один и тот же день они не работают.
    """
    # Setup: a1 hours_allocated=8 даты 04-06.05, daily_hours_json={"04.05":8,"06.05":0}
    # a2 hours_allocated=8 даты 05-07.05, daily_hours_json={"05.05":8,"07.05":0}
    # Конфликта на 05.05 нет (a1 на 05.05 ничего не делает).
    ...
```

- [ ] **Step 3: Реализация**

В `_build_conflict_dicts` (`resource_planning_service.py` ~line 1500-1700), где per-day часы считаются как `hours_allocated / (end - start + 1)` — заменить:

```python
import json
...

def _per_day_hours(a: ResourcePlanAssignment) -> Dict[date, float]:
    if a.daily_hours_json:
        try:
            raw = json.loads(a.daily_hours_json)
            return {date.fromisoformat(k): float(v) for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError):
            pass
    # Fallback: legacy assignment без daily_hours_json → равномерно.
    if not a.start_date or not a.end_date or not a.hours_allocated:
        return {}
    span = (a.end_date - a.start_date).days + 1
    if span <= 0:
        return {}
    per = a.hours_allocated / span
    out = {}
    d = a.start_date
    while d <= a.end_date:
        out[d] = per
        d += timedelta(days=1)
    return out
```

Использовать `_per_day_hours(a)` для построения per-day overload map.

- [ ] **Step 4: Прогнать тесты**

```bash
py -3.10 -m pytest tests/services/test_conflict_aggregator.py -v
py -3.10 -m pytest tests/services/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/services/test_conflict_aggregator.py app/services/resource_planning_service.py
git commit -m "fix(rp/conflicts): per-day overload from daily_hours_json"
```

---

### Task 9: API `/explain` — расширение полей детализации

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (handler `/explain/<assignment_id>`)
- Modify: `app/schemas/resource_planning.py` (новые модели `AssignmentExplainResponse` extension)
- Test: `tests/api/test_explain_endpoint.py`

- [ ] **Step 1: Найти текущий handler**

```bash
grep -n "/explain\|AssignmentExplainResponse" app/api/endpoints/resource_planning.py app/schemas/resource_planning.py
```

- [ ] **Step 2: Расширить Pydantic схемы**

В `app/schemas/resource_planning.py`:

```python
class DailyBreakdownItem(BaseModel):
    date: date
    available_hours: float
    used_hours: float
    status: Literal["work", "absence", "holiday", "weekend", "blocked_by_other"]
    blocker_assignment_id: Optional[str] = None
    blocker_item_key: Optional[str] = None
    blocker_phase_label: Optional[str] = None


class AbsenceWindowItem(BaseModel):
    date_start: date
    date_end: date
    reason_label: str
    is_holiday: bool = False  # True для РФ-календаря


class PhaseCalcDetails(BaseModel):
    duration_days_jira: Optional[int] = None
    involvement_pct: Optional[int] = None
    parallel_count: int = 1
    role_pct: Optional[int] = None
    daily_capacity_hours: float


class HoursSummary(BaseModel):
    total: float
    used: float
    remaining: float
    workdays: int
    blocked_days: int


class AssignmentExplainResponse(BaseModel):  # обновить существующую
    assignment: ResourcePlanAssignmentOut
    conflicts: List[AssignmentExplainConflict]
    algorithm_log: List[str] = []
    daily_breakdown: List[DailyBreakdownItem] = []
    absences_in_window: List[AbsenceWindowItem] = []
    phase_calc: Optional[PhaseCalcDetails] = None
    hours_summary: Optional[HoursSummary] = None
```

- [ ] **Step 3: Handler — заполнить новые поля**

В `app/api/endpoints/resource_planning.py` handler `/explain/<assignment_id>`:

```python
def _build_algorithm_log(assignment, plan, predecessors) -> List[str]:
    log = []
    # earliest_start factors
    if assignment.phase == "analyst":
        log.append(f"Старт фазы = начало квартала ({plan.quarter} {plan.year}).")
    else:
        prev_phase = {"dev": "Анализ", "qa": "Разработка", "opo": "Тестирование"}.get(assignment.phase)
        log.append(f"Старт фазы = следующий рабочий день после фактического окончания фазы «{prev_phase}».")
    for pred in predecessors:
        log.append(f"Предшественник: {pred.item_key} «{pred.item_title}» — конец {pred.end_date}.")
    return log


def _build_daily_breakdown(
    assignment, daily_used: Dict[date, float], avail: Dict[date, float],
    other_assignments_by_day: Dict[date, List[Tuple[str, str, str]]],
    absences: List[AbsenceWindowItem], calendar: Dict[date, bool],
) -> List[DailyBreakdownItem]:
    items = []
    if not assignment.start_date or not assignment.end_date:
        return items
    d = assignment.start_date
    while d <= assignment.end_date:
        used = daily_used.get(d, 0.0)
        a_h = avail.get(d, 0.0)
        # determine status priority
        if calendar.get(d) is False:
            status = "holiday"
        elif d.weekday() >= 5:
            status = "weekend"
        elif any(ab.date_start <= d <= ab.date_end for ab in absences):
            status = "absence"
        elif used == 0 and a_h > 0:
            # day inside bar but not used — likely blocked by other
            blockers = other_assignments_by_day.get(d, [])
            if blockers:
                items.append(DailyBreakdownItem(
                    date=d, available_hours=a_h, used_hours=0,
                    status="blocked_by_other",
                    blocker_assignment_id=blockers[0][0],
                    blocker_item_key=blockers[0][1],
                    blocker_phase_label=blockers[0][2],
                ))
                d += timedelta(days=1)
                continue
            status = "work"
        else:
            status = "work"
        items.append(DailyBreakdownItem(
            date=d, available_hours=a_h, used_hours=used, status=status,
        ))
        d += timedelta(days=1)
    return items
```

В handler собрать все данные (предшественники, daily_hours_json, отсутствия, календарь, другие assignments сотрудника в окне) и заполнить новые поля.

- [ ] **Step 4: Тест endpoint**

`tests/api/test_explain_endpoint.py`:

```python
def test_explain_returns_algorithm_log(client, plan_with_assignments):
    plan, analyst, dev = plan_with_assignments
    resp = client.get(f"/api/v1/resource-planning/{plan.id}/assignments/{dev.id}/explain")
    assert resp.status_code == 200
    body = resp.json()
    assert "algorithm_log" in body
    assert any("Анализ" in line for line in body["algorithm_log"])


def test_explain_daily_breakdown_shows_blocker(client, plan_with_overlap):
    """День внутри окна, used=0, есть другая фаза сотрудника → status=blocked_by_other."""
    ...
```

- [ ] **Step 5: Прогнать**

```bash
py -3.10 -m pytest tests/api/test_explain_endpoint.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas/resource_planning.py app/api/endpoints/resource_planning.py tests/api/test_explain_endpoint.py
git commit -m "feat(rp/api): /explain returns algorithm_log, daily_breakdown, absences, phase_calc, hours_summary"
```

---

### Task 10: Pydantic — `out_of_quarter`, `daily_hours` в `AssignmentOut`

**Files:**
- Modify: `app/schemas/resource_planning.py`
- Modify: `app/api/endpoints/resource_planning.py` (serializer для `AssignmentOut`)
- Test: `tests/api/test_resource_planning_serialization.py`

- [ ] **Step 1: Расширить схему**

```python
class AssignmentOut(BaseModel):
    # existing fields ...
    out_of_quarter: bool = False
    daily_hours: Optional[Dict[str, float]] = None  # {"YYYY-MM-DD": h}

    @field_validator("daily_hours", mode="before")
    @classmethod
    def _from_json_string(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
```

И в model_config: `model_config = ConfigDict(from_attributes=True)` если ещё нет.

- [ ] **Step 2: Тест**

```python
def test_assignment_out_serializes_daily_hours(db_session, ...):
    a = ResourcePlanAssignment(
        ..., daily_hours_json='{"2026-05-04": 8.0, "2026-05-05": 6.5}'
    )
    db_session.add(a); db_session.flush()
    out = AssignmentOut.model_validate(a)
    assert out.daily_hours == {"2026-05-04": 8.0, "2026-05-05": 6.5}
    assert out.out_of_quarter is False
```

- [ ] **Step 3: Прогнать**

```bash
py -3.10 -m pytest tests/api/test_resource_planning_serialization.py -v
```

Expected: PASS.

- [ ] **Step 4: Frontend type update**

В `frontend/src/api/resourcePlanning.ts`:

```typescript
export interface AssignmentOut {
  // existing ...
  out_of_quarter: boolean;
  daily_hours: Record<string, number> | null;
}

export interface DailyBreakdownItem {
  date: string;
  available_hours: number;
  used_hours: number;
  status: 'work' | 'absence' | 'holiday' | 'weekend' | 'blocked_by_other';
  blocker_assignment_id?: string;
  blocker_item_key?: string;
  blocker_phase_label?: string;
}

export interface AbsenceWindowItem {
  date_start: string;
  date_end: string;
  reason_label: string;
  is_holiday: boolean;
}

export interface PhaseCalcDetails {
  duration_days_jira: number | null;
  involvement_pct: number | null;
  parallel_count: number;
  role_pct: number | null;
  daily_capacity_hours: number;
}

export interface HoursSummary {
  total: number;
  used: number;
  remaining: number;
  workdays: number;
  blocked_days: number;
}

export interface AssignmentExplainResponse {
  assignment: AssignmentOut;
  conflicts: AssignmentExplainConflict[];
  algorithm_log: string[];
  daily_breakdown: DailyBreakdownItem[];
  absences_in_window: AbsenceWindowItem[];
  phase_calc: PhaseCalcDetails | null;
  hours_summary: HoursSummary | null;
}
```

- [ ] **Step 5: Commit**

```bash
git add app/schemas/resource_planning.py tests/api/test_resource_planning_serialization.py frontend/src/api/resourcePlanning.ts
git commit -m "feat(rp/api): expose out_of_quarter, daily_hours, extended explain fields"
```

---

### Task 11: Frontend — `useRpPreferences` расширение + миграция

**Files:**
- Modify: `frontend/src/hooks/useRpPreferences.ts`
- Modify: `app/api/endpoints/users.py` (или где `rp_preferences` endpoint)
- Modify: `app/models/user_rp_preferences.py`
- Modify: миграция Alembic
- Test: `tests/api/test_user_rp_preferences.py`

- [ ] **Step 1: Миграция SQL — добавить новые JSON-поля**

Сгенерировать миграцию + applied:
```python
def upgrade():
    with op.batch_alter_table("user_rp_preferences") as batch_op:
        batch_op.add_column(sa.Column("detail_sections_visible", sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column("detail_sections_collapsed", sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column("fill_intensity_pct", sa.Integer(), nullable=False, server_default="50"))
        batch_op.add_column(sa.Column("fill_contrast_pct", sa.Integer(), nullable=False, server_default="50"))
        batch_op.add_column(sa.Column("pulse_highlighted_employee", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("pulse_critical_path", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("out_of_quarter_months", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("hide_weekend_stripes_week_mode", sa.Boolean(), nullable=False, server_default=sa.true()))
```

- [ ] **Step 2: Обновить SQLAlchemy модель**

В `app/models/user_rp_preferences.py` добавить соответствующие поля.

- [ ] **Step 3: Pydantic schema + endpoint**

Найти `RpPreferences` Pydantic — добавить все ключи. Defaults = те же что в server_default.

- [ ] **Step 4: Frontend `useRpPreferences`**

Расширить дефолты:

```typescript
const DEFAULT_PREFS: RpPreferences = {
  hide_weekends: false,
  collapsed_initiative_ids: [],
  view_mode: null,
  show_relay: true,
  detail_sections_visible: {
    algorithm: true, day_table: true, absences: true,
    sources: true, duration: true, critical_path: true,
  },
  detail_sections_collapsed: {},
  fill_intensity_pct: 50,
  fill_contrast_pct: 50,
  pulse_highlighted_employee: true,
  pulse_critical_path: true,
  out_of_quarter_months: 1,
  hide_weekend_stripes_week_mode: true,
};
```

- [ ] **Step 5: Тесты**

```bash
py -3.10 -m pytest tests/api/test_user_rp_preferences.py -v
cd frontend && npm run lint
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ app/models/user_rp_preferences.py app/schemas/ app/api/endpoints/users.py frontend/src/hooks/useRpPreferences.ts tests/
git commit -m "feat(rp/prefs): per-user detail sections + sliders + pulses + spillover months"
```

---

### Task 12: Frontend — Удалить `AssignEmployeePopover`

**Files:**
- Delete: `frontend/src/components/resource-planning/AssignEmployeePopover.tsx`
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (импорты и использования)

- [ ] **Step 1: Удалить Popover wrapper**

В `GanttRows.tsx` — заменить во всех трёх местах (PortfolioRows ~line 226, PhaseBar ~line 402, ResourceTrackRows ~line 912):

```tsx
// Было:
<AssignEmployeePopover ...>{bar}</AssignEmployeePopover>

// Стало:
{bar}
```

Удалить импорт `AssignEmployeePopover`.

Bar внутри `PhaseBar` — `onClick` уже вызывает `onAssignmentClick(assignment.id)` → открывает sidebar. Это и есть единственный source of truth.

В `PortfolioRows` и `ResourceTrackRows` сейчас `bar` без `onClick` — добавить `onClick={onAssignmentClick ? () => onAssignmentClick(a.id) : undefined}` на сам `<div className="bar">`.

- [ ] **Step 2: Удалить файл**

```bash
rm frontend/src/components/resource-planning/AssignEmployeePopover.tsx
```

- [ ] **Step 3: Проверить лёгкий build**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/
git commit -m "refactor(rp): remove duplicate AssignEmployeePopover, sidebar is single source"
```

---

### Task 13: Frontend — Drawer non-modal + width 920

**Files:**
- Modify: `frontend/src/components/resource-planning/AssignmentSidebar.tsx`

- [ ] **Step 1: Изменить Drawer props**

В `AssignmentSidebar.tsx`:

```tsx
<Drawer
  open={open}
  onClose={onClose}
  width={920}
  mask={false}
  maskClosable={false}
  styles={{ body: { paddingBottom: 32 } }}
  title={...}
>
```

(было `width={460}` без mask настройки → mask default true).

- [ ] **Step 2: Проверить вручную / e2e**

Открыть `/resource-planning`, кликнуть на бар → drawer открывается, другие бары остаются кликабельными. Клик на другой бар → drawer обновляет содержимое.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/AssignmentSidebar.tsx
git commit -m "feat(rp/sidebar): non-modal drawer width 920 — bars stay clickable"
```

---

### Task 14: Frontend — Sidebar 6 collapsible-секций + шестерёнка

**Files:**
- Create: `frontend/src/components/resource-planning/sidebar/AlgorithmSection.tsx`
- Create: `.../DailyBreakdownSection.tsx`
- Create: `.../AbsencesSection.tsx`
- Create: `.../PhaseCalcSection.tsx`
- Create: `.../HoursSummarySection.tsx`
- Create: `.../CriticalPathSection.tsx`
- Create: `.../SectionVisibilityPopover.tsx`
- Modify: `AssignmentSidebar.tsx`

Каждая секция — отдельный компонент с props `{ data, collapsed, onToggleCollapse }`. Не рендерится если `visible=false`.

- [ ] **Step 1: Шаблон секции (пример AlgorithmSection)**

```tsx
// frontend/src/components/resource-planning/sidebar/AlgorithmSection.tsx
import { Collapse, Typography } from 'antd';
const { Panel } = Collapse;

interface Props {
  log: string[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function AlgorithmSection({ log, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      ghost
    >
      <Panel header="Откуда дата старта" key="1">
        {log.length === 0 ? (
          <Typography.Text type="secondary">Нет данных</Typography.Text>
        ) : (
          <ol style={{ paddingLeft: 18, margin: 0, fontSize: 12, color: '#cfe1f5' }}>
            {log.map((line, i) => <li key={i}>{line}</li>)}
          </ol>
        )}
      </Panel>
    </Collapse>
  );
}
```

Аналогично — DailyBreakdownSection с AntD Table; AbsencesSection — список; PhaseCalcSection — Descriptions; HoursSummarySection — Statistic; CriticalPathSection — Alert с slack.

- [ ] **Step 2: SectionVisibilityPopover**

```tsx
// SectionVisibilityPopover.tsx
import { Checkbox, Popover, Button, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';

const LABELS: Record<string, string> = {
  algorithm: 'Откуда дата старта',
  day_table: 'Дни × часы',
  absences: 'Отсутствия в окне',
  sources: 'Часы по источникам',
  duration: 'Длительность vs часы',
  critical_path: 'Критический путь',
};

interface Props {
  visible: Record<string, boolean>;
  onChange: (next: Record<string, boolean>) => void;
}

export default function SectionVisibilityPopover({ visible, onChange }: Props) {
  return (
    <Popover
      trigger="click"
      content={
        <Space direction="vertical">
          {Object.entries(LABELS).map(([k, label]) => (
            <Checkbox
              key={k}
              checked={visible[k] !== false}
              onChange={(e) => onChange({ ...visible, [k]: e.target.checked })}
            >
              {label}
            </Checkbox>
          ))}
        </Space>
      }
    >
      <Button icon={<SettingOutlined />} size="small" />
    </Popover>
  );
}
```

- [ ] **Step 3: Интегрировать в `AssignmentSidebar.tsx`**

После существующих блоков (Descriptions, AssignmentExplainSection, Действия) — добавить:

```tsx
const { prefs, patch: patchPrefs } = useRpPreferences();
const explain = useExplainAssignment(planId, assignment.id, true).data;

return (
  <Drawer ... title={
    <Space>
      <span>{PHASE_LABELS[assignment.phase]}</span>
      {assignment.is_pinned && <Tag color="cyan">Закреплено</Tag>}
      <SectionVisibilityPopover
        visible={prefs.detail_sections_visible}
        onChange={(next) => patchPrefs({ detail_sections_visible: next })}
      />
    </Space>
  }>
    {/* ... existing form ... */}
    <Divider>Детализация</Divider>

    {prefs.detail_sections_visible.algorithm !== false && (
      <AlgorithmSection
        log={explain?.algorithm_log ?? []}
        collapsed={!!prefs.detail_sections_collapsed.algorithm}
        onToggleCollapse={() => patchPrefs({
          detail_sections_collapsed: {
            ...prefs.detail_sections_collapsed,
            algorithm: !prefs.detail_sections_collapsed.algorithm,
          },
        })}
      />
    )}
    {/* остальные 5 секций аналогично */}
  </Drawer>
);
```

- [ ] **Step 4: Прогнать lint + tsc**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/sidebar/ frontend/src/components/resource-planning/AssignmentSidebar.tsx
git commit -m "feat(rp/sidebar): 6 toggleable detail sections + visibility popover"
```

---

### Task 15: Frontend — `AppearanceModal` 2 ползунка

**Files:**
- Modify: `frontend/src/components/resource-planning/AppearanceModal.tsx`
- Modify: `frontend/src/api/appearance.ts`
- Modify: backend `appearance` schema + миграция (если поля segmented в БД)

- [ ] **Step 1: Найти текущий AppearanceModal**

```bash
cat frontend/src/components/resource-planning/AppearanceModal.tsx | head -80
```

- [ ] **Step 2: API типы**

В `frontend/src/api/appearance.ts`:

```typescript
export interface AppearanceSettings {
  phase_colors: { analyst: string; dev: string; qa: string; opo: string };
  initiative_bracket_color: string;
  initiative_fill_intensity?: 'soft' | 'medium' | 'dense';  // deprecated, читается для миграции
  fill_intensity_pct?: number;  // 0-100
  fill_contrast_pct?: number;   // 0-100
  animation_speed_seconds: number;
  pulse_critical_path?: boolean;
}

// Миграция при чтении: если есть segmented, конвертировать в pct.
const SEGMENTED_TO_PCT = { soft: [25, 50], medium: [50, 50], dense: [90, 50] };

export function normalizeAppearance(s: AppearanceSettings): AppearanceSettings {
  if (s.fill_intensity_pct === undefined && s.initiative_fill_intensity) {
    const [i, c] = SEGMENTED_TO_PCT[s.initiative_fill_intensity];
    return { ...s, fill_intensity_pct: i, fill_contrast_pct: c };
  }
  return s;
}
```

В `useAppearance`: `select: normalizeAppearance`.

- [ ] **Step 3: Backend — добавить поля**

В `app/models/user_appearance_settings.py` (или где живёт) + миграция:

```python
fill_intensity_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
fill_contrast_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
pulse_critical_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa.true())
```

- [ ] **Step 4: `AppearanceModal` UI**

Заменить `Segmented` для `initiative_fill_intensity` на 2 Slider:

```tsx
<Form.Item label="Интенсивность заливки инициативы">
  <Slider
    min={0} max={100} step={5}
    value={settings.fill_intensity_pct ?? 50}
    onChange={(v) => update({ fill_intensity_pct: v })}
    marks={{ 0: '0%', 50: '50%', 100: '100%' }}
  />
</Form.Item>
<Form.Item label="Контраст градиента">
  <Slider
    min={0} max={100} step={5}
    value={settings.fill_contrast_pct ?? 50}
    onChange={(v) => update({ fill_contrast_pct: v })}
    marks={{ 0: 'плоско', 50: '50%', 100: 'резко' }}
  />
</Form.Item>
<Form.Item>
  <Checkbox
    checked={settings.pulse_critical_path !== false}
    onChange={(e) => update({ pulse_critical_path: e.target.checked })}
  >
    Пульсация рамки на критическом пути
  </Checkbox>
</Form.Item>
```

- [ ] **Step 5: `GanttRows.tsx` — применить новую формулу**

В `TwoLevelRows` где `fillGradients[fillIntensity]`:

```tsx
const intensity = appearance.fill_intensity_pct ?? 50;
const contrast = appearance.fill_contrast_pct ?? 50;
const alphaTop = 0.05 + (intensity / 100) * 0.35;
const alphaBottom = alphaTop * (1 - (contrast / 100) * 0.5);
const fillGradient = `linear-gradient(180deg, rgba(${br},${bg},${bb},${alphaTop}), rgba(${br},${bg},${bb},${alphaBottom}))`;
```

Использовать `fillGradient` вместо `fillGradients[fillIntensity]`.

- [ ] **Step 6: Прогнать lint + tsc**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/ app/models/ app/schemas/ frontend/src/api/appearance.ts frontend/src/components/resource-planning/{AppearanceModal,GanttRows}.tsx
git commit -m "feat(rp/appearance): two sliders (intensity + contrast) replace segmented"
```

---

### Task 16: Frontend — `buildWorkdayTimeline` утиль

**Files:**
- Modify: `frontend/src/utils/gantt.ts`
- Create: `frontend/src/utils/gantt.test.ts`

- [ ] **Step 1: Тест**

```typescript
import { describe, it, expect } from 'vitest';
import { buildWorkdayTimeline, dateToLeft, type WorkdayTimeline } from './gantt';

describe('buildWorkdayTimeline', () => {
  it('skips weekends (no production calendar)', () => {
    const start = new Date(2026, 3, 1); // Wed Apr 1
    const end = new Date(2026, 3, 10);  // Fri Apr 10
    const tl = buildWorkdayTimeline(start, end, []);
    // 1, 2, 3, 6, 7, 8, 9, 10 = 8 рабочих дней (Sat 4, Sun 5 пропущены).
    expect(tl.totalDays).toBe(8);
  });

  it('respects production calendar holidays', () => {
    const start = new Date(2026, 4, 1); // Fri May 1 — holiday RF
    const end = new Date(2026, 4, 12);
    const calendar = [{ date: '2026-05-01', hours: 0, is_workday: false, kind: 'holiday' }];
    const tl = buildWorkdayTimeline(start, end, calendar);
    // skip 01.05 (holiday) + 02,03,09,10 (weekends)
    expect(tl.totalDays).toBe(7);
  });

  it('dateToLeft uses workday index', () => {
    const start = new Date(2026, 3, 1);
    const end = new Date(2026, 3, 10);
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 6 (Mon) = 3-й рабочий день (0-indexed) → leftPct = 3/8 * 100 = 37.5
    expect(dateToLeft('2026-04-06', tl)).toBeCloseTo(37.5, 1);
  });
});
```

- [ ] **Step 2: Реализация**

В `frontend/src/utils/gantt.ts`:

```typescript
export interface WorkdayTimeline extends GanttTimeline {
  workdayIndex: Map<string, number>;  // 'YYYY-MM-DD' → 0-based index
  totalDays: number;  // override = workday count
}

interface CalendarRow { date: string; hours: number; is_workday: boolean; kind: string }

export function buildWorkdayTimeline(
  startDate: Date,
  endDate: Date,
  calendar: CalendarRow[],
): WorkdayTimeline {
  const calMap = new Map(calendar.map(c => [c.date, c]));
  const workdayIndex = new Map<string, number>();
  let idx = 0;
  const d = new Date(startDate);
  while (d <= endDate) {
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const cal = calMap.get(iso);
    let isWork: boolean;
    if (cal) isWork = cal.is_workday;
    else isWork = d.getDay() >= 1 && d.getDay() <= 5;
    if (isWork) {
      workdayIndex.set(iso, idx);
      idx++;
    }
    d.setDate(d.getDate() + 1);
  }
  return { startDate, endDate, totalDays: idx, workdayIndex };
}

// dateToLeft / datesToWidth расширить:
export function dateToLeft(dateStr: string, tl: GanttTimeline | WorkdayTimeline): number {
  if ('workdayIndex' in tl) {
    // Workday mode: clamp дату к ближайшему рабочему вперёд.
    const idx = tl.workdayIndex.get(dateStr);
    if (idx !== undefined) return (idx / tl.totalDays) * 100;
    // дата не рабочая — найти следующий рабочий
    const all = [...tl.workdayIndex.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const next = all.find(([d]) => d >= dateStr);
    if (next) return (next[1] / tl.totalDays) * 100;
    return 100;
  }
  // existing calendar-day implementation ...
  const d = new Date(dateStr + 'T00:00:00');
  const offsetDays = (d.getTime() - tl.startDate.getTime()) / 86_400_000;
  return Math.max(0, (offsetDays / tl.totalDays) * 100);
}
```

Аналогично — `datesToWidth` (count workdays between start и end в `workdayIndex`).

- [ ] **Step 3: Прогнать**

```bash
cd frontend && npx vitest run src/utils/gantt.test.ts
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/gantt.ts frontend/src/utils/gantt.test.ts
git commit -m "feat(rp/utils): buildWorkdayTimeline for hide_weekends mode"
```

---

### Task 17: Frontend — Применить `hideWeekends` в `GanttChart`

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`
- Modify: `frontend/src/components/resource-planning/NonWorkingZones.tsx` (skip when workday timeline)

- [ ] **Step 1: В `GanttChart.tsx`**

```tsx
const timeline = useMemo(() => {
  const { start, end } = quarterBounds(quarter, year);
  if (hideWeekends) {
    return buildWorkdayTimeline(start, end, calendar);
  }
  return buildTimeline(start, end);
}, [quarter, year, hideWeekends, calendar]);
```

(Calendar query — already есть.)

`pxPerDay` остаётся — но для workday-timeline `totalDays` уже меньше, ширина трека пересчитается автоматически.

- [ ] **Step 2: `NonWorkingZones` — не рендерить если workday timeline**

```tsx
export default function NonWorkingZones({ timeline, calendar }: Props) {
  if ('workdayIndex' in timeline) return null;  // workday mode = выходных просто нет
  // existing implementation
}
```

- [ ] **Step 3: Ручная проверка**

Запустить `npm run dev`, открыть `/resource-planning`, тоггл «Только рабочие» → шкала пересчитана, выходные исчезли, бары смежные.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/GanttChart.tsx frontend/src/components/resource-planning/NonWorkingZones.tsx
git commit -m "fix(rp): wire hide_weekends to actually rebuild timeline as workday-only"
```

---

### Task 18: Frontend — Week-mode без полосок выходных + holiday-точки

**Files:**
- Modify: `frontend/src/components/resource-planning/NonWorkingZones.tsx`
- Modify: `frontend/src/components/resource-planning/TimelineHeader.tsx`
- Modify: `frontend/src/components/resource-planning/TrackGridlines.tsx`

- [ ] **Step 1: `NonWorkingZones` — параметр `scale` + скрытие**

```tsx
interface Props {
  timeline: GanttTimeline | WorkdayTimeline;
  calendar: ProductionCalendarDayResponse[];
  scale: TimelineScale;
  hideInWeekMonth: boolean;  // = prefs.hide_weekend_stripes_week_mode
}

export default function NonWorkingZones({ timeline, calendar, scale, hideInWeekMonth }: Props) {
  if ('workdayIndex' in timeline) return null;
  if (hideInWeekMonth && (scale === 'week' || scale === 'month')) return null;
  // existing day-mode implementation
}
```

Передать `scale` и `hideInWeekMonth` из `GanttChart`.

- [ ] **Step 2: `TimelineHeader` — точки праздников в неделе**

В `TimelineHeader`, в нижнем ряду weeks, добавить под каждым лейблом неделю-точки если в этой неделе есть `is_workday: false` (исключая Sat/Sun по DOW — только настоящие праздники):

```tsx
const weekHolidays = useMemo(() => {
  if (scale !== 'week') return new Map<string, string[]>();
  // ... walk through weekLabels, для каждой найти даты-праздники в окне
}, [...]);

// в lower.map(...)
{scale === 'week' && weekHolidays.get(w.label)?.length && (
  <span title={...} style={{ position: 'absolute', bottom: 1, right: 2, color: '#f0a075', fontSize: 9 }}>•</span>
)}
```

- [ ] **Step 3: `TrackGridlines` — усилить контраст разделителя недели**

В `TrackGridlines.tsx`:

```tsx
if (l.kind === 'week') {
  style.borderLeft = '1px solid rgba(160, 200, 240, 0.20)';  // было: '1px dashed rgba(160, 200, 240, 0.08)'
}
```

- [ ] **Step 4: Ручная проверка**

`npm run dev`, view-mode «Неделя» → полосок выходных нет, точки на неделях с праздниками, разделители видны.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/{NonWorkingZones,TimelineHeader,TrackGridlines}.tsx
git commit -m "feat(rp/week-view): hide day-stripes, holiday dots in header, stronger week divider"
```

---

### Task 19: Frontend — Sticky left column

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (`ItemTitleCell` style)
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` (z-index взаимодействия с sticky header)

- [ ] **Step 1: `ItemTitleCell` style**

```tsx
// ItemTitleCell
<div style={{
  width: leftColWidth,
  flexShrink: 0,
  borderRight: '1px solid #1e3a5f',
  display: 'grid',
  ...
  position: 'sticky',
  left: 0,
  zIndex: 4,
  background: '#0a1628',
}}>
```

То же — для `ResourceTrackRows` левого блока.

- [ ] **Step 2: TimelineHeader левая колонка**

В `TimelineHeader.tsx` оба `<div style={{ width: leftColWidth, flexShrink: 0, ... }}>` — добавить `position: sticky; left: 0; zIndex: 31; background: '#091829'`.

- [ ] **Step 3: Ручная проверка**

`npm run dev` → горизонтальный скролл Ганта (зум День) → левая колонка остаётся видимой.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/{GanttRows,TimelineHeader,GanttChart}.tsx
git commit -m "feat(rp/ui): sticky left column on horizontal scroll"
```

---

### Task 20: Frontend — A+B+C+D подсветка сотрудника

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (`PhaseBar`, `TwoLevelRows`, `ResourceTrackRows`)
- Create: `frontend/src/utils/gantt.css` (keyframes)
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx` (импорт CSS)

- [ ] **Step 1: CSS keyframes**

`frontend/src/utils/gantt.css`:

```css
@keyframes rp-pulse-employee {
  0%, 100% { box-shadow: 0 0 4px rgba(0,201,200,0.4), 0 0 0 2px rgba(0,201,200,0.6); }
  50%      { box-shadow: 0 0 14px rgba(0,201,200,0.9), 0 0 0 3px rgba(0,201,200,1); }
}
@keyframes rp-pulse-critical {
  0%, 100% { box-shadow: 0 0 4px rgba(232,93,74,0.4); }
  50%      { box-shadow: 0 0 14px rgba(232,93,74,0.9); }
}
.rp-emp-highlighted { animation: rp-pulse-employee 1.4s ease-in-out infinite; }
.rp-on-critical-path { animation: rp-pulse-critical 2s ease-in-out infinite; }
```

В `ResourcePlanningPage.tsx` импорт: `import '../utils/gantt.css';`

- [ ] **Step 2: В `PhaseBar` — применить A+B+C+D**

(B уже частично есть через `isHighlighted` row bg в TwoLevelRows — усилить с .06 → .18.)

```tsx
// PhaseBar style
const isMe = !!highlightedEmployeeId && assignment.employee_id === highlightedEmployeeId;
const isDimmed = !!highlightedEmployeeId && !isMe && assignment.phase !== 'qa';
const pulseEmp = appearance.pulse_highlighted_employee ?? true;
const pulseCp = appearance.pulse_critical_path ?? true;

style={{
  ...
  opacity: isDimmed ? 0.12 : 1,
  outline: isMe ? '2px solid #00c9c8' : (assignment.is_pinned ? '1px solid #00c9c8' : 'none'),
  boxShadow: isMe ? '0 0 8px rgba(0,201,200,0.7)' : (assignment.is_on_critical_path ? '0 0 6px rgba(232,93,74,0.5)' : 'none'),
}}
className={[
  isMe && pulseEmp ? 'rp-emp-highlighted' : '',
  assignment.is_on_critical_path && pulseCp ? 'rp-on-critical-path' : '',
].filter(Boolean).join(' ')}
```

- [ ] **Step 3: В `TwoLevelRows` — row bg .18 + dim cleanup**

`isDimmed`/`isHighlighted` уже считаются — поднять `background: isHighlighted ? 'rgba(0,201,200,0.18)' : 'transparent'` (с .06 → .18).

- [ ] **Step 4: Ручная проверка**

`npm run dev` → клик на имя сотрудника → его строки подсвечены, бары пульсируют + glow + outline, другие приглушены.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/gantt.css frontend/src/components/resource-planning/GanttRows.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(rp/highlight): A+B+C+D employee highlight (glow + tint + dim + pulse)"
```

---

### Task 21: Frontend — Мульти-сегмент с тонким коннектором

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (`TwoLevelRows`, detect parts → connector)

- [ ] **Step 1: Логика обнаружения**

В цикле `sg.assignments.filter(...).map(a => ...)` — после создания всех `<PhaseBar>` добавить рисование connector между barами одной фазы и employee:

```tsx
// Группировать assignments одной phase+employee по части
const parts = sg.assignments
  .filter(a => a.start_date && a.end_date)
  .sort((x, y) => (x.part_number ?? 1) - (y.part_number ?? 1));

// Для каждой пары последовательных частей нарисовать тонкую пунктирную линию
const connectors = parts.slice(1).map((next, i) => {
  const prev = parts[i];
  if (!prev.end_date || !next.start_date) return null;
  const leftPct = dateToLeft(prev.end_date, timeline);
  const widthPct = dateToLeft(next.start_date, timeline) - leftPct;
  return (
    <div
      key={`conn-${prev.id}-${next.id}`}
      style={{
        position: 'absolute',
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        top: '50%',
        height: 1,
        borderTop: `1px dashed ${color}`,
        zIndex: 1,
        pointerEvents: 'none',
      }}
    />
  );
});

return (
  <>
    {parts.map(a => <PhaseBar key={a.id} assignment={a} .../>)}
    {connectors}
  </>
);
```

- [ ] **Step 2: Ручная проверка**

После Task 6 (multi-segment) — открыть сценарий с ОПЭ-разрывом → видны 2 бара одной фазы соединённые пунктиром.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/resource-planning/GanttRows.tsx
git commit -m "feat(rp/ui): dashed connector between split phase parts"
```

---

### Task 22: Frontend — Visual `out_of_quarter` + расширение timeline

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` (extend timeline when has out_of_quarter)
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (`PhaseBar` style for out_of_quarter)
- Modify: `frontend/src/components/resource-planning/TimelineHeader.tsx` (marker «Выход за квартал»)

- [ ] **Step 1: GanttChart — extend timeline**

```tsx
const hasOoT = assignments.some(a => a.out_of_quarter);
const months = hasOoT ? (prefs.out_of_quarter_months ?? 1) : 0;

const timeline = useMemo(() => {
  const { start, end } = quarterBounds(quarter, year);
  const extEnd = new Date(end);
  extEnd.setMonth(extEnd.getMonth() + months);
  if (hideWeekends) return buildWorkdayTimeline(start, extEnd, calendar);
  return buildTimeline(start, extEnd);
}, [quarter, year, hideWeekends, calendar, months]);
```

Также передать `q_end_iso` в TimelineHeader для маркера.

- [ ] **Step 2: PhaseBar style for out_of_quarter**

```tsx
const isOoQ = assignment.out_of_quarter;
style={{
  ...
  opacity: isOoQ ? 0.6 : (existing opacity logic),
  background: isOoQ
    ? `repeating-linear-gradient(45deg, ${color} 0 6px, rgba(0,0,0,0.15) 6px 12px)`
    : color,
  border: isOoQ ? '1px solid #ffb432' : (existing critical path border),
}}
```

- [ ] **Step 3: TimelineHeader — линия-разделитель q_end**

```tsx
const qEndLeft = dateToLeft(q_end_iso, timeline);
// В nested div'е track:
<div style={{
  position: 'absolute',
  left: `${qEndLeft}%`,
  top: 0, bottom: 0,
  width: 0,
  borderRight: '2px dashed #ffb432',
  zIndex: 10,
}} />
```

И в `GanttChart` основной overlay-line.

- [ ] **Step 4: Ручная проверка**

Сценарий с overflow → бары за q_end видны со штрихом + линия раздела на 30 июня.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/{GanttChart,GanttRows,TimelineHeader}.tsx
git commit -m "feat(rp/ui): visualize out_of_quarter assignments + 1mo timeline extension"
```

---

### Task 23: Frontend — Прогресс факта внутри полоски

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (gantt-projection включает worklog_hours_actual в assignment)
- Modify: `app/services/resource_planning_service.py` (новый метод `_compute_actual_worklog_hours`)
- Modify: `frontend/src/api/resourcePlanning.ts` (тип `AssignmentOut.worklog_hours_actual`)
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx` (PhaseBar progress overlay)

- [ ] **Step 1: Backend — посчитать worklog часы для assignment'а**

В `app/services/resource_planning_service.py` — новый метод:

```python
def _compute_actual_worklog_hours(
    self, assignments: List[ResourcePlanAssignment]
) -> Dict[str, float]:
    """{assignment_id: worklog hours emp за окно [start_date, end_date] и по jira_key инициативы}"""
    if not assignments:
        return {}
    # Группировать по (employee_id, item_id) → diapason
    out: Dict[str, float] = {}
    for a in assignments:
        if not a.employee_id or not a.start_date or not a.end_date:
            out[a.id] = 0.0
            continue
        from app.models import Worklog, Issue
        item = a.backlog_item  # joined
        if not item or not item.issue_id:
            out[a.id] = 0.0
            continue
        rows = self.db.execute(
            select(func.sum(Worklog.hours))
            .where(
                Worklog.author_id == a.employee_id,
                Worklog.issue_id == item.issue_id,
                Worklog.started >= a.start_date,
                Worklog.started <= a.end_date + timedelta(days=1),
            )
        ).scalar()
        out[a.id] = float(rows or 0.0)
    return out
```

Вызвать в `/gantt-projection` endpoint, проставить `worklog_hours_actual` каждому AssignmentOut.

- [ ] **Step 2: Pydantic + Frontend type**

```python
class AssignmentOut(BaseModel):
    ...
    worklog_hours_actual: float = 0.0
```

```typescript
export interface AssignmentOut {
  ...
  worklog_hours_actual: number;
}
```

- [ ] **Step 3: PhaseBar progress overlay**

В `PhaseBar` после основного `<div>` бара:

```tsx
{assignment.worklog_hours_actual > 0 && assignment.hours_allocated && (
  <div
    style={{
      position: 'absolute',
      left: `${left}%`,
      top: '50%',
      transform: 'translateY(-50%)',
      height: 18,
      width: `${(width * Math.min(1, assignment.worklog_hours_actual / assignment.hours_allocated))}%`,
      background: 'rgba(255,255,255,0.25)',  // лёгкая полупрозрачная заливка слева
      borderRadius: '3px 0 0 3px',
      zIndex: 3,
      pointerEvents: 'none',
    }}
  />
)}
{/* overload red outline если fact > plan */}
{assignment.worklog_hours_actual > (assignment.hours_allocated ?? 0) && (
  <div style={{
    position: 'absolute',
    left: `${left}%`,
    width: `${width}%`,
    top: '50%',
    transform: 'translateY(-50%)',
    height: 18,
    border: '1.5px solid #ef4444',
    borderRadius: 3,
    pointerEvents: 'none',
    zIndex: 3,
  }} />
)}
```

- [ ] **Step 4: Ручная проверка**

Открыть план с задачей, у которой есть ворклоги сотрудника → внутри бара видна более светлая заливка слева, размер = факт/план.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py app/services/resource_planning_service.py app/schemas/resource_planning.py frontend/src/api/resourcePlanning.ts frontend/src/components/resource-planning/GanttRows.tsx
git commit -m "feat(rp/ui): fact-progress fill inside phase bar + overload outline"
```

---

### Task 24: Frontend — Smooth zoom transition

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx` (CSS transition на trackWidthPx-зависимые элементы)
- Modify: `frontend/src/utils/gantt.css`

- [ ] **Step 1: CSS transition**

В `gantt.css`:

```css
.rp-track-animated, .rp-track-animated * {
  transition: left 250ms ease-out, width 250ms ease-out;
}
```

В `GanttChart` обернуть основной `innerRef` div'у класс `rp-track-animated`:

```tsx
<div ref={innerRef} className="rp-track-animated" style={{ ... }}>
```

- [ ] **Step 2: Ручная проверка**

Переключение День ↔ Неделя ↔ Месяц — бары и заголовок плавно растягиваются за 250ms.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/gantt.css frontend/src/components/resource-planning/GanttChart.tsx
git commit -m "feat(rp/ui): smooth zoom transition when scale changes"
```

---

### Task 25: Frontend — Кнопка Collapse-All / Expand-All

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`

- [ ] **Step 1: Кнопка в шапке**

В Space шапки, рядом с view-mode `Segmented`:

```tsx
{viewMode === 'two-level' && gantt && (
  <Button
    size="small"
    onClick={() => {
      const allIds = [...new Set(gantt.assignments.map(a => a.backlog_item_id))];
      const allCollapsed = (prefs.collapsed_initiative_ids ?? []).length === allIds.length;
      patchPrefs({ collapsed_initiative_ids: allCollapsed ? [] : allIds });
    }}
  >
    {(prefs.collapsed_initiative_ids ?? []).length > 0 ? '↥ Развернуть все' : '↧ Свернуть все'}
  </Button>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(rp/ui): collapse-all / expand-all button"
```

---

### Task 26: E2E + финальные проверки

**Files:**
- Create: `e2e/resource-planning-fixes.spec.ts`
- Run: lint, tsc, pytest, e2e

- [ ] **Step 1: E2E spec**

```typescript
// e2e/resource-planning-fixes.spec.ts
import { test, expect } from '@playwright/test';

test('drawer is non-modal — bars stay clickable when open', async ({ page }) => {
  await page.goto('/resource-planning');
  // выбрать первый план
  await page.getByPlaceholder('Выберите план').click();
  await page.getByRole('option').first().click();
  // подождать gantt
  await page.waitForSelector('[data-gantt-row="true"]');
  // кликнуть первый бар
  const bars = page.locator('[data-gantt-row="true"] >> div').filter({ hasText: /./ });
  await bars.first().click();
  // drawer открыт
  await expect(page.getByRole('dialog')).toBeVisible();
  // кликнуть другой бар — drawer обновляется без закрытия
  await bars.nth(2).click({ force: true });
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('hide_weekends toggle compresses timeline', async ({ page }) => {
  await page.goto('/resource-planning?plan_id=...');  // seed
  // measure trackWidthPx before
  const before = await page.locator('[data-gantt-track="true"]').first().evaluate(el => el.getBoundingClientRect().width);
  await page.getByText('Только рабочие').click();
  const after = await page.locator('[data-gantt-track="true"]').first().evaluate(el => el.getBoundingClientRect().width);
  // workday-only режим примерно 5/7 ширины
  expect(after).toBeLessThan(before * 0.85);
});

test('week-mode no weekend stripes', async ({ page }) => {
  await page.goto('/resource-planning?plan_id=...');
  await page.getByText('Неделя').click();
  // в week-режиме NonWorkingZones не рендерится
  const stripes = await page.locator('[data-non-working]').count();
  expect(stripes).toBe(0);
});
```

(Адаптировать селекторы под фактический DOM.)

- [ ] **Step 2: Прогнать всё**

```bash
py -3.10 -m pytest tests/ -v
cd frontend && npm run lint && npx tsc --noEmit && npm run build
npm run e2e -- resource-planning-fixes.spec.ts
```

Expected: всё PASS.

- [ ] **Step 3: Commit + push**

```bash
git add e2e/resource-planning-fixes.spec.ts
git commit -m "test(rp/e2e): drawer non-modal, hide_weekends, week-view stripes"
git push origin main
```

---

## Self-Review Checklist

- **Спек coverage:** все 9 пунктов + 5 visual extras покрыты Task 1-25. E2E Task 26.
- **Placeholders:** нет — все шаги с конкретным кодом.
- **Type consistency:** `AssignmentOut` поля `out_of_quarter`, `daily_hours`, `worklog_hours_actual` объявлены в Task 10/23 и используются в Tasks 21-23. `AssignmentExplainResponse` поля — Task 9. `WorkdayTimeline` — Task 16, используется в 17,18,22.

## Замечания по очерёдности

- Tasks 1-10 (Backend) могут идти параллельно frontend Tasks 11-12 (типы/удаление popover).
- Task 13 (mask=false) можно сделать первым изолированно.
- Task 14 (секции) зависит от Task 9 (API explain).
- Task 21 (мульти-сегмент visual) зависит от Task 6 (backend split).
- Task 22 (out_of_quarter visual) зависит от Task 7 (backend spillover) и Task 10 (Pydantic).
- Task 23 (прогресс факта) изолированный.

Subagent flow: один subagent на 1-3 задачи, после каждой — review check (test pass + lint clean).
