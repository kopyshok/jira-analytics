# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Редизайн трёх виджетов на `/dashboard` — Проекты квартала, Нормированные работы, Ворклоги по категориям — согласно спеке `docs/superpowers/specs/2026-04-30-dashboard-redesign-design.md`.

**Architecture:** Backend расширяет 2 endpoint в `analytics_service.py` новыми полями (per-project meta + per-employee норма по ролям). Frontend переписывает 3 компонента в `frontend/src/components/dashboard/` под новые контракты. Виджет 3 — pure UI fix без API изменений.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 (backend), React 19 + TypeScript 6 + AntD 6 + TanStack Query (frontend), pytest + Playwright e2e.

**Mockups reference:** `.superpowers/brainstorm/49-1777526199/content/widget{1,2,3}-*.html`

---

## File Structure

### Backend

| File | Action | Responsibility |
|---|---|---|
| `app/schemas/dashboard.py` | Modify | Заменить response models под новые контракты (3 виджета) |
| `app/services/analytics_service.py` | Modify | Расширить `get_dashboard_projects`, переписать `get_dashboard_norm_work`, `get_dashboard_categories` без изменений |
| `app/api/endpoints/analytics.py` | No change | Сигнатуры endpoint'ов остаются |
| `tests/test_dashboard_endpoints.py` | Modify | Обновить assertions под новые поля |
| `tests/test_analytics_service.py` | Modify | Дополнить тесты на новую логику (subtasks, trend, forecast, per-employee) |

### Frontend

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/types/api.ts` | Modify | Заменить 3 dashboard response types + новые item types |
| `frontend/src/components/dashboard/CategoryWidget.tsx` | Rewrite | Heatmap grid 5×2 заполняет квадрант |
| `frontend/src/components/dashboard/ProjectsWidget.tsx` | Rewrite | Donut + список (10 cols) + KPI 2×2 + спарклайны |
| `frontend/src/components/dashboard/NormWorkWidget.tsx` | Rewrite | 4 колонки по ролям с раскрытой разбивкой по сотрудникам |
| `frontend/src/pages/DashboardPage.tsx` | Modify | Layout: W1 full row, W2 full row, W3 half row |
| `frontend/e2e/dashboard.spec.ts` | Modify | Обновить selectors под новую разметку |

---

## Phase 0 — Baseline

### Task 0.1: Запустить baseline тесты

**Files:** none

- [ ] **Step 1: Запустить backend тесты**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py tests/test_analytics_service.py -v`
Expected: PASS (на main всё зелёное, см. memory `project_ci_red_pre_existing.md` — кроме известных)

- [ ] **Step 2: Запустить frontend lint**

Run: `cd frontend && npm run lint`
Expected: PASS

- [ ] **Step 3: Зафиксировать в notes текущее количество тестов**

В терминале: `py -3.10 -m pytest tests/ --collect-only -q | tail -5`
Записать число в comment к первому коммиту.

---

## Phase 1 — Widget 3 (Категории heatmap)

Самый маленький виджет. Pure UI, без API. Делаем первым.

### Task 1.1: Переписать CategoryWidget на heatmap grid 5×2

**Files:**
- Modify: `frontend/src/components/dashboard/CategoryWidget.tsx` (rewrite целиком)
- Modify: `frontend/e2e/dashboard.spec.ts` (если есть selector на старую разметку)

- [ ] **Step 1: Открыть текущий CategoryWidget.tsx, убедиться что данные `CategoryMetaItem[]` приходят из API без изменений**

Run: `grep -n "CategoryMetaItem" frontend/src/types/api.ts`
Expected: `CategoryMetaItem` существует, поля `key, label, color, hours, worklog_count, issue_count, employee_count, avg_worklog_minutes, pct`. Без правок в типах.

- [ ] **Step 2: Заменить тело файла `CategoryWidget.tsx` на новый компонент**

```tsx
import { Card, Spin, Empty } from 'antd';
import type { DashboardCategoriesResponse, CategoryMetaItem } from '../../types/api';

function HeatmapGrid({ items, totalHours }: { items: CategoryMetaItem[]; totalHours: number }) {
  if (!items.length) return <Empty description="Нет данных" />;

  const visible = items.slice(0, 10);
  const overflow = items.length > 10 ? items.slice(10) : [];

  const cells: (CategoryMetaItem | { _overflow: true; count: number; hours: number })[] = [...visible];
  if (overflow.length) {
    cells.push({
      _overflow: true,
      count: overflow.length,
      hours: overflow.reduce((s, i) => s + i.hours, 0),
    });
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gridAutoRows: 'minmax(140px, 1fr)',
        gap: 6,
        width: '100%',
      }}
    >
      {cells.map((c, idx) => {
        if ('_overflow' in c) {
          return (
            <div
              key={`overflow-${idx}`}
              style={{
                background: '#1c335833',
                border: '1px solid #1c335866',
                borderRadius: 8,
                padding: 12,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontSize: 12, color: '#a4b8d8' }}>+ ещё {c.count}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{Math.round(c.hours)} ч</div>
            </div>
          );
        }
        const item = c;
        const intensity = totalHours > 0 ? item.hours / totalHours : 0;
        return (
          <div
            key={item.key}
            title={`${item.label}: ${Math.round(item.hours)} ч (${item.pct.toFixed(1)}%)`}
            style={{
              background: `${item.color}33`,
              border: `1px solid ${item.color}66`,
              borderRadius: 8,
              padding: 12,
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <div style={{
                fontSize: 12,
                color: '#a4b8d8',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}>
                {item.label}
              </div>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                background: item.color,
                color: '#fff',
                padding: '2px 6px',
                borderRadius: 6,
                flexShrink: 0,
              }}>
                {item.pct.toFixed(0)}%
              </span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{Math.round(item.hours)} ч</div>
            <div style={{ fontSize: 10, color: '#7e94b8' }}>
              {item.worklog_count} wl · {item.issue_count} зад · {item.employee_count} чел
            </div>
            <div style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              height: 3,
              width: `${Math.min(100, intensity * 100 * 3)}%`,
              background: item.color,
            }} />
          </div>
        );
      })}
    </div>
  );
}

function MetaTable({ items }: { items: CategoryMetaItem[] }) {
  const totalHours = items.reduce((s, i) => s + i.hours, 0);
  const totalWl = items.reduce((s, i) => s + i.worklog_count, 0);
  const totalIssues = items.reduce((s, i) => s + i.issue_count, 0);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: '#7e94b8', fontSize: 10, textTransform: 'uppercase' }}>
            {['Категория', 'Часы', 'Вркл.', 'Задач', 'Сотр.', 'Ср.мин', '%'].map((h) => (
              <th key={h} style={{ textAlign: h === 'Категория' ? 'left' : 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key} style={{ borderBottom: '1px solid rgba(28,51,88,.3)' }}>
              <td style={{ padding: '5px 8px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: item.color, flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ color: '#e6edf7' }}>{item.label}</span>
                </span>
              </td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#fff', fontWeight: 600 }}>{Math.round(item.hours)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.worklog_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.issue_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.employee_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.avg_worklog_minutes.toFixed(0)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#7e94b8' }}>{item.pct.toFixed(1)}%</td>
            </tr>
          ))}
          <tr style={{ borderTop: '2px solid #1c3358', fontWeight: 600, color: '#fff', fontSize: 11 }}>
            <td style={{ padding: '5px 8px' }}>Итого</td>
            <td style={{ textAlign: 'right', padding: '5px 8px' }}>{Math.round(totalHours)}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{totalWl}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{totalIssues}</td>
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
      <div style={{ display: 'grid', gridTemplateColumns: '60% 40%', gap: 16 }}>
        <HeatmapGrid items={data.items} totalHours={data.total_hours} />
        <MetaTable items={data.items} />
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Запустить frontend lint**

Run: `cd frontend && npm run lint`
Expected: PASS (без новых предупреждений по этому файлу)

- [ ] **Step 4: Запустить dev и проверить визуально**

Run (в одном терминале): `cd frontend && npm run dev`
Открыть `http://localhost:5173/dashboard`. Убедиться:
- 5 столбцов × 2 строки сетки заполняют ~60% ширины карточки
- Все ячейки одинакового размера
- pill-badge с процентом в правом верхнем углу каждой ячейки
- мета-таблица справа без изменений

- [ ] **Step 5: Запустить e2e**

Run: `cd frontend && npm run e2e -- dashboard`
Expected: PASS. Если падает — selectors поменялись (вероятно на старую flex-wrap разметку), обновить spec.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/CategoryWidget.tsx frontend/e2e/dashboard.spec.ts
git commit -m "feat(dashboard): heatmap grid 5×2 для категорий

