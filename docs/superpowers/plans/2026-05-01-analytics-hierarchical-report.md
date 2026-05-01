# Hierarchical Analytics Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить старую страницу `/analytics` на единый иерархический отчёт (Команда → Роль → Сотрудник → Вид работ → Категория → Задача → ворклоги) с master-detail layout, drill-down с виджетов дашборда, глобальным пикером периода в шапке и настройкой видимости колонок per-user.

**Architecture:** 4 фазы. (1) Backend агрегация: один эндпоинт строит дерево из `worklogs JOIN issues + employee_teams + categories + mandatory_work_types`, второй эндпоинт ленивая выгрузка ворклогов задачи. (2) Глобальный пикер периода в шапке + поле `User.selected_period`, локальный override на странице. (3) Новая страница AnalyticsPage с master-detail layout (вариант C) + виртуализированная иерархическая таблица + фильтры + настройка колонок + переключатель ворклогов inline/drawer + xlsx-экспорт. (4) Drill-down с виджетов NormWork и CategoryWidget через URL query params + удаление старого кода.

**Tech Stack:** Python 3.10, SQLAlchemy 2.0, FastAPI, Alembic, pytest. Frontend: React 19 + TS 6 + AntD 6 + TanStack Query + react-window (для виртуализации). Реализация — на main, без worktree (см. user memory `feedback_subagent_flow`).

**Спек:** [docs/superpowers/specs/2026-05-01-analytics-hierarchical-report-design.md](../specs/2026-05-01-analytics-hierarchical-report-design.md)

---

## File Structure

**Backend:**
- Modify: `app/models/user.py` — добавить `selected_period_raw` (JSON: year/quarter/month) и `analytics_columns_raw` (JSON list of visible column codes)
- Create: `alembic/versions/<rev>_add_user_selected_period_and_analytics_columns.py`
- Create: `app/schemas/analytics_report.py` — pydantic schemas для дерева
- Modify: `app/services/analytics_service.py` — новый метод `get_hierarchical_report` + `get_issue_worklogs`
- Modify: `app/api/endpoints/analytics.py` — новые роуты `/report`, `/report/issue/{id}/worklogs`, `/report/export.xlsx`. Удалить старые: `hours-by-{employee|project|category|period}`, `context-switching`
- Modify: `app/api/endpoints/users.py` — добавить `GET/PUT /users/me/period`, `GET/PUT /users/me/analytics-columns`
- Modify: `app/services/export_service.py` — добавить `export_analytics_report_xlsx`
- Create: `tests/test_analytics_report.py` — интеграционные

**Frontend:**
- Create: `frontend/src/hooks/useGlobalPeriod.ts` (контекст)
- Create: `frontend/src/components/shared/GlobalPeriodPicker.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx` (или там, где сейчас рендерится TeamFilter pill) — добавить `GlobalPeriodPicker`
- Modify: `frontend/src/App.tsx` — обернуть в `GlobalPeriodFilterProvider`
- Modify: `frontend/src/hooks/useDashboardWidgets.ts` (или эквивалент) — читать период из `useGlobalPeriod`
- Modify: `frontend/src/pages/CapacityPage.tsx` — читать период из `useGlobalPeriod` (с локальным override)
- Create: `frontend/src/api/analyticsReport.ts` — fetch методы
- Create: `frontend/src/hooks/useAnalyticsReport.ts`
- Create: `frontend/src/hooks/useIssueWorklogs.ts`
- Create: `frontend/src/hooks/useAnalyticsColumns.ts`
- Create: `frontend/src/pages/AnalyticsPage.tsx` (полная замена существующей)
- Create: `frontend/src/components/analytics/AnalyticsTeamList.tsx`
- Create: `frontend/src/components/analytics/AnalyticsTable.tsx`
- Create: `frontend/src/components/analytics/AnalyticsFilters.tsx`
- Create: `frontend/src/components/analytics/AnalyticsColumnSettings.tsx`
- Create: `frontend/src/components/analytics/AnalyticsWorklogsBlock.tsx`
- Modify: `frontend/src/components/dashboard/NormWorkWidget.tsx` — кликабельные строки + навигация
- Modify: `frontend/src/components/dashboard/CategoryWidget.tsx` — кликабельные плитки + карточки

**Удаления:**
- `frontend/src/hooks/useAnalytics.ts` (старые хуки)
- Старая `AnalyticsPage.tsx` (заменяется новой)
- Старые методы в `frontend/src/api/analytics.ts` (по `hours-by-*` и `context-switching`)
- Старые методы в `app/services/analytics_service.py` (`get_hours_by_*`, `get_context_switching`)
- Старые тесты этих эндпоинтов

**Зависимости (npm):**
- `react-window` (если ещё не установлен)

---

# Фаза 1 — Backend: иерархический отчёт

### Task 1: Pydantic-схемы для дерева отчёта

**Files:**
- Create: `app/schemas/analytics_report.py`

- [ ] **Step 1: Создать файл с типами**

```python
"""Pydantic-схемы иерархического отчёта Аналитики."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NodeTotals(BaseModel):
    fact_hours: float
    plan_hours: Optional[float] = None
    pct_plan: Optional[float] = None
    pct_total: float
    worklog_count: int
    issue_count: int
    employee_count: int
    avg_worklog_minutes: float


class AnalyticsIssueNode(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    issue_type: str
    category: Optional[str] = None
    last_worklog_at: Optional[datetime] = None
    assignee_name: Optional[str] = None
    totals: NodeTotals


class AnalyticsCategoryNode(BaseModel):
    category_code: Optional[str] = None
    label: str
    color: str
    totals: NodeTotals
    issues: list[AnalyticsIssueNode]


class AnalyticsWorkTypeNode(BaseModel):
    work_type_id: str
    label: str
    totals: NodeTotals
    categories: list[AnalyticsCategoryNode]


class AnalyticsEmployeeNode(BaseModel):
    employee_id: str
    name: str
    initials: str
    totals: NodeTotals
    work_types: list[AnalyticsWorkTypeNode]


class AnalyticsRoleNode(BaseModel):
    role_code: Optional[str] = None
    role_label: str
    role_color: str
    totals: NodeTotals
    employees: list[AnalyticsEmployeeNode]


class AnalyticsTeamNode(BaseModel):
    team: Optional[str] = None
    totals: NodeTotals
    roles: list[AnalyticsRoleNode]


class AnalyticsReportResponse(BaseModel):
    teams: list[AnalyticsTeamNode]
    grand_totals: NodeTotals


class IssueWorklogItem(BaseModel):
    worklog_id: str
    started_at: datetime
    hours: float
    employee_name: str
    comment: Optional[str] = None
```

- [ ] **Step 2: Импортировать в `__init__.py` (если нужен namespace)**

В `app/schemas/__init__.py` (если он есть и существующие схемы там реэкспортятся) добавить:

```python
from app.schemas.analytics_report import (  # noqa: F401
    AnalyticsReportResponse,
    AnalyticsTeamNode,
    AnalyticsRoleNode,
    AnalyticsEmployeeNode,
    AnalyticsWorkTypeNode,
    AnalyticsCategoryNode,
    AnalyticsIssueNode,
    NodeTotals,
    IssueWorklogItem,
)
```

(Если `__init__.py` не реэкспортит — пропустить шаг.)

- [ ] **Step 3: Commit**

```bash
git add app/schemas/analytics_report.py app/schemas/__init__.py
git commit -m "feat(analytics): pydantic schemas for hierarchical report"
```

---

### Task 2: Сервис get_hierarchical_report — базовая агрегация

**Files:**
- Modify: `app/services/analytics_service.py`
- Create: `tests/test_analytics_report.py`

- [ ] **Step 1: Создать тест-каркас**

В `tests/test_analytics_report.py`:

```python
"""Hierarchical /analytics/report endpoint."""
from datetime import datetime
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import (
    Category, Employee, EmployeeTeam, Issue, MandatoryWorkType,
    Project, Role, Worklog,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_minimal(db):
    wt_support = MandatoryWorkType(
        id=str(uuid.uuid4()), code="support_consult",
        label="Сопровождение и консультация",
        is_active=True, sort_order=1, subtracts_from_pool=True, is_system=True,
    )
    wt_other = MandatoryWorkType(
        id=str(uuid.uuid4()), code="other_foreign", label="Прочие / Чужие задачи",
        is_active=True, sort_order=99, subtracts_from_pool=False, is_system=True,
    )
    db.add_all([wt_support, wt_other])
    db.flush()
    db.add(Category(
        id=str(uuid.uuid4()), code="support_consultation",
        label="Сопровождение", sort_order=0, work_type_id=wt_support.id, color="#0bc"
    ))
    db.add(Role(
        id=str(uuid.uuid4()), code="developer", label="Программист",
        color="#0c8", sort_order=0, is_active=True,
    ))
    db.commit()


def _seed_emp(db, name, team, role="developer"):
    emp = Employee(
        id=str(uuid.uuid4()), jira_account_id=f"acc-{uuid.uuid4()}",
        display_name=name, is_active=True, role=role,
    )
    db.add(emp); db.flush()
    db.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team=team, is_primary=True,
    ))
    db.commit()
    return emp


def _seed_issue(db, project, key, team, category, summary="t"):
    i = Issue(
        id=str(uuid.uuid4()), jira_issue_id=f"ji-{uuid.uuid4()}",
        key=key, summary=summary, issue_type="Задача",
        status="In Progress", status_category="indeterminate",
        project_id=project.id, category=category, team=team,
        participating_teams=json.dumps([]),
    )
    db.add(i); db.commit()
    return i


def _seed_project(db):
    p = Project(id=str(uuid.uuid4()), jira_project_id="10000",
                key="TEST", name="Test", is_active=True)
    db.add(p); db.commit()
    return p


def _seed_worklog(db, issue, emp, hours, day=15):
    db.add(Worklog(
        id=str(uuid.uuid4()), jira_worklog_id=f"wl-{uuid.uuid4()}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, day, 10, 0, 0),
        time_spent_seconds=int(hours * 3600), hours=hours,
    ))
    db.commit()


def test_report_returns_team_role_employee_tree(db_session, client):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 4.0)

    resp = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["teams"]) == 1
    team_node = data["teams"][0]
    assert team_node["team"] == "Команда A"
    assert team_node["totals"]["fact_hours"] == 4.0
    role = team_node["roles"][0]
    assert role["role_code"] == "developer"
    emp_node = role["employees"][0]
    assert emp_node["name"] == "Тест Тест"
    wt = emp_node["work_types"][0]
    assert wt["label"] == "Сопровождение и консультация"
    cat = wt["categories"][0]
    assert cat["category_code"] == "support_consultation"
    issue_node = cat["issues"][0]
    assert issue_node["key"] == "T-1"
    assert issue_node["totals"]["fact_hours"] == 4.0
    assert data["grand_totals"]["fact_hours"] == 4.0
```

- [ ] **Step 2: Запустить — тест должен упасть (404)**

Run: `py -3.10 -m pytest tests/test_analytics_report.py::test_report_returns_team_role_employee_tree -v`

Expected: FAIL — endpoint не существует.

- [ ] **Step 3: Реализовать `AnalyticsService.get_hierarchical_report` (базовая агрегация без фильтров)**

В `app/services/analytics_service.py` после метода `get_dashboard_norm_work` добавить:

```python
    def get_hierarchical_report(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        teams: Optional[list[str]] = None,
        employee_id: Optional[str] = None,
        task_query: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
        category_codes: Optional[list[str]] = None,
    ) -> AnalyticsReportResponse:
        """Иерархический отчёт: Команда → Роль → Сотрудник → ВидРабот → Категория → Задача."""
        from app.schemas.analytics_report import (
            AnalyticsReportResponse, AnalyticsTeamNode, AnalyticsRoleNode,
            AnalyticsEmployeeNode, AnalyticsWorkTypeNode, AnalyticsCategoryNode,
            AnalyticsIssueNode, NodeTotals,
        )
        from app.models.employee_team import EmployeeTeam

        # 1. Период (приоритет start_date/end_date > month > quarter)
        if start_date and end_date:
            period_start, period_end = start_date, end_date
        else:
            period_start, period_end = quarter_to_dates(year, quarter, month)
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())

        # 2. Справочники
        work_types: list[MandatoryWorkType] = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .order_by(MandatoryWorkType.sort_order)
            .all()
        )
        wt_by_id = {wt.id: wt for wt in work_types}
        other_foreign_wt = next((wt for wt in work_types if wt.code == "other_foreign"), None)

        cat_rows = (
            self.db.query(Category.code, Category.work_type_id, Category.label, Category.color)
            .all()
        )
        cat_meta: dict[str, tuple[str, str, str | None]] = {
            r.code: (r.label, r.color or "#7e94b8", r.work_type_id) for r in cat_rows
        }
        code_to_wt = {code: meta[2] for code, meta in cat_meta.items() if meta[2]}

        roles_db = self.db.query(Role).filter(Role.is_active.is_(True)).order_by(Role.sort_order).all()
        role_by_code = {r.code: r for r in roles_db}

        ORPHAN_WT_ID = "__unmapped__"
        ORPHAN_WT_LABEL = "Не указана категория/вид работ"
        ORPHAN_CAT_CODE = None
        ORPHAN_CAT_LABEL = "Без категории"

        # 3. Сотрудники + primary team
        emp_query = self.db.query(Employee).filter(Employee.is_active.is_(True))
        if employee_id:
            emp_query = emp_query.filter(Employee.id == employee_id)
        all_employees: list[Employee] = emp_query.all()

        emp_team_rows = (
            self.db.query(EmployeeTeam.employee_id, EmployeeTeam.team)
            .filter(
                EmployeeTeam.employee_id.in_([e.id for e in all_employees]),
                EmployeeTeam.is_primary.is_(True),
            )
            .all()
        )
        emp_team_by_id: dict[str, str] = {r.employee_id: r.team for r in emp_team_rows}

        # team filter — оставляем только сотрудников чья primary team подходит
        if teams:
            team_set = set(teams)
            employees = [e for e in all_employees if emp_team_by_id.get(e.id) in team_set]
        else:
            employees = all_employees

        if not employees:
            return AnalyticsReportResponse(
                teams=[],
                grand_totals=_empty_totals(),
            )

        # 4. Ворклоги за период с агрегацией по emp×issue
        wl_q = (
            self.db.query(
                Worklog.employee_id,
                Worklog.issue_id,
                Issue.key,
                Issue.summary,
                Issue.status,
                Issue.status_category,
                Issue.issue_type,
                Issue.category,
                Issue.team,
                Issue.participating_teams,
                Issue.assignee_name if hasattr(Issue, "assignee_name") else None,
                func.sum(Worklog.time_spent_seconds).label("secs"),
                func.count(Worklog.id).label("wl_count"),
                func.max(Worklog.started_at).label("last_at"),
            )
            .join(Issue, Issue.id == Worklog.issue_id)
            .filter(
                Worklog.employee_id.in_([e.id for e in employees]),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
        )
        if task_query:
            q = f"%{task_query}%"
            wl_q = wl_q.filter(or_(Issue.key.ilike(q), Issue.summary.ilike(q)))
        wl_q = wl_q.group_by(
            Worklog.employee_id, Worklog.issue_id, Issue.key, Issue.summary,
            Issue.status, Issue.status_category, Issue.issue_type, Issue.category,
            Issue.team, Issue.participating_teams,
        )
        wl_rows = wl_q.all()

        # 5. Бакетируем строки по (team, role, emp, wt_id, cat_code, issue)
        # team = emp_primary_team; cross-team → other_foreign work_type
        # cat_code → wt_id; cat_code without mapping → orphan
        bucket: dict[tuple, dict] = {}  # key=(team, role, emp_id, wt_id, cat_code, issue_id) → fields

        for row in wl_rows:
            emp_id = row.employee_id
            issue_id = row.issue_id
            cat_code = row.category
            issue_team = row.team
            parts_json = row.participating_teams
            secs = row.secs or 0
            wl_count = row.wl_count or 0
            last_at = row.last_at
            h = secs / 3600.0

            emp = next((e for e in employees if e.id == emp_id), None)
            if emp is None:
                continue
            emp_team = emp_team_by_id.get(emp_id)

            # Cross-team routing
            is_foreign = False
            if emp_team:
                parts = []
                if parts_json:
                    try:
                        decoded = json.loads(parts_json)
                        parts = [p for p in decoded if isinstance(p, str)] if isinstance(decoded, list) else []
                    except ValueError:
                        pass
                if not issue_team:
                    is_foreign = True
                elif issue_team == emp_team or emp_team in parts:
                    is_foreign = False
                else:
                    is_foreign = True

            if is_foreign and other_foreign_wt is not None:
                wt_id = other_foreign_wt.id
                cat_code_eff = ORPHAN_CAT_CODE  # Чужие задачи без категории на этом уровне
            else:
                if cat_code is None:
                    wt_id = ORPHAN_WT_ID
                    cat_code_eff = ORPHAN_CAT_CODE
                else:
                    mapped_wt = code_to_wt.get(cat_code)
                    if mapped_wt is None:
                        wt_id = ORPHAN_WT_ID
                        cat_code_eff = cat_code  # сохраним код категории чтобы видно было «Архив»
                    else:
                        wt_id = mapped_wt
                        cat_code_eff = cat_code

            # Дополнительные фильтры
            if work_type_codes:
                wt_obj = wt_by_id.get(wt_id)
                wt_code = wt_obj.code if wt_obj else (
                    "__unmapped__" if wt_id == ORPHAN_WT_ID else None
                )
                if wt_code not in work_type_codes:
                    continue
            if category_codes:
                if cat_code_eff not in category_codes:
                    continue

            team_key = emp_team or "__no_team__"
            role_key = emp.role
            key = (team_key, role_key, emp_id, wt_id, cat_code_eff, issue_id)

            entry = bucket.get(key)
            if entry is None:
                entry = {
                    "issue_id": issue_id, "key": row.key, "summary": row.summary,
                    "status": row.status, "status_category": row.status_category,
                    "issue_type": row.issue_type, "category": cat_code,
                    "fact_hours": 0.0, "wl_count": 0,
                    "last_at": None,
                    "assignee_name": getattr(row, "assignee_name", None),
                }
                bucket[key] = entry
            entry["fact_hours"] += h
            entry["wl_count"] += wl_count
            if last_at is not None and (entry["last_at"] is None or last_at > entry["last_at"]):
                entry["last_at"] = last_at

        # 6. Свёртка bucket → дерево
        # group: team → role → emp → wt → cat → [issues]
        tree: dict = {}
        for (team_k, role_k, emp_id, wt_id, cat_code, issue_id), v in bucket.items():
            tree.setdefault(team_k, {}).setdefault(role_k, {}).setdefault(emp_id, {}).setdefault(
                wt_id, {}).setdefault(cat_code, []).append(v)

        # 7. Plan-часы (только сотрудник × вид работ) — TODO в Task 3
        # Базовая реализация: plan_hours=None везде кроме wt-уровня (None даже там пока).
        # Полноценный расчёт plan_hours интегрируется отдельно в Task 3.

        def calc_totals(rows: list[dict], plan_hours: float | None = None,
                        emp_count: int = 0, parent_total: float | None = None) -> NodeTotals:
            fact = sum(r["fact_hours"] for r in rows)
            wl = sum(r["wl_count"] for r in rows)
            issues = len({r["issue_id"] for r in rows})
            avg_min = (fact * 60 / wl) if wl else 0.0
            pct_plan = (fact / plan_hours * 100) if plan_hours and plan_hours > 0 else None
            pct_total = (fact / parent_total * 100) if parent_total and parent_total > 0 else 0.0
            return NodeTotals(
                fact_hours=round(fact, 1),
                plan_hours=round(plan_hours, 1) if plan_hours is not None else None,
                pct_plan=round(pct_plan, 1) if pct_plan is not None else None,
                pct_total=round(pct_total, 1),
                worklog_count=wl,
                issue_count=issues,
                employee_count=emp_count,
                avg_worklog_minutes=round(avg_min, 1),
            )

        grand_total_fact = sum(v["fact_hours"] for v in bucket.values())

        teams_out: list[AnalyticsTeamNode] = []
        for team_key, roles_dict in tree.items():
            team_rows: list[dict] = []
            roles_out: list[AnalyticsRoleNode] = []
            team_emp_ids: set[str] = set()
            for role_key, emps_dict in roles_dict.items():
                role_rows: list[dict] = []
                emps_out: list[AnalyticsEmployeeNode] = []
                for emp_id, wts_dict in emps_dict.items():
                    emp = next((e for e in employees if e.id == emp_id), None)
                    if emp is None:
                        continue
                    emp_rows: list[dict] = []
                    wts_out: list[AnalyticsWorkTypeNode] = []
                    for wt_id, cats_dict in wts_dict.items():
                        wt_rows: list[dict] = []
                        cats_out: list[AnalyticsCategoryNode] = []
                        wt_obj = wt_by_id.get(wt_id)
                        wt_label = wt_obj.label if wt_obj else ORPHAN_WT_LABEL
                        for cat_code, issues_list in cats_dict.items():
                            cat_label, cat_color, _ = cat_meta.get(
                                cat_code or "", (ORPHAN_CAT_LABEL, "#7e94b8", None)
                            )
                            issues_out: list[AnalyticsIssueNode] = []
                            for v in issues_list:
                                issues_out.append(AnalyticsIssueNode(
                                    id=v["issue_id"], key=v["key"], summary=v["summary"],
                                    status=v["status"], status_category=v["status_category"],
                                    issue_type=v["issue_type"], category=v["category"],
                                    last_worklog_at=v["last_at"], assignee_name=v.get("assignee_name"),
                                    totals=calc_totals([v], parent_total=grand_total_fact),
                                ))
                            cats_out.append(AnalyticsCategoryNode(
                                category_code=cat_code,
                                label=cat_label, color=cat_color,
                                totals=calc_totals(issues_list, parent_total=grand_total_fact),
                                issues=sorted(issues_out, key=lambda x: -x.totals.fact_hours),
                            ))
                            wt_rows.extend(issues_list)
                        wts_out.append(AnalyticsWorkTypeNode(
                            work_type_id=wt_id, label=wt_label,
                            totals=calc_totals(wt_rows, parent_total=grand_total_fact),
                            categories=sorted(cats_out, key=lambda x: -x.totals.fact_hours),
                        ))
                        emp_rows.extend(wt_rows)
                    role_obj_for_color = role_by_code.get(emp.role)
                    role_color = role_obj_for_color.color if role_obj_for_color else "#7e94b8"
                    emps_out.append(AnalyticsEmployeeNode(
                        employee_id=emp.id,
                        name=emp.display_name or "",
                        initials=_initials(emp.display_name or ""),
                        totals=calc_totals(emp_rows, emp_count=1, parent_total=grand_total_fact),
                        work_types=sorted(wts_out, key=lambda x: -x.totals.fact_hours),
                    ))
                    role_rows.extend(emp_rows)
                    team_emp_ids.add(emp.id)
                role_obj = role_by_code.get(role_key)
                role_label = role_obj.label if role_obj else (role_key or "Без роли")
                role_color_main = role_obj.color if role_obj else "#7e94b8"
                roles_out.append(AnalyticsRoleNode(
                    role_code=role_key,
                    role_label=role_label, role_color=role_color_main,
                    totals=calc_totals(role_rows, emp_count=len(emps_out),
                                       parent_total=grand_total_fact),
                    employees=sorted(emps_out, key=lambda x: -x.totals.fact_hours),
                ))
                team_rows.extend(role_rows)
            teams_out.append(AnalyticsTeamNode(
                team=team_key if team_key != "__no_team__" else None,
                totals=calc_totals(team_rows, emp_count=len(team_emp_ids),
                                   parent_total=grand_total_fact),
                roles=sorted(roles_out, key=lambda x: -x.totals.fact_hours),
            ))

        teams_out.sort(key=lambda t: -t.totals.fact_hours)
        all_emp_ids: set[str] = set()
        for t in tree.values():
            for r in t.values():
                for emp_id in r.keys():
                    all_emp_ids.add(emp_id)
        return AnalyticsReportResponse(
            teams=teams_out,
            grand_totals=NodeTotals(
                fact_hours=round(grand_total_fact, 1),
                plan_hours=None, pct_plan=None, pct_total=100.0 if grand_total_fact > 0 else 0.0,
                worklog_count=sum(v["wl_count"] for v in bucket.values()),
                issue_count=len({v["issue_id"] for v in bucket.values()}),
                employee_count=len(all_emp_ids),
                avg_worklog_minutes=round(
                    (grand_total_fact * 60 / sum(v["wl_count"] for v in bucket.values()))
                    if any(v["wl_count"] for v in bucket.values()) else 0.0,
                    1,
                ),
            ),
        )


def _empty_totals():
    from app.schemas.analytics_report import NodeTotals
    return NodeTotals(
        fact_hours=0.0, plan_hours=None, pct_plan=None, pct_total=0.0,
        worklog_count=0, issue_count=0, employee_count=0, avg_worklog_minutes=0.0,
    )


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()
```

