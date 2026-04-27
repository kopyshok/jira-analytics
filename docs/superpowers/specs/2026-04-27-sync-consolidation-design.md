# Консолидация синхронизации: единый хаб + pipeline + планировщик + событийная инвалидация

**Дата:** 2026-04-27
**Этап:** 4 из 4 (см. дорожную карту глобальной реструктуризации; этапы 1, 2, 3 — отдельные спеки в будущем)
**Цель:** заменить 18 разрозненных sync-кнопок единым хабом `/sync` с pipeline-оркестратором, добавить расписание автозапуска и событийную инвалидацию кэшей открытых страниц.

## Контекст и проблема

Текущее состояние:
- 18 sync-кнопок на 6 страницах фронта (Dashboard, Backlog, Planning, Capacity, Settings + хаб SyncPage). Дубли вызовов одних и тех же эндпоинтов с разной семантикой.
- 16 sync-эндпоинтов на бэке, нет общей оркестрации; порядок (calendar → projects → issues → worklogs → mapping) не enforced.
- Нет планировщика — `app/main.py.lifespan` пуст, любая синхронизация запускается руками.
- Нет автоматической инвалидации кэшей — открытый Dashboard показывает старые данные пока пользователь не обновит страницу.
- Сценарий «обновить данные по одной команде» сейчас требует 3-4 ручных действия.

PM-боль:
- Долго: каждую страницу синхронизировать отдельно.
- Непонятно: на хабе SyncPage 11 кнопок без чёткого приоритета.
- Каскад: после sync нужно вручную дёргать recalc mapping, recalc capacity, sync scenario backlog.

## Цели

1. Одна главная кнопка делает «правильное» из коробки.
2. Один кейс «обновить команду» = один клик.
3. Открытые страницы автоматически обновляются после завершения стадии sync.
4. Расписание автозапуска без вмешательства пользователя.
5. История запусков с таймингами и ошибками.

## Не-цели (вне scope этого спека)

- Мульти-тенант / публикация сервиса (этап 2).
- Реактивность ручных правок между разделами «Бэклог ↔ Сценарии ↔ Capacity» (этап 3) — фундамент кладётся (event bus), но full coverage отдельным спеком.
- Полное удаление deprecated `/sync/*` эндпоинтов — через 1 спринт после релиза.
- Background-воркер вне процесса FastAPI (Celery/RQ) — единственный процесс через APScheduler, single-user MVP это покрывает.

## Архитектура

```
┌──────────────┐  POST /sync/pipeline       ┌──────────────────────┐
│  /sync UI    │ ─────────────────────────▶ │ PipelineOrchestrator │
│  (хаб)       │                            │  (новый сервис)      │
└──────────────┘                            └──────────────────────┘
       │                                              │
       │ GET /events/stream (SSE, глобальный)         │ runs stages
       │◀──────── EventBroadcaster ─────────────┐     │
       │           {stage, invalidates: [...]}  │     │
       ▼                                        │     ▼
  React QueryClient                       ┌─────┴───────────────────┐
  invalidateQueries(...)                  │ существующие сервисы:    │
                                          │ Sync/Mapping/Capacity/   │
                                          │ ProductionCalendar/      │
                                          │ EmployeeTeam/Backlog     │
                                          └──────────────────────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │  sync_run    │
                                              │  (history)   │
                                              └──────────────┘
                ▲                                     ▲
                │ APScheduler triggers                │
       ┌────────┴────────┐                            │
       │ SchedulerService │ ──── reads sync_schedule ─┘
       │ (lifespan boot) │
       └─────────────────┘
```

Новые компоненты:

| Компонент | Файл | Ответственность |
|---|---|---|
| PipelineOrchestrator | `app/services/sync_pipeline.py` | Запуск стадий в правильном порядке, обработка ошибок, advisory lock, запись sync_run, публикация событий |
| EventBroadcaster | `app/services/event_bus.py` | In-memory pub/sub + SSE-эндпоинт, dropping для медленных подписчиков, ping каждые 30с |
| SchedulerService | `app/services/scheduler.py` | APScheduler в lifespan, читает sync_schedule, дёргает PipelineOrchestrator |
| SyncRunRepository | `app/repositories/sync_run.py` | CRUD + последние 20 + раскрытие stages_json |
| SyncScheduleRepository | `app/repositories/sync_schedule.py` | CRUD + cron validation |

## Pipeline контракт

**Endpoint:** `POST /sync/pipeline`