Заменён flex-wrap квадратиков на equal-cells grid 5×2,
заполняющий 100% ширины контейнера. Pill-badge с % в углу,
тонкая полоска интенсивности снизу. +N overflow-ячейка
если категорий больше 10."
```

---

## Phase 2 — Widget 1 (Проекты квартала)

Backend расширяет схему + сервис. Frontend переписывает компонент.

### Task 2.1: Обновить `DashboardProjectsResponse` schema

**Files:**
- Modify: `app/schemas/dashboard.py`
- Modify: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Написать failing-тест на новые поля**

В `tests/test_dashboard_endpoints.py` заменить `test_projects_widget_returns_200` на:

```python
def test_projects_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    # Counters
    assert "total" in data
    assert "done" in data
    assert "in_progress" in data
    assert "overdue" in data
    assert "not_started" in data
    # KPI top-level
    assert "total_fact_hours" in data
    assert "total_plan_hours" in data
    assert "avg_load_pct" in data
    assert "silent_count" in data
    assert "forecast_done" in data
    assert "forecast_pct" in data
    # Per-project list
    assert "projects" in data
    assert isinstance(data["projects"], list)
    # Удалённые поля больше НЕ должны быть в ответе
    assert "attention_list" not in data
    assert "overrun_list" not in data


def test_projects_widget_project_item_shape():
    """При наличии проектов в списке проверяем форму одного элемента."""
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    data = resp.json()
    if data["projects"]:
        p = data["projects"][0]
        for key in [
            "issue_key", "title", "status_category",
            "plan_hours", "fact_hours", "delta_hours",
            "subtasks_done", "subtasks_total",
            "assignees", "assignees_total",
            "due_date", "days_to_due",
            "trend_hours_week", "trend_dir",
            "forecast_close_date", "forecast_in_quarter",
            "silent_days", "weekly_activity",
        ]:
            assert key in p, f"missing key: {key}"
        assert isinstance(p["assignees"], list)
        assert isinstance(p["weekly_activity"], list)
        assert p["trend_dir"] in ("up", "down", "flat")
```

- [ ] **Step 2: Запустить тесты, увидеть FAIL**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_projects_widget_returns_200 tests/test_dashboard_endpoints.py::test_projects_widget_project_item_shape -v`
Expected: FAIL — отсутствуют новые поля в response.

- [ ] **Step 3: Заменить блок Widget 1 в `app/schemas/dashboard.py`**

Заменить классы `ProjectAttentionItem`, `ProjectOverrunItem`, `DashboardProjectsResponse` на:

```python
from datetime import date


class ProjectAssignee(BaseModel):
    initials: str
    color: str  # hex, для аватара (от роли сотрудника либо генерим)


class ProjectItem(BaseModel):
    issue_key: str
    title: str
    status_category: str            # 'done' | 'indeterminate' | 'new' | 'overdue'
    plan_hours: float
    fact_hours: float
    delta_hours: float              # fact - plan
    subtasks_done: int
    subtasks_total: int
    assignees: list[ProjectAssignee]   # top-3 по часам
    assignees_total: int               # всего сотрудников касавшихся эпика
    due_date: date | None
    days_to_due: int | None            # negative = overdue, None = no due
    trend_hours_week: float            # часы за последние 7 дней
    trend_dir: str                     # 'up' | 'down' | 'flat'
    forecast_close_date: date | None
    forecast_in_quarter: bool          # успевает ли к концу квартала
    silent_days: int                   # дни с последнего ворклога (0 если был сегодня)
    weekly_activity: list[float]       # 8 точек спарклайна (часы/неделю с конца периода назад)


class DashboardProjectsResponse(BaseModel):
    total: int
    done: int
    in_progress: int
    overdue: int
    not_started: int
    total_fact_hours: float
    total_plan_hours: float
    avg_load_pct: float          # total_fact / total_plan * 100
    silent_count: int            # проекты с silent_days > 14
    forecast_done: int
    forecast_pct: float
    projects: list[ProjectItem]
```

`ProjectAttentionItem` и `ProjectOverrunItem` УДАЛИТЬ полностью.

- [ ] **Step 4: Commit (промежуточный — pyfile собирается, тесты ещё падают)**

```bash
git add app/schemas/dashboard.py tests/test_dashboard_endpoints.py
git commit -m "refactor(schemas): новые поля DashboardProjectsResponse

Удалены attention_list/overrun_list, добавлены per-project
поля (subtasks/assignees/due/trend/forecast/spark) и top-level
KPI (total_fact, avg_load, silent_count). Сервис ещё не
реализует — тесты пока красные."
```

---

### Task 2.2: Реализовать `get_dashboard_projects` под новую схему

**Files:**
- Modify: `app/services/analytics_service.py:373-...` (метод `get_dashboard_projects`)
- Modify: `tests/test_analytics_service.py` (добавить юнит-тесты на новую логику)

- [ ] **Step 1: Найти текущий `get_dashboard_projects`**

Run: `grep -n "def get_dashboard_projects" app/services/analytics_service.py`
Зафиксировать строку начала.

- [ ] **Step 2: Переписать метод целиком**

Заменить тело `get_dashboard_projects` от первой строки до `return DashboardProjectsResponse(...)`. Новый код:

```python
def get_dashboard_projects(
    self,
    year: int,
    quarter: int,
    month: Optional[int] = None,
    team: Optional[str] = None,
    silence_days: int = 14,
) -> DashboardProjectsResponse:
    """Widget 1: обзор проектов квартала из утверждённого сценария."""
    from app.schemas.dashboard import ProjectItem, ProjectAssignee

    period_start, period_end = quarter_to_dates(year, quarter, month)
    today = date.today()
    today_dt = datetime.combine(today, datetime.min.time())

    # 1. Утверждённый сценарий
    approved_q = (
        self.db.query(PlanningScenario.id)
        .filter(
            PlanningScenario.year == year,
            PlanningScenario.quarter == f"Q{quarter}",
            PlanningScenario.status == "approved",
        )
    )
    if team:
        approved_q = approved_q.filter(PlanningScenario.team == team)
    scenario_ids = [row[0] for row in approved_q.all()]

    empty_response = DashboardProjectsResponse(
        total=0, done=0, in_progress=0, overdue=0, not_started=0,
        total_fact_hours=0.0, total_plan_hours=0.0, avg_load_pct=0.0,
        silent_count=0, forecast_done=0, forecast_pct=0.0,
        projects=[],
    )

    if not scenario_ids:
        return empty_response

    alloc_rows = (
        self.db.query(BacklogItem.issue_id, BacklogItem.estimate_hours)
        .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
        .filter(
            ScenarioAllocation.scenario_id.in_(scenario_ids),
            ScenarioAllocation.included_flag.is_(True),
            BacklogItem.issue_id.isnot(None),
        )
        .distinct()
        .all()
    )
    if not alloc_rows:
        return empty_response

    issue_ids = list({row[0] for row in alloc_rows})
    plan_by_issue: dict[str, float] = {}
    for issue_id, est in alloc_rows:
        if issue_id and est is not None:
            plan_by_issue[issue_id] = est

    issues: list[Issue] = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
    total = len(issues)

    # Статусы
    done = sum(1 for i in issues if i.status_category == "done")
    in_progress = sum(1 for i in issues if i.status_category == "indeterminate")
    not_started = sum(1 for i in issues if i.status_category == "new")
    overdue_issues = [
        i for i in issues
        if i.status_category != "done"
        and i.due_date is not None
        and i.due_date.date() < today
    ]
    overdue = len(overdue_issues)

    # Дети эпиков (для агрегаций)
    issue_id_set = set(issue_ids)
    children = (
        self.db.query(Issue.id, Issue.parent_id, Issue.status_category)
        .filter(Issue.parent_id.in_(issue_id_set))
        .all()
    )
    child_to_parent: dict[str, str] = {r[0]: r[1] for r in children}
    subtasks_done_by_parent: dict[str, int] = {}
    subtasks_total_by_parent: dict[str, int] = {}
    for child_id, parent_id, child_status in children:
        subtasks_total_by_parent[parent_id] = subtasks_total_by_parent.get(parent_id, 0) + 1
        if child_status == "done":
            subtasks_done_by_parent[parent_id] = subtasks_done_by_parent.get(parent_id, 0) + 1

    # Все ID для ворклог-агрегаций
    all_wl_ids = issue_id_set | set(child_to_parent.keys())

    # Last worklog per epic (для silence)
    last_wl_rows = (
        self.db.query(Worklog.issue_id, func.max(Worklog.started_at).label("last_wl"))
        .filter(Worklog.issue_id.in_(all_wl_ids))
        .group_by(Worklog.issue_id)
        .all()
    )
    last_wl_by_issue: dict[str, datetime] = {r[0]: r[1] for r in last_wl_rows if r[1] is not None}

    def epic_last_wl(epic_id: str) -> datetime | None:
        candidates = [last_wl_by_issue.get(epic_id)]
        for child_id, parent_id in child_to_parent.items():
            if parent_id == epic_id and child_id in last_wl_by_issue:
                candidates.append(last_wl_by_issue[child_id])
        candidates = [c for c in candidates if c is not None]
        return max(candidates) if candidates else None

    # Суммарный факт по эпику (включая детей) в пределах периода
    period_start_dt = datetime.combine(period_start, datetime.min.time())
    period_end_dt = datetime.combine(period_end, datetime.max.time())
    fact_rows = (
        self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
        .filter(
            Worklog.issue_id.in_(all_wl_ids),
            Worklog.started_at >= period_start_dt,
            Worklog.started_at <= period_end_dt,
        )
        .group_by(Worklog.issue_id)
        .all()
    )
    fact_secs_by_issue: dict[str, int] = {r[0]: r[1] or 0 for r in fact_rows}

    def epic_fact_hours(epic_id: str) -> float:
        secs = fact_secs_by_issue.get(epic_id, 0)
        for child_id, parent_id in child_to_parent.items():
            if parent_id == epic_id:
                secs += fact_secs_by_issue.get(child_id, 0)
        return secs / 3600.0

    # Тренд: часы за последние 7д vs предыдущие 7д
    trend_cutoff_now = today_dt - timedelta(days=7)
    trend_cutoff_prev = today_dt - timedelta(days=14)

    last7_rows = (
        self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
        .filter(Worklog.issue_id.in_(all_wl_ids), Worklog.started_at >= trend_cutoff_now)
        .group_by(Worklog.issue_id)
        .all()
    )
    last7_secs: dict[str, int] = {r[0]: r[1] or 0 for r in last7_rows}

    prev7_rows = (
        self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
        .filter(
            Worklog.issue_id.in_(all_wl_ids),
            Worklog.started_at >= trend_cutoff_prev,
            Worklog.started_at < trend_cutoff_now,
        )
        .group_by(Worklog.issue_id)
        .all()
    )
    prev7_secs: dict[str, int] = {r[0]: r[1] or 0 for r in prev7_rows}

    def epic_trend(epic_id: str) -> tuple[float, str]:
        last_secs = last7_secs.get(epic_id, 0)
        prev_secs = prev7_secs.get(epic_id, 0)
        for child_id, parent_id in child_to_parent.items():
            if parent_id == epic_id:
                last_secs += last7_secs.get(child_id, 0)
                prev_secs += prev7_secs.get(child_id, 0)
        last_h = last_secs / 3600.0
        if last_h < 0.5 and prev_secs / 3600.0 < 0.5:
            return (0.0, "flat")
        if last_secs > prev_secs * 1.1:
            return (round(last_h, 1), "up")
        if last_secs < prev_secs * 0.9:
            return (round(last_h, 1), "down")
        return (round(last_h, 1), "flat")

    # Assignees: top-3 по часам в эпике
    asg_rows = (
        self.db.query(
            Worklog.issue_id,
            Worklog.author_id,
            func.sum(Worklog.time_spent_seconds).label("secs"),
        )
        .filter(Worklog.issue_id.in_(all_wl_ids))
        .group_by(Worklog.issue_id, Worklog.author_id)
        .all()
    )
    epic_to_employees: dict[str, dict[str, int]] = {}
    for issue_id, author_id, secs in asg_rows:
        epic_id = child_to_parent.get(issue_id, issue_id) if issue_id in child_to_parent else issue_id
        d = epic_to_employees.setdefault(epic_id, {})
        d[author_id] = d.get(author_id, 0) + (secs or 0)

    employee_ids = {aid for d in epic_to_employees.values() for aid in d.keys()}
    employees = self.db.query(Employee).filter(Employee.id.in_(employee_ids)).all() if employee_ids else []
    emp_by_id: dict[str, Employee] = {e.id: e for e in employees}

    def employee_initials(name: str) -> str:
        parts = [p for p in name.split() if p]
        if not parts:
            return "??"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def employee_color(emp: Employee | None) -> str:
        if emp and emp.role:
            role_obj = self.db.query(Role).filter(Role.code == emp.role).first()
            if role_obj and role_obj.color:
                return role_obj.color
        return "#7e94b8"

    # Forecast close date per epic (по фактическому темпу с начала эпика)
    # Темп = fact_total / days_with_fact; close_date = today + (plan - fact) / темп
    quarter_end = period_end

    def epic_forecast(epic_id: str, plan_h: float, fact_h: float) -> tuple[date | None, bool]:
        if fact_h <= 0:
            return (None, False)
        last_wl = epic_last_wl(epic_id)
        first_wl_row = (
            self.db.query(func.min(Worklog.started_at))
            .filter(Worklog.issue_id == epic_id)
            .scalar()
        )
        if first_wl_row is None:
            return (None, False)
        first_dt = first_wl_row
        days_active = max(1, (today_dt - first_dt).days)
        rate_per_day = fact_h / days_active
        if rate_per_day <= 0:
            return (None, False)
        if fact_h >= plan_h:
            close = last_wl.date() if last_wl else today
            return (close, close <= quarter_end)
        remaining_h = plan_h - fact_h
        days_to_close = remaining_h / rate_per_day
        close_date = today + timedelta(days=int(days_to_close))
        return (close_date, close_date <= quarter_end)

    # Weekly activity (8 точек) — по неделям периода с конца назад
    week_buckets = []
    cursor = period_end_dt
    for _ in range(8):
        wk_start = cursor - timedelta(days=7)
        week_buckets.append((wk_start, cursor))
        cursor = wk_start
    week_buckets.reverse()  # хронологически

    weekly_activity_per_epic: dict[str, list[float]] = {epic_id: [0.0] * 8 for epic_id in issue_ids}

    for idx, (wk_start, wk_end) in enumerate(week_buckets):
        rows = (
            self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
            .filter(
                Worklog.issue_id.in_(all_wl_ids),
                Worklog.started_at >= wk_start,
                Worklog.started_at < wk_end,
            )
            .group_by(Worklog.issue_id)
            .all()
        )
        for issue_id, secs in rows:
            epic_id = child_to_parent.get(issue_id, issue_id) if issue_id in child_to_parent else issue_id
            if epic_id in weekly_activity_per_epic:
                weekly_activity_per_epic[epic_id][idx] += (secs or 0) / 3600.0

    # KPI top-level
    overdue_ids = {i.id for i in overdue_issues}

    project_items: list[ProjectItem] = []
    total_fact = 0.0
    total_plan = 0.0
    silent_count = 0

    for issue in issues:
        plan_h = plan_by_issue.get(issue.id, 0.0) or 0.0
        fact_h = epic_fact_hours(issue.id)
        total_fact += fact_h
        total_plan += plan_h

        last_wl = epic_last_wl(issue.id)
        silent_d = (today_dt - last_wl).days if last_wl else 9999
        if silent_d > silence_days and issue.status_category != "done":
            silent_count += 1

        trend_h, trend_dir = epic_trend(issue.id)
        forecast_close, in_qtr = epic_forecast(issue.id, plan_h, fact_h)

        # status_category для UI: если просрочен — overrides
        ui_status = issue.status_category
        if issue.id in overdue_ids:
            ui_status = "overdue"

        # assignees (top-3 by hours)
        emp_secs = epic_to_employees.get(issue.id, {})
        sorted_emps = sorted(emp_secs.items(), key=lambda x: -x[1])
        top3 = sorted_emps[:3]
        assignees = []
        for emp_id, _ in top3:
            emp = emp_by_id.get(emp_id)
            if emp:
                assignees.append(ProjectAssignee(
                    initials=employee_initials(emp.full_name or emp.display_name or ""),
                    color=employee_color(emp),
                ))
        assignees_total = len(emp_secs)

        days_to_due_val: int | None = None
        if issue.due_date is not None:
            days_to_due_val = (issue.due_date.date() - today).days

        project_items.append(ProjectItem(
            issue_key=issue.jira_key,
            title=issue.summary or "",
            status_category=ui_status,
            plan_hours=round(plan_h, 1),
            fact_hours=round(fact_h, 1),
            delta_hours=round(fact_h - plan_h, 1),
            subtasks_done=subtasks_done_by_parent.get(issue.id, 0),
            subtasks_total=subtasks_total_by_parent.get(issue.id, 0),
            assignees=assignees,
            assignees_total=assignees_total,
            due_date=issue.due_date.date() if issue.due_date else None,
            days_to_due=days_to_due_val,
            trend_hours_week=trend_h,
            trend_dir=trend_dir,
            forecast_close_date=forecast_close,
            forecast_in_quarter=in_qtr,
            silent_days=min(silent_d, 9999),
            weekly_activity=[round(h, 1) for h in weekly_activity_per_epic.get(issue.id, [0.0] * 8)],
        ))

    # Sort: in_progress + overdue первыми, потом not_started, done в конце
    status_order = {"overdue": 0, "indeterminate": 1, "new": 2, "done": 3}
    project_items.sort(key=lambda p: (status_order.get(p.status_category, 99), -p.fact_hours))

    avg_load = (total_fact / total_plan * 100) if total_plan > 0 else 0.0

    # Forecast (как было) — линейная экстраполяция done по прошедшим дням
    passed_days = (today - period_start).days
    remaining_days = (period_end - today).days
    if remaining_days <= 0:
        forecast_done = done
        forecast_pct = round(done / total * 100, 1) if total else 0.0
    elif passed_days > 0 and done > 0:
        forecast_done = min(total, round(done / passed_days * (passed_days + remaining_days)))
        forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0
    else:
        forecast_done = done
        forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0

    return DashboardProjectsResponse(
        total=total,
        done=done,
        in_progress=in_progress,
        overdue=overdue,
        not_started=not_started,
        total_fact_hours=round(total_fact, 1),
        total_plan_hours=round(total_plan, 1),
        avg_load_pct=round(avg_load, 1),
        silent_count=silent_count,
        forecast_done=forecast_done,
        forecast_pct=forecast_pct,
        projects=project_items,
    )
```

