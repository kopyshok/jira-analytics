# Раздел «Проекты»: план/факт, задачи, таймлайн — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в раздел «Проекты» вкладку «План и сроки» (план/факт по видам работ, таймлайн фаз, список задач) и сводный экран портфеля в правой панели, когда проект не выбран.

**Architecture:** Общие расчётные хелперы рабочих столов выносятся из `work_desk_widgets.py` в новый `plan_common.py`; новый `project_plan_service.py` строит на них проектный (а не персональный) срез. Два новых GET-эндпоинта. На фронте — три переиспользуемых блока (кольца, таймлайн, таблица задач) и два экрана, которые их собирают.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, pytest; React 19 + TypeScript + AntD 6 + TanStack Query.

**Спека:** [docs/superpowers/specs/2026-07-27-projects-plan-timeline-design.md](../specs/2026-07-27-projects-plan-timeline-design.md)

---

## File Structure

**Backend — создаём:**

| Файл | Ответственность |
|---|---|
| `app/services/plan_common.py` | Общие константы и расчёты плана: роли, метки фаз, границы квартала, поддеревья, состав команды, выбор свежих планов, разбивка план/факт по видам работ |
| `app/services/project_plan_service.py` | Проектный срез: план/факт одного проекта, задачи, таймлайн; агрегация портфеля и сигналы |
| `tests/services/test_plan_common.py` | Тесты общих хелперов |
| `tests/services/test_project_plan_service.py` | Тесты проектного сервиса |

**Backend — правим:**

| Файл | Что меняем |
|---|---|
| `app/services/work_desk_widgets.py` | Убираем вынесенные хелперы, импортируем их из `plan_common` под старыми именами |
| `app/services/projects_service.py` | Квартальный фильтр переезжает со сценария на поле «Цели» |
| `app/api/endpoints/projects.py` | Два новых эндпоинта + схемы |
| `tests/services/test_projects_service.py` | Обновляем тесты квартального фильтра |

**Frontend — создаём:**

| Файл | Ответственность |
|---|---|
| `frontend/src/components/projects/plan/WorkTypeRings.tsx` | Полоса «факт/план + кольца + Внешние» |
| `frontend/src/components/projects/plan/PhaseTimeline.tsx` | Таймлайн: месячная шкала, полосы, «сегодня», затенение квартала |
| `frontend/src/components/projects/plan/ProjectTasksTable.tsx` | Таблица задач проекта |
| `frontend/src/components/projects/plan/PortfolioSignals.tsx` | Полоса чипов-сигналов |
| `frontend/src/components/projects/ProjectPlanView.tsx` | Вкладка «План и сроки» |
| `frontend/src/components/projects/PortfolioView.tsx` | Сводный экран портфеля |

**Frontend — правим:**

| Файл | Что меняем |
|---|---|
| `frontend/src/types/projects.ts` | Типы ответов новых эндпоинтов |
| `frontend/src/api/projects.ts` | Два новых метода клиента |
| `frontend/src/hooks/useProjects.ts` | `useProjectPlan`, `usePortfolio` |
| `frontend/src/pages/ProjectsPage.tsx` | Подъём фильтров списка, `PortfolioView` вместо заглушки |
| `frontend/src/components/projects/ProjectsList.tsx` | Фильтры приходят пропсами, кнопка «Сводка», снятие выбора |
| `frontend/src/components/projects/ProjectDetailPanel.tsx` | Третий режим `plan` |
| `frontend/src/components/projects/ProjectHeader.tsx` | Третья кнопка переключателя |

---

## Task 1: Вынести общие хелперы плана в `plan_common.py`

Чисто механический вынос. Поведение столов не меняется — это проверяется существующими тестами.

**Files:**
- Create: `app/services/plan_common.py`
- Modify: `app/services/work_desk_widgets.py`
- Test: `tests/services/test_plan_common.py`

- [ ] **Step 1: Создать `app/services/plan_common.py`**

Переносим код из `work_desk_widgets.py` без изменения логики. Два отличия от оригинала:
`role_breakdown` принимает **список** планов вместо одного и не принимает неиспользуемый `q_start`.

```python
"""Общие расчёты плана: используются и рабочими столами, и разделом «Проекты».

Столы дают персональный срез (доля одного сотрудника), «Проекты» — проектный
(все исполнители). Формулы плана/факта одни и те же, поэтому живут здесь.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

QUARTER_MONTHS: Dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

JIRA_BROWSE = "https://itgri.atlassian.net/browse/"

# Все фазы плана.
ROLES: tuple[str, ...] = ("analyst", "dev", "qa", "opo")

# Фазы, для которых рисуем плитку/кольцо. ОПЭ отдельно не показываем — его план
# раскидывается по Анализу и Разработке (см. role_breakdown).
DISPLAY_ROLES: tuple[str, ...] = ("analyst", "dev", "qa")

# Фаза назначения → поле плановой оценки на BacklogItem.
PHASE_ESTIMATE_FIELD: Dict[str, str] = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
}

# Фаза назначения → человекочитаемое название.
PHASE_LABEL: Dict[str, str] = {
    "analyst": "Анализ",
    "cons": "Консультация",
    "dev": "Разработка",
    "qa": "Тестирование",
    "opo": "ОПЭ",
}


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    months = QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    last_month = months[-1]
    end = date(year, last_month, _cal.monthrange(year, last_month)[1])
    return start, end


def jira_url(key: Optional[str]) -> Optional[str]:
    return f"{JIRA_BROWSE}{key}" if key else None


def find_recent_plan(db: Session, teams: List[str], year: int, quarter: int):
    """Самый свежий ResourcePlan команды за квартал, либо None."""
    from app.models import ResourcePlan

    if not teams:
        return None
    q_variants = [str(quarter), f"Q{quarter}", f"q{quarter}"]
    rows = (
        db.execute(
            select(ResourcePlan)
            .where(
                ResourcePlan.team.in_(teams),
                ResourcePlan.year == year,
                ResourcePlan.quarter.in_(q_variants),
            )
            .order_by(
                ResourcePlan.computed_at.desc().nullslast(),
                ResourcePlan.created_at.desc(),
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


def plan_ids_for_issues(db: Session, issue_ids: Sequence[str]) -> List[str]:
    """Планы, где есть назначения этих задач — по свежайшему на каждый квартал.

    Проект может идти два-три квартала, назначения лежат в разных ResourcePlan.
    Форки и baseline-копии одного квартала удвоили бы часы, поэтому на каждую
    тройку (команда, год, квартал) оставляем только самый свежий план.
    """
    from app.models import BacklogItem, ResourcePlan, ResourcePlanAssignment

    ids = [i for i in dict.fromkeys(issue_ids) if i]
    if not ids:
        return []
    raw_plan_ids = (
        db.execute(
            select(ResourcePlanAssignment.plan_id)
            .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
            .where(BacklogItem.issue_id.in_(ids))
            .distinct()
        )
        .scalars()
        .all()
    )
    if not raw_plan_ids:
        return []
    plans = (
        db.execute(select(ResourcePlan).where(ResourcePlan.id.in_(raw_plan_ids)))
        .scalars()
        .all()
    )
    best: Dict[tuple, object] = {}
    for p in plans:
        # Квартал в БД встречается как "3", "Q3", "q3" — нормализуем.
        q = (p.quarter or "").lower().lstrip("q")
        bucket = (p.team, p.year, q)
        cur = best.get(bucket)
        if cur is None or _plan_sort_key(p) > _plan_sort_key(cur):
            best[bucket] = p
    return [p.id for p in best.values()]


def _plan_sort_key(p) -> tuple:
    """Свежесть плана: сначала computed_at, затем created_at. None — самый старый."""
    return (
        p.computed_at or datetime.min,
        p.created_at or datetime.min,
    )


def subtree_ids(db: Session, root_ids: Sequence[str]) -> Dict[str, set]:
    """Для каждой задачи-корня — множество id её поддерева (корень + потомки).

    Списания часто висят на подзадачах, а не на задаче-инициативе. BFS по
    Issue.parent_id уровнями (несколько запросов, ограничено глубиной дерева).
    """
    from app.models import Issue

    roots = [r for r in dict.fromkeys(root_ids) if r]
    result: Dict[str, set] = {r: {r} for r in roots}
    if not roots:
        return result
    parent_root: Dict[str, str] = {r: r for r in roots}
    current = list(roots)
    while current:
        rows = (
            db.query(Issue.id, Issue.parent_id)
            .filter(Issue.parent_id.in_(current))
            .all()
        )
        nxt: List[str] = []
        for cid, pid in rows:
            root = parent_root.get(pid)
            if root is None or cid in result[root]:
                continue
            result[root].add(cid)
            parent_root[cid] = root
            nxt.append(cid)
        current = nxt
    return result


def team_member_ids(db: Session, teams: Sequence[str]) -> set[str]:
    """ID сотрудников указанных команд + QA (общий ресурс компании)."""
    from app.models import Employee
    from app.models.employee_team import EmployeeTeam

    ids: set[str] = set()
    if teams:
        rows = db.query(EmployeeTeam.employee_id).filter(EmployeeTeam.team.in_(list(teams))).all()
        ids = {r[0] for r in rows}
    qa_rows = db.query(Employee.id).filter(Employee.role == "qa").all()
    ids |= {r[0] for r in qa_rows}
    return ids


def assignment_norm(a) -> float:
    """Плановые часы фазы: hours_allocated, иначе оценка роли на BacklogItem."""
    allocated = a.hours_allocated
    if allocated is not None and allocated > 0:
        return float(allocated)
    item = a.backlog_item
    if item is not None:
        field = PHASE_ESTIMATE_FIELD.get(a.phase)
        if field is not None:
            est = getattr(item, field, None)
            if est is not None:
                return float(est)
    return 0.0


def role_breakdown(
    db: Session,
    plan_ids: Sequence[str],
    root_ids: Sequence[str],
    subtree: Dict[str, set],
    fact_until: date,
    team_ids: set[str],
) -> Dict[str, dict]:
    """План/факт по видам работ для каждой задачи-корня.

    План — плановые часы всех фаз проекта во всех переданных планах.
    Факт — накопительно по всему поддереву до ``fact_until``, разнесённый по
    роли автора ворклога; роль РП засчитывается в Анализ.

    Часы авторов вне команды и без плитки-роли идут в «прочее» (``info``) —
    они не входят в план/факт, показываются информационно.

    Возвращает {root_issue_id: {"plan": {role: ч}, "fact": {role: ч}, "info": ч}}.
    """
    from app.models import BacklogItem, Employee, ResourcePlanAssignment, Worklog

    ids = [i for i in root_ids if i]
    out: Dict[str, dict] = {
        i: {"plan": {r: 0.0 for r in ROLES}, "fact": {r: 0.0 for r in ROLES}, "info": 0.0}
        for i in ids
    }
    if not ids:
        return out

    ratios: Dict[str, float] = {}
    if plan_ids:
        arows = (
            db.query(
                ResourcePlanAssignment,
                BacklogItem.issue_id,
                BacklogItem.opo_analyst_ratio,
            )
            .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
            .filter(
                ResourcePlanAssignment.plan_id.in_(list(plan_ids)),
                BacklogItem.issue_id.in_(ids),
            )
            .all()
        )
        for a, issue_id, opo_ratio in arows:
            if a.phase in ROLES and issue_id in out:
                out[issue_id]["plan"][a.phase] += assignment_norm(a)
                ratios[issue_id] = 0.5 if opo_ratio is None else float(opo_ratio)

    issue_to_root: Dict[str, str] = {}
    for root, members in subtree.items():
        for iid in members:
            issue_to_root[iid] = root
    all_ids = list(issue_to_root.keys())
    if all_ids:
        end_dt = datetime.combine(fact_until, time.max)
        rows = (
            db.query(
                Worklog.issue_id,
                Worklog.employee_id,
                Employee.role,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
            )
            .join(Employee, Employee.id == Worklog.employee_id)
            .filter(
                Worklog.issue_id.in_(all_ids),
                Worklog.started_at <= end_dt,
            )
            .group_by(Worklog.issue_id, Worklog.employee_id, Employee.role)
            .all()
        )
        for issue_id, emp_id, role, hours in rows:
            root = issue_to_root.get(issue_id)
            if root not in out:
                continue
            h = float(hours or 0.0)
            r = (role or "").lower()
            if r == "rp":  # РП засчитываем в Анализ
                r = "analyst"
            if emp_id in team_ids and r in ROLES:
                out[root]["fact"][r] += h
            else:
                out[root]["info"] += h

    # ОПЭ нельзя зафиксировать по факту отдельно — план ОПЭ распределяем на
    # Анализ/Разработку по коэффициенту деления, плитку ОПЭ убираем.
    for iid, bd in out.items():
        ratio = ratios.get(iid, 0.5)
        for kind in ("plan", "fact"):
            opo = bd[kind].pop("opo", 0.0)
            bd[kind]["analyst"] += opo * ratio
            bd[kind]["dev"] += opo * (1.0 - ratio)
    return out
```

