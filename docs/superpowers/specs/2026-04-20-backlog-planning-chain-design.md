# Бэклог инициатив → Сценарии планирования (design)

**Дата:** 2026-04-20
**Автор:** Claude (совместно с PM)
**Статус:** approved-by-user
**Scope:** полная цепочка от синхронизации RFA/ITL из Jira до нового экрана «Сценарии» с чекбоксами и ёмкостью по ролям.

## Цели

1. **Бэклог инициатив** в нашей БД наполняется автоматически из Jira-задач с категорией `initiatives_backlog` «Бэклог инициатив». Оценки (анализ / разработка / тестирование / ОПЭ) синкаются из customfields вкладки «Плановые трудозатраты».
2. **Ручные записи бэклога** поддерживаются для идей, которых в Jira ещё нет. Позднее связываются с RFA/ITL по ключу.
3. **Страница «Сценарии» (`/planning`)** переделывается под прототип `design-ja/project/Prototype.html` — two-column layout с бэклогом + чекбоксами слева и sticky-панелью capacity по ролям справа.
4. **Capacity по ролям** (Аналитик / Программист / Тестировщик) рассчитывается агрегацией по `Employee.role`; ОПЭ-часы задачи распределяются между analyst/dev через `opo_analyst_ratio`.
5. **Меню** реорганизуется: группа «ПЛАНИРОВАНИЕ» поднимается над «ДАННЫЕ».

**Явно не входит в scope:**
- Ресурсное календарное планирование (вовлеченность + длительности) — поля синкаем и храним, но UI/логика позже.
- Полноценный UI редактирования `Employee.role` — ограничимся добавлением dropdown в существующую форму.

## Терминология

- **Бэклог (BacklogItem)** — строка списка идей для планирования. Может быть привязана к `Issue` (автоматически из Jira) или создана вручную.
- **Сценарий (PlanningScenario)** — сохранённый выбор идей на квартал.
- **Роль (role)** — одно из `analyst | dev | qa`. Определяется полем `Employee.role`.
- **ОПЭ (Пусконаладочные)** — часы запуска, распределяются между аналитиком и программистом через per-task `opo_analyst_ratio` (default 0.5).

## Модель данных

### 1. Новая категория (seed через миграцию)

```python
("initiatives_backlog", "Бэклог инициатив", "#7F77DD", 23, True)
# (code, label, color, sort_order, is_system) — 23 = следующий после archive_target (22)
```

`ARCHIVE_CATEGORY_CODES` не трогаем — это не архив.

### 2. Issue — новые колонки

Все nullable, Float / String(20). Одна миграция:

```python
planned_analyst_hours    Float
planned_dev_hours        Float
planned_qa_hours         Float
planned_opo_hours        Float
involvement_analyst      Float  # 0..1, для будущего календарного планирования
involvement_dev          Float
involvement_qa           Float
involvement_launch       Float  # «вовлеченность аналитика и разработчика на запуск»
duration_analyst_days    Float
duration_dev_days        Float
duration_qa_days         Float
duration_launch_days     Float
impact                   String(20)  # low | medium | high (или как в Jira, нормализуем)
risk                     String(20)  # low | medium | high
```

`sync_service._upsert_issue` читает ID кастом-полей из `AppSetting`, извлекает значения через существующий паттерн `_extract_field_value(extra, field_id)` (числовое значение для часов/долей, текст для impact/risk).

**Нормализация impact/risk:** маппим распространённые Jira-значения в три уровня:
- `high | высокий | critical | major` → `high`
- `medium | средний | normal` → `medium`
- `low | низкий | minor | trivial` → `low`
- Пустое / неизвестное → `NULL`.

### 3. BacklogItem — новые колонки

```python
issue_id               String(36), FK → issues.id, nullable, **unique**, indexed
estimate_analyst_hours Float
estimate_dev_hours     Float
estimate_qa_hours      Float
estimate_opo_hours     Float
opo_analyst_ratio      Float, default 0.5  # доля ОПЭ → аналитику; 1 - ratio → программисту
impact                 String(20)
risk                   String(20)
```

Существующее поле `estimate_hours` **становится derived-колонкой**: считается при записи как `sum(estimate_*_hours)` или через `@property`. Оставляем в схеме для обратной совместимости с PlanningService (греда) и экспортом.

**Инвариант:** `issue_id UNIQUE` — один BacklogItem на одну Jira-задачу.

### 4. AppSetting — новые ключи

Настраиваются в `/settings → Поля Jira`:

```
jira_planned_analyst_hours_field_id   # напр. customfield_12001
jira_planned_dev_hours_field_id
jira_planned_qa_hours_field_id
jira_planned_opo_hours_field_id
jira_involvement_analyst_field_id     # для будущего
jira_involvement_dev_field_id
jira_involvement_qa_field_id
jira_involvement_launch_field_id
jira_duration_analyst_field_id
jira_duration_dev_field_id
jira_duration_qa_field_id
jira_duration_launch_field_id
jira_impact_field_id
jira_risk_field_id
```

Если какой-то ID не задан — поле просто не синкаем (остаётся NULL в Issue).

## Backend

### Sync

`sync_service.py`:
- `_list_custom_field_ids()` расширяется новыми ключами. Все присутствующие ID попадают в параметр `fields=` Jira-запроса.
- `_upsert_issue` добавляет блок извлечения:

```python
def _f(field_id, cast=float):
    if not field_id:
        return None
    raw = (extra or {}).get(field_id)
    if raw is None:
        return None
    try:
        return cast(raw) if cast is not float else float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None

issue.planned_analyst_hours = _f(analyst_id)
# ...
issue.impact = _normalize_level(_f(impact_id, cast=str))
issue.risk  = _normalize_level(_f(risk_id, cast=str))
```

### Авто-создание BacklogItem по категории

Новый метод в **`BacklogService.sync_from_issue(issue, session)`**:

1. Используется **собственная** `issue.category` (денормализованное поле в Issue — это code-строка, не FK; не наследуется, чтобы не захватывать подзадачи эпика-бэклог-инициативы).
2. Если `issue.category == 'initiatives_backlog'`:
   - `get_or_create BacklogItem(issue_id=issue.id)`;
   - **Jira — источник истины**: всегда перезаписывает `estimate_analyst/dev/qa/opo_hours`, `impact`, `risk` из issue;
   - `title = issue.summary`, `project_id = issue.project_id` (также перезаписываются из Jira);
   - **Локальные поля, Jira не трогает:** `priority`, `opo_analyst_ratio`, `year`, `quarter`, `id`, `created_at`;
   - year/quarter — по текущему «активному» значению (из AppSetting `backlog_default_year` / `backlog_default_quarter`) при **create**; при update не меняются.
3. Если `issue.category != 'initiatives_backlog'` и BacklogItem существует:
   - Если `BacklogItem.id` **не ссылается из ScenarioAllocation** → удаляем;
   - Иначе → `issue_id = NULL` (soft unlink), оставляем как historical-запись.

**Политика перезаписи оценок:** для задач с привязанным Issue:
- При `BacklogService.sync_from_issue` оценки из Jira **перезаписывают** локальные (источник истины — Jira), но `priority`, `opo_analyst_ratio`, `year`, `quarter` — локальные и не трогаются.
- В UI бэклога ячейки часов **read-only** для Jira-задач, редактируемы для ручных (см. Frontend).

### Новые endpoints

```
POST   /backlog/{id}/link-jira     body: {jira_key: "RFA-123"}
  → находит Issue(jira_key=RFA-123), проверяет что Issue существует локально
    (иначе 404 «нужно сначала синкнуть»), ставит BacklogItem.issue_id,
    вызывает BacklogService.sync_from_issue для перетирания оценок.
    Возвращает обновлённый BacklogItem.

POST   /backlog/{id}/unlink-jira
  → issue_id = NULL; оценки оставляет как есть.

POST   /backlog/refresh-from-jira?year=N&quarter=Q
  → пробегает все Issue(category='initiatives_backlog') за период
    и вызывает sync_from_issue для каждой. Идемпотентно.
```

### Existing endpoints — правки

- `POST /backlog` и `PATCH /backlog/{id}` принимают новые поля: `estimate_analyst_hours/...`, `opo_analyst_ratio`, `impact`, `risk`, `issue_id`.
- `GET /backlog` возвращает новые поля + денормализованный `jira_key` (join с Issue) для UI.

### CapacityService — per-role

Добавляем метод `team_role_capacity(year, quarter, team_filter?) -> dict[role, hours]`:

```python
def team_role_capacity(year, quarter, team_filter=None):
    out = {"analyst": 0.0, "dev": 0.0, "qa": 0.0}
    for emp in active_employees(team_filter):
        role = (emp.role or "").lower()
        if role not in out:
            continue  # сотрудники без роли или с нестандартной ролью не учитываются
        avail = employee_available_hours(emp, year, quarter)  # norm − absence − mandatory
        out[role] += avail
    return out
```