(Перенести `_initials` если в файле уже есть подобный helper — переиспользовать.)

- [ ] **Step 4: Импорты в начале analytics_service.py — добавить `or_` если нет**

```python
from sqlalchemy import func, or_
```

- [ ] **Step 5: Заглушка-эндпоинт (раз нет ещё роутера — Task 4 добавит)**

Пока запускаем тест с прямым вызовом сервиса. Если в тесте hit на /api/v1/analytics/report — он упадёт 404. Это ожидаемо до Task 4.

Альтернатива: написать прямой service-test (не endpoint). Перепишем `test_report_returns_team_role_employee_tree`:

```python
def test_report_service_returns_tree(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 4.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(year=2026, quarter=2, teams=["Команда A"])
    assert len(data.teams) == 1
    assert data.teams[0].team == "Команда A"
    assert data.teams[0].totals.fact_hours == 4.0
    assert data.grand_totals.fact_hours == 4.0
```

(Endpoint-test добавим в Task 4.)

- [ ] **Step 6: Запустить service-test — должен пройти**

Run: `py -3.10 -m pytest tests/test_analytics_report.py::test_report_service_returns_tree -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/analytics_service.py tests/test_analytics_report.py
git commit -m "feat(analytics): hierarchical report service (base aggregation)"
```

---

### Task 3: Добавить расчёт plan_hours и фильтры

**Files:**
- Modify: `app/services/analytics_service.py` (метод `get_hierarchical_report`)
- Modify: `tests/test_analytics_report.py`

- [ ] **Step 1: Добавить тесты для фильтров и плана**

```python
def test_report_employee_filter(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp1 = _seed_emp(db_session, "Один", "Команда A")
    emp2 = _seed_emp(db_session, "Два", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp1, 3.0)
    _seed_worklog(db_session, issue, emp2, 5.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], employee_id=emp1.id,
    )
    all_emps = [e for t in data.teams for r in t.roles for e in r.employees]
    assert len(all_emps) == 1
    assert all_emps[0].employee_id == emp1.id


def test_report_task_query_filter(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    issue1 = _seed_issue(db_session, project, "PROD-1", "Команда A",
                         "support_consultation", summary="Bugfix login")
    issue2 = _seed_issue(db_session, project, "OS-2", "Команда A",
                         "support_consultation", summary="Refactor module")
    _seed_worklog(db_session, issue1, emp, 2.0)
    _seed_worklog(db_session, issue2, emp, 3.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], task_query="bugfix",
    )
    all_issues = [
        i for t in data.teams for r in t.roles for e in r.employees
        for w in e.work_types for c in w.categories for i in c.issues
    ]
    assert len(all_issues) == 1
    assert all_issues[0].key == "PROD-1"
```

- [ ] **Step 2: Запустить — должны пройти (фильтры уже реализованы в Task 2)**

Run: `py -3.10 -m pytest tests/test_analytics_report.py -v`

Expected: оба теста PASS. Если нет — починить логику фильтров в Task 2 шаг 3.

- [ ] **Step 3: Добавить расчёт plan_hours в employee×work_type**

В `get_hierarchical_report` после `bucket` (но до сборки дерева) переиспользуем логику из `get_dashboard_norm_work` — копируем секцию построения `plan_per_emp_wt`:

```python
        # Plan-часы per emp×work_type (копия логики из get_dashboard_norm_work § 5-7)
        from app.services.capacity_service import CapacityService
        from app.models.role_capacity_rule import RoleCapacityRule
        from app.models.employee_capacity_override import EmployeeCapacityOverride
        from app.models.scenario_rule import ScenarioRule

        rules_by_role: dict[str | None, dict[str, float]] = {}
        approved_q = (
            self.db.query(PlanningScenario.id)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
        )
        if teams:
            approved_q = approved_q.filter(PlanningScenario.team.in_(teams))
        approved_ids = [r[0] for r in approved_q.all()]
        if approved_ids:
            for sr in self.db.query(ScenarioRule).filter(
                ScenarioRule.scenario_id.in_(approved_ids)
            ).all():
                rules_by_role.setdefault(sr.role, {})[sr.work_type_id] = sr.percent_of_norm
        if not rules_by_role:
            for rule in self.db.query(RoleCapacityRule).filter(
                RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter,
            ).all():
                rules_by_role.setdefault(rule.role, {})[rule.work_type_id] = rule.percent_of_norm

        overrides_by_emp: dict[str, dict[str, float]] = {}
        for ov in self.db.query(EmployeeCapacityOverride).filter(
            EmployeeCapacityOverride.year == year,
            EmployeeCapacityOverride.quarter == quarter,
        ).all():
            overrides_by_emp.setdefault(ov.employee_id, {})[ov.work_type_id] = ov.percent_of_norm

        def pct_for(emp_role: str | None, emp_id: str, wt_id_inner: str) -> float:
            ov = overrides_by_emp.get(emp_id, {})
            if wt_id_inner in ov:
                return ov[wt_id_inner]
            r = rules_by_role.get(emp_role, {})
            if wt_id_inner in r:
                return r[wt_id_inner]
            return rules_by_role.get(None, {}).get(wt_id_inner, 0.0)

        cap_svc = CapacityService(self.db)
        base_hours_by_emp: dict[str, float] = {}
        try:
            team_caps = cap_svc.team_quarter_capacity(
                year=year, quarter=quarter,
                employee_ids=[e.id for e in employees],
            )
        except ValueError:
            team_caps = []
        for qcap in team_caps:
            if month is not None:
                mcap = next((m for m in qcap.months if m.month == month), None)
                base_hours_by_emp[qcap.employee_id] = mcap.available_hours if mcap else 0.0
            else:
                base_hours_by_emp[qcap.employee_id] = qcap.total_available_hours
        for emp in employees:
            base_hours_by_emp.setdefault(emp.id, 0.0)

        project_wt = next((wt for wt in work_types if wt.code == "project"), None)
        plan_per_emp_wt: dict[str, dict[str, float]] = {}
        for emp in employees:
            base = base_hours_by_emp.get(emp.id, 0.0)
            per_wt: dict[str, float] = {}
            mandatory_total = 0.0
            for wt in work_types:
                if project_wt is not None and wt.id == project_wt.id:
                    continue
                p = pct_for(emp.role, emp.id, wt.id)
                if p > 0:
                    h = base * p / 100.0
                    per_wt[wt.id] = h
                    mandatory_total += h
            if project_wt is not None:
                per_wt[project_wt.id] = max(0.0, base - mandatory_total)
            plan_per_emp_wt[emp.id] = per_wt
```

- [ ] **Step 4: Прокинуть план в `calc_totals`**

В сборке дерева — на уровне employee×work_type получать план:

```python
                    for wt_id, cats_dict in wts_dict.items():
                        ...
                        plan_for_wt = plan_per_emp_wt.get(emp.id, {}).get(wt_id)
                        wts_out.append(AnalyticsWorkTypeNode(
                            work_type_id=wt_id, label=wt_label,
                            totals=calc_totals(wt_rows, plan_hours=plan_for_wt,
                                               parent_total=grand_total_fact),
                            ...
```

На уровне employee — суммировать план по всем `plan_per_emp_wt[emp.id].values()`:

```python
                    emp_plan = sum(plan_per_emp_wt.get(emp.id, {}).values())
                    emps_out.append(AnalyticsEmployeeNode(
                        ...
                        totals=calc_totals(emp_rows, plan_hours=emp_plan if emp_plan > 0 else None,
                                           emp_count=1, parent_total=grand_total_fact),
                        ...
                    ))
```

На уровне role — суммировать по сотрудникам этой роли:

```python
                role_plan = sum(
                    sum(plan_per_emp_wt.get(emp_id, {}).values())
                    for emp_id in emps_dict.keys()
                )
                roles_out.append(AnalyticsRoleNode(
                    ...
                    totals=calc_totals(role_rows,
                                       plan_hours=role_plan if role_plan > 0 else None,
                                       emp_count=len(emps_out),
                                       parent_total=grand_total_fact),
                    ...
                ))
```

На уровне team — аналогично, по всем сотрудникам команды.

На grand_totals — суммировать по всем employees.

- [ ] **Step 5: Добавить тест проверки plan**

```python
def test_report_plan_hours_at_employee_level(db_session):
    from app.services.analytics_service import AnalyticsService
    from app.models.role_capacity_rule import RoleCapacityRule
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    # support_consult, 50% от нормы
    wt_support = db_session.query(MandatoryWorkType).filter_by(code="support_consult").first()
    db_session.add(RoleCapacityRule(
        id=str(uuid.uuid4()), year=2026, quarter=2, role="developer",
        work_type_id=wt_support.id, percent_of_norm=50.0,
    ))
    db_session.commit()
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 2.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(year=2026, quarter=2, teams=["Команда A"])
    emp_node = data.teams[0].roles[0].employees[0]
    assert emp_node.totals.plan_hours is not None
    assert emp_node.totals.plan_hours > 0
    sup_wt = next(w for w in emp_node.work_types if w.label == "Сопровождение и консультация")
    assert sup_wt.totals.plan_hours is not None
```

- [ ] **Step 6: Запустить полный набор тестов**

Run: `py -3.10 -m pytest tests/test_analytics_report.py -v`

Expected: все PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/analytics_service.py tests/test_analytics_report.py
git commit -m "feat(analytics): plan hours at employee/role/team levels"
```

---

### Task 4: Эндпоинт `/analytics/report`

**Files:**
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/test_analytics_report.py`

