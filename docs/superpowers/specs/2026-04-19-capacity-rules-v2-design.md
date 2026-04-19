# Capacity Rules v2 — Mandatory Work Directory + Role Rules + Employee Overrides

Date: 2026-04-19
Status: approved, ready for implementation

## Problem

Текущая `MonthlyCapacityRule` — плоская: `year, month, percent_of_norm`. Один глобальный процент для всех сотрудников и всех типов обязательной нагрузки. Не масштабируется: PM хочет

1. вести справочник обязательных работ (Орг. вопросы, Руководство/администрирование, Сопровождение, Технический долг, Технические задачи) и пополнять его вручную,
2. назначать процент времени на каждую роль × тип работ (Программист 10% на тех. долг, Аналитик 15% на орг),
3. перекрывать норму для конкретного сотрудника (Аналитики 10% на орг, но Копышков — 30%).

Batches A и B уже в main: A (7dabfe3) — TeamTab-баги, B (7ccfb8f) — поле `Employee.role` с 5 ролями (programmer, consultant, tester, analyst, project_manager).

## Solution

### Новые модели

**`mandatory_work_types`** — справочник обязательных работ.
- `id` String(36) PK, `code` String(64) unique, `label` String(255), `is_active` bool default True, `sort_order` int default 0.
- TimestampMixin.
- Seed: 5 записей (organizational, management_admin, support_consult, tech_debt, technical_tasks) с русскими label.

**`role_capacity_rules`** — базовое правило per-квартал × роль × тип работ.
- `id`, `year` int, `quarter` int (1..4), `role` String(50) nullable (EMPLOYEE_ROLES или NULL = «для всех ролей» fallback), `work_type_id` FK → mandatory_work_types, `percent_of_norm` Float.
- UniqueConstraint: `(year, quarter, role, work_type_id)` — NULL трактуется как отдельная «роль».
- TimestampMixin.

**`employee_capacity_overrides`** — индивидуальный override.
- `id`, `year`, `quarter`, `employee_id` FK → employees, `work_type_id` FK, `percent_of_norm`.
- UniqueConstraint: `(year, quarter, employee_id, work_type_id)`.
- TimestampMixin.

### Миграция (clean start)

Alembic batch-мигрирует:
1. Drop `monthly_capacity_rules` целиком (data loss — ok, продакшен-данные малоценные глобальные %).
2. Create `mandatory_work_types`, `role_capacity_rules`, `employee_capacity_overrides`.
3. Seed 5 базовых work_types.

### Сервис: `CapacityService.mandatory_percent_for(employee, year, quarter)`

Возвращает `dict[work_type_code, percent]` + `total_percent`.

Приоритет резолвинга per (employee, work_type):
1. `employee_capacity_overrides` для этого emp/wt → взять %.
2. Иначе — `role_capacity_rules(role=employee.role, ...)` → взять %.
3. Иначе — `role_capacity_rules(role=NULL, ...)` (fallback «для всех») → взять %.
4. Иначе — 0.

`mandatory_hours` для месяца считается как `norm_hours_month × total_percent / 100` (то же поведение что раньше, но total_percent теперь агрегирован из квартальных правил). Допущение: квартальный % распределяется равномерно по долям `norm_hours` каждого месяца внутри квартала — это даёт справедливое распределение без новых параметров.

### API

**`/mandatory-work-types`** (новый роутер, стиль `hierarchy-rules`):
- `GET ""` → list (с фильтром `is_active`).
- `POST ""` → create `{code, label, is_active?, sort_order?}`.
- `PATCH "/{id}"` → partial update.
- `DELETE "/{id}"` → delete; если есть связанные rule/override — 409 с instruktsionnym сообщением (возможно soft: is_active=false).
- `POST "/reorder"` → массовое переписывание `sort_order` по списку id.

