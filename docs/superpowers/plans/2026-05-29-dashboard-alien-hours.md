# Dashboard «Помощь извне» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Виджет «Проекты квартала» отделяет часы помощников извне от часов команды; средняя загрузка считается только от команды; в строке проекта появляется колонка «Помощь» с аватарами; в правой стопке появляется KPI-карточка «Помощь извне».

**Architecture:** Backend (`AnalyticsService.get_dashboard_projects`) делит ворклоги на «командные» и «чужие» через множество employee IDs команды (из `employee_teams`). Расширяем `ProjectItem` и `DashboardProjectsResponse` новыми полями (alien_*, team_*). Старые поля `fact_hours`, `total_fact_hours`, `avg_load_pct` пересчитываются от команды. Фронт добавляет новую опциональную колонку (через существующий `ColKey`/`COLS`-механизм) и новый KPI-tile.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + pytest; React 19 + TypeScript 6 + AntD 6.

---

## File Structure

**Backend:**
- Modify `app/schemas/dashboard.py` — добавить поля в `ProjectItem` + `DashboardProjectsResponse`
- Modify `app/services/analytics_service.py` (метод `get_dashboard_projects`, строки 180-556) — split team vs alien
- Modify `tests/test_dashboard_endpoints.py` — добавить тесты

**Frontend:**
- Modify `frontend/src/types/api.ts:745-780` — добавить поля в типы
- Modify `frontend/src/components/dashboard/ProjectsWidget.tsx` — новая колонка `help`, новый KPI tile, переключение `fact_hours` → `team_fact_hours`

---

## Task 1: Расширить схемы Pydantic

**Files:**
- Modify: `app/schemas/dashboard.py:13-47`

- [ ] **Step 1: Дополнить `ProjectItem`**

В файле `app/schemas/dashboard.py` после строки `weekly_activity: list[float]` (строка 32) добавить:

```python
    team_fact_hours: float = 0.0       # часы команды по эпику (включая детей)
    alien_fact_hours: float = 0.0      # часы помощников извне
    alien_helpers: list[ProjectAssignee] = []   # top-3 помощника
    alien_helper_count: int = 0        # сколько всего помощников
```

`fact_hours` оставляем (сумма team+alien, для совместимости).

- [ ] **Step 2: Дополнить `DashboardProjectsResponse`**

После строки `projects: list[ProjectItem]` (строка 47) добавить:

```python
    total_team_fact_hours: float = 0.0     # факт только команды
    total_alien_fact_hours: float = 0.0    # факт помощников извне
    alien_helper_count: int = 0            # уникальных помощников
    alien_projects_count: int = 0          # сколько проектов получили помощь
```

`total_fact_hours` = `total_team_fact_hours + total_alien_fact_hours` (старое поле). `avg_load_pct` пересчитывается от команды: `total_team_fact_hours / total_plan_hours * 100`.

- [ ] **Step 3: Запустить mypy на схеме**

Run: `py -3.10 -m mypy app/schemas/dashboard.py`
Expected: `Success: no issues found`

- [ ] **Step 4: Commit**

```bash
git add app/schemas/dashboard.py
git commit -m "feat(dashboard): схемы для помощи извне в виджете проектов"
```

---

## Task 2: Тест на split team/alien часов

**Files:**
- Test: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Прочитать существующие тесты дашборда**

Run: `head -120 tests/test_dashboard_endpoints.py`
Цель: понять фикстуры (как создаются Issue/Worklog/Employee/EmployeeTeam/PlanningScenario/ScenarioAllocation/BacklogItem).

- [ ] **Step 2: Написать падающий тест**

Добавить в `tests/test_dashboard_endpoints.py` (в конец файла):

