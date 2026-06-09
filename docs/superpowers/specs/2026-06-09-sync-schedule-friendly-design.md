# Удобный редактор расписаний синхронизации

**Дата:** 2026-06-09
**Раздел:** `/sync` → вкладка «Расписание»
**Файлы:** `frontend/src/components/sync/SyncSchedule.tsx`, `app/api/endpoints/sync.py`, `app/services/scheduler.py`

## Проблема

1. Создание расписания требует ввода cron-выражения (`0 6 * * *`). Аналитик не знает синтаксис.
2. Существующие расписания нельзя редактировать — только удалять и пересоздавать.

## Цели

- Создавать расписание через типы (каждые N минут/часов, ежедневно, будни, выходные, по дням недели, еженедельно), без знания cron.
- Cron-выражение сохранить как «продвинутый» режим для редких случаев.
- Открыть редактирование уже существующих расписаний.
- Показать человеку, когда расписание реально сработает (3 ближайших запуска).
- В таблице вместо `0 6 * * *` показать «Каждый день в 06:00».

## Не входит

- Изменения backend-эндпоинтов CRUD (`PATCH /sync/schedule/{id}` уже существует).
- Хранение исходного «типа» расписания — тип каждый раз вычисляется из cron при открытии редактирования.
- Поддержка cron-выражений с секундами, годами или `L`/`W`/`#` (APScheduler standard 5-field).

## UX

### Таблица расписаний

Колонка `Cron` → `Расписание`:
- Рендерит человекочитаемое описание (`Каждый день в 06:00`).
- При наведении — Tooltip с raw cron-выражением.

Вся строка кликабельна → открывает modal редактирования (поля предзаполнены). Кнопки «Запустить» и удаление в колонке действий не должны триггерить open-edit (`stopPropagation`).

Кнопка «Добавить» (existing) → тот же modal в режиме create.

### Modal редактора (create + edit)

**Заголовок:** «Новое расписание» / «Редактирование расписания».

**Поля:**

| Поле | Тип | Условие |
|---|---|---|
| Название | Input | всегда |
| Тип расписания | Select | всегда |
| Каждые N минут | InputNumber 1-30 (только делители 60: 1,2,3,4,5,6,10,12,15,20,30) | type=`every_minutes` |
| Каждые N часов | InputNumber 1-12 (только делители 24: 1,2,3,4,6,8,12) | type=`every_hours` |
| Время | TimePicker HH:mm | type ∈ `daily`/`weekdays`/`weekends`/`specific_days`/`weekly` |
| Дни недели | Checkbox.Group (пн-вс) | type=`specific_days` |
| День недели | Select (пн-вс) | type=`weekly` |
| Cron-выражение | Input | type=`cron` |
| Режим | Select (быстрый/обычный/полный/команда) | всегда |
| Команда | Input | mode=`team` (если другой режим — поле скрыто, значение очищается) |
| Включено | Switch | всегда |

**Описание расписания** (read-only текст под формой, серый): «Каждый день в 06:00 — Обычный синк».

**Превью** (Alert типа info под описанием): «Следующие запуски: 10.06.2026 06:00, 11.06.2026 06:00, 12.06.2026 06:00».

Превью обновляется при изменении любого поля расписания (debounce 300ms) через POST `/sync/schedule/preview`.

**Сабмит:** create → POST, edit → PATCH с diff-fields. Cron-выражение строится из полей формы на фронте. Для type=`cron` используется raw input.

### Парсинг cron на open-edit

При открытии редактирования cron существующего расписания парсится в `type` + поля:

| Регекс cron | Type |
|---|---|
| `*/N * * * *` (N — делитель 60) | `every_minutes`, N |
| `0 */N * * *` (N — делитель 24) | `every_hours`, N |
| `M H * * *` | `daily`, time=H:M |
| `M H * * 1-5` или `M H * * 1,2,3,4,5` | `weekdays`, time=H:M |
| `M H * * 0,6` или `M H * * 6,0` | `weekends`, time=H:M |
| `M H * * D1,D2,...` (произвольный набор 0-6) | `specific_days`, days, time |
| `M H * * D` (один день) | `weekly`, day, time |
| Всё остальное | `cron`, raw |

