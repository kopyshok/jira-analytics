# Рабочие столы аналитиков — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Публичная (no-auth) страница-монитор `/desk/<token>` на сотрудника с настраиваемым набором из 12 виджетов; РМ создаёт/отзывает/перевыпускает столы для сотрудников своих команд.

**Architecture:** Новая таблица `work_desk` хранит токен + список виджетов + ссылку на сотрудника. Публичный роутер `desk_public` резолвит стол по токену (зависимость `get_desk_by_token`, без JWT) и отдаёт мету + данные виджетов лениво, переиспользуя существующие сервисы как адаптеры (новой расчётной логики нет). Управляющий роутер `work_desks` под `get_current_user` со скоупингом по командам. Фронт: standalone `DeskPage` вне `AppLayout`/`ProtectedRoute` + вкладка управления на `/capacity`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (batch), React 19 + TS + AntD 6 + TanStack Query, pytest, Playwright.

Спека: `docs/superpowers/specs/2026-06-15-analyst-work-desk-design.md`.

**Каталог виджетов (12 ключей, константа `WIDGET_KEYS` в `app/services/work_desk_widgets.py`):**
`my_tasks`, `weekly_load`, `my_conflicts`, `hours_balance`, `unlogged_days`, `category_breakdown`, `team_absences`, `team_availability`, `production_calendar`, `quarter_deadlines`, `external_help`, `recent_changes`.

---

## Phase 0 — Backend foundation: модель + миграция

### Task 0.1: Модель `WorkDesk`

**Files:**
- Create: `app/models/work_desk.py`
- Modify: `app/models/__init__.py` (добавить импорт `WorkDesk`)
- Test: `tests/test_work_desk_model.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_work_desk_model.py
from app.models.work_desk import WorkDesk

def test_work_desk_defaults(db_session):
    desk = WorkDesk(employee_id="emp-1", token="tok-abc", created_by_user_id="usr-1")
    db_session.add(desk)
    db_session.commit()
    assert desk.id is not None
    assert desk.revoked_at is None
    assert desk.enabled_widgets == []
    assert desk.is_active is True  # property: revoked_at is None
```

- [ ] **Step 2: Run, expect fail** — `py -3.10 -m pytest tests/test_work_desk_model.py -v` → ImportError.

- [ ] **Step 3: Implement**

```python
# app/models/work_desk.py
"""Рабочий стол аналитика — публичная страница-монитор по токену."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class WorkDesk(Base, TimestampMixin):
    __tablename__ = "work_desks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    enabled_widgets_raw: Mapped[str] = mapped_column(
        "enabled_widgets", Text, nullable=False, default="[]", server_default="[]"
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    employee = relationship("Employee")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def enabled_widgets(self) -> list[str]:
        try:
            return json.loads(self.enabled_widgets_raw or "[]")
        except (TypeError, ValueError):
            return []

    @enabled_widgets.setter
    def enabled_widgets(self, value: list[str]) -> None:
        self.enabled_widgets_raw = json.dumps(list(value or []))
```

Добавить в `app/models/__init__.py`: `from app.models.work_desk import WorkDesk` и в `__all__`.

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `feat(models): таблица work_desks для рабочих столов аналитиков`

### Task 0.2: Alembic миграция

**Files:**
- Create: `alembic/versions/<hash>_add_work_desks.py` (через autogenerate)

- [ ] **Step 1:** `alembic revision --autogenerate -m "add work_desks table"`
- [ ] **Step 2:** Проверить, что миграция в batch-режиме создаёт таблицу с FK на `employees`/`users`, unique index на `token`, index на `employee_id`. Если autogenerate не обернул в batch — обернуть вручную (паттерн соседних миграций).
- [ ] **Step 3:** `alembic upgrade head` → без ошибок.
- [ ] **Step 4:** `alembic downgrade -1 && alembic upgrade head` → таблица пересоздаётся чисто.
- [ ] **Step 5: Commit** — `feat(db): миграция work_desks`

---

## Phase 1 — Токен-доступ + публичная мета

### Task 1.1: Репозиторий + сервис создания токена

**Files:**
- Create: `app/services/work_desk_service.py`
- Test: `tests/test_work_desk_service.py`