```python
def test_dashboard_projects_splits_team_alien(client, db_session, seed_quarter_scenario):
    """Виджет делит часы на командные и чужие; загрузка считается от команды."""
    from app.models import Worklog, EmployeeTeam, Employee
    from datetime import datetime
    from uuid import uuid4

    # seed_quarter_scenario возвращает (epic_id, team_name, period_start)
    epic_id, team, period_start = seed_quarter_scenario

    # Создаём двух сотрудников: один в команде, один вне
    own = Employee(id=str(uuid4()), display_name="Свой Иван", is_active=True)
    alien = Employee(id=str(uuid4()), display_name="Чужой Орлов", is_active=True)
    db_session.add_all([own, alien])
    db_session.add(EmployeeTeam(employee_id=own.id, team=team, is_primary=True))
    db_session.commit()

    # 2 ворклога на эпике: 10ч от своего, 5ч от чужого
    worklog_dt = datetime.combine(period_start, datetime.min.time())
    db_session.add_all([
        Worklog(id=str(uuid4()), issue_id=epic_id, employee_id=own.id,
                started_at=worklog_dt, time_spent_seconds=10*3600, hours=10.0),
        Worklog(id=str(uuid4()), issue_id=epic_id, employee_id=alien.id,
                started_at=worklog_dt, time_spent_seconds=5*3600, hours=5.0),
    ])
    db_session.commit()

    resp = client.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_team_fact_hours"] == 10.0
    assert data["total_alien_fact_hours"] == 5.0
    assert data["alien_helper_count"] == 1
    assert data["alien_projects_count"] == 1

    project = data["projects"][0]
    assert project["team_fact_hours"] == 10.0
    assert project["alien_fact_hours"] == 5.0
    assert project["alien_helper_count"] == 1
    assert len(project["alien_helpers"]) == 1
    assert project["alien_helpers"][0]["initials"] == "ЧО"
```

Если фикстура `seed_quarter_scenario` не существует — создать её в `conftest.py` (см. step 3).

- [ ] **Step 3: Если нужна фикстура `seed_quarter_scenario` — добавить в `tests/conftest.py`**

Прочитать `tests/conftest.py`. Если фикстуры нет — добавить:

```python
@pytest.fixture
def seed_quarter_scenario(db_session):
    """Создаёт минимальный утверждённый сценарий Q2 2026 с одним эпиком."""
    from app.models import (Project, Issue, BacklogItem, PlanningScenario,
                            ScenarioAllocation, Category)
    from datetime import date
    from uuid import uuid4

    team = "Команда Тест"
    cat = db_session.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        cat = Category(id=str(uuid4()), code="quarterly_tasks",
                       label="Квартальные задачи", color="#2dd4bf")
        db_session.add(cat)

    project = Project(id=str(uuid4()), jira_id="proj1", key="TST", name="Test")
    db_session.add(project)

    epic_id = str(uuid4())
    epic = Issue(id=epic_id, jira_issue_id="ji1", key="TST-1", summary="Test epic",
                 issue_type="Epic", status="In Progress", status_category="indeterminate",
                 project_id=project.id, category="quarterly_tasks")
    db_session.add(epic)

    bi = BacklogItem(id=str(uuid4()), issue_id=epic_id, title="Test epic", quarter="Q2",
                    year=2026, category_code="initiatives_rfa", team=team)
    db_session.add(bi)

    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026 plan", year=2026,
                           quarter="Q2", team=team, status="approved")
    db_session.add(scn)
    db_session.flush()

    alloc = ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                               backlog_item_id=bi.id, included_flag=True,
                               planned_hours=100.0)
    db_session.add(alloc)
    db_session.commit()

    return epic_id, team, date(2026, 4, 15)
```

Если в моделях BacklogItem или PlanningScenario поля отличаются от перечисленных — прочитай `app/models/` и подгони fixture под реальные имена.

- [ ] **Step 4: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_dashboard_projects_splits_team_alien -v`
Expected: FAIL — поле `team_fact_hours` отсутствует или = 0, потому что service ещё не делит ворклоги.

---

## Task 3: Реализовать split в backend сервисе

**Files:**
- Modify: `app/services/analytics_service.py` (метод `get_dashboard_projects`, строки 180-556)

- [ ] **Step 1: Найти место для team_employee_ids после строки 279 (после `all_wl_ids = ...`)**

Прочитать строки 270-320 файла `app/services/analytics_service.py`.

- [ ] **Step 2: Добавить вычисление множества команды**

После строки `all_wl_ids = issue_id_set | set(child_to_parent.keys())` (около строки 279) добавить:

```python
        # Множество сотрудников команды (для split team vs alien)
        from app.models import EmployeeTeam
        if teams:
            team_emp_rows = (
                self.db.query(EmployeeTeam.employee_id)
                .filter(EmployeeTeam.team.in_(teams))
                .all()
            )
            team_employee_ids: set[str] = {r[0] for r in team_emp_rows}
        else:
            team_employee_ids = set()  # пустое = «помощников нет», всё командное
