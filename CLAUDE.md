# Jira Analytics — Инструкции для Claude Code

## Контекст проекта

Локальный сервис для анализа данных из Jira Cloud и квартального планирования.
MVP на SQLite с сохранением совместимости для будущей миграции на PostgreSQL.
Однопользовательский режим для руководителя проектов.

## Технологический стек

- **Backend:** Python 3.10+ (dev/test: `py -3.10`) + FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** SQLite (MVP) → PostgreSQL (позже)
- **HTTP Client:** httpx (async)
- **Frontend:** React + TypeScript (будет позже)

> На Windows тесты запускаются через `py -3.10 -m pytest` — в Python 3.14 (обычный `python`) не установлен pytest.

## Архитектура слоёв

```
Connector Layer → Service Layer → Repository Layer → Database
     ↓                 ↓                 ↓
  Jira API      Бизнес-логика      SQLAlchemy ORM
```

Архитектурный принцип: ни один модуль прикладной логики не зависит от SQLite-специфичных особенностей.

## Структура проекта

```
jira-analytics/
├── app/
│   ├── api/endpoints/     # FastAPI роутеры (sync, scope, analytics, mapping, capacity, backlog, planning)
│   ├── connectors/        # Jira HTTP клиент + Pydantic schemas
│   ├── models/            # SQLAlchemy модели (16 таблиц)
│   ├── repositories/      # Абстракция доступа к данным
│   ├── services/          # Бизнес-логика (sync, category_resolver, mapping, analytics, capacity, planning)
│   ├── config.py          # Pydantic Settings
│   ├── database.py        # Engine + Session + Base
│   └── main.py            # FastAPI app
├── alembic/               # Миграции БД
├── tests/                 # pytest + pytest-asyncio
└── data/                  # SQLite файл (gitignored)
```

## Быстрый старт

```bash
# Установка
pip install -r requirements.txt
cp .env.example .env
mkdir -p data exports

# Настройка .env
JIRA_BASE_URL=https://YOUR-DOMAIN.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token

# Миграции и запуск
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Схема данных (16 таблиц)

### Основные сущности (Jira sync)
- **employees** — справочник сотрудников (id, jira_account_id, display_name, email, is_active, role, team, department)
- **projects** — проекты Jira (id, jira_project_id, key, name)
- **issues** — задачи и эпики (id, jira_issue_id, key, summary, issue_type, status, parent_id, project_id, category)
- **worklogs** — фактические трудозатраты (id, jira_worklog_id, issue_id, employee_id, started_at, hours)
- **comments** — комментарии Jira (id, jira_comment_id, issue_id, author_id, body)
- **sync_state** — состояние инкрементальной синхронизации

### Конфигурация области выгрузки
- **scope_projects** — разрешённые проекты Jira для загрузки (jira_project_key, is_enabled)
- **scope_roots** — корневые эпики/задачи для авто-раскладки (category_code, jira_issue_key)
- **category_overrides** — точечные переопределения категорий (jira_issue_key, category_code)
- **worklog_quality_rules** — правила выявления сомнительных worklog (rule_code, threshold_value)

### Категории и мэппинг
- **category_mappings** — связь сущностей с категориями (entity_type, entity_id, category, source_rule)

### Планирование
- **vacations** — отпуска сотрудников (employee_id, start_date, end_date, hours_total)
- **monthly_capacity_rules** — процентные вычеты от нормы часов (month, year, percent_of_norm)
- **backlog_items** — квартальный бэклог (title, project_id, quarter, year, estimate_hours, priority)
- **planning_scenarios** — сценарии планирования (name, quarter, year)
- **scenario_allocations** — результаты сценариев (scenario_id, backlog_item_id, planned_hours, included_flag)

## Управленческие категории работ

Приоритет определения категории:
1. Явное переопределение задачи (category_overrides)
2. Ближайший настроенный корневой эпик/задача (scope_roots)
3. Системные правила качества данных (worklog_quality_rules)
4. Категория «незаполненные / сомнительные worklog»

Категории:
- Сопровождение и консультация
- Анализ/развитие бизнес-процессов
- Встречи вне развития и консультации
- Административные потери
- Внутренние коммуникации
- Незаполненные / сомнительные worklog
- Технический долг / прочее

## API Endpoints

```
# Health & Info
GET  /health                         # Healthcheck
GET  /api/v1/                        # API info