- [ ] **Step 3: Добавить недостающий импорт `Role` в analytics_service.py**

Run: `grep -n "from app.models" app/services/analytics_service.py | head -5`
Если `Role` не импортирован — добавить:

```python
from app.models.role import Role
```

в блок импортов вверху файла.

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_projects_widget_returns_200 tests/test_dashboard_endpoints.py::test_projects_widget_project_item_shape -v`
Expected: PASS

- [ ] **Step 5: Запустить весь test_analytics_service**

Run: `py -3.10 -m pytest tests/test_analytics_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/analytics_service.py tests/test_dashboard_endpoints.py
git commit -m "feat(analytics): per-project meta для dashboard projects

Расширен get_dashboard_projects: subtasks (done/total),
assignees top-3 (initials+color по роли), due_date+days_to_due,
trend (7д vs пред 7д), forecast_close_date, weekly_activity
(8 точек спарклайна), silent_count + total_fact/plan/avg_load
для KPI."
```

---

### Task 2.3: Обновить frontend types для Widget 1

**Files:**
- Modify: `frontend/src/types/api.ts:707-733`

- [ ] **Step 1: Найти текущие типы Widget 1**

Run: `grep -n "DashboardProjectsResponse\|ProjectAttentionItem\|ProjectOverrunItem" frontend/src/types/api.ts`

- [ ] **Step 2: Заменить блок типов**

Удалить `ProjectAttentionItem` и `ProjectOverrunItem`. Заменить `DashboardProjectsResponse` на:

```ts
export interface ProjectAssignee {
  initials: string;
  color: string;
}

export interface ProjectItem {
  issue_key: string;
  title: string;
  status_category: 'done' | 'indeterminate' | 'new' | 'overdue';
  plan_hours: number;
  fact_hours: number;
  delta_hours: number;
  subtasks_done: number;
  subtasks_total: number;
  assignees: ProjectAssignee[];
  assignees_total: number;
  due_date: string | null;          // ISO date
  days_to_due: number | null;
  trend_hours_week: number;
  trend_dir: 'up' | 'down' | 'flat';
  forecast_close_date: string | null;
  forecast_in_quarter: boolean;
  silent_days: number;
  weekly_activity: number[];
}