```

- [ ] **Step 3: Заменить агрегат `fact_rows` на два отдельных по team/alien**

Найти блок (строки ~298-311) `fact_rows = self.db.query(Worklog.issue_id, ...)`. Заменить на:

```python
        period_start_dt = datetime.combine(period_start, datetime.min.time())
        period_end_dt = datetime.combine(period_end, datetime.max.time())

        # Все ворклоги — для legacy fact_secs_by_issue (сумма team+alien)
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

        # Командные ворклоги
        if teams and team_employee_ids:
            team_fact_rows = (
                self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
                .filter(
                    Worklog.issue_id.in_(all_wl_ids),
                    Worklog.started_at >= period_start_dt,
                    Worklog.started_at <= period_end_dt,
                    Worklog.employee_id.in_(team_employee_ids),
                )
                .group_by(Worklog.issue_id)
                .all()
            )
            team_fact_secs_by_issue: dict[str, int] = {r[0]: r[1] or 0 for r in team_fact_rows}
        else:
            # Если команда не выбрана — всё считаем командным
            team_fact_secs_by_issue = dict(fact_secs_by_issue)
```

- [ ] **Step 4: Добавить per-epic функцию `epic_team_fact_hours`**

После функции `epic_fact_hours` (около строки 313-318) добавить:

```python
        def epic_team_fact_hours(epic_id: str) -> float:
            secs = team_fact_secs_by_issue.get(epic_id, 0)
            for child_id, parent_id in child_to_parent.items():
                if parent_id == epic_id:
                    secs += team_fact_secs_by_issue.get(child_id, 0)
            return secs / 3600.0

        def epic_alien_fact_hours(epic_id: str) -> float:
            return epic_fact_hours(epic_id) - epic_team_fact_hours(epic_id)
```

- [ ] **Step 5: Собрать alien_employees per epic**

Найти блок `asg_rows = self.db.query(...)` (около строки 361). После него (после построения `epic_to_employees`) добавить:

```python
        # Разбить epic_to_employees на команда / чужие
        epic_alien_employees: dict[str, dict[str, int]] = {}
        for epic_id, emp_secs in epic_to_employees.items():
            aliens = {
                eid: secs for eid, secs in emp_secs.items()
                if team_employee_ids and eid not in team_employee_ids
            }
            if aliens:
                epic_alien_employees[epic_id] = aliens
```

- [ ] **Step 6: В сборке `ProjectItem` добавить новые поля**

Найти где собирается `ProjectItem(...)` в цикле `for issue in issues:` (около строки 500+). Перед `project_items.append(...)` добавить:

```python
            # Помощь извне для этого эпика
            team_fact_h = epic_team_fact_hours(issue.id)
            alien_fact_h = epic_alien_fact_hours(issue.id)
            alien_emp_secs = epic_alien_employees.get(issue.id, {})
            sorted_aliens = sorted(alien_emp_secs.items(), key=lambda x: -x[1])
            top3_aliens = sorted_aliens[:3]
            alien_helpers_list = []
            for emp_id, _ in top3_aliens:
                emp = emp_by_id.get(emp_id)
                if emp:
                    alien_helpers_list.append(ProjectAssignee(
                        initials=employee_initials(emp.display_name or ""),
                        color="#84cc16",  # мятно-зелёный для помощников
                    ))
