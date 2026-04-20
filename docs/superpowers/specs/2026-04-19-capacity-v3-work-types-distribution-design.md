# Capacity v3 — 100 %-распределение времени + редактируемые причины отсутствий

**Дата:** 2026-04-19
**Scope:** страница `/capacity` → вкладки «Правила» и «Отсутствия»; `/settings` → справочник причин отсутствий + поле «Вид работ» на категории.
**Статус:** design approved, готово к `writing-plans`.

---

## 1. Мотивация и контекст

Capacity v2 (спринт 2026-04-19, миграция `020_capacity_rules_v2`) дал справочник обязательных работ, role-level правила в процентах нормы, и per-employee overrides. Текущая семантика: `mandatory_hours = norm × Σ percent / 100`, `available = norm − absence − mandatory`.

PM попросил три изменения.

1. **Правила по ролям обязаны давать Σ = 100 %.** «100 % времени сотрудника должно быть распределено по видам работ.» Это меняет семантику: виды работ описывают **всю** нагрузку (включая продуктивную), а не только «вычитаемое». Чтобы факт (ворклоги) автоматически сопоставлялся с планом, виды работ привязываются к категориям.
2. **Индивидуальные правила — та же матричная структура, что и правила по ролям, с тем же правилом 100 %.**
3. **Отсутствия:**
   - Массовый ввод (хотя бы вся команда на год вперёд не через 40 модалок).
   - Редактируемый справочник причин с флагом «плановое / внеплановое». Внеплановые в будущем будут подсвечены на аналитических дашбордах.

## 2. Ключевые дизайн-решения

| № | Вопрос | Выбор |
|---|--------|-------|
| 1 | Что значит «100 %» | Виды работ покрывают **всю** нагрузку: продуктивные (= Jira-ворклоги) + накладные (= без Jira) |
| 2 | Связь «вид работ ↔ категория» | Один вид работ ← много категорий. Храним как `Category.work_type_id` (nullable FK) |
| 3 | UX валидации 100 % | Draft + явная кнопка «Сохранить»; серверная валидация 422 на Σ ≠ 100 % |
| 4 | Индивидуальные правила в UI | Вариант C: все активные сотрудники в матрице; toggle «Индивидуальное правило» → под ним базовая role-строка серым для справки; разворачивается редактируемая копия |
| 5 | Массовый ввод отсутствий | B + C: строка-на-сотрудника с inline-тегами (B) + кнопка «Массовое добавление» сверху (C). Heatmap сверху остаётся read-only |
| 6 | Справочник причин | Новая таблица `absence_reasons` (FK из `Absence`), CRUD в `/settings` |
| 7 | Будущее (на дорожную карту, **не в этом спеке**) | Редактируемая календарь-матрица отпусков (вариант A в обсуждении bulk UX) |

## 3. Границы

**В scope:**
- Alembic-миграция (таблица `absence_reasons`, FK `Absence.reason_id`, колонка `Category.work_type_id`).
- `CapacityService` — новая формула `available_hours` и метод breakdown per-work-type.
- Батч-эндпоинты для правил (role + employee) с серверной валидацией Σ = 100 %.
- Батч-эндпоинт для отсутствий + CRUD причин.
- Frontend: Rules tab (две матрицы с Save), Absences tab (строка-на-сотрудника + массовый ввод), Settings (справочник причин, поле work_type на категории).

**Не в scope:**
- Jira-синк — не трогаем.
- `PlanningService`, `Backlog`, аналитика, экспорты — будут обновлены отдельными задачами по факту потребности.
- Редактируемый календарь отпусков (вариант A) — на дорожную карту.
- Миграция существующих правил в БД к 100 %: инфра добавляется, но сами правила никто не переписывает — при первом открытии PM увидит 422 по каждой недораспределённой роли и доводит сам.

## 4. Data model

Одна миграция `021_capacity_v3_work_types_distribution`.