- [ ] **Step 1: Добавить тест эндпоинта**

```python
def test_report_endpoint_returns_200(db_session, client):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 4.0)

    resp = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["grand_totals"]["fact_hours"] == 4.0


def test_report_endpoint_filters(db_session, client):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp1 = _seed_emp(db_session, "Один", "Команда A")
    emp2 = _seed_emp(db_session, "Два", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp1, 3.0)
    _seed_worklog(db_session, issue, emp2, 5.0)

    resp = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A",
                "employee_id": emp1.id},
    )
    data = resp.json()
    assert data["grand_totals"]["fact_hours"] == 3.0
```

- [ ] **Step 2: Запустить тесты — должны упасть (404)**

Run: `py -3.10 -m pytest tests/test_analytics_report.py::test_report_endpoint_returns_200 -v`

Expected: 404.

- [ ] **Step 3: Добавить роут в `app/api/endpoints/analytics.py`**

```python
from app.schemas.analytics_report import AnalyticsReportResponse


@router.get("/report", response_model=AnalyticsReportResponse)
def get_analytics_report(
    year: int,
    quarter: int,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    teams: Optional[str] = None,
    employee_id: Optional[str] = None,
    task_query: Optional[str] = None,
    work_type_codes: Optional[str] = None,
    category_codes: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Иерархический отчёт Аналитики."""
    teams_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    wt_codes = [c.strip() for c in work_type_codes.split(",") if c.strip()] if work_type_codes else None
    cat_codes = [c.strip() for c in category_codes.split(",") if c.strip()] if category_codes else None
    return AnalyticsService(db).get_hierarchical_report(
        year=year, quarter=quarter, month=month,
        start_date=start_date, end_date=end_date,
        teams=teams_list, employee_id=employee_id,
        task_query=task_query, work_type_codes=wt_codes, category_codes=cat_codes,
    )
```

(Импорты `date`, `Optional`, `Session`, `Depends`, `get_db`, `AnalyticsService` уже должны быть в файле; если нет — добавить.)

- [ ] **Step 4: Запустить тесты эндпоинта**

Run: `py -3.10 -m pytest tests/test_analytics_report.py::test_report_endpoint_returns_200 tests/test_analytics_report.py::test_report_endpoint_filters -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/analytics.py tests/test_analytics_report.py
git commit -m "feat(analytics): /analytics/report endpoint"
```

---

### Task 5: Эндпоинт ворклогов задачи + сервис

**Files:**
- Modify: `app/services/analytics_service.py`
- Modify: `app/api/endpoints/analytics.py`
- Modify: `tests/test_analytics_report.py`

- [ ] **Step 1: Тест**

```python
def test_issue_worklogs_endpoint(db_session, client):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 2.0, day=10)
    _seed_worklog(db_session, issue, emp, 3.0, day=15)

    resp = client.get(
        f"/api/v1/analytics/report/issue/{issue.id}/worklogs",
        params={"start": "2026-04-01", "end": "2026-04-30"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert sum(i["hours"] for i in items) == 5.0
    assert all(i["employee_name"] == "Тест" for i in items)
```

- [ ] **Step 2: Запустить — fail 404**

- [ ] **Step 3: Сервис-метод**

В `analytics_service.py`:

```python
    def get_issue_worklogs(
        self, issue_id: str, start: date, end: date,
    ) -> list[IssueWorklogItem]:
        from app.schemas.analytics_report import IssueWorklogItem
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        rows = (
            self.db.query(
                Worklog.id, Worklog.started_at, Worklog.hours,
                Employee.display_name, Worklog.comment,
            )
            .join(Employee, Employee.id == Worklog.employee_id)
            .filter(
                Worklog.issue_id == issue_id,
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
            .order_by(Worklog.started_at)
            .all()
        )
        return [
            IssueWorklogItem(
                worklog_id=r.id, started_at=r.started_at, hours=r.hours or 0.0,
                employee_name=r.display_name or "", comment=r.comment,
            )
            for r in rows
        ]
```

- [ ] **Step 4: Эндпоинт**

```python
@router.get("/report/issue/{issue_id}/worklogs", response_model=list[IssueWorklogItem])
def get_issue_worklogs_endpoint(
    issue_id: str,
    start: date,
    end: date,
    db: Session = Depends(get_db),
):
    return AnalyticsService(db).get_issue_worklogs(issue_id, start, end)
```

- [ ] **Step 5: Тест PASS**

Run: `py -3.10 -m pytest tests/test_analytics_report.py::test_issue_worklogs_endpoint -v`

- [ ] **Step 6: Commit**

```bash
git add app/services/analytics_service.py app/api/endpoints/analytics.py tests/test_analytics_report.py
git commit -m "feat(analytics): issue worklogs lazy-load endpoint"
```

---

# Фаза 2 — Глобальный пикер периода

### Task 6: Миграция и поля User

**Files:**
- Modify: `app/models/user.py`
- Create: `alembic/versions/<rev>_add_user_period_and_columns.py`

- [ ] **Step 1: Сгенерировать миграцию**

Run: `py -3.10 -m alembic revision --autogenerate -m "add user.selected_period and analytics_columns"`

Получим файл `alembic/versions/<rev>_<msg>.py`.

- [ ] **Step 2: Отредактировать миграцию (batch для SQLite)**

```python
def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column(
            "selected_period", sa.Text(), nullable=False, server_default="{}"
        ))
        batch_op.add_column(sa.Column(
            "analytics_columns", sa.Text(), nullable=False, server_default="[]"
        ))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("analytics_columns")
        batch_op.drop_column("selected_period")
```

- [ ] **Step 3: Добавить поля в модель**

```python
    selected_period_raw: Mapped[str] = mapped_column(
        "selected_period", Text, nullable=False, default="{}"
    )
    analytics_columns_raw: Mapped[str] = mapped_column(
        "analytics_columns", Text, nullable=False, default="[]"
    )

    @property
    def selected_period(self) -> dict:
        try:
            return json.loads(self.selected_period_raw or "{}")
        except (TypeError, ValueError):
            return {}

    @selected_period.setter
    def selected_period(self, value: dict) -> None:
        self.selected_period_raw = json.dumps(value or {})

    @property
    def analytics_columns(self) -> list[str]:
        try:
            return json.loads(self.analytics_columns_raw or "[]")
        except (TypeError, ValueError):
            return []

    @analytics_columns.setter
    def analytics_columns(self, value: list[str]) -> None:
        self.analytics_columns_raw = json.dumps(list(value or []))
```

- [ ] **Step 4: Применить миграцию**

Run: `py -3.10 -m alembic upgrade head`

- [ ] **Step 5: Test базовый**

```python
# tests/test_user_settings.py
def test_user_period_default_empty(db_session):
    from app.models import User
    u = User(email="a@b.com", password_hash="x", display_name="A", role="manager")
    db_session.add(u); db_session.commit()
    assert u.selected_period == {}
    u.selected_period = {"year": 2026, "quarter": 2, "month": 4}
    db_session.commit()
    assert u.selected_period == {"year": 2026, "quarter": 2, "month": 4}
```

Run + verify pass.

- [ ] **Step 6: Commit**

```bash
git add app/models/user.py alembic/versions/<rev>_*.py tests/test_user_settings.py
git commit -m "feat(user): selected_period and analytics_columns fields"
```

---

### Task 7: Эндпоинты `/users/me/period` и `/users/me/analytics-columns`

**Files:**
- Modify: `app/api/endpoints/users.py`
- Modify: `tests/test_user_settings.py` (или соответствующий)

- [ ] **Step 1: Тест endpoint**

```python
def test_get_set_my_period(db_session, client_authenticated_as_user):
    resp = client_authenticated_as_user.get("/api/v1/users/me/period")
    assert resp.status_code == 200
    assert resp.json() == {}

    resp = client_authenticated_as_user.put(
        "/api/v1/users/me/period",
        json={"year": 2026, "quarter": 2, "month": 4},
    )
    assert resp.status_code == 200

    resp = client_authenticated_as_user.get("/api/v1/users/me/period")
    assert resp.json() == {"year": 2026, "quarter": 2, "month": 4}
```

(Если нет фикстуры `client_authenticated_as_user` — посмотреть существующие тесты на `/users/me/*` и переиспользовать паттерн авторизации, скорее всего через JWT-токен.)

- [ ] **Step 2: Запустить — fail**

- [ ] **Step 3: Реализовать**

В `app/api/endpoints/users.py`:

```python
class PeriodPayload(BaseModel):
    year: int | None = None
    quarter: int | None = None
    month: int | None = None


class ColumnsPayload(BaseModel):
    columns: list[str]


@router.get("/me/period")
def get_my_period(current_user: User = Depends(get_current_user)):
    return current_user.selected_period


@router.put("/me/period")
def set_my_period(
    payload: PeriodPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.selected_period = payload.model_dump(exclude_none=True)
    db.commit()
    return {"ok": True}


@router.get("/me/analytics-columns")
def get_my_columns(current_user: User = Depends(get_current_user)):
    return {"columns": current_user.analytics_columns}


@router.put("/me/analytics-columns")
def set_my_columns(
    payload: ColumnsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.analytics_columns = payload.columns
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Тесты PASS**

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/users.py tests/test_user_settings.py
git commit -m "feat(user): GET/PUT /me/period and /me/analytics-columns"
```

---

### Task 8: Frontend контекст глобального периода

**Files:**
- Create: `frontend/src/hooks/useGlobalPeriod.ts`
- Create: `frontend/src/components/shared/GlobalPeriodFilterProvider.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Хук**

```typescript
// useGlobalPeriod.ts
import { createContext, useContext } from 'react';

export type GlobalPeriod = {
  year: number;
  quarter: number;
  month?: number;
};

export type GlobalPeriodCtx = {
  period: GlobalPeriod;
  setPeriod: (p: GlobalPeriod) => Promise<void>;
  saving: boolean;
  queryParams: { year: number; quarter: number; month?: number };
};

export const GlobalPeriodContext = createContext<GlobalPeriodCtx | null>(null);

export function useGlobalPeriod(): GlobalPeriodCtx {
  const ctx = useContext(GlobalPeriodContext);
  if (!ctx) throw new Error('useGlobalPeriod must be used inside GlobalPeriodFilterProvider');
  return ctx;
}
```

- [ ] **Step 2: Провайдер**

```typescript
// GlobalPeriodFilterProvider.tsx
import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { GlobalPeriodContext, type GlobalPeriod } from '../../hooks/useGlobalPeriod';
import { api } from '../../api/client';

const CURRENT = (() => {
  const d = new Date();
  return {
    year: d.getFullYear(),
    quarter: Math.floor(d.getMonth() / 3) + 1,
    month: d.getMonth() + 1,
  };
})();

export function GlobalPeriodFilterProvider({ children }: { children: ReactNode }) {
  const [period, setPeriodState] = useState<GlobalPeriod>(CURRENT);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<GlobalPeriod>('/users/me/period').then((p) => {
      if (p && p.year && p.quarter) setPeriodState({ year: p.year, quarter: p.quarter, month: p.month });
    }).catch(() => { /* ignore */ });
  }, []);

  const setPeriod = useCallback(async (p: GlobalPeriod) => {
    setPeriodState(p);
    setSaving(true);
    try {
      await api.put('/users/me/period', p);
    } finally {
      setSaving(false);
    }
  }, []);

  return (
    <GlobalPeriodContext.Provider value={{
      period, setPeriod, saving,
      queryParams: { year: period.year, quarter: period.quarter, month: period.month },
    }}>
      {children}
    </GlobalPeriodContext.Provider>
  );
}
```

- [ ] **Step 3: Подключить в App.tsx**

Найти, где обернут `GlobalTeamFilterProvider`. Обернуть туда же `GlobalPeriodFilterProvider`:

```tsx
<GlobalTeamFilterProvider>
  <GlobalPeriodFilterProvider>
    <Routes>...</Routes>
  </GlobalPeriodFilterProvider>
