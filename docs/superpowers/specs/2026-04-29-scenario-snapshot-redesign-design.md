# Scenario Snapshot Redesign — Design

**Дата:** 2026-04-29
**Тема:** Полный пересмотр snapshot-модели ревизии сценария квартального планирования

---

## 1. Цели

### A. Аудит истории сценария

Для каждой ревизии хранить полный снимок входов и результатов расчёта на момент утверждения, чтобы в любой момент в будущем можно было:
- увидеть «что именно утверждали 25 апреля» (состав команды, правила, allocations, часы)
- сравнить две ревизии: что добавили/удалили, как изменились ресурсы, правила, часы

### B. План/факт по утверждённой версии

Хранить достаточно данных для воспроизведения расчёта плана и сопоставления с фактом по любому срезу:
- по сотрудникам × месяцам
- по ролям × месяцам
- по видам работ (нормированные)
- по элементам бэклога × месяцам × ролям

### Не цели (вне scope)

- Откат сценария к произвольной ревизии (`restore`) — не нужен
- Конкретные виджеты на основе snapshot — будут проработаны позже
- Распределение dev/qa-часов по конкретным сотрудникам — отдельный этап «Ресурсное планирование», не блокирует этот redesign

---

## 2. Текущее состояние и проблемы

### Что есть сейчас

| Таблица | Содержимое | Гранулярность |
|---|---|---|
| `scenario_revisions` | id, revision_number, approved_at, note | по ревизии |
| `scenario_capacity_snapshots` | norm_hours, available_hours, backlog_pool_hours (всегда NULL) | сотрудник × месяц |
| `scenario_norm_snapshots` | norm_hours = pct × календарь | сотрудник × месяц × вид работ |
| `scenario_absence_snapshots` | start, end, reason, hours_total | строка отсутствия |
| `scenario_revision_items` | backlog_item_id + action (added/removed) | элемент бэклога |

### Проблемы

1. **`scenario_norm_snapshots` считает неверно.** Хранит `493 ч × pct` для каждого сотрудника без вычета отсутствий. Также не учитывает `external_qa_hours` сценария. Пример: на Q2 2026 для сценария «Q2 2026 plan» дашборд показывает план 1898 ч, а live-расчёт страницы «Сценарии» — 1997 ч (разница 99 ч из-за отсутствий и внешнего QA).
2. **Не фиксируется состав команды** — список сотрудников и их роли мутируют (`employee_teams`, `Employee.role`); ревизия теряет связи.
3. **Не фиксируются правила сценария** — `scenario_rules` мутируют; правки правил искажают трактовку прошлых ревизий.
4. **Не фиксируется производственный календарь** — `production_calendar_day` мутирует (например, синхронизация официального календаря задним числом); расчёт нельзя воспроизвести точно.
5. **Не фиксируется `external_qa_hours`** сценария.
6. **Не фиксируются utверждённые allocations** — `scenario_allocations` мутирует. Ревизия знает только `action='added'/'removed'`, не часы и не атрибуты бэклог-элементов.
7. **Нет помесячного распределения allocations.** Бэклог-элемент = «общая сумма часов на квартал». Сравнить план с фактом помесячно невозможно.
8. **Нет снимка справочников** (`mandatory_work_types`, `roles`, `absence_reasons`). Удаление/переименование вида работ ломает старые ревизии.

---

## 3. Новая snapshot-модель

### 3.1. Расширение `scenario_revisions`

Добавляются столбцы:

- `parent_revision_id VARCHAR(36) NULL` — ссылка на предыдущую ревизию того же сценария (для diff). NULL для первой ревизии.
- `approved_by_user_id VARCHAR(36) NULL` — кто утвердил (FK на `users`).
- `algo_version VARCHAR(16) NOT NULL DEFAULT 'v1'` — версия алгоритма расчёта на момент создания ревизии. Позволяет в будущем менять формулы без потери трактовки старых ревизий.

Существующие поля (`id`, `scenario_id`, `revision_number`, `approved_at`, `note`, `created_at`, `updated_at`) сохраняются без изменений.

### 3.2. `scenario_team_snapshots` (новая)

Состав команды на момент утверждения. Один сотрудник = одна строка.

