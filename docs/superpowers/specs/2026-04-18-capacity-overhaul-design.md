# Capacity Overhaul — Design

**Date:** 2026-04-18
**Status:** Approved by user, ready for implementation plan.

## Problem

The Capacity page (`/capacity`) currently shows only the **plan** (`available = norm − vacation − mandatory`) and has these gaps:

1. Employees table includes everyone ever seen by the sync (many are bots / ex-employees / irrelevant people). No way to narrow it to "people who actually work on our quarterly tasks".
2. Worklogs are synced by Jira's `updated` cursor. A worklog entered retroactively for an old period is missed by the incremental sync. There is no way to say "re-pull everything that happened on or after 2026-01-01, by `started` date".
3. Workday calendar is hardcoded to `weekday < 5` — Russian production calendar (holidays, moved workdays) is not respected.
4. There is no **fact**: we show plan (available hours) but never compare to actual logged hours.
5. No way to add a new employee that hasn't yet logged time on anything.

## Goals

Ship these capabilities as one cohesive set of changes to the Capacity domain, in phases that are independently useful and independently testable:

- **Reload worklogs by `started_at`** over a user-chosen period, with the last-used date persisted.
- **Recalculate the active employee set** based on who actually logs time on issues in the "Active stack" / "Quarterly archive" categories.
- **Filter and extend** the employee list: by-employee filter in the Team tab, "Add from Jira" button using Jira's user search.
- **Production calendar** (RU) stored locally: prefill from xmlcalendar.ru, override manually via `/settings`, integrate into workday counting.
- **Historical fact phase 1**: plan / fact / % per month per employee, side-by-side in the Team tab.
- **Historical fact phase 2**: fact distribution across category buckets, new "Распределение" tab.

## Non-goals

- Time-zone-aware month boundaries. Worklog `started_at` is compared as naive datetime; fine for Moscow-only team.
- Per-employee `hours_per_day` or per-employee `percent_of_norm` overrides. Still global.
- Background / async sync execution. All new endpoints are synchronous.
- Productivity factor, rate/cost, project-level capacity drilldown.

## Decisions taken during brainstorming

| # | Question | Decision |
|---|---|---|
| Q1 | What defines an "employee in Active stack / Quarterly archive"? | Employees with **worklogs** on issues whose `assigned_category` is in Active-stack-codes ∪ `archive_target`. |
| Q2 | Worklog reload semantics | Delete `worklog` rows with `started_at >= :since`, then re-pull via JQL `worklogDate >= :since`, filter locally by `started >= :since`. Date param persisted in AppSetting, default `2026-01-01`, UI button on "Синхронизация" tab. |
| Q3 | Production calendar source | Hybrid: xmlcalendar.ru as default source, manual override in `/settings`. Table stores **only special days**; absence of a row means fallback to `weekday < 5`. |
| Q4 | "Historical fact" scope | Phase 1 (План/Факт/%, columns side-by-side, not two-line cells). Phase 2 (category breakdown) as separate tab. |
| Q5 | Add Employee source | Jira `/rest/api/3/user/search?query=...` via new autocomplete modal. |
| Q6 | Employee cleanup safety | Soft-delete: toggle `is_active`. No FK breakage, reversible, idempotent. Exposed as `POST /employees/recalc-active`. |

---

## Architecture overview

All six fields of work touch the existing layer stack:

```
Connector Layer  →  Service Layer  →  Repository / ORM  →  DB
  JiraClient       CapacityService
  (+ new user         EmployeeService  (new service)
   search method)   ProductionCalendarService (new service)
  ProductionCalendarClient (new connector)
```

New DB objects: `production_calendar_day` table; new `AppSetting` key `worklog_reload_since_date`; new optional column `UI` filter key `ui_capacity_team_filter`.

No changes to `employee` / `worklog` / `issue` schemas. No changes to Jira custom-field IDs.

---

## Phased plan

Six phases, each independently shippable and independently testable. Each phase ends with `pytest` + frontend `build` + commit + push to `origin/main`.

