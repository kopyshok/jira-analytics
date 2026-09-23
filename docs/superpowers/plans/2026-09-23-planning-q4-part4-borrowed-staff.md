# Планирование Q4 — Часть 4. Привлечение сотрудников из чужих команд. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ресурсный план команды может брать исполнителей из других команд; занятость человека в опорных планах других команд вычитается из его доступности в обе стороны, видна на диаграмме и в подвале, а пересечения помечаются в плане привлекающей команды.

**Architecture:** Новый модуль `app/services/cross_team_occupancy.py` (чистое чтение) выбирает опорный план каждой команды на квартал и одним запросом отдаёт брони сотрудников в чужих опорных планах. `ResourcePlanningService.compute_schedule` добавляет привлечённых сотрудников в пул (ручное закрепление + «Разработчик» из Jira через новый `app/services/jira_developer.py`) и вычитает внешнюю занятость из доступности до раскладки. Эндпоинт диаграммы отдаёт внешние брони, строки привлечённых в подвале, долю «других команд» по дням и «живой» конфликт пересечения. `ResourceBaseService` вычитает брони других команд из базы сценария. Фронт: блок «Привлечённые», двухцветный подвал, выбор исполнителя по всем сотрудникам с группами.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, pytest; React 19 + TypeScript + AntD 6, TanStack Query, vitest.

**Спека:** `docs/superpowers/specs/2026-09-23-planning-q4-design.md`, «Часть 4». Части 1–3 уже реализованы (Часть 1.6 добавила строкам подвала `left_to` / `joined_from` — не ломать).

---

## Решения и расхождения со спекой

Проверено по коду; там, где спека неоднозначна или неисполнима буквально, выбрано простейшее корректное поведение.

1. **Опорный план.** Признак `is_baseline` в коде нигде не выставляется в `True` (только читается, форк пишет `False`), поэтому на практике работает запасная ступень. Порядок выбора внутри утверждённых сценариев команды на квартал: `is_baseline` → статус «Готово» → свежесть (`computed_at`, `created_at`, `id` — тот же ключ `_plan_sort_key`, что в `plan_common`). План в статусе «Требуется пересчёт» тоже годится, если «Готово» нет (иначе брони команды исчезли бы после любой правки). Копии-форки (`parent_plan_id`) исключены, как в `plan_common.find_recent_plan`. Если утверждённых нет — самый свежий черновик по `updated_at` сценария, признак «предварительно». Планы без сценария не участвуют.
2. **«Привлечённый» — на квартал, а не на день.** Привлечённый в плане P = исполнитель фазы, который не состоял в команде P **ни одного дня квартала**. Сотрудник команды, выбывший в середине квартала, остаётся «своим»: его дни после выбытия по-прежнему нулевые и дают `OUT_OF_TEAM` (существующее поведение и тест `tests/services/test_rp_out_of_team_conflict.py`). Посуточное смешение «свой до 11.08, привлечённый после» не делаем.
3. **Выравниватель (`RcpspLeveler`) получает доступность без внешней занятости.** Раскладка фаз (`remaining`, ёмкость квартала для групп, сдвиг по предшественникам) идёт по доступности за вычетом внешней занятости — так авторасчёт обходит чужие брони. А перегрузки выравниватель считает по «сырой» ёмкости, иначе ручная постановка поверх брони в домашнем плане давала бы там перегрузку, а спека требует помечать пересечение только в плане привлекающей команды.
4. **Конфликт пересечения — «живой», не хранится.** Считается при каждом чтении диаграммы только для привлечённых сотрудников, по дням квартала, где у фазы этого плана есть часы, и `часы этого плана + брони других команд > ёмкость дня`. Тип `CROSS_TEAM_OVERLAP`, в ответе помечен `is_live=true`; у такого конфликта нельзя менять статус (в панели скрыто меню статусов). Пересчёт чужих планов не запускается.
5. **«Разработчик» из Jira.** Если у задачи поле пустое (или человек неактивен/не найден) — самый частый «Разработчик» во **всём поддереве** задачи (для RFA разработчики сидят на подзадачах эпиков, прямых детей мало). Ничья — по учётной записи Jira по алфавиту (детерминированно). Подстановка действует и для своих сотрудников команды — это меняет прежний жадный выбор: задача с заполненным «Разработчиком» уйдёт именно ему. Разработчик ОПЭ = исполнитель разработки, в том числе привлечённый.
6. **Жадный подбор и выравниватель не трогают привлечённых.** Пулы аналитиков/разработчиков, пулы ОПЭ и пулы переназначения выравнивателя строятся только из сотрудников команды. Привлечённый попадает в план только ручным закреплением или через «Разработчика» из Jira. Аналитик из чужой команды — только вручную (исполнитель инициативы из другой команды не подставляется).
7. **Брони без посуточной раскладки** (старые строки без `daily_hours_json`) размазываются поровну по будним дням отрезка.
8. **Базовые ресурсы сценария.** В посуточной базе (`compute`): `часы дня = норма × (1 − обязательные%) − брони других команд`, не ниже нуля; обязательные работы по-прежнему считаются от полной нормы («10% не трогаем»). В сводке (`compute_summary`) брутто и отсутствия не меняются (иначе «Итого» отсутствий в блоке справа начнёт врать), брони вычитаются только из «На бэклог»; новое поле `booked_by_other_teams_by_role` + подпись под таблицей. Учитываются только брони в дни участия сотрудника в команде сценария. Шкалы разные (база — 8 ч, планировщик — 6 ч в день) — так и есть сейчас, не выравниваем.
9. **Выбор исполнителя.** Новый эндпоинт кандидатов. «Из Jira»: для разработки — «Разработчик», для остальных фаз — исполнитель инициативы. «Моя команда» — состав команды за квартал плана. «Другие команды» — все остальные активные, подпись — текущая команда сотрудника. Загрузка за квартал = брони во **всех** опорных планах квартала / (календарь − отсутствия), та же шкала 6 ч, что у планировщика.
10. **Превью смены сотрудника** (`preview-employee-change`) брони других команд не показывает — пересечение проявится «живым» конфликтом после сохранения. Вне объёма.
11. **Блокировки команды по роли** (`ScheduledBlock` с ролями) действуют и на привлечённых этой роли — работа идёт в плане этой команды. Блокировка «на всю команду» (без ролей и людей) их не задевает (`_block_targets` сверяет `Employee.team`).
12. **Конфликт «Нет разработчика»** не поднимается, если в плане есть привлечённый разработчик (список сотрудников для него включает привлечённых). Это ожидаемо: разработка обеспечена.
13. **Подвал.** Цвета «в этом плане» / «в планах других команд» одинаковы для домашней и привлекающей команды (формулировка спеки «домашняя команда / эта команда» переведена в нейтральную, одинаково верную с обеих сторон). Строки привлечённых идут отдельной секцией «Привлечённые» внизу с подписью «из <команда>».
14. **Диаграмма** — собственная (`GanttChart` / `GanttRows`), не dhtmlx. Блок «Привлечённые» — отдельный компонент над строками задач в той же прокручиваемой области, позиционирование через `dateToLeft` / `datesToWidth`.
15. **Расшифровки.** `explain_assignment` («почему фаза тут») вычитает брони других команд из «Доступно»; обе расшифровки не обнуляют дни привлечённого как «вне команды».
16. Номера строк в тексте спеки и ниже — ориентиры: Части 1–3 сдвинули файлы. Искать по именам функций и приведённым фрагментам.

---

## Карта файлов

**Создать**
- `app/services/cross_team_occupancy.py` — опорные планы, внешние брони, вычитание, пересечения, привлечённые, загрузка за квартал.
- `app/services/jira_developer.py` — «Разработчик» из Jira для инициатив.
- `tests/services/xteam_factory.py` — фабрики тестовых данных (сотрудник, сценарий+план, инициатива, бронь, задача Jira).
- `tests/services/test_cross_team_occupancy.py`
- `tests/services/test_jira_developer.py`
- `tests/services/test_rp_borrowed_staff.py` — доступность, подбор, полный расчёт.
- `tests/services/test_resource_base_external.py`
- `tests/api/test_rp_cross_team_gantt.py` — диаграмма и кандидаты.
- `frontend/src/utils/externalBookings.ts` + `.test.ts`
- `frontend/src/utils/heatmapFill.ts` + `.test.ts`
- `frontend/src/utils/rpCandidates.ts` + `.test.ts`
- `frontend/src/components/resource-planning/ExternalBookingsRows.tsx`

**Изменить**
- `app/services/resource_planning_service.py` — `build_availability`, `compute_schedule`, `_assign_employees`, новый `_load_borrowed`, `_build_conflict_dicts`.
- `app/api/endpoints/resource_planning.py` — схемы, `get_gantt`, новый эндпоинт кандидатов, `_cross_team_conflicts`, `explain_conflict`, `explain_assignment`.
- `app/services/resource_base_service.py` — `compute`, `compute_summary`, `ResourceSummary`.
- `app/api/endpoints/planning.py` — `ResourceSummaryOut` + проброс поля.
- `frontend/src/api/resourcePlanning.ts`, `frontend/src/hooks/useResourcePlanning.ts`, `frontend/src/types/api.ts`
- `frontend/src/components/resource-planning/GanttChart.tsx`, `EmployeeLoadHeatmap.tsx`, `AssignmentSidebar.tsx`, `ConflictPanel.tsx`
- `frontend/src/pages/ResourcePlanningPage.tsx`
- `frontend/src/components/planning/ScenarioResourceSummary.tsx`
- `docs/help/resource-planning.md`, `app/services/CLAUDE.md`
- `release_notes/drafts.json` (через CLI)

Команды: бэкенд-тесты `py -3.10 -m pytest <путь> -v` (весь прогон — с `--ignore=tests/api/test_llm.py`, он виснет без сети). Фронт: `cd frontend && npx vitest run <файл>`, `npm run build`, `npm run lint`.

Коммиты: сообщения на русском в формате conventional, в конце `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Всегда `git add <явные пути>` и `git commit -F - <<'EOF' ... EOF` (не `git commit -- пути`: он берёт рабочую копию целиком).

---

### Task 1: Фабрики тестов и выбор опорного плана

**Files:**
- Create: `tests/services/xteam_factory.py`
- Create: `app/services/cross_team_occupancy.py`
- Test: `tests/services/test_cross_team_occupancy.py`

- [ ] **Step 1: Фабрики тестовых данных**

```python
# tests/services/xteam_factory.py
"""Фабрики для тестов привлечения сотрудников из чужих команд."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Dict, Optional

from app.models import (
    BacklogItem,
    Employee,
    Issue,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam


def make_employee(
    db,
    name: str,
    team: str,
    role: str = "developer",
    jira_account_id: Optional[str] = None,
    member: bool = True,
    is_active: bool = True,
) -> Employee:
    e = Employee(
        jira_account_id=jira_account_id or f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role=role,
        team=team,
        is_active=is_active,
    )
    db.add(e)
    db.flush()
    if member:
        db.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        db.flush()
    return e


def make_plan(
    db,
    team: str,
    scenario_status: str = "approved",
    plan_status: str = "ready",
    year: int = 2026,
    quarter: str = "Q1",
    scenario_updated_at: Optional[datetime] = None,
    **plan_kw,
) -> tuple[PlanningScenario, ResourcePlan]:
    sc = PlanningScenario(
        name=f"{team}-{scenario_status}-{uuid.uuid4().hex[:6]}",
        quarter=quarter,
        year=year,
        team=team,
        status=scenario_status,
    )
    if scenario_updated_at is not None:
        sc.updated_at = scenario_updated_at
    db.add(sc)
    db.flush()
    plan = ResourcePlan(
        team=team,
        quarter=quarter,
        year=year,
        status=plan_status,
        scenario_id=sc.id,
        **plan_kw,
    )
    db.add(plan)
    db.flush()
    return sc, plan


def add_item(
    db,
    scenario: PlanningScenario,
    title: str,
    dev: float = 0.0,
    analyst: float = 0.0,
    assignee: Optional[Employee] = None,
    issue: Optional[Issue] = None,
    priority: int = 1,
) -> BacklogItem:
    item = BacklogItem(
        title=title,
        priority=priority,
        estimate_analyst_hours=analyst,
        estimate_dev_hours=dev,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        issue_id=issue.id if issue else None,
    )
    db.add(item)
    db.flush()
    db.add(
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
        )
    )
    db.flush()
    return item


def book(
    db,
    plan: ResourcePlan,
    item: BacklogItem,
    employee: Employee,
    daily: Dict[str, float],
    phase: str = "dev",
    **kw,
) -> ResourcePlanAssignment:
    """Бронь сотрудника в плане: фаза с посуточной раскладкой."""
    days = sorted(daily)
    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase=phase,
        employee_id=employee.id,
        part_number=1,
        hours_allocated=sum(daily.values()),
        start_date=date.fromisoformat(days[0]),
        end_date=date.fromisoformat(days[-1]),
        daily_hours_json=json.dumps(daily),
        **kw,
    )
    db.add(a)
    db.flush()
    return a


def make_issue(
    db,
    project,
    key: str,
    developer: Optional[str] = None,
    parent: Optional[Issue] = None,
) -> Issue:
    i = Issue(
        jira_issue_id=f"j-{key}",
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id=project.id,
        developer_account_id=developer,
        parent_id=parent.id if parent else None,
    )
    db.add(i)
    db.flush()
    return i
```

- [ ] **Step 2: Падающий тест на выбор опорного плана**

```python
# tests/services/test_cross_team_occupancy.py
"""Занятость сотрудников в опорных планах других команд."""

from datetime import date, datetime

from app.services import cross_team_occupancy as cto
from tests.services.xteam_factory import make_plan


def test_reference_plan_prefers_ready_over_newer_stale(db_session):
    sc, ready = make_plan(db_session, "A", plan_status="ready",
                          computed_at=datetime(2026, 1, 1))
    from app.models import ResourcePlan
    stale = ResourcePlan(team="A", quarter="Q1", year=2026, status="stale",
                         scenario_id=sc.id, computed_at=datetime(2026, 1, 5))
    fork = ResourcePlan(team="A", quarter="Q1", year=2026, status="ready",
                        scenario_id=sc.id, computed_at=datetime(2026, 1, 9),
                        parent_plan_id=ready.id)
    db_session.add_all([stale, fork])
    db_session.commit()

    refs = cto.reference_plans(db_session, 2026, 1)

    assert refs["A"].plan_id == ready.id
    assert refs["A"].provisional is False


def test_reference_plan_prefers_baseline(db_session):
    sc, ready = make_plan(db_session, "B", plan_status="ready",
                          computed_at=datetime(2026, 1, 9))
    from app.models import ResourcePlan
    base = ResourcePlan(team="B", quarter="Q1", year=2026, status="stale",
                        scenario_id=sc.id, is_baseline=True)
    db_session.add(base)
    db_session.commit()

    assert cto.reference_plans(db_session, 2026, 1)["B"].plan_id == base.id


def test_reference_plan_falls_back_to_freshest_draft(db_session):
    make_plan(db_session, "C", scenario_status="draft",
              scenario_updated_at=datetime(2026, 1, 1))
    _, fresh = make_plan(db_session, "C", scenario_status="draft",
                         scenario_updated_at=datetime(2026, 2, 1))
    db_session.commit()

    ref = cto.reference_plans(db_session, 2026, 1)["C"]

    assert ref.plan_id == fresh.id
    assert ref.provisional is True


def test_reference_plan_approved_beats_draft_and_exclude_team(db_session):
    make_plan(db_session, "D", scenario_status="draft",
              scenario_updated_at=datetime(2026, 3, 1))
    _, approved = make_plan(db_session, "D", scenario_status="approved")
    make_plan(db_session, "E", quarter="1")  # квартал без буквы Q тоже находится
    db_session.commit()

    refs = cto.reference_plans(db_session, 2026, 1, exclude_team="E")

    assert refs["D"].plan_id == approved.id
    assert "E" not in refs
    assert "E" in cto.reference_plans(db_session, 2026, 1)


def test_quarter_num():
    assert cto.quarter_num("Q3") == 3
    assert cto.quarter_num("4") == 4
    assert cto.quarter_num(None) is None
    assert cto.quarter_num("Q9") is None
```

- [ ] **Step 3: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.cross_team_occupancy'`

- [ ] **Step 4: Минимальная реализация**

```python
# app/services/cross_team_occupancy.py
"""Занятость сотрудников в планах других команд.