Сервис `WorkDeskService` — операции: `create(db, employee_id, enabled_widgets, created_by_user_id)`, `get_active_by_employee(db, employee_id)`, `get_by_token(db, token)`, `revoke(db, desk_id)`, `regenerate(db, desk_id)`, `set_widgets(db, desk_id, widgets)`. Токен — `secrets.token_urlsafe(32)`. Инвариант: при `create`/`regenerate` старый активный стол того же сотрудника отзывается.

- [ ] **Step 1: Failing tests**

```python
# tests/test_work_desk_service.py
from app.services.work_desk_service import WorkDeskService

svc = WorkDeskService()

def test_create_generates_unique_token(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    assert len(desk.token) >= 32
    assert desk.enabled_widgets == ["hours_balance"]

def test_create_revokes_previous_active(db_session, seed_employee):
    first = svc.create(db_session, seed_employee.id, [], "usr-1")
    second = svc.create(db_session, seed_employee.id, [], "usr-1")
    db_session.refresh(first)
    assert first.revoked_at is not None
    assert second.is_active

def test_get_by_token_skips_revoked(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    svc.revoke(db_session, desk.id)
    assert svc.get_by_token(db_session, desk.token) is None

def test_regenerate_changes_token(db_session, seed_employee):
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    old_token = desk.token
    new_desk = svc.regenerate(db_session, desk.id)
    assert new_desk.token != old_token
    assert svc.get_by_token(db_session, old_token) is None
```

Добавить фикстуру `seed_employee` если её нет (минимальный `Employee` + commit) в `tests/conftest.py` или локально.

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement** `WorkDeskService`. `get_by_token` фильтрует `revoked_at IS NULL`. `revoke` ставит `revoked_at = datetime.utcnow()`. `regenerate` = revoke + create с теми же `enabled_widgets` и `created_by_user_id`.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `feat(services): WorkDeskService — токены и жизненный цикл столов`

### Task 1.2: Зависимость `get_desk_by_token` + публичный роутер (мета)

**Files:**
- Create: `app/api/endpoints/desk_public.py`
- Create: `app/schemas/work_desk.py` (Pydantic ответы)
- Modify: `app/main.py` или `app/api/router.py` (подключить роутер; узнать как подключаются остальные)
- Test: `tests/test_desk_public_endpoint.py`

Зависимость в `desk_public.py`:
```python
def get_desk_by_token(token: str, db: Session = Depends(get_db)) -> WorkDesk:
    desk = WorkDeskService().get_by_token(db, token)
    if desk is None:
        raise HTTPException(status_code=404, detail="Стол не найден")
    return desk
```

`GET /desk/{token}` → `DeskMeta`: `employee` (id, display_name, avatar_url), `teams` (список команд сотрудника через `EmployeeTeam`), `enabled_widgets`, `period` (текущий год/квартал — из даты сервера). Side-effect: после чтения diff обновляет `last_viewed_at = utcnow()` (значение «до» уже захвачено для виджета recent_changes — здесь только апдейт).

- [ ] **Step 1: Failing test**

```python
# tests/test_desk_public_endpoint.py — использует TestClient
def test_meta_valid_token(client, db_session, seed_employee):
    from app.services.work_desk_service import WorkDeskService
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    r = client.get(f"/api/v1/desk/{desk.token}")
    assert r.status_code == 200
    body = r.json()
    assert body["employee"]["display_name"] == seed_employee.display_name
    assert body["enabled_widgets"] == ["hours_balance"]

def test_meta_unknown_token_404(client):
    assert client.get("/api/v1/desk/nope").status_code == 404

def test_meta_revoked_token_404(client, db_session, seed_employee):
    from app.services.work_desk_service import WorkDeskService
    svc = WorkDeskService()
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    svc.revoke(db_session, desk.id)
    assert client.get(f"/api/v1/desk/{desk.token}").status_code == 404
```

> ORM caveat (см. tests/CLAUDE.md): endpoint-тесты должны переопределять `get_db` на ту же сессию, что и фикстуры. Следовать существующему паттерну endpoint-тестов.

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement** роутер + схему + подключение. Роутер БЕЗ `get_current_user`. Префикс согласовать с тем, как смонтированы остальные (`/api/v1`).
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `feat(api): публичный desk endpoint — мета по токену`

---

## Phase 2 — Управление столами (РМ)

### Task 2.1: Управляющий роутер CRUD + скоупинг по команде

**Files:**
- Create: `app/api/endpoints/work_desks.py`
- Modify: router include
- Test: `tests/test_work_desks_admin_endpoint.py`

