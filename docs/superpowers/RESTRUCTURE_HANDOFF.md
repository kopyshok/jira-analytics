# Глобальная реструктуризация — хэндофф для новой сессии

## Контекст

Начата глобальная реструктуризация по 4 направлениям. Обсуждалось 2026-04-27.

---

## Дорожная карта (порядок выполнения)

| # | Тема | Статус | Артефакты |
|---|---|---|---|
| **4** | Единый хаб синхронизации + pipeline + scheduler + событийная инвалидация | **✅ Спек + план готовы, задачи не выполнены** | spec: `2026-04-27-sync-consolidation-design.md`, plan: `2026-04-27-sync-consolidation.md` |
| **1** | Кросс-секционная реактивность (ручные правки → авто-update везде) | ⬜ Не начато. Фундамент (EventBroadcaster) кладётся в п.4 | — |
| **3** | Пересмотр зависимостей показателей (смена исполнителя в Бэклоге → обновление Сценариев и наоборот) | ⬜ Не начато. Завязан на EventBroadcaster из п.4 | — |
| **2** | Публикация + мульти-тенант (другие пользователи со своими командами и настройками) | ⬜ Не начато. Делать последним на стабильной single-user базе | — |

---

## Что делать в новой сессии

### Шаг 1 — Выполнить план п.4 (sync consolidation)

**Файл плана:** [`docs/superpowers/plans/2026-04-27-sync-consolidation.md`](plans/2026-04-27-sync-consolidation.md)

Использовать скилл `superpowers:subagent-driven-development` (рекомендуется) или `superpowers:executing-plans`.

40 задач в 5 фазах:
- Phase 1 (T1–T11): модели SyncRun/SyncSchedule, миграция 035, репозитории, EventBroadcaster, SSE endpoint `/events/stream`, SyncLock
- Phase 2 (T12–T18): MappingService.recalculate_for_issues, PipelineOrchestrator, стадии pipeline, build_pipeline, POST /sync/pipeline, cancellation
- Phase 3 (T19–T22): SchedulerService (APScheduler), trigger runner, lifespan, /sync/schedule CRUD
- Phase 4 (T23–T33): фронт-API клиенты, useEventStream, useSyncPipeline, компоненты (PipelineRunner/Schedule/History/Advanced), SyncHubPage, маршруты, /categories
- Phase 5 (T34–T40): удаление дублей кнопок, E2E тест, smoke + push

Phase 6 — отдельный PR через 1 неделю после релиза (удаление deprecated эндпоинтов + `/sync-old`).

### Шаг 2 — Брейнсторм и план п.1 + п.3 (реактивность)

Запустить `superpowers:brainstorming` по теме:
> «Кросс-секционная реактивность: изменение данных в одном разделе (Бэклог, Сценарии, Задачи Jira) должно автоматически обновлять все связанные разделы. Фундамент — EventBroadcaster из п.4, уже задеплоен. Что нужно добавить для полной связности?»

Контекст для брейнсторма:
- EventBroadcaster (pub/sub + SSE) уже работает после п.4
- Бэклог → Сценарии: при изменении assignee/статуса в Бэклоге сценарии должны пересчитать allocation
- Сценарии → Бэклог: изменение `included` в Сценарии отражается в Бэклоге
- После синхронизации с Jira (issue sync) — все разделы автоматически обновляются (уже частично через EventBroadcaster stage events)
- Главный вопрос: нужен ли серверный push (backend публикует entity_changed) или достаточно клиентской инвалидации после pipeline?

### Шаг 3 — Брейнсторм и план п.2 (мульти-тенант + публикация)

Отдельная большая задача. Затронет:
- Auth (OAuth / email+password)
- Изоляция данных (tenant_id на каждой таблице)
- Jira creds per-user (сейчас global AppSetting)
- PostgreSQL вместо SQLite
- Деплой (Docker, домен, HTTPS, reverse proxy)
- Возможно: billing, лимиты, GDPR

---

## Ключевые файлы

| Артефакт | Путь |
|---|---|
| Спек синхронизации | `docs/superpowers/specs/2026-04-27-sync-consolidation-design.md` |
| План синхронизации | `docs/superpowers/plans/2026-04-27-sync-consolidation.md` |
| Этот хэндофф | `docs/superpowers/RESTRUCTURE_HANDOFF.md` |

---

## Критичные особенности проекта для исполнителя плана

| Особенность | Действие |
|---|---|
| Windows + uvicorn `--reload` не подхватывает изменения бэка | После каждой правки бэка: kill PID :8000 + перезапуск |
| AntD 6: нотификации используют `title`, не `message` | `message` deprecated в AntD 6.3 |
| Имена полей моделей: `Issue.issue_type`, `Category.label/is_system` | Не `name/is_builtin` |
| Последняя миграция: `034_scenario_allocation_sort_order.py` | Новая миграция = `035_sync_pipeline.py` |
| pytest: запускать через `py -3.10 -m pytest` (не `pytest`) | Дефолтный Python 3.14 без зависимостей |
| Commit + push в origin/main после каждой завершённой фазы | Без лишних вопросов |
| Brainstorm-сессии: Opus формулирует, Sonnet через Agent рисует HTML-mockup | |

---

## Текущее состояние репозитория (2026-04-27)

- Ветка: `main`
- Последний коммит: `aaedd75` — `docs(plan): sync consolidation implementation plan + spec migration fix`
- БД: SQLite `data/dev.db`, последняя миграция `034_scenario_allocation_sort_order`
- CI: pre-existing red на main (SyncPage lint, hierarchy_rules test DB errors, test_sync_service mock drift, 3 e2e flakies) — не трогать, не наша работа
