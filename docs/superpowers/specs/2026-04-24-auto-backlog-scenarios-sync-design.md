# Автосинхронизация бэклога и черновых сценариев при назначении категории «Инициативы»

**Дата:** 2026-04-24
**Статус:** Design

## Проблема

Сейчас когда PM в SyncPage/CategoryConfigTab назначает задаче категорию «Инициативы» (`initiatives_rfa`), бэкенд уже создаёт `BacklogItem` через `BacklogService.sync_from_issue`. Но PM воспринимает процесс как ручной по двум причинам:

1. **Страница «Бэклог»** не обновляется после сохранения категории — TanStack Query не инвалидирует ключ `['backlog']`, элемент появится только при следующем заходе или по истечении `staleTime`.
2. **Существующие черновые сценарии** не получают allocation-строку на новый элемент бэклога. PM должен зайти в каждый черновик и нажать «Синхронизировать бэклог» вручную (endpoint `POST /planning/scenarios/{id}/sync-backlog`).

Ожидание PM: одно действие — задача попадает и в бэклог, и в «Элементы бэклога» каждого активного черновика.

## Решение

Расширить единую точку синка `BacklogService.sync_from_issue`, чтобы она вместе с `BacklogItem` поддерживала и `ScenarioAllocation` в **черновых** сценариях. Всё в одной транзакции, вызывается из уже существующих мест (`set_issue_category`, `batch_set_category`, `refresh-from-jira`) — новых API не появляется.

На фронте — дополнить инвалидацию кэшей в хуках назначения категории.

## Поведение

| Событие | BacklogItem | Allocations в черновых | Allocations в утверждённых |
|---|---|---|---|
| Категория → Инициативы (создание) | create | create (`included_flag=false`, `planned_hours=0`) | не трогаем |
| Категория → Инициативы (разархивация существующего) | `archived_at=null` | добить недостающие строки | не трогаем |
| Категория ушла из Инициатив | `archived_at=now()` | удалить из черновых | не трогаем |

**Идемпотентность:** если в черновике уже есть allocation на этот элемент — пропустить, не перетирать `planned_hours` и `included_flag` (PM мог уже вручную проставить галочку и часы).

**Симметрия с ручным `sync-backlog`:** поведение совпадает с тем, что сейчас делает endpoint `POST /planning/scenarios/{id}/sync-backlog` — но теперь это применяется автоматически ко всем черновикам, а не к одному по клику.

## Изменения

### Бэкенд

**`app/services/backlog_service.py`** — расширить `sync_from_issue`:

- После создания/разархивации `BacklogItem`: выбрать все `PlanningScenario` со `status='draft'`, для каждого проверить наличие `ScenarioAllocation(scenario_id, backlog_item_id)` — если нет, создать с дефолтами `included_flag=False`, `planned_hours=0` (без `involvement_coefficient` — оставляем `NULL`). Дефолты ровно как в существующем `POST /planning/scenarios/{id}/sync-backlog`.
- После архивации `BacklogItem`: удалить `ScenarioAllocation` для этого `backlog_item_id` в сценариях со `status='draft'` (утверждённые — не трогаем).

Импорты: добавить `PlanningScenario`, `ScenarioAllocation` к существующему `BacklogItem, Issue`.

Транзакция: `sync_from_issue` делает `flush()`, не коммитит — commit остаётся за вызывающим кодом (уже так работает).

### Фронтенд

**`frontend/src/hooks/useIssueTree.ts`** — в `onSuccess` хуков `useSetIssueCategory` и `useBatchSetCategory` добавить:

```ts
qc.invalidateQueries({ queryKey: ['backlog'] });
qc.invalidateQueries({ queryKey: ['planning'] });
```

Рядом с уже существующим `qc.invalidateQueries({ queryKey: ['issues', 'tree'] })`.

### Миграции

Нет. Схема БД не меняется.

## Тесты

**`tests/test_backlog_service.py`** — новые кейсы для `sync_from_issue`:

1. `test_sync_creates_allocations_in_draft_scenarios` — задача получает `initiatives_rfa`, есть 2 черновика и 1 утверждённый → в черновиках появились allocations с `included_flag=False, planned_hours=0`, в утверждённом — нет.
2. `test_sync_preserves_existing_allocation_values` — в черновике уже есть allocation с `included_flag=True, planned_hours=40` → повторный вызов `sync_from_issue` не перетирает значения.
3. `test_sync_removes_allocations_from_drafts_on_category_leave` — задача уходит из `initiatives_rfa` → allocations удалены из черновиков, в утверждённых — остались.
4. `test_sync_readds_allocations_on_unarchive` — задача ушла, потом вернулась в `initiatives_rfa` → allocations в черновиках восстановлены.
5. `test_sync_idempotent_on_batch` — две задачи → два черновика, порядок вызовов не ломает состояние.

**`tests/test_issue_config_endpoints.py`** (если существует, иначе `test_api_issues.py`) — интеграционный тест на `PUT /issues/batch-category`: после назначения `initiatives_rfa` на 3 задачи allocations созданы в черновиках.

## Out of scope

- UI-индикация «задача ушла в бэклог» после сохранения категории (toast, счётчик) — не запрошено.
- Подчистка allocations в утверждённых сценариях — явно исключено по согласованию.
- Изменение поведения `refresh-from-jira` — оно уже вызывает `sync_from_issue` и получит новое поведение бесплатно.