| # | Phase | Depends on |
|---|---|---|
| 1 | Worklog reload by `started_at` | — |
| 2 | Employee `recalc_active` + filter in Team tab | 1 |
| 3 | Jira user search + "Add employee" modal | 2 |
| 4 | Production calendar (model + xmlcalendar + manual UI + `CapacityService` integration) | — |
| 5 | Historical fact phase 1 (plan / fact / %) | 1, 4 |
| 6 | Historical fact phase 2 (category breakdown) | 5 |

Phases 1 and 4 are independent — safe to parallelise if desired. 2→3 and 5→6 are strict chains.

---

## Phase 1 — Worklog reload by `started_at`

### Backend

- **AppSetting key** `worklog_reload_since_date` (ISO date string). Read/write via existing `_get_setting` / `_set_setting` in `app/api/endpoints/settings.py`. Default shown in UI `2026-01-01` if missing.
- **`SyncService.reload_worklogs_since(since: date) -> ReloadStats`**:
  1. `db.query(Worklog).filter(Worklog.started_at >= since).delete(synchronize_session=False)` → commit.
  2. JQL iterator: `iter_issues('worklogDate >= "YYYY-MM-DD"', fields=['summary','issuetype','status','project'], batch=100)`. Only issues **already present in local DB** are processed — unknowns skipped. (Prevents accidentally creating issues outside scope.)
  3. For each local issue: `iter_worklogs_for_issue(issue.jira_issue_id)` → filter `started >= since` → `_upsert_worklog` (existing helper). Auto-creates missing employees via `_upsert_employee`.
  4. Returns `ReloadStats(deleted: int, issues_scanned: int, worklogs_inserted: int)`.
  5. **Does not** update `sync_state.last_sync` — the regular incremental sync path is orthogonal.
- **Endpoint** `POST /sync/worklogs/reload` body `{since: "YYYY-MM-DD"}`:
  - Validates date, calls service, **updates `worklog_reload_since_date`** in AppSetting, returns stats.
  - Synchronous. If volume proves too large to finish in a request cycle, background task added later — not now.

### Frontend (SyncControls / `SyncPage.tsx`)

- New block "Перезагрузка worklog'ов с даты" alongside existing sync buttons:
  - `DatePicker` — initial value from `useGenericSetting('worklog_reload_since_date')`, fallback `2026-01-01`.
  - `Popconfirm` → `Button` "Перезагрузить" → `POST /sync/worklogs/reload`.
  - On success: notification `Удалено: N, прочитано issues: M, вставлено: K`. Invalidate `['employees']` + `['capacity']`.

### Tests

- Unit:
  - Delete filter correctness: pre-2026 rows survive; post-2026 rows removed.
  - `_upsert_worklog` is idempotent after truncate (no duplicate on rerun).
  - Unknown-issue skip path.
- Integration:
  - Endpoint end-to-end with mocked `JiraClient.iter_issues` + `iter_worklogs_for_issue`.
  - AppSetting upsert after successful call.

### Commit message

`Add dated worklog reload (truncate-by-started + JQL worklogDate)`

---

## Phase 2 — Employee `recalc-active` + Team-tab filter

### Backend

- **`EmployeeService.recalc_active_by_categories() -> RecalcStats`**:
  - `target_codes` = all category codes whose `code` is NOT in `{"archive", "initiatives_rfa"}`. That set equals the union of the "Active stack" and "Archive quarterly tasks" tabs as defined in frontend `matchesTab`. Computed by loading the `Category` table and filtering.
  - One SQL: `SELECT DISTINCT w.employee_id FROM worklog w JOIN issue i ON w.issue_id = i.id WHERE i.assigned_category IN :target_codes` → `active_ids`.
  - Two updates:
    - `UPDATE employee SET is_active = TRUE WHERE id IN :active_ids`
    - `UPDATE employee SET is_active = FALSE WHERE id NOT IN :active_ids`
  - Returns `RecalcStats(activated, deactivated, total_active)`.
  - Idempotent. Commits internally. Tests must clean up.
- **Endpoint** `POST /employees/recalc-active` — no body, returns stats.

### Frontend — Team tab

