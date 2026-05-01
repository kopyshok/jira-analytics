# Orphan Worklogs Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В виджете «Нормированные работы» на дашборде показать виртуальную строку «Не указана категория/вид работ» с фактом по orphan-ворклогам (нет категории либо нет вида работ у категории), чтобы Σ факт виджета = Σ ворклогов сотрудника за период.

**Architecture:** Маленькая правка в `analytics_service.get_dashboard_norm_work`: добавить orphan-bucket в цикле обхода ворклогов, выпустить виртуальную запись `NormWorkTypeBreakdown` с `work_type_id="__unmapped__"` в каждом блоке сотрудника, где факт > 0. Без миграций, без правок фронта.

**Tech Stack:** Python 3.10, SQLAlchemy 2.0, FastAPI, pytest. Frontend: React 19 (без правок).

**Спек:** [docs/superpowers/specs/2026-05-01-orphan-worklogs-row-design.md](../specs/2026-05-01-orphan-worklogs-row-design.md)

---

## File Structure

- **Modify:** `app/services/analytics_service.py` (метод `get_dashboard_norm_work`, ~строки 954-1148)
- **Create:** `tests/test_norm_work_orphan.py` — 5 кейсов (orphan no-category, orphan no-work-type, foreign приоритет, нет orphan-ворклогов, проверка Σ)

---

### Task 1: Тесты orphan-маршрутизации (TDD)

**Files:**
- Create: `tests/test_norm_work_orphan.py`

- [ ] **Step 1: Создать файл с фикстурами и базовыми хелперами**

Скопировать структуру из `tests/test_norm_work_cross_team.py` (фикстуры `db_session`, `client`, хелперы `_seed_*`, `_find_emp_breakdown`, `_wt_label_hours`). Добавить хелпер `_seed_category_with_no_work_type`:

```python
"""Orphan-bucket routing in dashboard NormWork widget."""

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
    Category,
    Employee,
    EmployeeTeam,
    Issue,
    MandatoryWorkType,
    Project,
    Role,
    Worklog,
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
    session = Session()
    try:
        yield session
    finally:
        session.close()
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


def _seed_base(db):
    """work_types + 1 категория с work_type + 1 категория без work_type + 1 роль."""
    other = MandatoryWorkType(
        id=str(uuid.uuid4()), code="other_foreign", label="Прочие / Чужие задачи",
        is_active=True, sort_order=99, subtracts_from_pool=False, is_system=True,
    )
    support_wt = MandatoryWorkType(
        id=str(uuid.uuid4()), code="support_consult", label="Сопровождение и консультация",
        is_active=True, sort_order=1, subtracts_from_pool=True, is_system=True,
    )
    db.add_all([other, support_wt])
    db.flush()
    db.add_all([
        Category(
            id=str(uuid.uuid4()), code="support_consultation", label="Сопровождение",
            sort_order=0, work_type_id=support_wt.id,
        ),
        # Категория без work_type — её ворклоги должны попасть в orphan
        Category(
            id=str(uuid.uuid4()), code="archive", label="Архив",
            sort_order=10, work_type_id=None,
        ),
    ])
    db.add(Role(
        id=str(uuid.uuid4()), code="developer", label="Программист",
        color="#0c8", sort_order=0, is_active=True,
    ))
    db.commit()
    return other, support_wt


def _seed_project(db):
    p = Project(id=str(uuid.uuid4()), jira_project_id="10000", key="TEST",
                name="Test Project", is_active=True)
    db.add(p)
    db.commit()
    return p


def _seed_employee(db, name, team):
    emp = Employee(
        id=str(uuid.uuid4()), jira_account_id=f"acc-{uuid.uuid4()}",
        display_name=name, is_active=True, role="developer",
    )
    db.add(emp)
    db.flush()
    if team is not None:
        db.add(EmployeeTeam(
            id=str(uuid.uuid4()), employee_id=emp.id, team=team, is_primary=True,
        ))
    db.commit()
    return emp


def _seed_issue(db, project, key, team, category):
    i = Issue(
        id=str(uuid.uuid4()), jira_issue_id=f"ji-{uuid.uuid4()}",
        key=key, summary=key, issue_type="Задача", status="In Progress",
        project_id=project.id, category=category, team=team,
        participating_teams=json.dumps([]),
    )
    db.add(i)
    db.commit()
    return i


def _seed_worklog(db, issue, emp, hours):
    db.add(Worklog(
        id=str(uuid.uuid4()), jira_worklog_id=f"wl-{uuid.uuid4()}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=int(hours * 3600), hours=hours,
    ))
    db.commit()


def _find_emp(data, emp_id):
    for grp in data["roles"]:
        for emp in grp["employees"]:
            if emp["employee_id"] == emp_id:
                return emp
    return None


def _wt_by_id(emp, wt_id):
    if emp is None:
        return None
    for wt in emp["work_types"]:
        if wt["work_type_id"] == wt_id:
            return wt
    return None


ORPHAN_ID = "__unmapped__"
```

