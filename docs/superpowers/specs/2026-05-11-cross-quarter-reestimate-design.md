# Cross-Quarter Re-estimate — Design

**Дата:** 2026-05-11
**Автор:** brainstorm с PM
**Контекст:** ITL-299 и аналогичные инициативы — старт в Q1 (часть часов списали), пауза, продолжение в Q2 с новой оценкой. Сейчас BacklogItem хранит одну оценку из Jira initiatives_rfa, перенос в новый сценарий не позволяет переоценить.

---

## Цель

Дать PM возможность вручную переоценить инициативу в конкретном сценарии (per-quarter), не трогая Jira-поля и не ломая исходные одобренные сценарии.

## Базовое решение

**Per-scenario override оценок по 4 ролям**, живёт на `ScenarioAllocation`. `BacklogItem` = эталон из Jira, override = «что планируем в этом сценарии». Одобренные сценарии используют свои snapshot-ы — старые цифры не «убегают» при появлении override в новом черновике.

## Решённые вопросы

| # | Вопрос | Решение |
|---|---|---|
| 1 | Источник новой оценки | PM вводит руками в нашем сервисе. Jira-поля не трогаем |
| 2 | Формат ввода | 4 цифры: аналитика / разработка / тестирование / ОПЭ |
| 3 | Подсказка «уже потрачено» | Показываем разбивкой по ролям в pop-over редактирования |
| 4 | UI расположение | Pop-over по кнопке «✎» в строке allocation (вариант B) |
| 5 | Поведение по умолчанию (без override) для «продолжения» | ⚠ строка не учитывается в норме до ручного ввода |
| 6 | База «списано» | Все ворклоги по issue с датой < начало квартала сценария |
| 7 | Валидация (план < списано) | Сохраняем, красное предупреждение |

## Что НЕ делаем

- Не клонируем BacklogItem (issue_id unique)
- Не меняем оценки в Jira
- Не различаем «остаток» vs «переоценка» в данных — один механизм override
- Не вводим quarter-versioned оценки на BacklogItem (override на allocation решает)
- Не делаем audit trail изменений override (MVP без истории)

---

## Модель данных

### Новые поля на `scenario_allocations`

| Поле | Тип | Nullable | Описание |
|---|---|---|---|
| `override_estimate_analyst_hours` | Float | yes | Часы аналитики на квартал. NULL = inherit |
| `override_estimate_dev_hours` | Float | yes | Часы разработки |
| `override_estimate_qa_hours` | Float | yes | Часы тестирования |
| `override_estimate_opo_hours` | Float | yes | Часы ОПЭ |

**Правило inherit:** если все 4 NULL → inherit из `BacklogItem.estimate_*_hours`. Если хотя бы один не-NULL → используем все 4 из override (несработавшие читаем как 0.0).

### Новые поля на `scenario_allocation_snapshots`

Те же 4 поля. Заполняются при approve через `snapshot_writer`. Одобренный сценарий после этого живёт независимо.

### Миграция

Один Alembic batch revision (SQLite-safe):
- `add_column` × 4 на `scenario_allocations` (default NULL)
- `add_column` × 4 на `scenario_allocation_snapshots` (default NULL)

Backfill не нужен (NULL = существующее поведение).

---

## Эффективные часы — единый источник правды

Хелпер `effective_estimate_hours(allocation)` → `{analyst, dev, qa, opo}`:

```
если any(override_*) is not None:
    return {analyst: override_analyst or 0,
            dev:     override_dev or 0,
            qa:      override_qa or 0,
            opo:     override_opo or 0}
else:
    return {analyst: backlog_item.estimate_analyst_hours or 0,
            dev:     backlog_item.estimate_dev_hours or 0,
            qa:      backlog_item.estimate_qa_hours or 0,
            opo:     backlog_item.estimate_opo_hours or 0}
```

