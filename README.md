# Jira Analytics

Сервис аналитики трудозатрат на основе данных из Jira Cloud.

## 🚀 Быстрый старт

```bash
# Клонирование
git clone https://github.com/kopyshok/jira-analytics.git
cd jira-analytics

# Установка зависимостей
make dev

# Настройка Jira (см. раздел ниже)
cp .env.example .env
# Отредактируйте .env и укажите Jira credentials

# Миграции
make migrate

# Запуск backend
make run

# Запуск frontend (в отдельном терминале)
cd frontend
cp .env.example .env
npm install
npm run dev

# Smoke-проверка локального запуска (PowerShell, из корня проекта)
.\scripts\smoke-local.ps1

# Browser E2E без Jira-зависимости (первый запуск скачает Chromium)
.\scripts\e2e-local.ps1 -InstallBrowsers
```

API: http://localhost:8000  
Документация: http://localhost:8000/docs  
Frontend: http://localhost:5173

## 🧪 Рабочий локальный smoke

Для M6 добавлен smoke-runner, который применяет миграции, поднимает отсутствующие
backend/frontend dev-серверы, проверяет ключевые URL и останавливает только
те процессы, которые запустил сам:

```powershell
.\scripts\smoke-local.ps1
```

Проверяются:

- `GET /health`
- `GET /api/v1/`
- `GET /api/v1/projects`
- `GET /api/v1/employees`
- frontend `/`
- Vite module `/src/main.tsx`

Если серверы уже запущены, скрипт переиспользует их:

```powershell
.\scripts\smoke-local.ps1 -NoStart
```

## 🎭 Browser E2E

Playwright E2E запускает backend на отдельной SQLite-базе `data/e2e.db`,
поднимает Vite frontend, проходит по основным разделам SPA, CRUD-потокам и
download-проверкам экспортов. Тесты падают при browser `console.error` или
`pageerror`. Jira credentials для этого не нужны.
Перед запуском база пересоздаётся, применяются Alembic-миграции и seed:
сотрудник `E2E Analyst` и проект `E2E`.

Первый запуск:

```powershell
.\scripts\e2e-local.ps1 -InstallBrowsers
```

Повторные запуски:

```powershell
.\scripts\e2e-local.ps1
```

То же из `frontend/`:

```bash
npm run e2e:install
npm run e2e
```

## 🔧 Настройка Jira Cloud

### 1. Создание API токена

1. Перейдите на https://id.atlassian.com/manage-profile/security/api-tokens
2. Нажмите "Create API token"
3. Укажите имя (например, "jira-analytics")
4. Скопируйте токен

### 2. Настройка .env

```env
DEBUG=true
DATABASE_URL=sqlite:///./data/jira_analytics.db
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token-here
```

Frontend читает URL API из `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. Проверка соединения

```bash
curl http://localhost:8000/api/v1/sync/test-connection
```

## 📡 API эндпоинты

### Синхронизация

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/employees` | GET | Список сотрудников |
| `/api/v1/projects` | GET | Список проектов |
| `/api/v1/sync/test-connection` | GET | Проверка соединения с Jira |
| `/api/v1/sync/projects` | POST | Синхронизация проектов |
| `/api/v1/sync/issues` | POST | Синхронизация задач |
| `/api/v1/sync/worklogs` | POST | Синхронизация worklogs |
| `/api/v1/sync/comments` | POST | Синхронизация комментариев |
| `/api/v1/sync/full` | POST | Полная синхронизация |
| `/api/v1/sync/status` | GET | Статус синхронизации |

### Примеры запросов

```bash
# Проверить соединение
curl http://localhost:8000/api/v1/sync/test-connection

# Синхронизировать проекты
curl -X POST http://localhost:8000/api/v1/sync/projects

# Синхронизировать задачи конкретных проектов
curl -X POST http://localhost:8000/api/v1/sync/issues \
  -H "Content-Type: application/json" \
  -d '{"project_keys": ["PRJ", "ECO"], "incremental": true}'

# Полная синхронизация
curl -X POST http://localhost:8000/api/v1/sync/full
```

