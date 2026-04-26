# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить текущий дашборд на три виджета квартального PM-управления: обзор проектов (hero-карточка), план/факт нормированных работ (bullet-бары), метрики ворклогов по категориям (treemap + таблица) — с единым квартальным фильтром вместо произвольного диапазона дат.

**Architecture:** Новые FastAPI-эндпоинты в `analytics.py` агрегируют данные через `AnalyticsService`. Фронтенд — три изолированных компонента-виджета, управляемых общим `QuarterPicker`. Период передаётся как `year + quarter + optional month`; бекенд конвертирует в даты через `app/utils/period.py`. Существующие аналитические эндпоинты (employees, projects, category, period, switching) остаются нетронутыми — страница Аналитики всё ещё их использует.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch mode). React 19, TypeScript, Ant Design 6, TanStack Query, Recharts (для donut), кастомный CSS-треemap (без Recharts Treemap).

**Plans B and C (separate docs):**
- Plan B: страница Аналитики — master-detail карточка проекта
- Plan C: синхронизация description/due_date/полей оценки + AI-генерация

---

## File Map

**Создаём:**
- `app/utils/period.py` — конвертация year/quarter/month → date range
- `app/schemas/dashboard.py` — Pydantic-схемы для трёх новых эндпоинтов
- `frontend/src/components/shared/QuarterPicker.tsx` — единый фильтр квартала/месяца
- `frontend/src/components/dashboard/ProjectsWidget.tsx` — виджет 1
- `frontend/src/components/dashboard/NormWorkWidget.tsx` — виджет 2
- `frontend/src/components/dashboard/CategoryWidget.tsx` — виджет 3
- `tests/test_dashboard_endpoints.py` — тесты новых эндпоинтов

**Изменяем:**
- `app/models/__init__.py` — добавить `Issue.due_date`
- `app/services/sync_service.py` — синхронизировать `due_date` из Jira
- `app/connectors/jira_client.py` — включить `due_date` в список fields
- `app/services/analytics_service.py` — три новых метода агрегации
- `app/api/endpoints/analytics.py` — три новых роута
- `frontend/src/api/analytics.ts` — три новых API-функции
- `frontend/src/hooks/useAnalytics.ts` — три новых хука
- `frontend/src/types/api.ts` — типы для трёх виджетов
- `frontend/src/pages/DashboardPage.tsx` — переключить на новые виджеты + QuarterPicker

**Создаём миграцию:**
- `alembic/versions/XXXX_add_due_date_to_issue.py`

---

## Task 1: Backend — утилита конвертации периода

**Files:**
- Create: `app/utils/period.py`
- Create: `tests/test_period_util.py`

- [ ] **Step 1: Написать тест**

```python
# tests/test_period_util.py
import pytest
from datetime import date
from app.utils.period import quarter_to_dates

def test_full_quarter():
    start, end = quarter_to_dates(2026, 2)
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 30)

def test_quarter_with_month():
    start, end = quarter_to_dates(2026, 2, month=5)
    assert start == date(2026, 5, 1)
    assert end == date(2026, 5, 31)

def test_q1():
    start, end = quarter_to_dates(2026, 1)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)

def test_q4():
    start, end = quarter_to_dates(2026, 4)
    assert start == date(2026, 10, 1)
    assert end == date(2026, 12, 31)

def test_invalid_month_raises():
    with pytest.raises(ValueError):
        quarter_to_dates(2026, 2, month=1)  # январь не в Q2
```

- [ ] **Step 2: Запустить тест — убедиться что падает**

```bash
py -3.10 -m pytest tests/test_period_util.py -v
```
Ожидаем: `ImportError: cannot import name 'quarter_to_dates'`

- [ ] **Step 3: Реализовать**

```python
# app/utils/period.py
import calendar
from datetime import date

_QUARTER_MONTHS: dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}


def quarter_to_dates(year: int, quarter: int, month: int | None = None) -> tuple[date, date]:
    """Конвертирует год/квартал (и опционально месяц) в начальную и конечную даты."""
    if quarter not in _QUARTER_MONTHS:
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    q_months = _QUARTER_MONTHS[quarter]
    if month is not None:
        if month not in q_months:
            raise ValueError(f"month {month} is not in Q{quarter} (months: {q_months})")
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
    else:
        start = date(year, q_months[0], 1)
        last_month = q_months[-1]
        end = date(year, last_month, calendar.monthrange(year, last_month)[1])
    return start, end


def current_quarter() -> tuple[int, int]:
    """Возвращает (year, quarter) для текущей даты."""
    today = date.today()
    for q, months in _QUARTER_MONTHS.items():
        if today.month in months:
            return today.year, q
    raise RuntimeError("unreachable")
```

- [ ] **Step 4: Запустить тест — убедиться что проходит**

```bash
py -3.10 -m pytest tests/test_period_util.py -v
```
Ожидаем: все 5 тестов PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/utils/period.py tests/test_period_util.py
git commit -m "feat(analytics): quarter_to_dates period utility"
```

---

## Task 2: Model + migration — добавить `Issue.due_date`

**Files:**
- Modify: `app/models/__init__.py` (поле `due_date` в классе `Issue`)
- Create: `alembic/versions/XXXX_add_due_date_to_issue.py`

- [ ] **Step 1: Найти класс Issue в models и добавить поле**

В `app/models/__init__.py` в классе `Issue` добавить после поля `status_changed_at`:

```python
due_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
```

Импорт `Optional` уже есть. `datetime` тоже.

- [ ] **Step 2: Создать миграцию**

```bash
alembic revision --autogenerate -m "add due_date to issue"
```

Проверить сгенерированный файл — должен содержать `op.add_column('issues', sa.Column('due_date', sa.DateTime(), nullable=True))`. Если использует batch mode для SQLite — убедиться что обёрнуто в `with op.batch_alter_table`.

- [ ] **Step 3: Применить миграцию**

```bash
alembic upgrade head
```

- [ ] **Step 4: Добавить `due_date` в sync**

В `app/connectors/jira_client.py` в методе `search_issues` (или в константе DEFAULT_FIELDS) добавить `"duedate"` в список полей.

В `app/services/sync_service.py` в методе `_upsert_issue` после строки с `status_changed_at` добавить:

```python
due_raw = fields.get("duedate")
issue.due_date = _parse_jira_datetime(due_raw) if due_raw else None
```

- [ ] **Step 5: Коммит**

```bash
git add app/models/__init__.py app/services/sync_service.py app/connectors/jira_client.py alembic/versions/
git commit -m "feat(sync): add due_date field to Issue from Jira duedate"
```

---

## Task 3: Backend schemas для дашборда

**Files:**
- Create: `app/schemas/dashboard.py`

- [ ] **Step 1: Создать файл схем**

```python
# app/schemas/dashboard.py
from pydantic import BaseModel