# Sync (загрузка данных из Jira)
GET  /api/v1/sync/test-connection    # Проверка связи с Jira
POST /api/v1/sync/projects           # Синхронизация проектов (по scope)
POST /api/v1/sync/issues             # Синхронизация задач
POST /api/v1/sync/worklogs           # Синхронизация worklogs
POST /api/v1/sync/comments           # Синхронизация комментариев
POST /api/v1/sync/full               # Полная синхронизация
GET  /api/v1/sync/status             # Статус синхронизации

# Scope (конфигурация области загрузки)
GET    /api/v1/scope/projects        # Список scope-проектов
POST   /api/v1/scope/projects        # Добавить проект в scope
DELETE /api/v1/scope/projects/{key}  # Удалить проект из scope
GET    /api/v1/scope/roots           # Список корневых эпиков/задач
POST   /api/v1/scope/roots           # Добавить корневой элемент
DELETE /api/v1/scope/roots/{id}      # Удалить корневой элемент
GET    /api/v1/scope/overrides       # Список переопределений
POST   /api/v1/scope/overrides       # Добавить переопределение
DELETE /api/v1/scope/overrides/{key} # Удалить переопределение

# Mapping (пересчёт категорий)
POST /api/v1/mapping/recalculate     # Пересчитать категории по текущим правилам
GET  /api/v1/mapping/summary         # Сводка по распределению категорий

# Analytics (отчёты факта)
GET /api/v1/analytics/hours-by-employee   # Часы по сотрудникам (+ фильтры по периоду/проекту/категории)
GET /api/v1/analytics/hours-by-project    # Часы по проектам
GET /api/v1/analytics/hours-by-category   # Часы по категориям
GET /api/v1/analytics/hours-by-period     # Динамика по дням/неделям/месяцам
GET /api/v1/analytics/context-switching   # Контекстные переключения сотрудников

# Capacity (планирование ёмкости)
GET    /api/v1/capacity/vacations            # Список отпусков
POST   /api/v1/capacity/vacations            # Добавить отпуск
DELETE /api/v1/capacity/vacations/{id}
GET    /api/v1/capacity/rules                # Правила обязательных работ (% от нормы)
POST   /api/v1/capacity/rules                # Upsert правила (по year+month)
DELETE /api/v1/capacity/rules/{id}
GET    /api/v1/capacity/monthly/{employee_id}?year=&month=
GET    /api/v1/capacity/quarter/{employee_id}?year=&quarter=
GET    /api/v1/capacity/team?year=&quarter=  # Активная команда за квартал

# Backlog (квартальный бэклог задач-кандидатов)
GET    /api/v1/backlog?year=&quarter=&project_id=   # Список (сорт: priority, None в конец)
POST   /api/v1/backlog                              # Создать элемент
GET    /api/v1/backlog/{id}                         # Получить элемент
PATCH  /api/v1/backlog/{id}                         # Частичное обновление
DELETE /api/v1/backlog/{id}

