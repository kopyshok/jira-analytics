# Usage Analytics — Design

**Дата:** 2026-05-28
**Статус:** утверждено для реализации
**Назначение:** админ-аналитика использования сервиса — кто заходит, какие разделы востребованы, кто как глубоко работает.

## 1. Цель

Дать админу три среза в одном экране:

- **Кто живой** — список юзеров, последний вход, активность за неделю/месяц.
- **Что востребовано** — рейтинг страниц по визитам и реальному времени работы.
- **Кто чем живёт** — связка юзер↔раздел (Петров живёт в Resource Planning, Иванов — только Dashboard).

## 2. Скоуп

**Включено:**
- Фиксация заходов на страницы, реального времени работы на каждой странице, ключевых действий.
- Хранение raw-событий 90 дней, дневных агрегатов — навсегда.
- Админ-UI на `/settings` → вкладка «Использование».

**Не включено (out of scope):**
- Каждый клик и каждый API-запрос (только заранее перечисленные действия).
- Логирование payload-полей (значения фильтров, имена сценариев) — только тип события и опц. ID сущности.
- A/B-тесты, funnels, retention cohorts.
- Экспорт сырых логов внешним сервисам.

## 3. Что собираем

### 3.1 Типы событий

**Page view** — заход на маршрут SPA. Поля: `user_id`, `path` (нормализованный — без query, ID заменены на `:id`), `at`.

**Heartbeat** — каждые 30 секунд, пока вкладка реально видима (Page Visibility API: `visibilityState === 'visible'`). Поля: `user_id`, `path`, `at`. Свёрнутая вкладка, переключение на другую вкладку браузера, lock экрана — heartbeat не шлёт. Точное время работы = `count(heartbeats) × 30 секунд`.

**Action** — целевое действие. Поля: `user_id`, `action_type` (enum-string), `entity_id` (опц., UUID связанной сущности), `path` (откуда сделал), `at`.

### 3.2 Список actions (стартовый)

| action_type | где трекается |
|---|---|
| `login` | успешный логин |
| `logout` | явный логаут |
| `sync_started` | кнопки sync на `/sync` |
| `sync_cancelled` | прерывание sync |
| `scenario_created` | создание сценария |
| `scenario_approved` | утверждение сценария |
| `scenario_xlsx_exported` | xlsx-экспорт «Бухгалтерия» |
| `ai_summary_requested` | AI-саммари проекта |
| `ai_summary_refreshed` | ручное обновление AI-саммари |
| `feedback_submitted` | отправка bug/idea |
| `resource_plan_edited` | drag/PATCH в Resource Planning |
| `theme_merged` | merge тем в тематическом отчёте |
| `category_changed` | смена категории issue |

Список — стартовый минимум. Расширяется в коде вызовом `trackAction(type, entityId?)`; на бэке `action_type` хранится как свободная строка, без enum-валидации.

### 3.3 Нормализация пути

Маршруты вида `/projects/PROJ-123` → `/projects/:key`, `/scenarios/abc-uuid/edit` → `/scenarios/:id/edit`. Нормализация на фронте перед отправкой, чтобы агрегация работала.

Whitelist маршрутов SPA (`React Router` route table) задаёт нормализацию. Неизвестные пути отбрасываются (защита от мусора).

## 4. Архитектура

```
SPA (browser)
  ├─ usePageView()   → на каждом route change → POST бьём в буфер
  ├─ useHeartbeat()  → setInterval 30s + visibilitychange listener
  └─ trackAction()   → вызывается из onClick/onSuccess
                ↓
          UsageSender (буфер)
                ↓  раз в 30 сек или при beforeunload (sendBeacon)
                ↓
POST /api/v1/usage/events  (bulk, до 100 за раз)
                ↓
   FastAPI endpoint (validate, insert)
                ↓
   usage_events table (raw, 90 дней)
                ↓
  APScheduler cron daily 03:00
                ↓
  Aggregator: свернуть вчерашний день
                ↓
  usage_daily table (forever)
                ↓
  DELETE FROM usage_events WHERE at < now() - 90d
                ↓
GET /api/v1/admin/usage/* (admin only)
                ↓
SPA /settings → tab «Использование»
```

## 5. Модель данных

### 5.1 `usage_events` (raw, 90 дней)