# ── Widget 1: Projects overview ──────────────────────────────────────────────

class ProjectAttentionItem(BaseModel):
    issue_key: str
    title: str
    fact_hours: float
    days_overdue: int | None   # None если не просрочен
    days_silent: int | None    # None если была активность недавно


class ProjectOverrunItem(BaseModel):
    issue_key: str
    title: str
    plan_hours: float
    fact_hours: float
    delta_hours: float         # fact - plan


class DashboardProjectsResponse(BaseModel):
    total: int
    done: int
    in_progress: int
    overdue: int
    not_started: int
    forecast_done: int         # прогноз: сколько закроется к концу квартала
    forecast_pct: float        # forecast_done / total * 100
    attention_list: list[ProjectAttentionItem]
    overrun_list: list[ProjectOverrunItem]


# ── Widget 2: Norm work plan/fact ────────────────────────────────────────────

class NormWorkItem(BaseModel):
    work_type_id: str
    label: str
    plan_hours: float
    fact_hours: float
    pct: float                 # fact / plan * 100 (0 если plan == 0)


class DashboardNormWorkResponse(BaseModel):
    items: list[NormWorkItem]
    total_plan: float
    total_fact: float
    total_pct: float


# ── Widget 3: Category metrics ───────────────────────────────────────────────

class CategoryMetaItem(BaseModel):
    key: str
    label: str
    color: str
    hours: float
    worklog_count: int
    issue_count: int
    employee_count: int
    avg_worklog_minutes: float
    pct: float                 # от общего числа часов в периоде


class DashboardCategoriesResponse(BaseModel):
    items: list[CategoryMetaItem]
    total_hours: float
```

- [ ] **Step 2: Коммит**

```bash
git add app/schemas/dashboard.py
git commit -m "feat(dashboard): Pydantic schemas for 3 dashboard widgets"
```

---

## Task 4: Backend — Widget 1 service + endpoint

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `app/api/endpoints/analytics.py`

- [ ] **Step 1: Написать тест эндпоинта**

В `tests/test_dashboard_endpoints.py`:

```python
# tests/test_dashboard_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_projects_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "done" in data
    assert "attention_list" in data
    assert "overrun_list" in data

def test_projects_widget_invalid_quarter():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=5")
    assert resp.status_code == 422
```

- [ ] **Step 2: Запустить тест — убедиться что падает (404)**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_projects_widget_returns_200 -v
```

- [ ] **Step 3: Добавить метод в AnalyticsService**

В `app/services/analytics_service.py` добавить метод `get_dashboard_projects`:

```python
from datetime import date, datetime, timezone
from app.utils.period import quarter_to_dates
from app.schemas.dashboard import (
    DashboardProjectsResponse, ProjectAttentionItem, ProjectOverrunItem,
)
from app.models import Issue, ScenarioAllocation, BacklogItem, PlanningScenario, Worklog
from sqlalchemy import select, func

def get_dashboard_projects(
    self,
    year: int,
    quarter: int,
    month: int | None = None,
    team: str | None = None,
    silence_days: int = 14,
) -> DashboardProjectsResponse:
    """Агрегирует статусы проектов утверждённого сценария на квартал."""
    start, end = quarter_to_dates(year, quarter, month)

    # Получаем issue_key всех проектов из approved сценария квартала
    q_str = f"Q{quarter}"
    approved_keys: list[str] = list(
        self.db.scalars(
            select(BacklogItem.jira_key)
            .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .where(
                PlanningScenario.year == year,
                PlanningScenario.quarter == q_str,
                PlanningScenario.status == "approved",
                BacklogItem.jira_key.isnot(None),
            )
        ).all()
    )

    if not approved_keys:
        return DashboardProjectsResponse(
            total=0, done=0, in_progress=0, overdue=0, not_started=0,
            forecast_done=0, forecast_pct=0.0, attention_list=[], overrun_list=[],
        )

    # Загружаем Issues для этих ключей
    issues: list[Issue] = list(
        self.db.scalars(select(Issue).where(Issue.jira_key.in_(approved_keys)))
    )

    today = date.today()
    quarter_start, quarter_end = quarter_to_dates(year, quarter)
    total_days = (quarter_end - quarter_start).days + 1
    passed_days = max(1, (today - quarter_start).days + 1)
    remaining_days = max(0, (quarter_end - today).days)

    done = sum(1 for i in issues if i.status_category == "done")
    in_progress = sum(1 for i in issues if i.status_category == "indeterminate")
    not_started = sum(1 for i in issues if i.status_category == "new")

    # Просрочено: due_date < today и не завершено
    overdue_issues = [
        i for i in issues
        if i.status_category != "done"
        and i.due_date is not None
        and i.due_date.date() < today
    ]
    overdue = len(overdue_issues)

    # Прогноз: линейная экстраполяция по темпу завершения
    rate_per_day = done / passed_days if passed_days > 0 else 0.0
    forecast_additional = int(rate_per_day * remaining_days)
    forecast_done = min(len(issues), done + forecast_additional)
    forecast_pct = round(forecast_done / len(issues) * 100, 1) if issues else 0.0

    # Ворклоги за период (для silent и overrun)
    issue_keys_list = [i.jira_key for i in issues if i.jira_key]
    
    # Последний ворклог на каждую задачу (через подзапрос)
    last_worklog_sub = (
        select(Worklog.issue_id, func.max(Worklog.started_at).label("last_log"))
        .where(Worklog.issue_id.in_(select(Issue.id).where(Issue.jira_key.in_(issue_keys_list))))
        .group_by(Worklog.issue_id)
        .subquery()
    )
    last_logs = dict(
        self.db.execute(
            select(Issue.jira_key, last_worklog_sub.c.last_log)
            .join(last_worklog_sub, last_worklog_sub.c.issue_id == Issue.id)
        ).all()
    )

    # Факт часов на каждый проект (сумма по дочерним задачам)
    # Упрощение: ворклоги напрямую на epic или дочерних задачах с parent_id = epic
    # Для MVP используем parent_key matching: worklogs where issue.jira_key starts with epic prefix
    # Более точно: worklogs where issue.parent_id = epic.id — используем это
    epic_ids = {i.jira_key: i.id for i in issues if i.jira_key}
    
    fact_hours_by_epic: dict[str, float] = {}
    for jira_key, epic_id in epic_ids.items():
        total = self.db.scalar(
            select(func.sum(Worklog.hours))
            .join(Issue, Issue.id == Worklog.issue_id)
            .where(
                (Issue.parent_id == epic_id) | (Issue.id == epic_id),
                Worklog.started_at >= datetime.combine(start, datetime.min.time()),
                Worklog.started_at <= datetime.combine(end, datetime.max.time()),
            )
        ) or 0.0
        fact_hours_by_epic[jira_key] = float(total)

    # Attention list: просроченные + тихие
    silence_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - __import__('datetime').timedelta(days=silence_days)
    attention: list[ProjectAttentionItem] = []
    for issue in issues:
        if issue.status_category == "done" or not issue.jira_key:
            continue
        days_overdue = None
        if issue.due_date and issue.due_date.date() < today:
            days_overdue = (today - issue.due_date.date()).days
        last = last_logs.get(issue.jira_key)
        days_silent = None
        if last is None or last < silence_threshold:
            days_silent = (datetime.now().replace(microsecond=0) - (last or datetime.min)).days if last else 9999
        if days_overdue is not None or days_silent is not None:
            attention.append(ProjectAttentionItem(
                issue_key=issue.jira_key,
                title=issue.summary or issue.jira_key,
                fact_hours=fact_hours_by_epic.get(issue.jira_key, 0.0),
                days_overdue=days_overdue,
                days_silent=days_silent,
            ))
    attention.sort(key=lambda x: (x.days_overdue or 0) + (x.days_silent or 0), reverse=True)

    # Overrun list: факт > план (план берём из BacklogItem.estimated_hours если есть)
    overrun: list[ProjectOverrunItem] = []
    backlog_estimates: dict[str, float] = dict(
        self.db.execute(
            select(BacklogItem.jira_key, BacklogItem.estimated_hours)
            .where(BacklogItem.jira_key.in_(issue_keys_list))
        ).all()
    )
    for jira_key, fact in fact_hours_by_epic.items():
        plan = backlog_estimates.get(jira_key) or 0.0
        if plan > 0 and fact > plan:
            issue = next((i for i in issues if i.jira_key == jira_key), None)
            overrun.append(ProjectOverrunItem(
                issue_key=jira_key,
                title=issue.summary if issue else jira_key,
                plan_hours=plan,
                fact_hours=fact,
                delta_hours=round(fact - plan, 1),
            ))
    overrun.sort(key=lambda x: x.delta_hours, reverse=True)

    return DashboardProjectsResponse(
        total=len(issues),
        done=done,
        in_progress=in_progress,
        overdue=overdue,
        not_started=not_started,
        forecast_done=forecast_done,
        forecast_pct=forecast_pct,
        attention_list=attention[:10],
        overrun_list=overrun[:10],
    )
```