- [ ] **Step 2: Убрать вынесенный код из `work_desk_widgets.py` и импортировать из `plan_common`**

Удалить из `work_desk_widgets.py` определения: `_QUARTER_MONTHS`, `_JIRA_BROWSE`,
`_PHASE_ESTIMATE_FIELD`, `_PHASE_LABEL`, `_quarter_bounds`, `_jira_url`, `_find_recent_plan`,
`_subtree_ids`, `_team_member_ids`, `_assignment_norm`, `_ROLES`, `_DISPLAY_ROLES`,
`_role_breakdown`.

Вместо них — импорт под старыми именами сразу после `from app.models.work_desk import WorkDesk`:

```python
from app.services.plan_common import (
    DISPLAY_ROLES as _DISPLAY_ROLES,
    JIRA_BROWSE as _JIRA_BROWSE,
    PHASE_ESTIMATE_FIELD as _PHASE_ESTIMATE_FIELD,
    PHASE_LABEL as _PHASE_LABEL,
    QUARTER_MONTHS as _QUARTER_MONTHS,
    ROLES as _ROLES,
    assignment_norm as _assignment_norm,
    find_recent_plan as _find_recent_plan,
    jira_url as _jira_url,
    quarter_bounds as _quarter_bounds,
    role_breakdown as _role_breakdown,
    subtree_ids as _subtree_ids,
    team_member_ids as _team_member_ids,
)
```

- [ ] **Step 3: Поправить единственный вызов `_role_breakdown` под новую сигнатуру**

В `_adapter_my_tasks` (около строки 525) было:

```python
    breakdown = _role_breakdown(db, plan.id, issue_ids, subtree, q_start, q_end, team_ids)
```

Стало (список планов, без `q_start`):

```python
    breakdown = _role_breakdown(db, [plan.id], issue_ids, subtree, q_end, team_ids)
```

- [ ] **Step 4: Написать тест на `plan_ids_for_issues` — новый код, которого не было**

Create `tests/services/test_plan_common.py`:

```python
"""plan_common: общие расчёты плана."""
import uuid
from datetime import date, datetime

from app.models.backlog_item import BacklogItem
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.services.plan_common import plan_ids_for_issues, quarter_bounds


def _uid() -> str:
    return str(uuid.uuid4())


def test_quarter_bounds_q3():
    assert quarter_bounds(2026, 3) == (date(2026, 7, 1), date(2026, 9, 30))


def test_plan_ids_for_issues_keeps_freshest_plan_per_quarter(db_session):
    db = db_session
    db.add(Project(id="p1", jira_project_id="p1", key="PRJ", name="Project"))
    db.add(Issue(id="i1", jira_issue_id="1", key="PRJ-1", summary="Epic",
                 issue_type="Epic", status="В работе", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Epic", issue_id="i1"))

    # Два плана одного квартала (форк) + один плана следующего квартала.
    stale_id, fresh_id, next_q_id = _uid(), _uid(), _uid()
    db.add(ResourcePlan(id=stale_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 1)))
    db.add(ResourcePlan(id=fresh_id, team="T", year=2026, quarter="3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlan(id=next_q_id, team="T", year=2026, quarter="Q4",
                        computed_at=datetime(2026, 10, 1)))
    for pid in (stale_id, fresh_id, next_q_id):
        db.add(ResourcePlanAssignment(id=_uid(), plan_id=pid, backlog_item_id=item_id,
                                      phase="analyst", hours_allocated=10.0))
    db.commit()

    got = set(plan_ids_for_issues(db, ["i1"]))
    assert got == {fresh_id, next_q_id}, "форк того же квартала должен отсеяться"


def test_plan_ids_for_issues_empty_input(db_session):
    assert plan_ids_for_issues(db_session, []) == []
```

- [ ] **Step 5: Прогнать тесты — новые и существующие тесты столов**

Run: `py -3.10 -m pytest tests/services/test_plan_common.py tests/ -k "desk or work_desk or plan_common" -v`
Expected: PASS. Тесты столов не должны измениться — вынос механический.

- [ ] **Step 6: Прогнать весь бэкенд**

Run: `py -3.10 -m pytest tests/ -q`
Expected: столько же passed, сколько до задачи (сверить с `git stash` прогоном, если есть сомнения). Допустимы только уже известные красные тесты.

- [ ] **Step 7: Коммит**

```bash
git add app/services/plan_common.py app/services/work_desk_widgets.py tests/services/test_plan_common.py
git commit -m "refactor(plan): вынести общие расчёты плана в plan_common"
```

---

## Task 2: ~~Квартальный фильтр проектов по полю «Цели»~~ — ОТМЕНЕНА

> **Задача выполнена и откачена.** Коммит `d773814`, откат `dd20228`.
>
> Уточнение PM: цели квартала — это состав **утверждённого сценария**, а не Jira-поле
> «Цели». Существующий фильтр через `PlanningScenario` + `ScenarioAllocation` уже правильный,
> менять его не нужно. См. §4 спеки.
>
> Побочный плюс отката: в квартальном режиме команда определяется по команде сценария, а не
> по авторам списаний — значит проект нового квартала без единого ворклога не пропадает из
> списка при фильтре команды. Ревью Task 2 отдельно поймало эту регрессию у отменённого
> варианта.
>
> **Шаги ниже оставлены как история. Не выполнять.**

**Files:**
- Modify: `app/services/projects_service.py`
- Test: `tests/services/test_projects_service.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/services/test_projects_service.py`:

```python
def test_list_projects_filters_by_goals_quarter(db_session):
    db = db_session
    _make_project(db, "pg", "PG")
    db.add(Issue(id="g1", jira_issue_id="900", key="PG-1", summary="В квартале",
                 issue_type="Epic", status="В работе", project_id="pg",
                 category="quarterly_tasks", include_in_analysis=True,
                 goals="3кв26"))
    db.add(Issue(id="g2", jira_issue_id="901", key="PG-2", summary="Другой квартал",
                 issue_type="Epic", status="В работе", project_id="pg",
                 category="quarterly_tasks", include_in_analysis=True,
                 goals="2кв26"))
    db.add(Issue(id="g3", jira_issue_id="902", key="PG-3", summary="Без цели",
                 issue_type="Epic", status="В работе", project_id="pg",
                 category="quarterly_tasks", include_in_analysis=True,
                 goals=None))
    db.commit()

    items = ProjectsService(db).list_projects(year=2026, quarter=3)
    assert {i.key for i in items} == {"PG-1"}


def test_list_projects_goals_accepts_multiple_values_and_case(db_session):
    db = db_session
    _make_project(db, "pg2", "PG2")
    db.add(Issue(id="g4", jira_issue_id="903", key="PG2-1", summary="Список целей",
                 issue_type="Epic", status="В работе", project_id="pg2",
                 category="quarterly_tasks", include_in_analysis=True,
                 goals="2кв26, 3КВ26"))
    db.commit()

    items = ProjectsService(db).list_projects(year=2026, quarter=3)
    assert {i.key for i in items} == {"PG2-1"}
```

- [ ] **Step 2: Прогнать — должны упасть**

Run: `py -3.10 -m pytest tests/services/test_projects_service.py -k goals -v`
Expected: FAIL — сейчас фильтр идёт через approved scenario, проектов не найдёт (вернёт `[]`).

- [ ] **Step 3: Заменить ветку квартального фильтра**

В `app/services/projects_service.py` добавить хелпер над классом `ProjectsService`:

```python
def goals_quarter_tokens(year: int, quarter: int) -> list[str]:
    """Варианты записи квартала в Jira-поле «Цели»: 3кв26 / 3КВ26 / 3Кв26.

    ponytail: три варианта регистра вместо нормализации в SQL — SQLite lower()
    не сворачивает кириллицу. Если появятся ещё формы записи — чинить здесь.
    """
    yy = year % 100
    return [f"{quarter}кв{yy:02d}", f"{quarter}КВ{yy:02d}", f"{quarter}Кв{yy:02d}"]
```

Импорт `or_` в шапку файла:

```python
from sqlalchemy import or_, select
```

(если `select` уже импортирован — просто добавить `or_` в тот же импорт).

Заменить блок `if year is not None and quarter is not None:` (строки ~147–186) целиком на:

```python
        if year is not None and quarter is not None:
            # Привязка проекта к кварталу — Jira-поле «Цели» (формат 3кв26).
            # Проекты с незаполненным полем в квартальную выборку не попадают.
            tokens = goals_quarter_tokens(year, quarter)
            stmt = (
                select(Issue)
                .where(
                    Issue.category.in_(PROJECT_CATEGORY_CODES),
                    Issue.parent_id.is_(None),
                    or_(*[Issue.goals.contains(t) for t in tokens]),
                )
            )
        else:
```