### 4.1. Новая таблица `absence_reasons`

```python
class AbsenceReason(Base, TimestampMixin):
    __tablename__ = "absence_reasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_planned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex, опционален
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

**Seed (data migration):**

| code | label | is_planned | color |
|------|-------|-----------|-------|
| `vacation` | Отпуск | `true` | `#fa8c16` |
| `sick` | Больничный | `false` | `#f5222d` |
| `day_off` | Отгул | `false` | `#1677ff` |
| `other` | Прочее | `false` | `#8c8c8c` |

Записи не защищаются флагом `is_system` — пользователь может их переименовать и удалить через UI. Но удаление блокируется в сервисе, если есть хотя бы один `Absence`, ссылающийся на причину.

### 4.2. `Absence.reason` (строка) → `Absence.reason_id` (FK)

```python
# было
reason: Mapped[str] = mapped_column(String(32), nullable=False, default="vacation")

# становится
reason_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("absence_reasons.id", ondelete="RESTRICT"),
    nullable=False, index=True,
)
reason: Mapped["AbsenceReason"] = relationship()
```

**Шаги миграции (batch-mode для SQLite):**
1. Создать таблицу `absence_reasons` и засеять 4 записи.
2. Добавить `reason_id` в `absences` как nullable.
3. Data-migration: для каждой строки `absences` найти `absence_reasons.id` по `absences.reason = absence_reasons.code`; fallback на `other`.
4. Сделать `reason_id` NOT NULL.
5. Дропнуть колонку `reason`.

**Последствия:**
- Удаляем `ABSENCE_REASONS` tuple из `app/models/absence.py` и `app/models/__init__.py`.
- Удаляем `Literal["vacation", "sick", "day_off", "other"]` в `app/api/endpoints/capacity.py` (AbsenceCreate / AbsenceResponse).
- Frontend: хардкодные `REASON_OPTIONS` в `CapacityPage.tsx` заменяются на хук `useAbsenceReasons()`.
- Убираем упоминание `ABSENCE_REASONS` из `CLAUDE.md` (отдельным коммитом после миграции).

### 4.3. `categories.work_type_id` (nullable FK)

```python
# добавляется в app/models/category.py
work_type_id: Mapped[str | None] = mapped_column(
    String(36), ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
    nullable=True, index=True,
)
work_type: Mapped[Optional["MandatoryWorkType"]] = relationship()
```

- `nullable=True` — категория без привязки не участвует в plan/fact breakdown; ворклоги этой категории агрегируются в «Без вида работ» (warning-отчёт для PM).
- `ondelete="SET NULL"` — удаление типа работ не ломает категории.

Миграция просто добавляет колонку как NULL. Привязку пользователь заводит через новый UI на редакторе категорий (см. §7).

### 4.4. Что НЕ меняем

- `mandatory_work_types` — имя таблицы и модели без изменений. Переименование «обязательные» → «виды работ» только в UI-labels, доке, и Russian docstring'ах.
- `role_capacity_rules`, `employee_capacity_overrides` — структура как в v2; меняется только семантика (Σ = 100) и валидация.
- `Absence.hours_total` — остаётся опциональным ручным override.

## 5. `CapacityService` — новая формула

### 5.1. Базовые величины (без изменений)

- `norm_hours` — сумма `ProductionCalendarDay.hours` за период.
- `absence_hours` — сумма по перекрывающимся дням отпусков.

### 5.2. Новый расчёт `available_hours`

```
effective_norm = norm_hours − absence_hours  (clamped to >= 0)

productive_percent = Σ percent_resolved(employee, wt) for wt in WORK_TYPES
                     where wt has at least one linked category

available_hours = effective_norm × productive_percent / 100
mandatory_hours = effective_norm × (100 − productive_percent) / 100
```

`percent_resolved(employee, wt)` — существующий приоритет: override > role exact > role NULL > 0.