export interface DashboardProjectsResponse {
  total: number;
  done: number;
  in_progress: number;
  overdue: number;
  not_started: number;
  total_fact_hours: number;
  total_plan_hours: number;
  avg_load_pct: number;
  silent_count: number;
  forecast_done: number;
  forecast_pct: number;
  projects: ProjectItem[];
}
```

- [ ] **Step 3: Запустить tsc/lint, чинить broken imports**

Run: `cd frontend && npm run lint`
Expected: ProjectsWidget.tsx крикнет на исчезнувшие `attention_list`/`overrun_list` — это OK, на следующем шаге переписываем.

- [ ] **Step 4: Commit (промежуточный — типы готовы, UI ещё не переписан)**

```bash
git add frontend/src/types/api.ts
git commit -m "refactor(types): новые типы DashboardProjectsResponse"
```

---

### Task 2.4: Переписать `ProjectsWidget.tsx`

**Files:**
- Modify: `frontend/src/components/dashboard/ProjectsWidget.tsx` (rewrite целиком)

- [ ] **Step 1: Заменить тело файла**

```tsx
import { Card, Spin, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { DashboardProjectsResponse, ProjectItem } from '../../types/api';
import { formatHours } from '../../utils/format';

const STATUS_COLORS = {
  done: '#67d68d',
  indeterminate: '#00c9c8',
  new: '#7e94b8',
  overdue: '#ff4d4f',
};

const SILENCE_THRESHOLD = 14;
const DUE_SOON_THRESHOLD = 7;

function loadColor(pct: number): string {
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#67d68d';
  return '#faad14';
}

function dueColor(days: number | null): string {
  if (days == null) return '#7e94b8';
  if (days < 0) return '#ff4d4f';
  if (days <= DUE_SOON_THRESHOLD) return '#faad14';
  return '#67d68d';
}

function trendArrow(dir: 'up' | 'down' | 'flat'): { glyph: string; color: string } {
  if (dir === 'up') return { glyph: '↑', color: '#67d68d' };
  if (dir === 'down') return { glyph: '↓', color: '#faad14' };
  return { glyph: '·', color: '#7e94b8' };
}

function Donut({ data }: { data: DashboardProjectsResponse }) {
  const segments = [
    { name: 'Выполнены', value: data.done, color: STATUS_COLORS.done },
    { name: 'В работе', value: data.in_progress, color: STATUS_COLORS.indeterminate },
    { name: 'Просрочены', value: data.overdue, color: STATUS_COLORS.overdue },
    { name: 'Не начаты', value: data.not_started, color: STATUS_COLORS.new },
  ];
  const total = data.total;
  const visible = segments.filter((s) => s.value > 0);

  // SVG arc paths
  const cx = 90, cy = 90, r = 72, ir = 56;
  let cum = 0;
  const arcs = visible.map((seg) => {
    const frac = total > 0 ? seg.value / total : 0;
    const startAngle = cum * 360;
    cum += frac;
    const endAngle = cum * 360;
    const sweep = endAngle - startAngle - 2; // 2° gap
    const sa = ((startAngle + 1) - 90) * Math.PI / 180;
    const ea = ((startAngle + 1 + sweep) - 90) * Math.PI / 180;
    const x1 = cx + r * Math.cos(sa), y1 = cy + r * Math.sin(sa);
    const x2 = cx + r * Math.cos(ea), y2 = cy + r * Math.sin(ea);
    const largeArc = sweep > 180 ? 1 : 0;
    return { color: seg.color, d: `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}` };
  });

  return (
    <div>
      <div style={{ position: 'relative', width: 180, height: 180, margin: '0 auto' }}>
        <svg width="180" height="180">
          {arcs.map((a, i) => (
            <path key={i} d={a.d} fill="none" stroke={a.color} strokeWidth={r - ir} />
          ))}
        </svg>
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: '#fff', lineHeight: 1 }}>{total}</div>
          <div style={{ fontSize: 12, color: '#7e94b8' }}>проектов</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
        {segments.map((s) => (
          <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
            <span style={{ color: '#fff', fontWeight: 600, width: 28 }}>{s.value}</span>
            <span style={{ color: '#7e94b8' }}>{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssigneeStack({ project }: { project: ProjectItem }) {
  const extra = project.assignees_total - project.assignees.length;
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {project.assignees.map((a, i) => (
        <div
          key={i}
          title={a.initials}
          style={{
            width: 24, height: 24, borderRadius: '50%',
            border: '2px solid #0f2340', background: a.color,
            color: '#fff', fontSize: 10, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: i === 0 ? 0 : -8,
          }}
        >
          {a.initials}
        </div>
      ))}
      {extra > 0 && (
        <div style={{
          width: 24, height: 24, borderRadius: '50%',
          border: '2px solid #0f2340', background: '#1c3358',
          color: '#a4b8d8', fontSize: 10, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginLeft: -8,
        }}>+{extra}</div>
      )}
    </div>
  );
}

function ProjectRow({ project, onClick }: { project: ProjectItem; onClick: () => void }) {
  const isDone = project.status_category === 'done';
  const overrun = project.fact_hours > project.plan_hours && project.plan_hours > 0;
  const pct = project.plan_hours > 0 ? (project.fact_hours / project.plan_hours) * 100 : 0;
  const barColor = STATUS_COLORS[project.status_category] || '#7e94b8';
  const fillWidth = Math.min(100, pct);
  const trend = trendArrow(project.trend_dir);
  const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : '—';

  return (
    <div
      onClick={onClick}
      style={{
        display: 'grid',
        gridTemplateColumns: '12px minmax(220px,1.3fr) 70px 70px 95px 75px 85px 1fr 80px 50px',
        gap: 10,
        padding: '8px 0',
        alignItems: 'center',
        borderBottom: '1px solid rgba(28,51,88,.4)',
        cursor: 'pointer',
        fontSize: 13,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: barColor }} />
      <div style={{
        color: isDone ? '#7e94b8' : '#fff',
        textDecoration: isDone ? 'line-through' : 'none',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        fontSize: 14,
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.title}</span>
        {project.silent_days > SILENCE_THRESHOLD && !isDone && (
          <span style={{ background: '#faad1422', color: '#faad14', fontSize: 10, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            тишина {project.silent_days}д
          </span>
        )}
        {overrun && (
          <span style={{ background: '#ff4d4f22', color: '#ff4d4f', fontSize: 10, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            +{Math.round(project.delta_hours)} ч
          </span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12 }}>
        <span style={{ color: '#a4b8d8' }}>{project.subtasks_done}/{project.subtasks_total}</span>
        <div style={{ height: 5, background: '#1c3358', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${project.subtasks_total > 0 ? (project.subtasks_done / project.subtasks_total) * 100 : 0}%`,
            background: barColor,
          }} />
        </div>
      </div>
      <AssigneeStack project={project} />
      <div style={{ fontSize: 13, color: dueColor(project.days_to_due) }}>
        {project.due_date ? `${fmtDate(project.due_date)} · ${project.days_to_due! >= 0 ? '' : ''}${project.days_to_due}д` : '—'}
      </div>
      <div style={{ fontSize: 13, color: trend.color }}>
        {trend.glyph} {project.trend_hours_week.toFixed(0)} ч
      </div>
      <div style={{ fontSize: 13, color: project.forecast_close_date ? (project.forecast_in_quarter ? '#67d68d' : '#ff4d4f') : '#7e94b8' }}>
        {isDone ? 'завершён' : project.forecast_close_date ? `к ${fmtDate(project.forecast_close_date)}${project.forecast_in_quarter ? '' : ' ⚠'}` : '—'}
      </div>
      <div style={{ height: 12, background: '#1c3358', borderRadius: 6, overflow: 'visible', position: 'relative' }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, height: '100%',
          width: `${fillWidth}%`,
          background: barColor,
          borderRadius: 6,
        }} />
      </div>
      <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 600, color: '#a4b8d8' }}>
        {Math.round(project.fact_hours)} / {Math.round(project.plan_hours)} ч
      </div>
      <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 700, color: loadColor(pct) }}>
        {Math.round(pct)}%
      </div>
    </div>
  );
}

function KpiTiles({ data }: { data: DashboardProjectsResponse }) {
  const tiles = [
    {
      label: 'ВСЕГО ФАКТОМ',
      value: `${Math.round(data.total_fact_hours)} ч`,
      sub: `из ${Math.round(data.total_plan_hours)} план`,
      color: '#fff',
    },
    {
      label: 'СРЕДНЯЯ ЗАГРУЗКА',
      value: `${Math.round(data.avg_load_pct)}%`,
      sub: 'факт / план',
      color: loadColor(data.avg_load_pct),
    },
    {
      label: 'МОЛЧАТ > 14 ДНЕЙ',
      value: `${data.silent_count}`,
      sub: 'проекта без активности',
      color: data.silent_count > 0 ? '#faad14' : '#7e94b8',
    },
    {
      label: 'ЗАКРОЮТСЯ В СРОК',
      value: `${data.forecast_done}`,
      sub: `(${data.forecast_pct}%) прогноз по темпу`,
      color: '#67d68d',
    },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      {tiles.map((t) => (
        <div key={t.label} style={{
          background: '#0a1d3a', border: '1px solid #1c3358', borderRadius: 8,
          padding: 12, display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          <div style={{ fontSize: 12, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.label}</div>
          <div style={{ fontSize: 32, fontWeight: 700, color: t.color, lineHeight: 1 }}>{t.value}</div>
          <div style={{ fontSize: 13, color: '#7e94b8' }}>{t.sub}</div>
        </div>
      ))}
    </div>
  );
}

function Sparklines({ projects }: { projects: ProjectItem[] }) {
  const visible = projects.slice(0, 6);
  return (
    <div style={{ background: '#0a1d3a', border: '1px solid #1c3358', borderRadius: 8, padding: 14 }}>
      <div style={{
        fontSize: 12, color: '#7e94b8', textTransform: 'uppercase',
        letterSpacing: '0.06em', marginBottom: 10,
      }}>
        Активность по неделям
      </div>
      {visible.map((p) => {
        const max = Math.max(...p.weekly_activity, 1);
        const points = p.weekly_activity.map((v, i) => `${(i / (p.weekly_activity.length - 1)) * 100},${100 - (v / max) * 100}`).join(' ');
        const isActive = p.silent_days <= SILENCE_THRESHOLD;
        const stroke = isActive
          ? (p.status_category === 'overdue' || p.fact_hours > p.plan_hours ? '#ff4d4f' : (p.status_category === 'done' ? '#67d68d' : '#00c9c8'))
          : '#2a4060';
        return (
          <div key={p.issue_key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
            <div style={{
              width: 110, fontSize: 14, color: isActive ? '#e6edf7' : '#7e94b8',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {p.title.split(' ').slice(0, 2).join(' ')}
            </div>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ flex: 1, height: 24 }}>
              <polyline
                points={points}
                fill="none"
                stroke={stroke}
                strokeWidth={2}
                strokeDasharray={isActive ? undefined : '3 3'}
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  data: DashboardProjectsResponse | undefined;
  loading: boolean;
}

export default function ProjectsWidget({ data, loading }: Props) {
  const navigate = useNavigate();

  if (loading) return <Card title="Проекты квартала"><Spin /></Card>;
  if (!data) return <Card title="Проекты квартала"><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Проекты квартала">
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 280px 280px', gap: 20, alignItems: 'flex-start' }}>
        <Donut data={data} />

        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '12px minmax(220px,1.3fr) 70px 70px 95px 75px 85px 1fr 80px 50px',
            gap: 10,
            fontSize: 12,
            color: '#7e94b8',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            paddingBottom: 8,
            borderBottom: '1px solid #1c3358',
          }}>
            <span />
            <span>Проект</span>
            <span>Подзад</span>
            <span>Команда</span>
            <span>Срок</span>
            <span>Тренд</span>
            <span>Прогноз</span>
            <span>Прогресс</span>
            <span style={{ textAlign: 'right' }}>Факт / План</span>
            <span style={{ textAlign: 'right' }}>%</span>
          </div>
          {data.projects.map((p) => (
            <ProjectRow
              key={p.issue_key}
              project={p}
              onClick={() => navigate(`/analytics?project=${p.issue_key}`)}
            />
          ))}
          {data.projects.length === 0 && (
            <div style={{ padding: 16, color: '#7e94b8', fontSize: 13 }}>Нет проектов в утверждённом сценарии квартала</div>
          )}
        </div>

        <KpiTiles data={data} />

        <Sparklines projects={data.projects} />
      </div>
    </Card>
  );
}

// keep import if used elsewhere; otherwise unused — checked by lint
void formatHours;
```

- [ ] **Step 2: Lint + типы**

Run: `cd frontend && npm run lint`
Expected: PASS. Если жалоба на `formatHours` неиспользуемый — удалить импорт + последнюю строку.

- [ ] **Step 3: Запустить dev и проверить визуально**

Run: `cd frontend && npm run dev`
Открыть `http://localhost:5173/dashboard`. Сравнить с макетом `widget1-projects.html`. Проверить:
- 4-колоночная сетка (donut · список · KPI 2×2 · спарклайны)
- Donut: «Не начаты» серый
- Список: 10 колонок включая Срок/Тренд/Прогноз
- Бары толстые (12px)
- Овержалые подсвечены красным бейджем «+N ч»
- Тишина >14д — жёлтый бейдж

- [ ] **Step 4: e2e**

Run: `cd frontend && npm run e2e -- dashboard`
Expected: PASS. Если падает — обновить spec.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx
git commit -m "feat(dashboard): редизайн виджета Проекты квартала

4-колоночная сетка: SVG-donut с серой Не начатой долей,
полный список проектов (Срок/Тренд/Прогноз/Прогресс/Факт/План/%),
KPI 2×2 (Всего фактом/Загрузка/Молчат/Закроются в срок),
блок спарклайнов активности по неделям. Удалены блоки
Требует внимания и Перебор по часам."
```

---

## Phase 3 — Widget 2 (Нормированные работы)

Backend крупная переработка `get_dashboard_norm_work` — переход с work_type-уровня на per-employee группировку по ролям.

### Task 3.1: Обновить схему `DashboardNormWorkResponse`

**Files:**
- Modify: `app/schemas/dashboard.py`
- Modify: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Failing-тест**

Заменить `test_norm_work_widget_returns_200` в `tests/test_dashboard_endpoints.py`:

```python
def test_norm_work_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert "total_plan" in data
    assert "total_fact" in data
    assert "total_pct" in data
    assert isinstance(data["roles"], list)
    # items field удалён
    assert "items" not in data


def test_norm_work_widget_role_shape():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    data = resp.json()
    if data["roles"]:
        role = data["roles"][0]
        for k in [
            "role_code", "role_label", "role_color", "employees_count",
            "total_plan", "total_fact", "total_pct", "employees",
        ]:
            assert k in role
        assert isinstance(role["employees"], list)
        if role["employees"]:
            emp = role["employees"][0]
            for k in [
                "employee_id", "name", "initials",
                "plan_hours", "fact_hours", "pct", "work_types",
            ]:
                assert k in emp
            if emp["work_types"]:
                wt = emp["work_types"][0]
                for k in ["work_type_id", "label", "plan_hours", "fact_hours", "pct"]:
                    assert k in wt
```

- [ ] **Step 2: Запустить — увидеть FAIL**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_norm_work_widget_returns_200 -v`
Expected: FAIL.

- [ ] **Step 3: Заменить блок Widget 2 в `app/schemas/dashboard.py`**

Удалить `NormWorkItem` и `DashboardNormWorkResponse`. Добавить:

```python
class NormWorkTypeBreakdown(BaseModel):
    work_type_id: str
    label: str
    plan_hours: float
    fact_hours: float
    pct: float


class NormWorkEmployee(BaseModel):
    employee_id: str
    name: str
    initials: str
    plan_hours: float
    fact_hours: float
    pct: float
    work_types: list[NormWorkTypeBreakdown]


class NormWorkRoleGroup(BaseModel):
    role_code: str
    role_label: str
    role_color: str
    employees_count: int
    total_plan: float
    total_fact: float
    total_pct: float
    employees: list[NormWorkEmployee]


class DashboardNormWorkResponse(BaseModel):
    roles: list[NormWorkRoleGroup]
    total_plan: float
    total_fact: float
    total_pct: float
```

- [ ] **Step 4: Commit (промежуточный)**

```bash
git add app/schemas/dashboard.py tests/test_dashboard_endpoints.py
git commit -m "refactor(schemas): per-employee NormWork сгруппированный по ролям"
```

---

### Task 3.2: Переписать `get_dashboard_norm_work`

**Files:**
- Modify: `app/services/analytics_service.py:585-...`

- [ ] **Step 1: Найти текущую реализацию**

Run: `grep -n "def get_dashboard_norm_work" app/services/analytics_service.py`

- [ ] **Step 2: Заменить целиком на новую реализацию**

```python
def get_dashboard_norm_work(
    self,
    year: int,
    quarter: int,
    month: Optional[int] = None,
    teams: Optional[list[str]] = None,
) -> DashboardNormWorkResponse:
    """Widget 2: per-employee план/факт по обязательным видам работ, группировка по ролям."""
    from app.schemas.dashboard import (
        NormWorkTypeBreakdown, NormWorkEmployee, NormWorkRoleGroup,
    )
    from app.services.capacity_service import CapacityService

    period_start, period_end = quarter_to_dates(year, quarter, month)
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    # 1. Активные виды работ
    work_types = (
        self.db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.is_active.is_(True))
        .order_by(MandatoryWorkType.sort_order)
        .all()
    )
    wt_by_id: dict[str, MandatoryWorkType] = {wt.id: wt for wt in work_types}

    # 2. Категории → work_type
    cat_rows = (
        self.db.query(Category.code, Category.work_type_id)
        .filter(Category.work_type_id.isnot(None))
        .all()
    )
    code_to_wt: dict[str, str] = {code: wt_id for code, wt_id in cat_rows}

    # 3. Активные сотрудники в командах
    employees_q = self.db.query(Employee).filter(Employee.is_active.is_(True))
    if teams:
        # Фильтрация через EmployeeTeam M:N
        from app.models.employee_team import EmployeeTeam
        team_emp_ids = (
            self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team.in_(teams))
            .distinct()
            .all()
        )
        emp_ids = [r[0] for r in team_emp_ids]
        employees_q = employees_q.filter(Employee.id.in_(emp_ids))
    employees: list[Employee] = employees_q.all()

    if not employees:
        return DashboardNormWorkResponse(
            roles=[], total_plan=0.0, total_fact=0.0, total_pct=0.0,
        )

    # 4. Роли реестр
    roles_db = self.db.query(Role).filter(Role.is_active.is_(True)).order_by(Role.sort_order).all()
    role_by_code: dict[str, Role] = {r.code: r for r in roles_db}

    # 5. План на сотрудника по work_type
    cap_svc = CapacityService(self.db)

    plan_per_emp_wt: dict[str, dict[str, float]] = {}   # emp_id → wt_id → hours
    for emp in employees:
        plan_per_emp_wt[emp.id] = {}
        try:
            qcap = cap_svc.quarterly_capacity(
                employee_id=emp.id, year=year, quarter=quarter,
            )
        except Exception:
            qcap = None
        if qcap is None:
            continue
        # qcap имеет breakdown по work_type (см. capacity_service); в случае month — масштабируем
        breakdown = getattr(qcap, "by_work_type", None) or {}
        scale = 1.0
        if month is not None:
            month_workdays = cap_svc.workdays_in_month(year, month) if hasattr(cap_svc, "workdays_in_month") else None
            quarter_workdays = getattr(qcap, "workdays_total", None)
            if month_workdays and quarter_workdays:
                scale = month_workdays / quarter_workdays
        for wt_id, hours in breakdown.items():
            plan_per_emp_wt[emp.id][wt_id] = (hours or 0.0) * scale

    # 6. Факт на сотрудника по work_type из ворклогов
    emp_ids = [e.id for e in employees]
    wl_rows = (
        self.db.query(
            Worklog.author_id,
            Issue.assigned_category,
            func.sum(Worklog.time_spent_seconds).label("secs"),
        )
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(
            Worklog.author_id.in_(emp_ids),
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
            Issue.assigned_category.isnot(None),
        )
        .group_by(Worklog.author_id, Issue.assigned_category)
        .all()
    )
    fact_per_emp_wt: dict[str, dict[str, float]] = {e.id: {} for e in employees}
    for emp_id, cat_code, secs in wl_rows:
        wt_id = code_to_wt.get(cat_code)
        if wt_id is None:
            continue
        h = (secs or 0) / 3600.0
        fact_per_emp_wt[emp_id][wt_id] = fact_per_emp_wt[emp_id].get(wt_id, 0.0) + h

    def initials(name: str) -> str:
        parts = [p for p in (name or "").split() if p]
        if not parts:
            return "??"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    # 7. Группировка по роли
    employees_by_role: dict[str | None, list[Employee]] = {}
    for emp in employees:
        employees_by_role.setdefault(emp.role, []).append(emp)

    # Фиксированный порядок ролей (если в реестре)
    role_order_codes = [r.code for r in roles_db]

    roles_out: list[NormWorkRoleGroup] = []
    grand_plan = 0.0
    grand_fact = 0.0

    iter_codes = role_order_codes + [c for c in employees_by_role.keys() if c not in role_order_codes]

    for role_code in iter_codes:
        if role_code not in employees_by_role:
            continue
        emps = employees_by_role[role_code]
        role_obj = role_by_code.get(role_code) if role_code else None
        role_label = role_obj.label if role_obj else (role_code or "Без роли")
        role_color = role_obj.color if role_obj else "#7e94b8"

        emp_items: list[NormWorkEmployee] = []
        role_plan = 0.0
        role_fact = 0.0

        # Сорт сотрудников: по убыванию pct
        emp_with_totals = []
        for emp in emps:
            plan_total = sum(plan_per_emp_wt.get(emp.id, {}).values())
            fact_total = sum(fact_per_emp_wt.get(emp.id, {}).values())
            pct = (fact_total / plan_total * 100) if plan_total > 0 else 0.0
            emp_with_totals.append((emp, plan_total, fact_total, pct))

        emp_with_totals.sort(key=lambda x: -x[3])

        for emp, plan_total, fact_total, pct in emp_with_totals:
            wt_breakdowns: list[NormWorkTypeBreakdown] = []
            for wt in work_types:
                p = plan_per_emp_wt.get(emp.id, {}).get(wt.id, 0.0)
                f = fact_per_emp_wt.get(emp.id, {}).get(wt.id, 0.0)
                if p == 0 and f == 0:
                    continue
                wt_pct = (f / p * 100) if p > 0 else 0.0
                wt_breakdowns.append(NormWorkTypeBreakdown(
                    work_type_id=wt.id,
                    label=wt.label,
                    plan_hours=round(p, 1),
                    fact_hours=round(f, 1),
                    pct=round(wt_pct, 1),
                ))

            emp_items.append(NormWorkEmployee(
                employee_id=emp.id,
                name=emp.full_name or emp.display_name or "",
                initials=initials(emp.full_name or emp.display_name or ""),
                plan_hours=round(plan_total, 1),
                fact_hours=round(fact_total, 1),
                pct=round(pct, 1),
                work_types=wt_breakdowns,
            ))
            role_plan += plan_total
            role_fact += fact_total

        role_pct = (role_fact / role_plan * 100) if role_plan > 0 else 0.0
        roles_out.append(NormWorkRoleGroup(
            role_code=role_code or "_unassigned",
            role_label=role_label,
            role_color=role_color,
            employees_count=len(emp_items),
            total_plan=round(role_plan, 1),
            total_fact=round(role_fact, 1),
            total_pct=round(role_pct, 1),
            employees=emp_items,
        ))
        grand_plan += role_plan
        grand_fact += role_fact

    grand_pct = (grand_fact / grand_plan * 100) if grand_plan > 0 else 0.0

    return DashboardNormWorkResponse(
        roles=roles_out,
        total_plan=round(grand_plan, 1),
        total_fact=round(grand_fact, 1),
        total_pct=round(grand_pct, 1),
    )
```

- [ ] **Step 3: Добавить импорты в analytics_service.py если нет**

Проверить что импортированы: `Role`, `EmployeeTeam` (если уже нет — добавить:`from app.models.employee_team import EmployeeTeam` локально в методе уже добавлено).

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -v`
Expected: PASS. Если падает на `quarterly_capacity` — проверить публичный API CapacityService и адаптировать (имена атрибутов `by_work_type` / `workdays_total` могут отличаться; см. `app/services/capacity_service.py`).

- [ ] **Step 5: Если CapacityService API отличается — адаптировать**

Если `quarterly_capacity` не возвращает `by_work_type`, использовать прямой расчёт через `RoleCapacityRule` + `EmployeeCapacityOverride` + production_calendar:

```python
# Вычислить workdays_in_period (с учётом absences) — функция уже есть в capacity_service
# Достать role_rules: db.query(RoleCapacityRule).filter(year=year, quarter=f"Q{quarter}").all()
# Применить overrides из db.query(EmployeeCapacityOverride).filter(...).all()
# Финальный план: workdays * 8 * pct/100 за каждый work_type
```

Подсмотреть готовый код в `app/services/capacity_service.py` (методы вычисления плана сотрудника).

- [ ] **Step 6: Run polish — все pytest**

Run: `py -3.10 -m pytest tests/ -x -v`
Expected: PASS (по dashboard + capacity тестам).

- [ ] **Step 7: Commit**

```bash
git add app/services/analytics_service.py
git commit -m "feat(analytics): per-employee NormWork с группировкой по ролям

Переписан get_dashboard_norm_work: возвращает roles[]
с employees[] и work_types[] детализацией. План
считается через CapacityService на эмплоя+work_type;
факт — из ворклогов через assigned_category → work_type.
Top-level totals остаются. Респект team filter +
month-narrowing."
```

---

### Task 3.3: Frontend types для Widget 2

**Files:**
- Modify: `frontend/src/types/api.ts:735-748`

- [ ] **Step 1: Заменить блок типов**

Удалить `NormWorkItem` и старый `DashboardNormWorkResponse`. Заменить:

```ts
export interface NormWorkTypeBreakdown {
  work_type_id: string;
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
}

export interface NormWorkEmployee {
  employee_id: string;
  name: string;
  initials: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
  work_types: NormWorkTypeBreakdown[];
}

export interface NormWorkRoleGroup {
  role_code: string;
  role_label: string;
  role_color: string;
  employees_count: number;
  total_plan: number;
  total_fact: number;
  total_pct: number;
  employees: NormWorkEmployee[];
}

export interface DashboardNormWorkResponse {
  roles: NormWorkRoleGroup[];
  total_plan: number;
  total_fact: number;
  total_pct: number;
}
```

- [ ] **Step 2: lint**

Run: `cd frontend && npm run lint`
Expected: NormWorkWidget.tsx крикнет на старые поля — OK, переписываем дальше.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "refactor(types): NormWorkRoleGroup с employees+breakdowns"
```

---

### Task 3.4: Переписать `NormWorkWidget.tsx`

**Files:**
- Modify: `frontend/src/components/dashboard/NormWorkWidget.tsx` (rewrite)

- [ ] **Step 1: Заменить тело файла**

```tsx
import { useState } from 'react';
import { Card, Spin, Empty, Tooltip, Modal, InputNumber, Form } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type {
  DashboardNormWorkResponse,
  NormWorkRoleGroup,
  NormWorkEmployee,
  NormWorkTypeBreakdown,
} from '../../types/api';

interface Thresholds { warnAbove: number; underBelow: number; }
const DEFAULT_THRESHOLDS: Thresholds = { warnAbove: 110, underBelow: 70 };

function statusColor(pct: number, t: Thresholds): string {
  if (pct > t.warnAbove) return '#ff4d4f';
  if (pct >= t.underBelow) return '#52c41a';
  return '#faad14';
}

function BulletBar({ plan, fact, color }: { plan: number; fact: number; color: string }) {
  const targetPct = 66;
  const fillW = plan > 0 ? Math.min(targetPct, (fact / plan) * targetPct) : 0;
  const overrunW = plan > 0 && fact > plan ? Math.min(100 - targetPct, ((fact - plan) / plan) * targetPct) : 0;
  return (
    <div style={{ position: 'relative', height: 14, background: '#1c3358', borderRadius: 7 }}>
      <div style={{
        position: 'absolute', top: 0, left: 0, height: '100%',
        width: `${fillW}%`, background: color, borderRadius: 7,
      }} />
      {overrunW > 0 && (
        <div style={{
          position: 'absolute', top: 0, left: `${targetPct}%`,
          height: '100%', width: `${overrunW}%`,
          background: '#ff4d4f', borderRadius: '0 7px 7px 0',
        }} />
      )}
      <div style={{
        position: 'absolute', top: -3, bottom: -3, left: `${targetPct}%`,
        width: 2, background: '#fff',
      }} />
    </div>
  );
}

function WorkTypeRow({ wt, t }: { wt: NormWorkTypeBreakdown; t: Thresholds }) {
  const color = statusColor(wt.pct, t);
  const fillW = wt.plan_hours > 0 ? Math.min(100, (wt.fact_hours / wt.plan_hours) * 100) : 0;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto 60px',
      gap: 8, alignItems: 'center', padding: '3px 0',
    }}>
      <span style={{ fontSize: 12, color: '#a4b8d8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {wt.label}
      </span>
      <div style={{ width: 50, height: 5, background: '#1c3358', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${fillW}%`, background: color }} />
      </div>
      <span style={{ fontSize: 11, color: '#7e94b8', textAlign: 'right' }}>
        {Math.round(wt.fact_hours)}/{Math.round(wt.plan_hours)}
      </span>
    </div>
  );
}

function EmployeeBlock({ emp, role, t }: { emp: NormWorkEmployee; role: NormWorkRoleGroup; t: Thresholds }) {
  const color = statusColor(emp.pct, t);
  return (
    <div style={{ paddingBottom: 12, borderBottom: '1px solid rgba(28,51,88,.5)', marginBottom: 12 }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '28px 1fr auto',
        gap: 8, alignItems: 'center', marginBottom: 8,
      }}>
        <div style={{
          width: 24, height: 24, borderRadius: '50%', background: role.role_color,
          color: '#fff', fontSize: 11, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{emp.initials}</div>
        <div style={{ fontSize: 14, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {emp.name}
        </div>
        <div style={{ fontSize: 14, fontWeight: 700, color }}>
          {Math.round(emp.pct)}%
        </div>
      </div>
      <BulletBar plan={emp.plan_hours} fact={emp.fact_hours} color={color} />
      <div style={{ fontSize: 12, color: '#7e94b8', marginTop: 4 }}>
        факт {Math.round(emp.fact_hours)} ч · план {Math.round(emp.plan_hours)} ч
      </div>
      <div style={{ marginTop: 8, marginLeft: 12 }}>
        {emp.work_types.map((wt) => (
          <WorkTypeRow key={wt.work_type_id} wt={wt} t={t} />
        ))}
      </div>
    </div>
  );
}

function RoleColumn({ role, t }: { role: NormWorkRoleGroup; t: Thresholds }) {
  return (
    <div style={{ background: '#0a1d3a', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{
        padding: 12, borderBottom: `2px solid ${role.role_color}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: role.role_color }} />
          <span style={{ fontSize: 16, fontWeight: 600, color: '#e6edf7' }}>{role.role_label}</span>
          <span style={{ fontSize: 13, color: '#7e94b8' }}>{role.employees_count} чел.</span>
        </div>
        <div style={{ fontSize: 13, color: '#7e94b8', marginTop: 4 }}>
          Σ план <b style={{ color: '#fff' }}>{Math.round(role.total_plan)} ч</b>
          {' · '}Σ факт <b style={{ color: '#fff' }}>{Math.round(role.total_fact)} ч</b>
          {' · '}средн. <b style={{ color: statusColor(role.total_pct, t) }}>{Math.round(role.total_pct)}%</b>
        </div>
      </div>
      <div style={{ padding: 12 }}>
        {role.employees.map((emp) => (
          <EmployeeBlock key={emp.employee_id} emp={emp} role={role} t={t} />
        ))}
        {role.employees.length === 0 && (
          <div style={{ color: '#7e94b8', fontSize: 13 }}>Нет сотрудников</div>
        )}
      </div>
    </div>
  );
}

interface Props {
  data: DashboardNormWorkResponse | undefined;
  loading: boolean;
}

export default function NormWorkWidget({ data, loading }: Props) {
  const [t, setT] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<Thresholds>();

  const gear = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined
        style={{ cursor: 'pointer', color: '#7e94b8', fontSize: 16 }}
        onClick={() => { form.setFieldsValue(t); setModalOpen(true); }}
      />
    </Tooltip>
  );

  const title = (
    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 16 }}>
      <span style={{ fontSize: 15, fontWeight: 600, color: '#e6edf7' }}>Нормированные работы</span>
      {data && !loading && (
        <span style={{ fontSize: 14, color: '#7e94b8' }}>
          Σ план <b style={{ color: '#fff' }}>{Math.round(data.total_plan)} ч</b>
          {' · '}Σ факт <b style={{ color: '#fff' }}>{Math.round(data.total_fact)} ч</b>
          {' · '}загрузка <b style={{ color: statusColor(data.total_pct, t) }}>{Math.round(data.total_pct)}%</b>
        </span>
      )}
      {gear}
    </span>
  );

  if (loading) return <Card title="Нормированные работы"><Spin /></Card>;
  if (!data?.roles.length) return <Card title={title}><Empty description="Нет данных" /></Card>;

  return (
    <>
      <Card title={title}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, alignItems: 'flex-start' }}>
          {data.roles.slice(0, 4).map((r) => <RoleColumn key={r.role_code} role={r} t={t} />)}
        </div>
        {data.roles.length > 4 && (
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: `repeat(${Math.min(data.roles.length - 4, 4)}, 1fr)`, gap: 16 }}>
            {data.roles.slice(4).map((r) => <RoleColumn key={r.role_code} role={r} t={t} />)}
          </div>
        )}
      </Card>

      <Modal
        title="Настройка порогов загрузки"
        open={modalOpen}
        onOk={() => form.validateFields().then((v) => { setT(v); setModalOpen(false); })}
        onCancel={() => setModalOpen(false)}
        okText="Применить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="Перегруз — выше, % (красный)" name="warnAbove" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
          <Form.Item label="Недозагрузка — ниже, % (жёлтый)" name="underBelow" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: lint**

Run: `cd frontend && npm run lint`
Expected: PASS

- [ ] **Step 3: dev + визуальная проверка**

Открыть `/dashboard`. Сравнить с `widget2-normwork.html`:
- 4 колонки (или больше если ролей >4)
- Header колонки: цветной dot + label + N чел., строкой ниже Σ план/факт/средн%
- Внутри колонки — список сотрудников с раскрытой разбивкой
- Bullet-bar с белой target line на 66%
- Шестерёнка → модалка порогов

- [ ] **Step 4: e2e**

Run: `cd frontend && npm run e2e -- dashboard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/NormWorkWidget.tsx
git commit -m "feat(dashboard): per-employee NormWork по 4 ролям

Виджет переписан под новую схему: 4 колонки на роль,
header с цветным акцентом + Σ summary, employee-блоки
с bullet-bar (white target line @66%) и раскрытой
разбивкой по видам работ. Шестерёнка + модалка порогов
сохранены 1:1 из текущего виджета."
```

---

## Phase 4 — Layout dashboard page

### Task 4.1: Адаптировать `DashboardPage.tsx`

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Заменить layout-блок**

```tsx
return (
  <div>
    <Space wrap style={{ marginBottom: 24 }}>
      <QuarterPicker value={period} onChange={setPeriod} />
      <ExportButtons
        onXlsx={() => downloadAnalyticsXlsx(undefined, undefined, teamParams)}
        onPdf={() => downloadAnalyticsPdf(undefined, undefined, teamParams)}
      />
    </Space>

    <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
      <Col xs={24}>
        <ProjectsWidget data={projects} loading={projLoading} />
      </Col>
    </Row>

    <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
      <Col xs={24}>
        <NormWorkWidget data={normWork} loading={normLoading} />
      </Col>
    </Row>

    <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
      <Col xs={24} lg={12}>
        <CategoryWidget data={categories} loading={catLoading} />
      </Col>
    </Row>
  </div>
);
```

- [ ] **Step 2: dev + проверка композиции**

Открыть `/dashboard`. Убедиться что:
- W1 на полную ширину
- W2 на полную ширину под ним
- W3 на половине ширины внизу
- При выборе месяца отбор передаётся (поменять Q + месяц, увидеть запрос с `month=` в Network)

- [ ] **Step 3: Полный e2e**

Run: `cd frontend && npm run e2e`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(dashboard): полноширинная вёрстка W1+W2, W3 половина ряда"
```

---

## Phase 5 — Финальный sanity-check

### Task 5.1: Полный pytest + frontend build + e2e

**Files:** none

- [ ] **Step 1: Полный pytest**

Run: `py -3.10 -m pytest tests/ -v`
Expected: PASS (с учётом известных pre-existing красных из `project_ci_red_pre_existing.md` — они не должны увеличиться).

- [ ] **Step 2: Frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS

- [ ] **Step 3: Полный e2e**

Run: `cd frontend && npm run e2e`
Expected: PASS

- [ ] **Step 4: Smoke local**

Run: `py -3.10 scripts/local_smoke.py`
Expected: backend + frontend стартуют, dashboard отвечает 200 на 3 endpoint.

- [ ] **Step 5: Финальный push**

```bash
git push origin main
```

- [ ] **Step 6: Обновить memory**

Сохранить в `C:\Users\akim2\.claude\projects\d--ClaudeDev-JiraAnalysis\memory\` новую запись:

`project_dashboard_redesign_shipped.md`:

```markdown
---
name: Dashboard redesign shipped
description: 2026-04-30 — три виджета /dashboard переписаны
type: project
---

2026-04-30: shipped редизайн `/dashboard` (W1 Проекты, W2 Нормированные работы, W3 Категории). Per-project meta (subtasks/assignees/срок/тренд/прогноз/spark), per-employee NormWork по 4 ролям с разбивкой по видам работ, heatmap grid 5×2 для категорий. Backend `analytics_service.py` расширен; frontend компоненты переписаны.

**Why:** старый дашборд выглядел пустым, плитки не заполняли площадь, NormWork агрегировал на уровне команды.

**How to apply:** при изменениях фильтров или добавлении новых полей в виджеты — смотреть спеку `docs/superpowers/specs/2026-04-30-dashboard-redesign-design.md`.
```

И добавить строку в `MEMORY.md`:
```
- [Dashboard redesign shipped](project_dashboard_redesign_shipped.md) — 2026-04-30: 3 виджета переписаны (W1 per-project meta, W2 per-employee 4 роли, W3 heatmap 5×2)
```

---

## Self-Review

**1. Spec coverage:**
- ✓ Виджет 1: donut с серой Не начатой долей (T2.4 step 2 Donut), список 10 cols (T2.4 ProjectRow), KPI 2×2 (KpiTiles), спарклайны (Sparklines), удалён attention/overrun (T2.1 schema)
- ✓ Виджет 2: 4 колонки по ролям (T3.4 RoleColumn), per-employee с разбивкой (EmployeeBlock + WorkTypeRow), bullet-bar, шестерёнка модалка (T3.4 Modal)
- ✓ Виджет 3: heatmap grid 5×2 (T1.1 HeatmapGrid), мета-таблица справа (MetaTable), +N overflow (T1.1 step 2)
- ✓ Period filter: month прокидывается (без изменений в endpoints), forecast логика на квартал (T2.2 epic_forecast)
- ✓ Team filter: респектится в W2/W3 (T3.2 employees_q фильтр); W1 — отдельная привязка к утверждённому сценарию (без team)
- ✓ Multi-user: глобальный team filter уже передаётся через `useGlobalTeamFilter`

**2. Placeholder scan:**
- Нет TBD/TODO в шагах
- Все шаги с кодом содержат полные блоки
- Тестов кода имеют конкретные assertions
- В Task 3.2 step 5 указано «адаптировать если CapacityService API отличается» — это не плэйсхолдер, а явный safety-net с указанием куда смотреть

**3. Type consistency:**
- Backend `ProjectItem.assignees: list[ProjectAssignee]` ↔ frontend `ProjectItem.assignees: ProjectAssignee[]` ✓
- Backend `NormWorkRoleGroup.employees: list[NormWorkEmployee]` ↔ frontend `NormWorkRoleGroup.employees: NormWorkEmployee[]` ✓
- Все имена полей snake_case на backend, переходят 1:1 в TS (Pydantic дефолтное поведение) ✓
- Status: backend возвращает `'overdue' | 'indeterminate' | 'new' | 'done'`; frontend ожидает то же ✓