| Поле | Тип | Описание |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `revision_id` | VARCHAR(36) FK | → `scenario_revisions.id` |
| `employee_id` | VARCHAR(36) | оригинальный id (не FK — может быть удалён) |
| `display_name` | VARCHAR(255) | копия |
| `role` | VARCHAR(50) | копия `Employee.role` на момент утверждения |
| `hours_per_day` | FLOAT | копия (если поле есть в `Employee` — иначе 8.0 по умолчанию) |
| `is_active` | BOOLEAN | копия |
| `is_external` | BOOLEAN | для пометки внешнего ресурса (зарезервировано на будущее) |

Индекс по `(revision_id, role)`.

### 3.3. `scenario_calendar_snapshots` (новая)

Производственный календарь квартала на момент утверждения, **per-day**. ~90 строк × ревизия.

| Поле | Тип |
|---|---|
| `id` | VARCHAR(36) PK |
| `revision_id` | VARCHAR(36) FK |
| `date` | DATE |
| `hours` | FLOAT |
| `is_workday` | BOOLEAN |
| `kind` | VARCHAR(32) — `workday` / `holiday` / `pre_holiday` / `weekend` |

Уникальный `(revision_id, date)`.

### 3.4. `scenario_absence_snapshots` (существующая, без изменений)

Уже хранит копии отсутствий за период квартала. Оставляем как есть.

### 3.5. `scenario_rules_snapshots` (новая)

Снимок `scenario_rules` на момент утверждения.

| Поле | Тип |
|---|---|
| `id` | VARCHAR(36) PK |
| `revision_id` | VARCHAR(36) FK |
| `role` | VARCHAR(50) |
| `work_type_id` | VARCHAR(36) — снапшот, не FK |
| `work_type_label` | VARCHAR(255) — копия для readability |
| `pct_of_norm` | FLOAT |

Уникальный `(revision_id, role, work_type_id)`.

### 3.6. `scenario_capacity_snapshots` (расширить, без удаления старых полей)

Добавляем новые поля; старые сохраняем как deprecated для совместимости с v1-ревизиями.

| Поле | Тип | Статус | Описание |
|---|---|---|---|
| `id`, `revision_id`, `employee_id`, `employee_name`, `year`, `month` | — | без изменений | |
| `norm_hours` | FLOAT | **deprecated в v2** (заполняется = `gross_hours` для v2 ради совместимости) | старое поле, читалось как «брутто календарь» |
| `available_hours` | FLOAT | **смысл уточняется** | `gross_hours − absence_hours` (в v1 было то же самое) |
| `backlog_pool_hours` | FLOAT NULL | **deprecated** (всегда NULL и в v1, и в v2) | удалится в отдельной миграции через 1 release |
| `gross_hours` | FLOAT | **новое** | сумма `production_calendar_day.hours` за месяц × коэф. `hours_per_day / 8` |
| `absence_hours` | FLOAT | **новое** | часы отсутствий сотрудника в этом месяце |
| `mandatory_hours` | FLOAT | **новое** | сумма часов нормированных работ за месяц (после применения правил) |
| `project_hours` | FLOAT | **новое** | `available_hours − mandatory_hours` |

Уникальный `(revision_id, employee_id, year, month)`.

При чтении v1-ревизии: `gross_hours = norm_hours`, `absence_hours/mandatory_hours/project_hours = NULL` (helper-методы возвращают `None` → потребитель решает что показывать).

### 3.7. `scenario_norm_snapshots` (исправить расчёт)

Структура **остаётся прежней** (`employee_id × month × work_type_id → norm_hours`), но логика заполнения исправляется.

#### Для штатных сотрудников

`norm_hours = available_hours_emp_month × pct_role_work_type / 100`

где `available_hours_emp_month` уже учитывает отсутствия (берётся из 3.6).

#### Для внешнего QA

Если у сценария задано `external_qa_hours = X`:

- роль `qa` рассматривается как «виртуальный сотрудник» с `available_hours[month] = X / 3` (равномерный split по 3 месяцам квартала)
- для каждого вида работ, у которого есть правило для роли `qa`: `norm_hours = (X / 3) × pct / 100`
- строки добавляются с `employee_id = NULL`, `is_external = TRUE`