**Важно:** если для роли/сотрудника правила в БД не сумируются до 100 %, backend возвращает из списковых эндпоинтов правил warning-флаг, но `CapacityService` не падает и считает с тем, что есть. Это даёт грациозную деградацию, пока PM не добьёт правила (валидация Σ = 100 включается только на save через батч-эндпоинт).

### 5.3. Новый breakdown: plan-vs-fact per work_type

Новый метод `CapacityService.work_type_breakdown(employee_id, year, quarter) -> list[WorkTypeBreakdown]`:

```python
@dataclass
class WorkTypeBreakdown:
    work_type_id: str
    work_type_label: str
    is_productive: bool   # True if hasAnyCategory(wt)
    plan_hours: float     # effective_norm × percent_resolved / 100
    fact_hours: float     # Σ worklog.hours where worklog.issue.category.work_type_id = wt.id
    plan_pct: float       # percent_resolved
```

- `fact_hours` считается через JOIN `Worklog → Issue → Category → work_type_id`.
- Ворклоги в категориях БЕЗ `work_type_id` группируются в синтетическую запись `{work_type_id: None, label: "Без вида работ", is_productive: False, plan_hours: 0, fact_hours: Σ, plan_pct: 0}`. UI показывает это как warning-строку.

### 5.4. Backward compat

- Существующий `QuarterCapacityResponse.total_mandatory_hours` остаётся — но теперь это `(100 − productive_percent) × (norm − absence) / 100`.
- Поле `total_vacation_hours` = `absence_hours` — без изменений.
- Поле `total_available_hours` = `productive_percent × (norm − absence) / 100` — формула изменилась, но поле то же. `TeamTab`, `AbsenceHeatmap`, экспорт `capacity.xlsx` продолжают работать без модификаций.
- Фронт для `BreakdownTab` можно оставить как есть сейчас (по buckets категорий) до следующей итерации; полноценный «plan vs fact per work_type» — отдельная задача в рамках этого же спринта (§7).

## 6. API — изменения

### 6.1. CRUD `absence_reasons`

Новый роутер `app/api/endpoints/absence_reasons.py`, подключить в `app/api/router.py`:

```
GET    /capacity/absence-reasons                  # list all (active + inactive), sort by sort_order
POST   /capacity/absence-reasons                  # create { code, label, is_planned, color?, is_active?, sort_order? }
PATCH  /capacity/absence-reasons/{id}             # update partial
DELETE /capacity/absence-reasons/{id}             # 409 Conflict, если есть зависящие Absence
POST   /capacity/absence-reasons/reorder          # body: { ids: [...] } — сдвиг sort_order
```

### 6.2. `Category` — добавить `work_type_id`

Существующий `PATCH /categories/{id}` расширяется — принимает `work_type_id: str | None` (nullable). Валидация: если не NULL, должен существовать `MandatoryWorkType.id`. Ошибка 422 если тип неактивен.

`GET /categories` — ответ расширяется полем `work_type_id` (и опционально денорм-подсказкой `work_type_label`).

### 6.3. Batch-save для правил с валидацией 100 %

#### 6.3.1. Роль-правила

```
PUT /capacity/role-rules/batch?year=Y&quarter=Q
body: {
  rules: [
    { role: "pm" | "dev" | ... | null, work_type_id: "uuid", percent_of_norm: 20 },
    ...
  ]
}
```

Семантика: **atomic replace** для `(year, quarter)`. Сервер удаляет все существующие правила на `(year, quarter)` и вставляет те, что в body.

**Валидация сервера:**
- Для каждой группы `(role)`: либо сумма по всем `work_type_id` = 100.0 (допуск 0.01), либо группа полностью пустая. Иначе → 422 с детализацией: `{ "errors": [{"role": "pm", "sum": 90, "expected": 100}, ...] }`.
- Группа `role=null` (fallback) — та же валидация.

