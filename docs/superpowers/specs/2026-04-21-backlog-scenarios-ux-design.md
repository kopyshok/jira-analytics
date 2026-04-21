# Backlog + Scenarios UX — Design Spec
_Date: 2026-04-21_

## Overview

8 improvements across the Backlog and Scenarios pages.
Frontend-only items (Б-1..3, С-1, С-3) are pure React/CSS changes.
С-2 and С-5 are bug fixes. С-4 requires a backend extension + frontend collapse widget.

---

## Б-1 · Исполнитель + Заказчик в таблице Бэклога

**What:** Two new columns added to `BacklogPage.tsx` after «Статус».

**Data:** Already present in `BacklogItemResponse` (`assignee_employee_id`, `assignee_display_name`, `customer`). No backend changes needed.

**Behaviour:**
- **Ручной элемент** (`issue_id == null`): Исполнитель — `<Select>` с активными сотрудниками (same list as used in Scenarios); Заказчик — inline `<Input>` text field. Both save via existing `PATCH /backlog/{id}`.
- **Jira-привязка** (`issue_id != null`): both fields read-only, show `assignee_display_name` / `customer` as plain text (same pattern as `estimate_*` fields).

**Columns:**
| Column | Width | Source |
|---|---|---|
| Исполнитель | 140px | `assignee_display_name` (RO) or Select (editable) |
| Заказчик | 120px | `customer` text |

**Employee list source:** `useEmployees()` filtered to `is_active=true` — same hook already used elsewhere.

---

## Б-2 · Цветные ячейки АН / ПР / ТС / ОПЭ в Бэклоге

**What:** Replace plain `InputNumber` cells with `BacklogRoleCell`-style colored widgets. Component already exists at `frontend/src/components/planning/BacklogRoleCell.tsx`.

**Editable state (manual items):** Wrap each widget in a `<Popover>` containing an `<InputNumber>`. Click on the widget opens the popover; on blur/enter saves via `PATCH`.

**Read-only state (Jira items):** Render `BacklogRoleCell` directly (no popover).

**% calculation:** `pct = hours / sum(all 4 roles)` — same as current `BacklogRoleCell` logic.

**Colors:** Use `getRoleColor(roles, roleCode)` from `utils/roles.ts`.
- АН → `analyst`, ПР → `dev`, ТС → `qa`, ОПЭ → `OPO_COLOR` from `utils/opo.ts`.

---

## Б-3 · Убрать «Риск», переименовать «Всего» → «Всего часов» с %

**In `BacklogPage.tsx`:**
- Remove `Risk` column from `baseColumns()`.
- Add column **«Всего часов»** (width 90px, right-aligned):
  - Top line: `estimate_hours` (or sum of 4 role fields) in монospace.
  - Bottom line (small): `X% ресурса` where denominator = sum of `estimate_hours` across all rows in current view.
  - Denominator computed once via `useMemo` over the active rows array.

---

## С-1 · Верхняя таблица сценария: шрифт, цвета ролей, виды работ в одну строку

**File:** `frontend/src/components/planning/ScenarioResourceSummary.tsx`

**Changes:**
1. **Font size:** `CELL.fontSize` 12 → 14px; label cells 12 → 13px.
2. **Role column header:** add colored horizontal bar (3px height, role color) between role name and «N чел.». Color from `getRoleColor(roles, role)`. РП column gets `border-left` AND `border-right` in role color; all others `border-left` only. Column bg = `${roleColor}08` tint.
3. **Work type row labels:** truncate to ~18 chars with CSS `text-overflow: ellipsis; white-space: nowrap; overflow: hidden` + `<Tooltip title={fullLabel}>`. Max label width: 140px.
4. **Column separator style (Variant В):** each role column gets `border-left: 2px solid {roleColor}` + subtle bg tint. Last role column (РП) additionally gets `border-right: 2px solid {roleColor}`.
5. **Консультант column:** already dynamically rendered from `summary.roles` — appears automatically once employees have `consultant` role set. No explicit addition needed.

---

## С-2 · Баг: роль не сохраняется в «По сотрудникам»

**File:** `frontend/src/components/planning/PlanningCapacityPanel.tsx`

**Root cause:** `knownRole` is derived as:
```ts
const knownRole = e.role && CORE_ROLE_KEYS.includes(e.role) ? e.role : null;
```
`CORE_ROLE_KEYS = ['analyst', 'dev', 'qa']` — so `project_manager`, `consultant`, etc. always return `null`, making the role Select re-appear after save and looking like the role didn't persist.

**Fix:** Replace the CORE_ROLE_KEYS check with a lookup in the `roles` registry:
```ts
const knownRole = e.role && roles.some(r => r.code === e.role && r.is_active) ? e.role : null;
```
The `roles` array is already available in the component from `useRoles()`.

**Impact:** After fix, all active roles from the registry are treated as "known" — badge shows and Select disappears. Role colors and abbreviations for non-core roles use `getRoleColor` / `ROLE_SHORT_LOCAL` fallback (first 2 chars uppercased if not in map).

---

## С-3 · Элементы бэклога в Сценарии: убрать Риск, «Всего часов» + %

**File:** `frontend/src/pages/PlanningPage.tsx`

**Grid:** `const GRID = '40px 60px 1fr 150px 120px 280px 75px 100px 95px'`
Remove the last `95px` (Risk column). Update to:
`'40px 60px 1fr 150px 120px 280px 90px 100px'`