Ниже, в ветке `else`, оставить существующий запрос без изменений.

- [ ] **Step 4: Убрать ставший мёртвым код**

После замены `PlanningScenario`, `ScenarioAllocation`, `BacklogItem` могут остаться
неиспользованными в `projects_service.py`. Проверить и убрать только те импорты,
которые перестали использоваться из-за этой правки:

Run: `py -3.10 -m ruff check app/services/projects_service.py`
Expected: чисто. Если ruff укажет на неиспользуемый импорт — удалить его.

- [ ] **Step 5: Убрать worklog-based team filter из legacy-ветки**

Строки ~247–252 содержат условие `if team_filter and (year is None or quarter is None):`.
Теперь квартальная ветка тоже фильтрует по эпикам, а не по сценарию — team filter должен
работать одинаково в обеих ветках. Заменить условие на:

```python
            # Проект принадлежит команде, если по нему списывался кто-то из неё.
            if team_filter:
                has_team = any(r.team in team_filter for r in rows)
                if not has_team:
                    continue
```

- [ ] **Step 6: Прогнать тесты**

Run: `py -3.10 -m pytest tests/services/test_projects_service.py -v`
Expected: PASS. Тест `test_list_projects_filters_by_approved_scenario` теперь проверяет
устаревшее поведение — переписать его под «Цели» или удалить, если он полностью дублирует
`test_list_projects_filters_by_goals_quarter`. Решение: **удалить**, поведение заменено.

- [ ] **Step 7: Коммит**

```bash
git add app/services/projects_service.py tests/services/test_projects_service.py
git commit -m "feat(projects): квартальный фильтр по полю «Цели» вместо сценария"
```

---

## Task 3: `ProjectPlanService` — план/факт одного проекта

**Files:**
- Create: `app/services/project_plan_service.py`
- Test: `tests/services/test_project_plan_service.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/services/test_project_plan_service.py`:

```python
"""ProjectPlanService: план/факт проекта по видам работ."""
import uuid
from datetime import date, datetime

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.worklog import Worklog
from app.services.project_plan_service import ProjectPlanService


def _uid() -> str:
    return str(uuid.uuid4())


def _employee(db, name: str, role: str, team: str | None) -> str:
    eid = _uid()
    db.add(Employee(id=eid, jira_account_id=eid, display_name=name, role=role))
    if team:
        db.add(EmployeeTeam(id=_uid(), employee_id=eid, team=team, is_primary=True))
    return eid


def _worklog(db, employee_id: str, issue_id: str, hours: float, started: datetime) -> None:
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id=issue_id,
                   employee_id=employee_id, hours=hours, started_at=started))


def _seed_project(db) -> dict:
    """Эпик + подзадача + план на 2 квартала + свои и чужие списания."""
    db.add(Project(id="pp", jira_project_id="pp", key="PP", name="Project"))
    db.add(Issue(id="root", jira_issue_id="1", key="PP-1", summary="Проект",
                 issue_type="Epic", status="В работе", project_id="pp",
                 category="quarterly_tasks", include_in_analysis=True,
                 team="T", goals="3кв26"))
    db.add(Issue(id="kid", jira_issue_id="2", key="PP-2", summary="Подзадача",
                 issue_type="Task", status="Готово", project_id="pp",
                 parent_id="root", include_in_analysis=True))
    db.add(Issue(id="grandkid", jira_issue_id="3", key="PP-3", summary="Внучка",
                 issue_type="Sub-task", status="Готово", project_id="pp",
                 parent_id="kid", include_in_analysis=True))

    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Проект", issue_id="root",
                       estimate_analyst_hours=40.0, estimate_dev_hours=60.0,
                       estimate_qa_hours=20.0, estimate_opo_hours=10.0,
                       opo_analyst_ratio=0.5))

    q3_id, q4_id = _uid(), _uid()
    db.add(ResourcePlan(id=q3_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlan(id=q4_id, team="T", year=2026, quarter="Q4",
                        computed_at=datetime(2026, 10, 1)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=40.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 8, 15)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="dev", hours_allocated=60.0,
                                  start_date=date(2026, 8, 16), end_date=date(2026, 9, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q4_id, backlog_item_id=item_id,
                                  phase="qa", hours_allocated=20.0,
                                  start_date=date(2026, 10, 1), end_date=date(2026, 10, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="opo", hours_allocated=10.0,
                                  start_date=date(2026, 9, 21), end_date=date(2026, 9, 30)))

    mine = _employee(db, "Свой аналитик", "analyst", "T")
    dev = _employee(db, "Свой разработчик", "dev", "T")
    alien = _employee(db, "Чужой", "analyst", "OTHER")
    # Списание раньше квартала — накопительный факт обязан его учесть.
    _worklog(db, mine, "kid", 12.0, datetime(2026, 6, 10))
    _worklog(db, mine, "grandkid", 3.0, datetime(2026, 7, 5))
    _worklog(db, dev, "kid", 20.0, datetime(2026, 8, 1))
    _worklog(db, alien, "kid", 5.0, datetime(2026, 8, 2))
    db.commit()
    return {"analyst": mine, "dev": dev, "alien": alien}


def test_plan_sums_across_quarters_and_splits_opo(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    assert set(by_code) == {"analyst", "dev", "qa"}, "ОПЭ отдельным кольцом не показываем"
    # ОПЭ 10ч делится 50/50 между Анализом и Разработкой.
    assert by_code["analyst"]["plan_hours"] == 45.0
    assert by_code["dev"]["plan_hours"] == 65.0
    # Тестирование пришло из плана СЛЕДУЮЩЕГО квартала — горизонт весь проект.
    assert by_code["qa"]["plan_hours"] == 20.0
    assert plan["total_plan"] == 130.0


def test_fact_is_cumulative_over_subtree_and_excludes_outsiders(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    # 12ч (до квартала) + 3ч (внучка) = 15ч аналитика.
    assert by_code["analyst"]["fact_hours"] == 15.0
    assert by_code["dev"]["fact_hours"] == 20.0
    assert plan["total_fact"] == 35.0
    # Чужие 5ч — только в отдельной плашке.
    assert plan["external_hours"] == 5.0


def test_plan_absent_returns_none_plan(db_session):
    db = db_session
    db.add(Project(id="np", jira_project_id="np", key="NP", name="No plan"))
    db.add(Issue(id="nproot", jira_issue_id="10", key="NP-1", summary="Без плана",
                 issue_type="Epic", status="Новый", project_id="np",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.commit()

    plan = ProjectPlanService(db).get_plan("NP-1", year=2026, quarter=3)

    assert plan["total_plan"] is None
    assert plan["total_pct"] is None
    assert plan["total_fact"] == 0.0


def test_unknown_key_returns_none(db_session):
    assert ProjectPlanService(db_session).get_plan("NOPE-1", year=2026, quarter=3) is None
```

- [ ] **Step 2: Прогнать — должны упасть**

Run: `py -3.10 -m pytest tests/services/test_project_plan_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.project_plan_service'`

- [ ] **Step 3: Реализовать сервис**

Create `app/services/project_plan_service.py`:

```python
"""Проектный срез плана: план/факт по видам работ, задачи, таймлайн.

Отличие от рабочих столов: там персональная доля одного сотрудника, здесь —
проект целиком, со всеми исполнителями. Формулы общие, живут в plan_common.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.plan_common import (
    DISPLAY_ROLES,
    PHASE_LABEL,
    jira_url,
    plan_ids_for_issues,
    quarter_bounds,
    role_breakdown,
    subtree_ids,
    team_member_ids,
)


class ProjectPlanService:
    """Агрегаты вкладки «План и сроки» и сводного экрана портфеля."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Один проект
    # ------------------------------------------------------------------

    def get_plan(self, key: str, *, year: int, quarter: int) -> Optional[dict]:
        """Контракт вкладки «План и сроки». None — задача с таким ключом не найдена."""
        from app.models import Issue

        root = self._db.execute(select(Issue).where(Issue.key == key)).scalars().first()
        if root is None:
            return None

        q_start, q_end = quarter_bounds(year, quarter)
        subtree = subtree_ids(self._db, [root.id])
        plan_ids = plan_ids_for_issues(self._db, [root.id])
        team_ids = team_member_ids(self._db, self._project_teams(root, plan_ids))
        bd = role_breakdown(
            self._db, plan_ids, [root.id], subtree, q_end, team_ids
        )[root.id]

        work_types, total_plan, total_fact = _project_work_types(bd)
        return {
            "key": root.key,
            "work_types": work_types,
            "external_hours": round(bd["info"], 1),
            "total_plan": total_plan,
            "total_fact": total_fact,
            "total_pct": _pct(total_fact, total_plan),
            "timeline": self._timeline(plan_ids, [root.id], q_start, q_end),
            "children": self._children(root.id, q_end),
        }

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------

    def _project_teams(self, root, plan_ids: Sequence[str]) -> List[str]:
        """Команда проекта: поле задачи, иначе команда плана, иначе пусто."""
        if root.team:
            return [root.team]
        if plan_ids:
            from app.models import ResourcePlan

            teams = (
                self._db.execute(
                    select(ResourcePlan.team).where(ResourcePlan.id.in_(list(plan_ids)))
                )
                .scalars()
                .all()
            )
            return [t for t in dict.fromkeys(teams) if t]
        return []

    def _children(self, root_id: str, fact_until: date) -> List[dict]:
        """Прямые дети проекта; часы — по поддереву каждого ребёнка."""
        from app.models import Issue, Worklog

        rows = (
            self._db.query(Issue.id, Issue.key, Issue.summary, Issue.status)
            .filter(Issue.parent_id == root_id)
            .all()
        )
        if not rows:
            return []
        child_ids = [r.id for r in rows]
        sub = subtree_ids(self._db, child_ids)
        all_ids = {i for ids in sub.values() for i in ids}
        end_dt = datetime.combine(fact_until, time.max)
        hours_rows = (
            self._db.query(
                Worklog.issue_id,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
            )
            .filter(Worklog.issue_id.in_(all_ids), Worklog.started_at <= end_dt)
            .group_by(Worklog.issue_id)
            .all()
        )
        by_issue = {r.issue_id: float(r.hours or 0.0) for r in hours_rows}
        out = [
            {
                "key": r.key,
                "title": r.summary,
                "status": r.status,
                "jira_url": jira_url(r.key),
                "hours": round(sum(by_issue.get(i, 0.0) for i in sub.get(r.id, ())), 1),
            }
            for r in rows
        ]
        out.sort(key=lambda c: (-c["hours"], c["key"] or ""))
        return out

    def _timeline(
        self,
        plan_ids: Sequence[str],
        root_ids: Sequence[str],
        q_start: date,
        q_end: date,
    ) -> dict:
        """Полосы фаз по проектам. Шкала — от первой до последней даты назначений."""
        from app.models import BacklogItem, Issue, ResourcePlanAssignment

        rows: List[tuple] = []
        if plan_ids and root_ids:
            rows = (
                self._db.query(ResourcePlanAssignment, BacklogItem.issue_id, Issue.key,
                               Issue.summary, Issue.status)
                .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
                .join(Issue, Issue.id == BacklogItem.issue_id)
                .filter(
                    ResourcePlanAssignment.plan_id.in_(list(plan_ids)),
                    BacklogItem.issue_id.in_(list(root_ids)),
                    ResourcePlanAssignment.start_date.is_not(None),
                    ResourcePlanAssignment.end_date.is_not(None),
                )
                .order_by(ResourcePlanAssignment.start_date)
                .all()
            )

        by_issue: Dict[str, dict] = {}
        starts: List[date] = []
        ends: List[date] = []
        for a, issue_id, key, summary, status in rows:
            row = by_issue.setdefault(
                issue_id, {"key": key, "title": summary, "status": status, "bars": []}
            )
            row["bars"].append(
                {
                    "phase": a.phase,
                    "label": PHASE_LABEL.get(a.phase, a.phase or "—"),
                    "start_date": a.start_date.isoformat(),
                    "end_date": a.end_date.isoformat(),
                }
            )
            starts.append(a.start_date)
            ends.append(a.end_date)

        return {
            "start": min(starts).isoformat() if starts else None,
            "end": max(ends).isoformat() if ends else None,
            "quarter_start": q_start.isoformat(),
            "quarter_end": q_end.isoformat(),
            "rows": list(by_issue.values()),
        }


# ----------------------------------------------------------------------
# Чистые функции
# ----------------------------------------------------------------------

def _pct(fact: float, plan: Optional[float]) -> Optional[int]:
    if plan is None or plan <= 0:
        return None
    return round(fact / plan * 100)


def _project_work_types(bd: dict) -> tuple[List[dict], Optional[float], float]:
    """Из разбивки — список видов работ + итоги. total_plan=None если плана нет."""
    work_types: List[dict] = []
    for role in DISPLAY_ROLES:
        plan = round(bd["plan"].get(role, 0.0), 1)
        fact = round(bd["fact"].get(role, 0.0), 1)
        work_types.append(
            {
                "code": role,
                "label": PHASE_LABEL[role],
                "plan_hours": plan,
                "fact_hours": fact,
                "pct": _pct(fact, plan),
            }
        )
    total_plan_raw = round(sum(w["plan_hours"] for w in work_types), 1)
    total_fact = round(sum(w["fact_hours"] for w in work_types), 1)
    return work_types, (total_plan_raw if total_plan_raw > 0 else None), total_fact
```