Старые per-cell эндпоинты (`POST /capacity/role-rules`, `PATCH /capacity/role-rules/{id}`, `DELETE /capacity/role-rules/{id}`) **удаляются** — они несовместимы с новой семантикой. Если какие-то тесты на них есть, переписываем на batch.

#### 6.3.2. Employee-правила

```
PUT /capacity/employee-rules/batch?year=Y&quarter=Q
body: {
  employee_rules: [
    { employee_id: "uuid", rules: [
        { work_type_id: "uuid", percent_of_norm: 25 },
        ...
    ]},
    ...
  ]
}
```

**Семантика:** для каждого `employee_id` в body — atomic replace его overrides на `(year, quarter)`. Сотрудники, не упомянутые в body, не трогаются.

**Валидация:**
- Для каждого `employee_id`: либо `rules` пустой (означает «отключить индивидуальное правило, падать на role»), либо Σ = 100.0.
- Нет требования, чтобы все active-сотрудники были в body.

Старые per-override эндпоинты (POST / PATCH / DELETE) — **удаляются**.

### 6.4. Batch `/absences`

```
POST /absences/batch
body: {
  employee_ids: ["uuid", ...],
  start_date: "2026-07-01",
  end_date: "2026-07-14",
  reason_id: "uuid",
  hours_total: null
}
```

Создаёт одну запись `Absence` на каждого `employee_id`. Возвращает `list[AbsenceResponse]`. Валидация: `end_date >= start_date`, `reason_id` существует и `is_active`, employees существуют. Создаётся в одной транзакции.

Одиночный `POST /absences` оставляем как есть.

### 6.5. Сводка изменений API

| Endpoint | Изменение |
|----------|-----------|
| `GET/POST/PATCH/DELETE /capacity/absence-reasons` | Новый |
| `POST /capacity/absence-reasons/reorder` | Новый |
| `POST /capacity/role-rules` + `PATCH /{id}` + `DELETE /{id}` | **Удалены** |
| `PUT /capacity/role-rules/batch` | Новый (заменяет удалённые) |
| `POST /capacity/employee-rules` + `PATCH /{id}` + `DELETE /{id}` | **Удалены** |
| `PUT /capacity/employee-rules/batch` | Новый (заменяет удалённые) |
| `POST /capacity/role-rules/copy` | Остаётся (копирование между кварталами) |
| `GET /capacity/role-rules` | Остаётся; ответ расширяется полем `sum_per_role` для подсветки в UI |
| `GET /capacity/employee-rules` | Остаётся |
| `PATCH /categories/{id}` | Принимает `work_type_id` |
| `GET /categories` | Ответ включает `work_type_id` |
| `POST /absences/batch` | Новый |

## 7. Frontend

### 7.1. Rules tab — реорганизация

Структура остаётся: 3 подвкладки. Меняем реализацию второй и третьей.

#### 7.1.1. Subtab «Виды работ» (бывшая «Обязательные работы»)

Переименование label вкладки: `Обязательные работы` → `Виды работ`. Никаких функциональных изменений. В описании сверху заменяем «справочник обязательных работ» на «виды работ, покрывающие 100 % времени сотрудника».

#### 7.1.2. Subtab «Правила по ролям» — матрица с draft + Save

Сейчас матрица пишет каждую клетку на blur. Переделываем:
- Локальный state `Map<string, number | null>` (`${role ?? '__all__'}::${wt.id}` → percent).
- Hydration из `GET /capacity/role-rules` при mount и при смене года/квартала.
- «Изменения» trackятся diff'ом: добавляем бейдж «Несохранённых изменений: N» сверху.
- Новая кнопка **«Сохранить»** (primary) — отправляет `PUT /capacity/role-rules/batch`. Неё кнопка «Отменить изменения».
- Колонка **Σ**: окрашивается
  - зелёным, если Σ = 100;
  - красным, если Σ > 100 или 0 < Σ < 100;
  - нейтральным, если Σ = 0 (пустая строка — валидно).