**Changes:**
- Remove `<span>Риск</span>` header and Risk tag cell from row render.
- Rename `<span>Всего</span>` → `<span>Всего часов</span>`.
- Under the total hours number add small text: `X% ресурса` where:
  - Numerator: `total` (sum of 4 role estimates for this allocation).
  - Denominator: `summary.available_for_backlog_total` from `useScenarioResourceSummary`.
  - `PlanningPage` already fetches the summary indirectly via `ScenarioResourceSummary` component — pass `available_for_backlog_total` down as a prop or fetch `useScenarioResourceSummary` directly in `PlanningPage`.

---

## С-4 · «Ресурс команды» — разворачиваемый блок

### Backend

**File:** `app/services/resource_base_service.py` — extend `ResourceSummary` dataclass and `compute_summary()`.

Add two fields to `ResourceSummary`:
```python
calendar_gross_by_role: dict[str, float]   # production calendar hours, no deductions at all
absence_days_by_employee: list[dict]       # [{employee_id, display_name, role, days: float}]
```

**`calendar_gross_by_role` computation:** For each employee, sum `day_hours(d)` for all days in quarter (no absence check, no mandatory). Then aggregate by role. This is a second pass before the absence-filtered loop already in the method.

**`absence_days_by_employee` computation:** For each employee, count working days (`day_hours(d) > 0`) where the employee is on absence.

**API schema:** `ResourceSummaryOut` in the planning endpoint — add `calendar_gross_by_role` and `absence_days_by_employee` fields.

### Frontend

**File:** `frontend/src/components/planning/PlanningCapacityPanel.tsx`

Replace the static «Ресурс команды» Card header with an `<Ant Design Collapse>` (single panel).

**Collapsed state (default):** Shows existing gauge (big number + progress bar).

**Expanded state:** Shows gauge + detail breakdown table:

```
                   | АН    | ПР    | ТС    | КН    | РП    | Итого
Брутто (календарь) | 480   | 1440  | 480   | 480   | 480   | 2880
− Отпуска          | −57   | −176  | −19   | −19   | −18   | −289
− Обяз. работы     | −63   | −190  | −69   | −69   | −139  | −530
= Доступно         | 360   | 1074  | 392   | 392   | 323   | 2541
  (N чел.)         | 1     | 3     | 1     | 1     | 1     |
─────────────────────────────────────────────────────────────────
Отпуска по сотрудникам:
  Иванов И.         АН · 7 дн
  Петрова Н.        ПР · 14 дн
```

**Data sources:**
- `calendar_gross_by_role` → Брутто row (new field from backend).
- Отпуска per role = `calendar_gross_by_role[role] − gross_by_role[role]` (gross_by_role already in ResourceSummary).
- Обяз. работы = sum of `work_type_rows[*].hours_by_role[role]` where `subtracts_from_pool=true`.
- Доступно = `available_by_role` (already in ResourceSummary).
- `absence_days_by_employee` → bottom section (new field from backend), shows employee name + role badge + days.

**Fetch:** `PlanningCapacityPanel` receives `resourceBase` (ResourceBase) as prop. Needs to also receive `summary` (ResourceSummaryOut). `PlanningPage` must call `useScenarioResourceSummary(scenarioId, !!scenario?.team)` directly (currently only `ScenarioResourceSummary` component calls it internally) and pass the result as `summary` prop to `PlanningCapacityPanel`.

### Total gauge fix (РП included)

`totalCapacity` currently sums only `CORE_ROLE_KEYS`. Change to sum **all** keys in `resourceBase.role_totals`:
```ts
const totalCapacity = Object.values(resourceBase.role_totals).reduce((s, v) => s + v, 0);
```
This makes the gauge «X / Y ч» match «= Доступно Итого» in the expanded table.

---

## С-5 · Согласованность «На бэклог» Итого

**Root cause:** `ResourceBase.compute()` subtracts only `subtracts_from_pool=True` rules from role totals. `ResourceSummary.compute_summary()` subtracts ALL work type rows from `available_by_role`. These may diverge if a work type has `subtracts_from_pool=False`.

**Fix:** In `compute_summary()`, when computing `available_by_role`, only subtract rows where `subtracts_from_pool=True`:
```python
mandatory_total = sum(
    row.hours_by_role.get(role, 0.0)
    for row in wt_rows
    if row.subtracts_from_pool
)
```
`wt_rows` already has `subtracts_from_pool` field on `WorkTypeSummaryRow` — just add the filter.

---

## Implementation Order

1. **С-2** (bug fix, no deps, unblocks QA column visibility)
2. **С-5** (bug fix, backend only, small change)
3. **С-4 backend** (ResourceSummary extension)
4. **С-1** (frontend, needs roles from С-2)
5. **С-3** (frontend, needs summary data from С-4 backend)
6. **С-4 frontend** (needs backend + С-3 data)
7. **Б-1** (frontend, independent)
8. **Б-2** (frontend, independent)
9. **Б-3** (frontend, independent)

---

## Files Changed

| File | Change |
|---|---|
| `app/services/resource_base_service.py` | Add `calendar_gross_by_role`, `absence_days_by_employee` to ResourceSummary |
| `app/api/endpoints/planning.py` | Add new fields to `ResourceSummaryOut` schema |
| `frontend/src/pages/BacklogPage.tsx` | Б-1, Б-2, Б-3 |
| `frontend/src/pages/PlanningPage.tsx` | С-3, pass summary to PlanningCapacityPanel |
| `frontend/src/components/planning/ScenarioResourceSummary.tsx` | С-1 |
| `frontend/src/components/planning/PlanningCapacityPanel.tsx` | С-2, С-4, С-5 (gauge) |
| `frontend/src/types/api.ts` | Add fields to ResourceSummaryOut |
