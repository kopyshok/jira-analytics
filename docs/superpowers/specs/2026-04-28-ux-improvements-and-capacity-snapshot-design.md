# Design: UX Improvements + Capacity Snapshot Architecture

**Date:** 2026-04-28  
**Scope:** 8 improvement areas across Categories, Settings, Sync, Target Tasks, Resources, Dashboard

---

## Summary of Decisions

| Area | Decision |
|------|----------|
| Categories list truncation | Replace fixed 600px scroll height with dynamic viewport-based height |
| Settings → Projects in scope | Keep tab, no changes needed |
| Settings → Work categories tab | Make editable (rename, color, sort order, add/delete) |
| Sync → legacy buttons | Remove 2 issue-sync buttons; keep worklogs + service ops |
| Target tasks → missing RFA-241 | Investigate and fix backlog filter bug |
| Target tasks → Archive tab | Add quarter column + grouping toggle (Variant B); "Без квартала" always last |
| Dashboard → team filter missing | Apply global team filter to CategoryWidget and NormWorkWidget |
| Dashboard + Resources → norm/fact + capacity changes | Snapshot norms + absences at approval; indicator A3 on scenario |

---

## 1. Quick Fixes (no architecture changes)

### 1.1 Categories list truncation
- **File:** `frontend/src/pages/SyncPage.tsx:168`
- **Change:** Replace `const tableScroll = { y: 600 }` with dynamic calculation: `y: window.innerHeight - TABLE_TOP_OFFSET` or use CSS `calc(100vh - Npx)` via AntD `scroll={{ y: 'calc(100vh - 280px)' }}`
- **Applies to:** all tabs in CategoryConfigTab

### 1.2 Sync → remove legacy issue-sync buttons
- **File:** `frontend/src/components/sync/SyncAdvanced.tsx`
- Remove buttons: "Обновить задачи (incremental)" and "Полная синхронизация задач"
- Keep: worklogs update/reload, recalculate mapping, auto-detect teams
- The "Синхронизация задач (legacy)" section header also removed

### 1.3 Dashboard → apply global team filter to widgets
- **Files:** `frontend/src/pages/DashboardPage.tsx`, `frontend/src/hooks/useAnalytics.ts`
- Pass `selectedTeams` from global filter to `useDashboardCategories` and `useDashboardNormWork` hooks
- **Backend:** `GET /analytics/dashboard/categories` and `GET /analytics/dashboard/norm-work` — add `teams` query param, filter worklogs by employee team membership

### 1.4 Round hours to integers everywhere
- All hour values in Dashboard widgets, Capacity page, Scenario page: `Math.round(hours)` before display
- No decimal fractions: `5 ч` not `4.5 ч`

### 1.5 Target tasks → RFA-241 missing from Backlog tab
- Investigate: BacklogPage "active" tab filter vs CategoryConfigTab "initiatives" tab
- Likely cause: filter mismatch between `category = 'initiatives_rfa'` and backlog item creation condition
- Fix after investigation

---

## 2. Archive Tab: Quarter Column + Grouping

### UI changes (`frontend/src/pages/BacklogPage.tsx`)

**New column:** "Квартал" — shows quarter tag (e.g. `2 кв. 2026`) derived from the backlog item's approved scenario quarter, or `—` if none.

**Grouping toggle:** Button in tab toolbar: "Группировать по кварталам" (on/off, persisted in localStorage).

**When grouping ON:**
- Rows grouped under collapsible section headers: `▼ 2 кв. 2026 (8 задач)`, `▼ 1 кв. 2026 (5 задач)`
- Sorted newest quarter first
- `Без квартала` group always last, collapsed by default
- Each group header shows task count badge

**When grouping OFF:** flat list with sortable "Квартал" column (default sort: newest first)

### Data
- Quarter derived from `backlog_item.allocations` → `scenario.quarter + scenario.year` where `scenario.status = 'approved'`
- If multiple approved scenarios → show the most recent one
- Backlog API response: add `quarter_label: str | None` field to `BacklogItemResponse`

---

## 3. Settings → Work Categories Tab (Editable)

### Current state
`SettingsPage` "categories" tab → `CategoriesTab` component — currently display-only.

### New behavior
Inline-editable table with:
- **Label** — editable text field
- **Color** — color picker (existing colors from AntD palette)
- **Sort order** — drag handle for reorder
- **Add row** — "+ Добавить категорию" button at bottom
- **Delete** — only non-system categories (`is_system = false`) can be deleted; system ones show lock icon
- **Save/Cancel** — row-level or batch save

### API (already exists)
- `GET /categories` — list all
- `POST /categories` — create
- `PUT /categories/{id}` — update label/color/sort_order
- `DELETE /categories/{id}` — only non-system

---

## 4. Capacity Snapshot Architecture (Core Feature)

### Problem
After scenario approval:
- Absences change (added/deleted) → available hours change
- No way to detect or surface this to the user
- Dashboard norm-hours widget recalculates dynamically → norm "drifts" when rules change

### Solution: two new snapshot tables at approval time

#### 4.1 New table: `scenario_norm_snapshot`

Stores per-employee × per-month × per-work-type norm hours at approval time.

