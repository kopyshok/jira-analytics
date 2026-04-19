# Capacity Page v2 — Design

**Date:** 2026-04-19
**Status:** Approved by user, ready for implementation plan.
**Supersedes parts of:** [2026-04-18-capacity-overhaul-design.md](./2026-04-18-capacity-overhaul-design.md) (Team/Vacations/Rules tabs; other sections unchanged).

## Problem

After the capacity overhaul (2026-04-18) the page works but the UX does not match how PM actually groups work:

1. **No team axis.** The page shows a flat list of employees. Capacity planning is done per product team ("Продуктовая команда"), and right now there is no way to see "how loaded is team X this quarter".
2. **`Employee.team` column exists in the DB but is never populated.** The `/sync` path does not write it, and there is no UI to set it.
3. **Fact/% columns are always on.** In the forecast conversation PM wants to hide actuals to focus on plan; in the retrospective review PM wants them. No toggle today.
4. **"Отпуска" is too narrow.** Sick leave, comp time (отгул), and "other" absences are operationally the same as vacation — they reduce available hours — but have nowhere to go.
5. **No absence visualisation.** A dense list of rows does not answer "who is out in June?" at a glance.
6. **Operational friction.** Rules have to be re-entered each quarter. Capacity cannot be exported to Excel for planning meetings. Over-allocation (>100 %) is not visually distinguished from "fully loaded" (=100 %).

## Goals

Ship one cohesive update to the `/capacity` page and its backing domain:

- **Team assignment.** Each `Employee` has an editable team (from the Jira custom field's configured options). Inline edit in the Team tab, bulk auto-detect from worklogs, team column in the list.
- **Team hierarchy.** Team tab groups employees by team with team-level totals; un-assigned rows collect under "Без команды".
- **Team filter.** Multi-select by team, alongside the existing by-employee filter.
- **Column toggles.** Switches "Показать факт" / "Показать %" above the table, off by default, persisted.
- **Absences domain.** `Vacation` → `Absence` with a typed `reason` (`vacation` / `sick` / `day_off` / `other`); capacity math unchanged.
- **Absence heatmap.** Day × employee grid at the top of the Absences tab for the current quarter.
- **Rules: copy to next quarter.** Button on the Rules tab clones all rules from `(year, quarter)` into the next quarter.
- **Capacity Excel export.** `GET /exports/capacity.xlsx?year&quarter` downloads the Team-tab data (plan / fact / % per month, per employee, grouped by team).
- **Overload alert.** `pct > 110 %` styled as danger (red), `100 % ≤ pct ≤ 110 %` success (green), `< 50 %` muted.

## Non-goals

- **Historical team membership** (`team_membership(employee, team, start_date, end_date)`). Flat `Employee.team` is sufficient for current-quarter views. Deferred.
- Per-employee overrides for `hours_per_day` / `percent_of_norm`. Still global.
- Absence approval workflow. The tab is a tracking surface, not an HR process.
- Editing an absence in place — delete + re-add is enough.
- Background export / async long-running jobs.
- Heatmap drag-to-add. Heatmap is read-only; adds go through the form.

## Decisions taken during brainstorming

| # | Question | Decision |
|---|---|---|
| A | Data model for absences | **Rename `vacations` → `absences`** + `reason` String(32) NOT NULL. Rename `Vacation` model → `Absence`, migrate API to `/capacity/absences` (under the existing `/capacity` router). |
| B | Team grouping rendering | **Expandable parent rows** via AntD Table tree data. Team row shows aggregates; children are employees. `Без команды` is always-last group. |
| C | Heatmap placement | **Inside the Absences tab**, above the records table, scoped to the selected quarter. |
| D | Team assignment UX | **All three:** inline Select in the first column of the Team tab (A), plus a bulk "Определить команды автоматически" button (C), plus the route works from the Employees API so a future Employees page (B) can reuse it. |
| E | Overload threshold | `> 110 %` is danger. Keeps "round-to-100 %" from flipping colour on every small variance. |

## Data model changes

### 1. Rename `vacations` → `absences` (migration `0XX_rename_vacations_to_absences`)

```python
# alembic op sequence, all in a single batch for SQLite
op.rename_table("vacations", "absences")
with op.batch_alter_table("absences") as b:
    b.add_column(sa.Column("reason", sa.String(32), nullable=False, server_default="vacation"))
op.execute("UPDATE absences SET reason='vacation' WHERE reason IS NULL OR reason=''")
```

Downgrade: drop column, rename back.

Model rename (`app/models/vacation.py` → `app/models/absence.py`, class `Vacation` → `Absence`). Update:
- `app/models/__init__.py` export list.
- `Employee.vacations` relationship → `Employee.absences`.
- All references in `app/services/capacity_service.py` (reads vacation rows to subtract hours — keeps working unchanged, just reads `absences` table; **all reasons are treated identically for capacity math**).

### 2. `Employee.team` — usage

Column already exists (`String(100)`, nullable). No schema change. New endpoint to mutate it (see below). Values are free-form strings but UI picks from `/sync/jira-teams` to keep them aligned with Jira's configured options.

### 3. No schema changes

to: `MonthlyCapacityRule`, `Issue`, `Worklog`, `Project`, `AppSetting`. Copy-rules is a service-layer operation.

## Backend API

### New / changed endpoints

All paths are API-v1-prefixed (`/api/v1/...`), shown here without the prefix for brevity.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/capacity/absences` | List all absences. Replaces `/capacity/vacations`. Response row has `reason`. |
| `POST` | `/capacity/absences` | Create. Body: `{employee_id, start_date, end_date, reason}`. |
| `DELETE` | `/capacity/absences/{absence_id}` | Delete. |
| `PUT` | `/employees/{employee_id}/team` | Body: `{team: string\|null}`. Sets or clears only the team field. Dedicated sub-path (not a generic `PATCH /employees/{id}`) so that future employee-level partial updates cannot collide with this action and so that permission rules can be scoped per-field. |
| `POST` | `/employees/auto-detect-teams` | Bulk action. For every employee whose `team IS NULL`, derive team from worklog mode (see service). Response: `{assigned: int, skipped: int, details: [{employee_id, team}]}`. Follows the existing `POST /employees/recalc-active` convention — action name as a fixed segment parallel to `{employee_id}`-parametrised routes; safe because FastAPI matches literal paths before path-params. |
| `POST` | `/capacity/rules/copy-to-quarter` | Body: `{from_year, from_quarter, to_year, to_quarter}`. Clones rules. `409` with list of conflicting `(year, month)` pairs if any target slot already has a rule. The explicit `copy-to-quarter` segment removes any reading as `{rule_id}=copy`. |
| `GET` | `/exports/capacity.xlsx?year&quarter` | Download xlsx of the Team-tab view. |

### `/capacity/vacations` compatibility

Delete the `/capacity/vacations` handlers entirely — no legacy shim. Tests + e2e seed updated in the same PR. `Vacation` import in [capacity.py:15](app/api/endpoints/capacity.py#L15) is replaced by `Absence`.

### Response shape changes

- `QuarterCapacityResponse` gains `team: string | null`. Frontend groups on it; the service does not assume any particular sort order.
- Existing `/capacity/quarter/{year}/{quarter}` keeps all current fields; clients that ignore `team` continue to work.

## Services

### `AbsenceService` (renamed from `VacationService`)

Identical surface to current service, plus `reason` passed through on create. Capacity calculation continues to subtract all absence types from available hours (workdays × hours − absence overlap hours − mandatory hours).

### `EmployeeTeamService` (new, `app/services/employee_team_service.py`)

```python
def auto_detect_team(self, employee_id: str, *, lookback_days: int = 180) -> str | None:
    """
    Mode of issue.team across this employee's worklogs within lookback window.
    Ties broken by the team with the highest aggregate time_spent_seconds.
    Returns None when employee has no worklogs or all worklogged issues have team=NULL.
    """

def auto_detect_all_missing(self) -> AutoDetectSummary:
    """Runs auto_detect_team on every active employee with team IS NULL."""
```

Lookback default 180 d so we capture the current quarter plus the prior one (new hires without enough history fall through to manual assignment).

### `CapacityService` extensions

- `get_team_capacity` already returns one row per employee; add `team` (read from `Employee.team` in the eager-loaded query).
- `copy_rules(from_year, from_quarter, to_year, to_quarter)`:
  - Query `monthly_capacity_rules` where `(year, month) in QUARTER_MONTHS[from_quarter]`.
  - For each row, compute `to_month = QUARTER_MONTHS[to_quarter][index]`.
  - Raise `RulesConflict` if any `(to_year, to_month)` already exists.
  - Bulk insert.
  - Commit.

### `ExportService` extensions

```python
def export_capacity_xlsx(self, year: int, quarter: int) -> bytes:
    """
    One worksheet. Group rows: team header row (bold, aggregate), then employees.
    Columns: Сотрудник, <M1 plan>, <M1 fact>, <M1 %>, <M2 ...>, ..., Total plan, Total fact, Total %.
    Openpyxl lazy-imported (matches existing pattern).
    """
```

## Frontend

### `CapacityPage.tsx` tab structure

```
<Tabs>
  Команда        → TeamTab (rewritten)
  Распределение  → BreakdownTab (unchanged)
  Отсутствия     → AbsencesTab (rewritten, replaces VacationsTab)
  Правила        → RulesTab (+ "Скопировать в следующий квартал")
</Tabs>
```

### `TeamTab` — grouping, filters, toggles

**Toolbar (single row, wraps on narrow screens):**
- Team filter — `Select mode="multiple"`, options from `useJiraTeams()`, persisted to `ui_capacity_team_filter_teams`.
- Employee filter — existing, persisted to `ui_capacity_team_filter` (unchanged key).
- `Switch` "Показать факт" — off by default, persisted to `ui_capacity_show_fact`.
- `Switch` "Показать %" — off by default, persisted to `ui_capacity_show_pct`.
- `Button` "Экспорт в Excel" — `href={...}/exports/capacity.xlsx?year&quarter`.
- Existing `Button` "Пересчитать состав" — unchanged.
- Existing `Button` "Добавить сотрудника" — unchanged.
- `Button` "Определить команды автоматически" — new. Confirmation popup. Success → invalidate `employees` cache.

**Data shape:**

```ts
type Row = EmployeeRow | TeamRow;
type TeamRow = {
  key: string;              // `team:${name}` or `team:__none__`
  isTeam: true;
  team: string;             // display name, "Без команды" for null group
  totals: {plan: number, fact: number};
  children: EmployeeRow[];
};
type EmployeeRow = {
  key: string;              // employee_id
  isTeam: false;
  employee_id: string;
  employee_name: string;
  team: string | null;
  months: {...};
  total_available_hours: number;
  total_fact_hours: number;
};
```

Groups sorted by team name ascending, `__none__` last. Empty teams hidden.

**Table columns:**
- `Сотрудник` — on employee row: name + inline `Select` (team, allowClear, options from `useJiraTeams`). On team row: team name bold + employee count.
- For each quarter month: `{m}.План` always visible. `{m}.Факт` if `showFact`. `{m}.%` if `showPct`.
- `Итого`: `План` always, `Факт` / `%` per toggles.
- `pctColor` updated: `> 110` red, `100–110` green, `< 50` muted, else default.

Tree rendering: AntD `Table` with `childrenColumnName: 'children'`, `expandable={{ defaultExpandAllRows: true }}`. Team rows styled via `rowClassName`.

Inline team edit: `PATCH /employees/{id}` with `{team}`; on success invalidate `useTeamCapacity` and `useEmployees`.

### `AbsencesTab` — heatmap + records

**Heatmap (top block):**
- Scope: current `(year, quarter)` from `useQuarterYear`.
- Rows: employees present in current team/employee filter (same Selects as on the Team tab *visually*, **but AbsencesTab has its own state** — reusing the Team tab's filter store is out of scope for v2; keep it simple). Filter within the Absences tab is a standalone `Select mode="multiple"` over employees.
- Columns: every day of the selected quarter (~90–92). Column width 18 px; weekends dimmed via `ProductionCalendar` lookup.
- Cell rendering: colour per reason — `vacation #fa8c16`, `sick #f5222d`, `day_off #1677ff`, `other #8c8c8c`. Empty cell = transparent.
- Tooltip on hover: `"{employee_name}: {reason_label}, {start_date}–{end_date}"`.
- Client-side projection: reads the existing `/capacity/absences` list; no new heatmap API.
- Horizontal scroll container; the records table below is a separate block.

**Records table (below):**
- Identical to today's Vacations table plus:
  - `Причина` column, rendered with coloured tag.
  - Add-form has `reason` `Select` with four options, default `vacation`.

### `RulesTab` — copy button

- New button "Скопировать в следующий квартал".
- Computes `(to_year, to_quarter)`: `quarter + 1`, rollover to `year + 1, Q1`.
- Calls `POST /capacity/rules/copy`. On 409 → notification warning with target months that conflicted.
- On success → invalidate rules query; switch `QuarterYearSelect` to target quarter so PM sees the result.

### Hooks & types

- Split `useCapacity.ts`: keep team/rules hooks; extract absence hooks to `useAbsences.ts`.
- `useJiraTeams()` already exists — reused for both filters.
- `useSetEmployeeTeam()`, `useAutoDetectTeams()` — new mutations under `useCapacity.ts`.
- `useCopyRules()` — new mutation.
- Type rename: `VacationResponse` → `AbsenceResponse` with `reason`.

### AppSetting keys added

| Key | Value |
|---|---|
| `ui_capacity_show_fact` | `"0"` / `"1"` |
| `ui_capacity_show_pct` | `"0"` / `"1"` |
| `ui_capacity_team_filter_teams` | comma-joined team names |
| `ui_capacity_absences_filter` | comma-joined employee ids (absences tab own filter) |

## Tests

### Backend (`tests/`)

- `test_absence_service.py` — CRUD, `reason` persistence, `reason` defaults to `"vacation"` when migrated.
- `test_capacity_service_team.py` — `get_team_capacity` includes `team` field; auto-detect mode / tie-break behaviour.
- `test_capacity_rules_copy.py` — happy path (Q1 → Q2), conflict (target month already present), rollover (Q4 → next year Q1).
- `test_capacity_export.py` — xlsx renders; header row present; team groups appear; numbers match service.
- `tests/test_api_absences.py` — endpoint parity with old `/capacity/vacations` + `reason`.
- Migration smoke test: add a row to `vacations` on a pre-migration DB, upgrade, assert it moved to `absences` with `reason='vacation'`.

### E2E (`frontend/e2e/`)

- `capacity.spec.ts` extensions:
  - Team filter narrows rows.
  - Both switches OFF by default; toggle shows fact / pct columns; refresh persists.
  - Inline team edit on an employee updates the row and re-groups.
  - Отсутствия: add a sick leave, heatmap cell for those dates is `sick` red.
  - Копировать правила: click button on Rules, QuarterYearSelect moves to next quarter, rules present.
  - Excel download returns a non-empty xlsx.
- Seed (`scripts/seed_e2e.py`) assigns E2E Analyst to a team.

## Migrations plan

1. `0XX_rename_vacations_to_absences` — one alembic revision, batch-mode for SQLite.

No other schema migrations; everything else is code/endpoint churn.

## Out of scope

- Historical team membership (defer).
- Absence approval workflow.
- Heatmap drag-to-add.
- Per-row edit of absences (delete + re-add is fine).
- Capacity rules diff-view when copying.
- Gantt-style absence visualisation.

## Open risks / notes

- **`Employee.team` values drift from Jira options.** If an admin renames a team in Jira, `/sync/jira-teams` returns the new value, but `Employee.team` still holds the old one. Mitigation for v2: the inline Select in TeamTab shows current value in a red tag when it is not in `/sync/jira-teams`, so PM can fix it. Implemented; no backend migration needed.
- **Heatmap performance.** ~50 employees × 92 days = 4 600 cells. Plain divs in a CSS grid handle this easily; no virtualization required. Re-measured if the team grows past ~200.
- **Excel export colouring.** Openpyxl supports fills; overload / underload tinting matches the table. Kept simple — no conditional formatting formulas.
- **Copy-rules rollover.** `Q4 2026 → Q1 2027` works via the rollover rule. Tested explicitly.
- **Rename blast radius.** ~15 files change due to Vacation → Absence. Acceptable per decision A; handled by the subagent flow with a commit per phase.