Опорный план команды на квартал — тот, по которому остальные команды видят,
когда её люди заняты: основной (иначе «Готово», иначе самый свежий) план
утверждённого сценария; нет утверждённого — план самого свежего черновика
с признаком «предварительно». Копии-форки не участвуют.

Все функции — чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanningScenario, ResourcePlan
from app.services.plan_common import _plan_sort_key, _quarter_variants


@dataclass(frozen=True)
class ReferencePlan:
    """Опорный план команды на квартал."""

    plan_id: str
    team: str
    provisional: bool


def quarter_num(value) -> Optional[int]:
    """«Q3» / «3» / 3 → 3; мусор → None."""
    try:
        q = int(str(value or "").strip().upper().lstrip("Q"))
    except ValueError:
        return None
    return q if 1 <= q <= 4 else None


def _ref_key(plan: ResourcePlan) -> tuple:
    """Порядок выбора внутри сценариев: основной → «Готово» → свежесть."""
    return (bool(plan.is_baseline), plan.status == "ready", _plan_sort_key(plan))


def reference_plans(
    db: Session,
    year: int,
    quarter: int,
    exclude_team: Optional[str] = None,
) -> Dict[str, ReferencePlan]:
    """Опорные планы всех команд квартала: {команда: ReferencePlan}.

    Один запрос. ``exclude_team`` — команда, чей собственный план не должен
    считаться «чужой» занятостью.
    """
    rows = db.execute(
        select(ResourcePlan, PlanningScenario)
        .join(PlanningScenario, PlanningScenario.id == ResourcePlan.scenario_id)
        .where(
            ResourcePlan.year == year,
            ResourcePlan.quarter.in_(_quarter_variants(quarter)),
            ResourcePlan.parent_plan_id.is_(None),
            ResourcePlan.team.is_not(None),
            PlanningScenario.status.in_(("approved", "draft")),
        )
    ).all()

    approved: Dict[str, list] = defaultdict(list)
    drafts: Dict[str, list] = defaultdict(list)
    for plan, sc in rows:
        if exclude_team is not None and plan.team == exclude_team:
            continue
        bucket = approved if sc.status == "approved" else drafts
        bucket[plan.team].append((plan, sc))

    out: Dict[str, ReferencePlan] = {}
    for team in set(approved) | set(drafts):
        if approved.get(team):
            best = max((p for p, _ in approved[team]), key=_ref_key)
            out[team] = ReferencePlan(best.id, team, False)
            continue
        fresh_sc = max(
            (sc for _, sc in drafts[team]),
            key=lambda s: (s.updated_at or s.created_at or datetime.min, s.id),
        )
        best = max(
            (p for p, sc in drafts[team] if sc.id == fresh_sc.id), key=_ref_key
        )
        out[team] = ReferencePlan(best.id, team, True)
    return out
```

- [ ] **Step 5: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add tests/services/xteam_factory.py app/services/cross_team_occupancy.py tests/services/test_cross_team_occupancy.py
git commit -F - <<'EOF'
feat(planning): выбор опорного плана команды на квартал

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Внешние брони, вычитание, пересечения, привлечённые

**Files:**
- Modify: `app/services/cross_team_occupancy.py`
- Test: `tests/services/test_cross_team_occupancy.py`

- [ ] **Step 1: Падающие тесты** — дописать в конец `tests/services/test_cross_team_occupancy.py`:

```python
from app.models import ResourcePlanAssignment
from tests.services.xteam_factory import add_item, book, make_employee

D = date.fromisoformat


def _setup_booked(db_session):
    """Сотрудник E команды A занят в опорном плане A; M — сотрудник B."""
    e = make_employee(db_session, "Пряничников", "A")
    m = make_employee(db_session, "Свой B", "B")
    sc, plan = make_plan(db_session, "A")
    item = add_item(db_session, sc, "Задача A", dev=12)
    book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0})
    # Старая строка без посуточной раскладки: 9 ч на Чт, Пт, Пн.
    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="analyst",
        employee_id=e.id, part_number=1, hours_allocated=9.0,
        start_date=D("2026-01-08"), end_date=D("2026-01-12"),
    ))
    db_session.commit()
    return e, m


def test_external_bookings_from_other_team(db_session):
    e, _m = _setup_booked(db_session)

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    )

    assert {b.team for b in bookings} == {"A"}
    assert all(b.provisional is False for b in bookings)
    assert cto.daily_totals(bookings) == {
        e.id: {
            D("2026-01-05"): 6.0, D("2026-01-06"): 6.0,
            D("2026-01-08"): 3.0, D("2026-01-09"): 3.0, D("2026-01-12"): 3.0,
        }
    }


def test_own_team_bookings_are_not_external(db_session):
    e, _m = _setup_booked(db_session)

    assert cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    ) == []


def test_external_bookings_cut_by_window(db_session):
    e, _m = _setup_booked(db_session)

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-06"), end=D("2026-01-06"),
    )

    assert cto.daily_totals(bookings) == {e.id: {D("2026-01-06"): 6.0}}


def test_subtract_occupancy():
    avail = {"e": {D("2026-01-05"): 6.0, D("2026-01-07"): 6.0}}
    occupied = {"e": {D("2026-01-05"): 4.0}, "x": {D("2026-01-05"): 9.0}}

    assert cto.subtract_occupancy(avail, occupied) == {
        "e": {D("2026-01-05"): 2.0, D("2026-01-07"): 6.0}
    }


def test_overlap_days_only_where_own_plan_works_inside_capacity():
    own = {D("2026-01-05"): 4.0, D("2026-01-07"): 2.0, D("2026-04-01"): 5.0}
    external = {D("2026-01-05"): 6.0, D("2026-01-06"): 6.0, D("2026-04-01"): 6.0}
    capacity = {D("2026-01-05"): 6.0, D("2026-01-06"): 6.0, D("2026-01-07"): 6.0}

    assert cto.overlap_days(own, external, capacity) == [D("2026-01-05")]


def test_borrowed_ids(db_session):
    e, m = _setup_booked(db_session)

    assert cto.borrowed_ids(
        db_session, "B", D("2026-01-01"), D("2026-03-31"), [e.id, m.id, None]
    ) == {e.id}
    assert cto.borrowed_ids(
        db_session, None, D("2026-01-01"), D("2026-03-31"), [e.id]
    ) == set()
```

- [ ] **Step 2: Запустить — должны упасть**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: FAIL — `AttributeError: module 'app.services.cross_team_occupancy' has no attribute 'external_bookings'`

- [ ] **Step 3: Реализация** — в `app/services/cross_team_occupancy.py`:

Заменить блок импортов на:

```python
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import BacklogItem, PlanningScenario, ResourcePlan, ResourcePlanAssignment
from app.services import team_membership as tm
from app.services.plan_common import _plan_sort_key, _quarter_variants
```

Дописать в конец файла:

```python
@dataclass
class ExternalBooking:
    """Фаза сотрудника в опорном плане другой команды."""

    assignment_id: str
    employee_id: str
    team: str
    issue_key: Optional[str]
    title: str
    phase: str
    start: date
    end: date
    daily_hours: Dict[date, float]
    provisional: bool


def _assignment_daily(a: ResourcePlanAssignment) -> Dict[date, float]:
    """Часы фазы по дням: раскладка планировщика, иначе поровну по будням."""
    if a.daily_hours_json:
        try:
            raw = json.loads(a.daily_hours_json)
            return {
                date.fromisoformat(k): float(v) for k, v in raw.items() if float(v) > 0
            }
        except (ValueError, TypeError):
            pass
    if not a.start_date or not a.end_date or not a.hours_allocated:
        return {}
    days: List[date] = []
    d = a.start_date
    while d <= a.end_date:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    if not days:
        days = [a.start_date]
    per = float(a.hours_allocated) / len(days)
    return {d: per for d in days}


def external_bookings(
    db: Session,
    *,
    team: Optional[str],
    year: Optional[int],
    quarter: Optional[int],
    employee_ids: Iterable[Optional[str]],
    start: date,
    end: date,
) -> List[ExternalBooking]:
    """Брони сотрудников в опорных планах квартала всех команд, кроме ``team``.

    ``team=None`` — берутся опорные планы всех команд (загрузка за квартал).
    Два запроса на любой объём: опорные планы + их назначения.
    """
    ids = [i for i in dict.fromkeys(employee_ids) if i]
    if not ids or not year or not quarter:
        return []
    refs = reference_plans(db, year, quarter, exclude_team=team)
    if not refs:
        return []
    by_plan = {r.plan_id: r for r in refs.values()}
    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(
                joinedload(ResourcePlanAssignment.backlog_item).joinedload(
                    BacklogItem.issue
                )
            )
            .where(
                ResourcePlanAssignment.plan_id.in_(list(by_plan)),
                ResourcePlanAssignment.employee_id.in_(ids),
                ResourcePlanAssignment.start_date <= end,
                ResourcePlanAssignment.end_date >= start,
            )
        )
        .scalars()
        .unique()
        .all()
    )
    out: List[ExternalBooking] = []
    for a in rows:
        daily = {d: h for d, h in _assignment_daily(a).items() if start <= d <= end}
        if not daily:
            continue
        ref = by_plan[a.plan_id]
        bi = a.backlog_item
        out.append(
            ExternalBooking(
                assignment_id=a.id,
                employee_id=a.employee_id,
                team=ref.team,
                issue_key=bi.issue.key if bi is not None and bi.issue is not None else None,
                title=bi.title if bi is not None else "",
                phase=a.phase,
                start=a.start_date,
                end=a.end_date,
                daily_hours=daily,
                provisional=ref.provisional,
            )
        )
    out.sort(key=lambda b: (b.employee_id, b.start, b.issue_key or "", b.phase))
    return out