```
id              String(36) PK
user_id         String(36) FK users.id
event_type      Enum('page_view', 'heartbeat', 'action')
path            String(255)    -- нормализованный
action_type     String(64) NULL
entity_id       String(36) NULL
at              DateTime indexed
created_at      DateTime (TimestampMixin)
```

Индексы:
- `(user_id, at)` — выборки по юзеру
- `(at, event_type)` — агрегатор
- `(path, at)` — выборки по разделу

### 5.2 `usage_daily` (агрегат, навсегда)

```
id              String(36) PK
date            Date           -- день агрегата (UTC)
user_id         String(36) FK users.id
path            String(255)    -- нормализованный
views           Integer        -- count(page_view)
seconds         Integer        -- count(heartbeat) × 30
actions_json    Text           -- {"sync_started": 3, "scenario_created": 1}
```

Уникальный индекс `(date, user_id, path)`.

Индексы:
- `(date, user_id)` — отчёт по юзеру
- `(date, path)` — отчёт по разделу

### 5.3 Что не дублируем

- `last_login_at` юзера = `MAX(at)` из `usage_events`/`usage_daily` где `action_type='login'`. Не отдельная колонка в `users`.

## 6. Backend

### 6.1 Endpoints

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| `POST` | `/api/v1/usage/events` | любой залогиненный | bulk-вставка batch событий от клиента |
| `GET` | `/api/v1/admin/usage/overview` | admin | KPI: DAU, WAU, MAU, total seconds сегодня/неделю |
| `GET` | `/api/v1/admin/usage/users` | admin | таблица юзеров: last_seen, days_active_30d, total_seconds_30d, top_path |
| `GET` | `/api/v1/admin/usage/pages` | admin | таблица страниц: unique_users_30d, views_30d, seconds_30d |
| `GET` | `/api/v1/admin/usage/matrix?days=30` | admin | юзер × страница → секунды (heatmap) |
| `GET` | `/api/v1/admin/usage/timeline?days=30&group_by=day` | admin | временной ряд: views, seconds, actions per day |
| `GET` | `/api/v1/admin/usage/actions?days=30` | admin | счётчики action_type × user |

Все admin-эндпоинты — только `UserRole.admin` (не super_manager, не manager).

### 6.2 Batch insert

`POST /usage/events` принимает `{events: [{event_type, path, action_type?, entity_id?, at}]}` до 100 за запрос. Сервер берёт `user_id` из cookie auth (никакого `user_id` в payload — клиент не должен подделывать).

Сервер валидирует:
- `path` — match с whitelist (если не match, событие тихо игнорируется без 4xx, чтобы не сломать клиента старым кодом)
- `at` — не дальше 1 часа в прошлом/будущем (антимусор)
- `event_type` ∈ {page_view, heartbeat, action}
- если `event_type=action` — `action_type` обязателен

Ответ — `{accepted: N, rejected: M}`. Не 4xx на отдельные плохие события.

### 6.3 Агрегатор (cron)

APScheduler job `aggregate_usage_daily`:
- запуск daily 03:00 локального времени сервера
- для вчерашнего дня группировать `usage_events` по `(user_id, path)`, считать views/seconds/actions, UPSERT в `usage_daily` через select-then-update/insert на ORM-уровне (SQLite-совместимо)
- после успешного UPSERT — удалить записи `usage_events` где `at < datetime.utcnow() - timedelta(days=90)` через ORM bulk delete

Идемпотентность: повторный запуск за тот же день перезаписывает запись (find-by-(date,user_id,path) → update; else insert).

Ручной запуск — кнопка «Пересчитать агрегаты» на admin UI (только для отладки, по умолчанию скрыта).

### 6.4 Сервисный слой

`app/services/usage_service.py`:
- `record_events(user_id, events)` — bulk insert с валидацией
- `aggregate_day(date)` — свернуть raw в daily для указанной даты
- `cleanup_old_events(retention_days=90)` — DELETE
- `query_overview()`, `query_users()`, `query_pages()`, `query_matrix()`, `query_timeline()`, `query_actions()` — отчётные запросы

Используют чистый ORM, никакого raw SQL.

## 7. Frontend

### 7.1 UsageSender

