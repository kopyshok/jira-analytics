# Implementation Plan: Plane-style view for /resource-planning

**Spec:** [`2026-05-12-resource-planning-plane-view-design.md`](../specs/2026-05-12-resource-planning-plane-view-design.md)
**Date:** 2026-05-12
**Branch:** main (subagent-flow, not worktree)

## Discovery (from spec read)

- `ViewMode` actual values: `'portfolio' | 'two-level' | 'resource-track'` (NOT Gantt/List/Heatmap as spec said). Labels: «Портфель» / «Фазы» / «Ресурсы»
- `Segmented` lives at `ResourcePlanningPage.tsx:241-249`
- Heatmap is conditional below grid for `viewMode === 'two-level'`, not a separate mode
- Plane mockup is resource-centric (employees on left, bars on right) — matches `resource-track` style closest
- `AssignmentSidebar` accepts `assignment` prop and is already wired to `selectedAssignmentId` state
- `useGanttProjection` returns `assignments`, `conflicts`, `dependencies`, `employee_load`, `plan` — all data ready

## Steps

### 1. Extend ViewMode + add Plane button
- `frontend/src/components/resource-planning/GanttRows.tsx`: `ViewMode` += `'plane'`
- `ResourcePlanningPage.tsx:244-249`: add 4th option `{ label: 'Plane', value: 'plane', icon: <ExperimentOutlined /> }`
- Verify: `npm run lint` — no TS errors

### 2. Persist viewMode in localStorage
- `ResourcePlanningPage.tsx:42`: replace `useState<ViewMode>('two-level')` with read-from-`localStorage` initializer + write on change
- Key: `rp_view_mode`, fallback `'two-level'`
- Verify: F5 keeps selection

### 3. Add Inter font
- `frontend/index.html`: add `<link>` Google Fonts Inter (400/500/600/700)
- Verify: font loads in Network tab

### 4. Create `PlaneGantt.module.css` with all tokens
- Tokens: surface/bg/border/text/accent/role colors per spec
- Layout grid: `.shell` 3-zone (sidebar 280 / main flex)
- Components: `.header`, `.sidebar`, `.filterGroup`, `.grid`, `.row`, `.bar`, `.todayLine`, `.overload`
- All colors hardcoded — no theme deps
- Use `:global()` sparingly if AntD components leak in

### 5. Create `PlaneSidebar.tsx`
- Props: `{ employees, allEmployees, scenarios, filters, onFiltersChange }`
- 5 collapsible groups: Проект / Сотрудник / Роль / Период / Статус
- Each group: header with caret + checkbox list
- Search input in Сотрудник group
- «Сбросить всё» link at bottom
- No saved-views block per spec
- ~150 lines

### 6. Create `PlaneGantt.tsx`
- Props: same shape as `GanttChart` (`assignments`, `blocks`, `employees`, `quarter`, `year`, `onAssignmentClick`, etc)
- Internal structure:
  - Top: breadcrumb + plan name + dates
  - Body: `<PlaneSidebar>` + `<div class="grid">` schedule
  - Grid: compute week buckets from quarter/year (reuse `utils/gantt` helpers if available, otherwise inline 13-week calc)
  - Left column: employee rows (avatar initials + name + role)
  - Right: weekly columns header sticky + bar rows per employee
  - Bars: position by `started_at / completed_at` → week %, color by `role` field, click → `onAssignmentClick(id)`
  - Today line: vertical dashed indigo at current-week % position
  - Overload row: red triangle + tinted bg if `employee_load` for that employee > 1.1
- ~300 lines

### 7. Wire PlaneGantt into ResourcePlanningPage
- Replace `<GanttChart>` block when `viewMode === 'plane'`:
  ```tsx
  {gantt && !ganttLoading && planId && (
    viewMode === 'plane'
      ? <PlaneGantt {...sameProps} />
      : <GanttChart {...sameProps} />
  )}
  ```
- Skip ConflictPanel + Heatmap rendering in plane mode (clean Plane look)
- `AssignmentSidebar` стelf — keeps working same way

### 8. Polish + smoke
- Open `/resource-planning?plan_id=...` in browser
- Click Plane button — verify layout, palette, fonts
- Click a bar — verify `AssignmentSidebar` opens with correct data
- Toggle filters in sidebar — verify they apply
- F5 — verify Plane stays selected
- Switch to Фазы — verify classic Gantt unchanged

### 9. Lint + commit + push
- `npm run lint --prefix frontend` — green
- Commit message: `feat(resource-planning): Plane-style view (experiment)`
- Push origin/main

## Verification checklist (must pass before commit)

- [ ] Lint green
- [ ] Plane button visible in Segmented
- [ ] Click Plane → Plane layout renders without console errors
- [ ] Click bar → AssignmentSidebar opens
- [ ] Sidebar filters apply (at minimum: Сотрудник checkbox toggles row visibility)
- [ ] F5 keeps Plane selected
- [ ] Switch to «Фазы» → classic Gantt renders normally
- [ ] No visual breakage on other pages (Inter font scoped via `.planeShell *` rule)

## Out of scope (do NOT implement)

- Saved Views block
- Filter chips bar
- Drag/resize bars in Plane mode
- Dependency arrows in Plane mode
- ConflictPanel inside Plane view
- Heatmap inside Plane view
- List/Heatmap restyling
