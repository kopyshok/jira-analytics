# JiraAnalysis

Многопользовательский веб-сервис анализа данных Jira Cloud и квартального планирования ресурсов команды.

## Что это

Тянет issues + worklogs из Jira Cloud, считает фактическую загрузку сотрудников против производственного календаря, ведёт реестр инициатив и сценарии квартального планирования. Каждый пользователь видит свои команды; синхронизация общая, изменения push-ятся в UI через SSE.

### Возможности

- **Dashboard** — KPI по проектам (W1), загрузка по 4 ролям (W2), тепловая карта 5×2 (W3).
- **Аналитика** — иерархический master-detail отчёт с drill-down до ворклогов, период в шапке, per-user видимость колонок.
- **Capacity** — план/факт/% по ролям и категориям, отсутствия (Vacation/Absence + reason), копирование правил между месяцами, экспорт в xlsx, тепловая карта, overload >110% красным.
- **Backlog** — реестр инициатив с lifecycle (Активные/В работе/Архив), автосинхронизация в draft-сценарии.
- **Planning** — сценарии (draft/approved) с per-role правилами, обязательные работы, посуточная база ресурса, клиент-сайд пересчёт, xlsx «Бухгалтерия» (4 листа).
- **Projects** — master-detail по проектам, AI-саммари (Gemini 2.0 Flash + cron), оценка заказчика, PDF-печать.
- **Sync** — единый хаб синхронизации (incremental/full, APScheduler, EventBroadcaster), все sync прерываемы.
- **Settings** — креды Jira, кастомные поля, иерархия типов задач, производственный календарь РФ, пользователи.
- **Auth** — email + password JWT, роли (admin/user), управление пользователями.

## Стек

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic, APScheduler, httpx (async) |
| **Frontend** | React 19, TypeScript 6, Vite 8, Ant Design 6 (dark theme), TanStack Query, Recharts |
| **БД** | SQLite (MVP) → PostgreSQL (готово на уровне ORM) |
| **Auth** | JWT (python-jose) + bcrypt |
| **Тесты** | pytest, Playwright (E2E) |
| **CI** | GitHub Actions (pytest + frontend lint/build + E2E) |

## Требования

- Python 3.10 (на Windows — `py -3.10`; pytest не работает под Python 3.14)
- Node.js 20+
- Учётка Jira Cloud + API token: https://id.atlassian.com/manage-profile/security/api-tokens

## Установка

```bash
git clone <repo-url>
cd JiraAnalysis
```

### Backend

```bash
# Виртуальное окружение (рекомендуется)
py -3.10 -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Зависимости
pip install -r requirements.txt
```

Что ставится: FastAPI, SQLAlchemy 2.0, Alembic, httpx, openpyxl/reportlab/python-pptx (экспорты), APScheduler, python-jose, passlib[bcrypt], pytest. Полный список — [requirements.txt](requirements.txt).

### Frontend

```bash
cd frontend
npm install
cd ..
```

## Настройка

### 1. Backend `.env`

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Минимально заполнить:

```ini
# БД
DATABASE_URL=sqlite:///./data/jira_analytics.db

# Jira (можно оставить пустым — задать через UI после первого логина)
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token-here

# Auth — обязательно сменить в проде
JWT_SECRET_KEY=<случайная_строка_32+_символов>
JWT_EXPIRE_HOURS=8

# Первый админ (для scripts/create_admin.py)
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=<надёжный_пароль>

# CORS
CORS_ORIGINS=["http://localhost:5173"]

# Опционально
DEBUG=true
LOG_LEVEL=INFO
JIRA_REQUEST_DELAY=0.1
JIRA_BATCH_SIZE=100
```

> Креды Jira лучше задать через UI: **Настройки → Подключение** (хранятся в БД через AppSetting). `.env` — fallback для CI/dev когда DB пустая.

### 2. Frontend `.env` (опционально)

Дефолт API URL — `http://localhost:8000/api/v1`. Если backend на другом хосте/порту:

```bash
copy frontend\.env.example frontend\.env
```

```ini
VITE_API_BASE_URL=http://your-host:8000/api/v1
```

### 3. Применить миграции

```bash
alembic upgrade head
```

Создаст SQLite БД по пути из `DATABASE_URL` (`data/jira_analytics.db`).

### 4. Создать первого админа

```bash
py -3.10 scripts/create_admin.py
# или с явными аргументами:
py -3.10 scripts/create_admin.py --email admin@company.com --password secret
```