`employee_available_hours` — уже существующая логика, просто обёртка вокруг `CapacityService.monthly_capacity` × 3 месяца квартала.

### PlanningService — per-role allocation

Обновляется `generate_scenario(year, quarter, backlog_item_ids?)`:

```python
capacity_role = capacity_service.team_role_capacity(year, quarter)

def demand_roles(item):
    ea = item.estimate_analyst_hours or 0
    ed = item.estimate_dev_hours or 0
    eq = item.estimate_qa_hours or 0
    eo = item.estimate_opo_hours or 0
    r  = item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
    return {
        "analyst": ea + eo * r,
        "dev":     ed + eo * (1 - r),
        "qa":      eq,
    }

# greedy by priority; item fits if for each role: remaining[role] >= demand[role]
```

Поле `ScenarioAllocation.planned_hours` = общий sum; детализация по ролям считается на лету из `BacklogItem` (не денормализуем, т.к. `opo_ratio` может меняться).

### Новый endpoint «превью ёмкости»

```
POST /planning/capacity-preview
  body: {year, quarter, backlog_item_ids: [...], team_filter?: [...]}
  → {
      capacity_by_role: {analyst, dev, qa},
      demand_by_role:   {analyst, dev, qa},
      total_capacity, total_demand,
      per_employee: [
        {employee_id, name, role, raw_hours, mandatory_hours, available_hours, vacation_days}
      ],
      breakdown: {
        workdays_per_month: [...],
        gross_hours, vacation_hours, mandatory_hours, available_hours
      }
    }
```

Используется новой страницей «Сценарии» для live-расчёта без сохранения сценария.

## Frontend

### Меню

[frontend/src/components/Layout/SideMenu.tsx](frontend/src/components/Layout/SideMenu.tsx):

```
ОБЗОР         Дашборд, Аналитика
ПЛАНИРОВАНИЕ  Ресурсы, Бэклог, Сценарии
ДАННЫЕ        Задачи/синк, Настройки
```

Внутренний порядок групп не меняется.

### Settings → Поля Jira

Расширяем [frontend/src/components/JiraFieldsCard.tsx](frontend/src/components/JiraFieldsCard.tsx):

- Группа **«Плановые трудозатраты (часы)»**: 4 поля (analyst/dev/qa/opo)
- Группа **«Вовлеченность и длительности»** (collapsed by default, с подписью «Для будущего календарного планирования»): 4 + 4 полей
- Группа **«Приоритизация»**: impact, risk

Каждое поле — `Input` с `customfield_XXXX`, сохраняется через существующий `/settings/generic/{key}`.

### Employee — роль

В [frontend/src/pages/EmployeesPage.tsx](frontend/src/pages/EmployeesPage.tsx) (или где редактируется сотрудник):

- Добавляем dropdown `role`: options `['analyst', 'dev', 'qa', 'other']` (4-й вариант — «без роли в сценариях», сохраняется как `"other"` или пусто).
- Labels Ru: Аналитик / Программист / Тестировщик / Другое.

### Страница «Бэклог» (`/backlog`)

Таблица:

| ☐ | Prio | Название | Jira-ключ | АН ч | ПР ч | ТС ч | ОПЭ ч | ОПЭ→АН | Impact | Risk | Проект | Q | Действия |

- Jira-ключ — кликабельная ссылка на Jira (если `issue_id` не NULL).
- `АН/ПР/ТС/ОПЭ ч` — read-only если `issue_id != NULL`, иначе editable.
- `ОПЭ→АН` — inline-editable slider / number input `0..1` (всегда editable).
- Impact/Risk — read-only для Jira-задач, editable для ручных.
- Prio — всегда editable (локальное поле).
- Кнопка **«+ Идея вручную»** → Modal с полями: `title`, `project`, `year/quarter`, оценки 4, ratio, impact, risk. `issue_id = NULL`.
- Действие **«Связать с Jira»** (только для ручных) → Modal с `jira_key` → `POST /backlog/{id}/link-jira`.
- Действие **«Обновить с Jira»** (только для Jira-задач) → `POST /backlog/refresh-from-jira?year=X&quarter=Y` (batch).
- Drag-and-drop для приоритета — **сохраняем существующий**.

### Страница «Сценарии» (`/planning`) — redesign

**Основной layout:** grid `1fr 460px`, `gap:16`.