```json
{
  "mode": "quick" | "normal" | "full" | "team",
  "team": "string (только для team)",
  "since": "YYYY-MM-DD (опц., default = max(sync_run.finished_at where status in ('ok','partial')))"
}
```

**Стадии по режимам:**

| Стадия | quick | normal | full | team |
|---|---|---|---|---|
| 1. calendar (если нет данных за текущий год) | – | ✓ | ✓ force | – |
| 2. projects | – | ✓ | ✓ | – |
| 3. issues incremental | – | ✓ | – | – |
| 4. issues full reread | – | – | ✓ | – |
| 5. worklogs delta (since) | ✓ | ✓ | – | ✓ Bucket A+B по team |
| 6. worklogs full reread (since) | – | – | ✓ | – |
| 7. issues refresh by collected keys | – | – | – | ✓ (keys собираются в ст.5: множество уникальных `worklog.issue_key` за прогон) |
| 8. mapping recalc | – | ✓ all | ✓ all | ✓ только затронутые issue_ids |

**Поведение по ошибкам (гибрид):**

| Стадия | Критичность | При падении |
|---|---|---|
| calendar | **non-critical** | warn в stages_json, продолжаем |
| projects | **critical** | stop, status=failed |
| issues | **critical** | stop, status=failed |
| worklogs | **critical** | stop, status=failed |
| mapping | **non-critical** | warn, status=partial, продолжаем |

**Cancellation:** через `request.is_disconnected()` — наследуется текущий паттерн (HTTP 499 → status=cancelled, advisory lock освобождается).

**Concurrency:** в момент старта pipeline берётся advisory lock в БД через `AppSetting.sync_lock = run_id`. Параллельный POST → `409 Conflict` с `{"running_run_id": "..."}`. Scheduler видит lock → пропускает свой тик с пометкой `skipped: previous_running` (создаёт sync_run со status=skipped).

**Ответ:** SSE-stream:
```
event: stage_start    data: {"stage":"projects","run_id":"...","eta_sec":30}
event: stage_progress data: {"stage":"issues","scanned":1247,"total":5000}
event: stage_done     data: {"stage":"projects","duration_ms":1820,"invalidates":["projects","issues"]}
event: stage_failed   data: {"stage":"mapping","error":"...","critical":false}
event: pipeline_done  data: {"run_id":"...","status":"ok|partial|failed","duration_ms":275000}
```

**Дополнительный endpoint:**

`POST /sync/team/refresh` `{team: "..."}` — sugar для `POST /sync/pipeline {mode:"team", team:"..."}`. Альтернативно фронт зовёт основной endpoint напрямую с mode=team.

## EventBroadcaster + SSE

**Endpoint:** `GET /events/stream` — SSE, один listener на сессию фронта.

Pipeline после каждой стадии вызывает `event_bus.publish({type:"stage_done", stage, invalidates, run_id})`.

Дополнительные типы событий (фундамент для этапа 3):
```
{"type":"entity_changed", "entity":"backlog_item", "id":"...", "invalidates":[...]}
{"type":"sync_started", "run_id":"...", "mode":"...", "trigger":"manual|scheduled"}
{"type":"sync_finished", "run_id":"...", "status":"..."}
```

**Карта invalidates (стадия → query keys фронта):**

| stage | query keys |
|---|---|
| calendar | `["production-calendar", "capacity"]` |
| projects | `["projects"]` |
| issues | `["issues", "tree", "backlog", "planning"]` |
| worklogs | `["analytics", "capacity", "employees"]` |
| mapping | `["analytics", "categories"]` |

**Реализация фронта:** `App.tsx` подключает `useEventStream()` хук на старте, EventSource подписывается на `/events/stream`, callback дёргает `queryClient.invalidateQueries({queryKey: [...]})` для каждого ключа из invalidates.

**Устойчивость:** ping каждые 30с от бэка, авто-reconnect фронта при разрыве (нативное поведение EventSource).

**Slow consumer:** EventBus держит `asyncio.Queue(maxsize=100)` per subscriber; при переполнении старые события дропаются с warning в лог.

## Scheduler

**Сервис:** `app/services/scheduler.py` использует APScheduler (`AsyncIOScheduler`).

Жизненный цикл:
- Старт в `lifespan()` `app/main.py` после connection-pool init.
- Остановка при shutdown (graceful, ждёт текущий job до 30с).

