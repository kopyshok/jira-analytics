# Кросс-секционная реактивность — дизайн

**Дата:** 2026-04-27  
**Статус:** Утверждён  
**Контекст:** Реструктуризация п.1 + п.3 (EventBroadcaster уже задеплоен в п.4)

---

## Проблема

Сервис разворачивается в многопользовательском режиме: несколько сотрудников работают одновременно, у каждого своя команда. Синхронизация с Jira — общая, по расписанию.

**Текущие симптомы:**
1. Пользователь помечает инициативу как «включена» в Сценарии → переходит в Бэклог — статус «в работе» устарел, надо вручную обновлять страницу.
2. Плановая синхронизация завершается → ни один открытый раздел не обновляется автоматически.
3. Второй пользователь, работающий параллельно, никогда не видит изменений первого без перезагрузки.

---

## Решение: серверный push через SSE (Подход B)

EventBroadcaster (pub/sub + SSE) уже работает. Фронтенд уже обрабатывает `entity_changed` события в `useEventStream`, но бэкенд их никогда не публикует. Нужно дозаполнить оставшиеся 20%.

### Принцип

После каждой мутации бэкенд публикует событие `entity_changed` с перечнем затронутых сущностей. Все подключённые браузеры получают событие через SSE и тихо инвалидируют нужные кэши TanStack Query — без баннеров, без перезагрузки.

---

## Архитектура

### Форма события

```python
# app/services/event_bus.py — расширить существующий publish()
{
    "type": "entity_changed",
    "entities": ["backlog", "planning"]   # список затронутых доменов
}
```

`entities` — массив строк из фиксированного словаря:

| Ключ | Что означает |
|---|---|
| `issues` | Задачи Jira (дерево, категории) |
| `backlog` | Бэклог инициатив |
| `planning` | Сценарии и аллокации |
| `capacity` | Загрузка сотрудников |
| `analytics` | Аналитика / Dashboard |
| `employees` | Справочник сотрудников |
| `projects` | Проекты (scope) |

### Frontend: invalidateForEntity()

Файл `frontend/src/hooks/useEventStream.ts`. Расширить `invalidateForEntity()`:

| Entity | Инвалидируемые queryKey |
|---|---|
| `issues` | `['issues']`, `['analytics']`, `['backlog']` |
| `backlog` | `['backlog']`, `['planning']` |
| `planning` | `['planning']`, `['backlog']` |
| `capacity` | `['capacity']` |
| `analytics` | `['analytics']` |
| `employees` | `['employees']`, `['capacity']` |
| `projects` | `['scope', 'projects']` |
| `worklogs` | `['employees']`, `['capacity']`, `['analytics']` |

Обработчик `entity_changed` должен поддерживать как строку (`event.entity`), так и массив (`event.entities`):

```typescript
case 'entity_changed':
  const entities = event.entities ?? (event.entity ? [event.entity] : []);
  entities.forEach(e => invalidateForEntity(e, qc));
  break;
```

---

## Backend: что и где публиковать

### 1. Мутации Бэклога

**Файл:** `app/api/endpoints/backlog.py`

| Endpoint | entities |
|---|---|
| `POST /backlog` (создание) | `["backlog"]` |
| `PATCH /backlog/{id}` | `["backlog"]` |
| `POST /backlog/{id}/archive` | `["backlog"]` |
| `POST /backlog/{id}/restore` | `["backlog"]` |

### 2. Мутации Сценариев и аллокаций

**Файл:** `app/api/endpoints/planning.py`

| Endpoint | entities |
|---|---|
| `POST /scenarios` | `["planning"]` |
| `DELETE /scenarios/{id}` | `["planning", "backlog"]` |
| `PATCH /scenarios/{id}/allocations/{alloc_id}` (included_flag, planned_hours) | `["planning", "backlog"]` |
| `PATCH /scenarios/{id}/allocations/{alloc_id}/assignee` | `["planning"]` |
| `POST /scenarios/{id}/approve` | `["planning", "backlog"]` |
| `POST /scenarios/{id}/revert` | `["planning", "backlog"]` |

### 3. Массовое обновление категорий задач

**Файл:** `app/api/endpoints/issues.py`

| Endpoint | entities |
|---|---|
| `POST /issues/batch-category` | `["issues", "backlog"]` |

### 4. Sync pipeline: pipeline_done

**Файл:** `app/services/sync_pipeline.py`

При публикации `pipeline_done` добавить в событие суммарный список `entities` из всех этапов — и одновременно опубликовать отдельное `entity_changed`:

```python
# После завершения всех этапов
all_entities = list({e for stage in completed_stages for e in stage.invalidates})
await event_bus.publish({"type": "entity_changed", "entities": all_entities})
```

Маппинг существующих `stage.invalidates` строк → entity-ключи:

| stage.invalidates | entity |
|---|---|
| `"issues"`, `"tree"` | `"issues"` |
| `"backlog"`, `"planning"` | `"backlog"`, `"planning"` |
| `"worklogs"` | `"worklogs"` |
| `"capacity"` | `"capacity"` |
| `"analytics"` | `"analytics"` |

**Фронтенд:** обработчик `pipeline_done` в `useEventStream` — оставить существующую инвалидацию `['sync', 'runs']` и `['sync', 'status']` как есть (нужна для UI истории синхронизаций). Дата-разделы обновятся автоматически через отдельное `entity_changed` событие, которое бэкенд публикует сразу после `pipeline_done`.

---

## Паттерн внедрения в endpoint

Инъекция `event_bus` через FastAPI Depends. Публикация — **после** успешного `db.commit()`, до возврата ответа:

```python
async def patch_allocation(
    ...,
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    # ... мутация ...
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning", "backlog"]})
    return result
```

Если мутация кидает исключение до commit — событие не публикуется (правильно: данные не изменились).

---

## Что явно вне скоупа

- Глобальный фильтр команды — отдельная задача.
- Auth / изоляция данных по пользователю — п.2 реструктуризации.
- Оптимистичные обновления на фронте — не нужны, silent refresh достаточно.
- Отдельные события на уровне отдельной записи (item_id) — избыточно для текущего масштаба.

---

## Тестирование

1. **Unit-тесты endpoint'ов:** mock EventBroadcaster, проверить что `publish()` вызван с правильными entities после commit.
2. **Integration SSE тест:** реальный SSE stream + мутация → проверить что событие получено.
3. **Frontend:** TanStack Query cache inspection в тестах — проверить инвалидацию после получения entity_changed.

---

## Оценка

| Работа | Объём |
|---|---|
| Backend: publish в 10 endpoints | ~4 ч |
| Frontend: расширить invalidateForEntity + handler | ~2 ч |
| Sync pipeline: entity_changed при pipeline_done | ~1 ч |
| Тесты | ~3 ч |
| **Итого** | **~1.5 дня** |