Эндпоинты под `Depends(get_current_user)`:
- `GET /work-desks` — столы сотрудников из команд пользователя (`user.selected_teams`; если пусто — все команды, к которым у него доступ — следовать паттерну других эндпоинтов). Каждый элемент: employee, статус (active/revoked/none), token (только для отображения ссылки), enabled_widgets.
- `POST /work-desks` `{employee_id, enabled_widgets}` → создаёт. **Проверка скоупинга:** сотрудник должен состоять в одной из команд пользователя через `EmployeeTeam`; иначе 403.
- `PATCH /work-desks/{id}` `{enabled_widgets}` → меняет виджеты (проверка скоупинга).
- `POST /work-desks/{id}/revoke` → отзыв.
- `POST /work-desks/{id}/regenerate` → перевыпуск.

Хелпер `_assert_employee_in_user_teams(db, user, employee_id)` → 403 если нет пересечения.

- [ ] **Step 1: Failing tests**

```python
def test_create_desk_for_own_team(client_as_manager, db_session, seed_employee_in_team):
    r = client_as_manager.post("/api/v1/work-desks",
        json={"employee_id": seed_employee_in_team.id, "enabled_widgets": ["hours_balance"]})
    assert r.status_code == 201
    assert r.json()["token"]

def test_create_desk_foreign_employee_403(client_as_manager, db_session, seed_employee_other_team):
    r = client_as_manager.post("/api/v1/work-desks",
        json={"employee_id": seed_employee_other_team.id, "enabled_widgets": []})
    assert r.status_code == 403

def test_regenerate_kills_old_link(client_as_manager, db_session, seed_employee_in_team):
    created = client_as_manager.post("/api/v1/work-desks",
        json={"employee_id": seed_employee_in_team.id, "enabled_widgets": []}).json()
    old = created["token"]
    desk_id = created["id"]
    client_as_manager.post(f"/api/v1/work-desks/{desk_id}/regenerate")
    assert client_as_manager.get(f"/api/v1/desk/{old}").status_code == 404
```

Фикстуры `client_as_manager` (авторизованный manager с `selected_teams=["TeamA"]`), `seed_employee_in_team` (в TeamA), `seed_employee_other_team` (в TeamB) — следовать существующим auth-фикстурам тестов.

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `feat(api): управление рабочими столами (CRUD + скоупинг по команде)`

---

## Phase 3 — Данные виджетов (адаптеры поверх существующих сервисов)

Общий эндпоинт: `GET /desk/{token}/widget/{key}` в `desk_public.py`, без auth, через `get_desk_by_token`. Диспетчер по `key` → функция-адаптер в `app/services/work_desk_widgets.py`. Если key не входит в `desk.enabled_widgets` → 403. Если key неизвестен → 404.

Каждый адаптер получает `(db, desk, year, quarter)` и переиспользует существующий сервис (НЕ пишет новую расчётную логику). Возвращает простой dict под фронт. Перед реализацией адаптера **прочитать сигнатуру целевого метода в указанном файле** — сигнатуры в проекте уточняются.

### Task 3.0: Каркас диспетчера + тест enabled-gate

**Files:**
- Create: `app/services/work_desk_widgets.py` (`WIDGET_KEYS`, `dispatch(db, desk, key, year, quarter)`)
- Modify: `app/api/endpoints/desk_public.py` (route `/widget/{key}`)
- Test: `tests/test_desk_widgets.py`

- [ ] **Step 1: Failing test**

```python
def test_widget_not_enabled_403(client, db_session, seed_employee):
    from app.services.work_desk_service import WorkDeskService
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/my_tasks").status_code == 403

def test_widget_unknown_key_404(client, db_session, seed_employee):
    from app.services.work_desk_service import WorkDeskService
    desk = WorkDeskService().create(db_session, seed_employee.id, ["bogus"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/bogus").status_code == 404
```

- [ ] **Step 2-5:** Implement каркас + dispatcher с реестром `{}` (пока пустой), gate-логика, тесты pass, commit `feat(api): диспетчер виджетов рабочего стола`.

### Task 3.1–3.12: Адаптеры виджетов

Для каждого: написать тест (адаптер на seed-данных возвращает dict ожидаемой формы и не падает) → реализовать адаптер, вызвав указанный сервис с `employee_id = desk.employee_id` и командами сотрудника → тест pass → commit `feat(desk): виджет <key>`.