Если `external_qa_hours = NULL` (внешний QA не задан) и в команде есть штатные QA — расчёт идёт обычным способом по их `available_hours` (как для других ролей).

Если `external_qa_hours = NULL` и штатных QA в команде нет — строки для роли `qa` не создаются.

#### Новые столбцы

- `is_external BOOLEAN DEFAULT FALSE`

Уникальность ключа меняется на `(revision_id, employee_id, year, month, work_type_id, is_external)` — чтобы внешний QA (employee_id=NULL) и штатный (employee_id=...) могли сосуществовать без конфликта (хотя на практике это либо/либо).

### 3.8. `scenario_allocation_snapshots` (новая)

Список утверждённых allocations с копиями всех полей бэклог-элемента и сценария.

| Поле | Тип | Описание |
|---|---|---|
| `id` | VARCHAR(36) PK | |
| `revision_id` | VARCHAR(36) FK | |
| `allocation_id` | VARCHAR(36) | оригинальный id |
| `backlog_item_id` | VARCHAR(36) | оригинальный id (не FK) |
| `sort_order` | FLOAT | |
| `included_flag` | BOOLEAN | |
| `involvement_coefficient` | FLOAT | |
| `title` | TEXT | копия `backlog_items.title` |
| `issue_id` | VARCHAR(36) NULL | копия |
| `project_id` | VARCHAR(36) NULL | копия |
| `customer` | TEXT NULL | копия |
| `cost_type` | VARCHAR(50) NULL | копия |
| `impact` | VARCHAR(20) NULL | копия |
| `risk` | VARCHAR(20) NULL | копия |
| `priority` | INTEGER NULL | копия |
| `estimate_analyst_hours` | FLOAT NULL | копия |
| `estimate_dev_hours` | FLOAT NULL | копия |
| `estimate_qa_hours` | FLOAT NULL | копия |
| `estimate_opo_hours` | FLOAT NULL | копия |
| `opo_analyst_ratio` | FLOAT NULL | копия |
| `assignee_employee_id` | VARCHAR(36) NULL | копия `backlog_items.assignee_employee_id` на момент утверждения |
| `assignee_role_at_approval` | VARCHAR(50) NULL | роль assignee на момент утверждения (для трактовки `analyst` vs `consultant`) |

Индекс по `revision_id`.

### 3.9. `scenario_allocation_breakdown_snapshots` (новая)

Помесячный сплит часов allocation по ролям и сотрудникам. **Под капотом**: пользователь утверждает квартальные суммы, snapshot раскладывает их.

| Поле | Тип | Описание |
|---|---|---|
| `id` | VARCHAR(36) PK | |
| `revision_id` | VARCHAR(36) FK | |
| `allocation_id` | VARCHAR(36) | |
| `month` | INTEGER (1..12) | |
| `role` | VARCHAR(50) — `analyst`/`dev`/`qa`/`consultant`/`RP` | |
| `employee_id` | VARCHAR(36) NULL | заполнено для AN/RP/Cons; NULL для dev (пул роли) и QA |
| `is_external` | BOOLEAN | TRUE для qa если у сценария `external_qa_hours` задан |
| `hours` | FLOAT | часы плана для этой комбинации |

Уникальный `(revision_id, allocation_id, month, role, employee_id, is_external)`.

#### Алгоритм автосплита (под капотом, фиксируется в snapshot)

Применяется при создании новой ревизии:

1. Для каждой allocation вычисляются часы по ролям:
   - `analyst_or_consultant_hours = estimate_analyst_hours + estimate_opo_hours × opo_analyst_ratio` → роль определяется по `assignee.role` на момент утверждения:
     - если `assignee.role = analyst` → роль `analyst`, employee_id = assignee.id
     - если `assignee.role = consultant` → роль `consultant`, employee_id = assignee.id
     - если `assignee_employee_id = NULL` или роль не входит в `{analyst, consultant}` → роль `analyst` (по умолчанию), employee_id = NULL (висит как «не назначено»)
   - `rp_hours = estimate_opo_hours × (1 − opo_analyst_ratio)` → роль `RP`, employee_id = единственный сотрудник команды с ролью `RP`
   - `dev_hours = estimate_dev_hours` → роль `dev`, employee_id = NULL (пул роли)
   - `qa_hours = estimate_qa_hours` → роль `qa`, employee_id = NULL, is_external = (`external_qa_hours IS NOT NULL`)