- [ ] **Step 4: Прогнать тесты**

Run: `py -3.10 -m pytest tests/services/test_project_plan_service.py -v`
Expected: 4 passed

- [ ] **Step 5: Коммит**

```bash
git add app/services/project_plan_service.py tests/services/test_project_plan_service.py
git commit -m "feat(projects): сервис плана/факта проекта по видам работ"
```

---

## Task 4: Задачи проекта и таймлайн — покрыть тестами

Код написан в Task 3, но не покрыт. Дописываем тесты.

**Files:**
- Test: `tests/services/test_project_plan_service.py`

- [ ] **Step 1: Написать тесты**

Дописать в конец `tests/services/test_project_plan_service.py`:

```python
def test_children_include_own_subtree_hours(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    children = plan["children"]
    assert [c["key"] for c in children] == ["PP-2"], "только прямые дети корня"
    # 12 (свои) + 3 (внучка) + 20 (dev) + 5 (чужой) = 40ч по поддереву PP-2.
    assert children[0]["hours"] == 40.0
    assert children[0]["status"] == "Готово"
    assert children[0]["jira_url"].endswith("/PP-2")


def test_timeline_spans_all_quarters_of_the_project(db_session):
    db = db_session
    _seed_project(db)

    tl = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)["timeline"]

    assert tl["start"] == "2026-07-01"
    assert tl["end"] == "2026-10-20", "фаза следующего квартала не должна обрезаться"
    assert tl["quarter_start"] == "2026-07-01"
    assert tl["quarter_end"] == "2026-09-30"
    labels = [b["label"] for b in tl["rows"][0]["bars"]]
    assert labels == ["Анализ", "Разработка", "ОПЭ", "Тестирование"]


def test_timeline_empty_when_no_assignments(db_session):
    db = db_session
    db.add(Project(id="np2", jira_project_id="np2", key="NP2", name="No plan"))
    db.add(Issue(id="np2root", jira_issue_id="20", key="NP2-1", summary="Без плана",
                 issue_type="Epic", status="Новый", project_id="np2",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.commit()

    tl = ProjectPlanService(db).get_plan("NP2-1", year=2026, quarter=3)["timeline"]

    assert tl["start"] is None
    assert tl["rows"] == []
```

- [ ] **Step 2: Прогнать**

Run: `py -3.10 -m pytest tests/services/test_project_plan_service.py -v`
Expected: 7 passed. Если порядок полос в `test_timeline_spans_all_quarters_of_the_project`
не совпал — сортировка идёт по `start_date`, сверить даты в `_seed_project` и поправить
ожидание, а не код.

- [ ] **Step 3: Коммит**

```bash
git add tests/services/test_project_plan_service.py
git commit -m "test(projects): задачи проекта и таймлайн"
```

---

## Task 5: Агрегация портфеля + сигналы

**Files:**
- Modify: `app/services/project_plan_service.py`
- Test: `tests/services/test_project_plan_service.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/services/test_project_plan_service.py`:

```python
def test_portfolio_sums_projects_and_keeps_external_apart(db_session):
    db = db_session
    _seed_project(db)

    pf = ProjectPlanService(db).get_portfolio(["PP-1"], year=2026, quarter=3)

    assert pf["project_count"] == 1
    assert pf["total_plan"] == 130.0
    assert pf["total_fact"] == 35.0
    assert pf["total_pct"] == 27
    assert pf["external_hours"] == 5.0
    assert [r["key"] for r in pf["timeline"]["rows"]] == ["PP-1"]


def test_portfolio_signal_overload(db_session):
    db = db_session
    db.add(Project(id="ov", jira_project_id="ov", key="OV", name="Overload"))
    db.add(Issue(id="ovroot", jira_issue_id="30", key="OV-1", summary="Перегруз",
                 issue_type="Epic", status="В работе", project_id="ov",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Перегруз", issue_id="ovroot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=10.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 30)))
    emp = _employee(db, "Аналитик", "analyst", "T")
    _worklog(db, emp, "ovroot", 25.0, datetime(2026, 7, 15))
    db.commit()

    pf = ProjectPlanService(db).get_portfolio(["OV-1"], year=2026, quarter=3)

    kinds = {s["kind"] for s in pf["signals"]}
    assert "overload" in kinds
    overload = next(s for s in pf["signals"] if s["kind"] == "overload")
    assert "1" in overload["text"]


def test_portfolio_empty_list(db_session):
    pf = ProjectPlanService(db_session).get_portfolio([], year=2026, quarter=3)
    assert pf["project_count"] == 0
    assert pf["total_plan"] is None
    assert pf["signals"] == []
```

- [ ] **Step 2: Прогнать — упадут**

Run: `py -3.10 -m pytest tests/services/test_project_plan_service.py -k portfolio -v`
Expected: FAIL — `AttributeError: 'ProjectPlanService' object has no attribute 'get_portfolio'`

- [ ] **Step 3: Реализовать `get_portfolio`**

Добавить в класс `ProjectPlanService` (после `get_plan`):

```python
    # ------------------------------------------------------------------
    # Портфель
    # ------------------------------------------------------------------

    SILENT_DAYS = 14
    LAGGING_GAP_PP = 15

    def get_portfolio(self, keys: Sequence[str], *, year: int, quarter: int) -> dict:
        """Сводка по набору проектов — тому же, что видно в списке слева."""
        from app.models import Issue

        empty = {
            "project_count": 0,
            "work_types": [
                {"code": r, "label": PHASE_LABEL[r], "plan_hours": 0.0,
                 "fact_hours": 0.0, "pct": None}
                for r in DISPLAY_ROLES
            ],
            "external_hours": 0.0,
            "total_plan": None,
            "total_fact": 0.0,
            "total_pct": None,
            "timeline": {"start": None, "end": None, "rows": [],
                         "quarter_start": quarter_bounds(year, quarter)[0].isoformat(),
                         "quarter_end": quarter_bounds(year, quarter)[1].isoformat()},
            "signals": [],
        }
        wanted = [k for k in keys if k]
        if not wanted:
            return empty

        roots = (
            self._db.execute(select(Issue).where(Issue.key.in_(wanted))).scalars().all()
        )
        if not roots:
            return empty

        q_start, q_end = quarter_bounds(year, quarter)
        root_ids = [r.id for r in roots]
        subtree = subtree_ids(self._db, root_ids)
        plan_ids = plan_ids_for_issues(self._db, root_ids)

        # Состав команды считаем по каждому проекту отдельно: аналитик чужой
        # команды на одном проекте не должен портить цифры остальным.
        per_project: Dict[str, dict] = {}
        for root in roots:
            team_ids = team_member_ids(self._db, self._project_teams(root, plan_ids))
            per_project[root.id] = role_breakdown(
                self._db, plan_ids, [root.id], {root.id: subtree[root.id]}, q_end, team_ids
            )[root.id]

        totals = {"plan": {r: 0.0 for r in DISPLAY_ROLES},
                  "fact": {r: 0.0 for r in DISPLAY_ROLES},
                  "info": 0.0}
        project_pcts: Dict[str, Optional[int]] = {}
        for root in roots:
            bd = per_project[root.id]
            wt, total_plan, total_fact = _project_work_types(bd)
            for w in wt:
                totals["plan"][w["code"]] += w["plan_hours"]
                totals["fact"][w["code"]] += w["fact_hours"]
            totals["info"] += bd["info"]
            project_pcts[root.key] = _pct(total_fact, total_plan)

        work_types = [
            {
                "code": r,
                "label": PHASE_LABEL[r],
                "plan_hours": round(totals["plan"][r], 1),
                "fact_hours": round(totals["fact"][r], 1),
                "pct": _pct(totals["fact"][r], totals["plan"][r] or None),
            }
            for r in DISPLAY_ROLES
        ]
        total_plan_raw = round(sum(w["plan_hours"] for w in work_types), 1)
        total_plan = total_plan_raw if total_plan_raw > 0 else None
        total_fact = round(sum(w["fact_hours"] for w in work_types), 1)
        total_pct = _pct(total_fact, total_plan)

        return {
            "project_count": len(roots),
            "work_types": work_types,
            "external_hours": round(totals["info"], 1),
            "total_plan": total_plan,
            "total_fact": total_fact,
            "total_pct": total_pct,
            "timeline": self._timeline(plan_ids, root_ids, q_start, q_end),
            "signals": self._signals(roots, subtree, project_pcts, work_types, total_pct, q_end),
        }

    def _signals(
        self,
        roots,
        subtree: Dict[str, set],
        project_pcts: Dict[str, Optional[int]],
        work_types: List[dict],
        total_pct: Optional[int],
        fact_until: date,
    ) -> List[dict]:
        """Короткие подсказки «куда смотреть». Пустой список — полосу не рисуем."""
        from app.models import Worklog

        out: List[dict] = []

        overloaded = [k for k, p in project_pcts.items() if p is not None and p > 100]
        if overloaded:
            out.append({
                "kind": "overload",
                "text": f"{len(overloaded)} {_plural_projects(len(overloaded))} > 100% плана",
                "severity": "warn",
            })

        all_ids = {i for ids in subtree.values() for i in ids}
        last_rows = (
            self._db.query(Worklog.issue_id, func.max(Worklog.started_at).label("last"))
            .filter(Worklog.issue_id.in_(all_ids))
            .group_by(Worklog.issue_id)
            .all()
        )
        last_by_issue = {r.issue_id: r.last for r in last_rows}
        cutoff = datetime.combine(fact_until, time.max)
        silent = 0
        for root in roots:
            stamps = [last_by_issue[i] for i in subtree[root.id] if last_by_issue.get(i)]
            if not stamps:
                continue  # ещё не начинали — это не «замолчал»
            if (cutoff - max(stamps)).days > self.SILENT_DAYS:
                silent += 1
        if silent:
            out.append({
                "kind": "silent",
                "text": f"{silent} {_plural_projects(silent)} без списаний "
                        f"{self.SILENT_DAYS}+ дней",
                "severity": "warn",
            })

        if total_pct is not None:
            lagging = [
                w for w in work_types
                if w["pct"] is not None and total_pct - w["pct"] > self.LAGGING_GAP_PP
            ]
            if lagging:
                worst = min(lagging, key=lambda w: w["pct"])
                out.append({
                    "kind": "lagging",
                    "text": f"{worst['label']} отстаёт: {worst['pct']}% "
                            f"при {total_pct}% общей",
                    "severity": "info",
                })
        return out
```