Используют:
- `PlanningService` — расчёт плана и нормы сценария
- `ResourcePlanningService` — длительности фаз и часы
- `ScenarioXlsxExportService` — лист «Включено»
- `AnalyticsService` — где сейчас читается backlog estimate
- `ExecutiveDashboardService` — фактический план сценария

Хелпер живёт в `app/services/allocation_estimates.py` (или внутри `PlanningService`).

---

## «Списано» и флаг продолжения

### Расчёт списанного

Для каждой allocation в сценарии:

```
quarter_start = date(scenario.year, (scenario.quarter-1)*3 + 1, 1)
worklogs = Worklog WHERE issue_id = backlog_item.issue_id
                     AND started_at < quarter_start
spent[role] = SUM(worklog.hours_spent) grouped by category_role
```

Маппинг категории ворклога → роль (analyst/dev/qa/opo) уже существует в `CategoryResolver` / `AnalyticsService`. Используем тот же.

**Важно:** считается только если `backlog_item.issue_id IS NOT NULL` (ручные backlog item без Jira-привязки → spent = все нули, флаг продолжения = false).

### Флаг is_continuation

```
is_continuation = sum(spent.values()) > 0
```

### Состояние allocation в Q2

| Условие | Поведение в UI | Учёт в норме |
|---|---|---|
| `is_continuation=false`, override пуст | Обычная строка, цифры из Jira (как сейчас) | Учитывается |
| `is_continuation=true`, override пуст | ⚠ красная строка «укажи план на Q2 руками» | **НЕ учитывается** |
| Override сохранён | Бейдж «переоценка», цифры из override | Учитывается |

`PlanningService.compute_*` скипает allocation если `is_continuation AND override is empty`.

---

## API

### `PATCH /api/v1/planning/scenarios/{scenario_id}/allocations/{allocation_id}/override`

Body:
```json
{
  "analyst": 25.0,
  "dev": 80.0,
  "qa": 40.0,
  "opo": 20.0
}
```

- Все 4 поля обязательны (PM вводит сразу четвёрку)
- Чтобы сбросить — передать `null` во всех 4: `{analyst: null, dev: null, qa: null, opo: null}` → запись 4 NULL в БД
- Запрещён на `scenario.status = approved` → 409
- 404 если allocation не найдена в этом сценарии
- Возвращает обновлённую allocation

### `GET /api/v1/planning/scenarios/{scenario_id}/continuation-info`

Один батч-запрос для всех allocations сценария. Ответ:

```json
{
  "info_by_allocation_id": {
    "<allocation-uuid>": {
      "spent": {"analyst": 20, "dev": 60, "qa": 0, "opo": 0},
      "spent_total": 80,
      "is_continuation": true,
      "jira_estimate": {"analyst": 40, "dev": 120, "qa": 30, "opo": 20}
    }
  }
}
```

Используется фронтом для рендера бейджей и заполнения pop-over. Без N+1.

### Reactivity

После PATCH публикуется `entity_changed` через `EventBroadcaster` (тип `scenario_allocation`, `scenario_id`). Существующий механизм SSE инвалидации.

---

## UI

### Строка allocation (PlanningPage)

Компактная как сейчас, плюс:
- Кнопка «✎» справа от чекбокса (всегда видна)
- Бейдж справа от названия:
  - «переоценка» (жёлтый Tag) — если override сохранён
  - «⚠ продолжение» (красный Tag) — если is_continuation и override пуст
- Текст с цифрами под названием:
  - Override: `Q2: А 25 / Р 80 / Т 40 / ОПЭ 20 = 165ч`
  - is_continuation без override: `⚠ укажи план на Q2`
  - Иначе как сейчас (Jira оригинал)

### Pop-over (AntD Popover)

Триггер: клик по «✎». Содержимое:

**Шапка:**
- «Оригинал Jira: А 40 / Р 120 / Т 30 / ОПЭ 20 = 210ч»
- «Списано в прошлых периодах: А 20 / Р 60 / Т 0 / ОПЭ 0 = 80ч»