**Конфиг — таблица `sync_schedule`:**
```
id (UUID)
name (str, unique)
cron_expr (str, валидируется croniter)
mode (enum: quick|normal|full|team)
team (str, nullable, только для mode=team)
enabled (bool)
last_run_id (FK sync_run, nullable)
next_run_at (datetime, для UI)
created_at, updated_at
```

**Дефолт-сиды (миграция 029):**

| name | cron | mode |
|---|---|---|
| daily_incremental | `0 6 * * *` | normal |
| worklogs_workhours | `0 8-20/2 * * 1-5` | quick |
| weekly_full | `0 3 * * 0` | full |

Все `enabled=true`.

**Поведение тика:**
1. Проверить advisory lock в `AppSetting.sync_lock`.
2. Lock занят → создать `sync_run(status="skipped", trigger="scheduled", error_text="previous_running")`.
3. Lock свободен → внутренний вызов pipeline через сервисный слой (не HTTP), записать `last_run_id` в schedule.

**API планировщика:**
- `GET /sync/schedule` — список.
- `PATCH /sync/schedule/{id}` — обновление cron / enabled / mode.
- `POST /sync/schedule/{id}/run-now` — внеплановый запуск.
- `POST /sync/schedule` / `DELETE /sync/schedule/{id}` — добавление / удаление пользовательских правил.

## UI хаба `/sync`

```
┌─ /sync ─────────────────────────────────────────────────────────┐
│  [ 🔄 Синхронизировать ▾ ]   [ 👥 Команда: [Select▾] ↻ ]        │
│   ├─ Быстро (worklogs delta)                                    │
│   ├─ Обычно ★ (incremental + worklogs + mapping)                │
│   └─ Полностью (full reread)                                    │
│                                                                 │
│  Идёт: Обычная синхронизация · этап 3/5 · worklogs              │
│  ████████████░░░░ 62%   issues_scanned: 1247   [ Прервать ]     │
├─────────────────────────────────────────────────────────────────┤
│ Расписание                                          [ Настроить]│
│  ✓ Ежедневно 06:00 — incremental                                │
│  ✓ Каждые 2ч 8-20 будни — worklogs delta                        │
│  ✓ Воскресенье 03:00 — full pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│ История                                                         │
│  2026-04-27 06:00  manual    ✓  4m 32s   Обычно                 │
│  2026-04-27 04:00  scheduled ✓  3m 18s   Worklogs               │
│  2026-04-26 22:14  manual    ⚠  2m 01s   Обычно (mapping skip)  │
│  ... (последние 20)                                             │
├─────────────────────────────────────────────────────────────────┤
│ Дополнительно                                          ▸ развернуть│
│  · Полная перезагрузка ворклогов с даты [date] [ Запустить ]    │
│  · Синхронизировать производственный календарь [year] [ Загрузить ]│
│  · Авто-определить команды сотрудников                          │
│  · Тест подключения к Jira                                      │
│  · Пересчитать маппинг категорий                                │
└─────────────────────────────────────────────────────────────────┘
```

Секции:
1. **Главные кнопки + прогресс** — всегда видно. Прогресс блок показывается только когда pipeline идёт.
2. **Расписание** — список из `sync_schedule`, inline toggle enabled, кнопка «Настроить» открывает модалку с полным редактором.
3. **История** — таблица последних 20 sync_run, клик → раскрытие stages_json (durations + warnings/errors per stage).
4. **Дополнительно** — свёрнуто по умолчанию; редкие операции (full reload, calendar, auto-detect, test connection, recalc mapping).

## Изменения бэкенда

**Добавить файлы:**
- `app/services/sync_pipeline.py` — PipelineOrchestrator
- `app/services/event_bus.py` — EventBroadcaster
- `app/services/scheduler.py` — SchedulerService (APScheduler wrapper)
- `app/api/endpoints/events.py` — `GET /events/stream`
- `app/repositories/sync_run.py`, `app/repositories/sync_schedule.py`
- `app/models/sync_run.py`, `app/models/sync_schedule.py`
- `alembic/versions/029_sync_pipeline.py` — таблицы + сиды

**Дополнить файлы:**
- `app/api/endpoints/sync.py` — новые маршруты:
  - `POST /sync/pipeline`
  - `POST /sync/team/refresh`
  - `GET /sync/runs` (пагинация, default 20)
  - `GET /sync/runs/{id}` (со stages_json)
  - `GET /sync/schedule`, `PATCH /sync/schedule/{id}`, `POST /sync/schedule`, `DELETE /sync/schedule/{id}`, `POST /sync/schedule/{id}/run-now`