2. Каждая ролевая сумма раскладывается по месяцам пропорционально `available_hours[month]` соответствующей роли в команде:
   - для AN/Cons/RP с известным employee_id — `available_hours[month]` конкретного assignee из 3.6
   - для AN/Cons без employee_id (assignee удалён или роль не подходит) — равномерный split по числу месяцев квартала
   - для dev — суммарный `available_hours[month]` всех активных dev команды
   - для qa штатного — суммарный `available_hours[month]` всех активных qa
   - для qa внешнего — равномерно `qa_hours / число_месяцев`

3. Результаты округляются до 0.01 ч; финальная корректировка последнего месяца компенсирует ошибку округления, чтобы сумма помесячных часов точно совпадала с квартальной.

#### Edge cases

- **0 РП в команде** — `rp_hours` пишется со строкой `employee_id = NULL`, роль `RP`. Это сигнал «не назначено». UI/diff показывает предупреждение.
- **>1 РП в команде** — берётся первый по сортировке `display_name`. Запись о выборе попадает в лог утверждения (`scenario_revisions.note` или отдельный лог; можно опустить в MVP).
- **0 dev в команде, но `estimate_dev_hours > 0`** — пишется строка `employee_id = NULL`, роль `dev`, `is_external = FALSE`. Диагностический сигнал.
- **assignee_employee_id ссылается на уволенного/удалённого сотрудника** — копируем как есть в snapshot (`assignee_employee_id` сохраняется), но `assignee.role` берётся из `scenario_team_snapshots` если есть, иначе из живой `Employee` (если запись ещё жива), иначе NULL.
- **Деление на ноль при пропорциональном split** — если суммарный `available_hours` нулевой (вся команда в отпуске месяц) — fallback на равномерный split.

Алгоритм работает только при создании ревизии. Конкретные часы фиксируются в `scenario_allocation_breakdown_snapshots`, после чего более не пересчитываются.

### 3.10. `scenario_dictionary_snapshots` (новая, единая)

Снимки справочников на момент утверждения — для readability при удалении/переименовании оригинала.

| Поле | Тип | Описание |
|---|---|---|
| `id` | VARCHAR(36) PK | |
| `revision_id` | VARCHAR(36) FK | |
| `kind` | VARCHAR(32) — `work_type` / `role` / `absence_reason` | |
| `original_id` | VARCHAR(36) | id оригинальной записи |
| `code` | VARCHAR(64) NULL | для ролей |
| `label` | VARCHAR(255) | |
| `sort_order` | INTEGER NULL | |
| `extra_json` | JSON NULL | дополнительные атрибуты (`subtracts_from_pool` для work_type и т.п.) |

Уникальный `(revision_id, kind, original_id)`.

---

## 4. Удаление ревизии

### Endpoint

`DELETE /planning/scenarios/{scenario_id}/revisions/{revision_id}`

### Поведение

- Каскадное удаление всех snapshot-таблиц по `revision_id`:
  - `scenario_team_snapshots`
  - `scenario_calendar_snapshots`
  - `scenario_absence_snapshots`
  - `scenario_rules_snapshots`
  - `scenario_capacity_snapshots`
  - `scenario_norm_snapshots`
  - `scenario_allocation_snapshots`
  - `scenario_allocation_breakdown_snapshots`
  - `scenario_dictionary_snapshots`
  - `scenario_revision_items`
- Сама запись `scenario_revisions` удаляется
- Если у удаляемой ревизии есть `parent_revision_id = X`, то все ревизии у которых `parent_revision_id = удаляемая.id` обновляются: новый `parent_revision_id = X` (re-link)
- Если удаляется последняя оставшаяся ревизия approved-сценария — сценарий переводится в `status='draft'`

### Edge cases

- Удаление промежуточной ревизии — допустимо, цепочка `parent_revision_id` склеивается
- Удаление ревизии, на которую кто-то ссылается из внешних систем — нет таких ссылок (snapshot-таблицы — единственные потребители)
- В UI: подтверждение действия с явным текстом «Это действие необратимо» (не каваман-стиль, обычная человеческая фраза)

### Concurrency

