# app/models — DB schema

29 таблиц. Источник правды — `app/models/__init__.py`.

## Инварианты

- UUID string keys (`String(36)`) для всех таблиц
- Стандартные timestamps: `created_at`, `updated_at`, `synced_at`
- Все DB-изменения — через Alembic batch migrations (SQLite требует batch для ALTER)

## Группы таблиц

### Core (Jira sync, 7)

`Employee`, `EmployeeTeam` (M:N), `Project`, `Issue`, `Worklog`, `Comment`, `SyncState`.

**`EmployeeTeam` — периодизованное участие.** Активно в день `d`, если `(joined_at is None or joined_at <= d) and (left_at is None or d < left_at)`; `left_at` — первый день ВНЕ команды. На одну пару сотрудник/команда допустимо несколько непересекающихся периодов (ушёл — вернулся), unique-constraint снят.

Инварианты enforce'ятся в `EmployeeTeamService` (не в БД — SQLite не поддерживает partial unique): периоды одной пары не пересекаются; на любую дату не более одной `is_primary=true` записи. Поле `Employee.team` — derived от основной команды **на сегодня**, обновляется через `_recompute_legacy_team`.

**Состав команды НЕ запрашивать напрямую** — только через `app/services/team_membership.py` (см. [app/services/CLAUDE.md](../services/CLAUDE.md)), иначе выбывшие снова попадут в расчёты задним числом.

**`Issue` user/Jira-metadata fields:**
- `team` — первое значение team-поля
- `participating_teams` — JSON list (Text)
- `assigned_category` — ручная override
- `include_in_analysis` — флаг показа в analytics
- `out_of_scope` — Bucket B auto-ingest (см. `app/services/CLAUDE.md` Worklog buckets)
- `status_category` — Jira `new|indeterminate|done` из `status.statusCategory.key`
- `status_changed_at` — из `statuscategorychangedate`
- `paused_days` — дни в статусах паузы («Приостановлено»), считаются из истории статусов Jira и вычитаются из факта Cycle Time в KPI
- `goals` — comma-joined `customfield_11421`
- `developer_account_id` / `developer_display_name` — кастомное поле Jira «Разработчик» (тип user, `customfield_14052`)
- `dev_est_hours` — «DEV est (ч)» (`customfield_12952`), оценка разработки задачи; не путать с `planned_dev_hours` (вкладка плановых трудозатрат RFA/эпика)

### Scope / category config (6)

`ScopeProject`, `ScopeRoot`, `CategoryOverride`, `WorklogQualityRule`, `CategoryMapping`, `Category`.

`Category` — user-editable, seeded 10 записей. `ARCHIVE_CATEGORY_CODES = {archive, archive_target}` автоматически снимают `include_in_analysis` в single/batch endpoint. `Category.work_type_id` — nullable FK → `mandatory_work_types.id` с `ondelete=SET NULL`.

### Hierarchy (1)

`HierarchyRule` — user-editable parent→child type rules, заменяют hard-coded `CONTAINER_ISSUE_TYPES`. Управляются на `/settings` → «Иерархия».

### Capacity / planning (12)

- `Absence` (бывший `Vacation`, миграция 018) с `reason_id` FK → `absence_reasons.id`
- `AbsenceReason` — редактируемый справочник: `is_planned`, `color`, `is_active`, `sort_order`
- `MandatoryWorkType` — user-editable, seeded 5: `organizational`, `management_admin`, `support_consult`, `tech_debt`, `technical_tasks`
- `Role` — редактируемый реестр ролей сотрудников
- `RoleCapacityRule` — per (year, quarter, role?, work_type_id), `role=NULL` = fallback «для всех»; шаблон копируется в новые сценарии
- `EmployeeCapacityOverride` — per (year, quarter, employee_id, work_type_id); приоритет выше role-rule
- `ProductionCalendarDay` — per-day `hours` для RU календаря
- `BacklogItem` — с `archived_at` lifecycle (active/in-work/archive вкладки)
- `PlanningScenario` — `status` ∈ {draft, approved}, привязка к `team`
- `ScenarioAllocation` — per-scenario галочки на `BacklogItem`
- `ScenarioRule` — per-scenario правила обязательных работ (копия `RoleCapacityRule` на момент создания)
- `ScenarioRevision` + `ScenarioRevisionItem` + `ScenarioCapacitySnapshot` — история утверждений сценария: дифф включённых инициатив + снапшот нормы команды

### Team desk (1)

`TeamDeskMark` — отметка «просмотрено» на паре задача + признак (`uq_team_desk_mark`). `signature` — снимок причины на момент отметки; расходится с текущей — отметка сгорает и удаляется (см. `app/services/team_desk/marks.py`). Настройки раздела живут не тут, а в `AppSetting['team_desk_config']`.

### App state (1)

`AppSetting` — flat key-value store. Helpers `_get_setting` / `_set_setting` в `app/api/endpoints/settings.py` (get-or-insert, commits internally).

**Ключи:**
- Credentials: `jira_email`, `jira_api_token`, `jira_base_url`
- Jira custom field IDs: `jira_team_field_id`, `jira_participating_teams_field_id`, `jira_goals_field_id` (seeded `customfield_11421` миграцией 012)
- UI persistence: `ui_team_projects` (TaskSectionsTab single team), `ui_teams_categories` (CategoryConfigTab multi-team, comma-joined)