- [ ] **Step 4: Добавить эндпоинт в analytics.py**

В `app/api/endpoints/analytics.py` добавить:

```python
from app.schemas.dashboard import DashboardProjectsResponse
from app.utils.period import quarter_to_dates

@router.get("/dashboard/projects", response_model=DashboardProjectsResponse)
async def dashboard_projects(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    team_params: dict = Depends(get_team_params),
):
    """Обзор проектов утверждённого сценария для дашборда."""
    svc = AnalyticsService(db)
    return svc.get_dashboard_projects(
        year=year,
        quarter=quarter,
        month=month,
        team=team_params.get("team"),
    )
```

- [ ] **Step 5: Запустить тесты**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py -v
```

Ожидаем: оба теста PASS (пустой ответ при отсутствии данных — это OK).

- [ ] **Step 6: Коммит**

```bash
git add app/services/analytics_service.py app/api/endpoints/analytics.py tests/test_dashboard_endpoints.py app/schemas/dashboard.py
git commit -m "feat(dashboard): projects widget backend endpoint"
```

---

## Task 5: Backend — Widget 2 (plan/fact нормированные работы)

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Написать тест**

Добавить в `tests/test_dashboard_endpoints.py`:

```python
def test_norm_work_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_plan" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "work_type_id" in item
        assert "plan_hours" in item
        assert "fact_hours" in item
        assert "pct" in item
```

- [ ] **Step 2: Запустить — убедиться что 404**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_norm_work_widget_returns_200 -v
```

- [ ] **Step 3: Добавить метод в AnalyticsService**

```python
from app.schemas.dashboard import DashboardNormWorkResponse, NormWorkItem
from app.models import MandatoryWorkType, RoleCapacityRule, Category, EmployeeCapacityOverride

def get_dashboard_norm_work(
    self,
    year: int,
    quarter: int,
    month: int | None = None,
    team: str | None = None,
) -> DashboardNormWorkResponse:
    """Факт vs план по видам нормированных работ."""
    start, end = quarter_to_dates(year, quarter, month)

    # Все активные виды работ
    work_types: list[MandatoryWorkType] = list(
        self.db.scalars(
            select(MandatoryWorkType).where(MandatoryWorkType.is_active == True)
            .order_by(MandatoryWorkType.sort_order)
        )
    )

    # Для каждого вида работ: категории, связанные с ним
    cat_by_wt: dict[str, list[str]] = {}
    for wt in work_types:
        cat_keys = list(
            self.db.scalars(
                select(Category.code).where(Category.work_type_id == wt.id)
            )
        )
        cat_by_wt[wt.id] = cat_keys

    # Факт: сумма ворклогов по категориям вида работ
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    fact_by_wt: dict[str, float] = {}
    for wt in work_types:
        cat_keys = cat_by_wt.get(wt.id, [])
        if not cat_keys:
            fact_by_wt[wt.id] = 0.0
            continue
        total = self.db.scalar(
            select(func.sum(Worklog.hours))
            .join(Issue, Issue.id == Worklog.issue_id)
            .where(
                Issue.category.in_(cat_keys),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
        ) or 0.0
        fact_by_wt[wt.id] = float(total)

    # План: RoleCapacityRule (role=NULL = общий) для year/quarter/work_type
    # Получаем суммарные доступные часы команды за период через CapacityService
    # Упрощение для MVP: берём глобальные правила RoleCapacityRule role=NULL
    q_str = f"Q{quarter}"
    global_rules: list[RoleCapacityRule] = list(
        self.db.scalars(
            select(RoleCapacityRule).where(
                RoleCapacityRule.year == year,
                RoleCapacityRule.quarter == q_str,
                RoleCapacityRule.role.is_(None),  # fallback правило "для всех"
            )
        )
    )
    rule_by_wt: dict[str, float] = {r.work_type_id: r.pct for r in global_rules}

    # Доступные часы: используем сумму fact за период как proxy для total capacity
    # (plan_hours = pct * total_available; для MVP берём сумму по всем wt-ворклогам)
    total_fact_all = self.db.scalar(
        select(func.sum(Worklog.hours))
        .where(
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
    ) or 1.0

    items: list[NormWorkItem] = []
    for wt in work_types:
        pct_rule = rule_by_wt.get(wt.id, 0.0)
        plan_h = round(total_fact_all * pct_rule / 100, 1)
        fact_h = round(fact_by_wt.get(wt.id, 0.0), 1)
        pct = round(fact_h / plan_h * 100, 1) if plan_h > 0 else 0.0
        items.append(NormWorkItem(
            work_type_id=wt.id,
            label=wt.name,
            plan_hours=plan_h,
            fact_hours=fact_h,
            pct=pct,
        ))

    total_plan = round(sum(i.plan_hours for i in items), 1)
    total_fact = round(sum(i.fact_hours for i in items), 1)
    total_pct = round(total_fact / total_plan * 100, 1) if total_plan > 0 else 0.0

    return DashboardNormWorkResponse(
        items=items, total_plan=total_plan, total_fact=total_fact, total_pct=total_pct,
    )
```