## Запуск

### Dev

Два терминала:

```bash
# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

- UI: http://localhost:5173
- API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs

Логин — `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `.env`.

### Smoke-тест (Windows)

Поднимает оба сервиса разом и прогоняет проверки:

```powershell
.\scripts\smoke-local.ps1
```

Если уже запущены — `-NoStart` переиспользует.

### Production build (frontend)

```bash
cd frontend
npm run build       # → frontend/dist
```

Раздавай `dist/` любым статическим веб-сервером. Backend — `uvicorn` без `--reload` за reverse proxy (nginx/traefik).

## Первый запуск — чек-лист

1. `pip install -r requirements.txt`
2. `cd frontend && npm install`
3. `copy .env.example .env` → задать `JWT_SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`
4. `alembic upgrade head`
5. `py -3.10 scripts/create_admin.py`
6. `uvicorn app.main:app --reload --port 8000`
7. В другом терминале: `cd frontend && npm run dev`
8. http://localhost:5173 → залогиниться
9. **Настройки → Подключение** — URL/email/API token Jira
10. **Настройки → Поля** — ID кастомных полей (team, goals и т.д.)
11. **Настройки → Иерархия** — правила parent→child для типов задач
12. **Sync → Состав работ** — выбрать проекты + команды
13. **Sync → Управление** — «Полная синхронизация»

## Команды

### Makefile (Linux/Mac)

```bash
make install                       # pip install
make run                           # uvicorn :8000
make test                          # pytest
make lint                          # ruff + mypy
make format                        # ruff format
make migrate                       # alembic upgrade head
make migration msg='описание'      # новая миграция
make downgrade                     # alembic downgrade -1
make clean                         # очистить кеши + БД
make reset                         # clean + migrate
```

### Windows (без make)

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
py -3.10 -m pytest tests/ -v
ruff check app/ tests/
mypy app/
ruff format app/ tests/
alembic upgrade head
alembic revision --autogenerate -m "описание"
```

### Frontend

```bash
cd frontend
npm run dev                # dev :5173
npm run build              # production build
npm run lint               # eslint
npm run e2e:install        # установить браузеры Playwright (один раз)
npm run e2e                # E2E тесты
```

## Тесты

### Backend (pytest)

```bash
py -3.10 -m pytest tests/ -v
```

### E2E (Playwright)

Отдельная БД `data/e2e.db`, порты `:8010` (backend) / `:5174` (frontend), без Jira credentials. Перед запуском база пересоздаётся, применяются миграции и seed (`E2E Analyst` employee + `E2E` project).

```powershell
.\scripts\e2e-local.ps1 -InstallBrowsers   # первый раз
.\scripts\e2e-local.ps1                    # повторные запуски
```

Падают при browser `console.error` или `pageerror`.

## Структура

```
app/
├── api/endpoints/      # FastAPI routers (21 router)
├── connectors/         # Jira HTTP client + schemas
├── models/             # SQLAlchemy (29 таблиц, 6 групп)
├── repositories/       # Data access layer
├── services/           # Business logic
├── core/               # security (JWT, bcrypt)
├── config.py           # Settings из .env
├── database.py         # Engine + Session + Base
└── main.py             # FastAPI app

frontend/
├── src/api/            # API client + domain modules
├── src/hooks/          # TanStack Query hooks
├── src/pages/          # 8 страниц (Dashboard, Sync, Analytics, Capacity, Backlog, Planning, Projects, Settings)
├── src/components/     # Shared + layout
└── src/types/          # TypeScript interfaces

alembic/versions/       # миграции БД
tests/                  # pytest
scripts/                # local_smoke, e2e-local, seed_e2e, create_admin
docs/                   # дизайн-доки, спеки, планы
data/                   # SQLite БД (создаётся при первом запуске)
exports/                # xlsx/pdf отчёты
```

Детальная документация по слоям — `CLAUDE.md` каждой папки ([app/models](app/models/CLAUDE.md), [app/api](app/api/CLAUDE.md), [app/services](app/services/CLAUDE.md), [app/connectors](app/connectors/CLAUDE.md), [frontend](frontend/CLAUDE.md), [tests](tests/CLAUDE.md)).

## Архитектура

```
Frontend (React + TanStack Query)
     ↓ REST + SSE
Backend (FastAPI)
     ↓
Connector (httpx) → Jira Cloud API
     ↓
Service Layer (бизнес-логика)
     ↓
Repository (SQLAlchemy 2.0 ORM)
     ↓
