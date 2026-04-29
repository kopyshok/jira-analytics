# app/services — бизнес-логика

Async где возможно. Type hints везде. Docstrings на русском для бизнес-логики. **Сервисы коммитят сами** — тесты должны чистить таблицы (см. [tests/CLAUDE.md](../../tests/CLAUDE.md)).

## CategoryResolver ([category_resolver.py](category_resolver.py))

Приоритет: `category_overrides` → ближайший `scope_roots` (walk up `parent_id`) → `worklog_quality_rules` → fallback. Worklog наследует категорию своей задачи.

## MappingService ([mapping_service.py](mapping_service.py))

Идемпотентно пересчитывает таблицу `category_mappings` и денормализованное `Issue.category`. Commits internally.

## CapacityService ([capacity_service.py](capacity_service.py))

Базовые ресурсы сотрудника — единственная формула:
- `available_hours = max(0, norm_hours − absence_hours)`
- `mandatory_hours = 0` (поле в ответе для backward compat)

`norm_hours` — сумма `production_calendar_day.hours` за период (8ч будни, 7ч предпраздничные, 0 выходные/праздники), масштабируется на `hours_per_day / 8`. Если в БД нет записи — fallback на `hours_per_day` для Пн–Пт (источник: `ProductionCalendarService`).

`absence_hours` — тот же расчёт по дням отсутствий (`Absence.reason_id` → `absence_reasons`), перекрытие через `max(start, period_start)` / `min(end, period_end)`.

`fact_hours` — сумма `Worklog.hours` сотрудника за период; даёт plan/fact %.

Quarter mapping: `QUARTER_MONTHS = {1:(1,2,3), 2:(4,5,6), 3:(7,8,9), 4:(10,11,12)}`.

`role_capacity_rules` / `employee_capacity_overrides` / `Category.work_type_id` — **шаблоны для новых сценариев**. В Team-tab расчёте не участвуют (см. `ScenarioRule` и `ResourceBaseService`).

## ResourceBaseService ([resource_base_service.py](resource_base_service.py))

Посуточная база ресурса команды для сценария. Для каждого сотрудника команды считает доступные «проектные» часы на каждый рабочий день квартала: вычитает дни отсутствия и процент нормы, занятый обязательными работами (только `subtracts_from_pool=True` work types).

Используется в `/planning/scenarios/{id}/resource` (посуточная матрица) и `/resource-summary` (разбивка по ролям × work_types).

## EmployeeTeamService ([employee_team_service.py](employee_team_service.py))

CRUD для M:N `employee_teams`. API: `list_teams`, `add_team`, `remove_team`, `set_primary`, `replace_teams`. Инвариант: ровно одна `is_primary=true` строка на сотрудника (enforce в сервисе, не в БД — SQLite не поддерживает partial unique). Поле `Employee.team` — derived, обновляется через `_recompute_legacy_team`. Авто-определение команды (`auto_detect_team` / `auto_detect_all_missing`) пишет в primary membership через тот же сервис.

## ExportService ([export_service.py](export_service.py))

`openpyxl` / `reportlab` / `pptx` — **lazy import внутри методов**, чтобы missing library не ломала module import. Analytics exports переиспользуют `AnalyticsService`. Scenario xlsx — отдельный модуль [scenario_xlsx_export.py](scenario_xlsx_export.py) («Бухгалтерия»: 4 листа — Сводка / Включено / Не вошло / Справочник).

## PlanningService ([planning_service.py](planning_service.py))

**Тонкий helper, не оркестратор.** Раньше содержал greedy auto-allocation `generate_scenario` — удалён. Теперь только `_team_capacity_hours(year, quarter)` и `_demand_by_role(item)` — используются `ExportService` для шапки scenario.xlsx / pptx.

Реальный flow сценария — ручные галочки в endpoints (см. [app/api/CLAUDE.md](../api/CLAUDE.md) Scenario flow).

## SyncService ([sync_service.py](sync_service.py))

Dependency order: Projects → Issues (need projects) → Worklogs (need issues + auto-create employees).

Incremental sync через `sync_state.last_sync` per entity; JQL `updated >= "timestamp" ORDER BY updated ASC` для дельт. Rate limiting: 100ms delay между requests + exponential backoff на HTTP 429. Batch size: 100 issues per Jira API request.