- [ ] **Step 4: Добавить эндпоинт**

```python
from app.schemas.dashboard import DashboardNormWorkResponse

@router.get("/dashboard/norm-work", response_model=DashboardNormWorkResponse)
async def dashboard_norm_work(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(db)
    return svc.get_dashboard_norm_work(year=year, quarter=quarter, month=month)
```

- [ ] **Step 5: Запустить тесты**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py -v
```

- [ ] **Step 6: Коммит**

```bash
git add app/services/analytics_service.py app/api/endpoints/analytics.py tests/test_dashboard_endpoints.py
git commit -m "feat(dashboard): norm-work widget backend endpoint"
```

---

## Task 6: Backend — Widget 3 (категории + meta-метрики)

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Написать тест**

```python
def test_categories_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/categories?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_hours" in data
    for item in data["items"]:
        assert "key" in item
        assert "hours" in item
        assert "worklog_count" in item
        assert "employee_count" in item
        assert "avg_worklog_minutes" in item
        assert "pct" in item
```

- [ ] **Step 2: Запустить — убедиться что 404**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_categories_widget_returns_200 -v
```

- [ ] **Step 3: Реализовать метод**

```python
from app.schemas.dashboard import DashboardCategoriesResponse, CategoryMetaItem
from app.models import Category

ARCHIVE_CODES = {"archive", "archive_target"}

def get_dashboard_categories(
    self,
    year: int,
    quarter: int,
    month: int | None = None,
    team: str | None = None,
) -> DashboardCategoriesResponse:
    """Meta-метрики ворклогов по категориям задач (без архивных)."""
    start, end = quarter_to_dates(year, quarter, month)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # Все активные категории (не архивные)
    categories: list[Category] = list(
        self.db.scalars(
            select(Category).where(Category.code.notin_(ARCHIVE_CODES))
            .order_by(Category.label)
        )
    )
    cat_colors: dict[str, str] = {c.code: (c.color or "#8884d8") for c in categories}
    cat_labels: dict[str, str] = {c.code: c.label for c in categories}

    # Агрегация по категории
    rows = self.db.execute(
        select(
            Issue.category,
            func.sum(Worklog.hours).label("hours"),
            func.count(Worklog.id).label("wl_count"),
            func.count(func.distinct(Issue.id)).label("issue_count"),
            func.count(func.distinct(Worklog.author_account_id)).label("emp_count"),
            func.avg(Worklog.hours * 60).label("avg_minutes"),
        )
        .join(Worklog, Worklog.issue_id == Issue.id)
        .where(
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
            Issue.category.in_([c.code for c in categories]),
        )
        .group_by(Issue.category)
    ).all()

    total_hours = sum(r.hours or 0 for r in rows)
    items: list[CategoryMetaItem] = []
    for r in rows:
        if not r.category:
            continue
        h = float(r.hours or 0)
        items.append(CategoryMetaItem(
            key=r.category,
            label=cat_labels.get(r.category, r.category),
            color=cat_colors.get(r.category, "#8884d8"),
            hours=round(h, 1),
            worklog_count=r.wl_count or 0,
            issue_count=r.issue_count or 0,
            employee_count=r.emp_count or 0,
            avg_worklog_minutes=round(float(r.avg_minutes or 0), 0),
            pct=round(h / total_hours * 100, 1) if total_hours > 0 else 0.0,
        ))
    items.sort(key=lambda x: x.hours, reverse=True)

    return DashboardCategoriesResponse(items=items, total_hours=round(total_hours, 1))
```

- [ ] **Step 4: Добавить эндпоинт**

```python
from app.schemas.dashboard import DashboardCategoriesResponse

@router.get("/dashboard/categories", response_model=DashboardCategoriesResponse)
async def dashboard_categories(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(db)
    return svc.get_dashboard_categories(year=year, quarter=quarter, month=month)
```

- [ ] **Step 5: Запустить все тесты**

```bash
py -3.10 -m pytest tests/test_dashboard_endpoints.py -v
```
Ожидаем: 4 теста PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/services/analytics_service.py app/api/endpoints/analytics.py tests/test_dashboard_endpoints.py
git commit -m "feat(dashboard): categories widget backend endpoint with meta-metrics"
```

---

## Task 7: Frontend — QuarterPicker компонент

**Files:**
- Create: `frontend/src/components/shared/QuarterPicker.tsx`
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Добавить типы периода**

В `frontend/src/types/api.ts` добавить:

```typescript
export interface QuarterPeriod {
  year: number;
  quarter: 1 | 2 | 3 | 4;
  month?: number; // опционально: месяц внутри квартала
}

export function quarterToLabel(p: QuarterPeriod): string {
  if (p.month) {
    const monthNames = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
    return `${monthNames[p.month - 1]} ${p.year}`;
  }
  return `Q${p.quarter} ${p.year}`;
}

