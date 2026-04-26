# app/api — FastAPI routers

21 router include в `app/api/router.py`. Все эндпоинты под `/api/v1/`.

## Routers

| Prefix | File | Назначение |
|---|---|---|
| `/employees` | `employees.py` | список + create-from-Jira + recalc-active + auto-detect-teams + M:N teams CRUD |
| `/projects` | `projects.py` | GET-only список локально известных проектов |
| `/sync` | `sync.py` | sync triggers (full/projects/issues/teams/worklogs) + browse Jira live (`/jira-projects`, `/jira-epics`, `/jira-fields`, `/jira-issuetypes`, `/jira-teams`) + targeted refresh + SSE-стримы worklog reload/update |
| `/jira` | `sync.jira_router` | алиас для browse Jira (см. выше) |
| `/scope` | `scope.py` | scope projects + roots + category overrides |
| `/analytics` | `analytics.py` | dashboard widgets + hours by-{employee\|project\|category\|period} + context-switching |
| `/mapping` | `mapping.py` | recalculate categories (all / issues / worklogs) |
| `/capacity` | `capacity.py` | absences CRUD + batch + monthly/quarterly capacity + team |
| `/capacity/role-rules` | `role_capacity_rules.py` | GET + batch PUT (атомарная замена + 422 если Σ ≠ 100% по роли) + copy-to-quarter |
| `/capacity/employee-overrides` | `employee_capacity_overrides.py` | GET + batch PUT (partial — только упомянутые сотрудники) |
| `/capacity/absence-reasons` | `absence_reasons.py` | CRUD + reorder |
| `/backlog` | `backlog.py` | CRUD + refresh-from-jira + link/unlink-jira + archive/restore |
| `/planning` | `planning.py` | scenarios CRUD + allocations + rules + revisions + resource base (см. ниже) |
| `/exports` | `exports.py` | analytics.xlsx\|pdf, scenarios/{id}.xlsx\|pptx, capacity.xlsx |
| `/settings` | `settings.py` | `/jira` (GET\|PUT, redacts token) + `/jira/test` + `/generic` (PUT) + `/generic/{key}` (GET) |
| `/categories` | `categories.py` | CRUD; `PUT /{id}` принимает `work_type_id: str \| null` (валидация: MandatoryWorkType существует и активен) |
| `/issues` | `issue_config.py` | tree + per-issue category/include + batch-category |
| `/hierarchy-rules` | `hierarchy_rules.py` | CRUD + reorder |
| `/production-calendar` | `production_calendar.py` | GET + PUT single-day + DELETE manual + `POST /sync` pull RU календарь |
| `/mandatory-work-types` | `mandatory_work_types.py` | CRUD + reorder |
| `/roles` | `roles.py` | CRUD + reorder |

## Паттерны

**CRUD:** GET list + POST create, GET\|PATCH\|DELETE by id (backlog, capacity, scope, categories, absences, hierarchy-rules, production-calendar, roles, mandatory-work-types, absence-reasons).

**Batch:**
- `POST /scope/projects/batch` — add/remove multiple
- `POST /capacity/absences/batch` — one record per `employee_id`
- `PUT /capacity/role-rules/batch?year&quarter` — атомарная замена + 422 если Σ ≠ 100% по роли
- `PUT /capacity/employee-overrides/batch?year&quarter` — partial (только упомянутые)
- `PUT /issues/batch-category` — массовая смена категории по группам кодов; archive codes auto-drop `include_in_analysis`, returned in `archived_ids`

**SSE-стримы прогресса** (events `progress` / `done` / `error` / `cancelled`, cancel через `request.is_disconnected()`):
- `POST /sync/worklogs/update/stream` — upsert-only, безопасен в повседневке. Принимает `{since, teams?}`. Bucket A всегда + Bucket B если teams указан
- `POST /sync/worklogs/reload/stream` — жёсткая перезагрузка: `DELETE WHERE started_at >= since` + перечитать через `worklogDate >=` JQL

**Targeted refresh:** `POST /sync/issues/refresh` с `{jira_keys: [...]}` — re-reads только эти ключи в JQL `key in (...)` батчами по 100, обновляет только локально существующие, skip unknowns. Используется кнопкой «Обновить с Jira» чтобы dot-fill новые поля без 30-минутного полного resync.

## Issue tree (`GET /issues/tree`)

Параметры: `project_keys=A,B&teams=T1,T2` (SQL-filtered, teams OR'd).

**Virtual group nodes** в ответе с `issue_type: 'group'`:
- `__orphans__` — `parent_id` есть, но parent excluded
- `__operations__` — root leaf-type issues без детей per `hierarchy_rules`

**Ancestor context:** parents вне team filter включены с `is_context=true`, frontend рендерит read-only.

Mutations: `PUT /issues/{id}/category`, `PUT /issues/{id}/include`, `PUT /issues/batch-category`.

## Browse Jira (live)

`/sync/jira-projects`, `/sync/jira-epics`, `/sync/jira-fields`, `/sync/jira-teams` — без записи в DB, проксируют Jira с `in_scope` флагами. `/sync/jira-projects?team=X` использует per-project JQL probe (см. `app/connectors/CLAUDE.md` team filter).

## Employees

- `GET /employees` — список
- `POST /employees/from-jira` — Jira user search
- `POST /employees/recalc-active` — пересчёт `is_active`
- `POST /employees/auto-detect-teams` — primary team из ворклогов
- `/employees/{id}/teams` M:N CRUD: GET / POST / PUT / DELETE `/{team}`
- `PUT /employees/{id}/teams/primary` — выбор primary
- `PUT /employees/{id}/team` — legacy deprecated wrapper над `replace_teams`

## Scenario flow (`/planning`)

```
POST /scenarios          → create draft, в allocations все BacklogItem с included_flag=False
                           + копия role_capacity_rules в scenario_rules
PATCH /scenarios/{id}/allocations/{aid}  → toggle included; planned_hours авто
PATCH /scenarios/{id}/allocations/reorder → drag-and-drop порядок
POST  /scenarios/{id}/sync-backlog       → досоздать/удалить allocations при изменении BacklogItem
GET   /scenarios/{id}/rules / PUT       → per-scenario правила обязательных работ
POST  /scenarios/{id}/copy-rules-from-template?year&quarter → перекопировать из RoleCapacityRule
GET   /scenarios/{id}/resource          → посуточная база ресурса команды
GET   /scenarios/{id}/resource-summary  → разбивка по ролям × work_types
POST  /scenarios/{id}/approve           → status='approved' + создать ScenarioRevision (дифф + capacity snapshot)
POST  /scenarios/{id}/revert-to-draft   → status='draft'
GET   /scenarios/{id}/revisions         → история утверждений
```

Approved сценарии редактировать нельзя (409) — сначала revert.

Generic CRUD `/scenarios/{id}` (GET\|PATCH\|DELETE) объявлены последними чтобы не ловить `/rules`, `/approve` и т.д.

## ORM caveat

После `db.commit()` сессия expire-ит атрибуты; обращение триггерит reload на potentially thread-rotated connection (воспроизводится: `:memory:` SQLite + TestClient async endpoints). В endpoints **снимать снимок полей в локали до commit** (см. [issue_config.py](endpoints/issue_config.py) `set_issue_category`).