| Key | Сервис/файл для чтения сигнатуры | Что вернуть (контракт dict) |
|---|---|---|
| `my_tasks` | `ResourcePlanningService.get_gantt` (`app/services/resource_planning_service.py`); фильтр `ResourcePlanAssignment.employee_id` | `{tasks: [{key, title, phase, start_date, end_date, hours, jira_url}]}` |
| `weekly_load` | `CapacityService` (`app/services/capacity_service.py`) — план/факт по неделям для employee | `{weeks: [{week_start, norm_hours, fact_hours}]}` |
| `my_conflicts` | `ConflictAggregator` + `PlanConflict` (`app/services/conflict_aggregator.py`) по employee_id | `{conflicts: [{type, window_start, window_end, metric_value}]}` |
| `hours_balance` | `HoursBalanceService.compute_employee` (`app/services/hours_balance_service.py`) | `{balance_hours, days: [{date, kind, delta}], sparkline: [...]}` |
| `unlogged_days` | тот же сервис, дни с `kind=="skip"` | `{days: [{date, expected_hours}]}` |
| `category_breakdown` | `HoursBreakdownService` или `AnalyticsService` (`app/services/analytics_service.py`) по employee | `{categories: [{label, hours}]}` |
| `team_absences` | `Absence` + `AbsenceReason` по командам сотрудника | `{absences: [{employee_name, start_date, end_date, reason_label, color}]}` |
| `team_availability` | `ResourcePlanningService.get_gantt` + `ScheduledBlock` по команде | `{week_start, members: [{name, busy: [{label, start, end}]}]}` |
| `production_calendar` | `ProductionCalendarService` (`is_workday`, `hours_in_range_map`) | `{quarter_workdays, remaining_workdays, days: [{date, kind, hours}]}` |
| `quarter_deadlines` | `BacklogService` / `BacklogItem` по командам, текущий квартал | `{items: [{key, title, due_date, status}]}` |
| `external_help` | `ExecutiveDashboardService` cross-team / alien-hours логика (`app/services/executive_dashboard_service.py`) для employee | `{own_hours, alien_hours, by_team: [{team, hours}]}` |
| `recent_changes` | `ResourcePlanAssignment.updated_at > desk.last_viewed_at_before` (значение до апдейта меты) | `{changes: [{key, title, change: "added"|"moved", start_date, end_date}]}` |

> `recent_changes`: эндпоинт меты должен сохранить «предыдущее» `last_viewed_at` до его обновления, чтобы виджет сравнивал с ним. Хранить prev в самом desk нельзя — передавать через сравнение `updated_at > COALESCE(last_viewed_at, '1970')` на момент запроса виджета (last_viewed_at обновляется только метой, виджеты грузятся после — допустимое приближение для v1).

Каждый адаптер защищён от пустых данных (нет назначений → `{tasks: []}`), без 500.

---

## Phase 4 — Фронтенд: публичная страница

### Task 4.1: Роут + каркас `DeskPage`

**Files:**
- Create: `frontend/src/pages/DeskPage.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx` (ленивый экспорт `DeskPage`)
- Modify: `frontend/src/routes.tsx` — добавить роут `{ path: '/desk/:token', element: page(<DeskPage />) }` как ребёнок `AuthLayout` (рядом с `/login`), **без** `AppLayout` и `ProtectedRoute`.
- Create: `frontend/src/api/desk.ts` (fetch меты и виджета по token; без auth-cookie зависимости — но api.get и так шлёт cookie, это безвредно)

- [ ] **Step 1:** Добавить роут + lazy export. `DeskPage` читает `:token` из `useParams`, грузит мету через TanStack Query (`['desk', token]`), при 404 показывает «Стол не найден или ссылка отозвана».
- [ ] **Step 2:** Шапка: имя + аватар сотрудника, команды, текущий квартал. Aurora-тема (использовать существующий ConfigProvider — проверить, что тема применяется вне AppLayout; если тема висит в `main.tsx` глобально — ок).
- [ ] **Step 3:** Сетка виджетов (AntD `Row`/`Col`, responsive `xs/sm/lg`), для каждого включённого ключа — компонент-обёртка, грузящая свои данные лениво.
- [ ] **Step 4:** Авто-обновление: `refetchInterval` на queries (например 60s).
- [ ] **Step 5: Commit** — `feat(frontend): публичная страница рабочего стола /desk/:token`

### Task 4.2–4.x: Компоненты виджетов

