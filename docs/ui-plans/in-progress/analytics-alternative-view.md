# Analytics alternative detail view

Status: in-progress
Date: 2026-05-12
Owner: Codex

## Goal

Introduce a second visual mode for the Analytics page without replacing the existing mode.

The classic Analytics screen must remain available and usable. The new mode is an alternative detail workspace for task/worklog investigation.

## User-facing behavior

- Page: Analytics.
- Top control: segmented switch with two options:
  - `Текущий вид`
  - `Новый вид`
- Default mode: `Текущий вид`.
- User choice is persisted in browser storage.
- Fast rollback: switch back to `Текущий вид`.

## Files changed

- `frontend/src/pages/AnalyticsPage.tsx`
  - Adds the visual mode switch.
  - Keeps the classic layout untouched behind `Текущий вид`.
  - Renders the new workspace only when `Новый вид` is selected.
- `frontend/src/components/analytics/AnalyticsDetailWorkspace.tsx`
  - New alternative detail workspace.
  - Uses existing Analytics report data.
  - Uses existing filters and column settings.
  - Uses existing task context/category/worklog components in the right panel.
- `frontend/src/components/analytics/AnalyticsDetailWorkspace.css`
  - Styling for the alternative detail workspace.

## Existing functionality reused

- Existing Analytics report query.
- Existing employee, work type, category filters.
- Existing column settings.
- Existing task context block:
  - ancestors
  - siblings
  - children
  - child category editing
  - include/exclude from analysis
- Existing task category editor:
  - assigned vs inherited category
  - container warning
  - archive-category auto-exclude behavior
  - apply to subtree
- Existing issue worklogs block.

## Rollback

No backend rollback is required.

Fast rollback:

1. Open Analytics.
2. Select `Текущий вид`.

Full code rollback:

1. Remove the new workspace render from `AnalyticsPage.tsx`.
2. Delete:
   - `frontend/src/components/analytics/AnalyticsDetailWorkspace.tsx`
   - `frontend/src/components/analytics/AnalyticsDetailWorkspace.css`

Browser-storage key used by the switch:

```text
analytics:view-mode
```

Value:

```text
classic | detail
```

## Notes for next AI

- Do not remove the classic `AnalyticsTable` path while this is being tested.
- The alternative view intentionally reuses `IssueContextBlock`, `IssueCategorizer`, and `AnalyticsWorklogsBlock` instead of duplicating category/worklog logic.
- The classic inline/drawer worklog switch is hidden in the alternative mode because the right inspector always shows worklogs for the selected task.
- If the user approves the new view as primary later, change the default mode from `classic` to `detail`; do not delete the classic path until after a separate acceptance step.

## Verification checklist

- Frontend build passes.
- Analytics opens in classic mode by default for a new browser profile.
- Switch to `Новый вид` renders the alternative workspace.
- Switching back to `Текущий вид` restores the old layout.
- Clicking a task in the new table updates the right inspector.
- Category changes in the inspector still use the existing save path.
- Child-task category editing still works through the existing context block.
- Export button remains available in both modes.

## Current verification notes

2026-05-12:

- `npx eslint src/pages/AnalyticsPage.tsx src/components/analytics/AnalyticsDetailWorkspace.tsx` passes.
- `npm run build` is currently blocked by pre-existing unused variables in `frontend/src/components/resource-planning/GanttRows.tsx` at lines 172 and 839.
- The real app route `/analytics` opened locally, but the browser was on the login screen, so the new authenticated view still needs an in-app visual check after login.