def daily_totals(bookings: Iterable[ExternalBooking]) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день: часы во всех бронях}}."""
    acc: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            acc[b.employee_id][d] += h
    return {eid: dict(days) for eid, days in acc.items()}


def subtract_occupancy(
    avail: Dict[str, Dict[date, float]],
    occupied: Dict[str, Dict[date, float]],
) -> Dict[str, Dict[date, float]]:
    """Доступность минус внешняя занятость, не ниже нуля. Новый словарь."""
    return {
        eid: {
            d: max(0.0, h - occupied.get(eid, {}).get(d, 0.0))
            for d, h in days.items()
        }
        for eid, days in avail.items()
    }


def overlap_days(
    own: Dict[date, float],
    external: Dict[date, float],
    capacity: Dict[date, float],
) -> List[date]:
    """Дни, где часы этого плана + брони других команд больше ёмкости дня.

    Берутся только дни, в которые этот план сам ставит работу (иначе
    пересечение — не его забота) и которые есть в ``capacity``.
    """
    return sorted(
        d
        for d, h in external.items()
        if h > 0
        and d in capacity
        and own.get(d, 0.0) > 0
        and own.get(d, 0.0) + h > capacity[d] + 0.01
    )


def borrowed_ids(
    db: Session,
    team: Optional[str],
    start: date,
    end: date,
    employee_ids: Iterable[Optional[str]],
) -> set[str]:
    """Кто из перечисленных не состоял в ``team`` ни дня периода."""
    if not team:
        return set()
    members = set(tm.member_intervals(db, [team], start, end))
    return {e for e in employee_ids if e and e not in members}
```

- [ ] **Step 4: Запустить — должны пройти**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/cross_team_occupancy.py tests/services/test_cross_team_occupancy.py
git commit -F - <<'EOF'
feat(planning): брони сотрудников в опорных планах других команд

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: «Разработчик» из Jira для инициатив

**Files:**
- Create: `app/services/jira_developer.py`
- Test: `tests/services/test_jira_developer.py`

- [ ] **Step 1: Падающий тест**

```python
# tests/services/test_jira_developer.py
"""«Разработчик» из Jira: поле задачи, иначе самый частый в поддереве."""

from app.models import BacklogItem
from app.services.jira_developer import jira_developers_for_items
from tests.services.xteam_factory import make_employee, make_issue


def _item(db, issue=None):
    it = BacklogItem(title="x", issue_id=issue.id if issue else None)
    db.add(it)
    db.flush()
    return it


def test_own_field_then_most_frequent_child(db_session, sample_project):
    e1 = make_employee(db_session, "Первый", "A", jira_account_id="acc-1")
    e2 = make_employee(db_session, "Второй", "A", jira_account_id="acc-2")
    make_employee(db_session, "Третий", "A", jira_account_id="acc-3")
    make_employee(db_session, "Ушедший", "A", jira_account_id="acc-off",
                  is_active=False)

    r1 = make_issue(db_session, sample_project, "OS-1", developer="acc-1")
    r2 = make_issue(db_session, sample_project, "OS-2")
    epic = make_issue(db_session, sample_project, "OS-3", parent=r2)
    make_issue(db_session, sample_project, "OS-4", developer="acc-2", parent=epic)
    make_issue(db_session, sample_project, "OS-5", developer="acc-2", parent=epic)
    make_issue(db_session, sample_project, "OS-6", developer="acc-3", parent=r2)
    r3 = make_issue(db_session, sample_project, "OS-7", developer="acc-off")

    i1, i2, i3, i4 = _item(db_session, r1), _item(db_session, r2), _item(db_session, r3), _item(db_session)
    db_session.commit()

    got = jira_developers_for_items(db_session, [i1, i2, i3, i4])

    assert got == {i1.id: e1.id, i2.id: e2.id}


def test_tie_broken_by_account(db_session, sample_project):
    make_employee(db_session, "Б", "A", jira_account_id="acc-b")
    ea = make_employee(db_session, "А", "A", jira_account_id="acc-a")
    root = make_issue(db_session, sample_project, "OS-10")
    make_issue(db_session, sample_project, "OS-11", developer="acc-b", parent=root)
    make_issue(db_session, sample_project, "OS-12", developer="acc-a", parent=root)
    it = _item(db_session, root)
    db_session.commit()

    assert jira_developers_for_items(db_session, [it]) == {it.id: ea.id}
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_jira_developer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.jira_developer'`

- [ ] **Step 3: Реализация**

```python
# app/services/jira_developer.py
"""«Разработчик» из Jira для инициатив плана.

Поле «Разработчик» (настройка ``jira_developer_field_id``) синк кладёт в
``Issue.developer_account_id``. Для инициативы берётся значение самой задачи,
а если оно пустое или человек не найден среди активных — самый частый
«Разработчик» во всём её поддереве (у RFA разработчики стоят на подзадачах
эпиков). Ничья решается по учётной записи Jira — ответ не прыгает.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable

from sqlalchemy.orm import Session

from app.models import BacklogItem, Employee, Issue
from app.services.plan_common import subtree_ids


def jira_developers_for_items(
    db: Session, items: Iterable[BacklogItem]
) -> Dict[str, str]:
    """{backlog_item_id: employee_id} — только где «Разработчик» нашёлся."""
    roots = {it.id: it.issue_id for it in items if it.issue_id}
    if not roots:
        return {}
    trees = subtree_ids(db, list(roots.values()))
    all_ids = set().union(*trees.values()) if trees else set()
    if not all_ids:
        return {}
    dev_of = {
        iid: acc
        for iid, acc in db.query(Issue.id, Issue.developer_account_id)
        .filter(Issue.id.in_(list(all_ids)), Issue.developer_account_id.isnot(None))
        .all()
        if acc
    }
    if not dev_of:
        return {}
    emp_by_acc = {
        acc: eid
        for eid, acc in db.query(Employee.id, Employee.jira_account_id)
        .filter(
            Employee.jira_account_id.in_(list(set(dev_of.values()))),
            Employee.is_active.is_(True),
        )
        .all()
    }

    out: Dict[str, str] = {}
    for item_id, issue_id in roots.items():
        own = dev_of.get(issue_id)
        if own in emp_by_acc:
            out[item_id] = emp_by_acc[own]
            continue
        counts = Counter(
            dev_of[i]
            for i in trees.get(issue_id, ())
            if i != issue_id and dev_of.get(i) in emp_by_acc
        )
        if counts:
            acc = min(counts, key=lambda a: (-counts[a], a))
            out[item_id] = emp_by_acc[acc]
    return out
```

- [ ] **Step 4: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/services/test_jira_developer.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/jira_developer.py tests/services/test_jira_developer.py
git commit -F - <<'EOF'
feat(planning): «Разработчик» из Jira для инициатив плана

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Доступность привлечённого — дни «вне команды» не нулевые

**Files:**
- Modify: `app/services/resource_planning_service.py` (`build_availability`)
- Test: `tests/services/test_rp_borrowed_staff.py`

- [ ] **Step 1: Падающий тест**

```python
# tests/services/test_rp_borrowed_staff.py
"""Привлечение сотрудников из чужих команд в ресурсный план."""

from datetime import date

from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import make_employee

D = date.fromisoformat


def test_borrowed_employee_is_available_outside_plan_team(db_session):
    e = make_employee(db_session, "Чужой", "A")
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    plain = svc.build_availability([e], D("2026-01-05"), D("2026-01-05"), [], team="B")
    borrowed = svc.build_availability(
        [e], D("2026-01-05"), D("2026-01-05"), [], team="B", borrowed={e.id}
    )

    assert plain[e.id][D("2026-01-05")] == 0.0
    assert borrowed[e.id][D("2026-01-05")] == 6.0
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py -v`
Expected: FAIL — `TypeError: ... got an unexpected keyword argument 'borrowed'`

- [ ] **Step 3: Реализация** — в `build_availability`:

Сигнатура: после `team: Optional[str] = None,` добавить параметр:

```python
        team: Optional[str] = None,
        borrowed: Optional[set] = None,
    ) -> Dict[str, Dict[date, float]]:
```

В docstring после абзаца про ``team`` добавить:

```
        ``borrowed`` — привлечённые из других команд: для них дни вне команды
        плана — норма, а не простой.
```

Сразу после `emp_ids = [e.id for e in employees]` добавить:

```python
        borrowed_set = borrowed or set()
```

Строку

```python
                out_of_team = bool(team) and not tm.day_in_intervals(d, spans)
```

заменить на

```python
                out_of_team = (
                    bool(team)
                    and emp.id not in borrowed_set
                    and not tm.day_in_intervals(d, spans)
                )
```

- [ ] **Step 4: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_borrowed_staff.py
git commit -F - <<'EOF'
feat(planning): доступность привлечённого не режется командой плана

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Подбор исполнителей — «Разработчик» из Jira и пулы без привлечённых

**Files:**
- Modify: `app/services/resource_planning_service.py` (`_assign_employees`)
- Test: `tests/services/test_rp_borrowed_staff.py`

- [ ] **Step 1: Падающие тесты** — дописать в `tests/services/test_rp_borrowed_staff.py`:

```python
from app.models import BacklogItem


def _plain_item(db, title="x", dev=10.0, analyst=0.0, assignee=None, priority=1):
    it = BacklogItem(
        title=title, priority=priority, estimate_dev_hours=dev,
        estimate_analyst_hours=analyst, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
    )
    db.add(it)
    db.flush()
    return it


def test_jira_developer_from_other_team_wins(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], jira_dev={item.id: ext.id}, borrowed={ext.id}
    )

    assert res["dev"][item.id] == ext.id


def test_manual_pin_beats_jira_developer(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], pinned={(item.id, "dev", 1): own.id},
        jira_dev={item.id: ext.id}, borrowed={ext.id},
    )

    assert res["dev"][item.id] == own.id


def test_greedy_pool_skips_borrowed(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    a = _plain_item(db_session, "a", priority=2)
    b = _plain_item(db_session, "b", priority=1)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [a, b], [own, ext], borrowed={ext.id}
    )

    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == own.id


def test_analyst_from_other_team_only_manual(db_session):
    b_an = make_employee(db_session, "Аналитик B", "B", role="analyst")
    ext_an = make_employee(db_session, "Аналитик A", "A", role="analyst")
    item = _plain_item(db_session, dev=0.0, analyst=10.0, assignee=ext_an)
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    auto = svc._assign_employees([item], [b_an, ext_an], borrowed={ext_an.id})
    manual = svc._assign_employees(
        [item], [b_an, ext_an], pinned={(item.id, "analyst", 1): ext_an.id},
        borrowed={ext_an.id},
    )

    assert auto["analyst"][item.id] == b_an.id
    assert manual["analyst"][item.id] == ext_an.id
```

- [ ] **Step 2: Запустить — должны упасть**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'jira_dev'`

- [ ] **Step 3: Реализация** — в `_assign_employees`:

Сигнатура — после `capacity: Optional[Dict[str, float]] = None,` добавить:

```python
        capacity: Optional[Dict[str, float]] = None,
        jira_dev: Optional[Dict[str, str]] = None,
        borrowed: Optional[set] = None,
    ) -> Dict[str, Dict[str, Optional[str]]]:
```

В docstring строку про `dev:` заменить на:

```
        - dev:     закреп вручную → «Разработчик» из Jira (``jira_dev``, из любой
                   команды) → greedy по минимальной нагрузке в пуле DEV_ROLES
                   команды (fallback — вся команда). В команде с группами
                   сначала перебираются свои по группе (см. `_pick_in_group`).
        ``borrowed`` — привлечённые из других команд: в жадные пулы и в подбор
        аналитика по исполнителю инициативы не попадают, только закреп / Jira.
```

После `capacity = capacity or {}` добавить:

```python
        jira_dev = jira_dev or {}
        borrowed = borrowed or set()
        # Жадный подбор и подстановка аналитика — только из своей команды.
        team_emps = [e for e in employees if e.id not in borrowed]
```

Дальше в теле функции заменить источники `employees` на `team_emps` в четырёх местах:

```python
        by_id: Dict[str, Employee] = {e.id: e for e in team_emps}
```
```python
        for e in team_emps:
            if e.display_name:
```
```python
        dev_ids = [e.id for e in team_emps if (e.role or "").lower() in DEV_ROLES]
        if not dev_ids:
            dev_ids = [e.id for e in team_emps]

        analyst_ids = [e.id for e in team_emps if (e.role or "").lower() in ANALYST_ROLES]
```

Блок разработки:

```python
            dev_id: Optional[str] = pinned.get((item.id, "dev", 1))
            if not dev_id and dev_ids:
```

заменить на

```python
            dev_id: Optional[str] = pinned.get((item.id, "dev", 1))
            if not dev_id:
                dev_id = jira_dev.get(item.id)
            if not dev_id and dev_ids:
```

- [ ] **Step 4: Запустить — должны пройти (и старые тесты подбора)**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py tests/test_rp_subgroup_assignment.py tests/test_resource_planning_assignment_logic.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_borrowed_staff.py
git commit -F - <<'EOF'
feat(planning): разработчик из Jira и пулы подбора без привлечённых

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Полный расчёт плана — привлечённые и внешняя занятость

**Files:**
- Modify: `app/services/resource_planning_service.py` (`compute_schedule`, новый `_load_borrowed`, `_build_conflict_dicts`, импорты)
- Test: `tests/services/test_rp_borrowed_staff.py`

- [ ] **Step 1: Падающие тесты** — дописать в `tests/services/test_rp_borrowed_staff.py`:

```python
import json

from sqlalchemy import select

from app.models import PlanConflict, ResourcePlanAssignment
from tests.services.xteam_factory import add_item, book, make_issue, make_plan


def _dev_rows(db, plan_id):
    return db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).scalars().all()


def _days(rows):
    out = set()
    for r in rows:
        out |= {k for k, v in json.loads(r.daily_hours_json or "{}").items() if v > 0}
    return out


def _out_of_team(db, plan_id):
    return db.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan_id, PlanConflict.type == "OUT_OF_TEAM"
        )
    ).scalars().all()


def test_jira_developer_borrowed_and_skips_home_bookings(db_session, sample_project):
    """Техкоманда B берёт разработчика E из A по полю Jira и обходит его брони в A."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    item_a = add_item(db_session, sc_a, "Работа A", dev=12)
    book(db_session, plan_a, item_a, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})

    issue = make_issue(db_session, sample_project, "OS-91393", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = _dev_rows(db_session, plan_b.id)
    assert {r.employee_id for r in rows} == {e.id}
    assert _days(rows) == {"2026-01-05", "2026-01-06"}
    assert _out_of_team(db_session, plan_b.id) == []


def test_home_plan_avoids_borrower_bookings(db_session):
    """Обратная сторона: домашняя команда A обходит часы E в опорном плане B."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=12)
    book(db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    rows = _dev_rows(db_session, plan_a.id)
    assert {r.employee_id for r in rows} == {e.id}
    assert _days(rows) == {"2026-01-05", "2026-01-06"}


def test_manual_pin_to_other_team_gets_hours_without_out_of_team(db_session):
    own = make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Чужой", "A")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12)
    db_session.commit()
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan_b.id)

    row = _dev_rows(db_session, plan_b.id)[0]
    assert row.employee_id == own.id
    row.employee_id = ext.id
    row.pinned_employee = True
    db_session.commit()

    svc.compute_schedule(plan_b.id)

    rows = _dev_rows(db_session, plan_b.id)
    assert {r.employee_id for r in rows} == {ext.id}
    assert sum(r.hours_allocated or 0 for r in rows) == 12
    assert _days(rows) == {"2026-01-01", "2026-01-02"}
    assert _out_of_team(db_session, plan_b.id) == []
```