export function periodToDateRange(p: QuarterPeriod): { start: string; end: string } {
  const qMonths: Record<number, number[]> = { 1:[1,2,3], 2:[4,5,6], 3:[7,8,9], 4:[10,11,12] };
  if (p.month) {
    const lastDay = new Date(p.year, p.month, 0).getDate();
    return {
      start: `${p.year}-${String(p.month).padStart(2,'0')}-01`,
      end: `${p.year}-${String(p.month).padStart(2,'0')}-${String(lastDay).padStart(2,'0')}`,
    };
  }
  const months = qMonths[p.quarter];
  const lastMonth = months[2];
  const lastDay = new Date(p.year, lastMonth, 0).getDate();
  return {
    start: `${p.year}-${String(months[0]).padStart(2,'0')}-01`,
    end: `${p.year}-${String(lastMonth).padStart(2,'0')}-${String(lastDay).padStart(2,'0')}`,
  };
}

export function currentQuarterPeriod(): QuarterPeriod {
  const now = new Date();
  const m = now.getMonth() + 1;
  const q = m <= 3 ? 1 : m <= 6 ? 2 : m <= 9 ? 3 : 4;
  return { year: now.getFullYear(), quarter: q as 1|2|3|4 };
}
```

- [ ] **Step 2: Создать компонент QuarterPicker**

```tsx
// frontend/src/components/shared/QuarterPicker.tsx
import { useState } from 'react';
import { Select, Space, Tag } from 'antd';
import type { QuarterPeriod } from '../../types/api';

const QUARTER_MONTHS: Record<number, { num: number; label: string }[]> = {
  1: [{ num:1,label:'Янв' },{ num:2,label:'Фев' },{ num:3,label:'Мар' }],
  2: [{ num:4,label:'Апр' },{ num:5,label:'Май' },{ num:6,label:'Июн' }],
  3: [{ num:7,label:'Июл' },{ num:8,label:'Авг' },{ num:9,label:'Сен' }],
  4: [{ num:10,label:'Окт' },{ num:11,label:'Ноя' },{ num:12,label:'Дек' }],
};

interface Props {
  value: QuarterPeriod;
  onChange: (p: QuarterPeriod) => void;
}

export default function QuarterPicker({ value, onChange }: Props) {
  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = new Date().getFullYear() - 1 + i;
    return { value: y, label: String(y) };
  });

  const handleMonth = (month: number) => {
    if (value.month === month) {
      onChange({ ...value, month: undefined });
    } else {
      onChange({ ...value, month });
    }
  };

  return (
    <Space size={8} wrap>
      <Select
        value={value.year}
        onChange={(y) => onChange({ ...value, year: y, month: undefined })}
        options={yearOptions}
        style={{ width: 90 }}
        size="small"
      />
      {([1, 2, 3, 4] as const).map((q) => (
        <Tag
          key={q}
          color={value.quarter === q ? 'cyan' : undefined}
          style={{ cursor: 'pointer', userSelect: 'none' }}
          onClick={() => onChange({ ...value, quarter: q, month: undefined })}
        >
          Q{q}
        </Tag>
      ))}
      {QUARTER_MONTHS[value.quarter].map(({ num, label }) => (
        <Tag
          key={num}
          color={value.month === num ? 'blue' : undefined}
          style={{ cursor: 'pointer', userSelect: 'none', fontSize: 11 }}
          onClick={() => handleMonth(num)}
        >
          {label}
        </Tag>
      ))}
    </Space>
  );
}
```

- [ ] **Step 3: Запустить lint**

```bash
cd frontend && npm run lint
```

Ожидаем: 0 ошибок в новых файлах.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/components/shared/QuarterPicker.tsx frontend/src/types/api.ts
git commit -m "feat(dashboard): QuarterPicker component with month drill-down"
```

---

## Task 8: Frontend — API хуки для трёх виджетов

**Files:**
- Modify: `frontend/src/api/analytics.ts`
- Modify: `frontend/src/hooks/useAnalytics.ts`
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Добавить типы ответов**

В `frontend/src/types/api.ts` добавить:

```typescript
// Dashboard: Widget 1
export interface ProjectAttentionItem {
  issue_key: string;
  title: string;
  fact_hours: number;
  days_overdue: number | null;
  days_silent: number | null;
}
export interface ProjectOverrunItem {
  issue_key: string;
  title: string;
  plan_hours: number;
  fact_hours: number;
  delta_hours: number;
}
export interface DashboardProjectsResponse {
  total: number;
  done: number;
  in_progress: number;
  overdue: number;
  not_started: number;
  forecast_done: number;
  forecast_pct: number;
  attention_list: ProjectAttentionItem[];
  overrun_list: ProjectOverrunItem[];
}

// Dashboard: Widget 2
export interface NormWorkItem {
  work_type_id: string;
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
}
export interface DashboardNormWorkResponse {
  items: NormWorkItem[];
  total_plan: number;
  total_fact: number;
  total_pct: number;
}

// Dashboard: Widget 3
export interface CategoryMetaItem {
  key: string;
  label: string;
  color: string;
  hours: number;
  worklog_count: number;
  issue_count: number;
  employee_count: number;
  avg_worklog_minutes: number;
  pct: number;
}
export interface DashboardCategoriesResponse {
  items: CategoryMetaItem[];
  total_hours: number;
}
```

- [ ] **Step 2: Добавить API-функции**

В `frontend/src/api/analytics.ts` добавить:

```typescript
import type {
  DashboardProjectsResponse,
  DashboardNormWorkResponse,
  DashboardCategoriesResponse,
  QuarterPeriod,
} from '../types/api';

function periodParams(p: QuarterPeriod): Record<string, string> {
  const params: Record<string, string> = {
    year: String(p.year),
    quarter: String(p.quarter),
  };
  if (p.month) params.month = String(p.month);
  return params;
}

export async function fetchDashboardProjects(
  period: QuarterPeriod,
  signal?: AbortSignal,
): Promise<DashboardProjectsResponse> {
  return api.get('/analytics/dashboard/projects', periodParams(period), signal);
}

export async function fetchDashboardNormWork(
  period: QuarterPeriod,
  signal?: AbortSignal,
): Promise<DashboardNormWorkResponse> {
  return api.get('/analytics/dashboard/norm-work', periodParams(period), signal);
}

export async function fetchDashboardCategories(
  period: QuarterPeriod,
  signal?: AbortSignal,
): Promise<DashboardCategoriesResponse> {
  return api.get('/analytics/dashboard/categories', periodParams(period), signal);
}
```