**Левая колонка — бэклог:**
- Card «Бэклог идей на Q{N} {YEAR}», extra: «отсортировано по приоритету · оценка по ролям: АН / ПР / ТС / ОПЭ».
- Header-row: `40px | 60px | 1fr | 200px | 75px | 100px | 95px` — `✓`, `Prio`, `Идея + ID`, `АН/ПР/ТС/ОПЭ (bar)`, `Всего`, `Impact`, `Risk`.
- Строка:
  - Checkbox (включить в сценарий)
  - Prio badge (топ-3 — cyan, остальные — серый)
  - Название + Jira-ключ (ссылка)
  - **Breakdown bar** — горизонтальная цветная полоса 4 сегментов (АН/ПР/ТС/ОПЭ) пропорционально часам + правее числами `a/d/q/o`
  - Всего = сумма
  - Impact / Risk — Tag
  - Если при выборе задачи любая роль уходит в перегруз — tooltip «не влезает по ролям» + tinted background оранжевым.
  - Невыбранные — `opacity: 0.75`.

**Правая колонка (sticky, top:16):**

1. **Card «Ёмкость команды · Q{N}»** — крупно `plan / capacity ч`, CapacityBar; подпись «Запас N ч · M% свободно» или «Перегруз по ролям — см. ниже».

2. **Card «Ёмкость по ролям»** — 3 строки (АН/ПР/ТС):
   - Слева: цветной квадратик + название роли + `· N чел.`;
   - Справа: `demand / capacity ч`;
   - Progress bar с маркером 100% и оранжевой «перегруз»-зоной справа при `demand > capacity`;
   - Footer: `запас/перегруз N ч · загрузка M%`.

3. **Card «Расчёт ёмкости»** — KPI rows:
   - `Производств. календарь РФ: NN + NN + NN = NNN раб.дн`
   - `NN сотр. × 8 ч/день: XXX ч брутто`
   - `− Отпуска: −XX ч`
   - `− Обязат. работы: −XX ч`
   - `Доступно для бэклога: XXX ч` (strong)
   - Separator + «в разрезе ролей»: 3 строки с цветом и `(N чел · брутто XX ч − обязат. XX ч) → XX ч`

4. **Card «По сотрудникам»** — компактный список:
   - Role badge (АН/ПР/ТС/—) + имя + `отп. N дн` (если есть) + `XX ч`
   - Под ним двухслойная полоса: mandatory (серо-фиолетовый) + available (цвет роли).

5. **Actions:** `[Сохранить сценарий]` (primary, flex:1) + `[Экспорт]`.

**Взаимодействие:**
- Live-расчёт: `useQuery` → `POST /planning/capacity-preview` с `backlog_item_ids = Object.entries(selected).filter(...).map(...)`. `staleTime: Infinity`, триггер по ручному debounce на изменении `selected`.
- «Сохранить сценарий» → `POST /planning/scenarios/generate` с текущим set → редирект на созданный сценарий / toast.
- «Экспорт» — существующий `GET /exports/scenarios/{id}.xlsx` после сохранения.

**Обработка «без роли»:**
Сотрудники с `role` не в `{analyst, dev, qa}` не попадают в `capacity_by_role`. Показываем отдельной строкой внизу «По сотрудникам» с подписью «роль не задана — не учитывается в сценарии» (серая).

### Цвета (constants.ts)

```ts
export const ROLE_COLORS = {
  analyst: '#4db8e8',
  dev:     '#00c9c8',
  qa:      '#EF9F27',
  opo:     '#7F77DD',
};
export const ROLE_LABELS = {
  analyst: 'Аналитик',
  dev:     'Программист',
  qa:      'Тестировщик',
  opo:     'Запуск (ОПЭ)',
};
export const ROLE_SHORT = {
  analyst: 'АН', dev: 'ПР', qa: 'ТС', opo: 'ОПЭ',
};
```

## Миграции

Одна миграция `019_backlog_planning_chain.py`:
1. Add columns к `issues`: 4 planned_*_hours, 4 involvement_*, 4 duration_*, impact, risk.
2. Add columns к `backlog_items`: `issue_id`, 4 estimate_*_hours, `opo_analyst_ratio`, `impact`, `risk`. `issue_id UNIQUE` (batch mode).
3. INSERT seed `categories` (`initiatives_backlog`, …) — использовать `INSERT OR IGNORE` (SQLite) / `ON CONFLICT DO NOTHING` (PostgreSQL через SQLAlchemy Core).
4. INSERT 14 seed ключей в `app_settings` с пустым `value` — для последующей настройки в UI.

Batch mode для SQLite.

## Edge cases