- `app/main.py` — старт SchedulerService в lifespan
- `app/api/deps.py` — provider для EventBroadcaster (синглтон через `Depends`)
- `requirements.txt` / `pyproject.toml` — `apscheduler>=3.10`, `croniter>=2.0`

**Существующие сервисы (вызываются изнутри pipeline, не меняем):**
- `SyncService.sync_projects/sync_issues/sync_worklogs/refresh_issues_by_keys/update_worklogs_since/reload_worklogs_since`
- `MappingService.recalculate_all` (плюс новый метод `recalculate_for_issues(issue_ids)` — для team mode)
- `ProductionCalendarService.sync_year`
- `BacklogService.sync_from_issue` (inline в issue stage, как сейчас)

**Депрекейт (живые, но помеченные `deprecated=True`, фронт не зовёт):**
- `POST /sync/full`, `POST /sync/issues`, `POST /sync/teams`, `POST /sync/worklogs`, `POST /sync/comments`, `POST /sync/worklogs/reload`, `POST /sync/worklogs/update/stream`, `POST /sync/worklogs/reload/stream`
- `POST /employees/recalc-active` — теперь авто-вызывается после worklogs stage (опционально, по флагу в pipeline; включено по умолчанию)

Удаление deprecated маршрутов — отдельный PR через 1 спринт после релиза.

## Изменения фронта