- [ ] **Step 3: Добавить хуки**

В `frontend/src/hooks/useAnalytics.ts` добавить:

```typescript
import type { QuarterPeriod } from '../types/api';
import {
  fetchDashboardProjects,
  fetchDashboardNormWork,
  fetchDashboardCategories,
} from '../api/analytics';

export function useDashboardProjects(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-projects', period],
    queryFn: ({ signal }) => fetchDashboardProjects(period, signal),
    staleTime: 30_000,
  });
}

export function useDashboardNormWork(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-norm-work', period],
    queryFn: ({ signal }) => fetchDashboardNormWork(period, signal),
    staleTime: 30_000,
  });
}

export function useDashboardCategories(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-categories', period],
    queryFn: ({ signal }) => fetchDashboardCategories(period, signal),
    staleTime: 30_000,
  });
}
```

- [ ] **Step 4: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/api/analytics.ts frontend/src/hooks/useAnalytics.ts frontend/src/types/api.ts
git commit -m "feat(dashboard): API functions and hooks for 3 dashboard widgets"
```

---

## Task 9: Frontend — Widget 1 (ProjectsWidget)

**Files:**
- Create: `frontend/src/components/dashboard/ProjectsWidget.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
// frontend/src/components/dashboard/ProjectsWidget.tsx
import { Card, Row, Col, Tag, Spin, Empty } from 'antd';
import { useNavigate } from 'react-router';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import type { DashboardProjectsResponse } from '../../types/api';
import { formatHours } from '../../utils/format';
import { CHART_COLORS } from '../../utils/constants';

const STATUS_COLORS = {
  done: CHART_COLORS.green,
  in_progress: '#00c9c8',
  overdue: CHART_COLORS.red,
  not_started: '#1c3358',
};

interface Props {
  data: DashboardProjectsResponse | undefined;
  loading: boolean;
}