- [ ] **Step 2: Запустить — должны упасть**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py -v`
Expected: FAIL — первый тест: разработка уходит «Своему B» (или без часов); второй: дни 01–02 января; третий: у закреплённого чужого нет часов / есть `OUT_OF_TEAM`.

- [ ] **Step 3: Импорты** — в шапке `app/services/resource_planning_service.py` после строки `from app.services import opo_policy, team_membership as tm` добавить:

```python
from app.services import cross_team_occupancy as cto
from app.services.jira_developer import jira_developers_for_items
```

- [ ] **Step 4: Новый метод** — сразу после метода `_load_employees` вставить:

```python
    def _load_borrowed(self, ids: set) -> List[Employee]:
        """Активные сотрудники вне команды плана, попавшие в план.

        Источники — ручное закрепление фазы и «Разработчик» из Jira.
        """
        ids = {i for i in ids if i}
        if not ids:
            return []
        rows = (
            self.db.execute(
                select(Employee).where(
                    Employee.id.in_(list(ids)),
                    Employee.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        return list(rows)
```

- [ ] **Step 5: Состав пула в `compute_schedule`** — фрагмент

```python
        employees = self._load_employees(plan)
        if not employees:
            plan.status = "ready"
```

заменить на

```python
        employees = self._load_employees(plan)
        team_employees = list(employees)
        # Привлечённые: закреплены вручную или стоят «Разработчиком» в Jira,
        # но в команде плана не состояли ни дня квартала.
        jira_dev = jira_developers_for_items(self.db, items)
        team_ids = {e.id for e in team_employees}
        borrowed_rows = self._load_borrowed(
            (set(pinned_map.values()) | set(jira_dev.values())) - team_ids
        )
        borrowed = {e.id for e in borrowed_rows}
        employees = team_employees + borrowed_rows
        if not employees:
            plan.status = "ready"
```

- [ ] **Step 6: Доступность минус внешняя занятость** — вызов

```python
        avail = self.build_availability(
            employees, q_start, q_end_extended, list(blocks), team=plan.team
        )
```

заменить на

```python
        raw_avail = self.build_availability(
            employees, q_start, q_end_extended, list(blocks),
            team=plan.team, borrowed=borrowed,
        )
        # Часы, забронированные на этих людей опорными планами других команд,
        # раскладка не трогает — в обе стороны (домашняя ↔ привлекающая).
        external = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=plan.team,
                year=plan.year,
                quarter=cto.quarter_num(plan.quarter),
                employee_ids=[e.id for e in employees],
                start=q_start,
                end=q_end_extended,
            )
        )
        avail = cto.subtract_occupancy(raw_avail, external)
```

- [ ] **Step 7: Подбор с Jira и привлечёнными** — в вызове `self._assign_employees(` после `capacity=quarter_capacity,` добавить:

```python
            capacity=quarter_capacity,
            jira_dev=jira_dev,
            borrowed=borrowed,
        )
```

- [ ] **Step 8: Пулы ОПЭ** — фрагмент

```python
                    opo_analyst_pool = [
                        e.id for e in employees
                        if (e.role or "").lower() in ANALYST_ROLES
                    ]
                    opo_dev_pool = [
                        e.id for e in employees
                        if (e.role or "").lower() in DEV_ROLES
                    ]
                    analyst_id = assignments_by_role["analyst"].get(item.id)
                    dev_id = assignments_by_role["dev"].get(item.id)

                    # Аналитика для ОПЭ — только из аналитического пула.
                    if (not analyst_id or analyst_id not in opo_analyst_pool) and opo_analyst_pool:
```

заменить на

```python
                    # Пулы запасного выбора — только своя команда; исполнитель
                    # анализа/разработки, пришедший из другой команды, остаётся.
                    opo_analyst_pool = [
                        e.id for e in team_employees
                        if (e.role or "").lower() in ANALYST_ROLES
                    ]
                    opo_dev_pool = [
                        e.id for e in team_employees
                        if (e.role or "").lower() in DEV_ROLES
                    ]
                    analyst_id = assignments_by_role["analyst"].get(item.id)
                    dev_id = assignments_by_role["dev"].get(item.id)
                    analyst_ok = bool(analyst_id) and (
                        analyst_id in opo_analyst_pool or analyst_id in borrowed
                    )
                    dev_ok = bool(dev_id) and dev_id != analyst_id and (
                        dev_id in opo_dev_pool or dev_id in borrowed
                    )

                    # Аналитика для ОПЭ — только из аналитического пула.
                    if not analyst_ok and opo_analyst_pool:
```

и строку

```python
                    if (not dev_id or dev_id not in opo_dev_pool or dev_id == analyst_id) and dev_candidates:
```

на

```python
                    dev_ok = dev_ok and dev_id != analyst_id
                    if not dev_ok and dev_candidates:
```

- [ ] **Step 9: Выравниватель** — строки

```python
        role_pools = self._build_role_pools(employees)
        leveling_events = leveler.level(new_assignments, avail, q_end_extended, role_pools)
```

заменить на

```python
        # Переназначать можно только внутри своей команды. Перегрузку
        # выравниватель меряет по ёмкости без чужих броней: пересечение с
        # другой командой — отдельный «живой» конфликт в плане привлекающей
        # команды (см. get_gantt), а не перегрузка в домашнем.
        role_pools = self._build_role_pools(team_employees)
        leveling_events = leveler.level(new_assignments, raw_avail, q_end_extended, role_pools)
```

- [ ] **Step 10: Конфликты** — вызов

```python
        detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
```

заменить на

```python
        detected = self._build_conflict_dicts(
            plan, new_assignments, employees, q_end, borrowed=borrowed
        )
```

В `_build_conflict_dicts` сигнатуру дополнить параметром:

```python
        q_end: date,
        borrowed: Optional[set] = None,
    ) -> List[dict]:
```

в docstring строку про OUT_OF_TEAM заменить на

```
        - OUT_OF_TEAM (дни фазы вне периода участия исполнителя в команде;
          привлечённых из других команд не касается)