Парсинг — на фронте. Если не распознано — fallback на `cron`, сохраняется исходная строка.

## Backend

### Новый endpoint

```
POST /sync/schedule/preview
Body: { "cron_expr": "0 6 * * *" }
Response: {
  "description": "Каждый день в 06:00",
  "next_runs": ["2026-06-10T06:00:00", "2026-06-11T06:00:00", "2026-06-12T06:00:00"],
  "valid": true,
  "error": null
}
```

При невалидном cron: `200 OK` с `valid=false`, `error="Invalid cron expression"`, `next_runs=[]`, `description=null`. Это не ошибка пользователя, а состояние превью — фронт показывает сообщение об ошибке inline.

**Логика:**
- Валидация cron: `SchedulerService.is_valid_cron` (существующий метод).
- Следующие запуски: `APScheduler.triggers.cron.CronTrigger.from_crontab(cron_expr).get_next_fire_time()` × 3.
- Описание: новая функция `humanize_cron(cron_expr) -> str` в `app/services/scheduler.py`. Поддерживает те же типы, что фронт парсит. Для не распознанных возвращает `"По cron-выражению: {cron}"`.

### Изменение существующих эндпоинтов

`GET /sync/schedule` и `POST /sync/schedule` и `PATCH /sync/schedule/{id}` возвращают `SyncScheduleOut` с новым computed-полем `description: str`. Описание считается на бэке через `humanize_cron(cron_expr)`. Это устраняет необходимость дублировать парсер на фронте для таблицы.

## Frontend

### Файлы

- `frontend/src/components/sync/SyncSchedule.tsx` — таблица + кнопка «Добавить». Удаляет inline Modal, держит state `editingSchedule: SyncScheduleOut | null` и `creating: boolean`.
- `frontend/src/components/sync/ScheduleEditorModal.tsx` (новый) — modal с билдером, превью, валидацией. Используется и для create, и для edit.
- `frontend/src/utils/cronBuilder.ts` (новый) — чистые функции `parseCron(cron) → ScheduleForm` и `buildCron(form) → string`.
- `frontend/src/api/syncSchedule.ts` — добавить `previewSchedule(cron_expr) → Promise<PreviewResponse>`. В `SyncScheduleOut` добавить `description: string`.

### Типы

```ts
type ScheduleType =
  | 'every_minutes' | 'every_hours'
  | 'daily' | 'weekdays' | 'weekends'
  | 'specific_days' | 'weekly' | 'cron';

interface ScheduleForm {
  type: ScheduleType;
  minutes?: number;        // every_minutes
  hours?: number;          // every_hours
  time?: string;           // HH:mm — daily/weekdays/weekends/specific_days/weekly
  days?: number[];         // 0-6 (вс-сб по AntD), specific_days
  day?: number;            // weekly
  cron?: string;           // cron
}
```

День недели: APScheduler/cron — 0=вс, 1=пн, ..., 6=сб. AntD Checkbox.Group отображает пн первым; маппинг в `cronBuilder`.

## Валидация

**Frontend** перед сабмитом:
- Название — required, trimmed.
- Тип — required.
- Минуты — целое в {1,2,3,4,5,6,10,12,15,20,30}.
- Часы — целое в {1,2,3,4,6,8,12}.
- Время — required для type требующих времени.
- Дни недели — минимум один.
- Cron — required для type=`cron`.
- Команда — required если mode=`team`.

**Backend** (existing): `SchedulerService.is_valid_cron`. 400 если cron невалиден.

## Тесты

**Backend:**
- `tests/test_sync_schedule_preview.py`:
  - Валидный cron → 3 next_runs + description.
  - Невалидный cron → `valid=false`, `next_runs=[]`.
  - `humanize_cron`: каждый поддерживаемый тип → ожидаемая строка.
- Существующие тесты `test_sync_schedule_crud` обновить: проверить наличие `description` в ответе.

**Frontend:**
- Покрытие через ручной браузер-смок: создать каждый из 8 типов, проверить cron в БД, открыть на edit, убедиться что поля распарсились корректно. E2E не требуется.

## План отгрузки

Один батч. Бэк + фронт мёрджатся вместе, иначе новое поле `description` сломает типы. Тесты — pytest. Frontend lint + build.

## Открытые вопросы

Нет.