В рамках текущего MVP без блокировок. В multi-user режиме два одновременных удаления одной ревизии — второе вернёт 404 (запись уже удалена). Допустимо.

---

## 5. Diff между ревизиями

### Endpoint

`GET /planning/scenarios/{scenario_id}/revisions/{revision_id}/diff?against={other_revision_id}`

По умолчанию `against = parent_revision_id`. Если параметр явно указан — diff с произвольной ревизией того же сценария.

### Что возвращает (срезы)

- **allocations**:
  - `added`: список allocation_id есть в `revision_id`, нет в `against`
  - `removed`: наоборот
  - `changed`: есть в обеих, но изменились часы (estimate_*, involvement_coefficient) или атрибуты (impact, risk и т.д.). Возвращается `before/after` для каждого изменившегося поля
- **team**:
  - `added` / `removed` сотрудники
  - `role_changed` сотрудники (старая/новая роль)
- **rules**:
  - `added` / `removed` правила (role × work_type)
  - `changed` pct
- **external_qa_hours**: `before/after`
- **calendar/absences**:
  - per-emp × month дельта `available_hours` (если изменились отсутствия или календарь правился задним числом)

### Реализация

Чистое чтение snapshot-таблиц обеих ревизий + сравнение в Python. Никаких пересчётов от живых данных.

---

## 6. Алгоритм заполнения snapshot при утверждении

Когда нажимается «Утвердить» (создаётся новая ревизия):

```
1. Создать запись scenario_revisions с parent_revision_id = id предыдущей ревизии этого сценария.
2. Скопировать состав команды → scenario_team_snapshots.
3. Скопировать производственный календарь Q за квартал сценария → scenario_calendar_snapshots.
4. Скопировать отсутствия команды за период квартала → scenario_absence_snapshots.
5. Скопировать scenario_rules → scenario_rules_snapshots.
6. Посчитать capacity per-emp × month с учётом календаря + отсутствий → scenario_capacity_snapshots
   (gross, absence, available, mandatory, project).
7. Посчитать norm per-emp × month × work_type с учётом available_hours и pct правил → scenario_norm_snapshots
   (для внешнего QA — отдельные строки с employee_id=NULL, is_external=TRUE).
8. Скопировать scenario_allocations и атрибуты backlog_items → scenario_allocation_snapshots
   (только включённые allocations: included_flag=TRUE).
9. Прогнать алгоритм автосплита (раздел 3.9) → scenario_allocation_breakdown_snapshots.
10. Скопировать справочники (work_types, roles, absence_reasons) → scenario_dictionary_snapshots.
11. Записать diff с parent в scenario_revision_items (added/removed allocation_id) — оставить как сейчас,
    он используется UI «История».
```

Все шаги — в одной транзакции. Откат при любой ошибке оставляет БД в консистентном состоянии.

### Версия алгоритма

Все ревизии, создаваемые этим redesign, помечаются `algo_version='v2'`. Ревизии с `algo_version='v1'` (старые) остаются как есть, без обратной миграции — для них видно «считано старым алгоритмом» в API/UI (см. раздел 7).

---

## 7. Миграция

### Подход

**Без backfill.** Старые ревизии (`v1`) не пересчитываются:
- они остаются с старыми snapshot-таблицами в текущем виде
- новый код умеет читать `v1` ревизии в режиме «only-aggregates» (`gross_hours = norm_hours`, `available_hours` уже есть, без `mandatory/project_hours`, без `allocation_breakdown` и т.п.)
- diff между `v1` и `v2` ревизиями ограничен по полноте (часть полей будет пустой), но allocations/team срез доступен

Это решение:
- избегает пересчёта 10+ старых ревизий по неизвестным/устаревшим данным
- сохраняет историческую корректность (v1 — что есть, то есть)
- упрощает миграцию: только структурные изменения схемы

### Шаги миграции (Alembic)