- При 422 от сервера — notification с деталями + роль-строки, которые не прошли, подсвечиваются красным.

«Копировать в следующий квартал» работает как сейчас (серверный эндпоинт не меняем).

#### 7.1.3. Subtab «Индивидуальные правила» — матрица-карточки (вариант C)

Полностью переписываем. Новый макет: одна **карточка на сотрудника** (`Card` AntD), в carded-list.

Структура карточки:

```
┌─────────────────────────────────────────────────────┐
│ Иван Петров           [PM]            ✍ override ◯  │
│                                                     │
│ Role baseline: org 20% | admin 10% | ... | Σ 100%  │
│                                                     │
│ [если override выключен — карточка в этом состоянии] │
│                                                     │
│ ─ если override включен ──────────────────────────  │
│ │ org:   [20%]  admin: [15%]  support: [10%] ...  │ │
│ │ Σ: 100% ✅                                       │ │
│ ─────────────────────────────────────────────────── │
└─────────────────────────────────────────────────────┘
```

Правила:
- Переключатель «✍ override» слева от имени. Выкл → карточка свёрнута (только baseline серым). Вкл → клонируется role-strока в локальный state, раскрывается редактируемая матрица.
- Кнопка «Сохранить все» вверху страницы. Шлёт `PUT /capacity/employee-rules/batch` с теми сотрудниками, у кого override включён + те, кому override был выключен (для них `rules: []`, что соответствует удалению).
- Та же 100-валидация и цветовая индикация Σ, что у role-правил.
- Глобальный фильтр команды (`CapacityFilterProvider`) режет список сотрудников — как сейчас.
- Скрываем сотрудников без назначенной роли? **Нет** — роль может быть null, в этом случае baseline берётся из fallback-строки правил по ролям (role=null).

#### 7.1.4. Копирование role-rules в квартал

Уже есть (`POST /capacity/role-rules/copy`). Не трогаем. На клиенте: после copy — рефреш матрицы.

### 7.2. Absences tab — переделка под B + C

Верх страницы без изменений: `AbsenceHeatmap` остаётся read-only визуализацией.

Ниже — новая структура:

**Таблица-строка-на-сотрудника.**

Колонки:
- **Сотрудник** (с фильтром по имени, как в TeamTab).
- **Отпуска** — inline-теги для всех `Absence` этого сотрудника в видимом периоде (year/quarter из `QuarterYearSelect`). Каждый тег: `{reason.color}` цвет фона, текст `{DD.MM}—{DD.MM}` или `{MMM}`, кликабелен — открывает модалку редактирования / удаления.
- **+** кнопка в конце колонки → открывает модалку «Новое отсутствие» (уже существующую, предзаполняется `employee_id`).
- **Итого дней** — справа: Σ `(end − start + 1)` дней в видимом периоде.

Сверху таблицы:
- Кнопка **«Массовое добавление»** (primary) → открывает modal:
  ```
  Сотрудники:   [multi-select из active]
  Причина:      [select из absence_reasons, is_active]
  Диапазон:     [RangePicker]
  Часов (опц):  [InputNumber]
  [Отмена] [Создать N записей]
  ```
  Посылает `POST /absences/batch`. Успех → notification + invalidate queries.
- Кнопка «Фильтр: показать только внеплановые» — переключатель, фильтрует теги по `reason.is_planned = false`. Запоминается в `AppSetting` (`ui_absences_show_unplanned_only`).
- Существующие кнопки-фильтры (год/квартал) живут в `QuarterYearSelect` сверху страницы.

Текущий плоский список (одна строка = одно отсутствие) **удаляется** — его заменяет строка-на-сотрудника. Если понадобится табличный аудит, выносим в отдельный view в следующей итерации.

### 7.3. Settings page

Расширяется ещё одной вкладкой `reasons` в `SettingsPage`: «Причины отсутствий».