```

Если `emp_by_id` не содержит чужого employee — догрузить. Найти строку `employees = self.db.query(Employee).filter(Employee.id.in_(employee_ids)).all()` и убедиться что `employee_ids` включает чужих (вообще все из `epic_to_employees`).

В `ProjectItem(...)` добавить новые kwargs:

```python
                team_fact_hours=round(team_fact_h, 2),
                alien_fact_hours=round(alien_fact_h, 2),
                alien_helpers=alien_helpers_list,
                alien_helper_count=len(alien_emp_secs),
```

- [ ] **Step 7: Пересчитать KPI ответа**

В конце метода, где собирается `DashboardProjectsResponse(...)`, перед `return` добавить:

```python
        total_team_fact = sum(epic_team_fact_hours(i.id) for i in issues)
        total_alien_fact = sum(epic_alien_fact_hours(i.id) for i in issues)
        all_alien_emp_ids: set[str] = set()
        alien_projects_count = 0
        for epic_id, aliens in epic_alien_employees.items():
            if aliens:
                alien_projects_count += 1
                all_alien_emp_ids.update(aliens.keys())
```

`avg_load_pct` пересчитать: где сейчас `total_fact / total_plan`, заменить на `total_team_fact / total_plan`. Найти строку (около `avg_load_pct=...`) и поправить:

```python
            avg_load_pct=round((total_team_fact / total_plan * 100) if total_plan > 0 else 0.0, 1),
            total_fact_hours=round(total_team_fact + total_alien_fact, 2),
            total_team_fact_hours=round(total_team_fact, 2),
            total_alien_fact_hours=round(total_alien_fact, 2),
            alien_helper_count=len(all_alien_emp_ids),
            alien_projects_count=alien_projects_count,
```

- [ ] **Step 8: Запустить тест — должен пройти**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py::test_dashboard_projects_splits_team_alien -v`
Expected: PASS.

Если падает — прочитать вывод, исправить. Если фиксура падает на отсутствии полей у модели — прочитать `app/models/__init__.py` и поправить fixture.

- [ ] **Step 9: Запустить весь файл тестов**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -v`
Expected: все тесты PASS.

- [ ] **Step 10: Commit**

```bash
git add app/services/analytics_service.py tests/test_dashboard_endpoints.py tests/conftest.py
git commit -m "feat(dashboard): split team vs alien часы в виджете проектов

Сервис get_dashboard_projects делит ворклоги на командные
и помощников извне через employee_teams. avg_load_pct
теперь считается только от команды (total_team_fact / plan)."
```

---

## Task 4: Тесты — top-3 и no-teams

**Files:**
- Test: `tests/test_dashboard_endpoints.py`

- [ ] **Step 1: Тест top-3 помощников**

Добавить в `tests/test_dashboard_endpoints.py`:

```python
def test_dashboard_projects_alien_helpers_top3(client, db_session, seed_quarter_scenario):
    """В alien_helpers возвращается только top-3 по часам."""
    from app.models import Worklog, Employee
    from datetime import datetime
    from uuid import uuid4

    epic_id, team, period_start = seed_quarter_scenario
    worklog_dt = datetime.combine(period_start, datetime.min.time())

    # 5 чужих сотрудников с разными часами
    hours_map = [("А А", 10), ("Б Б", 8), ("В В", 6), ("Г Г", 4), ("Д Д", 2)]
    for name, h in hours_map:
        emp = Employee(id=str(uuid4()), display_name=name, is_active=True)
        db_session.add(emp)
        db_session.add(Worklog(id=str(uuid4()), issue_id=epic_id, employee_id=emp.id,
                               started_at=worklog_dt, time_spent_seconds=h*3600, hours=float(h)))
    db_session.commit()

    resp = client.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
    assert resp.status_code == 200
    project = resp.json()["projects"][0]
    assert project["alien_helper_count"] == 5
    assert len(project["alien_helpers"]) == 3
    assert [h["initials"] for h in project["alien_helpers"]] == ["АА", "ББ", "ВВ"]
