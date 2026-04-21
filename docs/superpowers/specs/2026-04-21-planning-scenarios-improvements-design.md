# Planning Scenarios — Improvements Design

**Date:** 2026-04-21  
**Scope:** Page `/planning`, scenario detail view  
**Approach:** Two-phase, single implementation plan

---

## Phase 1: Bug Fixes + UI

### 1. Rules not reflected in capacity table (bugs 1 & 3)

**Symptom:** After saving mandatory work rules on the Rules tab, the top capacity breakdown table still shows no mandatory work rows, and available-for-backlog hours remain unchanged.

**Root cause (to verify):** The capacity breakdown table fetches data from the backend after rules are saved. Either:
- The backend calculation does not read the current scenario's rules when computing mandatory work rows.
- The frontend does not invalidate the cached breakdown data after rules are saved, so stale data is shown.

**Fix:** Ensure the backend correctly reads scenario rules and subtracts them from norm hours when computing the breakdown. Ensure the frontend re-fetches the breakdown immediately after rules are saved.

---

### 2. Remove "Ёмкость по ролям" block (bug 2)

**Symptom:** The right sidebar shows two blocks with role information — "Ресурс по ролям" (with demand vs capacity bars) and a separate "Ёмкость по ролям" card below the employee list. They overlap in purpose.

**Fix:** Remove the lower "Ёмкость по ролям" card. "Ресурс по ролям" is sufficient.

---

### 3. "Роль не задана" for some employees (bug 4)

**Symptom:** In the "По сотрудникам" block, some employees (e.g. Копышков Николай, Медведева Надежда) show "роль не задана" instead of their role.

**Root cause:** The employee record in the database does not have a role assigned. These employees were likely added before roles were introduced.

**Fix:** Add an inline role picker in the "По сотрудникам" block — clicking "роль не задана" opens a dropdown to assign a role. Saves immediately. Role list comes from the roles directory.

---

### 4. Role cell visual redesign (bug 5)

**Chosen design:** Variant C + B saturation.

Each role (АН / ПР / ТС / ОПЭ) shown as a mini card:
- Background: 30% fill in role color
- Bottom border: 2px solid role color (full saturation)
- Top: subtle gradient fade from role color to transparent
- Label row: abbreviation (АН / ПР / ТС / ОПЭ) — small, uppercase, 80% opacity
- Value row: hours number (large, bold) + space + «ч» (small, 65% opacity, `margin-left: 4px`)
- Footer: percentage of total (small, muted)
- Empty cells (0 hours): same layout, value shows «—», overall opacity 25%

Role colors are dynamic (from roles directory, not hardcoded).

---

### 5. Backlog list height (bug 6)

**Symptom:** The backlog items list is cut off at an arbitrary height with a scrollbar appearing before the page boundary.

**Fix:** The list container gets `flex: 1` and `overflow-y: auto` so it fills all remaining vertical space in the page layout. The page outer wrapper is set to `height: 100vh` with `display: flex; flex-direction: column`.

---

### 6. Font size increase (bug 7)

**Scope:** All text on the planning page.

| Element | Before | After |
|---|---|---|
| Body text, row titles | 13px | 14px |
| Secondary labels, keys | 11px | 12px |
| Tiny hints (percentages, muted) | 10px | 11px |

---

## Phase 2: New Fields

### 7. Assignee (Исполнитель) — 8.1

**Data source:** Jira's built-in "Assignee" field on the linked Jira issue.

**Storage:** New field on the backlog item — nullable FK to Employee. Populated automatically during Jira sync and refresh-from-Jira. Can be overridden manually in the UI (independent of Jira).

**Eligible assignees:** Only employees with role Analyst, Project Manager, or Consultant. Other roles (Developer, QA) are not selectable.

**Display in backlog list:**
- New column «Исполнитель» after the title column
- Shows employee avatar (initials) + display name
- If not set: placeholder «—» in muted color

**Editing:**
- Click on the assignee cell → dropdown of eligible team members (filtered by team of the scenario) + clear option
- Saves immediately on selection
- Triggers capacity recalculation in the right panel (no page reload — client-side)

**Capacity effect:**
- In "По сотрудникам", each employee's bar now shows their personal demand = sum of their role's hours from items assigned to them and included in the scenario.
- Example: Фокеева Наталья (Аналитик) is assigned 3 items totalling 120 analyst-hours → her bar shows 120 demand.
- Items without an assignee: role hours go into the general role pool as before.
- Items where the assignee's role doesn't match a role column (shouldn't happen given the eligibility constraint): treated as unassigned for capacity purposes.

**Sync:** `refresh-from-jira` reads Jira's assignee account ID → matches to Employee by Jira account ID → stores the FK. If no match found (employee not in DB), field left null.

---

### 8. Customer (Заказчик) — 8.2

**Data source:** Jira custom field named «Заказчик (user)». Field ID discovered at implementation time via the Jira fields API by matching on field name.

**Storage:** New text field on the backlog item. Populated during Jira sync and refresh-from-Jira. Read-only in the UI (no manual override).

**Display:** New column «Заказчик» in the backlog list. Shows the display name from Jira. If not set: «—».

---

### 9. Cost type (Тип затрат) — 8.3

**Data source:** Jira custom field named «Тип затрат». Field ID discovered at implementation time. Expected values: «Change», «Run» (or Russian equivalents — verify at implementation).

**Storage:** New text field on the backlog item. Populated during Jira sync. Read-only in the UI.

**Display:** Small tag next to the initiative title. Two styles:
- Change: blue tag
- Run: green tag
- Not set: no tag shown

---

## Database migrations needed

1. `BacklogItem`: add `assignee_employee_id` (FK → Employee, nullable, with cascade set-null on employee delete)
2. `BacklogItem`: add `customer` (text, nullable)
3. `BacklogItem`: add `cost_type` (text, nullable)

All three in one migration.

---

## Frontend column layout (backlog list, updated)

| Col | Content | Width |
|---|---|---|
| ✓ | Checkbox | 32px |
| Прио | Priority badge | 48px |
| Идея | Title + Jira key + cost-type tag | flex 1 |
| Исполнитель | Avatar + name / dropdown | 160px |
| Заказчик | Name | 120px |
| АН / ПР / ТС / ОПЭ | Role mini-cells (new design) | 280px |
| Итого | Total hours | 70px |
| Накопленный итог | Cumulative | 70px |

---

## Out of scope

- Editing customer or cost type from the UI (Jira is the source of truth)
- Showing assignee history
- Multi-assignee per initiative
- Gantt view (separate roadmap item)