CRUD-таблица, та же схема, что `MandatoryWorkType`:
- Колонки: `↕`, `Code`, `Название`, `Плановое` (Switch), `Цвет` (color-picker или text input для hex), `Активен`, действие «удалить».
- Кнопка «Добавить причину» + модалка.
- Удаление вызывает `DELETE`; на 409 → notification «В БД N записей с этой причиной — сначала перепривяжите их».

Заменяется hardcoded `REASON_OPTIONS` в `CapacityPage.tsx`: теперь через `useAbsenceReasons()`. Meta (label + color) резолвится из справочника.

### 7.4. Привязка Category → WorkType

UI для управления справочником категорий сейчас отсутствует — хуки `useCreateCategory / useUpdateCategory / useDeleteCategory` есть, но не используются. Категории правятся через API или через seed-миграции.

Добавляем новую вкладку в `/settings` → **«Категории работ»** (рядом с «Причины отсутствий»). Содержит таблицу всех категорий:

| Колонка | Источник |
|---------|----------|
| ↕ (reorder) | `sort_order` |
| Code | `Category.code` (read-only — используется в правилах и кодом) |
| Название | `Category.label` (editable) |
| Цвет | `Category.color` (color-picker) |
| **Вид работ** | `Category.work_type_id` — Select из активных `MandatoryWorkType` + пункт «Без привязки» |
| Системная | `Category.is_system` (read-only Tag) |
| ⋯ | Delete (блокируется если `is_system` или если есть Issue с этой категорией) |

Кнопка «Добавить категорию» сверху. Форма минимальная: `code`, `label`, `color`, `work_type_id`.

Этот редактор — минимальный объём, но необходимый для того, чтобы PM смог привязать существующие 10 категорий к видам работ. Добавление / удаление категорий — бонус, не критичный.

### 7.5. Обновление типов (`types/api.ts`)

- Новый `AbsenceReason` интерфейс.
- `AbsenceResponse.reason: AbsenceReason` (было `string`), `AbsenceResponse.reason_id: string`.
- `Category` получает `work_type_id: string | null` и опциональный `work_type_label: string | null`.
- Интерфейсы batch-request/response для правил.

## 8. Тестирование

### 8.1. Backend (pytest)

- `test_capacity_v3_formula.py`: новая формула `available = productive_pct × (norm − absence) / 100` для разных комбинаций (все категории привязаны, часть без привязки, override перекрывает role).
- `test_work_type_breakdown.py`: plan-vs-fact per work_type с ворклогами в разных категориях; кейс с `work_type_id = null` попадает в «Без вида работ».
- `test_role_rules_batch.py`: 422 на Σ ≠ 100, atomic replace, пустая роль валидна.
- `test_employee_rules_batch.py`: то же + partial update (сотрудники вне body не трогаются).
- `test_absence_reasons_crud.py`: create/update/delete + 409 на delete с зависящими Absence.
- `test_absences_batch.py`: создание N записей, валидация `end >= start`, валидация активности reason.
- `test_category_work_type.py`: PATCH categories работает; `ondelete="SET NULL"` при удалении MandatoryWorkType не падает.

Миграция `021_capacity_v3`: smoke-test вверх/вниз на снепшоте БД (опциональный).

### 8.2. Frontend (Playwright E2E)

Расширяем существующий набор:
- `e2e/capacity-rules.spec.ts`: матрица role-правил — заполнить до 100, сохранить, увидеть «Сохранено»; попробовать 90 — увидеть 422 notification и красный Σ.
- `e2e/capacity-absences.spec.ts`: массовое добавление на 3 сотрудников → 3 тега появились в таблице.
- `e2e/settings-reasons.spec.ts`: добавить причину «Декрет» (is_planned=false), использовать её в новом отсутствии, увидеть тег новым цветом.

### 8.3. Manual QA checklist