- Row of controls above the table (`Space`):
  - `Select mode="multiple"` "Сотрудник": options from `/employees?is_active=true`, local client-side filter on `dataSource`. Persist choice in AppSetting `ui_capacity_team_filter` (comma-joined employee_ids), hydrate on mount (same pattern as `ui_teams_categories`).
  - Button "Пересчитать состав" → `Popconfirm` → endpoint call → notify with stats, invalidate `['employees']`, `['capacity']`.

### Tests

- Unit:
  - Employee A has worklog on issue in active category → stays / becomes `is_active=True`.
  - Employee B has only worklog on `archive` → `is_active=False`.
  - Employee C has no worklogs → `is_active=False`.
  - Re-running does not change output (idempotence).

### Commit message

`Recalc active employees from worklog categories + Team filter`

---

## Phase 3 — Jira user search + "Add employee"

### Backend

- **`JiraClient.search_users(query: str, max_results: int = 20) -> list[JiraUserSchema]`**:
  - Calls `GET /rest/api/3/user/search?query=<q>&maxResults=<n>` (note: singular `user`, different endpoint than `users/search`).
  - Parses into existing `JiraUserSchema`.
- **Endpoint** `GET /jira/users/search?query=<q>`:
  - Validates `len(query) >= 2`, proxies client, returns list — **no DB write**.
- **Endpoint** `POST /employees/from-jira` body matching the `JiraUserSchema` payload already returned by `/jira/users/search` (i.e. `{jira_account_id, display_name, email, avatar_url, is_active}`):
  - No extra round-trip to Jira — the frontend passes whatever the autocomplete already fetched.
  - Calls `_upsert_employee` (existing helper) with the payload.
  - Forces `is_active = True` post-upsert (so a previously-deactivated person comes back on explicit add, even if `recalc-active` would otherwise hide them).
  - Returns `EmployeeResponse`.

### Frontend — Team tab

- New button "Добавить сотрудника" → opens `Modal`:
  - `AutoComplete` with:
    - min query length 2
    - debounce 300ms
    - options from `GET /jira/users/search?query=` (react-query `enabled: query.length >= 2`, no caching of raw query → use `staleTime: 60_000`)
  - On option select → `POST /employees/from-jira` → close modal, invalidate `['employees']` + `['capacity']`.

### Tests

- Unit:
  - `search_users` client: correct URL, correct parse, handles empty result.
- Integration:
  - `/jira/users/search` rejects query <2 chars.
  - `/employees/from-jira` creates new employee; re-adding existing one flips `is_active` back to True without duplicating row.

### Commit message

`Add Jira user autocomplete + Add-employee modal`

---

## Phase 4 — Production calendar

### Model (Alembic migration)

```python
class ProductionCalendarDay(Base):
    __tablename__ = "production_calendar_day"
    date = Column(Date, primary_key=True)
    is_workday = Column(Boolean, nullable=False)
    kind = Column(String(32), nullable=False)        # weekend|holiday|preholiday|workday_moved
    note = Column(String(255), nullable=True)        # e.g. "Новогодние каникулы"
    source = Column(String(16), nullable=False)      # xmlcalendar|manual
    synced_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Only **special days** are stored. Plain working weekdays and plain weekends **without overrides** are not stored — the service falls back to `weekday < 5`.

### Connector — `app/connectors/production_calendar_client.py`

- `fetch_year(year: int) -> list[CalendarDayRaw]`:
  - `GET https://xmlcalendar.ru/data/ru/{year}/calendar.json`.
  - Parses the response structure into flat list of rows: `(date, is_workday, kind, note)`.
  - Returns only the dates the source marks as special (holidays, short-days, moved workdays).
- Isolated, easily mockable.

### Service — `app/services/production_calendar_service.py`

- `sync_year(year: int, overwrite_manual: bool = False) -> SyncStats`:
  - Calls client `fetch_year`.
  - For each row: upsert into `production_calendar_day`.
  - If a row exists with `source == "manual"` and `overwrite_manual is False` — skip that date.
  - Returns `{inserted, updated, skipped_manual}`.
- `is_workday(d: date) -> bool`:
  - `SELECT is_workday FROM production_calendar_day WHERE date = :d`.
  - If found → that value. Otherwise → `d.weekday() < 5`.