И чистая функция в конец файла:

```python
def _plural_projects(n: int) -> str:
    """Склонение слова «проект» для чисел в подсказках."""
    if 11 <= n % 100 <= 14:
        return "проектов"
    return {1: "проект", 2: "проекта", 3: "проекта", 4: "проекта"}.get(n % 10, "проектов")
```

- [ ] **Step 4: Прогнать**

Run: `py -3.10 -m pytest tests/services/test_project_plan_service.py -v`
Expected: 10 passed

- [ ] **Step 5: Коммит**

```bash
git add app/services/project_plan_service.py tests/services/test_project_plan_service.py
git commit -m "feat(projects): сводка портфеля и сигналы"
```

---

## Task 6: Эндпоинты `/projects/{key}/plan` и `/projects/portfolio`

**Files:**
- Modify: `app/api/endpoints/projects.py`
- Test: `tests/test_projects_plan_endpoints.py`

- [ ] **Step 1: Написать падающие тесты**

Create `tests/test_projects_plan_endpoints.py`:

```python
"""Эндпоинты вкладки «План и сроки» и сводки портфеля."""
import uuid
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.worklog import Worklog


def _uid() -> str:
    return str(uuid.uuid4())


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _seed(db) -> None:
    db.add(Project(id="ep", jira_project_id="ep", key="EP", name="Endpoint"))
    db.add(Issue(id="eproot", jira_issue_id="1", key="EP-1", summary="Проект",
                 issue_type="Epic", status="В работе", project_id="ep",
                 category="quarterly_tasks", include_in_analysis=True,
                 team="T", goals="3кв26"))
    db.add(Issue(id="epother", jira_issue_id="2", key="EP-2", summary="Прошлый квартал",
                 issue_type="Epic", status="В работе", project_id="ep",
                 category="quarterly_tasks", include_in_analysis=True,
                 team="T", goals="2кв26"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Проект", issue_id="eproot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=40.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 8, 15)))
    eid = _uid()
    db.add(Employee(id=eid, jira_account_id=eid, display_name="Аналитик", role="analyst"))
    db.add(EmployeeTeam(id=_uid(), employee_id=eid, team="T", is_primary=True))
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id="eproot",
                   employee_id=eid, hours=10.0, started_at=datetime(2026, 7, 10)))
    db.commit()


def test_plan_endpoint_returns_work_types(db_session):
    _seed(db_session)
    try:
        resp = _client(db_session).get("/api/v1/projects/EP-1/plan?year=2026&quarter=3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_plan"] == 40.0
        assert body["total_fact"] == 10.0
        assert body["total_pct"] == 25
        assert [w["code"] for w in body["work_types"]] == ["analyst", "dev", "qa"]
        assert body["timeline"]["quarter_start"] == "2026-07-01"
    finally:
        app.dependency_overrides.clear()


def test_plan_endpoint_404_on_unknown_key(db_session):
    try:
        resp = _client(db_session).get("/api/v1/projects/NOPE-1/plan?year=2026&quarter=3")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_portfolio_endpoint_respects_quarter_filter(db_session):
    _seed(db_session)
    try:
        resp = _client(db_session).get("/api/v1/projects/portfolio?year=2026&quarter=3")
        assert resp.status_code == 200
        body = resp.json()
        # EP-2 живёт во 2кв26 — в выборку не попадает.
        assert body["project_count"] == 1
        assert [r["key"] for r in body["timeline"]["rows"]] == ["EP-1"]
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Прогнать — упадут**

Run: `py -3.10 -m pytest tests/test_projects_plan_endpoints.py -v`
Expected: FAIL — 404 на `/plan`, 422/404 на `/portfolio`

- [ ] **Step 3: Добавить схемы и эндпоинты**

В `app/api/endpoints/projects.py` добавить импорт рядом с остальными:

```python
from app.services.project_plan_service import ProjectPlanService
```

Добавить схемы **после** `class ProjectDetailSchema` (перед секцией `# New endpoints`):

```python
class WorkTypeSchema(BaseModel):
    code: str
    label: str
    plan_hours: float
    fact_hours: float
    pct: Optional[int] = None


class TimelineBarSchema(BaseModel):
    phase: str
    label: str
    start_date: str
    end_date: str


class TimelineRowSchema(BaseModel):
    key: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    bars: List[TimelineBarSchema]


class TimelineSchema(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    quarter_start: str
    quarter_end: str
    rows: List[TimelineRowSchema]


class PlanChildSchema(BaseModel):
    key: str
    title: Optional[str] = None
    status: Optional[str] = None
    jira_url: Optional[str] = None
    hours: float


class ProjectPlanSchema(BaseModel):
    key: str
    work_types: List[WorkTypeSchema]
    external_hours: float
    total_plan: Optional[float] = None
    total_fact: float
    total_pct: Optional[int] = None
    timeline: TimelineSchema
    children: List[PlanChildSchema]


class PortfolioSignalSchema(BaseModel):
    kind: str
    text: str
    severity: str


class PortfolioSchema(BaseModel):
    project_count: int
    work_types: List[WorkTypeSchema]
    external_hours: float
    total_plan: Optional[float] = None
    total_fact: float
    total_pct: Optional[int] = None
    timeline: TimelineSchema
    signals: List[PortfolioSignalSchema]
```

Добавить эндпоинты. **Важно:** `/portfolio` должен быть объявлен **до** `@router.get("/{key}")`,
иначе generic-роут перехватит слово `portfolio` как ключ проекта. Место — сразу после
`list_quarterly_projects`:

```python
@router.get("/portfolio", response_model=PortfolioSchema)
def get_portfolio(
    year: int = Query(..., description="год квартала"),
    quarter: int = Query(..., ge=1, le=4, description="квартал 1-4"),
    teams: Optional[str] = Query(None, description="comma-separated team names"),
    category: Optional[str] = Query(None),
    status_category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Сводка по тем же проектам, что видны в списке слева."""
    team_filter = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    items = ProjectsService(db).list_projects(
        team_filter=team_filter,
        category=category,
        status_category=status_category,
        search=search,
        year=year,
        quarter=quarter,
    )
    keys = [i.key for i in items]
    return ProjectPlanService(db).get_portfolio(keys, year=year, quarter=quarter)
```

И после `get_project` (в самом конце файла):

```python
@router.get("/{key}/plan", response_model=ProjectPlanSchema)
def get_project_plan(
    key: str,
    year: int = Query(..., description="год квартала"),
    quarter: int = Query(..., ge=1, le=4, description="квартал 1-4"),
    db: Session = Depends(get_db),
):
    """План/факт по видам работ, таймлайн фаз и задачи проекта."""
    plan = ProjectPlanService(db).get_plan(key, year=year, quarter=quarter)
    if plan is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return plan
```

- [ ] **Step 4: Прогнать**

Run: `py -3.10 -m pytest tests/test_projects_plan_endpoints.py -v`
Expected: 3 passed

- [ ] **Step 5: Прогнать весь бэкенд + линт**

Run: `py -3.10 -m pytest tests/ -q && py -3.10 -m ruff check app/ tests/`
Expected: тесты зелёные (кроме известных красных), ruff чисто

- [ ] **Step 6: Коммит**

```bash
git add app/api/endpoints/projects.py tests/test_projects_plan_endpoints.py
git commit -m "feat(projects): эндпоинты плана проекта и сводки портфеля"
```

---

## Task 7: Типы, клиент и хуки на фронте

**Files:**
- Modify: `frontend/src/types/projects.ts`
- Modify: `frontend/src/api/projects.ts`
- Modify: `frontend/src/hooks/useProjects.ts`

- [ ] **Step 1: Добавить типы**

Дописать в конец `frontend/src/types/projects.ts`:

```typescript
export interface PlanWorkType {
  code: 'analyst' | 'dev' | 'qa';
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number | null;
}

export interface TimelineBar {
  phase: string;
  label: string;
  start_date: string;
  end_date: string;
}

export interface TimelineRow {
  key: string | null;
  title: string | null;
  status: string | null;
  bars: TimelineBar[];
}

export interface PlanTimeline {
  start: string | null;
  end: string | null;
  quarter_start: string;
  quarter_end: string;
  rows: TimelineRow[];
}

export interface PlanChild {
  key: string;
  title: string | null;
  status: string | null;
  jira_url: string | null;
  hours: number;
}

export interface ProjectPlan {
  key: string;
  work_types: PlanWorkType[];
  external_hours: number;
  total_plan: number | null;
  total_fact: number;
  total_pct: number | null;
  timeline: PlanTimeline;
  children: PlanChild[];
}

export interface PortfolioSignal {
  kind: 'overload' | 'silent' | 'lagging';
  text: string;
  severity: 'warn' | 'info';
}

export interface Portfolio {
  project_count: number;
  work_types: PlanWorkType[];
  external_hours: number;
  total_plan: number | null;
  total_fact: number;
  total_pct: number | null;
  timeline: PlanTimeline;
  signals: PortfolioSignal[];
}

/** Фильтры списка проектов — общие для списка и сводки портфеля. */
export interface ProjectListFiltersState {
  search: string;
  statusCategory: string;
  category: string;
  year: number;
  quarter: number;
}
```

- [ ] **Step 2: Добавить методы клиента**

В `frontend/src/api/projects.ts` дополнить импорт типов и объект `projectsApi`:

```typescript
import type {
  ProjectListItem,
  ProjectDetail,
  ProjectSummary,
  ProjectPlan,
  Portfolio,
} from '../types/projects';
```

Внутрь `projectsApi` добавить два метода:

```typescript
  plan: (key: string, params: { year: string; quarter: string }, signal?: AbortSignal) =>
    api.get<ProjectPlan>(`/projects/${encodeURIComponent(key)}/plan`, params, signal),

  portfolio: (
    params: {
      year: string;
      quarter: string;
      teams?: string;
      category?: string;
      status_category?: string;
      search?: string;
    },
    signal?: AbortSignal,
  ) => api.get<Portfolio>('/projects/portfolio', params as Record<string, string | undefined>, signal),
```

- [ ] **Step 3: Добавить хуки**

Дописать в конец `frontend/src/hooks/useProjects.ts`:

```typescript
export function useProjectPlan(key: string | null, year: number, quarter: number) {
  return useQuery({
    queryKey: ['project-plan', key, year, quarter],
    queryFn: ({ signal }) =>
      projectsApi.plan(key!, { year: String(year), quarter: String(quarter) }, signal),
    enabled: !!key,
    staleTime: 30_000,
  });
}

export function usePortfolio(filters: {
  category?: string;
  status_category?: string;
  search?: string;
  year: number;
  quarter: number;
}) {
  const { queryParams } = useGlobalTeamFilter();
  const teams = queryParams.teams;
  return useQuery({
    queryKey: ['projects-portfolio', teams, filters],
    queryFn: ({ signal }) => projectsApi.portfolio({
      teams,
      category: filters.category,
      status_category: filters.status_category,
      search: filters.search,
      year: String(filters.year),
      quarter: String(filters.quarter),
    }, signal),
    staleTime: 30_000,
  });
}
```

- [ ] **Step 4: Проверить типы**

Run: `cd frontend && npm run lint`
Expected: без ошибок (новый код пока никем не используется — это нормально)

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/types/projects.ts frontend/src/api/projects.ts frontend/src/hooks/useProjects.ts
git commit -m "feat(projects): типы, клиент и хуки для плана и сводки"
```

---

## Task 8: Компонент `WorkTypeRings`

**Files:**
- Create: `frontend/src/components/projects/plan/WorkTypeRings.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
import React from 'react';
import type { PlanWorkType } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const WT_COLOR: Record<string, string> = {
  analyst: '#00c9c8',
  dev: '#378ADD',
  qa: '#EF9F27',
};

const RING_CIRC = 2 * Math.PI * 14;

interface Props {
  /** Левая группа: подпись над счётчиком проектов. Нет — группа не рисуется. */
  countLabel?: string;
  count?: number;
  workTypes: PlanWorkType[];
  externalHours: number;
  totalPlan: number | null;
  totalFact: number;
  totalPct: number | null;
}

function pctColor(pct: number | null): string {
  if (pct === null) return DARK_THEME.textMuted;
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#67d68d';
  return DARK_THEME.textPrimary;
}

const Ring: React.FC<{ wt: PlanWorkType }> = ({ wt }) => {
  const over = wt.pct !== null && wt.pct > 110;
  const shown = Math.max(0, Math.min(100, wt.pct ?? 0));
  const offset = RING_CIRC * (1 - shown / 100);
  const color = WT_COLOR[wt.code] ?? DARK_THEME.cyanPrimary;
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 12px',
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
      }}
    >
      <div style={{ position: 'relative', width: 38, height: 38, flexShrink: 0 }}>
        <svg viewBox="0 0 38 38" width={38} height={38}>
          <circle cx="19" cy="19" r="14" fill="none" strokeWidth="4"
                  stroke="rgba(255,255,255,0.08)" />
          <circle cx="19" cy="19" r="14" fill="none" strokeWidth="4" strokeLinecap="round"
                  stroke={over ? '#ff4d4f' : color}
                  strokeDasharray={RING_CIRC.toFixed(2)}
                  strokeDashoffset={over ? 0 : offset.toFixed(2)}
                  transform="rotate(-90 19 19)" />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontWeight: 600, color: over ? '#ff4d4f' : DARK_THEME.textPrimary,
        }}>
          {wt.pct === null ? '—' : `${wt.pct}%`}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em',
          color, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {wt.label}
        </div>
        <div style={{ fontSize: 12, color: DARK_THEME.textPrimary, whiteSpace: 'nowrap' }}>
          {Math.round(wt.fact_hours)} / {Math.round(wt.plan_hours)} ч
        </div>
      </div>
    </div>
  );
};

export const WorkTypeRings: React.FC<Props> = ({
  countLabel, count, workTypes, externalHours, totalPlan, totalFact, totalPct,
}) => (
  <div style={{ display: 'flex', alignItems: 'stretch', gap: 10, flexWrap: 'wrap' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 20, paddingRight: 8 }}>
      {countLabel && count !== undefined && (
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: DARK_THEME.textPrimary, lineHeight: 1.1 }}>
            {count}
          </div>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>{countLabel}</div>
        </div>
      )}
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: DARK_THEME.textPrimary, lineHeight: 1.1 }}>
          {Math.round(totalFact)} / {totalPlan === null ? '—' : Math.round(totalPlan)} ч
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
          {totalPlan === null ? 'план не заведён' : 'всего факт / план'}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: pctColor(totalPct), lineHeight: 1.1 }}>
          {totalPct === null ? '—' : `${totalPct}%`}
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>загрузка</div>
      </div>
    </div>

    {workTypes.map((wt) => <Ring key={wt.code} wt={wt} />)}

    <div
      title={externalHours > 0 ? 'Часы сотрудников не из команды — вне плана и факта' : undefined}
      style={{
        width: 96, flexShrink: 0, padding: '8px 10px', borderRadius: 8,
        background: 'rgba(0,0,0,0.22)',
        border: '1px solid rgba(255,255,255,0.04)',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}
    >
      {externalHours > 0 && (
        <>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: DARK_THEME.textMuted }}>
            Внешние
          </div>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
            {Math.round(externalHours)} ч
          </div>
        </>
      )}
    </div>
  </div>
);
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && npm run lint`
Expected: без ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/projects/plan/WorkTypeRings.tsx
git commit -m "feat(projects): полоса план/факт с кольцами по видам работ"
```

---

## Task 9: Компонент `PhaseTimeline`

