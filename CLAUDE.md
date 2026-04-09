# Jira Analytics — Инструкции для Claude Code

## Контекст проекта

Локальный сервис для анализа данных из Jira Cloud и квартального планирования.
MVP на SQLite с сохранением совместимости для будущей миграции на PostgreSQL.
Однопользовательский режим для руководителя проектов.

## Технологический стек

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** SQLite (MVP) → PostgreSQL (позже)
- **HTTP Client:** httpx (async)
- **Frontend:** React + TypeScript (будет позже)

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
│   ├── api/endpoints/     # FastAPI роутеры (sync, scope)
│   ├── connectors/        # Jira HTTP клиент + Pydantic schemas
│   ├── models/            # SQLAlchemy модели (16 таблиц)
│   ├── repositories/      # Абстракция доступа к данным
│   ├── services/          # Бизнес-логика (sync, analytics, planning)
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
- **backlog_items** — квартальный бэклог (title, project_id, quarter, estimate_hours, priority)
- **planning_scenarios** — сценарии планирования (name, quarter, year)
- **scenario_allocations** — результаты сценариев (scenario_id, backlog_item_id, planned_hours)

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
```

## Roadmap

- [x] **M1** — Технический каркас (FastAPI, SQLite, SQLAlchemy, Alembic, конфигурация)
- [x] **M2** — Загрузка Jira (авторизация, sync issues/worklogs/comments/users, scope_projects)
- [ ] **M3** — Аналитика факта (категории, мэппинг, отчёты по людям и проектам, контекстные переключения)
- [ ] **M4** — Planning (производственный календарь, отпуска, процент обязательных работ, квартальный backlog)
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
Cloud ID: 00000000-0000-0000-0000-000000000000
Base URL: https://example.atlassian.net
```

## Полезные команды

```bash
# Тесты
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