```

- [ ] **Step 2: Тест без фильтра teams**

```python
def test_dashboard_projects_no_teams_means_no_aliens(client, db_session, seed_quarter_scenario):
    """Без фильтра teams все ворклоги командные, помощников нет."""
    from app.models import Worklog, Employee
    from datetime import datetime
    from uuid import uuid4

    epic_id, team, period_start = seed_quarter_scenario
    emp = Employee(id=str(uuid4()), display_name="Любой Кто", is_active=True)
    db_session.add(emp)
    db_session.add(Worklog(id=str(uuid4()), issue_id=epic_id, employee_id=emp.id,
                           started_at=datetime.combine(period_start, datetime.min.time()),
                           time_spent_seconds=20*3600, hours=20.0))
    db_session.commit()

    # Без &teams=...
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_alien_fact_hours"] == 0.0
    assert data["total_team_fact_hours"] == 20.0
    assert data["alien_helper_count"] == 0
```

- [ ] **Step 3: Запустить новые тесты**

Run: `py -3.10 -m pytest tests/test_dashboard_endpoints.py -v`
Expected: все PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard_endpoints.py
git commit -m "test(dashboard): top-3 помощников + поведение без фильтра teams"
```

---

## Task 5: Фронт-типы

**Files:**
- Modify: `frontend/src/types/api.ts:745-780`

- [ ] **Step 1: Добавить поля в `ProjectItem`**

В файле `frontend/src/types/api.ts` после строки `weekly_activity: number[];` (около строки 764) добавить:

```typescript
  team_fact_hours: number;
  alien_fact_hours: number;
  alien_helpers: ProjectAssignee[];
  alien_helper_count: number;
```

- [ ] **Step 2: Добавить поля в `DashboardProjectsResponse`**

После `projects: ProjectItem[];` (строка 779) добавить:

```typescript
  total_team_fact_hours: number;
  total_alien_fact_hours: number;
  alien_helper_count: number;
  alien_projects_count: number;
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(dashboard): типы для помощи извне"
```

---

## Task 6: Колонка «Помощь» в таблице проектов

**Files:**
- Modify: `frontend/src/components/dashboard/ProjectsWidget.tsx`

- [ ] **Step 1: Добавить `'help'` в `ColKey`**

Найти строку 19:

```typescript
type ColKey = 'status' | 'subtasks' | 'assignees' | 'due' | 'trend' | 'forecast' | 'progress' | 'factplan' | 'pct';
```

Заменить на:

```typescript
type ColKey = 'status' | 'subtasks' | 'help' | 'assignees' | 'due' | 'trend' | 'forecast' | 'progress' | 'factplan' | 'pct';
```

- [ ] **Step 2: Добавить запись в `COLS`**

Найти массив `COLS` (строки 22-32). Между `subtasks` и `assignees` вставить:

```typescript
  { key: 'help', label: 'Помощь', width: '95px' },
```

- [ ] **Step 3: Добавить `help: true` в `DEFAULT_PREFS.cols`**

Найти `DEFAULT_PREFS` (строки 47-50). В `cols` добавить `help: true`:

```typescript
  cols: { status: true, subtasks: true, help: true, assignees: true, due: true, trend: true, forecast: true, progress: true, factplan: true, pct: true },
```

- [ ] **Step 4: Создать компонент `AlienHelpersStack`**

После функции `AssigneeStack` (строки 148-178) добавить:

```typescript
function AlienHelpersStack({ project }: { project: ProjectItem }) {
  if (project.alien_helper_count === 0) {
    return <span style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>—</span>;
  }
  const extra = project.alien_helper_count - project.alien_helpers.length;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {project.alien_helpers.map((a, i) => (
          <div
            key={i}
            title={a.initials}
            style={{
              width: 22, height: 22, borderRadius: '50%',
              border: `2px solid ${DARK_THEME.cardBg}`,
              background: 'linear-gradient(135deg, #84cc16 0%, #22c55e 100%)',
              color: '#052e16', fontSize: 9, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginLeft: i === 0 ? 0 : -6,
            }}
          >
            {a.initials}
          </div>
        ))}
        {extra > 0 && (
          <div style={{
            width: 22, height: 22, borderRadius: '50%',
            border: `2px solid ${DARK_THEME.cardBg}`,
            background: 'rgba(132,204,22,0.15)', color: '#84cc16',
            fontSize: 9, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: -6,
          }}>+{extra}</div>
        )}
      </div>
      <span style={{ fontSize: 11, color: '#84cc16', fontWeight: 600 }}>
        +{Math.round(project.alien_fact_hours)}ч
      </span>
    </div>
  );
}
```