## 📁 Структура проекта

```
jira-analytics/
├── app/
│   ├── api/endpoints/        # FastAPI routers
│   ├── connectors/           # Jira HTTP client + schemas
│   ├── models/               # SQLAlchemy models
│   ├── repositories/         # Data access layer
│   ├── services/             # Business logic
│   ├── config.py             # Settings from env
│   ├── database.py           # Engine + Session + Base
│   └── main.py               # FastAPI app
├── frontend/                 # React + TypeScript SPA
│   ├── src/api/              # API client + domain modules
│   ├── src/hooks/            # TanStack Query hooks
│   ├── src/pages/            # Application pages
│   ├── src/components/       # Shared and layout components
│   └── src/types/            # API TypeScript interfaces
├── alembic/
│   └── versions/
├── tests/
├── .env.example
├── Makefile
└── requirements.txt
```

## 🔄 Как работает синхронизация

### Порядок загрузки (граф зависимостей)

```
1. Projects     ← нет зависимостей
2. Issues       ← зависит от Projects
3. Worklogs     ← зависит от Issues, Employees
   └── Employees создаются автоматически при обнаружении
```

### Инкрементальная синхронизация

При повторных запусках загружаются только изменённые данные:

```
JQL: project in (PRJ, ECO) AND updated >= "2024-01-15 10:30"
```

Курсор (timestamp последней синхронизации) хранится в таблице `sync_state`.

### Rate Limiting

- Задержка 100ms между запросами к Jira API
- При 429 ошибке — exponential backoff
- До 100 issues за один запрос

## 🗃️ Модели данных

### Employee (сотрудник)
- `jira_account_id` — ID аккаунта в Jira
- `display_name`, `email`, `avatar_url`
- `role`, `team`, `department` — для аналитики

### Project (проект)
- `jira_project_id`, `key`, `name`
- `project_type` (software, business, etc.)

### Issue (задача)
- `jira_issue_id`, `key`, `summary`
- `issue_type` (Task, Bug, Story, Epic)
- `status`, `priority`
- `parent_id` — для иерархии (Epic → Story → Subtask)
- `category`, `estimated_hours` — для аналитики

### Worklog (трудозатраты) — ключевая fact-таблица
- `jira_worklog_id`
- `started_at`, `hours`, `time_spent_seconds`
- `issue_id`, `employee_id`

## 🛠️ Makefile команды

```bash
make dev      # Установка зависимостей + создание .env
make migrate  # Применить миграции
make run      # Запустить сервер
make test     # Запустить тесты
make clean    # Очистить кэш и временные файлы
```

Frontend:

```bash
cd frontend
npm install
npm run lint
npm run build
npm run dev
npm run e2e
```

Smoke:

```powershell
.\scripts\smoke-local.ps1
.\scripts\e2e-local.ps1
```

## 📋 Roadmap

- [x] **M1** — Технический каркас: FastAPI, SQLite, SQLAlchemy, Alembic
- [x] **M2** — Jira загрузка: авторизация, sync projects/issues/worklogs
- [x] **M3** — Факт-аналитика: категории, мэппинг, отчёты
- [x] **M4** — Планирование: календарь, отпуска, ёмкость, бэклог, сценарии
- [x] **M5** — Экспорты: xlsx/pdf для аналитики, xlsx/pptx для сценариев
- [x] **M6** — Стабилизация frontend, smoke/E2E проверки, удобный onboarding
  - [x] Frontend route-level lazy loading для уменьшения стартового bundle
  - [x] Локальный smoke-runner для backend + frontend
  - [x] Browser E2E для основных SPA-маршрутов без Jira credentials
  - [x] E2E для CRUD-потоков Scope/Capacity/Backlog/Planning на seed-данных
  - [x] E2E для export/download сценариев

## 📄 Лицензия

MIT