**Удалить вызовы `/sync/*` со страниц:**
- `frontend/src/pages/DashboardPage.tsx` — кнопка «Синхронизация» (#3 в аудите) → удалить
- `frontend/src/pages/BacklogPage.tsx` — «Обновить с Jira» (#4) → заменить на локальный `queryClient.invalidateQueries({queryKey:['backlog']})`
- `frontend/src/pages/PlanningPage.tsx` — «Синк с бэклогом» (#5) → удалить, авто-trigger через event `entity_changed:backlog_item` после issue stage
- `frontend/src/pages/CapacityPage.tsx` — «Пересчитать состав» (#7), «Пересчитать ёмкость» (#8) → удалить, авто-обновление через event listener

**Перенести страницы:**
- 1a/1b (`SyncPage` Tab1 — get tasks tree + set category) → новая страница `frontend/src/pages/CategoriesEditorPage.tsx` под маршрутом `/categories`
- В меню добавить пункт «Категории» рядом с «Бэклог»

**Новые файлы:**
- `frontend/src/pages/SyncHubPage.tsx` (заменяет SyncPage Tab2)
- `frontend/src/components/sync/PipelineRunner.tsx` — главные кнопки + прогресс
- `frontend/src/components/sync/SyncSchedule.tsx`
- `frontend/src/components/sync/SyncHistory.tsx`
- `frontend/src/components/sync/SyncAdvanced.tsx`
- `frontend/src/hooks/useSyncPipeline.ts` — единый хук с SSE-чтением
- `frontend/src/hooks/useEventStream.ts` — глобальный SSE listener в App.tsx
- `frontend/src/api/events.ts` — типы событий + карта invalidates
- `frontend/src/api/syncPipeline.ts`, `frontend/src/api/syncSchedule.ts`, `frontend/src/api/syncRuns.ts`

**Модифицировать:**
- `frontend/src/App.tsx` — подключить `useEventStream()` на mount
- `frontend/src/router.tsx` (или эквивалент) — добавить `/sync` (новый), `/categories`, оставить редирект `/sync-old → /sync` (одна неделя)

**Оставить как есть:**
- `frontend/src/components/TaskSectionsTab.tsx` (#10, #11) — это scope-конфиг, не sync
- `frontend/src/components/ConnectionCard.tsx` (#9) — переехать в раздел «Дополнительно» хаба, либо остаться в `/settings`

## Модели БД (миграция 029)

```python
class SyncRun(Base):
    __tablename__ = "sync_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    status: Mapped[str]  # running | ok | partial | failed | cancelled | skipped
    trigger: Mapped[str]  # manual | scheduled
    mode: Mapped[str]  # quick | normal | full | team
    team: Mapped[str | None]
    stages_json: Mapped[dict] = mapped_column(JSON)  # [{stage, started, finished, status, counts, error}]
    error_text: Mapped[str | None]
    schedule_id: Mapped[str | None] = mapped_column(ForeignKey("sync_schedule.id"))
    created_at, updated_at

class SyncSchedule(Base):
    __tablename__ = "sync_schedule"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    cron_expr: Mapped[str]
    mode: Mapped[str]
    team: Mapped[str | None]
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_run.id"))
    next_run_at: Mapped[datetime | None]
    created_at, updated_at
```

Сиды в миграции — три дефолтных правила (см. таблицу выше).

`AppSetting.sync_lock` — новый ключ (string `run_id` или null).

## Тестирование

**Unit:**
- `tests/services/test_sync_pipeline.py` — порядок стадий по каждому mode, поведение при failure (critical/non-critical), cancellation, advisory lock
- `tests/services/test_event_bus.py` — pub/sub, multiple subscribers, slow consumer drop, ping
- `tests/services/test_scheduler.py` — skip if running, cron parsing, lifecycle

**Integration:**
- `tests/api/test_sync_pipeline.py` — `POST /sync/pipeline` end-to-end на seeded `data/e2e.db`, проверка sync_run + invalidate events в SSE
- `tests/api/test_sync_schedule.py` — CRUD расписания
- `tests/api/test_events_stream.py` — SSE-чтение, ping, авто-disconnect

**E2E (Playwright):**
- `tests/e2e/sync_hub.spec.ts` — главная кнопка → прогресс → история; редактирование расписания; раскрытие stages_json в истории

**Регрессия:**
- Старые `tests/api/test_sync.py` — оставить (deprecated эндпоинты ещё живы)
- Удалить тесты на снятые кнопки фронта (DashboardPage sync button и т.д.)

## Rollout

1. **PR 1 (бэк-фундамент):** миграция 029, модели, репозитории, EventBroadcaster, эндпоинт `/events/stream`. Не ломает ничего.
2. **PR 2 (pipeline):** PipelineOrchestrator, эндпоинты `/sync/pipeline`, `/sync/team/refresh`, `/sync/runs`. Старые эндпоинты живы.
3. **PR 3 (scheduler):** SchedulerService в lifespan, `/sync/schedule` API, дефолт-сиды. Расписание включено сразу — PM получит автозапуск с первого деплоя.
4. **PR 4 (фронт-хаб):** `SyncHubPage` под маршрутом `/sync` (старая `SyncPage` переезжает на `/sync-old`), глобальный `useEventStream()` в App.tsx, страница `/categories`.
5. **PR 5 (чистка):** удаление дубликатов кнопок на Dashboard/Backlog/Planning/Capacity, замена на event-driven обновления.
6. **PR 6 (через 1 неделю):** удаление редиректа `/sync-old`, удаление deprecated эндпоинтов.

**Ломающие:** для конечного пользователя ничего — старый маршрут `/sync` редиректит на новый хаб. Для разработчика: после PR 6 deprecated эндпоинты исчезнут, нужно обновить любые внешние интеграции (если такие есть).

## Метрики успеха

- Главный сценарий «обновить данные» = 1 клик (было 5-7).
- «Обновить команду» = 1 клик (было 3-4).
- После завершения pipeline открытые страницы обновляются автоматически за <2с.
- Расписание работает 7 дней без вмешательства, автоматический ежедневный sync в 06:00 завершён к 06:15.
- В истории видно тайминги per-stage и причины частичных провалов.

## Решения по UX (зафиксированы)

- **Создание новых расписаний пользователем:** API готов (`POST /sync/schedule` / `DELETE`), но UI первого релиза показывает только редактор существующих трёх дефолтных правил. Кнопка «Добавить правило» — на потом.
- **Test connection (#9):** остаётся в `/settings/connection`, в «Дополнительно» хаба отображается ярлык-ссылка туда.
- **Расписание enabled при первом деплое:** дефолтные сиды приходят с `enabled=true`. PM получает автозапуск с первого старта без явного opt-in. Если до миграции БД уже жила — миграция вставляет сиды только если таблица пуста.

## Риски

- **Single-process APScheduler** — при многократных рестартах uvicorn можно пропустить тик. Приемлемо для single-user MVP. При переходе на мульти-процесс (этап 2) заменить на внешний планировщик.
- **SSE через корпоративный proxy** — некоторые прокси буферизуют event-stream и ломают real-time. Mitigation: ping каждые 30с + `X-Accel-Buffering: no` header. Если останется проблема — фолбэк на polling `GET /sync/runs/latest`.
- **Advisory lock через AppSetting** — простое решение, но при крэше процесса с занятым lock'ом он не освобождается. Mitigation: проверка `started_at` в lock — если старше 1 часа, считается stale и игнорируется.