SQLite / PostgreSQL
```

**Правила:**
- All SQL через SQLAlchemy ORM — no raw SQL, no vendor-specific SQL
- All DB changes через Alembic миграции (batch mode для SQLite)
- UUID string keys (`String(36)`) везде
- Стандартные timestamps: `created_at`, `updated_at`, `synced_at`
- Async где возможно (httpx, FastAPI)

**Multi-user:** каждый юзер видит свои команды (`selected_teams`), синхронизация общая, изменения push-ятся в UI через SSE (`entity_changed` event).

## Синхронизация

### Граф зависимостей

```
1. Projects     ← нет зависимостей
2. Issues       ← Projects
3. Worklogs     ← Issues + Employees (Employees авто-создаются)
```

### Incremental

```
JQL: project in (PRJ, ECO) AND updated >= "2026-04-15 10:30"
```

Курсор хранится в `sync_state`. Полная синхронизация (60→25 мин) — bulk worklog API.

### Rate limiting

- Задержка между запросами — `JIRA_REQUEST_DELAY` (default 0.1s)
- 429 → exponential backoff
- До `JIRA_BATCH_SIZE` issues за запрос (default 100)

Все sync кнопки прерываемы (AbortController → `request.is_disconnected` → HTTP 499).

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) на push/PR:

1. `pytest` (Python 3.10)
2. Frontend lint + build (Node 20)
3. Playwright E2E

## Jira Cloud (текущий tenant)

```
Cloud ID:  604dc198-0f39-4cc9-bfbf-0a7cfdddd286
Base URL:  https://itgri.atlassian.net
```

## Embedding-модель (тематический отчёт)

Сервис использует локальную модель `intfloat/multilingual-e5-base` (sentence-transformers) для матчинга задач к темам тематического отчёта. Слияние кандидата автоматически расширяет «зону притяжения» темы — система обучается без переписывания LLM-промптов.

### Системные требования

- Python 3.10+, CPU x86_64 (arm64 поддерживается с альтернативным wheel-индексом для torch).
- RAM: ≥ 2 GB на процесс backend (модель занимает ~1.5 GB при загрузке).
- Диск: ~280 MB веса модели + ~500 MB зависимости torch CPU.
- GPU не нужен.

### Установка зависимостей

`requirements.txt` содержит `--extra-index-url https://download.pytorch.org/whl/cpu` — pip берёт CPU-only torch (~200 MB), без CUDA (~2 GB).

```
pip install -r requirements.txt
```

### Загрузка весов

Веса автоматически скачиваются при первом старте backend (~280 MB, нужен outbound к `huggingface.co`). Дальше работают из локального кэша.

Кэш модели — в директории `HF_HOME` (по умолчанию `~/.cache/huggingface`). На VPS лучше зафиксировать:

```
export HF_HOME=/var/cache/huggingface
```

### Offline-деплой (VPS без outbound)

1. Локально:
   ```
   huggingface-cli download intfloat/multilingual-e5-base --local-dir ./models/e5-base
   ```
2. Скопировать папку `models/e5-base` на сервер.
3. На сервере выставить `HF_HOME` в директорию которая содержит подкаталог `hub/models--intfloat--multilingual-e5-base/`, либо положить веса в этот путь напрямую.

### Docker (pre-bake)

В Dockerfile:

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('intfloat/multilingual-e5-base', \
                                   revision='d128750597153bb5987e10b1c3493a34e5a4502a')"
```

Веса вшиваются в слой образа, container на VPS не нуждается в интернете к HF.

### Production lens

- На холодном старте backend модель загружается в RAM ~5-10 с (через FastAPI lifespan). Первый запрос после рестарта чуть дольше обычного.
- Если RAM < 2 GB, замените `MODEL_NAME`/`MODEL_REVISION`/`EMBEDDING_DIM` в [app/services/llm/embedding_service.py](app/services/llm/embedding_service.py) на `intfloat/multilingual-e5-small` (118 MB / 384-dim, RAM ~700 MB). Embeddings придётся пересчитать — модуль автоматически инвалидирует устаревшие записи через `embedding_model_version`.

### Threshold-настройка

Порог матчинга (cosine ≥ X = «попало в тему») регулируется на странице тематического отчёта в разделе «Словарь тем» — слайдер 0.5–0.95. Дефолт 0.78. Значение хранится в `AppSetting` под ключом `theme_match_embedding_threshold`.

## Лицензия

Внутренний продукт.