**`/capacity/role-rules`**:
- `GET ""?year=&quarter=` → список правил для квартала (опционально плоский или `{role: {work_type_code: percent}}` — возвращаю плоский список, frontend сам pivot'ит).
- `POST ""` → create `{year, quarter, role?, work_type_id, percent_of_norm}`.
- `PATCH "/{id}"` → partial update (обычно только `percent`).
- `DELETE "/{id}"` → delete.
- `POST "/copy-to-quarter"` → `{from_year, from_quarter, to_year, to_quarter}` → копия всех правил; при конфликте — 409 с count.

**`/capacity/employee-overrides`**:
- `GET ""?year=&quarter=&employee_id?=` → список.
- `POST ""` → create `{year, quarter, employee_id, work_type_id, percent_of_norm}`.
- `PATCH "/{id}"` → partial.
- `DELETE "/{id}"` → delete.

**Удалить** (clean start):
- Старые `/capacity/rules*` endpoints и хуки `useCapacityRules`, `useAddCapacityRule`, `useRemoveCapacityRule`, `useCopyRules`.

### Frontend: RulesTab полный рефактор

Три nested tabs внутри главного таба «Правила»:

1. **«Обязательные работы»** (directory) — CRUD справочник.
   - Таблица: code, label, is_active switch, sort_order (↑↓ кнопки), действия.
   - Кнопка «+ Добавить работу» → модалка с code/label.
   - При удалении проверяем связи; если есть — предлагаем «деактивировать».

2. **«Правила по ролям»** (role × work_type matrix для квартала) — основной экран.
   - Rows: 5 ролей + строка «Все роли» (role=NULL) сверху как fallback.
   - Columns: активные work_types + колонка «Итого %».
   - Клетки: InputNumber (0..100), autosave on blur, debounced. Пустая = нет правила.
   - Кнопка «Скопировать в следующий квартал».

3. **«Индивидуальные правила»** (overrides) — per-employee table.
   - Плоская таблица: Сотрудник | Роль | work_type | % | базовое % (от role-rule с бейджем), действия.
   - Фильтр по сотруднику (Select) и квартaлу.
   - Подсветка override'ов где % ≠ role-rule %.
   - Кнопка «+ Индивидуальное правило» → выбор сотрудника + work_type + %.

Хуки: `useMandatoryWorkTypes`, `useRoleCapacityRules(year, quarter)`, `useEmployeeCapacityOverrides(year, quarter)`, каждая с mutation-парами (create/patch/delete) + оптимистичные апдейты для InputNumber grid'а.

### Тесты

Backend (pytest):
- `test_mandatory_work_types_crud` — 5 кейсов (list, create, patch, delete-blocked-if-in-use, reorder).
- `test_role_capacity_rules_crud` — 5 кейсов (list, create, patch, delete, copy-to-quarter happy + conflict).
- `test_employee_capacity_overrides_crud` — 4 кейса (list, create, patch, delete).
- `test_capacity_service_mandatory_percent_for` — 4 кейса (только role, только override, override > role, пусто → 0) + 1 кейс fallback на role=NULL.
- `test_capacity_service_quarter_integration` — e2e: create work_type + role-rule + override → GET /capacity/team возвращает ожидаемый `mandatory_hours`.

Frontend: добавляются по месту (smoke через E2E необязателен для MVP).

### Обратная совместимость

- `CategoryBreakdown` (fact-часы) не трогаем.
- `capacity.xlsx` экспорт: план `mandatory_hours` теперь честный per-work-type; разбивку добавим отдельным коммитом (C2, опционально).
- Старые capacity-rule API удаляются — frontend-хуки удаляются вместе с ними, lint проверит что нет висящих ссылок.

### План выпуска

**C1** (один коммит, MVP):
1. Модели + alembic-миграция (drop старой + create 3 новых + seed work_types).
2. `CapacityService.mandatory_percent_for` + апдейт `get_team_capacity` чтобы использовал новый метод.
3. 3 API-роутера с CRUD.
4. Удаление старых `/capacity/rules*` endpoints.
5. RulesTab frontend-рефактор: 3 nested-таба, новые хуки, удаление старого.
6. Тесты pytest.
7. Browser-verify: создать work_type + правило + override, проверить мгновенное отражение в TeamTab plan-часах.
8. Обновить CLAUDE.md (новые таблицы, сервис, endpoints) и memory.

**C2** (опционально, отдельный коммит): разбивка по обязательным работам в `capacity.xlsx` + (возможно) превью в BreakdownTab.