**Custom field extraction (`sync_issues`):** читает `jira_team_field_id`, `jira_participating_teams_field_id`, `jira_goals_field_id` из AppSetting, добавляет к `fields=` в каждом Jira request. Values попадают в `JiraIssueFieldsSchema._extra`. Helper `_extract_team_values(extra, field_id)` обрабатывает три формы (`{value: X}`, `[{value: X}, ...]`, plain string), питает team + goals. Пишется в `Issue.team` (первое значение), `Issue.participating_teams` (JSON list), `Issue.goals` (comma-joined). `null` → `team=None`, `participating_teams='[]'`, `goals=None`.

`_upsert_issue` также захватывает `status_category` из `status.statusCategory.key` и `status_changed_at` из `statuscategorychangedate` (parsed `_parse_jira_datetime` → naive UTC).

**Targeted refresh:** `refresh_issues_by_keys(jira_keys)` перечитывает keys в JQL `key in (...)` батчами по 100 через `iter_issues`, skip unknowns, переиспользует `_upsert_issue`.

### Worklog sync — два независимых прохода

- **Bucket A — issue-centric:** JQL `updated >= since`, upsert по локально существующим Issue. Ловит back-dated ворклоги через переход с `worklogDate` на `updated` — Jira двигает `issue.updated` при добавлении любого ворклога, включая записи с прошлым `started`.
- **Bucket B — employee-centric** (активируется параметром `teams`): для каждого Employee из `employee_teams.team IN teams` запускается JQL `worklogAuthor = <account> AND updated >= since`. Незнакомые Issue создаются с `out_of_scope=True`, их Project тоже автосоздаётся (без scope). Вне-scope задачи не попадают в CategoryConfigTab/дерево, но ворклоги видны в Capacity/Analytics.

## SnapshotWriter ([snapshot_writer.py](snapshot_writer.py))

Заполняет все snapshot-таблицы при создании ревизии сценария (`POST /scenarios/{id}/approve`). Один экземпляр = один проход. Методы: `write_team_snapshot`, `write_calendar_snapshot`, `write_rules_snapshot`, `write_dictionary_snapshot`, `write_capacity_snapshot`, `write_norm_snapshot`, `write_allocation_snapshot`, `write_allocation_breakdown`. Все добавляют строки в сессию; commit делает вызывающий код. Ревизии, созданные через writer, помечаются `algo_version='v2'`. Старые v1-ревизии не пересчитываются.

Algo notes:
- `write_capacity_snapshot` считает `gross/absence/available/mandatory/project` per emp×month с учётом отсутствий и правил роли.
- `write_norm_snapshot` использует `available_hours × pct/100` (НЕ gross), внешний QA — отдельные строки `employee_id=NULL, is_external=TRUE` с равномерным split `external_qa_hours / 3`.
- `write_allocation_breakdown` — авто-сплит часов allocation по месяцам и ролям пропорционально `available_hours`. Для AN/Cons — на assignee; для RP — на единственного РП команды (alphabetical first если несколько); для dev/qa — пул роли (`employee_id=NULL`); для внешнего QA — равномерно. Edge cases: 0 РП, 0 dev, удалённый assignee → строка с `employee_id=NULL`.

## SnapshotDiffer ([snapshot_differ.py](snapshot_differ.py))

Diff между двумя ревизиями того же сценария. Срезы: allocations (added/removed/changed), team (added/removed/role_changed), rules (added/removed/changed), external_qa_total_hours (before/after), capacity_changes (per emp×month available_hours delta). Чистое чтение snapshot-таблиц.

## AnalyticsService ([analytics_service.py](analytics_service.py))

Hours by-{employee | project | category | period} + dashboard widgets + context-switching. Все запросы фильтруют по двумерному team filter (employee OR issue) — см. `FactFilterProvider` на фронте.

## BacklogService ([backlog_service.py](backlog_service.py))

CRUD + refresh-from-jira. **Auto-sync `initiatives_rfa`:** задачи в категории `initiatives_rfa` автоматически создают/удаляют allocations в draft-сценариях (двусторонний sync, см. memory `project_auto_backlog_scenarios_sync_shipped`).

Lifecycle через `archived_at` — вкладки Активные / В работе / Архив (заменяет soft-unlink).

## ProductionCalendarService ([production_calendar_service.py](production_calendar_service.py))

Per-day часы для RU календаря. `POST /production-calendar/sync` тянет официальный календарь (см. [app/connectors/CLAUDE.md](../connectors/CLAUDE.md) production-calendar).