```
scenario_norm_snapshot
  id               UUID PK
  revision_id      FK → scenario_revision
  employee_id      FK → employee
  employee_name    String(200)   -- denormalized
  role             String(50)    -- 'analyst' | 'dev' | 'qa' | 'opo'
  year             Integer
  month            Integer       -- 1-12
  work_type_id     FK → work_type (nullable if category-based)
  work_type_label  String(200)   -- denormalized
  norm_hours       Float         -- hours allocated to this work type this month
```

**Purpose:** enables dashboard to read norm from snapshot (not recalculate), and future per-employee/role analysis.

**How computed at approval:**
For each employee in team × each month in quarter × each work type:
`norm_hours = monthly_norm_hours(employee, month) × scenario_rule_pct(role, work_type)`

#### 4.2 New table: `scenario_absence_snapshot`

Stores all absences in effect at approval time for employees in the scenario's team.

```
scenario_absence_snapshot
  id                  UUID PK
  revision_id         FK → scenario_revision
  employee_id         FK → employee
  employee_name       String(200)   -- denormalized
  original_absence_id String(36)    -- reference to absence.id at snapshot time (not FK)
  start_date          Date
  end_date            Date
  reason_id           FK → absence_reason (nullable)
  reason_label        String(200)   -- denormalized
  hours_total         Float
```

**Purpose:** diff current absences vs snapshot to detect what changed after approval.

### 4.3 Approval endpoint changes (`app/api/endpoints/planning.py`)

When `POST /planning/scenarios/{id}/approve`:
1. Existing: create `ScenarioRevision` + `ScenarioCapacitySnapshot` (keep as-is)
2. **New:** create `scenario_norm_snapshot` rows — for each employee × month × work_type
3. **New:** create `scenario_absence_snapshot` rows — for all absences of team employees intersecting the quarter

### 4.4 Capacity diff endpoint

New: `GET /planning/scenarios/{id}/capacity-diff`

Response:
```json
{
  "has_changes": true,
  "changed_employees": [
    {
      "employee_id": "...",
      "employee_name": "Копышков Николай",
      "months": [
        {
          "year": 2026,
          "month": 4,
          "snapshot_available_hours": 168,
          "current_available_hours": 176,
          "delta_hours": 8,
          "absence_changes": [
            {
              "type": "removed",
              "start_date": "2026-04-14",
              "end_date": "2026-04-18",
              "reason": "Отпуск",
              "hours": 40
            }
          ]
        }
      ]
    }
  ]
}
```

**Logic:**
1. Load latest `ScenarioRevision` for scenario
2. Load `ScenarioAbsenceSnapshot` for that revision
3. Load current absences for same employees × same date range
4. Set-diff: find absences added/removed/changed since approval
5. Also compare `ScenarioCapacitySnapshot.available_hours` vs current recalculated value

### 4.5 Scenario indicator: Variant A3

**Location:** `PlanningPage` — scenario card/header

**Trigger:** on page load, call `GET /scenarios/{id}/capacity-diff` for each approved scenario

**Display when `has_changes = true`:**
- Amber border on scenario card (`border: 1px solid rgba(245,158,11,0.5)`)
- Badge: `⚠ Доступность изменилась (N чел.)` — clickable
- On click: expands inline detail rows, one per changed employee-month
- Each row: `[Имя] | [Месяц]: [было] → [стало] ч | delta` + absence change reason
- Actions: "Пересмотреть" (re-opens approval flow) | "Игнорировать" (dismisses until next change, stored in `scenario.capacity_drift_acknowledged_at`)

**Performance:** diff endpoint called lazily (only for approved scenarios visible on screen), results cached in React Query with 5-min TTL.

### 4.6 Dashboard NormWorkWidget changes

**Month filter:** widget responds to global page-level month selector (Апр/Май/Июн pills already in header). No separate filter inside widget.

**Data source:** read from `scenario_norm_snapshot` (latest approved scenario for selected team) instead of dynamic recalculation.

**Grouping:** by `work_type_label` (same as current — Проекты и развитие, Орг. вопросы, etc.)

**Fact:** from worklogs, filtered by team + month (existing logic).

**Hours:** rounded to integers (`Math.round`).

**Click:** future — navigate to Analytics section detail page (out of scope for this spec).

**API change:** `GET /analytics/dashboard/norm-work?year=&quarter=&month=&teams=` — add `month` (optional, overrides quarter aggregation) and `teams` params. When `month` provided, read from `scenario_norm_snapshot` filtered by month; when only `quarter`, sum across 3 months.

---

## 5. Migrations Required

| Migration | Description |
|-----------|-------------|
| `038_scenario_norm_snapshot` | Create `scenario_norm_snapshot` table |
| `039_scenario_absence_snapshot` | Create `scenario_absence_snapshot` table |
| `040_scenario_capacity_drift_ack` | Add `capacity_drift_acknowledged_at` column to `planning_scenario` |

---

## 6. Out of Scope

- Detailed analytics page on NormWorkWidget click (future, in Analytics section)
- User-customizable category colors (separate spec)
- Full subtree count on issue tree
- Run/Change analytics (customfield_11506)