- [ ] **Step 5: Добавить case в `renderCell`**

Найти `switch (key)` в функции `renderCell` (строка 182). После `case 'subtasks':` блока добавить:

```typescript
    case 'help':
      return <AlienHelpersStack project={project} />;
```

- [ ] **Step 6: Лайв-чек**

Запустить dev-сервер:

```bash
cd frontend && npm run dev
```

Открыть `http://localhost:5173/`, на дашборде проверить:
- В таблице проектов появилась колонка «Помощь»
- В строках с помощью извне видны аватары мятно-зелёного цвета + «+Nч»
- Hover на аватаре показывает инициалы
- В строках без помощи стоит прочерк

Если колонка не видна — проверить, что в localStorage снёс старые `dashboard.projects.prefs` (или жми кнопку «Сбросить» в шестерёнке).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx
git commit -m "feat(dashboard): колонка «Помощь» с аватарами помощников"
```

---

## Task 7: KPI-карточка «Помощь извне» + переключение на team_fact

**Files:**
- Modify: `frontend/src/components/dashboard/ProjectsWidget.tsx`

- [ ] **Step 1: Обновить tile «Всего фактом» — теперь от команды**

Найти функцию `KpiTiles` (строки 326-367). В массиве `tiles` для tile с label `'ВСЕГО ФАКТОМ'` заменить:

```typescript
    {
      label: 'ВСЕГО ФАКТОМ',
      value: `${Math.round(data.total_team_fact_hours)} ч`,
      sub: `из ${Math.round(data.total_plan_hours)} план`,
      color: DARK_THEME.textPrimary,
    },
```

- [ ] **Step 2: Добавить tile «Помощь извне»**

После tile «СРЕДНЯЯ ЗАГРУЗКА» (перед «МОЛЧАТ») добавить:

```typescript
    {
      label: 'ПОМОЩЬ ИЗВНЕ',
      value: data.total_alien_fact_hours > 0 ? `+${Math.round(data.total_alien_fact_hours)} ч` : '—',
      sub: data.total_alien_fact_hours > 0
        ? `${data.alien_helper_count} чел · ${data.alien_projects_count} проектов`
        : 'нет внешней помощи',
      color: data.total_alien_fact_hours > 0 ? '#84cc16' : DARK_THEME.textMuted,
    },
```

- [ ] **Step 3: Обновить грид KPI — стало 5 плиток**

В JSX `<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', ... }}>` (строка 354) поменять на 5 плиток. Заменить блок:

```typescript
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      {tiles.map((t) => (
        <div key={t.label} style={{
          background: '#0a1d3a', border: `1px solid ${DARK_THEME.darkRows}`, borderRadius: 8,
          padding: 12, display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          ...
        </div>
      ))}
    </div>
  );
```

на:

```typescript
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      {tiles.map((t, idx) => (
        <div key={t.label} style={{
          background: t.label === 'ПОМОЩЬ ИЗВНЕ' && data.total_alien_fact_hours > 0
            ? 'rgba(132,204,22,0.06)'
            : '#0a1d3a',
          border: t.label === 'ПОМОЩЬ ИЗВНЕ' && data.total_alien_fact_hours > 0
            ? '1px solid rgba(132,204,22,0.25)'
            : `1px solid ${DARK_THEME.darkRows}`,
          borderRadius: 8,
          padding: 12, display: 'flex', flexDirection: 'column', gap: 4,
          // Если нечётное число плиток — последняя занимает всю ширину
          gridColumn: idx === tiles.length - 1 && tiles.length % 2 === 1 ? '1 / -1' : undefined,
        }}>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.label}</div>
          <div style={{ fontSize: 32, fontWeight: 700, color: t.color, lineHeight: 1 }}>{t.value}</div>
          <div style={{ fontSize: 13, color: DARK_THEME.textMuted }}>{t.sub}</div>
        </div>
      ))}
    </div>
  );
```