</GlobalTeamFilterProvider>
```

- [ ] **Step 4: Сборка не падает**

Run: `cd frontend && npm run build`

Expected: success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useGlobalPeriod.ts frontend/src/components/shared/GlobalPeriodFilterProvider.tsx frontend/src/App.tsx
git commit -m "feat(frontend): global period filter context"
```

---

### Task 9: GlobalPeriodPicker компонент в шапке

**Files:**
- Create: `frontend/src/components/shared/GlobalPeriodPicker.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx` (или эквивалент — там, где сейчас рендерится TeamFilter pill)

- [ ] **Step 1: Найти место в шапке**

```bash
grep -rn "GlobalTeamFilter" frontend/src/components/layout
```

Ожидается файл вроде `AppLayout.tsx` или `Header.tsx`. Запомнить его путь.

- [ ] **Step 2: Компонент**

```tsx
// GlobalPeriodPicker.tsx
import { Select, Space } from 'antd';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';

const QUARTERS = [
  { value: 1, label: 'Q1 (янв-мар)' },
  { value: 2, label: 'Q2 (апр-июн)' },
  { value: 3, label: 'Q3 (июл-сен)' },
  { value: 4, label: 'Q4 (окт-дек)' },
];

const MONTH_NAMES = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1,2,3], 2: [4,5,6], 3: [7,8,9], 4: [10,11,12],
};

export default function GlobalPeriodPicker() {
  const { period, setPeriod } = useGlobalPeriod();
  const months = QUARTER_MONTHS[period.quarter] || [];

  return (
    <Space size={4}>
      <Select
        size="small"
        style={{ minWidth: 80 }}
        value={period.year}
        onChange={(v) => setPeriod({ ...period, year: v })}
        options={[period.year - 1, period.year, period.year + 1].map(y => ({ value: y, label: y }))}
      />
      <Select
        size="small"
        style={{ minWidth: 130 }}
        value={period.quarter}
        onChange={(v) => setPeriod({ ...period, quarter: v, month: undefined })}
        options={QUARTERS}
      />
      <Select
        size="small"
        style={{ minWidth: 80 }}
        value={period.month ?? 'all'}
        onChange={(v) => setPeriod({ ...period, month: v === 'all' ? undefined : Number(v) })}
        options={[
          { value: 'all', label: 'Весь Q' },
          ...months.map(m => ({ value: m, label: MONTH_NAMES[m - 1] })),
        ]}
      />
    </Space>
  );
}
```

- [ ] **Step 3: Вставить в шапку рядом с TeamFilter**

В файле шапки (например `AppLayout.tsx`) — рядом с `<GlobalTeamFilter />`:

```tsx
import GlobalPeriodPicker from '../shared/GlobalPeriodPicker';
...
<Space>
  <GlobalTeamFilter />
  <GlobalPeriodPicker />
</Space>
```

- [ ] **Step 4: Visual smoke**

```bash
cd frontend && npm run dev
```

Открыть http://localhost:5173/ — в шапке видны два пикера; смена квартала меняет список месяцев; перезагрузка восстанавливает выбор.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/GlobalPeriodPicker.tsx frontend/src/components/layout/<file>
git commit -m "feat(frontend): GlobalPeriodPicker in app header"
```

---

### Task 10: Миграция Dashboard и Capacity на глобальный период

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Заменить локальный QuarterPicker на чтение из useGlobalPeriod**

В `DashboardPage.tsx`: убрать локальный стейт `year/quarter/month`, использовать `useGlobalPeriod`. Если был локальный `QuarterPicker` — удалить.

```tsx
const { period } = useGlobalPeriod();
// Раньше: const { data } = useDashboardNormWork(year, quarter, month);
// Теперь: 
const { data } = useDashboardNormWork(period.year, period.quarter, period.month);
```

- [ ] **Step 2: То же для CapacityPage.tsx**

В Capacity сохранить локальный override (например, чекбокс «Уточнить период» который раскрывает локальный пикер). По дефолту — берёт из global.

- [ ] **Step 3: Smoke-test**

`npm run dev` → переключить квартал в шапке → Dashboard и Capacity обновили данные синхронно.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/CapacityPage.tsx
git commit -m "refactor(frontend): Dashboard+Capacity read from global period"
```

---

# Фаза 3 — Новая страница Аналитики

### Task 11: API клиент + хуки

**Files:**
- Create: `frontend/src/api/analyticsReport.ts`
- Create: `frontend/src/hooks/useAnalyticsReport.ts`
- Create: `frontend/src/hooks/useIssueWorklogs.ts`
- Create: `frontend/src/hooks/useAnalyticsColumns.ts`
- Modify: `frontend/src/types/api.ts` — добавить типы из `app/schemas/analytics_report.py`

- [ ] **Step 1: Типы**

В `frontend/src/types/api.ts` добавить:

```typescript
export interface NodeTotals {
  fact_hours: number;
  plan_hours: number | null;
  pct_plan: number | null;
  pct_total: number;
  worklog_count: number;
  issue_count: number;
  employee_count: number;
  avg_worklog_minutes: number;
}

export interface AnalyticsIssueNode {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_category: string | null;
  issue_type: string;
  category: string | null;
  last_worklog_at: string | null;
  assignee_name: string | null;
  totals: NodeTotals;
}

export interface AnalyticsCategoryNode {
  category_code: string | null;
  label: string;
  color: string;
  totals: NodeTotals;
  issues: AnalyticsIssueNode[];
}

export interface AnalyticsWorkTypeNode {
  work_type_id: string;
  label: string;
  totals: NodeTotals;
  categories: AnalyticsCategoryNode[];
}

export interface AnalyticsEmployeeNode {
  employee_id: string;
  name: string;
  initials: string;
  totals: NodeTotals;
  work_types: AnalyticsWorkTypeNode[];
}

export interface AnalyticsRoleNode {
  role_code: string | null;
  role_label: string;
  role_color: string;
  totals: NodeTotals;
  employees: AnalyticsEmployeeNode[];
}

export interface AnalyticsTeamNode {
  team: string | null;
  totals: NodeTotals;
  roles: AnalyticsRoleNode[];
}

export interface AnalyticsReportResponse {
  teams: AnalyticsTeamNode[];
  grand_totals: NodeTotals;
}

export interface IssueWorklogItem {
  worklog_id: string;
  started_at: string;
  hours: number;
  employee_name: string;
  comment: string | null;
}
```

- [ ] **Step 2: API methods**

```typescript
// analyticsReport.ts
import { api } from './client';
import type { AnalyticsReportResponse, IssueWorklogItem } from '../types/api';

export interface AnalyticsReportParams {
  year: number;
  quarter: number;
  month?: number;
  start_date?: string;
  end_date?: string;
  teams?: string;
  employee_id?: string;
  task_query?: string;
  work_type_codes?: string;
  category_codes?: string;
}

export function fetchAnalyticsReport(p: AnalyticsReportParams, signal?: AbortSignal) {
  return api.get<AnalyticsReportResponse>('/analytics/report', p, signal);
}

export function fetchIssueWorklogs(issueId: string, start: string, end: string, signal?: AbortSignal) {
  return api.get<IssueWorklogItem[]>(
    `/analytics/report/issue/${issueId}/worklogs`, { start, end }, signal,
  );
}
```

- [ ] **Step 3: Хуки**

```typescript
// useAnalyticsReport.ts
import { useQuery } from '@tanstack/react-query';
import { fetchAnalyticsReport, type AnalyticsReportParams } from '../api/analyticsReport';

export function useAnalyticsReport(params: AnalyticsReportParams) {
  return useQuery({
    queryKey: ['analytics-report', params],
    queryFn: ({ signal }) => fetchAnalyticsReport(params, signal),
  });
}
```

```typescript
// useIssueWorklogs.ts
import { useQuery } from '@tanstack/react-query';
import { fetchIssueWorklogs } from '../api/analyticsReport';

export function useIssueWorklogs(issueId: string | null, start: string, end: string) {
  return useQuery({
    queryKey: ['issue-worklogs', issueId, start, end],
    queryFn: ({ signal }) => fetchIssueWorklogs(issueId!, start, end, signal),
    enabled: !!issueId,
  });
}
```

```typescript
// useAnalyticsColumns.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

const ALL_COLUMNS = [
  'plan_hours','pct_plan','pct_total','worklog_count','issue_count',
  'employee_count','avg_worklog_minutes',
  'status','issue_type','category','last_worklog_at','assignee_name',
];

export function useAnalyticsColumns() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['analytics-columns'],
    queryFn: () => api.get<{ columns: string[] }>('/users/me/analytics-columns'),
  });
  const visible = data?.columns?.length ? data.columns : ALL_COLUMNS;

  const setMutation = useMutation({
    mutationFn: (cols: string[]) => api.put('/users/me/analytics-columns', { columns: cols }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics-columns'] }),
  });

  return { visible, allColumns: ALL_COLUMNS, isLoading, setVisible: setMutation.mutate };
}
```

- [ ] **Step 4: Сборка**

Run: `cd frontend && npm run build`

Expected: success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/analyticsReport.ts frontend/src/hooks/useAnalyticsReport.ts frontend/src/hooks/useIssueWorklogs.ts frontend/src/hooks/useAnalyticsColumns.ts frontend/src/types/api.ts
git commit -m "feat(analytics): frontend API client + hooks for hierarchical report"
```

---

### Task 12: Каркас страницы AnalyticsPage (master-detail layout)

**Files:**
- Modify: `frontend/src/pages/AnalyticsPage.tsx` (полная замена)
- Create: `frontend/src/components/analytics/AnalyticsTeamList.tsx`
- Create: `frontend/src/components/analytics/AnalyticsTable.tsx`
- Create: `frontend/src/components/analytics/AnalyticsFilters.tsx`

- [ ] **Step 1: Переписать `AnalyticsPage.tsx`**

```tsx
import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { Space, DatePicker, Switch, Button, Empty, Spin } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import PageHeader from '../components/shared/PageHeader';
import AnalyticsTeamList from '../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../components/analytics/AnalyticsTable';
import { useAnalyticsReport } from '../hooks/useAnalyticsReport';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

  const [selectedTeam, setSelectedTeam] = useState<string | 'all'>(
    selectedTeams[0] || 'all',
  );

  // URL-driven filters
  const employeeId = params.get('employee') || undefined;
  const workType = params.get('work_type') || undefined;
  const category = params.get('category') || undefined;
  const taskQ = params.get('task') || undefined;

  const [localRange, setLocalRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [worklogMode, setWorklogMode] = useState<'inline' | 'drawer'>('inline');

  const queryParams = useMemo(() => ({
    year: period.year,
    quarter: period.quarter,
    month: period.month,
    start_date: localRange?.[0]?.format('YYYY-MM-DD'),
    end_date: localRange?.[1]?.format('YYYY-MM-DD'),
    teams: selectedTeam !== 'all' ? selectedTeam : (selectedTeams.join(',') || undefined),
    employee_id: employeeId,
    task_query: taskQ,
    work_type_codes: workType,
    category_codes: category,
  }), [period, localRange, selectedTeam, selectedTeams, employeeId, workType, category, taskQ]);

  const { data, isLoading } = useAnalyticsReport(queryParams);

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader eyebrow="Аналитика" title="Иерархический отчёт по часам" />

      <Space wrap>
        <DatePicker.RangePicker
          value={localRange}
          onChange={setLocalRange}
          placeholder={['Уточнить с', 'по']}
          allowClear
        />
        <span>Ворклоги:</span>
        <Switch
          checkedChildren="inline"
          unCheckedChildren="drawer"
          checked={worklogMode === 'inline'}
          onChange={(v) => setWorklogMode(v ? 'inline' : 'drawer')}
        />
      </Space>

      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <AnalyticsTeamList
          data={data}
          selected={selectedTeam}
          onSelect={setSelectedTeam}
        />
        <div>
          <AnalyticsFilters
            urlParams={{ employeeId, workType, category, taskQ }}
            onChange={(next) => {
              const p = new URLSearchParams(params);
              const set = (k: string, v: string | undefined) => {
                if (v) p.set(k, v); else p.delete(k);
              };
              set('employee', next.employeeId);
              set('work_type', next.workType);
              set('category', next.category);
              set('task', next.taskQ);
              setParams(p);
            }}
          />
          {isLoading ? <Spin /> :
            !data?.teams.length ? <Empty description="Нет данных за выбранный период" /> :
            <AnalyticsTable data={data} selectedTeam={selectedTeam} worklogMode={worklogMode}
                            periodStart={localRange?.[0]?.format('YYYY-MM-DD') || ''}
                            periodEnd={localRange?.[1]?.format('YYYY-MM-DD') || ''} />}
        </div>
      </div>
    </Space>
  );
}
```

- [ ] **Step 2: Заглушки компонентов**

`AnalyticsTeamList.tsx`:
```tsx
import { Card, List } from 'antd';
import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse | undefined;
  selected: string | 'all';
  onSelect: (t: string | 'all') => void;
}

