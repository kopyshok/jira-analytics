# Jira Analytics — Инструкции для Claude Code

## Контекст проекта

Локальный сервис для анализа данных из Jira Cloud и квартального планирования.
Миграция на PostgreSQL планируется позже — сейчас MVP на SQLite.

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

## Структура проекта

```
jira-analytics/
├── app/
│   ├── api/endpoints/     # FastAPI роутеры
│   ├── connectors/        # Jira HTTP клиент + Pydantic schemas
│   ├── models/            # SQLAlchemy модели
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

## API Endpoints (текущие)

```
GET  /health                    # Healthcheck
GET  /api/v1/                   # API info
GET  /api/v1/sync/test-connection  # Проверка связи с Jira
POST /api/v1/sync/projects      # Синхронизация проектов
POST /api/v1/sync/issues        # Синхронизация задач
POST /api/v1/sync/worklogs      # Синхронизация worklogs
POST /api/v1/sync/full          # Полная синхронизация
GET  /api/v1/sync/status        # Статус синхронизации
```

## Roadmap

- [x] **M1** — Технический каркас (FastAPI, SQLite, SQLAlchemy, Alembic)
- [x] **M2** — Jira Connector (авторизация, sync issues/worklogs/users)
- [ ] **M3** — Аналитика факта (категории, мэппинг, отчёты)
- [ ] **M4** — Planning (производственный календарь, отпуска, квартальный бэклог)
- [ ] **M5** — Экспорты (PDF, Excel, PPTX)

## Текущая задача: Завершить M2

1. Запустить тесты: `pytest tests/ -v`
2. Убедиться что sync endpoints работают
3. Протестировать синхронизацию с реальной Jira

## Принципы кода

- Все SQL через SQLAlchemy ORM (никакого raw SQL)
- Миграции через Alembic (даже для SQLite)
- Async где возможно (httpx, FastAPI)
- Type hints везде
- Docstrings на русском для бизнес-логики

## Jira Cloud ID

```
Cloud ID: 604dc198-0f39-4cc9-bfbf-0a7cfdddd286
Base URL: https://itgri.atlassian.net
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
```