**Таблица:**

| Роль | План Q2 | Списано | Остаток оригинала |
|---|---|---|---|
| Аналитика | `[input]` | 20 | 20 |
| Разработка | `[input]` | 60 | 60 |
| Тестирование | `[input]` | 0 | 30 |
| ОПЭ | `[input]` | 0 | 20 |

- Если `input < spent[role]` → красная подпись под input «план меньше уже списанного»
- Pre-fill при первом открытии: остаток оригинала (Jira − списано), но не отрицательный
- При сохранённом override — pre-fill из текущих значений

**Кнопки:**
- «Сохранить» (primary) — PATCH с 4 цифрами
- «Сбросить» (default) — PATCH с 4 null (показывается только если override уже сохранён)

### Хук

`useScenarioContinuationInfo(scenarioId)` — React Query запрос batch endpoint, ключ `['planning-continuation', scenarioId]`. Инвалидируется после PATCH и при approve/draft переключении.

### Доступ

Pop-over disabled на approved сценариях (видна, но read-only).

---

## Снапшоты

`ScenarioAllocationSnapshot` уже снимает `planned_hours` при approve. Расширение:
- 4 новых поля override (хранят значения, которые были эффективными на момент approve — либо override, либо inherit из BacklogItem)
- `snapshot_writer` читает `effective_estimate_hours()` и пишет 4 цифры в snapshot

После approve allocation override меняться не может (API блокирует), но даже если у нижележащего BacklogItem поменяется оценка в Jira — snapshot уже хранит зафиксированные числа.

---

## Тесты

### Backend

- `tests/services/test_allocation_estimates.py` — хелпер effective_hours: только Jira, только override, mix
- `tests/services/test_planning_service_continuation.py` — расчёт нормы скипает is_continuation без override
- `tests/services/test_continuation_info.py` — расчёт spent и is_continuation
- `tests/api/test_allocation_override.py` — PATCH success / 409 на approved / валидация / сброс
- `tests/api/test_continuation_info_endpoint.py` — батч-ответ, отсутствие N+1
- Расширение `tests/services/test_snapshot_writer.py` — snapshot включает override

### Frontend

- Existing E2E на planning: добавить кейс «перенос инициативы в Q2, ⚠ → ввод override → нормальная строка»
- Если есть unit-тесты Popover — добавить рендер pop-over с разными состояниями

---

## Открытые вопросы (отложено)

1. История изменений override (audit trail) — пока «нет», MVP
2. Что если worklog пересинкнули и spent пересчитался после ввода override → видно через актуальный continuation-info, override не трогаем

---

## Файлы (high-level)

**Создаём:**
- `alembic/versions/XXX_allocation_override.py`
- `app/services/allocation_estimates.py` (или метод в PlanningService)
- `app/services/continuation_service.py` (или метод в существующем сервисе)
- `app/api/endpoints/planning_override.py` (или добавление в `planning.py`)
- `tests/services/test_allocation_estimates.py`
- `tests/services/test_continuation_info.py`
- `tests/services/test_planning_service_continuation.py`
- `tests/api/test_allocation_override.py`
- `tests/api/test_continuation_info_endpoint.py`
- `frontend/src/components/planning/AllocationOverridePopover.tsx`
- `frontend/src/hooks/useScenarioContinuationInfo.ts`

**Редактируем:**
- `app/models/scenario_allocation.py`
- `app/models/scenario_allocation_snapshot.py`
- `app/services/planning_service.py`
- `app/services/resource_planning_service.py`
- `app/services/scenario_xlsx_export.py`
- `app/services/analytics_service.py`
- `app/services/executive_dashboard_service.py`
- `app/services/snapshot_writer.py`
- `app/api/endpoints/planning.py`
- `frontend/src/api/planning.ts`
- `frontend/src/hooks/usePlanning.ts`
- `frontend/src/pages/PlanningPage.tsx`