- [ ] **Step 2: Тест 1 — задача без категории**

Добавить в файл:

```python
def test_worklog_on_issue_without_category_routes_to_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Без Категории", "Команда A")
    issue = _seed_issue(db_session, project, "NC-1", team="Команда A", category=None)
    _seed_worklog(db_session, issue, emp, 4.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is not None
    assert orphan["fact_hours"] == 4.0
    assert orphan["plan_hours"] == 0
    assert "Не указана категория" in orphan["label"]
```

- [ ] **Step 3: Тест 2 — категория без вида работ**

```python
def test_worklog_on_category_without_work_type_routes_to_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Архив Архивыч", "Команда A")
    issue = _seed_issue(db_session, project, "ARC-1", team="Команда A", category="archive")
    _seed_worklog(db_session, issue, emp, 9.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is not None
    assert orphan["fact_hours"] == 9.0
```

- [ ] **Step 4: Тест 3 — приоритет foreign выше orphan**

```python
def test_foreign_team_beats_orphan_when_no_category(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Чужой Без Категории", "Команда A")
    issue = _seed_issue(db_session, project, "FNC-1", team="Команда B", category=None)
    _seed_worklog(db_session, issue, emp, 7.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    foreign = next((w for w in emp_block["work_types"] if "Прочие" in w["label"]), None)
    assert orphan is None or orphan.get("fact_hours", 0) == 0
    assert foreign is not None and foreign["fact_hours"] == 7.0
```

- [ ] **Step 5: Тест 4 — нет orphan-ворклогов → нет orphan-строки**

```python
def test_no_orphan_row_when_zero_orphan_hours(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Чистый", "Команда A")
    issue = _seed_issue(db_session, project, "OK-1", team="Команда A",
                        category="support_consultation")
    _seed_worklog(db_session, issue, emp, 5.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is None, "orphan-строка не должна появляться при нулевом факте"
```

- [ ] **Step 6: Тест 5 — Σ факт = Σ ворклогов**

```python
def test_total_fact_includes_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Микс", "Команда A")
    own = _seed_issue(db_session, project, "MIX-1", team="Команда A",
                      category="support_consultation")
    arc = _seed_issue(db_session, project, "MIX-2", team="Команда A", category="archive")
    _seed_worklog(db_session, own, emp, 10.0)
    _seed_worklog(db_session, arc, emp, 3.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    assert emp_block["fact_hours"] == 13.0
    sup = next(w for w in emp_block["work_types"] if "Сопровождение" in w["label"])
    orph = _wt_by_id(emp_block, ORPHAN_ID)
    assert sup["fact_hours"] == 10.0
    assert orph["fact_hours"] == 3.0
```

- [ ] **Step 7: Запустить тесты — все 5 должны упасть (FAIL)**

Run: `py -3.10 -m pytest tests/test_norm_work_orphan.py -v`

Expected: 5 FAIL — orphan-строки нет (или фактуры не совпадают).

---

### Task 2: Реализовать orphan-bucket в analytics_service

**Files:**
- Modify: `app/services/analytics_service.py:920-993` (worklog routing loop) + `:1099-1123` (per-employee row assembly)

- [ ] **Step 1: Добавить orphan константы перед циклом ворклогов**

В `app/services/analytics_service.py`, найти строку 953 (`fact_per_emp_wt: dict[str, dict[str, float]] = {e.id: {} for e in employees}`) и сразу ПЕРЕД ней вставить:

```python
        # Orphan-bucket: ворклоги без категории или с категорией без work_type_id
        # учитываются в виртуальной строке «Не указана категория/вид работ».
        ORPHAN_WT_ID = "__unmapped__"
        ORPHAN_WT_LABEL = "Не указана категория/вид работ"
```

- [ ] **Step 2: Заменить early-continue на orphan-маршрутизацию**

Найти блок (строки ~984-993):

```python
            # Стандартный routing — по категории задачи.
            if cat_code is None:
                continue
            wt_id = code_to_wt.get(cat_code)
            if wt_id is None:
                continue
            # Факт по project считаем отдельно (через scenario allocations) — пропускаем здесь.
            if project_wt is not None and wt_id == project_wt.id:
                continue
            fact_per_emp_wt[emp_id][wt_id] = fact_per_emp_wt[emp_id].get(wt_id, 0.0) + h
```

Заменить на:

```python
            # Стандартный routing — по категории задачи.
            # cat_code is None → orphan; cat_code без mapping → orphan.
            if cat_code is None:
                fact_per_emp_wt[emp_id][ORPHAN_WT_ID] = (
                    fact_per_emp_wt[emp_id].get(ORPHAN_WT_ID, 0.0) + h
                )
                continue
            wt_id = code_to_wt.get(cat_code)
            if wt_id is None:
                fact_per_emp_wt[emp_id][ORPHAN_WT_ID] = (
                    fact_per_emp_wt[emp_id].get(ORPHAN_WT_ID, 0.0) + h
                )
                continue
            # Факт по project считаем отдельно (через scenario allocations) — пропускаем здесь.
            if project_wt is not None and wt_id == project_wt.id:
                continue
            fact_per_emp_wt[emp_id][wt_id] = fact_per_emp_wt[emp_id].get(wt_id, 0.0) + h
```

- [ ] **Step 3: Эмитить orphan-строку в сборке per-employee (перед other_foreign)**

Найти блок (строки ~1099-1123) — внутренний цикл `for wt in work_types:` в сборке `wt_breakdowns`. Сразу ПОСЛЕ закрытия этого цикла, но ДО `emp_items.append(...)`, добавить:

```python
                # Виртуальная orphan-строка вставляется ПЕРЕД other_foreign
                # (либо в конец, если other_foreign в этом блоке нет).
                orphan_fact = fact_per_emp_wt.get(emp.id, {}).get(ORPHAN_WT_ID, 0.0)
                if orphan_fact > 0:
                    other_foreign_idx = next(
                        (i for i, b in enumerate(wt_breakdowns)
                         if other_foreign_wt is not None
                         and b.work_type_id == other_foreign_wt.id),
                        len(wt_breakdowns),
                    )
                    wt_breakdowns.insert(other_foreign_idx, NormWorkTypeBreakdown(
                        work_type_id=ORPHAN_WT_ID,
                        label=ORPHAN_WT_LABEL,
                        plan_hours=0.0,
                        fact_hours=round(orphan_fact, 1),
                        pct=0.0,
                    ))
```

(Строка вставляется между концом цикла `for wt in work_types:` и блоком `emp_items.append(NormWorkEmployee(...))`.)

- [ ] **Step 4: Учесть orphan в per-employee total**

Найти строку (~1088): `plan_total = sum(plan_per_emp_wt.get(emp.id, {}).values())`

Текущая `fact_total = sum(fact_per_emp_wt.get(emp.id, {}).values())` уже включает orphan ключ (мы пишем в тот же dict). НО эта сумма сейчас ИСПОЛЬЗУЕТСЯ для `emp.fact_hours` и далее для `role_fact`. Это правильное поведение — orphan должен войти в общий факт. Менять не надо.

Однако перепроверить: `pct = (fact_total / plan_total * 100) if plan_total > 0 else 0.0` — orphan plan = 0, fact_total включит orphan_fact, поэтому процент по сотруднику может вырасти выше 100% — это корректное отображение перегруза.

Никаких правок здесь не нужно.

- [ ] **Step 5: Запустить orphan-тесты — все должны пройти**