1. Создать новые таблицы: `scenario_team_snapshots`, `scenario_calendar_snapshots`, `scenario_rules_snapshots`, `scenario_allocation_snapshots`, `scenario_allocation_breakdown_snapshots`, `scenario_dictionary_snapshots`.
2. Расширить `scenario_revisions`: добавить `parent_revision_id`, `approved_by_user_id`, `algo_version` (default `'v1'` для существующих, новая логика создаёт `'v2'`).
3. Расширить `scenario_capacity_snapshots`: добавить `gross_hours`, `absence_hours`, `mandatory_hours`, `project_hours`. Старое `norm_hours` оставить (для совместимости с v1). Старое `backlog_pool_hours` оставить (NULL у всех v1 и v2 — поле deprecated, удалится в следующей миграции через 1 release).
4. Расширить `scenario_norm_snapshots`: добавить `is_external BOOLEAN DEFAULT FALSE`.
5. Скрипт `link_revisions.py` (одноразовый): для существующих ревизий проставить `parent_revision_id` по упорядочиванию `revision_number` внутри сценария. Запускается вручную или из миграции.

### Совместимость UI

Существующие чтения текущих snapshot-таблиц (страница «Сценарии», виджет дашборда) **не ломаются** — старые поля остаются. Виджеты будут редизайниться позже отдельно, поэтому здесь только обеспечиваем что API-ответы старого вида работают как сейчас.

---

## 8. API изменения

### Новые

- `DELETE /planning/scenarios/{sid}/revisions/{rid}` — удаление
- `GET /planning/scenarios/{sid}/revisions/{rid}/diff?against={rid2}` — diff
- `GET /planning/scenarios/{sid}/revisions/{rid}/breakdown` — допуск «под капот»: возвращает `scenario_allocation_breakdown_snapshots` для дебага

### Изменённые

- `GET /planning/scenarios/{sid}/revisions/{rid}` — добавляет в ответ:
  - `algo_version`
  - `parent_revision_id`
  - `approved_by_user_id`
  - расширенный `capacity_snapshot` (новые поля: gross/absence/mandatory/project)
  - `team_snapshot`, `rules_snapshot`, `allocation_snapshot` (списки)

### Без изменений

- Создание ревизии (`POST /planning/scenarios/{sid}/approve`) — внутренняя логика расширяется, контракт сохраняется.

---

## 9. Открытые мелочи и риски

### Производительность

- Snapshot per-day календаря = ~90 строк × ревизия. Для сценария за год это ~360 строк × ревизию. Учитывая 10 ревизий — ~3600 строк. Допустимо для SQLite/PostgreSQL.
- `scenario_allocation_breakdown_snapshots` ≈ 100 allocations × 3 месяца × 5 ролей × 6 сотрудников = ~9000 строк × ревизия в худшем случае. Лимит SQLite — миллиарды строк, ОК.

### Удаление справочников

- Если удалена `MandatoryWorkType`, на которую ссылаются live `scenario_rules` — текущая логика блокирует удаление (FK). Snapshot хранит копию label, поэтому отображение продолжит работать после удаления оригинала.

### Консистентность при сбое

- Все snapshot-вставки в одной транзакции при `approve` — если упало что-то, ревизия не создаётся вообще.
- Удаление ревизии — тоже в транзакции (каскад).

### Multi-user

- Утверждение сценария двумя пользователями одновременно: PostgreSQL (будущий target) — через row-level lock на `planning_scenarios`. SQLite (MVP) — через app-level lock или просто optimistic (последний победил, обе ревизии создаются с разными `revision_number`). Допустимо.

---

## 10. Что в scope этого спека

✅ Расширение `scenario_revisions` (parent, approved_by, algo_version)
✅ Новые таблицы snapshots (team, calendar, rules, allocation, allocation_breakdown, dictionary)
✅ Переделка `scenario_capacity_snapshots` (gross/absence/available/mandatory/project)
✅ Исправление логики `scenario_norm_snapshots` (учёт отсутствий + external_qa)
✅ Алгоритм автосплита allocations по месяцам и ролям
✅ API создания ревизии с заполнением всех snapshot
✅ API удаления ревизии (каскад + сценарий → draft если последняя)
✅ API diff между ревизиями
✅ API «под капот» для отладки
✅ Миграция Alembic (без backfill старых ревизий)

## 11. Что НЕ в scope

❌ Виджеты дашборда / страницы аналитики на основе snapshot — отдельный redesign позже
❌ Распределение dev/qa-часов по конкретным сотрудникам — этап «Ресурсное планирование», отдельный спек
❌ Откат сценария к произвольной ревизии (`restore`)
❌ Backfill v1 → v2