**Files:**
- Create: `frontend/src/components/projects/plan/PhaseTimeline.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
import React from 'react';
import { Tooltip, Empty } from 'antd';
import type { PlanTimeline } from '../../../types/projects';
import { DARK_THEME, MONTH_NAMES } from '../../../utils/constants';

const PHASE_COLOR: Record<string, string> = {
  analyst: '#00c9c8',
  cons: '#00c9c8',
  dev: '#378ADD',
  qa: '#EF9F27',
  opo: '#7F77DD',
};

const LANE_H = 20;

function toTime(iso: string): number {
  return new Date(iso.slice(0, 10)).getTime();
}

/** Начало месяца, в который попадает дата. */
function monthFloor(iso: string): Date {
  const d = new Date(iso.slice(0, 10));
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** Начало месяца, следующего за датой. */
function monthCeil(iso: string): Date {
  const d = new Date(iso.slice(0, 10));
  return new Date(d.getFullYear(), d.getMonth() + 1, 1);
}

function monthLabels(start: Date, end: Date): string[] {
  const out: string[] = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cur.getTime() < end.getTime()) {
    out.push((MONTH_NAMES[cur.getMonth() + 1] ?? '').slice(0, 3));
    cur.setMonth(cur.getMonth() + 1);
  }
  return out;
}

interface Props {
  timeline: PlanTimeline;
  /** 'by-phase' — подпись строки = название фазы (один проект).
   *  'by-project' — подпись строки = ключ и название проекта. */
  mode: 'by-phase' | 'by-project';
  onRowClick?: (key: string) => void;
}

export const PhaseTimeline: React.FC<Props> = ({ timeline, mode, onRowClick }) => {
  if (!timeline.start || !timeline.end || timeline.rows.length === 0) {
    return (
      <Empty
        description={<span style={{ color: DARK_THEME.textMuted }}>Нет плановых дат</span>}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const scaleStart = monthFloor(timeline.start);
  const scaleEnd = monthCeil(timeline.end);
  const s0 = scaleStart.getTime();
  const span = scaleEnd.getTime() - s0 || 1;
  const pos = (t: number) => ((t - s0) / span) * 100;

  const labels = monthLabels(scaleStart, scaleEnd);
  const gridlines = labels.map((_, i) => (i / labels.length) * 100).slice(1);

  const qLeft = pos(toTime(timeline.quarter_start));
  const qRight = pos(toTime(timeline.quarter_end));

  const nowTime = Date.now();
  const nowLeft = nowTime >= s0 && nowTime <= scaleEnd.getTime() ? pos(nowTime) : null;

  // 'by-phase': каждая полоса становится своей строкой, подпись — название фазы.
  const rows = mode === 'by-phase'
    ? timeline.rows.flatMap((r) =>
        r.bars.map((b) => ({ key: r.key, label: b.label, bars: [b] })))
    : timeline.rows.map((r) => ({
        key: r.key,
        label: `${r.key ?? ''} · ${r.title ?? ''}`.trim(),
        bars: r.bars,
      }));

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 8, marginBottom: 4 }}>
        <div />
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${labels.length}, 1fr)` }}>
          {labels.map((m, i) => (
            <div key={i} style={{
              fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em',
              color: DARK_THEME.textMuted, textAlign: 'center',
            }}>{m}</div>
          ))}
        </div>
      </div>

      {rows.map((row, ri) => (
        <div
          key={`${row.key ?? ''}-${ri}`}
          style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 8, marginBottom: 3 }}
        >
          <div
            role={onRowClick && row.key ? 'button' : undefined}
            tabIndex={onRowClick && row.key ? 0 : undefined}
            onClick={onRowClick && row.key ? () => onRowClick(row.key!) : undefined}
            onKeyDown={onRowClick && row.key ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick(row.key!); }
            } : undefined}
            title={row.label}
            style={{
              fontSize: 11, color: DARK_THEME.textPrimary, alignSelf: 'center',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              cursor: onRowClick && row.key ? 'pointer' : 'default',
            }}
          >
            {row.label}
          </div>
          <div style={{
            position: 'relative', height: LANE_H + 6,
            background: 'rgba(255,255,255,0.02)', borderRadius: 4,
          }}>
            <div style={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${qLeft}%`, width: `${Math.max(0, qRight - qLeft)}%`,
              background: 'rgba(255,255,255,0.035)',
              borderLeft: '1px dashed rgba(255,255,255,0.14)',
              borderRight: '1px dashed rgba(255,255,255,0.14)',
            }} />
            {gridlines.map((g, i) => (
              <div key={i} style={{
                position: 'absolute', top: 0, bottom: 0, left: `${g}%`,
                width: 1, background: 'rgba(255,255,255,0.05)',
              }} />
            ))}
            {row.bars.map((b, bi) => {
              const left = pos(toTime(b.start_date));
              const width = Math.max(1.5, pos(toTime(b.end_date)) - left);
              return (
                <Tooltip
                  key={bi}
                  mouseEnterDelay={0.2}
                  title={`${b.label}: ${b.start_date} — ${b.end_date}`}
                >
                  <div style={{
                    position: 'absolute', top: 3, height: LANE_H,
                    left: `${left}%`, width: `${width}%`,
                    background: PHASE_COLOR[b.phase] ?? DARK_THEME.cyanPrimary,
                    borderRadius: 4, color: '#0d1c33', fontSize: 10, lineHeight: `${LANE_H}px`,
                    padding: '0 5px', overflow: 'hidden', whiteSpace: 'nowrap',
                  }}>
                    {width > 8 ? b.label : ''}
                  </div>
                </Tooltip>
              );
            })}
            {nowLeft !== null && (
              <div style={{
                position: 'absolute', top: 0, bottom: 0, left: `${nowLeft}%`,
                width: 2, background: DARK_THEME.cyanPrimary,
              }} />
            )}
          </div>
        </div>
      ))}

      <div style={{
        display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8,
        fontSize: 11, color: DARK_THEME.textMuted,
      }}>
        {[['analyst', 'Анализ'], ['dev', 'Разработка'], ['qa', 'Тестирование'], ['opo', 'ОПЭ']].map(
          ([code, label]) => (
            <span key={code} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{
                width: 10, height: 10, borderRadius: 2, background: PHASE_COLOR[code],
              }} />
              {label}
            </span>
          ),
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 2, height: 11, background: DARK_THEME.cyanPrimary }} />
          сегодня
        </span>
        <span>Затенено — границы квартала</span>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Проверить, что `MONTH_NAMES` экспортируется**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: без ошибок про `MONTH_NAMES`. Если такого экспорта нет в `utils/constants.ts` —
он используется в `MyTimelineWidget.tsx`, значит есть; проверить точное имя импорта.

- [ ] **Step 3: Линт**

Run: `cd frontend && npm run lint`
Expected: без ошибок

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/components/projects/plan/PhaseTimeline.tsx
git commit -m "feat(projects): таймлайн фаз с затенением квартала"
```

---

## Task 10: Компонент `ProjectTasksTable`

**Files:**
- Create: `frontend/src/components/projects/plan/ProjectTasksTable.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
import React from 'react';
import { Empty, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PlanChild } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const columns: ColumnsType<PlanChild> = [
  {
    title: 'Ключ',
    dataIndex: 'key',
    width: 130,
    render: (key: string, row) =>
      row.jira_url ? (
        <a href={row.jira_url} target="_blank" rel="noreferrer">{key}</a>
      ) : key,
  },
  {
    title: 'Название',
    dataIndex: 'title',
    ellipsis: true,
    render: (title: string | null) => title ?? '—',
  },
  {
    title: 'Статус',
    dataIndex: 'status',
    width: 160,
    render: (status: string | null) => status ?? '—',
  },
  {
    title: 'Часы',
    dataIndex: 'hours',
    width: 90,
    align: 'right',
    sorter: (a, b) => a.hours - b.hours,
    render: (hours: number) => `${Math.round(hours)} ч`,
  },
];

export const ProjectTasksTable: React.FC<{ children: PlanChild[] }> = ({ children }) => {
  if (children.length === 0) {
    return (
      <Empty
        description={<span style={{ color: DARK_THEME.textMuted }}>Нет задач</span>}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }
  return (
    <Table
      rowKey="key"
      size="small"
      pagination={false}
      columns={columns}
      dataSource={children}
    />
  );
};
```

- [ ] **Step 2: Линт**

Run: `cd frontend && npm run lint`
Expected: без ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/projects/plan/ProjectTasksTable.tsx
git commit -m "feat(projects): таблица задач проекта"
```

---

## Task 11: Вкладка «План и сроки»

**Files:**
- Create: `frontend/src/components/projects/ProjectPlanView.tsx`
- Modify: `frontend/src/components/projects/ProjectHeader.tsx`
- Modify: `frontend/src/components/projects/ProjectDetailPanel.tsx`

- [ ] **Step 1: Создать `ProjectPlanView.tsx`**

```tsx
import React from 'react';
import { Card, Spin } from 'antd';
import { useProjectPlan } from '../../hooks/useProjects';
import { WorkTypeRings } from './plan/WorkTypeRings';
import { PhaseTimeline } from './plan/PhaseTimeline';
import { ProjectTasksTable } from './plan/ProjectTasksTable';
import { DARK_THEME } from '../../utils/constants';

const cardStyle = {
  background: DARK_THEME.cardBg,
  border: '1px solid rgba(255,255,255,0.06)',
};

const cardTitle = (text: string) => (
  <span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>{text}</span>
);

interface Props {
  projectKey: string;
  year: number;
  quarter: number;
}

export const ProjectPlanView: React.FC<Props> = ({ projectKey, year, quarter }) => {
  const { data, isLoading } = useProjectPlan(projectKey, year, quarter);

  if (isLoading || !data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <WorkTypeRings
        workTypes={data.work_types}
        externalHours={data.external_hours}
        totalPlan={data.total_plan}
        totalFact={data.total_fact}
        totalPct={data.total_pct}
      />

      <Card
        size="small"
        title={cardTitle('Таймлайн проекта')}
        style={cardStyle}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <PhaseTimeline timeline={data.timeline} mode="by-phase" />
      </Card>

      <Card
        size="small"
        title={cardTitle(`Задачи проекта · ${data.children.length}`)}
        style={cardStyle}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <ProjectTasksTable children={data.children} />
      </Card>
    </div>
  );
};
```

- [ ] **Step 2: Добавить третье значение режима в `ProjectHeader.tsx`**

Найти строку 16:

```typescript
type ViewMode = 'analysis' | 'presentation';
```

Заменить на:

```typescript
type ViewMode = 'analysis' | 'presentation' | 'plan';
```

Найти в JSX переключатель вкладок (кнопки «Анализ» / «Презентация») и добавить третью
кнопку той же разметкой сразу после «Презентация». Точная разметка зависит от того, как
там сверстаны первые две — **скопировать структуру существующей кнопки «Презентация»**,
заменив в копии:
- значение режима на `'plan'`
- подпись на `План и сроки`

- [ ] **Step 3: Пробросить режим и период в `ProjectDetailPanel.tsx`**

Заменить строку 11:

```typescript
type ViewMode = 'analysis' | 'presentation';
```

на:

```typescript
type ViewMode = 'analysis' | 'presentation' | 'plan';
```

Расширить пропсы (строки 13–15):

```typescript
interface Props {
  projectKey: string;
  year: number;
  quarter: number;
}
```

Изменить сигнатуру и добавить импорт:

```typescript
import { ProjectPlanView } from './ProjectPlanView';

export const ProjectDetailPanel: React.FC<Props> = ({ projectKey, year, quarter }) => {
```

Заменить блок рендера (строки 56–68) на:

```tsx
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {view === 'analysis' && (
          <ProjectAnalysisView
            detail={detail}
            summary={summaryLoading ? undefined : summary}
          />
        )}
        {view === 'presentation' && (
          <ProjectPresentationView
            detail={detail}
            summary={summaryLoading ? undefined : summary}
          />
        )}
        {view === 'plan' && (
          <ProjectPlanView projectKey={projectKey} year={year} quarter={quarter} />
        )}
      </div>
```

- [ ] **Step 4: Линт**

Run: `cd frontend && npm run lint`
Expected: ошибка о том, что `ProjectDetailPanel` в `ProjectsPage.tsx` вызывается без
`year`/`quarter` — она чинится в Task 13. Остальных ошибок быть не должно.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/components/projects/ProjectPlanView.tsx frontend/src/components/projects/ProjectHeader.tsx frontend/src/components/projects/ProjectDetailPanel.tsx
git commit -m "feat(projects): вкладка «План и сроки» в карточке проекта"
```

---

## Task 12: Компоненты `PortfolioSignals` и `PortfolioView`

**Files:**
- Create: `frontend/src/components/projects/plan/PortfolioSignals.tsx`
- Create: `frontend/src/components/projects/PortfolioView.tsx`

- [ ] **Step 1: Создать `PortfolioSignals.tsx`**

```tsx
import React from 'react';
import type { PortfolioSignal } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const DOT_COLOR: Record<string, string> = {
  warn: '#faad14',
  info: DARK_THEME.cyanPrimary,
};

export const PortfolioSignals: React.FC<{ signals: PortfolioSignal[] }> = ({ signals }) => {
  if (signals.length === 0) return null;
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {signals.map((s) => (
        <span
          key={s.kind}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            fontSize: 12, color: DARK_THEME.textPrimary,
            padding: '5px 12px', borderRadius: 14,
            background: 'rgba(255,255,255,0.04)',
            border: `1px solid ${DARK_THEME.border}`,
          }}
        >
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: DOT_COLOR[s.severity] ?? DARK_THEME.textMuted,
          }} />
          {s.text}
        </span>
      ))}
    </div>
  );
};
```

- [ ] **Step 2: Создать `PortfolioView.tsx`**

```tsx
import React from 'react';
import { Card, Empty, Spin } from 'antd';
import { useNavigate } from 'react-router';
import { usePortfolio } from '../../hooks/useProjects';
import type { ProjectListFiltersState } from '../../types/projects';
import { WorkTypeRings } from './plan/WorkTypeRings';
import { PhaseTimeline } from './plan/PhaseTimeline';
import { PortfolioSignals } from './plan/PortfolioSignals';
import { DARK_THEME } from '../../utils/constants';

export const PortfolioView: React.FC<{ filters: ProjectListFiltersState }> = ({ filters }) => {
  const navigate = useNavigate();
  const { data, isLoading } = usePortfolio({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  });

  if (isLoading || !data) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (data.project_count === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Empty
          description={
            <span style={{ color: DARK_THEME.textMuted }}>Нет проектов за выбранный квартал</span>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <WorkTypeRings
        countLabel="проектов"
        count={data.project_count}
        workTypes={data.work_types}
        externalHours={data.external_hours}
        totalPlan={data.total_plan}
        totalFact={data.total_fact}
        totalPct={data.total_pct}
      />

      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Таймлайн портфеля</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <PhaseTimeline
          timeline={data.timeline}
          mode="by-project"
          onRowClick={(key) => navigate(`/projects/${encodeURIComponent(key)}`)}
        />
      </Card>

      <PortfolioSignals signals={data.signals} />
    </div>
  );
};
```

- [ ] **Step 3: Линт**

Run: `cd frontend && npm run lint`
Expected: только известная ошибка про `ProjectDetailPanel` из Task 11

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/components/projects/plan/PortfolioSignals.tsx frontend/src/components/projects/PortfolioView.tsx
git commit -m "feat(projects): сводный экран портфеля"
```

---

## Task 13: Подъём фильтров и подключение сводки

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/components/projects/ProjectsList.tsx`

- [ ] **Step 1: Переписать `ProjectsPage.tsx`**

Фильтры переезжают сюда из `ProjectsList`, чтобы сводка считалась по тому же набору.

```tsx
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../components/projects/PortfolioView';
import type { ProjectListFiltersState } from '../types/projects';
import { DARK_THEME } from '../utils/constants';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = (Math.floor(new Date().getMonth() / 3) + 1) as 1 | 2 | 3 | 4;

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  const [filters, setFilters] = useState<ProjectListFiltersState>({
    search: '',
    statusCategory: '',
    category: '',
    year: CURRENT_YEAR,
    quarter: CURRENT_QUARTER,
  });

  const handleSelect = (selectedKey: string) => {
    // Повторный клик по выбранной карточке возвращает к сводке.
    if (selectedKey === key) {
      navigate('/projects');
      return;
    }
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  return (
    <div
      className="projects-master-detail"
      style={{
        display: 'flex',
        height: 'calc(100vh - 64px)',
        background: DARK_THEME.pageBg,
        overflow: 'hidden',
      }}
    >
      <ProjectsList
        selectedKey={key ?? null}
        onSelect={handleSelect}
        filters={filters}
        onFiltersChange={setFilters}
        onShowPortfolio={() => navigate('/projects')}
      />

      {key ? (
        <ProjectDetailPanel
          projectKey={key}
          year={filters.year}
          quarter={filters.quarter}
        />
      ) : (
        <PortfolioView filters={filters} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Переписать `ProjectsList.tsx` под внешние фильтры**

```tsx
import React from 'react';
import { Skeleton, Empty, Select, Tag, Button } from 'antd';
import { useProjectsList } from '../../hooks/useProjects';
import type { ProjectListFiltersState } from '../../types/projects';
import { ProjectListCard } from './ProjectListCard';
import { ProjectListFilters } from './ProjectListFilters';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  selectedKey: string | null;
  onSelect: (key: string) => void;
  filters: ProjectListFiltersState;
  onFiltersChange: (next: ProjectListFiltersState) => void;
  onShowPortfolio: () => void;
}

const CURRENT_YEAR = new Date().getFullYear();

export const ProjectsList: React.FC<Props> = ({
  selectedKey, onSelect, filters, onFiltersChange, onShowPortfolio,
}) => {
  const patch = (part: Partial<ProjectListFiltersState>) =>
    onFiltersChange({ ...filters, ...part });

  const { data: projects, isLoading } = useProjectsList({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  });

  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = CURRENT_YEAR - 1 + i;
    return { value: y, label: String(y) };
  });

  return (
    <div
      style={{
        width: 360,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${DARK_THEME.border}`,
        background: DARK_THEME.cardBg,
        height: '100%',
      }}
    >
      <div style={{ padding: '12px 12px 8px', borderBottom: `1px solid ${DARK_THEME.border}` }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: DARK_THEME.textPrimary }}>
            Проекты
            {projects && (
              <span style={{ fontSize: 12, fontWeight: 400, color: DARK_THEME.textMuted, marginLeft: 8 }}>
                {projects.length}
              </span>
            )}
          </div>
          <Button
            size="small"
            type={selectedKey ? 'default' : 'primary'}
            onClick={onShowPortfolio}
          >
            Сводка
          </Button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Select
            value={filters.year}
            onChange={(y) => patch({ year: y })}
            options={yearOptions}
            style={{ width: 78 }}
            size="small"
          />
          {([1, 2, 3, 4] as const).map((q) => (
            <Tag
              key={q}
              color={filters.quarter === q ? 'cyan' : undefined}
              style={{ cursor: 'pointer', userSelect: 'none', marginRight: 0, fontSize: 12 }}
              onClick={() => patch({ quarter: q })}
            >
              Q{q}
            </Tag>
          ))}
        </div>
      </div>

      <ProjectListFilters
        search={filters.search}
        onSearchChange={(v) => patch({ search: v })}
        statusCategory={filters.statusCategory}
        onStatusCategoryChange={(v) => patch({ statusCategory: v })}
        category={filters.category}
        onCategoryChange={(v) => patch({ category: v })}
      />

      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 8px' }}>
        {isLoading && (
          <>
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} active paragraph={{ rows: 2 }} style={{ marginBottom: 8 }} />
            ))}
          </>
        )}
        {!isLoading && (!projects || projects.length === 0) && (
          <Empty
            description="Нет проектов"
            style={{ marginTop: 48, color: DARK_THEME.textMuted }}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
        {!isLoading &&
          projects?.map((item) => (
            <ProjectListCard
              key={item.key}
              item={item}
              selected={item.key === selectedKey}
              onClick={() => onSelect(item.key)}
            />
          ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Линт и сборка**

Run: `cd frontend && npm run lint && npm run build`
Expected: обе команды зелёные, ошибка из Task 11 исчезла

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/components/projects/ProjectsList.tsx
git commit -m "feat(projects): сводка портфеля вместо заглушки + кнопка «Сводка»"
```

---

## Task 14: Проверка в браузере на реальных данных

**Files:** нет — ручная проверка

- [ ] **Step 1: Поднять бэкенд**

Windows: `--reload` часто зависает — убить процесс на порту и запустить заново.

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
py -3.10 -m uvicorn app.main:app --port 8000
```

- [ ] **Step 2: Поднять фронт**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Проверить сценарии**

Открыть `http://localhost:5173/projects` и убедиться:

1. Без выбранного проекта справа — сводка: кольца, таймлайн, чипы.
2. Кольца показывают три вида работ; «Внешние» видно только когда часы есть.
3. Таймлайн: затенение квартала на месте, полосы выходят за него у длинных проектов.
4. Клик по строке таймлайна открывает карточку проекта.
5. В карточке появилась третья вкладка «План и сроки», первые две не изменились.
6. На вкладке: полоса, таймлайн фаз, таблица задач с рабочими ссылками в Jira.
7. Кнопка «Сводка» и повторный клик по карточке возвращают к сводке.
8. Смена квартала Q1–Q4 меняет и список, и сводку.
9. Проект без плана: план `—`, «план не заведён», таймлайн — «Нет плановых дат».

- [ ] **Step 4: Записать найденные расхождения**

Если что-то не сходится с макетом или считается неверно — зафиксировать список и чинить
до перехода к Task 15. Расхождения по числам проверять против `/desk/<токен>` того же
проекта: там те же формулы, только персональный срез.

---

## Task 15: Заметка о релизе, граф и финальный прогон

**Files:**
- Modify: `release_notes/drafts.json` (через скрипт, руками не редактировать)

- [ ] **Step 1: Добавить заметку**

```bash
py -3.10 scripts/release_note.py add --type new --section projects \
  --title "Раздел «Проекты»: план, сроки и задачи" \
  --description "В карточке проекта появилась вкладка «План и сроки»: плановые и фактические часы по видам работ, таймлайн фаз проекта и список его задач со статусами и часами. Если проект не выбран, справа теперь сводка по всем проектам квартала — общая загрузка, разбивка по видам работ, таймлайн всех проектов и подсказки, где отставание или перегруз. Привязка проекта к кварталу берётся из поля «Цели»."
```

`--type` принимает только `new` / `improvement` / `fix` — не Conventional-Commits типы.

- [ ] **Step 2: Обновить граф кода**

```bash
graphify update .
```

- [ ] **Step 3: Полный прогон**

```bash
py -3.10 -m pytest tests/ -q
py -3.10 -m ruff check app/ tests/
cd frontend && npm run lint && npm run build
```

Expected: всё зелёное, кроме уже известных красных тестов, зафиксированных до начала работы.

- [ ] **Step 4: Коммит и пуш**

```bash
git add release_notes/drafts.json
git commit -m "docs(release): заметка про план, сроки и сводку в разделе «Проекты»"
git push origin main
```

---

## Проверка плана против спеки

| Требование спеки | Задача |
|---|---|
| §2.1 вкладка «План и сроки» | Task 11 |
| §2.2 сводный экран портфеля | Task 12, 13 |
| §2.3 возврат к сводке | Task 13 |
| §3.1 план по видам работ, весь срок, свежайший план на квартал | Task 1 (`plan_ids_for_issues`), Task 3 |
| §3.1 схлопывание ОПЭ | Task 1 (`role_breakdown`), тест в Task 3 |
| §3.2 накопительный факт по поддереву, роль РП в Анализ | Task 1, тест в Task 3 |
| §3.3 внешние часы отдельно, команда по проекту | Task 3 (`_project_teams`), Task 5 |
| §3.4 задачи проекта с часами поддерева | Task 3 (`_children`), тест в Task 4 |
| §3.5 таймлайн | Task 3 (`_timeline`), Task 9 |
| §4 квартальный фильтр | без изменений — Task 2 отменена |
| §5 пустые состояния | Task 3 (план `None`), Task 9 (нет дат), Task 10 (нет задач), Task 12 (нет проектов) |
| §6 два эндпоинта + вынос в `plan_common` | Task 1, Task 6 |
| §7 компоненты и правки страниц | Task 8–13 |
| §8 тесты | Task 1, 2, 3, 4, 5, 6 |