Run: `py -3.10 -m pytest tests/test_norm_work_orphan.py -v`

Expected: 5 PASS.

- [ ] **Step 6: Прогнать соседние тесты — не сломали ли cross-team**

Run: `py -3.10 -m pytest tests/test_norm_work_cross_team.py tests/test_dashboard_endpoints.py -v`

Expected: PASS (все существующие).

---

### Task 3: Полный backend прогон

- [ ] **Step 1: Прогнать все backend тесты**

Run: `py -3.10 -m pytest tests/ -v`

Expected: PASS (за исключением известных красных из памяти `project_ci_red_pre_existing`: SyncPage lint не относится; hierarchy_rules test DB errors / test_sync_service mock drift / 3 e2e flakies — допустимо если не относится к виджету).

Если упадёт что-то новое в `test_dashboard_*` или `test_norm_*` — это регрессия, чинить.

---

### Task 4: Ручная проверка на проде-данных

- [ ] **Step 1: Перезапустить uvicorn**

Windows reload зависает (память `feedback_windows_uvicorn_reload`). Найти PID на :8000 и перезапустить:

```bash
# Найти PID на :8000 и убить, потом запустить
netstat -ano | grep :8000
# taskkill /F /PID <pid>
py -3.10 -m uvicorn app.main:app --port 8000
```

(в фоне или отдельном терминале)

- [ ] **Step 2: Проверить ответ API на Шутов / апрель 2026**

```bash
curl -s "http://localhost:8000/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2&month=4" \
  | py -3.10 -c "import json,sys; d=json.load(sys.stdin); \
    [print(e['name'], e['fact_hours'], [(w['label'], w['fact_hours']) for w in e['work_types']]) \
     for r in d['roles'] for e in r['employees'] if 'Шутов Сергей' in e['name']]"
```

Expected: Шутов Сергей `fact_hours=176.0`, в `work_types` есть строка `Не указана категория/вид работ` с `fact_hours=9.0`.

- [ ] **Step 3: Открыть `/dashboard` в браузере, фильтр период=апрель**

- Виджет «Нормированные работы»
- Найти карточку Шутов Сергей
- Должна быть красная строка «Не указана категория/вид работ — 9/0»
- Σ факт по Шутову = 176

---

### Task 5: Commit + push

- [ ] **Step 1: Stage + commit**

```bash
git add app/services/analytics_service.py tests/test_norm_work_orphan.py \
        docs/superpowers/specs/2026-05-01-orphan-worklogs-row-design.md \
        docs/superpowers/plans/2026-05-01-orphan-worklogs-row.md
git commit -m "$(cat <<'EOF'
feat(dashboard): orphan worklogs row in NormWork widget

Worklogs without category or with category lacking work_type_id were
silently dropped by the dashboard NormWork widget. Now they aggregate
into a virtual «Не указана категория/вид работ» row per employee, so
total fact equals sum of worklogs.

Foreign-team routing keeps priority over orphan (cross-team worklog
without category goes to «Прочие / Чужие задачи», not orphan).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

Expected: push succeeds, CI green (orphan tests + existing).

---

## Self-Review

**Spec coverage:**
- ✅ Виртуальная orphan-строка → Task 2 Step 2-3
- ✅ Условия попадания (priority foreign > orphan) → Task 2 Step 2 (foreign branch above)
- ✅ Plan=0, fact>0 уже подсвечивается красным фронтом → существующая логика `WorkTypeRow.overflowZeroPlan` (без правки)
- ✅ Sort_order перед other_foreign → Task 2 Step 3 использует insert-before-other_foreign (исправлено инлайн).
- ✅ Сводные итоги (Σ fact включает orphan) → Task 2 Step 4 (объяснение, что менять не надо, fact_total уже суммирует)
- ✅ Drill-down — out of scope, упомянут в спеке
- ✅ Tests: 5 кейсов покрывают все ветки → Task 1

**Placeholders:** нет.

**Type consistency:** `ORPHAN_WT_ID` использован одинаково везде. `NormWorkTypeBreakdown` — реальный класс из `app/schemas/dashboard.py`.

**Ambiguity:** Step 3 в Task 2 уточнён выше — заменить на insert-перед-other_foreign.