**Files:**
- Create: `frontend/src/components/desk/<Key>Widget.tsx` (по компоненту на ключ)
- Переиспользовать существующие dashboard-компоненты где близко (напр. `NormWorkWidget` для `external_help`); где компонент завязан на auth/team-filter — обернуть, приняв данные пропсами/по token-API.

Для каждого виджета: компонент рендерит данные из `GET /desk/{token}/widget/{key}`, состояние загрузки (skeleton), пустое состояние («Нет данных»). Графики — Recharts (как на dashboard). Коммитить пачками по 2-3 виджета: `feat(frontend): виджеты рабочего стола <keys>`.

Минимальные представления:
- `my_tasks` — таблица/таймлайн задач с датами + ссылка в Jira.
- `weekly_load` — bar plan vs fact по неделям.
- `my_conflicts` — список с типом и окном.
- `hours_balance` — большое число баланса + sparkline.
- `unlogged_days` — список дат + кол-во.
- `category_breakdown` — pie/bar по категориям.
- `team_absences` — список/мини-календарь отпусков коллег.
- `team_availability` — кто чем занят на неделе.
- `production_calendar` — остаток рабочих дней + мини-календарь.
- `quarter_deadlines` — список с датами дедлайнов.
- `external_help` — свои vs чужие часы (как NormWorkWidget).
- `recent_changes` — список изменений с прошлого визита.

---

## Phase 5 — Управление на /capacity

### Task 5.1: Вкладка «Рабочие столы»

**Files:**
- Create: `frontend/src/components/capacity/WorkDesksTab.tsx`
- Modify: `frontend/src/pages/CapacityPage.tsx` (добавить вкладку)
- Create: `frontend/src/api/workDesks.ts` + `frontend/src/hooks/useWorkDesks.ts` (TanStack Query CRUD)

- [ ] **Step 1:** Хуки: `useWorkDesks()` (GET список), `useCreateDesk`, `useUpdateDeskWidgets`, `useRevokeDesk`, `useRegenerateDesk` — с инвалидацией `['work-desks']`.
- [ ] **Step 2:** Таблица сотрудников команды: колонки — сотрудник, статус стола (нет/активен/отозван), ссылка (кнопка «Копировать ссылку» → `/desk/<token>`), действия.
- [ ] **Step 3:** Создание/редактирование: модалка с чекбоксами 12 виджетов (лейблы на русском). При сохранении — POST или PATCH.
- [ ] **Step 4:** Кнопки «Отозвать» (Popconfirm) и «Перевыпустить» (Popconfirm, предупреждает что старая ссылка умрёт).
- [ ] **Step 5: Commit** — `feat(frontend): вкладка управления рабочими столами на /capacity`

---

## Phase 6 — E2E + верификация

### Task 6.1: E2E happy path

**Files:**
- Create: `frontend/e2e/work-desk.spec.ts`
- Modify: `scripts/seed_e2e.py` (если нужен seed стола для e2e)

- [ ] **Step 1:** Тест: РМ создаёт стол на /capacity → копирует ссылку → открывает `/desk/<token>` в новой странице без логина → виджеты видны.
- [ ] **Step 2:** Тест: отзыв → `/desk/<token>` показывает «Стол не найден».
- [ ] **Step 3: Commit** — `test(e2e): рабочие столы аналитиков`

### Task 6.2: Финальная верификация

- [ ] `py -3.10 -m pytest tests/ -q` — все зелёные (кроме известных pre-existing).
- [ ] `cd frontend && npm run lint && npm run build` — чисто.
- [ ] Ручной смок: создать стол на /capacity, открыть ссылку в инкогнито (без логина) — виджеты грузятся.
- [ ] Перезапустить backend (убить PID на :8000) после backend-правок — `--reload` на Windows зависает.

---

## Self-review (выполнено при написании)

- **Spec coverage:** модель/токен/мета/CRUD/скоупинг/12 виджетов/публичная страница/управление/отзыв-перевыпуск/E2E — все разделы спеки покрыты задачами.
- **Placeholders:** инфра-задачи с полным кодом; виджет-адаптеры заданы контрактом dict + точным сервисом для чтения сигнатуры (не «TODO» — конкретная инструкция; сигнатуры сервисов читаются исполнителем, т.к. в памяти могут расходиться).
- **Type consistency:** `enabled_widgets` (property) / `enabled_widgets_raw` (column), `get_by_token` / `get_active_by_employee` / `revoke` / `regenerate` — имена согласованы между Phase 1 и Phase 2/3.