- `workdays_in_range_map(start: date, end: date) -> dict[date, bool]`:
  - Fetches all special days within `[start, end]` in **one** query, returns a dict. `CapacityService._workdays_in_range` uses this map to avoid per-day SQL.
- `list_year(year: int) -> list[ProductionCalendarDay]`.
- `upsert_manual(date, is_workday, kind, note) -> ProductionCalendarDay`: sets `source="manual"`.
- `delete_manual(date)`: only permitted for rows with `source="manual"`.

### `CapacityService` integration

`_workdays_in_range` replaced by:

```python
def _workdays_in_range(self, start: date, end: date) -> int:
    if end < start:
        return 0
    calendar_map = self.production_calendar.workdays_in_range_map(start, end)
    days, current = 0, start
    while current <= end:
        is_workday = calendar_map.get(current, current.weekday() < 5)
        if is_workday:
            days += 1
        current += timedelta(days=1)
    return days
```

`CapacityService.__init__` accepts optional `production_calendar: ProductionCalendarService`, constructed with `self.db` if not passed (so tests can inject a stub).

### API

- `POST /settings/production-calendar/sync?year=YYYY` → stats.
- `GET /settings/production-calendar?year=YYYY` → list of year's special days.
- `PUT /settings/production-calendar` body `{date, is_workday, kind, note}` → upsert manual.
- `DELETE /settings/production-calendar/{date}`.

### Frontend — `/settings` new section

- Title "Производственный календарь".
- Year selector (`InputNumber` or `Select` 2024..2030) + button "Загрузить с xmlcalendar.ru" (→ `POST /sync?year=`; `Popconfirm` about overwrites).
- Table: `Date | Тип | Рабочий? | Примечание | Источник | Действия`.
  - Row actions enabled only when `source === "manual"`.
- Button "Добавить день" → modal with `DatePicker` + `Switch` "Рабочий?" + `Select` kind + `Input` note.

### Tests

- `fetch_year` parses a recorded xmlcalendar fixture correctly.
- `sync_year(overwrite_manual=False)` preserves manual rows.
- `is_workday`: fallback works; DB row overrides; cached map equivalent to per-day lookup.
- `CapacityService._workdays_in_range` returns correct count with mocked calendar.

### Commit message

`Production calendar (xmlcalendar + manual) with CapacityService integration`

---

## Phase 5 — Historical fact phase 1 (план / факт / %)

### Backend

- Extend `MonthlyCapacity` dataclass:
  ```python
  fact_hours: float      # sum of worklog.hours for this employee in [month_start, next_month_start)
  ```
- Extend `QuarterCapacity` dataclass: `total_fact_hours: float`.
- Add inside `CapacityService.monthly_capacity`:
  ```python
  month_start = date(year, month, 1)
  next_month_start = date(year + (month == 12), (month % 12) + 1, 1)
  fact = (
      self.db.query(func.coalesce(func.sum(Worklog.hours), 0.0))
        .filter(
            Worklog.employee_id == employee_id,
            Worklog.started_at >= month_start,
            Worklog.started_at <  next_month_start,
        )
        .scalar()
  )
  ```
  Compared as naive datetime (see "Non-goals" re: TZ).
- Extend `MonthCapacityResponse` / `QuarterCapacityResponse` schemas with `fact_hours`, `total_fact_hours`.

### Frontend — Team tab

- Column layout switches to AntD grouped columns:
  ```
  | Сотрудник | Январь {План|Факт|%} | Февраль {…} | Март {…} | Итого {План|Факт|%} |
  ```
- `%` = `fact / plan * 100`, rounded. Colour rules:
  - `%` ≥ 100 → green token (`token.colorSuccess`)
  - `%` < 50 → secondary grey
  - otherwise default text colour
- `scroll.x` bumped (AntD already supports).

### Tests

- `fact_hours` is exact sum for the month (boundary-sensitive: Jan 31 vs Feb 1).
- Worklog outside the month is not counted.
- Multiple employees don't bleed into each other.

### Commit message

`Plan/Fact/% columns in Team capacity view`

---

## Phase 6 — Historical fact phase 2 (category breakdown)

### Backend