- [ ] Открыть Capacity → Правила: старые правила отображаются, Σ подсвечивается там, где ≠ 100.
- [ ] Изменить клетку → появляется бейдж «Несохранённых изменений» + кнопка Save enabled.
- [ ] Сохранить с Σ = 85 → 422 notification, данные в БД не изменились.
- [ ] Сохранить с Σ = 100 → «Сохранено».
- [ ] Индивидуальные правила: активировать override для 1 сотрудника → baseline клонируется → править → сохранить.
- [ ] Отсутствия: массовый ввод на 5 человек на 2 недели — все теги отображаются сразу.
- [ ] Settings → Причины: добавить, переименовать, удалить (провал с 409), деактивировать.
- [ ] Categories: указать work_type_id на категории «active_stack» → во вкладке Team-капасити `available` пересчитан (если не все категории привязаны → warning).

## 9. Риски и трейд-оффы

| Риск | Митигация |
|------|-----------|
| Существующие правила в БД не сумируются до 100 % | Миграция НЕ правит данные; при первом save PM получит 422 по каждой роли и доведёт сам |
| Если ни одна категория не привязана к `work_type_id` | `productive_percent = 0 → available = 0`. Warning сверху страницы Capacity и в `/settings` → «Привяжите хотя бы одну категорию к виду работ» |
| Удаление причины отсутствия со ссылками | 409 с понятным сообщением — пусть PM перевесит/удалит Absence |
| Удаление MandatoryWorkType, на который ссылаются role_rules и категории | `ondelete` cascade для rules (уже есть) + SET NULL для categories. Предупреждение в UI перед delete |
| Масштаб: 18 employees × 5 work_types × 4 quarter × роли | Batch-payload — сотни записей максимум, atomic replace в одной транзакции — ОК для SQLite |

## 10. Roadmap (за рамками этого спека)

1. **Редактируемая календарь-матрица отпусков** (вариант A из обсуждения). UI: недели × сотрудники, drag-select создаёт `Absence`. Большой объём фронт-работы, отложено.
2. **Аналитические диаграммы с выделением внеплановых отсутствий.** Дашборд / Analytics получают фильтр/подсветку по `reason.is_planned=false`. Spec отдельным документом.
3. **Импорт CSV для отсутствий.** Если PM попросит — добавляем в массовый ввод как вторую вкладку «Из файла».
4. **`PlanningService` — учёт нового breakdown.** Сейчас PlanningService берёт `team_capacity_hours` из `CapacityService.quarter_capacity(..).total_available_hours` — формула изменится автоматически; но возможно, потребуется учитывать per-work-type plan при greedy-аллокации бэклога.
5. **Экспорт capacity.xlsx:** добавить блок «По видам работ plan/fact».

## 11. План работ (для `writing-plans`)

Грубые этапы:

1. **Backend: миграция + модели.** Новая таблица `absence_reasons`, FK на `Absence`, колонка `work_type_id` на `Category`. Одна alembic-ревизия `021_capacity_v3`.
2. **Backend: `CapacityService` v3.** Новая формула `available_hours`, метод `work_type_breakdown`. Тесты.
3. **Backend: batch-эндпоинты правил + валидация Σ=100.** Удаление per-cell endpoints. Тесты.
4. **Backend: `AbsenceReason` CRUD + `Category.work_type_id` PATCH + `/absences/batch`.** Тесты.
5. **Frontend: `useAbsenceReasons`, `useRoleRulesBatch`, `useEmployeeRulesBatch`, `useAbsencesBatch` хуки.**
6. **Frontend: Rules tab — matrix с draft/save для role-правил.**
7. **Frontend: Rules tab — карточки сотрудников с override-toggle для individual-правил.**
8. **Frontend: Absences tab — таблица-строка + модалка массового добавления.**
9. **Frontend: Settings — вкладка «Причины отсутствий» + `work_type_id` dropdown в редакторе категорий.**
10. **E2E + smoke-пасы, обновление `CLAUDE.md`, памятки, commit/push.**