```

и в блоке OUT_OF_TEAM

```python
        dated = [
            a
            for a in assignments
            if a.employee_id
            and isinstance(a.start_date, date)
```

заменить на

```python
        borrowed = borrowed or set()
        dated = [
            a
            for a in assignments
            if a.employee_id
            and a.employee_id not in borrowed
            and isinstance(a.start_date, date)
```

- [ ] **Step 11: Запустить — новые и связанные тесты**

Run: `py -3.10 -m pytest tests/services/test_rp_borrowed_staff.py tests/services/test_rp_out_of_team_conflict.py tests/test_resource_planning_service.py tests/test_resource_planning_allocate_hours.py tests/services/test_compute_schedule_extends_pinned.py tests/test_rp_pinned_start_ux.py -v`
Expected: all passed

- [ ] **Step 12: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_rp_borrowed_staff.py
git commit -F - <<'EOF'
feat(planning): расчёт плана с привлечёнными и занятостью в других командах

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: Загрузка за квартал и эндпоинт кандидатов в исполнители

**Files:**
- Modify: `app/services/cross_team_occupancy.py` (`quarter_load_pct`)
- Modify: `app/api/endpoints/resource_planning.py` (схемы + эндпоинт)
- Test: `tests/services/test_cross_team_occupancy.py`, `tests/api/test_rp_cross_team_gantt.py`

- [ ] **Step 1: Падающий тест загрузки** — дописать в `tests/services/test_cross_team_occupancy.py`:

```python
def test_quarter_load_pct_counts_all_reference_plans(db_session):
    e, m = _setup_booked(db_session)  # 12 + 9 = 21 ч в опорном плане A

    load = cto.quarter_load_pct(db_session, 2026, 1, [e, m])

    # Q1 2026 без записей календаря: 64 будних дня × 6 ч = 384 ч.
    assert load[e.id] == round(21 / 384 * 100, 1)
    assert load[m.id] == 0.0
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py::test_quarter_load_pct_counts_all_reference_plans -v`
Expected: FAIL — `AttributeError: ... has no attribute 'quarter_load_pct'`

- [ ] **Step 3: Реализация** — дописать в конец `app/services/cross_team_occupancy.py`:

```python
def quarter_load_pct(
    db: Session,
    year: int,
    quarter: int,
    employees: List["Employee"],
) -> Dict[str, float]:
    """Загрузка за квартал по всем опорным планам, % от «календарь − отсутствия».

    Шкала та же, что у планировщика (6 ч в обычный день).
    """
    if not employees:
        return {}
    from app.services.plan_common import quarter_bounds
    from app.services.resource_planning_service import ResourcePlanningService

    start, end = quarter_bounds(year, quarter)
    booked = daily_totals(
        external_bookings(
            db, team=None, year=year, quarter=quarter,
            employee_ids=[e.id for e in employees], start=start, end=end,
        )
    )
    avail = ResourcePlanningService(db).build_availability(employees, start, end, [])
    out: Dict[str, float] = {}
    for e in employees:
        cap = sum(avail.get(e.id, {}).values())
        hours = sum(booked.get(e.id, {}).values())
        out[e.id] = round(hours / cap * 100.0, 1) if cap > 0 else 0.0
    return out
```

И в импортах модуля добавить `TYPE_CHECKING`-импорт сотрудника (для аннотации):

```python
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from app.models import Employee
```

(строку `from typing import Dict, Iterable, List, Optional` заменить на первую строку выше; блок `if TYPE_CHECKING:` поставить после импортов `app.services`).

- [ ] **Step 4: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/services/test_cross_team_occupancy.py -v`
Expected: 12 passed

- [ ] **Step 5: Падающий тест эндпоинта кандидатов**

```python
# tests/api/test_rp_cross_team_gantt.py
"""Диаграмма и выбор исполнителя при привлечении сотрудников из чужих команд."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.project import Project
from tests.services.xteam_factory import add_item, book, make_employee, make_issue, make_plan

BASE = "/api/v1/resource-planning/resource-plans"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def two_teams(db_session):
    """E — разработчик команды A; B берёт его на разработку поверх его брони в A."""
    project = Project(jira_project_id="p-x", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    d = make_employee(db_session, "Свой B", "B")
    other = make_employee(db_session, "Посторонний", "C")

    sc_a, plan_a = make_plan(db_session, "A")
    item_a = add_item(db_session, sc_a, "Работа A", dev=12)
    a_row = book(db_session, plan_a, item_a, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})

    issue = make_issue(db_session, project, "OS-91393", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    b_row = book(
        db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0},
        pinned_employee=True,
    )
    db_session.commit()
    return {
        "e": e.id, "d": d.id, "other": other.id,
        "plan_a": plan_a.id, "plan_b": plan_b.id,
        "a_row": a_row.id, "b_row": b_row.id,
    }


def test_candidates_grouped_with_load(client, two_teams):
    t = two_teams
    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/candidates")
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}

    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [t["e"]]
    assert groups["jira"]["label"] == "Из Jira"
    assert [c["employee_id"] for c in groups["team"]["employees"]] == [t["d"]]
    assert t["other"] in [c["employee_id"] for c in groups["other"]["employees"]]
    jira_e = groups["jira"]["employees"][0]
    assert jira_e["team"] == "A"
    assert 0 < jira_e["load_pct"] < 10  # 24 ч из 384
    assert groups["team"]["employees"][0]["load_pct"] == 0.0
```

- [ ] **Step 6: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py -v`
Expected: FAIL — 404/405 на `/candidates`

- [ ] **Step 7: Схемы** — в `app/api/endpoints/resource_planning.py` сразу после класса `EmployeeChangePreviewResponse` добавить:

```python
class CandidateOut(BaseModel):
    """Кандидат в исполнители фазы."""

    employee_id: str
    display_name: str
    role: Optional[str] = None
    team: Optional[str] = None
    # Загрузка за квартал плана по всем опорным планам команд, %.
    load_pct: float = 0.0
    member_from: Optional[date] = None
    member_to: Optional[date] = None


class CandidateGroupOut(BaseModel):
    key: Literal["jira", "team", "other"]
    label: str
    employees: List[CandidateOut]
```

- [ ] **Step 8: Эндпоинт** — сразу после функции `preview_employee_change` добавить:

```python
@router.get(
    "/resource-plans/{plan_id}/assignments/{assignment_id}/candidates",
    response_model=List[CandidateGroupOut],
)
def list_assignment_candidates(
    plan_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Все активные сотрудники тремя группами: «Из Jira», «Моя команда», «Другие команды».

    «Из Jira»: для разработки — поле «Разработчик», для остальных фаз —
    исполнитель инициативы. У каждого — загрузка за квартал плана по всем
    опорным планам команд.
    """
    from app.models import Employee
    from app.services import cross_team_occupancy as cto
    from app.services import team_membership as tm
    from app.services.jira_developer import jira_developers_for_items

    a = db.execute(
        select(ResourcePlanAssignment)
        .options(joinedload(ResourcePlanAssignment.backlog_item))
        .where(
            ResourcePlanAssignment.id == assignment_id,
            ResourcePlanAssignment.plan_id == plan_id,
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    try:
        q_start, q_end = ResourcePlanningService(db)._quarter_bounds(plan)
    except ValueError as e:
        raise HTTPException(422, str(e))
    q = cto.quarter_num(plan.quarter)

    employees = list(
        db.execute(select(Employee).where(Employee.is_active == True))  # noqa: E712
        .scalars()
        .all()
    )
    by_id = {e.id: e for e in employees}
    member_iv = tm.member_intervals(db, [plan.team], q_start, q_end) if plan.team else {}

    jira_ids: List[str] = []
    item = a.backlog_item
    if item is not None:
        if a.phase == "dev":
            dev = jira_developers_for_items(db, [item]).get(item.id)
            if dev:
                jira_ids.append(dev)
        elif item.assignee_employee_id:
            jira_ids.append(item.assignee_employee_id)
    jira_ids = [i for i in jira_ids if i in by_id]

    load = cto.quarter_load_pct(db, plan.year, q, employees) if plan.year and q else {}

    def _out(e: "Employee") -> CandidateOut:
        iv = member_iv.get(e.id) or []
        return CandidateOut(
            employee_id=e.id,
            display_name=e.display_name,
            role=e.role,
            team=e.team,
            load_pct=load.get(e.id, 0.0),
            member_from=(iv[0][0] if iv and iv[0][0] > q_start else None),
            member_to=(iv[-1][1] if iv and iv[-1][1] < q_end else None),
        )

    def _name(e: "Employee") -> str:
        return (e.display_name or "").lower()

    jira = [by_id[i] for i in jira_ids]
    team = sorted(
        (e for e in employees if e.id in member_iv and e.id not in jira_ids), key=_name
    )
    other = sorted(
        (e for e in employees if e.id not in member_iv and e.id not in jira_ids),
        key=_name,
    )
    groups: List[CandidateGroupOut] = []
    for key, label, rows in (
        ("jira", "Из Jira", jira),
        ("team", "Моя команда", team),
        ("other", "Другие команды", other),
    ):
        if rows:
            groups.append(
                CandidateGroupOut(key=key, label=label, employees=[_out(e) for e in rows])
            )
    return groups
```

- [ ] **Step 9: Запустить — должен пройти**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py -v`
Expected: 1 passed

- [ ] **Step 10: Commit**

```bash
git add app/services/cross_team_occupancy.py app/api/endpoints/resource_planning.py tests/services/test_cross_team_occupancy.py tests/api/test_rp_cross_team_gantt.py
git commit -F - <<'EOF'
feat(planning): выбор исполнителя из всех сотрудников с загрузкой за квартал

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Диаграмма — привлечённые в подвале, брони других команд, живой конфликт

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (схемы, `get_gantt`, `_cross_team_conflicts`)
- Test: `tests/api/test_rp_cross_team_gantt.py`

- [ ] **Step 1: Падающие тесты** — дописать в `tests/api/test_rp_cross_team_gantt.py`:

```python
def _gantt(client, plan_id):
    r = client.get(f"{BASE}/{plan_id}/gantt")
    assert r.status_code == 200, r.text
    return r.json()


def _row(body, emp_id):
    return next(r for r in body["employee_load"] if r["employee_id"] == emp_id)


def _day(row, iso):
    return next(d for d in row["days"] if d["date"] == iso)


def test_borrower_plan_shows_overlap_bookings_and_borrowed_row(client, two_teams):
    t = two_teams
    body = _gantt(client, t["plan_b"])

    live = [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"]
    assert len(live) == 1
    assert live[0]["assignment_id"] == t["b_row"]
    assert live[0]["is_live"] is True
    assert "пересекается с планом A" in live[0]["message"]

    assert [(b["employee_id"], b["team"], b["phase"]) for b in body["external_bookings"]] == [
        (t["e"], "A", "dev")
    ]
    assert body["external_bookings"][0]["provisional"] is False
    assert body["external_bookings"][0]["employee_name"] == "Пряничников"

    row = _row(body, t["e"])
    assert row["is_borrowed"] is True
    assert row["borrowed_from"] == "A"
    day = _day(row, "2026-01-01")
    assert day["pct"] == 100.0
    assert day["ext_pct"] == 100.0
    assert day["off"] is None
    assert _day(row, "2026-01-05")["off"] is None  # вне команды B — не «вне команды»


def test_home_plan_shows_other_team_share_without_conflict(client, two_teams):
    t = two_teams
    body = _gantt(client, t["plan_a"])

    assert [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    assert body["external_bookings"] == []
    row = _row(body, t["e"])
    assert row["is_borrowed"] is False
    assert _day(row, "2026-01-01")["ext_pct"] == 100.0
    assert _day(row, "2026-01-05")["ext_pct"] == 0.0
```

- [ ] **Step 2: Запустить — должны упасть**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py -v`
Expected: FAIL — `KeyError: 'external_bookings'` / нет строки E в подвале B

- [ ] **Step 3: Схемы** — в `app/api/endpoints/resource_planning.py`:

В `ConflictOut` после `updated_at: datetime` добавить:

```python
    updated_at: datetime
    # «Живой» конфликт: считается при чтении диаграммы, в БД не хранится,
    # статус у него не меняется.
    is_live: bool = False
```

В `EmployeeLoadDay` после `off: Optional[str] = None` добавить:

```python
    # Доля ёмкости дня, занятая опорными планами других команд, %.
    ext_pct: float = 0.0
```

В `EmployeeLoadOut` в конец полей (после полей Части 1.6) добавить:

```python
    # Привлечён из другой команды: в команде плана не состоял ни дня квартала.
    is_borrowed: bool = False
    borrowed_from: Optional[str] = None
```

Перед классом `GanttProjection` добавить:

```python
class ExternalBookingOut(BaseModel):
    """Фаза привлечённого сотрудника в опорном плане другой команды."""

    assignment_id: str
    employee_id: str
    employee_name: Optional[str] = None
    team: str
    issue_key: Optional[str] = None
    title: str
    phase: str
    start: date
    end: date
    daily_hours: Dict[str, float] = {}
    provisional: bool = False
```

В `GanttProjection` после `employee_load: List[EmployeeLoadOut] = []` добавить:

```python
    # Брони привлечённых в опорных планах других команд — блок «Привлечённые».
    external_bookings: List[ExternalBookingOut] = []
```

- [ ] **Step 4: Помощник живого конфликта** — сразу перед функцией `get_gantt` добавить:

```python
def _cross_team_conflicts(
    plan: ResourcePlan,
    assignments_raw: List[ResourcePlanAssignment],
    borrowed: set,
    used: Dict[str, Dict[date, float]],
    capacity: Dict[str, Dict[date, float]],
    bookings: list,
    emp_names: Dict[str, str],
) -> List["ConflictOut"]:
    """Пересечение с планами других команд — только у привлечённых этого плана."""
    from app.services import cross_team_occupancy as cto

    ext_by_emp = cto.daily_totals(bookings)
    teams_on: Dict[tuple, set] = {}
    for b in bookings:
        for d in b.daily_hours:
            teams_on.setdefault((b.employee_id, d), set()).add(b.team)
    stamp = plan.computed_at or datetime.utcnow()

    out: List[ConflictOut] = []
    for eid in sorted(borrowed):
        days = set(
            cto.overlap_days(used.get(eid, {}), ext_by_emp.get(eid, {}), capacity.get(eid, {}))
        )
        if not days:
            continue
        for a in assignments_raw:
            if a.employee_id != eid or not a.start_date or not a.end_date:
                continue
            own_daily = _parse_daily_map(a.daily_hours_json)
            a_days = sorted(
                d
                for d in days
                if a.start_date <= d <= a.end_date and (not own_daily or d in own_daily)
            )
            if not a_days:
                continue
            teams = sorted(set().union(*(teams_on.get((eid, d), set()) for d in a_days)))
            name = emp_names.get(eid) or "Сотрудник"
            out.append(
                ConflictOut(
                    id=f"live:CROSS_TEAM_OVERLAP:{a.id}",
                    type="CROSS_TEAM_OVERLAP",
                    severity="warning",
                    status="open",
                    backlog_item_id=a.backlog_item_id,
                    backlog_item_title=a.backlog_item.title if a.backlog_item else None,
                    employee_id=eid,
                    employee_name=name,
                    assignment_id=a.id,
                    window_start=datetime.combine(a_days[0], datetime.min.time()),
                    window_end=datetime.combine(a_days[-1], datetime.min.time()),
                    metric_value=float(len(a_days)),
                    message=(
                        f"{name} пересекается с планом {', '.join(teams)} "
                        f"({_format_date_range(a_days[0], a_days[-1])})"
                    ),
                    created_at=stamp,
                    updated_at=stamp,
                    is_live=True,
                )
            )
    return out
```

(`_parse_daily_map` и `_format_date_range` — функции этого же модуля, объявлены ниже; вызываются во время выполнения, импорт не нужен.)

- [ ] **Step 5: `get_gantt` — состав подвала и брони.** Перед строкой `employee_load: list[EmployeeLoadOut] = []` добавить:

```python
    external_out: list[ExternalBookingOut] = []
    live_conflicts: list[ConflictOut] = []
```

Внутри `if plan.team:` после `from app.services import team_membership as tm` добавить:

```python
        from app.services import cross_team_occupancy as cto
```

Фрагмент

```python
        member_ids = tm.members_overlapping(db, [plan.team], q_start, q_end)
        member_iv = tm.member_intervals(db, [plan.team], q_start, q_end)
        plan_employees = (
            db.execute(
                select(Employee).where(
                    Employee.id.in_(list(member_ids)),
                    Employee.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
            if member_ids
            else []
        )
        if plan_employees:
            avail = svc.build_availability(
                plan_employees, q_start, q_end, [], team=plan.team
            )
```

заменить на

```python
        member_ids = tm.members_overlapping(db, [plan.team], q_start, q_end)
        member_iv = tm.member_intervals(db, [plan.team], q_start, q_end)
        # Привлечённые — исполнители фаз этого плана, не состоявшие в команде
        # ни дня квартала. Их строки тоже идут в подвал.
        borrowed = {eid for eid in emp_ids_in_plan if eid not in member_iv}
        row_ids = set(member_ids) | borrowed
        plan_employees = (
            db.execute(
                select(Employee).where(
                    Employee.id.in_(list(row_ids)),
                    Employee.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
            if row_ids
            else []
        )
        if plan_employees:
            avail = svc.build_availability(
                plan_employees, q_start, q_end, [], team=plan.team, borrowed=borrowed
            )
            _, _, q_end_ext = svc._quarter_bounds_extended(plan)
            bookings = cto.external_bookings(
                db,
                team=plan.team,
                year=plan.year,
                quarter=cto.quarter_num(plan.quarter),
                employee_ids=[e.id for e in plan_employees],
                start=q_start,
                end=q_end_ext,
            )
            ext_daily = cto.daily_totals(bookings)
            home_rows = tm.membership_rows(db, list(borrowed))
            home_team = {
                e.id: (
                    tm.team_on_day(home_rows.get(e.id, []), q_start)
                    or tm.team_on_day(home_rows.get(e.id, []), q_end)
                    or e.team
                )
                for e in plan_employees
                if e.id in borrowed
            }
```

- [ ] **Step 6: `get_gantt` — доля других команд по дням.** В посуточном цикле строки

```python
                    av = avail.get(e.id, {}).get(d, 0.0)
                    u = used.get(e.id, {}).get(d, 0.0)
                    pct = (u / av * 100.0) if av > 0 else 0.0
```

заменить на

```python
                    av = avail.get(e.id, {}).get(d, 0.0)
                    u = used.get(e.id, {}).get(d, 0.0)
                    pct = (u / av * 100.0) if av > 0 else 0.0
                    x = ext_daily.get(e.id, {}).get(d, 0.0)
                    ext_pct = (x / av * 100.0) if av > 0 else 0.0
```

и

```python
                    days_out.append(EmployeeLoadDay(date=d, pct=round(pct, 1), off=off))
```

на

```python
                    days_out.append(
                        EmployeeLoadDay(
                            date=d, pct=round(pct, 1), off=off, ext_pct=round(ext_pct, 1)
                        )
                    )
```

В вызове `EmployeeLoadOut(` (внутри `employee_load.append(...)`) добавить два аргумента к уже существующим (включая `left_to` / `joined_from` из Части 1.6):

```python
                        is_borrowed=e.id in borrowed,
                        borrowed_from=home_team.get(e.id),
```

Если код Части 1.6 для `left_to` / `joined_from` у привлечённого (без отрезков участия) даёт не `None` — обнулить эти поля для `e.id in borrowed`: подписи «выбыл/пришёл» относятся только к своей команде.

- [ ] **Step 7: `get_gantt` — выход блока и конфликтов.** Сразу после цикла `for e in plan_employees:` (на том же уровне, внутри `if plan_employees:`) добавить:

```python
            names = {e.id: e.display_name for e in plan_employees}
            external_out = [
                ExternalBookingOut(
                    assignment_id=b.assignment_id,
                    employee_id=b.employee_id,
                    employee_name=names.get(b.employee_id),
                    team=b.team,
                    issue_key=b.issue_key,
                    title=b.title,
                    phase=b.phase,
                    start=b.start,
                    end=b.end,
                    daily_hours={d.isoformat(): h for d, h in b.daily_hours.items()},
                    provisional=b.provisional,
                )
                for b in bookings
                if b.employee_id in borrowed
            ]
            live_conflicts = _cross_team_conflicts(
                plan, assignments_raw, borrowed, used, avail, bookings, names
            )
```

Строку

```python
    conflicts = _detect_conflicts(plan, assignments_raw, db)
```

заменить на

```python
    conflicts = _detect_conflicts(plan, assignments_raw, db) + live_conflicts
```

и в `return GanttProjection(` после `employee_load=employee_load,` добавить:

```python
        external_bookings=external_out,
```

- [ ] **Step 8: Запустить — новые и старые тесты диаграммы**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py tests/test_resource_planning_endpoints.py tests/test_membership_periods_resource.py -v`
Expected: all passed

- [ ] **Step 9: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_rp_cross_team_gantt.py
git commit -F - <<'EOF'
feat(planning): диаграмма показывает привлечённых и пересечения с другими командами

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Расшифровки фазы и конфликта для привлечённого

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (`explain_conflict`, `explain_assignment`)
- Test: `tests/api/test_rp_cross_team_gantt.py`

- [ ] **Step 1: Падающий тест** — дописать:

```python
def test_explain_borrowed_assignment_counts_external_bookings(client, two_teams, db_session):
    import json
    from datetime import date

    from app.models import ResourcePlanAssignment

    t = two_teams
    # В плане A оставляем бронь только на 01.01.
    a_row = db_session.get(ResourcePlanAssignment, t["a_row"])
    a_row.daily_hours_json = json.dumps({"2026-01-01": 6.0})
    a_row.end_date = date(2026, 1, 1)
    a_row.hours_allocated = 6.0
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/explain")
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["daily_breakdown"]}

    assert days["2026-01-01"]["available_hours"] == 0.0  # занят планом A
    assert days["2026-01-02"]["available_hours"] == 6.0  # свободен, не «вне команды B»
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py::test_explain_borrowed_assignment_counts_external_bookings -v`
Expected: FAIL — 02.01 даёт `0.0` (день считается «вне команды B»)

- [ ] **Step 3: `explain_assignment`** — фрагмент

```python
    full_avail: Dict[date, float] = {}
    if a.employee_id and horizon_start and horizon_end:
        full_avail = svc.build_availability(
            [e for e in employees if e.id == a.employee_id],
            horizon_start,
            horizon_end,
            list(blocks),
            team=plan.team,
        ).get(a.employee_id, {})
```

заменить на

```python
    full_avail: Dict[date, float] = {}
    if a.employee_id and horizon_start and horizon_end:
        from app.services import cross_team_occupancy as cto

        try:
            eq_start, eq_end = svc._quarter_bounds(plan)
            borrowed_here = cto.borrowed_ids(
                db, plan.team, eq_start, eq_end, [a.employee_id]
            )
        except ValueError:
            borrowed_here = set()
        raw_avail = svc.build_availability(
            [e for e in employees if e.id == a.employee_id],
            horizon_start,
            horizon_end,
            list(blocks),
            team=plan.team,
            borrowed=borrowed_here,
        )
        # «Доступно» — за вычетом броней других команд: ровно то, что видел
        # планировщик при раскладке.
        booked = cto.daily_totals(
            cto.external_bookings(
                db,
                team=plan.team,
                year=plan.year,
                quarter=cto.quarter_num(plan.quarter),
                employee_ids=[a.employee_id],
                start=horizon_start,
                end=horizon_end,
            )
        )
        full_avail = cto.subtract_occupancy(raw_avail, booked).get(a.employee_id, {})
```

- [ ] **Step 4: `explain_conflict`** — перед строкой `svc = ResourcePlanningService(db)` (внутри `explain_conflict`) добавить:

```python
    from app.services import cross_team_occupancy as cto

    try:
        cq_start, cq_end = ResourcePlanningService(db)._quarter_bounds(plan)
        borrowed_here = cto.borrowed_ids(db, team, cq_start, cq_end, [c.employee_id])
    except ValueError:
        borrowed_here = set()
```

и в обоих вызовах `svc.build_availability(` внутри `explain_conflict` добавить аргумент `borrowed=borrowed_here,` после `team=team,`. Ёмкость здесь остаётся «сырой» — перегрузку выравниватель меряет так же (решение 3).

- [ ] **Step 5: Запустить**

Run: `py -3.10 -m pytest tests/api/test_rp_cross_team_gantt.py tests/test_resource_planning_endpoints.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_rp_cross_team_gantt.py
git commit -F - <<'EOF'
feat(planning): расшифровка фазы учитывает брони других команд

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Базовые ресурсы сценария за вычетом броней других команд

**Files:**
- Modify: `app/services/resource_base_service.py`
- Modify: `app/api/endpoints/planning.py` (`ResourceSummaryOut`, `scenario_resource_summary`)
- Test: `tests/services/test_resource_base_external.py`

- [ ] **Step 1: Падающий тест**

```python
# tests/services/test_resource_base_external.py
"""База ресурса сценария вычитает часы, забронированные другими командами."""

from datetime import date

from app.services.resource_base_service import ResourceBaseService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan


def _setup(db_session):
    e = make_employee(db_session, "Пряничников", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a


def test_daily_base_minus_other_team_bookings(db_session):
    e, sc_a = _setup(db_session)

    base = ResourceBaseService(db_session).compute(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    by_day = {d.date: d.hours for d in emp.days}
    assert by_day[date(2026, 1, 5)] == 2.0
    assert by_day[date(2026, 1, 6)] == 8.0


def test_summary_available_minus_bookings(db_session):
    e, sc_a = _setup(db_session)

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == round(s.gross_by_role["developer"] - 6.0, 2)
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py -v`
Expected: FAIL — 8.0 вместо 2.0; `AttributeError: ... 'booked_by_other_teams_by_role'`

- [ ] **Step 3: Реализация** — `app/services/resource_base_service.py`:

Импорты: строку `from dataclasses import dataclass` заменить на `from dataclasses import dataclass, field`; после `from app.services import team_membership as tm` добавить:

```python
from app.services import cross_team_occupancy as cto
```

В `ResourceSummary` последним полем добавить:

```python
    # Часы сотрудников команды, забронированные опорными планами других
    # команд квартала (только дни участия в этой команде): роль → часы.
    booked_by_other_teams_by_role: dict[str, float] = field(default_factory=dict)
```

В `compute` сразу после запроса `employees = (...)` добавить:

```python
        # Часы, забронированные на этих людей опорными планами других команд.
        booked = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            )
        )
```

и строку

```python
                days_out.append(EmployeeDayHours(date=cur, hours=round(norm * pct, 2)))
```

заменить на

```python
                taken = booked.get(e.id, {}).get(cur, 0.0)
                days_out.append(
                    EmployeeDayHours(date=cur, hours=round(max(0.0, norm * pct - taken), 2))
                )
```

В `compute_summary` перед комментарием `# --- доступные часы = валовые − обязательные ...` добавить:

```python
        # --- брони других команд (только дни участия в этой команде) ---
        booked = cto.daily_totals(
            cto.external_bookings(
                self.db,
                team=team,
                year=year,
                quarter=q,
                employee_ids=[e.id for e in employees],
                start=period_start,
                end=last_day,
            )
        )
        booked_by_role: dict[str, float] = {}
        for e in employees:
            emp_intervals = intervals.get(e.id, [])
            h = sum(
                v for d, v in booked.get(e.id, {}).items()
                if tm.day_in_intervals(d, emp_intervals)
            )
            if e.role and h > 0:
                booked_by_role[e.role] = round(booked_by_role.get(e.role, 0.0) + h, 2)
```

строку

```python
            available_by_role[role] = round(max(0.0, gross - mandatory_total), 2)
```

заменить на

```python
            available_by_role[role] = round(
                max(0.0, gross - mandatory_total - booked_by_role.get(role, 0.0)), 2
            )
```

и в `return ResourceSummary(` последним аргументом добавить:

```python
            booked_by_other_teams_by_role=booked_by_role,
```

- [ ] **Step 4: API** — `app/api/endpoints/planning.py`: в `ResourceSummaryOut` последним полем:

```python
    # Часы команды, забронированные планами других команд (уже вычтены из «На бэклог»).
    booked_by_other_teams_by_role: Dict[str, float] = {}
```

в `scenario_resource_summary` в `ResourceSummaryOut(` после `available_by_subgroup_role=summary.available_by_subgroup_role,` добавить:

```python
        booked_by_other_teams_by_role=summary.booked_by_other_teams_by_role,
```

- [ ] **Step 5: Запустить**

Run: `py -3.10 -m pytest tests/services/test_resource_base_external.py tests/test_resource_base_service.py tests/test_resource_summary_subgroups.py tests/test_api_planning_resource.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_base_service.py app/api/endpoints/planning.py tests/services/test_resource_base_external.py
git commit -F - <<'EOF'
feat(planning): ёмкость сценария за вычетом занятости в других командах

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 11: Фронт — типы и чистые помощники (vitest)

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`, `frontend/src/types/api.ts`
- Create: `frontend/src/utils/externalBookings.ts` (+ `.test.ts`), `frontend/src/utils/heatmapFill.ts` (+ `.test.ts`), `frontend/src/utils/rpCandidates.ts` (+ `.test.ts`)

- [ ] **Step 1: Типы API** — `frontend/src/api/resourcePlanning.ts`:

В `ConflictOut` после `updated_at: string;`:

```ts
  /** «Живой» конфликт (пересечение с другой командой): не хранится, статус не меняется. */
  is_live?: boolean;
```

В `EmployeeLoadDay` после `off?: ...`:

```ts
  /** Доля ёмкости дня, занятая планами других команд, %. */
  ext_pct?: number;
```

В `EmployeeLoadOut` в конец:

```ts
  /** Привлечён из другой команды (в команде плана не состоял ни дня квартала). */
  is_borrowed?: boolean;
  borrowed_from?: string | null;
```

Перед `export interface GanttProjection`:

```ts
/** Фаза привлечённого сотрудника в опорном плане другой команды. */
export interface ExternalBookingOut {
  assignment_id: string;
  employee_id: string;
  employee_name: string | null;
  team: string;
  issue_key: string | null;
  title: string;
  phase: string;
  start: string;
  end: string;
  daily_hours: Record<string, number>;
  provisional: boolean;
}
```

В `GanttProjection` после `employee_load?: EmployeeLoadOut[];`:

```ts
  external_bookings?: ExternalBookingOut[];
```

После функции `previewEmployeeChange`:

```ts
export interface AssignmentCandidate {
  employee_id: string;
  display_name: string;
  role: string | null;
  team: string | null;
  load_pct: number;
  member_from?: string | null;
  member_to?: string | null;
}

export interface AssignmentCandidateGroup {
  key: 'jira' | 'team' | 'other';
  label: string;
  employees: AssignmentCandidate[];
}

export const getAssignmentCandidates = (planId: string, assignmentId: string) =>
  api.get<AssignmentCandidateGroup[]>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/candidates`,
  );
```

`frontend/src/types/api.ts` — в `ResourceSummaryOut` после `flow_by_subgroup: SubgroupFlowItem[];`:

```ts
  /** Часы команды, забронированные планами других команд (уже вычтены из «На бэклог»). */
  booked_by_other_teams_by_role?: Record<string, number>;
```

- [ ] **Step 2: Падающие тесты помощников**

```ts
// frontend/src/utils/externalBookings.test.ts
import { describe, it, expect } from 'vitest';
import { externalBookingLabel, groupExternalBookings } from './externalBookings';
import type { ExternalBookingOut } from '../api/resourcePlanning';

const b = (over: Partial<ExternalBookingOut>): ExternalBookingOut => ({
  assignment_id: 'a1',
  employee_id: 'e1',
  employee_name: 'Пряничников',
  team: 'Команда 1С',
  issue_key: 'OS-91393',
  title: 'Задача',
  phase: 'dev',
  start: '2026-01-05',
  end: '2026-01-06',
  daily_hours: {},
  provisional: false,
  ...over,
});

describe('externalBookingLabel', () => {
  it('ключ · фаза · фамилия', () => {
    expect(externalBookingLabel(b({}))).toBe('OS-91393 · Разработка · Пряничников');
  });
  it('без ключа — название задачи', () => {
    expect(externalBookingLabel(b({ issue_key: null, phase: 'analyst' }))).toBe(
      'Задача · Анализ · Пряничников',
    );
  });
});

describe('groupExternalBookings', () => {
  it('по сотруднику, внутри — по дате начала, сотрудники по алфавиту', () => {
    const groups = groupExternalBookings([
      b({ assignment_id: 'x2', start: '2026-02-01' }),
      b({ assignment_id: 'y1', employee_id: 'e2', employee_name: 'Андреев' }),
      b({ assignment_id: 'x1', start: '2026-01-10' }),
    ]);
    expect(groups.map(g => g.employee_id)).toEqual(['e2', 'e1']);
    expect(groups[1].rows.map(r => r.assignment_id)).toEqual(['x1', 'x2']);
  });
});
```

```ts
// frontend/src/utils/heatmapFill.test.ts
import { describe, it, expect } from 'vitest';
import { EXT_LOAD_COLOR, FREE_FILL, splitLoadFill } from './heatmapFill';

describe('splitLoadFill', () => {
  it('без других команд — прежняя заливка', () => {
    expect(splitLoadFill('X', 50, 0)).toBe('X');
  });
  it('снизу другие команды, выше этот план, остаток свободен', () => {
    expect(splitLoadFill('X', 30, 50)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 80%, ${FREE_FILL} 80% 100%)`,
    );
  });
  it('перегруз — шкала по сумме, свободного нет', () => {
    expect(splitLoadFill('X', 100, 100)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
});
```

```ts
// frontend/src/utils/rpCandidates.test.ts
import { describe, it, expect } from 'vitest';
import { candidateLabel, candidateOptions } from './rpCandidates';
import type { AssignmentCandidate } from '../api/resourcePlanning';

const c = (over: Partial<AssignmentCandidate>): AssignmentCandidate => ({
  employee_id: 'e1',
  display_name: 'Пряничников',
  role: 'developer',
  team: 'Команда 1С',
  load_pct: 42.4,
  ...over,
});

describe('candidateLabel', () => {
  it('чужая команда видна в подписи', () => {
    expect(candidateLabel(c({}), 'other')).toBe('Пряничников · Команда 1С · 42%');
  });
  it('своя команда — без названия команды, с границами участия', () => {
    expect(candidateLabel(c({ member_to: '2026-08-10' }), 'team')).toBe(
      'Пряничников · 42% (в команде по 10.08)',
    );
  });
});

describe('candidateOptions', () => {
  it('группы AntD Select', () => {
    const opts = candidateOptions([
      { key: 'jira', label: 'Из Jira', employees: [c({})] },
    ]);
    expect(opts).toEqual([
      {
        label: 'Из Jira',
        title: 'Из Jira',
        options: [{ value: 'e1', label: 'Пряничников · Команда 1С · 42%' }],
      },
    ]);
  });
});
```

- [ ] **Step 3: Запустить — должны упасть**

Run: `cd frontend && npx vitest run src/utils/externalBookings.test.ts src/utils/heatmapFill.test.ts src/utils/rpCandidates.test.ts`
Expected: FAIL — модули не найдены

- [ ] **Step 4: Реализация**

```ts
// frontend/src/utils/externalBookings.ts
import type { ExternalBookingOut } from '../api/resourcePlanning';
import { PHASE_LABELS } from './gantt';

/** «OS-91393 · Разработка · Пряничников». */
export function externalBookingLabel(b: ExternalBookingOut): string {
  return [b.issue_key ?? b.title, PHASE_LABELS[b.phase] ?? b.phase, b.employee_name ?? '']
    .filter(Boolean)
    .join(' · ');
}

export interface ExternalBookingGroup {
  employee_id: string;
  employee_name: string;
  rows: ExternalBookingOut[];
}

/** Брони по сотрудникам (по алфавиту), внутри — по дате начала. */
export function groupExternalBookings(bookings: ExternalBookingOut[]): ExternalBookingGroup[] {
  const map = new Map<string, ExternalBookingGroup>();
  for (const b of bookings) {
    let g = map.get(b.employee_id);
    if (!g) {
      g = { employee_id: b.employee_id, employee_name: b.employee_name ?? '', rows: [] };
      map.set(b.employee_id, g);
    }
    g.rows.push(b);
  }
  const out = [...map.values()];
  for (const g of out) g.rows.sort((x, y) => x.start.localeCompare(y.start));
  out.sort((x, y) => x.employee_name.localeCompare(y.employee_name, 'ru'));
  return out;
}
```

```ts
// frontend/src/utils/heatmapFill.ts
/** Цвет часов, занятых планами других команд. */
export const EXT_LOAD_COLOR = 'hsl(265 55% 62%)';
/** Свободная часть дня (как заливка свободного рабочего дня). */
export const FREE_FILL = 'rgba(255,255,255,0.06)';

/**
 * Заливка клетки дня: снизу — доля других команд, над ней — этот план
 * (цветом общей загрузки, чтобы перегруз краснел), сверху — свободно.
 * Шкала — 100% или сумма, если перегруз.
 */
export function splitLoadFill(ownBg: string, pct: number, extPct: number): string {
  if (extPct <= 0) return ownBg;
  const scale = Math.max(pct + extPct, 100);
  const e = Math.round((extPct / scale) * 100);
  const o = Math.round(((pct + extPct) / scale) * 100);
  return `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 ${e}%, ${ownBg} ${e}% ${o}%, ${FREE_FILL} ${o}% 100%)`;
}
```

```ts
// frontend/src/utils/rpCandidates.ts
import type { AssignmentCandidate, AssignmentCandidateGroup } from '../api/resourcePlanning';

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/** «Имя · Команда · 42%»; у своей команды — без команды, с границами участия. */
export function candidateLabel(
  e: AssignmentCandidate,
  groupKey: AssignmentCandidateGroup['key'],
): string {
  const parts = [e.display_name];
  if (groupKey !== 'team' && e.team) parts.push(e.team);
  parts.push(`${Math.round(e.load_pct)}%`);
  let label = parts.join(' · ');
  if (groupKey === 'team') {
    if (e.member_from && e.member_to) label += ` (в команде ${ddmm(e.member_from)}–${ddmm(e.member_to)})`;
    else if (e.member_to) label += ` (в команде по ${ddmm(e.member_to)})`;
    else if (e.member_from) label += ` (в команде с ${ddmm(e.member_from)})`;
  }
  return label;
}

/** Группы опций для AntD Select. */
export function candidateOptions(groups: AssignmentCandidateGroup[]) {
  return groups.map((g) => ({
    label: g.label,
    title: g.label,
    options: g.employees.map((e) => ({ value: e.employee_id, label: candidateLabel(e, g.key) })),
  }));
}
```

- [ ] **Step 5: Запустить — должны пройти**

Run: `cd frontend && npx vitest run src/utils/externalBookings.test.ts src/utils/heatmapFill.test.ts src/utils/rpCandidates.test.ts`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/types/api.ts frontend/src/utils/externalBookings.ts frontend/src/utils/externalBookings.test.ts frontend/src/utils/heatmapFill.ts frontend/src/utils/heatmapFill.test.ts frontend/src/utils/rpCandidates.ts frontend/src/utils/rpCandidates.test.ts
git commit -F - <<'EOF'
feat(rp-ui): типы и помощники для привлечённых сотрудников

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 12: Фронт — блок «Привлечённые» на диаграмме

**Files:**
- Create: `frontend/src/components/resource-planning/ExternalBookingsRows.tsx`
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`, `frontend/src/pages/ResourcePlanningPage.tsx`

- [ ] **Step 1: Компонент**

```tsx
// frontend/src/components/resource-planning/ExternalBookingsRows.tsx
import type { ExternalBookingOut } from '../../api/resourcePlanning';
import type { GanttTimeline, WorkdayTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth } from '../../utils/gantt';
import { externalBookingLabel, groupExternalBookings } from '../../utils/externalBookings';

const ROW_H = 26;
// Серая штриховка: чужая работа, только просмотр.
const HATCH =
  'repeating-linear-gradient(45deg, rgba(160,170,190,0.55) 0 4px, rgba(160,170,190,0.18) 4px 8px)';

interface Props {
  bookings: ExternalBookingOut[];
  timeline: GanttTimeline | WorkdayTimeline;
  leftColWidth: number;
  trackWidthPx: number;
}

/**
 * Блок «Привлечённые»: фазы привлечённых сотрудников в опорных планах других
 * команд. Только просмотр — свободные окна видны как незанятые дни.
 */
export default function ExternalBookingsRows({ bookings, timeline, leftColWidth, trackWidthPx }: Props) {
  const groups = groupExternalBookings(bookings);
  if (groups.length === 0) return null;
  return (
    <div style={{ position: 'relative', zIndex: 2, borderBottom: '1px solid #1e3a5f' }}>
      <div
        style={{
          position: 'sticky',
          left: 0,
          width: leftColWidth,
          padding: '6px 12px',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.06em',
          color: '#7a9ab8',
        }}
      >
        ПРИВЛЕЧЁННЫЕ · ЗАНЯТОСТЬ В ДРУГИХ КОМАНДАХ
      </div>
      {groups.flatMap((g) =>
        g.rows.map((b) => {
          const label = externalBookingLabel(b);
          const meta = `${b.team}${b.provisional ? ' · предварительно' : ''}`;
          return (
            <div key={b.assignment_id} style={{ display: 'flex', alignItems: 'center', height: ROW_H }}>
              <div
                title={`${label} — ${meta}`}
                style={{
                  width: leftColWidth,
                  flexShrink: 0,
                  position: 'sticky',
                  left: 0,
                  zIndex: 3,
                  background: '#0a1628',
                  paddingLeft: 12,
                  paddingRight: 8,
                  fontSize: 12,
                  color: '#9ab3cc',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {label}
                <span style={{ marginLeft: 8, fontSize: 10, color: '#5a7a9a' }}>{meta}</span>
              </div>
              <div style={{ position: 'relative', width: trackWidthPx, height: ROW_H }}>
                <div
                  title={`${label} — ${meta}, только просмотр`}
                  style={{
                    position: 'absolute',
                    left: `${dateToLeft(b.start, timeline)}%`,
                    width: `${datesToWidth(b.start, b.end, timeline)}%`,
                    top: 6,
                    height: ROW_H - 12,
                    borderRadius: 3,
                    background: HATCH,
                    border: '1px solid rgba(160,170,190,0.5)',
                  }}
                />
              </div>
            </div>
          );
        }),
      )}
    </div>
  );
}
```

- [ ] **Step 2: `GanttChart.tsx`** — импорты: в строку `import type { AssignmentOut, DependencyOut, ScheduledBlock } from '../../api/resourcePlanning';` добавить `ExternalBookingOut`; после `import DependencyArrows from './DependencyArrows';` добавить `import ExternalBookingsRows from './ExternalBookingsRows';`.

В `interface Props` после `onToggleSection?: ...;` добавить:

```ts
  /** Брони привлечённых в опорных планах других команд — блок «Привлечённые». */
  externalBookings?: ExternalBookingOut[];
```

В деструктуризации параметров после `onEmployeeRowClick,` добавить `externalBookings = [],`.

Перед `<GanttRows` вставить:

```tsx
          <ExternalBookingsRows
            bookings={externalBookings}
            timeline={timeline}
            leftColWidth={LEFT_COL}
            trackWidthPx={trackWidthPx}
          />
```

- [ ] **Step 3: `ResourcePlanningPage.tsx`** — в `<GanttChart` после `dependencies={gantt.dependencies ?? []}` добавить:

```tsx
          externalBookings={gantt.external_bookings ?? []}
```

- [ ] **Step 4: Сборка и линтер**

Run: `cd frontend && npm run build && npm run lint`
Expected: без ошибок (у линтера фронта могут быть старые красные предупреждения — новых в изменённых файлах быть не должно; сравнить с `git stash`-состоянием при сомнениях)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/resource-planning/ExternalBookingsRows.tsx frontend/src/components/resource-planning/GanttChart.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -F - <<'EOF'
feat(rp-ui): блок «Привлечённые» с занятостью в других командах

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 13: Фронт — подвал двумя цветами и строки привлечённых

**Files:**
- Modify: `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`

Часть 1.6 уже правила подписи под фамилией и подсказку дня «вне команды» в этом файле: если фрагменты ниже не совпадают дословно — вносить те же изменения поверх её кода, не откатывая её подписи.

- [ ] **Step 1: Импорт** — после `import type { EmployeeLoadOut } from '../../api/resourcePlanning';` добавить:

```ts
import { EXT_LOAD_COLOR, splitLoadFill } from '../../utils/heatmapFill';
```

- [ ] **Step 2: Пустая строка учитывает чужую занятость** —

```ts
        return !d || d.off || d.pct <= 0;
```

→

```ts
        return !d || d.off || (d.pct <= 0 && !((d.ext_pct ?? 0) > 0));
```

- [ ] **Step 3: Секции** — фрагмент

```ts
  const grouped = Object.keys(subgroupByEmployee ?? {}).length > 0;
  const groupOf = (employeeId: string) => subgroupByEmployee?.[employeeId] ?? '';
```

заменить на

```ts
  // Привлечённые из других команд — отдельная секция внизу.
  const BORROWED = 'Привлечённые';
  const borrowedFrom = useMemo(
    () => new Map(rows.filter((r) => r.is_borrowed).map((r) => [r.employee_id, r.borrowed_from ?? ''])),
    [rows],
  );
  const hasSubgroups = Object.keys(subgroupByEmployee ?? {}).length > 0;
  const grouped = hasSubgroups || borrowedFrom.size > 0;
  const groupOf = (employeeId: string) =>
    borrowedFrom.has(employeeId) ? BORROWED : (subgroupByEmployee?.[employeeId] ?? '');
  const sectionTitle = (group: string) =>
    group || (hasSubgroups ? 'Без группы' : 'Команда');
```

В сортировке `orderedRows` строки вычисления ранга:

```ts
      const ra = ga ? (rank.get(ga) ?? subgroupOrder.length) : subgroupOrder.length + 1;
      const rb = gb ? (rank.get(gb) ?? subgroupOrder.length) : subgroupOrder.length + 1;
```

заменить на

```ts
      const rankOf = (g: string) =>
        g === BORROWED ? subgroupOrder.length + 2
          : g ? (rank.get(g) ?? subgroupOrder.length) : subgroupOrder.length + 1;
      const ra = rankOf(ga);
      const rb = rankOf(gb);
```

и зависимости этого `useMemo` дополнить `borrowedFrom`:

```ts
  }, [data, grouped, subgroupByEmployee, subgroupOrder, borrowedFrom]);
```

Заголовок секции: `{(group || 'Без группы').toUpperCase()}` → `{sectionTitle(group).toUpperCase()}`.

- [ ] **Step 4: Подпись привлечённого** — после блока `{row.employee_role && (...)}` в левой колонке добавить:

```tsx
                  {row.is_borrowed && (
                    <span style={{ fontSize: 10, color: '#b39ddb', flexShrink: 0 }}>
                      {row.borrowed_from ? `из ${row.borrowed_from}` : 'привлечён'}
                    </span>
                  )}
```

- [ ] **Step 5: Клетка дня** — в рендере клетки:

```ts
                        const pct = d?.pct ?? 0;
```

→

```ts
                        const pct = d?.pct ?? 0;
                        const ext = d?.ext_pct ?? 0;
```

ветку

```ts
                        else {
                          const c = loadColor(pct);
                          bg = c.bg;
                          border = c.border;
                        }
```

→

```ts
                        else {
                          const c = loadColor(pct + ext);
                          bg = splitLoadFill(c.bg, pct, ext);
                          border = ext > 0 ? undefined : c.border;
                        }
```

и вызов подсказки `onMouseEnter={(e) => showTip(e, cell.date, off, pct)}` → `onMouseEnter={(e) => showTip(e, cell.date, off, pct, ext)}`.

- [ ] **Step 6: Подсказка** — сигнатуру `showTip` дополнить параметром `ext = 0`:

```ts
  const showTip = (e: React.MouseEvent, date: string, off: Off, pct: number, ext = 0) => {
```

ветку рабочего дня

```ts
    else body = pct > 0 ? `${Math.round(pct)}%` : 'нет загрузки';
```

→

```ts
    else if (ext > 0) body = `этот план ${Math.round(pct)}% · другие команды ${Math.round(ext)}%`;
    else body = pct > 0 ? `${Math.round(pct)}%` : 'нет загрузки';
```

- [ ] **Step 7: Легенда** — в массив легенды после `{ label: 'свыше 110%', ... }` добавить:

```ts
          { label: 'в планах других команд', fill: EXT_LOAD_COLOR },
```

- [ ] **Step 8: Сборка и линтер**

Run: `cd frontend && npm run build && npm run lint`
Expected: без новых ошибок

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx
git commit -F - <<'EOF'
feat(rp-ui): подвал показывает занятость в других командах и привлечённых

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 14: Фронт — выбор исполнителя из всех сотрудников

**Files:**
- Modify: `frontend/src/hooks/useResourcePlanning.ts`, `frontend/src/components/resource-planning/AssignmentSidebar.tsx`

- [ ] **Step 1: Хук** — в импорт из `'../api/resourcePlanning'` добавить `getAssignmentCandidates, type AssignmentCandidateGroup,`; после `useExplainAssignment` добавить:

```ts
export function useAssignmentCandidates(
  planId: string | null,
  assignmentId: string | null,
  enabled: boolean,
) {
  return useQuery<AssignmentCandidateGroup[]>({
    queryKey: ['assignment-candidates', planId, assignmentId],
    queryFn: () => getAssignmentCandidates(planId!, assignmentId!),
    enabled: !!planId && !!assignmentId && enabled,
    staleTime: 30_000,
    retry: false,
  });
}
```

- [ ] **Step 2: Панель** — `AssignmentSidebar.tsx`:

Импорт `import { useExplainAssignment } from '../../hooks/useResourcePlanning';` → `import { useAssignmentCandidates, useExplainAssignment } from '../../hooks/useResourcePlanning';`; добавить `import { candidateOptions } from '../../utils/rpCandidates';`.

После `const { prefs, patch: patchPrefs } = useRpPreferences();` добавить (до раннего `return` — правило хуков):

```ts
  // Кандидаты — все активные сотрудники тремя группами с загрузкой за квартал.
  const candidatesQuery = useAssignmentCandidates(
    planId || null,
    assignment?.id ?? null,
    open && !!assignment && assignment.phase !== 'qa',
  );
```

В `<Select` выбора сотрудника свойство `options={employees.map((e) => ({ value: e.id, label: e.display_name + membershipSuffix(e), }))}` заменить на:

```tsx
              options={
                candidatesQuery.data?.length
                  ? candidateOptions(candidatesQuery.data)
                  : employees.map((e) => ({
                      value: e.id,
                      label: e.display_name + membershipSuffix(e),
                    }))
              }
```

и `loading={saving}` → `loading={saving || candidatesQuery.isFetching}`.

В `onChanged`-цепочке после смены сотрудника список кандидатов обновится сам через 30 с; чтобы загрузка в подписях была свежей сразу, в `handleEmployeeChange` и `confirmEmployeeChange` после `onChanged?.();` вызвать `candidatesQuery.refetch();`.

- [ ] **Step 3: Сборка и линтер**

Run: `cd frontend && npm run build && npm run lint`
Expected: без новых ошибок

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useResourcePlanning.ts frontend/src/components/resource-planning/AssignmentSidebar.tsx
git commit -F - <<'EOF'
feat(rp-ui): исполнитель фазы — из Jira, своей или другой команды

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 15: Фронт — живой конфликт в панели и подпись в сценарии

**Files:**
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx`, `frontend/src/components/planning/ScenarioResourceSummary.tsx`

- [ ] **Step 1: Панель конфликтов** — в `TYPE_LABELS` после `OUT_OF_TEAM: 'Вне команды',` добавить:

```ts
  CROSS_TEAM_OVERLAP: 'Пересечение с другой командой',
```

В `ConflictAlert` блок `<Dropdown ...>...</Dropdown>` обернуть условием, чтобы у живого конфликта не было смены статуса:

```tsx
              {!c.is_live && (
                <Dropdown
                  menu={{
                    items: (['acknowledged', 'muted', 'resolved', 'open'] as const)
                      .filter(s => s !== c.status)
                      .map(s => ({
                        key: s,
                        label: STATUS_LABEL[s],
                        onClick: () => onStatusChange(c.id, s),
                      })),
                  }}
                  trigger={['click']}
                >
                  <a><MoreOutlined /></a>
                </Dropdown>
              )}
```

- [ ] **Step 2: Подпись в сценарии** — `ScenarioResourceSummary.tsx`, перед строкой `      {summary.subgroups.length > 0 && (` вставить:

```tsx
      {(() => {
        const booked = Object.values(summary.booked_by_other_teams_by_role ?? {}).reduce(
          (s, v) => s + v,
          0,
        );
        return booked > 0 ? (
          <div
            style={{
              borderTop: `1px solid ${DARK_THEME.border}`,
              padding: '8px 14px',
              fontSize: 12,
              color: DARK_THEME.textMuted,
            }}
          >
            Из часов «На бэклог» вычтено {Math.round(booked).toLocaleString('ru')} ч — сотрудники
            команды заняты в планах других команд этого квартала.
          </div>
        ) : null;
      })()}
```

- [ ] **Step 3: Сборка и линтер**

Run: `cd frontend && npm run build && npm run lint`
Expected: без новых ошибок

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/ConflictPanel.tsx frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -F - <<'EOF'
feat(rp-ui): пересечение с другой командой в конфликтах, подпись в сценарии

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 16: Справка и документация модулей

**Files:**
- Modify: `docs/help/resource-planning.md`, `app/services/CLAUDE.md`

- [ ] **Step 1: Справка раздела** — `docs/help/resource-planning.md`:

Абзац в 3.5, начинающийся «- **Из боковой панели**», заменить на:

```markdown
- **Из боковой панели** — поле «исполнитель» с поиском по всем активным сотрудникам компании. Список разбит на три группы: «Из Jira» (для разработки — человек из поля «Разработчик» задачи, для остальных фаз — исполнитель инициативы), «Моя команда» и «Другие команды». Рядом с каждым — его загрузка за квартал по планам всех команд, в процентах.
```

Последний абзац 3.5 («Аналитик по умолчанию подтягивается…») заменить на:

```markdown
Аналитик по умолчанию подтягивается из поля «исполнитель» инициативы в Jira, если этот человек в вашей команде; аналитика из другой команды можно поставить только вручную. Разработчик подставляется из поля «Разработчик» задачи в Jira — из любой команды; если у самой задачи поле пустое, берётся тот, кто чаще всего стоит «Разработчиком» в её подзадачах. Если и там пусто — разработчика подбирает планировщик среди своей команды. Тестирование — без сотрудника.
```

В список «Типы проблем» раздела 3.7 после пункта «Нарушен порядок предшественников…» добавить:

```markdown
  - Пересечение с другой командой — привлечённый сотрудник в эти дни уже занят в плане своей (или другой) команды, и вместе с вашей работой выходит больше его рабочего дня. Показывается только в плане команды, которая его привлекла; статус у такого конфликта не меняется — он исчезает, когда пересечение устранено;
```

После раздела 3.9 добавить новый подраздел:

```markdown
### 3.10. Привлечённые сотрудники из других команд

Сотрудник может работать в плане чужой команды — например, разработчик продуктовой команды на задаче технической команды. Такой человек называется «привлечённым».

- **Как он попадает в план:** вручную через поле «исполнитель» или сам — если он стоит «Разработчиком» задачи в Jira.
- **Когда он свободен:** для каждой команды на квартал берётся её опорный план — основной план утверждённого сценария, а если утверждённого нет, план самого свежего черновика (он помечается «предварительно»). Часы, которые стоят на человеке в опорных планах других команд, при распределении не занимаются — в обе стороны: техкоманда обходит часы домашней команды, домашняя — часы техкоманды. Вручную поставить работу поверх можно.
- **Блок «Привлечённые»** над задачами показывает, чем привлечённый занят в других командах: задача, фаза, команда. Только просмотр, серая штриховка; свободные окна — незанятые дни.
- **Подвал «Загрузка по дням»:** нижняя часть клетки дня фиолетовая — часы в планах других команд, выше — этот план. Привлечённые идут отдельной секцией внизу с подписью «из <команда>». Дни, когда привлечённый не в вашей команде, для него обычные — «вне команды» не ставится.
- **Сценарий:** в блоке ресурса сценария часы «На бэклог» уменьшаются на часы, забронированные на сотрудников команды в планах других команд; под таблицей есть подпись, сколько вычтено.
```

В разделе 6 пункт «**Глобальный фильтр команды** влияет на список сотрудников…» заменить на:

```markdown
- **Глобальный фильтр команды** выбирает команду плана. Исполнителя можно взять из любой команды — он станет «привлечённым» (см. 3.10). Проверка ёмкости в сценарии по ролям, которых нет в самой команде, пока показывает нехватку: привлечённые учитываются только в ресурсном плане.
```

- [ ] **Step 2: Карта сервисов** — `app/services/CLAUDE.md`, после раздела `## team_membership` добавить:

```markdown
## cross_team_occupancy ([cross_team_occupancy.py](cross_team_occupancy.py))

Занятость сотрудников в планах других команд. Опорный план команды на квартал (`reference_plans`): утверждённый сценарий → `is_baseline` → «Готово» → свежесть; нет утверждённого — свежайший черновик, `provisional=True`; форки не участвуют. `external_bookings(team=...)` — брони в опорных планах всех команд, кроме `team`, два запроса на любой объём. `subtract_occupancy` вычитается из доступности в `compute_schedule` (раскладка), выравниватель меряет перегрузку по «сырой» ёмкости. `overlap_days` — живой конфликт `CROSS_TEAM_OVERLAP` в `get_gantt` (не хранится). «Привлечённый» — не состоял в команде плана ни дня квартала (`borrowed_ids`). «Разработчик» из Jira — [jira_developer.py](jira_developer.py).
```

- [ ] **Step 3: Commit**

```bash
git add docs/help/resource-planning.md app/services/CLAUDE.md
git commit -F - <<'EOF'
docs(help): привлечённые сотрудники в ресурсном плане

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 17: Заметки «Что нового»

**Files:**
- Modify: `release_notes/drafts.json` (через CLI)

Порядок: Новое → Улучшение → Исправление. Исправлений в этой части нет.

- [ ] **Step 1: Добавить черновики**

```bash
py -3.10 scripts/release_note.py add --type new --section resources \
  --title "Сотрудники из других команд в ресурсном плане" \
  --description "В план можно взять человека из другой команды — например, разработчика продуктовой команды на задачу технической. Над задачами появился блок «Привлечённые»: чем этот человек занят в других командах. Распределение обходит часы, уже забронированные на него в планах других команд, — и в обратную сторону тоже. Если вручную поставить работу поверх, фаза подсветится конфликтом «Пересечение с другой командой»."

py -3.10 scripts/release_note.py add --type improvement --section resources \
  --title "Разработчик подставляется из Jira" \
  --description "Разработка задачи сразу ставится на человека из поля «Разработчик» в Jira, даже если он из другой команды. Если у самой задачи поле пустое, берётся тот, кто чаще всего стоит «Разработчиком» в её подзадачах. Ручной выбор по-прежнему главнее."

py -3.10 scripts/release_note.py add --type improvement --section resources \
  --title "Выбор исполнителя из всех сотрудников" \
  --description "В поле «исполнитель» теперь все активные сотрудники тремя группами — «Из Jira», «Моя команда», «Другие команды». Рядом с каждым видна его загрузка за квартал по планам всех команд."

py -3.10 scripts/release_note.py add --type improvement --section resources \
  --title "Загрузка по дням показывает другие команды" \
  --description "В подвале «Загрузка по дням» нижняя часть клетки дня окрашена отдельным цветом — это часы человека в планах других команд. Привлечённые сотрудники идут отдельной секцией с подписью, из какой они команды."

py -3.10 scripts/release_note.py add --type improvement --section scenarios \
  --title "Ёмкость сценария учитывает другие команды" \
  --description "Часы «На бэклог» уменьшаются на время, которое сотрудники команды уже отдали планам других команд этого квартала. Под таблицей ресурса видно, сколько часов вычтено."
```

- [ ] **Step 2: Проверить файл**

Run: `py -3.10 -c "import json;d=json.load(open('release_notes/drafts.json',encoding='utf-8'));print([n['type'] for n in d['notes']][-5:])"`
Expected: `['new', 'improvement', 'improvement', 'improvement', 'improvement']` (в конце списка; если в черновиках уже есть записи Частей 1–3 — порядок категорий внутри всего файла выровнять вручную: Новое → Улучшение → Исправление)

- [ ] **Step 3: Commit**

```bash
git add release_notes/drafts.json
git commit -F - <<'EOF'
docs(release-notes): привлечение сотрудников из других команд

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 18: Итоговая проверка

- [ ] **Step 1: Весь бэкенд**

Run: `py -3.10 -m pytest tests/ --ignore=tests/api/test_llm.py -q`
Expected: все зелёные. Особое внимание к `tests/test_resource_planning_*`, `tests/services/test_rp_*`, `tests/test_membership_periods_*`, `tests/test_resource_base_service.py` — подстановка «Разработчика» из Jira меняет прежний жадный выбор только у задач с заполненным полем; в старых тестах задач Jira с полем нет.

- [ ] **Step 2: Postgres (правило перед релизом)**

Run: `.\scripts\run_tests_postgres.ps1 -k "cross_team or borrowed or jira_developer or resource_base or rp_cross"`
Expected: все зелёные

- [ ] **Step 3: Линтеры бэкенда**

Run: `ruff check app/ tests/` и `mypy app/`
Expected: без новых ошибок

- [ ] **Step 4: Фронт**

Run: `cd frontend && npx vitest run && npm run build && npm run lint`
Expected: тесты зелёные, сборка без ошибок, новых замечаний линтера нет

- [ ] **Step 5: Граф**

Run: `graphify update .`

- [ ] **Step 6: Ручная проверка в приложении** (перезапустить бэкенд — `uvicorn --reload` на Windows виснет): открыть план техкоманды, у задачи с «Разработчиком» из другой команды нажать «Распределить» — разработка на нём, блок «Привлечённые» заполнен, в подвале его строка в секции «Привлечённые» с подписью «из <команда>»; перетащить его фазу на день, занятый в домашней команде, — фаза красная, в панели «Пересечение с другой командой» без меню статусов; открыть план домашней команды — у него нижняя часть клеток в эти дни фиолетовая, конфликта нет.
