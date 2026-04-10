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

# Запуск
make run
```

API: http://localhost:8000  
Документация: http://localhost:8000/docs

## 🔧 Настройка Jira Cloud

### 1. Создание API токена

1. Перейдите на https://id.atlassian.com/manage-profile/security/api-tokens
2. Нажмите "Create API token"
3. Укажите имя (например, "jira-analytics")
4. Скопируйте токен

### 2. Настройка .env

```env
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token-here
```

### 3. Проверка соединения

```bash
curl http://localhost:8000/api/v1/sync/test-connection
```

## 📡 API эндпоинты

### Синхронизация

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/sync/test-connection` | GET | Проверка соединения с Jira |
| `/api/v1/sync/projects` | POST | Синхронизация проектов |
| `/api/v1/sync/issues` | POST | Синхронизация задач |
| `/api/v1/sync/worklogs` | POST | Синхронизация worklogs |
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
│   ├── api/
│   │   ├── endpoints/
│   │   │   └── sync.py       # Sync API endpoints
│   │   └── router.py
│   ├── connectors/
│   │   ├── jira_client.py    # Jira HTTP client
│   │   └── schemas.py        # Pydantic schemas for Jira API
│   ├── models/
│   │   ├── employee.py
│   │   ├── project.py
│   │   ├── issue.py
│   │   ├── worklog.py
│   │   └── sync_state.py
│   ├── repositories/
│   │   └── base.py           # Generic repository
│   ├── services/
│   │   └── sync_service.py   # Sync orchestration
│   ├── config.py
│   ├── database.py
│   └── main.py
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

## 📋 Roadmap

- [x] **M1** — Технический каркас: FastAPI, SQLite, SQLAlchemy, Alembic
- [x] **M2** — Jira загрузка: авторизация, sync projects/issues/worklogs
- [x] **M3** — Факт-аналитика: категории, мэппинг, отчёты
- [x] **M4** — Планирование: календарь, отпуска, ёмкость, бэклог, сценарии
- [ ] **M5** — Экспорты: PDF, Excel, PPTX

## 📄 Лицензия

MIT