- Constant in service: `CATEGORY_BUCKETS`:
  ```python
  {
      "active_stack":    "[all category codes not in {'archive', 'archive_target', 'initiatives_rfa'}]",
      "initiatives":     "initiatives_rfa",
      "archive_target":  "archive_target",
      "archive_other":   "archive",
      "uncategorized":   None,   # assigned_category IS NULL
  }
  ```
  `"active_stack"` membership computed from the `Category` table so it stays in sync with user-editable categories.
- `CapacityService.category_breakdown(year: int, quarter: int) -> list[TeamCategoryBreakdownResponse]`:
  - One SQL: `JOIN worklog w ON issue i, filter by started_at in quarter + is_active employees, GROUP BY employee_id, assigned_category, sum hours`.
  - Post-aggregate: map each code → bucket, sum into `{employee_id → {bucket → hours}}`.
  - Returns per-employee row: `{employee_id, employee_name, by_bucket: {active_stack, initiatives, archive_target, archive_other, uncategorized}, total_hours}`.
- Endpoint: `GET /capacity/team/category-breakdown?year&quarter`.

### Frontend — new tab on `/capacity`

- Tab "Распределение" alongside `Команда / Отпуска / Правила`.
- Table:
  ```
  | Сотрудник | Активный стек | Инициативы | Архив кварт. | Архив прочих | Без категории | Итого |
  ```
  - One row per active employee (same filter as Team tab).
  - Cells formatted with `formatHours`.
  - Итого column `strong`, bucket columns standard.
- Per-month toggle deferred to a later iteration (YAGNI).

### Tests

- Employee with worklogs in 3 different categories → correct per-bucket sum.
- Worklog on issue with `assigned_category=null` → lands in `uncategorized`.
- Quarter boundary correctness.

### Commit message

`Category-breakdown tab on Capacity page`

---

## Testing & CI

- All existing `pytest` suites continue to pass each phase.
- New tests listed per phase go into existing `tests/` pattern:
  - `tests/test_sync_service_reload.py` (phase 1)
  - `tests/test_employee_service.py` (phases 2, 3)
  - `tests/test_production_calendar_service.py` (phase 4)
  - `tests/test_capacity_service_fact.py` (phase 5)
  - `tests/test_capacity_service_breakdown.py` (phase 6)
- One Playwright E2E per user-visible phase (reload button click, recalc button click, add-from-Jira modal, settings calendar, plan/fact columns render).

## Risks

| Risk | Mitigation |
|---|---|
| xmlcalendar.ru unreachable at sync time | Cached data in DB is authoritative; `sync_year` failure is non-fatal — old data keeps serving. |
| Large worklog reload slower than HTTP timeout | Scope is Jan 2026 onwards, not the entire history. If too slow, add background task in a later iteration. |
| Jira `user/search` rate limits | Debounce 300ms + min length 2. Real-world use is tens of queries per session. |
| Category codes change over time | `CATEGORY_BUCKETS` computes `active_stack` dynamically from the `Category` table — no hardcoded list that could drift. |
| TZ mismatch between `started_at` and month boundaries | Out of scope; naive comparison; accept small edge-case inaccuracy. |

## Acceptance criteria

After all six phases are merged:

1. On `/sync` there is a DatePicker + button that truncates `worklog` rows with `started_at >= :since` and repopulates them from Jira by `worklogDate` JQL. The chosen date persists.
2. On `/capacity` "Команда":
   - A multi-select "Сотрудник" filters the visible rows.
   - Button "Пересчитать состав" makes only employees with worklogs on active/archive_target issues appear in the list; others are hidden (soft-deleted).
   - Button "Добавить сотрудника" opens a modal with Jira-user autocomplete; picking one adds them with `is_active=True`.
3. On `/settings` there is a "Производственный календарь" section: load-from-xmlcalendar button, editable table of special days.
4. The workday count in `CapacityService` reflects the production calendar (e.g., January 1-8 2026 holidays reduce `norm_hours`).
5. "Команда" table shows План / Факт / % columns for each month and for the quarter total, coloured per the rules above.
6. New tab "Распределение" shows per-employee fact split across five category buckets for the selected quarter.