# Planning (сценарии квартального планирования)
GET    /api/v1/planning/scenarios?year=&quarter=    # Список сценариев
GET    /api/v1/planning/scenarios/{id}              # Один сценарий
DELETE /api/v1/planning/scenarios/{id}              # Удалить сценарий + его раскладки
GET    /api/v1/planning/scenarios/{id}/allocations  # Сохранённые раскладки
POST   /api/v1/planning/scenarios/generate          # Сгенерировать новый сценарий (greedy)
```

## Roadmap

- [x] **M1** — Технический каркас (FastAPI, SQLite, SQLAlchemy, Alembic, конфигурация)
- [x] **M2** — Загрузка Jira (авторизация, sync issues/worklogs/comments/users, scope_projects)
- [x] **M3** — Аналитика факта (CategoryResolver, MappingService, AnalyticsService: отчёты по людям/проектам/категориям/периодам и контекстные переключения)
- [x] **M4** — Planning
  - [x] CapacityService: производственный календарь (пн-пт), отпуска, `monthly_capacity_rules`, monthly/quarter/team ёмкость
  - [x] Backlog items CRUD (фильтры по year/quarter/project, сортировка по priority)
  - [x] Planning scenarios (жадная раскладка по приоритету с учётом team capacity)
- [ ] **M5** — Экспорты и polish (PDF, Excel, PPTX, фильтры интерфейса)

## Принципы кода

- Все SQL через SQLAlchemy ORM (никакого raw SQL и vendor-specific SQL)
- Миграции через Alembic (даже для SQLite, batch mode)
- Async где возможно (httpx, FastAPI)
- Type hints везде
- Docstrings на русском для бизнес-логики
- UUID строковые ключи (String(36)) для всех таблиц
- Служебные timestamps: created_at, updated_at, synced_at

## Принципы совместимости с PostgreSQL

- ORM как единственная точка доступа к БД
- Никакого vendor-specific SQL в сервисах
- Миграции обязательны даже для SQLite
- UUID, внешние ключи и служебные timestamps
- Конфигурируемые источники и пути экспорта

## Jira Cloud

```
Cloud ID: 604dc198-0f39-4cc9-bfbf-0a7cfdddd286
Base URL: https://itgri.atlassian.net
```

## Ключевые архитектурные моменты

### Определение категории (CategoryResolver)
Приоритет: `category_overrides` → ближайший `scope_roots` вверх по `parent_id` → `worklog_quality_rules` → fallback. Worklog наследует категорию своей задачи.

### MappingService
Идемпотентно пересчитывает таблицу `category_mappings` и денормализованное поле `Issue.category` под текущие правила. Коммитит внутри себя — тесты должны чистить таблицы после себя (см. ниже).

### CapacityService
Формула: `available = workdays × hours_per_day − vacation_hours − mandatory_hours`, с клампом `max(0.0, ...)`. Производственный календарь MVP — просто понедельник-пятница (`weekday() < 5`), без российских праздников. Отпуска пересекаются с месяцем через `max(start, month_start)` / `min(end, month_end)`. `mandatory_hours = norm × percent_of_norm / 100` берётся из `monthly_capacity_rules`. Квартал = три месяца по `QUARTER_MONTHS = {1:(1,2,3), ...}`.

### PlanningService
Жадная раскладка бэклога по приоритету. Ёмкость квартала = сумма `total_available_hours` активной команды из `CapacityService.team_quarter_capacity`. Сортировка: `(priority is None, priority, estimate_hours, title)` — меньше priority раньше, `None`-priority в конец. Задачи берутся **целиком** (не дробим): если `estimate_hours` помещается в остаток — включаем, иначе пропускаем (`reason="no_capacity_left"`). Пустая/нулевая оценка → `reason="no_estimate"`, пропуск. `ScenarioAllocation` сохраняется и для включённых, и для пропущенных задач (различаются по `included_flag`). Коммитит внутри себя — тесты опираются на очистку в `conftest`. Формат квартала в БД: `"Q1"`..`"Q4"` (строка), в API принимаем число `1..4`. `backlog_items.year + quarter` фильтруются автоматически, либо можно передать явный `backlog_item_ids`.

### Тестовые фикстуры (tests/conftest.py)
`engine` — session-scoped in-memory SQLite. `db_session` — function-scoped, **после каждого теста явно удаляет строки из всех таблиц** (`table.delete()` в reverse-order), потому что сервисы вроде `MappingService` коммитят внутри себя, и обычный `rollback()` на commit'нутых данных не сработает. Если добавляете сервис, который коммитит — НЕ ослабляйте эту очистку.

## Полезные команды

```bash
# Тесты (Windows dev: используйте py -3.10)
py -3.10 -m pytest tests/ -v
py -3.10 -m pytest tests/test_capacity_service.py -v
py -3.10 -m pytest tests/test_capacity_service.py::TestMonthlyCapacity::test_vacation_inside_month -v

# Linux/macOS
pytest tests/ -v
pytest tests/test_models.py -v

# Миграции
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# Линтинг
ruff check app/
ruff format app/

# Makefile
make dev       # Установка + настройка
make run       # Запуск сервера
make test      # Запуск тестов
make migrate   # Применить миграции
make clean     # Очистка
```