- [ ] **Step 4: Переключить `fact_hours` на `team_fact_hours` в строке проекта**

Найти функцию `ProjectRow` (строки 266-324). В вычислении `pct`:

```typescript
  const pct = project.plan_hours > 0 ? (project.fact_hours / project.plan_hours) * 100 : 0;
```

заменить на:

```typescript
  const pct = project.plan_hours > 0 ? (project.team_fact_hours / project.plan_hours) * 100 : 0;
```

Также найти `const overrun = project.fact_hours > project.plan_hours && ...`. Заменить на:

```typescript
  const overrun = project.team_fact_hours > project.plan_hours && project.plan_hours > 0;
```

В `renderCell` case `'factplan'` (строки 251-256) заменить:

```typescript
    case 'factplan':
      return (
        <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 600, color: '#a4b8d8' }}>
          {Math.round(project.team_fact_hours)} / {Math.round(project.plan_hours)} ч
        </div>
      );
```

В `delta_hours` overrun-chip (строка 315) показывает `Math.round(project.delta_hours)` — теперь `delta` всё ещё от total fact (схема не меняется). Заменить на использование `team_fact` дельты:

```typescript
        {overrun && (
          <span style={{ background: '#ff4d4f22', color: '#ff4d4f', fontSize: 10, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            +{Math.round(project.team_fact_hours - project.plan_hours)} ч
          </span>
        )}
```

- [ ] **Step 5: Запустить TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Лайв-чек в браузере**

Открыть `http://localhost:5173/`, дашборд. Проверить:
- «Всего фактом» показывает 204ч (только команда), а не 276
- «Средняя загрузка» 20% (была 27)
- Добавилась 5-я плитка «Помощь извне +73ч / 6 чел · 5 проектов» мятно-зелёным
- Прогресс-бары в строках проектов соответствуют командному факту
- «Факт/План» в строках показывает только командный факт
- Колонка «Помощь» (из Task 6) на месте

Если есть mismatch — открыть DevTools Network → запрос `/dashboard/projects` → проверить новые поля в ответе.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx
git commit -m "feat(dashboard): KPI «Помощь извне» + загрузка от команды"
```

---

## Task 8: Финальная проверка

- [ ] **Step 1: Полный pytest**

Run: `py -3.10 -m pytest tests/ -x --ignore=tests/e2e -q`
Expected: all PASS (или те же pre-existing failures что и до изменений).

- [ ] **Step 2: Frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: both succeed.

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ KPI «Всего фактом» от команды → Task 7 step 1
- ✅ KPI «Помощь извне» → Task 7 step 2
- ✅ Средняя загрузка от команды → Task 3 step 7 (backend пересчёт)
- ✅ Колонка «Помощь» с аватарами → Task 6
- ✅ Прогресс-бар от team_fact → Task 7 step 4
- ✅ Факт/План от team_fact → Task 7 step 4
- ✅ Бублик не меняется → не трогаем
- ✅ Backend split логика → Task 3
- ✅ Top-3 alien helpers → Task 3 step 6
- ✅ Поведение без фильтра teams → Task 4 step 2

**Placeholder scan:** нет TBD, нет «handle edge cases», все код-блоки полные.

**Type consistency:** `team_fact_hours`/`alien_fact_hours`/`alien_helpers`/`alien_helper_count` — везде одинаковые имена (backend Pydantic ↔ frontend TS).

---

## Notes

- Hardcoded color `#84cc16` (мятно-зелёный) для помощников. Если в будущем понадобится привязать к роли — заменить на `employee_color(emp)`. Сейчас цвет несёт смысл «помощь», не «роль».
- `delta_hours` в схеме остаётся `fact - plan` (от total). UI считает свою дельту от team локально (Task 7 step 4). Если позже всплывёт что нужна именно team_delta — добавить отдельным полем в схему.
- E2E-смоук скрипт `scripts/smoke-local.ps1` не запускается, потому что фронт-чек делается вручную в браузере (Task 6 step 6 + Task 7 step 6). Если smoke нужен — отдельная задача.