1. **Issue теряет категорию `initiatives_backlog`** → если BacklogItem не в сценариях → удаляется; иначе `issue_id=NULL`.
2. **Issue deleted from Jira** (отсутствует в следующем sync) — не трогаем BacklogItem автоматически (нет сигнала «deleted», инкрементальный sync не ловит это). Ручная очистка через UI.
3. **PM уже создал BacklogItem вручную с estimate_analyst_hours=X, потом привязал к Jira через `/link-jira`** → `sync_from_issue` перетирает X значением из Jira. Документируем в tooltip модалки «Связать с Jira»: «Локальные оценки будут заменены значениями из Jira».
4. **Employee.role не задан** → сотрудник не попадает в capacity, но его ворклоги (если есть) считаются фактом. Пользователь видит предупреждение.
5. **BacklogItem без `year/quarter`** (созданный при синке, когда defaults не проставлены) → не появляется в `/planning` за какой-либо квартал; висит в `/backlog` с фильтром «все». PM проставляет вручную.
6. **Массовая замена категории** в CategoryConfigTab на `initiatives_backlog` → триггер `sync_from_issue` для каждой затронутой задачи. Добавляем в `issue_config.set_issue_category` и `batch_category` вызов `BacklogService.sync_from_issue` после commit.
7. **`Category.is_system` vs user-editable** — seed категории `initiatives_backlog` с `is_system=True` (сейчас все seed-категории системные, нельзя удалить через API).

## Тестирование

### Backend (pytest)

Новые файлы:
- `tests/test_backlog_sync.py` — `BacklogService.sync_from_issue` для 4 сценариев (create, update, unlink, delete).
- `tests/test_api_backlog_link.py` — `/link-jira`, `/unlink-jira`, `/refresh-from-jira`.
- `tests/test_planning_role_allocation.py` — греда с per-role capacity, ОПЭ split, перегруз.
- `tests/test_capacity_role.py` — `team_role_capacity` с разными `Employee.role`.

Обновляем:
- `tests/test_sync_service.py` — новые customfields в `_extract_*`.
- `tests/test_api_planning.py` — новый `/capacity-preview` endpoint.

### Frontend

Добавляем в `frontend/e2e/crud-flows.spec.ts` сценарий:
1. Создать ручную идею → проверить что она в бэклоге
2. Связать с Jira (мок) → оценки перезаписались
3. Открыть `/planning` → переключить чекбоксы → capacity live-обновляется

## Субагенты и ревью

Декомпозиция на 4 батча:

**Batch 1 — Data model + Jira sync (backend-only):**
1. Миграция 019 (+ seed категории + seed AppSetting ключей).
2. `Issue` новые колонки + sync extraction.
3. `BacklogItem` новые колонки.
4. Тесты sync extraction.

**Batch 2 — Backlog service + API (backend-only):**
5. `BacklogService.sync_from_issue` + триггеры из issue_config.
6. `/backlog/{id}/link-jira`, `/unlink-jira`, `/refresh-from-jira`.
7. `GET/POST/PATCH /backlog` — новые поля.
8. Тесты backlog sync.

**Batch 3 — Capacity + Planning (backend):**
9. `CapacityService.team_role_capacity`.
10. `PlanningService.generate_scenario` — per-role allocation.
11. `POST /planning/capacity-preview`.
12. Тесты capacity + planning role.

**Batch 4 — Frontend:**
13. Меню reorder.
14. `JiraFieldsCard` расширение.
15. Employee role dropdown.
16. Страница `/backlog` — новые колонки, manual modal, link-to-jira, refresh.
17. Страница `/planning` — redesign полностью под прототип.
18. Constants.ts — ROLE_COLORS.
19. E2E сценарий.

После каждого батча: запуск `pytest` / `npm run lint && npm run build` / e2e → `code-reviewer` subagent → исправления → commit + push в `main` (per user feedback).

## Риски и митигации

| Риск | Митигация |
|---|---|
| Jira customfield IDs неизвестны на момент релиза | Все поля optional, sync просто пропускает если ID не задан. PM настраивает в Settings после деплоя. |
| Большой объём изменений (~18 задач) → риск регрессий | Разбиение на 4 батча с тестами и ревью между ними; commit/push после каждого. |
| `Employee.role` — free-text сейчас, в dev-БД могут быть произвольные значения | `team_role_capacity` фильтрует по whitelist. Показываем warning в UI. |
| ОПЭ ratio per-task = дубль если Jira добавит своё поле | Задокументировано в tooltip; при появлении Jira-поля — миграция переключит источник. |
| Логика «когда категория ушла» может удалить BacklogItem в середине планирования | Soft unlink если есть `ScenarioAllocation`; иначе удаление. Документируем в release notes. |