`frontend/src/lib/usage/sender.ts`:
- буфер в памяти, max 100 событий
- flush раз в 30 сек или при beforeunload через `navigator.sendBeacon` (не теряем хвост)
- retry с экспоненциальным backoff при сетевой ошибке (3 попытки)
- никаких блокирующих ожиданий — отправка fire-and-forget

### 7.2 Hooks

`usePageView()` — в корневом `App.tsx`, слушает `useLocation()` от React Router. На каждый change → нормализует path → пушит в sender.

`useHeartbeat()` — `setInterval(30000)` + `document.addEventListener('visibilitychange', ...)`. Когда `visibilityState === 'visible'` — таймер активен, иначе пауза.

### 7.3 trackAction

`frontend/src/lib/usage/track.ts`:
```ts
export function trackAction(type: string, entityId?: string): void
```

Вызывается из обработчиков. Точки внедрения (минимум) — см. п. 3.2.

### 7.4 Admin UI

`frontend/src/pages/SettingsPage.tsx` — новая вкладка «Использование» (видна только если `currentUser.role === 'admin'`).

Структура вкладки:

**Верх — KPI-плитки (4):**
- DAU (уник. юзеров сегодня)
- WAU (за 7 дней)
- MAU (за 30 дней)
- Σ часов за 30 дней (sum seconds / 3600)

**Селектор периода:** 7 / 30 / 90 дней (по умолчанию 30).

**Срезы (табы внутри вкладки):**
1. **Пользователи** — таблица: ФИО, роль, last_seen (относительное «X дней назад»), активных дней за период, часов за период, самый частый раздел.
2. **Разделы** — таблица: путь (с человекочитаемым названием — маппинг `/resource-planning` → «Планирование ресурсов»), уник. юзеров за период, заходов, часов.
3. **Матрица юзер × раздел** — heatmap: строки юзеры, колонки разделы, ячейка — часы (цветовая шкала: 0 → светло, max → насыщенно). Топ-10 юзеров и топ-10 разделов отбираются по суммарным часам за период.
4. **Динамика** — линейный график за период: views/day, активных юзеров/day.
5. **Действия** — таблица: action_type, всего за период, топ-3 юзера.

Использует существующие AntD 6 + Recharts (если уже стоит) или AntD `Chart` компоненты. Без новых зависимостей по возможности.

### 7.5 Что не показываем (privacy)

- entity_id'ы не показываем в UI («открыл сценарий 5 раз», но не «открыл сценарий X»)
- IP, user agent — не собираем вовсе

## 8. Миграции

**Alembic batch migration:**
- create `usage_events`
- create `usage_daily`
- индексы из п. 5

Старт с пустых таблиц, бэкфилл невозможен.

## 9. Тесты

**Backend:**
- `test_usage_endpoints.py`: POST events (валидация, ignore-unknown-path, антимусор по `at`)
- `test_usage_service.py`: aggregate_day идемпотентность, cleanup_old_events
- `test_admin_usage_endpoints.py`: admin-only, корректность KPI/срезов на seed-данных
- `test_aggregator_cron.py`: job регистрируется, ручной запуск работает

**Frontend:**
- unit для `normalizePath()` (route table → `:id`)
- unit для UsageSender (буфер, flush, beforeunload через sendBeacon mock)
- e2e не нужен — нет user-facing flow, только бэкграунд

## 10. Производительность и риски

**Объём:** ~20 юзеров × 8 ч × 120 heartbeat/ч ≈ 19k записей/день. За 90 дней — 1.7M. SQLite потянет с индексами; PostgreSQL — тривиально.

**Bottleneck:** bulk insert. Используем `session.add_all()` + один commit per batch.

**Риски:**
- Если фронт зальёт мусором (баг в нормализации) — серверный whitelist отсеет.
- Если cron упадёт — на следующий день догонит за оба дня (но raw 90 дней ≠ потеря данных).
- При горизонтальном масштабе бэка — каждый процесс пишет независимо, cron должен запускаться только в одном (existing APScheduler уже сконфигурен под single-process; см. документацию sync_schedule).

## 11. Скоуп MVP vs далее

**MVP (этот спек):** всё перечисленное выше.

**На будущее (вне скоупа):**
- Per-team срезы (фильтр по команде юзера)
- Экспорт отчёта в xlsx
- Алерты «юзер X не заходил Y дней»
- Funnels (page A → page B → action)
- Время до первого действия после логина