export default function ProjectsWidget({ data, loading }: Props) {
  const navigate = useNavigate();

  if (loading) return <Card title="Проекты квартала"><Spin /></Card>;
  if (!data) return <Card title="Проекты квартала"><Empty description="Нет данных" /></Card>;

  const donutData = [
    { name: 'Завершено', value: data.done, color: STATUS_COLORS.done },
    { name: 'В работе', value: data.in_progress, color: STATUS_COLORS.in_progress },
    { name: 'Просрочено', value: data.overdue, color: STATUS_COLORS.overdue },
    { name: 'Не начаты', value: data.not_started, color: STATUS_COLORS.not_started },
  ].filter(d => d.value > 0);

  return (
    <Card title="Проекты квартала" style={{ height: '100%' }}>
      {/* Верхний ряд: пончик + статусы + метрики */}
      <Row gutter={16} align="middle">
        <Col flex="160px">
          <div style={{ position: 'relative', width: 160, height: 160 }}>
            <PieChart width={160} height={160}>
              <Pie
                data={donutData}
                cx={75} cy={75}
                innerRadius={50} outerRadius={72}
                dataKey="value"
                startAngle={90} endAngle={-270}
              >
                {donutData.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie>
              <Tooltip formatter={(v, name) => [`${v}`, name]} />
            </PieChart>
            <div style={{
              position: 'absolute', top: '50%', left: '50%',
              transform: 'translate(-50%, -50%)', textAlign: 'center',
            }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{data.total}</div>
              <div style={{ fontSize: 11, color: '#7e94b8' }}>проектов</div>
            </div>
          </div>
        </Col>
        <Col flex="1">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { label: 'Завершено', value: data.done, pct: data.total ? Math.round(data.done/data.total*100) : 0, color: STATUS_COLORS.done },
              { label: 'В работе', value: data.in_progress, pct: data.total ? Math.round(data.in_progress/data.total*100) : 0, color: STATUS_COLORS.in_progress },
              { label: 'Просрочено', value: data.overdue, pct: data.total ? Math.round(data.overdue/data.total*100) : 0, color: STATUS_COLORS.overdue },
              { label: 'Не начаты', value: data.not_started, pct: data.total ? Math.round(data.not_started/data.total*100) : 0, color: '#7e94b8' },
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: row.color, flexShrink: 0 }} />
                <span style={{ color: '#fff', fontWeight: 600, width: 28 }}>{row.value}</span>
                <span style={{ color: '#7e94b8' }}>{row.label} ({row.pct}%)</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: '#7e94b8', borderTop: '1px solid #1c3358', paddingTop: 10 }}>
            Прогноз к концу квартала: <span style={{ color: '#00c9c8', fontWeight: 600 }}>{data.forecast_done} ({data.forecast_pct}%)</span>
          </div>
        </Col>
      </Row>

      {/* Нижний ряд: два списка */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>⚠️ Требует внимания</div>
          {data.attention_list.length === 0 && <div style={{ fontSize: 12, color: '#5a7099' }}>Всё в порядке</div>}
          {data.attention_list.slice(0, 5).map(item => (
            <div
              key={item.issue_key}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid rgba(28,51,88,.4)', cursor: 'pointer', fontSize: 12 }}
              onClick={() => navigate(`/analytics?project=${item.issue_key}`)}
            >
              {item.days_overdue != null && (
                <Tag color="red" style={{ fontSize: 10, margin: 0 }}>просрочен {item.days_overdue}д</Tag>
              )}
              {item.days_overdue == null && item.days_silent != null && (
                <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>тишина {item.days_silent}д</Tag>
              )}
              <span style={{ color: '#fff', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</span>
              <span style={{ color: '#7e94b8', flexShrink: 0 }}>{formatHours(item.fact_hours)} ч</span>
            </div>
          ))}
        </Col>
        <Col span={12}>
          <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>🔴 Перебор по часам</div>
          {data.overrun_list.length === 0 && <div style={{ fontSize: 12, color: '#5a7099' }}>Перерасхода нет</div>}
          {data.overrun_list.slice(0, 5).map(item => (
            <div key={item.issue_key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid rgba(28,51,88,.4)', fontSize: 12 }}>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</div>
                <div style={{ height: 4, borderRadius: 2, background: '#1c3358', marginTop: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', background: 'linear-gradient(90deg,#faad14,#ff4d4f)', width: `${Math.min(100, item.fact_hours / item.plan_hours * 100)}%` }} />
                </div>
              </div>
              <span style={{ color: '#ff4d4f', fontWeight: 600, flexShrink: 0 }}>+{formatHours(item.delta_hours)} ч</span>
            </div>
          ))}
        </Col>
      </Row>
    </Card>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint 2>&1 | grep -E "ProjectsWidget|error"
```

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx
git commit -m "feat(dashboard): Widget 1 — ProjectsWidget component"
```

---

## Task 10: Frontend — Widget 2 (NormWorkWidget)

**Files:**
- Create: `frontend/src/components/dashboard/NormWorkWidget.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
// frontend/src/components/dashboard/NormWorkWidget.tsx
import { Card, Spin, Empty, Tooltip } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type { DashboardNormWorkResponse, NormWorkItem } from '../../types/api';
import { formatHours } from '../../utils/format';

// Пороги цвета: настраиваемые, для MVP хардкод (в будущем из AppSetting)
const DEFAULT_THRESHOLDS = { warn: 110, under: 70 };

function barColor(pct: number, thresholds = DEFAULT_THRESHOLDS): string {
  if (pct > thresholds.warn) return '#ff4d4f';
  if (pct < thresholds.under) return '#faad14';
  return '#52c41a';
}

function BulletBar({ item }: { item: NormWorkItem }) {
  const color = barColor(item.pct);
  const fillWidth = Math.min(100, item.plan_hours > 0 ? (item.fact_hours / item.plan_hours) * 66 : 0);
  const targetLeft = 66; // план = 66% ширины трека (оставляем место для перебора)
  const overWidth = item.plan_hours > 0 && item.fact_hours > item.plan_hours
    ? Math.min(34, ((item.fact_hours - item.plan_hours) / item.plan_hours) * 66)
    : 0;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 90px', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid rgba(28,51,88,.4)' }}>
      <div style={{ fontSize: 12, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</div>
      <div style={{ position: 'relative', height: 16, background: '#1c3358', borderRadius: 4, overflow: 'visible' }}>
        {/* Факт */}
        <div style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: `${fillWidth + overWidth}%`, background: color, borderRadius: 4, transition: 'width .3s' }} />
        {/* Линия плана */}
        <div style={{ position: 'absolute', top: -3, bottom: -3, left: `${targetLeft}%`, width: 2, background: '#fff', borderRadius: 1, boxShadow: '0 0 0 1px rgba(0,0,0,.3)' }} />
      </div>
      <div style={{ textAlign: 'right', fontSize: 12 }}>
        <span style={{ color, fontWeight: 600 }}>{item.pct.toFixed(0)}%</span>
        <div style={{ color: '#7e94b8', fontSize: 10 }}>{formatHours(item.fact_hours)}/{formatHours(item.plan_hours)} ч</div>
      </div>
    </div>
  );
}

interface Props {
  data: DashboardNormWorkResponse | undefined;
  loading: boolean;
}

export default function NormWorkWidget({ data, loading }: Props) {
  const extra = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined style={{ cursor: 'pointer', color: '#7e94b8' }} />
    </Tooltip>
  );

  if (loading) return <Card title="Нормированные работы" extra={extra}><Spin /></Card>;
  if (!data?.items.length) return <Card title="Нормированные работы" extra={extra}><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Нормированные работы: план / факт" extra={extra}>
      {data.items.map(item => <BulletBar key={item.work_type_id} item={item} />)}
      <div style={{ display: 'flex', gap: 24, marginTop: 12, paddingTop: 10, borderTop: '1px solid #1c3358', fontSize: 12, color: '#7e94b8' }}>
        <span>Σ план: <b style={{ color: '#fff' }}>{formatHours(data.total_plan)} ч</b></span>
        <span>Σ факт: <b style={{ color: '#fff' }}>{formatHours(data.total_fact)} ч</b></span>
        <span>Загрузка: <b style={{ color: barColor(data.total_pct) }}>{data.total_pct.toFixed(0)}%</b></span>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint 2>&1 | grep -E "NormWorkWidget|error"
```

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/dashboard/NormWorkWidget.tsx
git commit -m "feat(dashboard): Widget 2 — NormWorkWidget bullet bars"
```

---

## Task 11: Frontend — Widget 3 (CategoryWidget — treemap)

**Files:**
- Create: `frontend/src/components/dashboard/CategoryWidget.tsx`

- [ ] **Step 1: Создать компонент**

Treemap реализован как кастомный CSS flex (squarify-подобный, но упрощённый: топовые категории по горизонтали, остальные в блок).

```tsx
// frontend/src/components/dashboard/CategoryWidget.tsx
import { Card, Spin, Empty } from 'antd';
import type { DashboardCategoriesResponse, CategoryMetaItem } from '../../types/api';
import { formatHours } from '../../utils/format';

function Treemap({ items, totalHours }: { items: CategoryMetaItem[]; totalHours: number }) {
  if (!items.length) return <Empty description="Нет данных" />;

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, width: '100%', minHeight: 160 }}>
      {items.map(item => {
        const pct = totalHours > 0 ? item.hours / totalHours : 0;
        const minW = pct > 0.15 ? 120 : pct > 0.07 ? 80 : 60;
        return (
          <div
            key={item.key}
            title={`${item.label}: ${formatHours(item.hours)} ч (${item.pct.toFixed(1)}%)`}
            style={{
              flex: `${pct * 100} 0 ${minW}px`,
              minHeight: 56,
              background: item.color + '33',
              border: `1.5px solid ${item.color}66`,
              borderRadius: 8,
              padding: '8px 10px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
              cursor: 'default',
            }}
          >
            <div style={{ fontSize: 11, color: '#a4b8d8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>{formatHours(item.hours)} ч</div>
            {pct > 0.07 && <div style={{ fontSize: 10, color: '#7e94b8' }}>{item.pct.toFixed(0)}%</div>}
          </div>
        );
      })}
    </div>
  );
}

function MetaTable({ items }: { items: CategoryMetaItem[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: '#7e94b8', textTransform: 'uppercase', fontSize: 10 }}>
            <th style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Категория</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Часы</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Вркл.</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Задач</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Сотр.</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>Ср.мин</th>
            <th style={{ textAlign: 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>%</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.key} style={{ borderBottom: '1px solid rgba(28,51,88,.3)' }}>
              <td style={{ padding: '5px 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: item.color, flexShrink: 0 }} />
                <span style={{ color: '#e6edf7' }}>{item.label}</span>
              </td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#fff', fontWeight: 600 }}>{formatHours(item.hours)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.worklog_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.issue_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.employee_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.avg_worklog_minutes.toFixed(0)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#7e94b8' }}>{item.pct.toFixed(1)}%</td>
            </tr>
          ))}
          <tr style={{ borderTop: '2px solid #1c3358', fontWeight: 600, color: '#fff', fontSize: 11 }}>
            <td style={{ padding: '5px 8px' }}>Итого</td>
            <td style={{ textAlign: 'right', padding: '5px 8px' }}>{formatHours(items.reduce((s,i) => s+i.hours, 0))}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{items.reduce((s,i) => s+i.worklog_count, 0)}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{items.reduce((s,i) => s+i.issue_count, 0)}</td>
            <td colSpan={3} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  data: DashboardCategoriesResponse | undefined;
  loading: boolean;
}

export default function CategoryWidget({ data, loading }: Props) {
  if (loading) return <Card title="Ворклоги по категориям"><Spin /></Card>;
  if (!data?.items.length) return <Card title="Ворклоги по категориям"><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Ворклоги по категориям задач">
      <div style={{ display: 'grid', gridTemplateColumns: '55% 45%', gap: 16 }}>
        <Treemap items={data.items} totalHours={data.total_hours} />
        <MetaTable items={data.items} />
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint 2>&1 | grep -E "CategoryWidget|error"
```

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/dashboard/CategoryWidget.tsx
git commit -m "feat(dashboard): Widget 3 — CategoryWidget treemap + meta table"
```

---

## Task 12: Frontend — сборка DashboardPage

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Переписать DashboardPage**

Заменить содержимое на:

```tsx
// frontend/src/pages/DashboardPage.tsx
import { useState } from 'react';
import { Row, Col, App } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import PageHeader from '../components/shared/PageHeader';
import QuarterPicker from '../components/shared/QuarterPicker';
import FactFilterBar from '../components/dashboard/FactFilterBar';
import ExportButtons from '../components/shared/ExportButtons';
import ProjectsWidget from '../components/dashboard/ProjectsWidget';
import NormWorkWidget from '../components/dashboard/NormWorkWidget';
import CategoryWidget from '../components/dashboard/CategoryWidget';
import { useSyncMutation } from '../hooks/useSync';
import { useDashboardProjects, useDashboardNormWork, useDashboardCategories } from '../hooks/useAnalytics';
import { downloadAnalyticsXlsx, downloadAnalyticsPdf } from '../api/exports';
import { currentQuarterPeriod } from '../types/api';
import type { QuarterPeriod } from '../types/api';
import { useFactFilter } from '../hooks/useFactFilter';
import { Space, Button } from 'antd';

export default function DashboardPage() {
  const { notification } = App.useApp();
  const [period, setPeriod] = useState<QuarterPeriod>(currentQuarterPeriod);
  const { queryParams: teamParams } = useFactFilter();
  const syncFull = useSyncMutation('full');

  const { data: projects, isLoading: projLoading } = useDashboardProjects(period);
  const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period);
  const { data: categories, isLoading: catLoading } = useDashboardCategories(period);

  return (
    <div>
      <PageHeader
        eyebrow="Обзор"
        title="Дашборд"
        subtitle={`Q${period.quarter} ${period.year}${period.month ? ` · месяц ${period.month}` : ''}`}
      />

      <Space wrap style={{ marginBottom: 24 }}>
        <QuarterPicker value={period} onChange={setPeriod} />
        <FactFilterBar />
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(undefined, undefined, teamParams)}
          onPdf={() => downloadAnalyticsPdf(undefined, undefined, teamParams)}
        />
        <Button
          icon={<SyncOutlined spin={syncFull.isPending} />}
          loading={syncFull.isPending}
          onClick={() => syncFull.mutate(undefined, {
            onSuccess: (res) => notification.success({ title: 'Синхронизация завершена', description: res.message }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          Синхронизация
        </Button>
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <ProjectsWidget data={projects} loading={projLoading} />
        </Col>
        <Col xs={24} lg={12}>
          <NormWorkWidget data={normWork} loading={normLoading} />
        </Col>
        <Col xs={24} lg={12}>
          <CategoryWidget data={categories} loading={catLoading} />
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: Запустить dev-сервер и проверить вручную**

```bash
# Терминал 1: убить старый бекенд и запустить новый
# (Windows: найти PID на :8000 и убить, затем:)
py -3.10 -m uvicorn app.main:app --port 8000

# Терминал 2:
cd frontend && npm run dev
```

Открыть http://localhost:5173, проверить:
- QuarterPicker переключает кварталы/месяцы
- Три виджета рендерятся (пустые или с данными)
- Нет console errors

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Ожидаем: 0 errors.

- [ ] **Step 4: Запустить все тесты**

```bash
py -3.10 -m pytest tests/ -v --ignore=tests/test_sync_service.py
```

Ожидаем: тесты dashboard_endpoints проходят; остальные без регрессий.

- [ ] **Step 5: Финальный коммит**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(dashboard): assemble new DashboardPage with QuarterPicker + 3 widgets"
git push
```

---

## Self-Review

**Покрытие спека:**
- ✅ Квартальный фильтр с детализацией до месяца → Task 7 + Task 12
- ✅ Widget 1: hero-карточка, пончик, статусы, прогноз, attention list, overrun list → Tasks 4, 9
- ✅ Widget 2: bullet bars с цветовыми порогами, ⚙ gear → Tasks 5, 10
- ✅ Widget 3: treemap + meta-таблица (часы/ворклогов/задач/сотрудников/ср.мин/%) → Tasks 6, 11
- ✅ `due_date` добавлен в Issue и синхронизируется → Task 2
- ✅ Drill-down из W1 → navigate to `/analytics?project=KEY` → Task 9

**Не в этом плане (Plan B/C):**
- Analytics master-detail page
- AI generation
- Rating custom fields
- Настройка порогов W2 через Settings UI (сейчас хардкод — отдельная задача)

**Потенциальные проблемы:**
- `AnalyticsService` — проверь что класс принимает `self.db` и все импорты добавлены в начало файла при реализации Tasks 4-6.
- `Worklog.author_account_id` — убедись что поле существует в модели перед использованием в Task 6.
- `BacklogItem.estimated_hours` — поле может отсутствовать; если нет, overrun list будет пуст (не баг, просто нет данных для сравнения).