export default function AnalyticsTeamList({ data, selected, onSelect }: Props) {
  const teams = data?.teams || [];
  return (
    <Card size="small" title="Команды">
      <List size="small">
        <List.Item onClick={() => onSelect('all')}
                   style={{ cursor: 'pointer', background: selected === 'all' ? '#1c3358' : undefined }}>
          Все команды
        </List.Item>
        {teams.map((t) => (
          <List.Item key={t.team || '_none_'}
                     onClick={() => onSelect(t.team || '_none_')}
                     style={{ cursor: 'pointer',
                              background: selected === t.team ? '#1c3358' : undefined }}>
            {t.team || 'Без команды'} <span style={{ color: '#7e94b8', marginLeft: 8 }}>
              {Math.round(t.totals.fact_hours)} ч
            </span>
          </List.Item>
        ))}
      </List>
    </Card>
  );
}
```

`AnalyticsFilters.tsx`:
```tsx
import { Space, Select, Input } from 'antd';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
}

export default function AnalyticsFilters({ urlParams, onChange }: Props) {
  return (
    <Space wrap style={{ marginBottom: 12 }}>
      <Input.Search
        placeholder="Поиск задачи"
        defaultValue={urlParams.taskQ}
        onSearch={(v) => onChange({ ...urlParams, taskQ: v || undefined })}
        style={{ width: 240 }}
      />
      {/* Сотрудник / Вид работ / Категория — TODO в Task 13 */}
    </Space>
  );
}
```

`AnalyticsTable.tsx`:
```tsx
import type { AnalyticsReportResponse } from '../../types/api';

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({ data, selectedTeam }: Props) {
  const teams = selectedTeam === 'all'
    ? data.teams
    : data.teams.filter(t => (t.team || '_none_') === selectedTeam);
  return (
    <div>
      {teams.map(t => (
        <div key={t.team || '_none_'} style={{ marginBottom: 24 }}>
          <h3>{t.team || 'Без команды'}</h3>
          <div style={{ color: '#7e94b8' }}>
            {Math.round(t.totals.fact_hours)} ч / {t.totals.issue_count} задач
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Сборка + smoke**

`npm run build` + `npm run dev` → /analytics показывает 2-колоночный layout, master-list слева, плейсхолдер таблицы справа.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AnalyticsPage.tsx frontend/src/components/analytics/
git commit -m "feat(analytics): page skeleton with master-detail layout"
```

---

### Task 13: AnalyticsTable — иерархическая таблица с раскрытием

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

- [ ] **Step 1: Полноценная таблица через AntD Table с expandable rows**

(Замена placeholder из Task 12.)

```tsx
import { useState } from 'react';
import { Table, Tag } from 'antd';
import type { ColumnsType, ExpandableConfig } from 'antd/es/table/interface';
import type {
  AnalyticsReportResponse, AnalyticsTeamNode, AnalyticsRoleNode,
  AnalyticsEmployeeNode, AnalyticsWorkTypeNode, AnalyticsCategoryNode,
  AnalyticsIssueNode, NodeTotals,
} from '../../types/api';

type Row =
  | { kind: 'team'; key: string; node: AnalyticsTeamNode }
  | { kind: 'role'; key: string; node: AnalyticsRoleNode }
  | { kind: 'emp'; key: string; node: AnalyticsEmployeeNode }
  | { kind: 'wt'; key: string; node: AnalyticsWorkTypeNode }
  | { kind: 'cat'; key: string; node: AnalyticsCategoryNode }
  | { kind: 'issue'; key: string; node: AnalyticsIssueNode };

function flattenTeam(t: AnalyticsTeamNode, prefix: string): Row[] {
  const out: Row[] = [{ kind: 'team', key: `${prefix}t`, node: t }];
  for (const r of t.roles) {
    out.push({ kind: 'role', key: `${prefix}t/r:${r.role_code}`, node: r });
    for (const e of r.employees) {
      out.push({ kind: 'emp', key: `${prefix}t/r:${r.role_code}/e:${e.employee_id}`, node: e });
      for (const w of e.work_types) {
        out.push({ kind: 'wt', key: `${prefix}t/r:${r.role_code}/e:${e.employee_id}/w:${w.work_type_id}`, node: w });
        for (const c of w.categories) {
          out.push({ kind: 'cat', key: `${prefix}t/r:${r.role_code}/e:${e.employee_id}/w:${w.work_type_id}/c:${c.category_code || '_none'}`, node: c });
          for (const i of c.issues) {
            out.push({
              kind: 'issue',
              key: `${prefix}t/r:${r.role_code}/e:${e.employee_id}/w:${w.work_type_id}/c:${c.category_code || '_none'}/i:${i.id}`,
              node: i,
            });
          }
        }
      }
    }
  }
  return out;
}

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({ data, selectedTeam }: Props) {
  const teams = selectedTeam === 'all'
    ? data.teams
    : data.teams.filter(t => (t.team || '_none_') === selectedTeam);

  // Преобразовать в форму с children для AntD Table tree mode
  const tableData = teams.map(t => buildAntTreeNode(t));

  const columns: ColumnsType<TreeNode> = [
    { title: 'Группа / Задача', dataIndex: 'label', key: 'label', width: 400 },
    { title: 'Часы факт', dataIndex: ['totals', 'fact_hours'], width: 100, align: 'right' },
    { title: 'Часы план', key: 'plan',
      render: (_, r) => r.totals.plan_hours != null ? Math.round(r.totals.plan_hours) : '—', width: 100, align: 'right' },
    { title: '% план', key: 'pct_plan',
      render: (_, r) => r.totals.pct_plan != null ? `${r.totals.pct_plan.toFixed(0)}%` : '—', width: 80, align: 'right' },
    { title: '% от итога', key: 'pct_total',
      render: (_, r) => `${r.totals.pct_total.toFixed(1)}%`, width: 90, align: 'right' },
    { title: 'Ворклогов', dataIndex: ['totals', 'worklog_count'], width: 90, align: 'right' },
    { title: 'Задач', dataIndex: ['totals', 'issue_count'], width: 70, align: 'right' },
    { title: 'Сотр.', dataIndex: ['totals', 'employee_count'], width: 70, align: 'right' },
    { title: 'Ср.мин', key: 'avg_min',
      render: (_, r) => r.totals.avg_worklog_minutes.toFixed(0), width: 80, align: 'right' },
  ];

  return (
    <Table<TreeNode>
      dataSource={tableData}
      columns={columns}
      rowKey="key"
      pagination={false}
      size="small"
      expandable={{
        defaultExpandAllRows: false,
      }}
    />
  );
}

interface TreeNode {
  key: string;
  label: React.ReactNode;
  totals: NodeTotals;
  children?: TreeNode[];
}

function buildAntTreeNode(t: AnalyticsTeamNode): TreeNode {
  return {
    key: `team:${t.team || '_none'}`,
    label: <b>{t.team || 'Без команды'}</b>,
    totals: t.totals,
    children: t.roles.map(r => ({
      key: `role:${r.role_code}`,
      label: <span style={{ color: r.role_color, marginLeft: 8 }}>{r.role_label}</span>,
      totals: r.totals,
      children: r.employees.map(e => ({
        key: `emp:${e.employee_id}`,
        label: <span style={{ marginLeft: 16 }}>{e.name}</span>,
        totals: e.totals,
        children: e.work_types.map(w => ({
          key: `wt:${w.work_type_id}`,
          label: <span style={{ marginLeft: 24 }}>{w.label}</span>,
          totals: w.totals,
          children: w.categories.map(c => ({
            key: `cat:${c.category_code || '_none'}`,
            label: (
              <span style={{ marginLeft: 32 }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: c.color, marginRight: 6 }} />
                {c.label}
              </span>
            ),
            totals: c.totals,
            children: c.issues.map(i => ({
              key: `issue:${i.id}`,
              label: <span style={{ marginLeft: 40 }}>
                <a href={`https://itgri.atlassian.net/browse/${i.key}`} target="_blank" rel="noreferrer">{i.key}</a>
                <Tag style={{ marginLeft: 6 }}>{i.status}</Tag>
                {' '}{i.summary}
              </span>,
              totals: i.totals,
            })),
          })),
        })),
      })),
    })),
  };
}
```

- [ ] **Step 2: Smoke-тест**

`npm run dev`, открыть /analytics, развернуть строки → видна иерархия + числа на каждом уровне.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(analytics): hierarchical table with expandable rows and aggregates"
```

---

### Task 14: Фильтры (сотрудник / вид работ / категория)

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsFilters.tsx`

- [ ] **Step 1: Полноценная строка фильтров**

```tsx
import { Space, Select, Input } from 'antd';
import { useEmployeesForFilter } from '../../hooks/useAnalytics'; // переиспользуем
import { useCategories } from '../../hooks/useCategories';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes'; // если есть; иначе создать

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
}

export default function AnalyticsFilters({ urlParams, onChange }: Props) {
  const { data: employees } = useEmployeesForFilter();
  const { labels: catLabels } = useCategories();
  const { data: workTypes } = useMandatoryWorkTypes();

  const update = (patch: Partial<typeof urlParams>) => onChange({ ...urlParams, ...patch });

  return (
    <Space wrap style={{ marginBottom: 12 }}>
      <Select
        allowClear placeholder="Сотрудник" style={{ minWidth: 200 }}
        showSearch optionFilterProp="label"
        value={urlParams.employeeId}
        onChange={(v) => update({ employeeId: v })}
        options={employees?.map(e => ({ value: e.id, label: e.display_name }))}
      />
      <Input.Search
        placeholder="Поиск задачи (ключ или текст)"
        defaultValue={urlParams.taskQ}
        onSearch={(v) => update({ taskQ: v || undefined })}
        style={{ width: 280 }}
      />
      <Select
        allowClear placeholder="Вид работ" style={{ minWidth: 200 }}
        value={urlParams.workType}
        onChange={(v) => update({ workType: v })}
        options={workTypes?.map(w => ({ value: w.code, label: w.label }))}
      />
      <Select
        allowClear placeholder="Категория" style={{ minWidth: 200 }}
        value={urlParams.category}
        onChange={(v) => update({ category: v })}
        options={Object.entries(catLabels).map(([code, label]) => ({ value: code, label }))}
      />
    </Space>
  );
}
```

- [ ] **Step 2: Если `useMandatoryWorkTypes` нет — создать**

```typescript
// frontend/src/hooks/useMandatoryWorkTypes.ts
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { MandatoryWorkTypeSchema } from '../types/api';

export function useMandatoryWorkTypes() {
  return useQuery({
    queryKey: ['mandatory-work-types'],
    queryFn: () => api.get<MandatoryWorkTypeSchema[]>('/mandatory-work-types'),
  });
}
```

(Если `useEmployeesForFilter` удаляется в Task 20 — здесь либо переиспользовать, либо создать локальный аналог через `/employees`.)

- [ ] **Step 3: Сборка + smoke**

`/analytics?employee=<id>` → таблица фильтрует по этому сотруднику.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsFilters.tsx frontend/src/hooks/useMandatoryWorkTypes.ts
git commit -m "feat(analytics): filter row (employee/task/work_type/category)"
```

---

### Task 15: Настройка видимости колонок

**Files:**
- Create: `frontend/src/components/analytics/AnalyticsColumnSettings.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 1: Компонент модалки**

```tsx
import { Modal, Checkbox, Button } from 'antd';
import { useState } from 'react';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';

const COLUMN_LABELS: Record<string, string> = {
  plan_hours: 'Часы план',
  pct_plan: '% план',
  pct_total: '% от итога',
  worklog_count: 'Ворклогов',
  issue_count: 'Задач',
  employee_count: 'Сотрудников',
  avg_worklog_minutes: 'Средняя длит. ворклога',
  status: 'Статус',
  issue_type: 'Тип задачи',
  category: 'Категория',
  last_worklog_at: 'Последний ворклог',
  assignee_name: 'Исполнитель',
};

export default function AnalyticsColumnSettings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { visible, allColumns, setVisible } = useAnalyticsColumns();
  const [draft, setDraft] = useState(visible);

  return (
    <Modal title="Настройка столбцов" open={open} onCancel={onClose}
           onOk={() => { setVisible(draft); onClose(); }}
           okText="Применить" cancelText="Отмена">
      <Checkbox.Group
        value={draft}
        onChange={(v) => setDraft(v as string[])}
        options={allColumns.map(c => ({ value: c, label: COLUMN_LABELS[c] || c }))}
      />
    </Modal>
  );
}
```

- [ ] **Step 2: Кнопка в AnalyticsPage и проброс в Table**

В `AnalyticsPage.tsx`:
```tsx
const [colSettingsOpen, setColSettingsOpen] = useState(false);
...
<Button onClick={() => setColSettingsOpen(true)}>Настройка столбцов</Button>
<AnalyticsColumnSettings open={colSettingsOpen} onClose={() => setColSettingsOpen(false)} />
```

- [ ] **Step 3: Учитывать видимость в AnalyticsTable**

В Table.tsx:
```tsx
const { visible } = useAnalyticsColumns();

const columns: ColumnsType<TreeNode> = [
  { title: 'Группа / Задача', dataIndex: 'label', key: 'label', width: 400 },
  { title: 'Часы факт', dataIndex: ['totals', 'fact_hours'], width: 100, align: 'right' },
  ...(visible.includes('plan_hours') ? [{ title: 'Часы план', ..., }] : []),
  ...(visible.includes('pct_plan') ? [{ title: '% план', ... }] : []),
  // и т. д.
];
```

(Аналогично для всех 12 настраиваемых колонок.)

- [ ] **Step 4: Smoke-test**

Открыть «Настройка столбцов» → снять галочку «Часы план» → таблица перерисовывается без этой колонки. Сменить пользователя/перезагрузка → настройка сохранена.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsColumnSettings.tsx frontend/src/components/analytics/AnalyticsTable.tsx frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(analytics): per-user column visibility settings"
```

---

### Task 16: Разворачивание ворклогов задачи (inline + drawer)

**Files:**
- Create: `frontend/src/components/analytics/AnalyticsWorklogsBlock.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

- [ ] **Step 1: Блок-список ворклогов**

```tsx
import { Spin, Empty } from 'antd';
import { useIssueWorklogs } from '../../hooks/useIssueWorklogs';

export default function AnalyticsWorklogsBlock({ issueId, start, end }: { issueId: string; start: string; end: string }) {
  const { data, isLoading } = useIssueWorklogs(issueId, start, end);
  if (isLoading) return <Spin />;
  if (!data?.length) return <Empty description="Нет ворклогов" />;
  return (
    <table style={{ width: '100%', fontSize: 12 }}>
      <thead>
        <tr style={{ color: '#7e94b8' }}>
          <th align="left">Когда</th><th align="left">Кто</th><th align="right">Часы</th><th align="left">Комментарий</th>
        </tr>
      </thead>
      <tbody>
        {data.map(w => (
          <tr key={w.worklog_id}>
            <td>{new Date(w.started_at).toLocaleString('ru-RU')}</td>
            <td>{w.employee_name}</td>
            <td align="right">{w.hours.toFixed(2)}</td>
            <td>{w.comment}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Inline expand на уровне задачи в AnalyticsTable**

Расширить Table `expandable.expandedRowRender`: для строк `kind: 'issue'` показывать `<AnalyticsWorklogsBlock>` (если `worklogMode === 'inline'`). Для `worklogMode === 'drawer'` — клик по строке открывает Drawer с тем же блоком.

```tsx
expandable={{
  expandedRowRender: (record) => {
    if (!record.key.startsWith('issue:')) return null;
    if (worklogMode !== 'inline') return null;
    const issueId = record.key.replace('issue:', '');
    return <AnalyticsWorklogsBlock issueId={issueId} start={periodStart} end={periodEnd} />;
  },
  rowExpandable: (record) => record.key.startsWith('issue:'),
}}
```

Drawer-режим: добавить state `drawerIssueId`, при клике на issue-строку (`onRow.onClick`) открывать Drawer.

- [ ] **Step 3: Smoke-test**

Развернуть задачу → видны её ворклоги; переключить тогл «inline → drawer» → клик на задачу открывает Drawer.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsWorklogsBlock.tsx frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(analytics): worklog expand inline + drawer"
```

---

### Task 17: XLSX экспорт

**Files:**
- Modify: `app/services/export_service.py`
- Modify: `app/api/endpoints/analytics.py`
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 1: Сервис export**

В `export_service.py` добавить:

```python
    def export_analytics_report_xlsx(
        self,
        report: "AnalyticsReportResponse",
        visible_columns: list[str],
    ) -> bytes:
        from io import BytesIO
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Аналитика"

        # Header row
        base_headers = ["Команда", "Роль", "Сотрудник", "Вид работ", "Категория",
                        "Ключ", "Заголовок", "Тип", "Статус", "Часы факт"]
        opt_headers = []
        opt_keys = []
        for col in visible_columns:
            label = {
                "plan_hours": "Часы план", "pct_plan": "% план", "pct_total": "% от итога",
                "worklog_count": "Ворклогов", "issue_count": "Задач",
                "employee_count": "Сотрудников", "avg_worklog_minutes": "Ср.мин",
                "category": "Категория (подп.)", "last_worklog_at": "Последний ворклог",
                "assignee_name": "Исполнитель", "issue_type": "Тип (подп.)",
            }.get(col)
            if label:
                opt_headers.append(label)
                opt_keys.append(col)
        ws.append(base_headers + opt_headers)

        # Flatten — по задачам
        for team in report.teams:
            for role in team.roles:
                for emp in role.employees:
                    for wt in emp.work_types:
                        for cat in wt.categories:
                            for issue in cat.issues:
                                row = [
                                    team.team or "Без команды",
                                    role.role_label,
                                    emp.name,
                                    wt.label,
                                    cat.label,
                                    issue.key, issue.summary, issue.issue_type, issue.status,
                                    issue.totals.fact_hours,
                                ]
                                for k in opt_keys:
                                    if k == "plan_hours": row.append(issue.totals.plan_hours or "")
                                    elif k == "pct_plan": row.append(issue.totals.pct_plan or "")
                                    elif k == "pct_total": row.append(issue.totals.pct_total)
                                    elif k == "worklog_count": row.append(issue.totals.worklog_count)
                                    elif k == "issue_count": row.append(issue.totals.issue_count)
                                    elif k == "avg_worklog_minutes": row.append(issue.totals.avg_worklog_minutes)
                                    elif k == "last_worklog_at": row.append(issue.last_worklog_at.isoformat() if issue.last_worklog_at else "")
                                    elif k == "assignee_name": row.append(issue.assignee_name or "")
                                    else: row.append("")
                                ws.append(row)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [ ] **Step 2: Эндпоинт**

В `app/api/endpoints/analytics.py`:

```python
from fastapi.responses import Response


@router.get("/report/export.xlsx")
def export_report_xlsx(
    year: int, quarter: int,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    teams: Optional[str] = None,
    employee_id: Optional[str] = None,
    task_query: Optional[str] = None,
    work_type_codes: Optional[str] = None,
    category_codes: Optional[str] = None,
    columns: Optional[str] = None,
    db: Session = Depends(get_db),
):
    teams_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    wt_codes = [c.strip() for c in work_type_codes.split(",") if c.strip()] if work_type_codes else None
    cat_codes = [c.strip() for c in category_codes.split(",") if c.strip()] if category_codes else None
    cols = [c.strip() for c in columns.split(",") if c.strip()] if columns else []

    report = AnalyticsService(db).get_hierarchical_report(
        year=year, quarter=quarter, month=month,
        start_date=start_date, end_date=end_date,
        teams=teams_list, employee_id=employee_id,
        task_query=task_query, work_type_codes=wt_codes, category_codes=cat_codes,
    )
    blob = ExportService(db).export_analytics_report_xlsx(report, cols)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=analytics_report.xlsx"},
    )
```

- [ ] **Step 3: Кнопка в AnalyticsPage**

```tsx
import { downloadFile } from '../utils/download'; // или свой helper

<Button onClick={() => {
  const params = new URLSearchParams({
    year: String(period.year),
    quarter: String(period.quarter),
    ...(period.month ? { month: String(period.month) } : {}),
    ...(employeeId ? { employee_id: employeeId } : {}),
    ...(taskQ ? { task_query: taskQ } : {}),
    ...(workType ? { work_type_codes: workType } : {}),
    ...(category ? { category_codes: category } : {}),
    ...(visibleColumns.length ? { columns: visibleColumns.join(',') } : {}),
  });
  window.location.href = `${import.meta.env.VITE_API_BASE_URL}/analytics/report/export.xlsx?${params}`;
}}>Экспорт XLSX</Button>
```

- [ ] **Step 4: Smoke-test**

Клик по кнопке → скачивается `analytics_report.xlsx` с применёнными фильтрами и колонками.

- [ ] **Step 5: Commit**

```bash
git add app/services/export_service.py app/api/endpoints/analytics.py frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(analytics): xlsx export with filters and visible columns"
```

---

# Фаза 4 — Drill-down с виджетов + удаление старого кода

### Task 18: Drill-down из NormWorkWidget

**Files:**
- Modify: `frontend/src/components/dashboard/NormWorkWidget.tsx`

- [ ] **Step 1: Сделать строки кликабельными → navigate**

```tsx
import { useNavigate } from 'react-router';

function WorkTypeRow({ wt, t, onOpen }: { wt: NormWorkTypeBreakdown; t: Thresholds; onOpen: () => void }) {
  return (
    <div onClick={onOpen} style={{
      display: 'grid', ..., cursor: 'pointer',
    }}>
      ...
    </div>
  );
}

function EmployeeBlock({ emp, role, t }: { emp: NormWorkEmployee; role: NormWorkRoleGroup; t: Thresholds }) {
  const navigate = useNavigate();
  const open = (extra: Record<string, string>) => {
    const params = new URLSearchParams({ employee: emp.employee_id, ...extra });
    navigate(`/analytics?${params.toString()}`);
  };
  return (
    <div>
      <div onClick={() => open({})} style={{ cursor: 'pointer', ... }}>
        {/* employee header */}
      </div>
      ...
      {emp.work_types.map((wt) => (
        <WorkTypeRow key={wt.work_type_id} wt={wt} t={t}
          onOpen={() => open({
            work_type: wt.work_type_id === '__unmapped__' ? '__unmapped__' : (wt.work_type_id),
          })}
        />
      ))}
    </div>
  );
}
```

(Заметка: `wt.work_type_id` — это UUID, а в /analytics фильтр работает по code. Нужен mapping. Передавать code из бэкенда: добавить в `NormWorkTypeBreakdown` поле `work_type_code`, либо принимать UUID на фильтре. Простейшее — на фронте маппить через `useMandatoryWorkTypes` data; либо на бэкенде в схему добавить `code`.)

Решение: в Task 4 эндпоинт `/analytics/report` принимает `work_type_codes`. Проще — передать в `NormWorkTypeBreakdown` поле `code`.

- [ ] **Step 1а: Расширить схему `NormWorkTypeBreakdown`**

В `app/schemas/dashboard.py`:
```python
class NormWorkTypeBreakdown(BaseModel):
    work_type_id: str
    work_type_code: str | None = None  # NEW
    label: str
    plan_hours: float
    fact_hours: float
    pct: float
```

В `analytics_service.get_dashboard_norm_work` при сборке `wt_breakdowns` добавить `work_type_code`:
```python
wt_breakdowns.append(NormWorkTypeBreakdown(
    work_type_id=wt.id,
    work_type_code=wt.code,
    ...
))
```

И для orphan:
```python
wt_breakdowns.insert(other_foreign_idx, NormWorkTypeBreakdown(
    work_type_id=ORPHAN_WT_ID,
    work_type_code="__unmapped__",
    ...
))
```

- [ ] **Step 2: Использовать `work_type_code` на клике**

```tsx
onOpen={() => open({ work_type: wt.work_type_code || '' })}
```

- [ ] **Step 3: Smoke-test**

В виджете кликнуть по строке вида работ Шутова → открывается `/analytics?employee=<id>&work_type=<code>` с применёнными фильтрами.

- [ ] **Step 4: Commit**

```bash
git add app/schemas/dashboard.py app/services/analytics_service.py frontend/src/components/dashboard/NormWorkWidget.tsx
git commit -m "feat(dashboard): NormWork rows drill into Analytics report"
```

---

### Task 19: Drill-down из CategoryWidget

**Files:**
- Modify: `frontend/src/components/dashboard/CategoryWidget.tsx`

- [ ] **Step 1: Кликабельные плитки и карточки**

```tsx
import { useNavigate } from 'react-router';

function HeatmapGrid({ items }: { items: CategoryMetaItem[] }) {
  const navigate = useNavigate();
  return (
    <div>
      {cells.map((c) => {
        if ('_overflow' in c) return ...;
        return (
          <div onClick={() => navigate(`/analytics?category=${item.key}`)}
               style={{ ..., cursor: 'pointer' }}>
            ...
          </div>
        );
      })}
    </div>
  );
}

function EmployeesActivity({ items, thresholds }) {
  const navigate = useNavigate();
  return items.map(emp => (
    <div onClick={() => navigate(`/analytics?employee=${emp.employee_id}`)}
         style={{ ..., cursor: 'pointer' }}>
      ...
    </div>
  ));
}
```

- [ ] **Step 2: Smoke-test**

Клик по плитке категории → `/analytics?category=<code>` с фильтром.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/CategoryWidget.tsx
git commit -m "feat(dashboard): CategoryWidget drill into Analytics report"
```

---

### Task 20: Удаление старого кода Аналитики

**Files (delete):**
- `frontend/src/hooks/useAnalytics.ts` (весь файл, кроме `useEmployeesForFilter` если переиспользуется в новом отчёте — мигрировать в общий хук)
- Старые методы в `frontend/src/api/analytics.ts` (`getHoursByEmployee`, `getHoursByProject`, `getHoursByCategory`, `getHoursByPeriod`, `getContextSwitching`)
- Старые эндпоинты в `app/api/endpoints/analytics.py` (`/hours-by-{employee|project|category|period}`, `/context-switching`)
- Соответствующие методы в `AnalyticsService` (`get_hours_by_employee`, `get_hours_by_project`, etc.)
- Старые тесты этих эндпоинтов в `tests/test_analytics_endpoints.py` (если есть)

- [ ] **Step 1: grep по старым именам**

```bash
grep -rn "getHoursByEmployee\|getHoursByProject\|getHoursByCategory\|getHoursByPeriod\|getContextSwitching\|useHoursByEmployee\|useHoursByProject\|useHoursByCategory\|useHoursByPeriod\|useContextSwitching" frontend/src
grep -rn "hours_by_employee\|hours_by_project\|hours_by_category\|hours_by_period\|context_switching\|get_hours_by_\|get_context_switching" app
```

Все найденные — кандидаты на удаление, кроме мест в новой странице (если использовались переходно).

- [ ] **Step 2: Удалить файлы / методы**

```bash
git rm <files>  # если файлы целиком
# для частичных — удалить руками через Edit
```

Использовать Edit для частичной чистки `app/api/endpoints/analytics.py` и `app/services/analytics_service.py`.

`useEmployeesForFilter` — переиспользовать (он нужен в фильтрах Аналитики). Перенести в `frontend/src/hooks/useEmployees.ts` если хочется логически отделить, либо оставить.

- [ ] **Step 3: Удалить старые тесты**

`tests/test_analytics_endpoints.py` (если он содержит только старые тесты) — удалить. Если миксован — выпиливать только старые `def test_*hours_by_*` и `test_*context_switching*`.

- [ ] **Step 4: Прогон тестов**

```bash
py -3.10 -m pytest tests/ -v
```

Expected: всё, что осталось, зелёное.

- [ ] **Step 5: Frontend build + smoke**

```bash
cd frontend && npm run build && npm run lint
```

Expected: success, нет dangling imports старых хуков.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(analytics): remove old hours-by-* and context-switching code"
```

---

### Task 21: Финальная верификация + push

- [ ] **Step 1: Полный backend прогон**

```bash
py -3.10 -m pytest tests/ -v
```

- [ ] **Step 2: Frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

- [ ] **Step 3: Локальный smoke**

```bash
.\scripts\smoke-local.ps1
```

Открыть /dashboard, /analytics. Кликать по виджетам — Аналитика открывается с фильтрами. Менять период в шапке — все страницы реагируют. Проверить экспорт XLSX, переключатель ворклогов, настройку столбцов.

- [ ] **Step 4: Push**

```bash
git push origin main
```

- [ ] **Step 5: Обновить memory MEMORY.md**

Добавить запись `project_analytics_report_shipped.md`:

```
- [Иерархический отчёт Аналитики shipped](project_analytics_report_shipped.md) — 2026-05-XX: master-detail layout, drill-down с виджетов, глобальный пикер периода в шапке, per-user колонки
```

И отдельный файл `project_analytics_report_shipped.md` с body:

```markdown
---
name: Иерархический отчёт Аналитики shipped
description: New /analytics page (master-detail, hierarchy Команда→Роль→...→Задача→ворклоги, drill-down с дашборда, global header period picker)
type: project
---

2026-05-XX: новая Аналитика заменила старые 5 вкладок. Master-detail layout (вариант C), иерархическая таблица с раскрытием на 6 уровнях, ленивая подгрузка ворклогов. Глобальный пикер периода в шапке (User.selected_period). Per-user видимость колонок (User.analytics_columns). Drill-down с виджетов NormWork (3 точки) и CategoryWidget (2 точки) через URL params. Старые эндпоинты hours-by-* и context-switching удалены.

Спек: docs/superpowers/specs/2026-05-01-analytics-hierarchical-report-design.md
Plan: docs/superpowers/plans/2026-05-01-analytics-hierarchical-report.md
```

---

## Self-Review

**Spec coverage:**
- ✅ Layout master-detail (вариант C) → Task 12-13
- ✅ Глобальный пикер периода в шапке → Task 6-9
- ✅ Локальный override диапазона дат → Task 12 (DatePicker.RangePicker)
- ✅ Иерархия 6 уровней + ленивая подгрузка ворклогов → Task 2, 5, 13, 16
- ✅ Фильтры (сотрудник/задача/виды работ/категории) → Task 14
- ✅ Полный набор колонок + настройка видимости (per-user) → Task 11 (типы), 15 (настройка), 7 (API), 6 (миграция)
- ✅ Drill-down контракт URL → Task 18-19
- ✅ Переключатель inline/drawer ворклогов → Task 16
- ✅ Экспорт XLSX → Task 17
- ✅ Удаление старой Аналитики → Task 20

**Placeholders:** нет.

**Type consistency:**
- `work_type_id` (UUID) vs `work_type_code` — Task 18 расширяет схему `NormWorkTypeBreakdown` полем `work_type_code`, чтобы drill-down принимал code. ОК.
- `analytics_columns_raw` поле и property `analytics_columns` — соответствуют паттерну `selected_teams_raw`/`selected_teams`. ОК.
- В тесте Task 2 Step 1 ссылается на `Issue.assignee_name` — поле в модели Issue: убедиться, что есть. Если нет — заменить на `None` placeholder. **TODO в реализации:** проверить наличие `Issue.assignee_name` в `app/models/issue.py`; если нет — добавить миграцию или использовать другую таблицу-источник (например, JOIN на Worklog.employee для последнего исполнителя).

**Ambiguity:**
- `useEmployeesForFilter` остаётся жить — переиспользуется в `AnalyticsFilters`; в Task 20 его НЕ удалять. Зафиксировать в Step 2.

**Out-of-scope items** (записаны в спек, не в этот план):
- Серверная пагинация при «Все команды»
- Сохранённые пресеты фильтров
- Графики/диаграммы поверх таблицы
- Свободный порядок группировки
- Поиск по комментариям ворклогов / тегам / целям
- Drill-up со страницы задачи
- Автопривязка категорий без вида работ
- Перепривязка «Технический долг» → правка справочника
- XLSX с иерархическими подитогами

---

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-05-01-analytics-hierarchical-report.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch fresh subagent per task, two-stage review between tasks (как `feedback_subagent_flow` в memory).

**2. Inline Execution** — выполнить задачи последовательно в этой сессии с checkpoint'ами для ревью.

Учитывая объём (~21 task, бэкенд+фронт, миграция БД), **рекомендую Subagent-Driven**. Иду в этом режиме?
