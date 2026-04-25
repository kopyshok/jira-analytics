# Planning page UX polish — design

**Date:** 2026-04-25
**Scope:** `/planning` page only — frontend-only batch, no DB or API changes
**Sister doc (engineering plan):** `docs/superpowers/plans/2026-04-25-planning-ux-polish.md`

## Problem

The `/planning` page works but feels static. The PM uses it heavily — toggling 50+ backlog items in/out of a draft scenario, comparing scenarios, watching capacity drift toward deficit. Several pain points emerged from the recent bug-fix batch (commits `89b2e24`, `dfcca04`, `be0bdce`):

1. **No visual feedback on toggle.** Clicking a row updates the resource table silently; the PM has to scan the table to find what changed.
2. **No sense of capacity health at a glance.** The «Черновик» badge says nothing about whether the team is over-allocated. Deficit only appears when you scroll to the «На бэклог» row.
3. **Long backlogs are hard to scan.** With 30+ items in `initiatives_rfa`, default row height (~52px) means heavy scrolling. There's also no visual distinction between healthy items, no-estimate items, and items whose scenario is in deficit.
4. **No comparison story.** The PM frequently asks «как этот черновик отличается от утверждённого Q1?» or «давай положим рядом два варианта Q2». Today they open two browser tabs and eyeball it.
5. **The sticky resource table snaps shut on scroll** without a transition, which feels janky.
6. **Approval is anti-climactic.** Clicking «Утвердить» just changes a small badge; for what is the most important action on the page, the PM gets no visceral acknowledgement.

The features below address these in priority order. None are blocking — the page works without them — but together they meaningfully raise the bar of «this is a tool I want to use».

## Out of scope

- Backend changes. All comparison data is already exposed by `/planning/scenarios` + `/scenarios/{id}/allocations`.
- Mobile / narrow viewports. The page is desktop-only by design.
- Drag-and-drop reordering, inline estimate editing, search, keyboard shortcuts — separate batch.
- Light theme. The dashboard is permanently dark.
- New animation libraries (Framer Motion, react-spring, Lottie). All animations are CSS keyframes.

## Feature specifications

### F1 — Smooth collapse/expand of resource table

**Today:** When the user clicks «↑ Свернуть» or scrolls and the table sticks, the height changes instantly — content jumps.

**Want:** The vertical height shall transition over 280ms with a standard easing curve (`cubic-bezier(0.4, 0, 0.2, 1)`).

**Behavior:**
- Manual toggle (button click): smooth height collapse from full to 44px (or expand back).
- Scroll-triggered stick: same animation when the sticky kicks in. Reverse when user scrolls back to top.
- Content swaps instantly during animation. No need to crossfade.
- The sticky shadow (added on stick) fades in/out over 200ms.

**Acceptance:**
- No part of the transition exceeds 350ms.
- No layout reflow outside the table itself during the animation (other content on the page does not visibly jump).

### F2 — Cyan flash on backlog row toggle

**Today:** Clicking a row toggles `included` silently. The optimistic update changes the row's background opacity, but the change is subtle.

**Want:** When the user clicks a row to include/exclude, the row briefly flashes in `cyan` (`rgba(0, 201, 200, 0.35)` → transparent over 600ms).

**Behavior:**
- Triggered on every click that fires `toggleAllocation`, regardless of include→exclude or exclude→include direction.
- Animation runs on the row itself (full width).
- If the user clicks rapidly (multiple rows in quick succession), each row independently animates — no stacking weirdness.
- Animation does NOT run when the row appears/disappears due to data refetch — only on user-initiated toggle.

**Acceptance:**
- Flash is clearly visible against both included and excluded row backgrounds.
- Does not interfere with hover state (F4).

### F3 — Pulse role-column numbers on toggle

**Today:** When toggling, the role columns in the «На бэклог» row update silently. With 5 columns, the PM may not notice which one changed.

**Want:** When a toggle changes demand for one or more roles, those role columns' big numeric values pulse briefly (scale 1 → 1.18 → 1, 550ms, with a soft cyan text-shadow at peak).

**Behavior:**
- Determine affected roles using the same logic as `demandByAssigneeRole` in `frontend/src/utils/planning.ts`:
  - Analyst portion (ea + eo·r) goes to assignee role if it's `RP`/`project_manager`/`consultant`, else to `analyst`.
  - Dev portion always to `dev` (if non-zero).
  - QA portion always to `qa` (if non-zero).
- Skip pulse for portions that are zero (don't pulse `qa` for a task with no QA estimate).
- Pulse runs in both expanded and collapsed views of the resource table.
- Pulse animation does not affect the cell's progress bar or other siblings.

**Acceptance:**
- After toggling a task with `40 АН + 80 ПР + 40 ТС + 10 ОПЭ` assigned to Копышков (`role=RP`), the pulse runs on `RP`, `dev`, `qa` columns — not `analyst`.
- After toggling a task with only QA hours and no assignee, only the `qa` column pulses.

### F4 — Backlog row hover effect

**Today:** Hover does nothing.

**Want:** On hover, the row gains a 3px solid cyan left border and slides 2px to the right. Transition: `transform 0.15s, border-left-color 0.15s`.

**Behavior:**
- Effect applies to all rows (included or not).
- The slide is purely visual — no layout shift for sibling rows.
- Hover state composes correctly with F2 (flash) and F11 (color-coded borders): the cyan border replaces the default neutral border, but a yellow/red/green coding-border (F11) wins over hover cyan.

**Acceptance:**
- Hover is reversible — leaving the row immediately returns it to natural position.
- Does not trigger if the user holds the mouse still over the row (CSS-only, no JS).

### F5 — Smooth-scroll toggled row into view

**Today:** Toggling a row off-screen (e.g. clicking a barely-visible row at the bottom edge) leaves the row partially clipped.

**Want:** After `toggleAllocation`, if the row is not fully inside the visible area (top ≥ 60px, bottom ≤ viewport height − 20px), the page smooth-scrolls so the row is visible.

**Behavior:**
- Use `scrollIntoView({ behavior: 'smooth', block: 'nearest' })`.
- The 60px top margin reserves space for the sticky resource table when stuck.
- If the row is fully visible already, do nothing — no jiggle.
- Does NOT scroll to the row when toggle came from elsewhere (e.g. cache invalidation from another mutation). Only on direct user click.

**Acceptance:**
- Click a row at top of visible list → no scroll.
- Click a row partially clipped at bottom → smooth scroll moves it ~50px up so it's fully visible.

### F6 — Approve celebration overlay

**Today:** Clicking «Утвердить» fires a mutation; on success the badge changes from «Черновик» to «Утверждён». No animation.

**Want:** On `approve.onSuccess`, render a centered full-screen overlay (`position: fixed, inset: 0, zIndex: 9999`) with:
1. A 120px SVG circle that strokes-in over 0.5s
2. A checkmark inside it that strokes-in over 0.4s, starting at 0.45s
3. Text «Сценарий утверждён» below the circle (28px bold, cyan)
4. A semi-transparent dark backdrop (`rgba(13, 28, 51, 0.78)` with 2px blur)

The whole overlay fades in/out over 1.6s total via the `celebration-fade` keyframe (in: 0–20% of duration, hold: 20–80%, out: 80–100%).

**Behavior:**
- `pointer-events: none` on the overlay so it doesn't block underlying clicks.
- Auto-dismisses after 1700ms (just past the fade keyframe).
- Concurrent toast notification («Сценарий утверждён») still appears.
- Does NOT play if approval failed.
- If the user navigates away mid-animation, the overlay is unmounted (no orphan).

**Acceptance:**
- The check draws in (not a static `✓` that fades).
- The user can still interact with the page during the animation (it's not a modal blocker).

### F7 — Compact mode for backlog rows

**Today:** Each backlog row is 12px vertical padding + 14px font = ~52px tall. With 30 items the user scrolls a lot.

**Want:** A toggle button in the backlog Card's `extra` slot that switches between «Обычный» (12px / 14px) and «Компактный» (4px / 13px) modes. State persists in `localStorage` under key `planning_backlog_compact`.

**Behavior:**
- Toggle button uses the AntD `CompressOutlined` icon. Active state (compact on) renders with `type="primary"` (cyan fill).
- Both row and header padding shrinks proportionally to keep header alignment.
- Switching modes does not trigger row animation (no flash, no transition required — instant is fine).
- Works in conjunction with all other features (hover, color coding, etc.).

**Acceptance:**
- In compact mode, ~30 rows fit in a 1080p viewport without scrolling (vs. ~16 in normal).
- Reload preserves the user's choice.
- The button label reads «Обычный» when normal is active, «Компактный» when compact is active.

### F8 — Deficit badge next to scenario name

**Today:** The PM has to look at the «На бэклог» row of the resource table to know whether they're in deficit.

**Want:** A cluster of small chips next to the «Черновик» / «Утверждён» status badge, one chip per role in deficit, styled as `−45ч РП`. If no role is in deficit, render nothing.

**Behavior:**
- Calculation:
  - `available` = `resourceSummary.available_for_backlog_by_role` (already provided by backend).
  - `demand` = computed client-side via `demandByAssigneeRole` if employees are loaded, else `demandByRole`.
  - `deficit[role] = available[role] − demand[role]` if negative, then absolute value rounded to integer.
- Chip text: `−<hours>ч <short_role_label>`. Short labels: `АН`, `ПР`, `ТС`, `КС` (Консультант), `РП` (Руководитель проекта). For unknown role codes, take first 2 letters of the role label.
- Chip styling:
  - Background `rgba(245, 34, 45, 0.12)`, text `#ff7875`, border `1px solid <role_color>40` (40 = ~25% alpha).
  - Subtle pulse animation (`box-shadow: 0 0 0 0 → 4px rgba(250, 140, 22, 0.15)` over 2.4s, infinite).
  - Tooltip on hover: «<full role label>: дефицит <hours> ч».
- Chips appear in role order (analyst, dev, qa, consultant, RP, …).

**Acceptance:**
- Adding tasks until any role goes below 0 — chip appears for that role.
- Removing tasks until balance restored — chip disappears.
- Multiple roles in deficit → multiple chips, each correctly labeled.

### F9 — Progress bars in «На бэклог» cells

**Today:** The cell shows `«117 из 162»` for utilization, but reading two numbers and computing the ratio is mental work.

**Want:** Below the numeric remaining/available pair, render a thin (4px) horizontal bar showing utilization (`used / available`):
- Width: `min(100%, used/available · 100%)`. Width never exceeds 100% — overflow visualizes only via color, not length.
- Color:
  - cyan (`#00c9c8`) if `≤ 100%`
  - amber (`#fa8c16`) if `100% < x ≤ 110%`
  - red (`#f5222d`) if `> 110%`
- Track: `rgba(255, 255, 255, 0.06)` (subtle dark background).
- Width transitions over 300ms when value changes.

**Behavior:**
- Only rendered in the **expanded** view (collapsed strip is too thin).
- Only rendered when `used > 0` — when nothing is allocated, no bar is shown (there's nothing to visualize).
- Rendered in role columns only, NOT in the «Итого» column.
- The numeric cell is repositioned with `position: relative` and bottom-padding so the bar sits flush with the bottom edge.

**Acceptance:**
- Empty bar invisible (no bar at all) when nothing allocated.
- Bar fills proportionally as items are toggled.
- Color transitions smoothly when crossing 100% / 110% thresholds.

### F10 — Color-coded backlog rows

**Today:** All rows look the same except for the «В работе» tag and the included/not opacity.

**Want:** Each row gets a 3px left border whose color reflects its state:

| State | Color | Condition |
|---|---|---|
| no estimates | `#fa8c16` (amber) | `ea + ed + eq + eo == 0` |
| deficit | `#f5222d` (red) | `included == true` AND scenario has any role in deficit |
| in work | `#1d9e75` (green) | `source_category === 'quarterly_tasks'` |
| neutral | transparent | otherwise |

**Priority** (highest wins): `no estimates` > `deficit` > `in work` > `neutral`. Rationale:
- Missing estimates is a data-quality blocker — most actionable.
- Deficit is a planning issue — second priority.
- «В работе» is informational — last.

**Behavior:**
- The colored border replaces the default-transparent border on `.backlog-row`.
- On hover: the row's color-coded border stays the same (does NOT switch to cyan). Only neutral-state rows get cyan-on-hover.
- The flash animation (F2) overlays on top of the border without changing it.

**Acceptance:**
- A backlog item with all-zero estimates shows amber, even if it's «в работе».
- Including a task that pushes the scenario into deficit immediately turns its border red. Excluding it back returns it to whatever state applies.
- Color changes are not animated — they switch instantly on state change.

### F11 — Diff with last approved scenario

**Today:** No diff view. PM compares manually.

**Want:** Button «Diff» appears in the scenario header card's action bar when the current scenario is a draft. Clicking opens an AntD Drawer (`width: 620px`) titled «Diff: «<draft name>» vs последний утверждённый».

**Behavior:**
- Server-side data: `useScenarios(year, quarter, 'approved')` returns approved scenarios for the same year+quarter as the current draft. Pick the first one (`approvedList[0]`). If list is empty, drawer shows `<Empty description="Утверждённых сценариев на этот квартал ещё нет" />`.
- Comparison:
  - A = current draft's allocations
  - B = chosen approved scenario's allocations
  - Match by `backlog_item_id`. Only `included === true` items are considered on either side.
- Three sections:
  1. «Добавлено в черновик» — items in A not in B (green tag, count).
  2. «Удалено в черновике» — items in B not in A (red tag, count).
  3. «Без изменений» — items in both (neutral tag, count, dimmed display).
- Each row shows: title, jira_key (mono), estimate hours, assignee_display_name (if any).
- Empty section shows «—».
- Drawer is dismissible via close button or backdrop click (default AntD).

**Acceptance:**
- For a draft with one new task vs an approved scenario, the new task appears in «Добавлено».
- Tasks excluded from draft but present in approved appear in «Удалено».
- Task counts in tags match section content.
- If multiple approved scenarios exist for the quarter, the «first» is taken by API order; not a regression because the API returns most-recent first by default. (If this becomes a problem, follow-up adds a picker — out of scope for this batch.)

### F12 — Side-by-side scenario comparison

**Today:** No comparison view. PM opens two browser tabs and squints.

**Want:** Button «Сравнить» in the page header (next to «Новый сценарий»). Clicking opens an AntD Drawer (`width: 80vw`, very wide). Inside:
- Two AntD `Select` controls labeled «Сценарий A» and «Сценарий B». Both list all scenarios across all quarters; option label format: `«<name> · <quarter> <year>»` with a `✓` suffix for approved scenarios. Searchable.
- Below the selectors, a two-column layout:
  - Column A: lists allocations of scenario A
  - Column B: lists allocations of scenario B
- Within each column, common items are listed first (neutral background), then column-only items (left-border tinted: green for A-only, red for B-only).
- Common items show identically in both columns.
- Headers above each column: `<Tag color="cyan">A</Tag> N включено` (and same for B).

**Behavior:**
- The drawer can be opened with `initialScenarioId` (pre-fills A as current scenario). B starts empty.
- Until both are picked, drawer shows `<Empty description="Выберите оба сценария для сравнения" />`.
- While allocations are loading: `<Spin />`.
- Drawer is dismissible.
- The user can pick the same scenario for A and B; that just shows everything in the «common» section. Acceptable (no special handling).

**Acceptance:**
- Pick A=Q2 draft, B=Q1 approved → shows three groupings: common, A-only (green), B-only (red).
- Picking different scenarios refetches their allocations independently.
- Closing and re-opening preserves the most recent selection until page navigation.

## Visual design tokens

All new colors and timings reuse the existing `DARK_THEME` palette + new keyframes. No new color tokens are introduced. Specifically:

| Token | Value | Used by |
|---|---|---|
| Cyan primary | `#00c9c8` | flash, hover border, role pulse, progress bar (healthy), check anim |
| Amber | `#fa8c16` | progress bar (warning), no-estimates row border |
| Red | `#f5222d` | progress bar (over), deficit row border, deficit chip text |
| Green | `#1d9e75` | in-work row border, A-only diff tint |
| Backdrop dark | `rgba(13, 28, 51, 0.78)` | approve overlay |

Animation timings:

| Animation | Duration | Easing |
|---|---|---|
| Resource table collapse | 280ms | `cubic-bezier(0.4, 0, 0.2, 1)` |
| Row cyan flash | 600ms | `ease-out` |
| Role number pulse | 550ms | `ease-in-out` |
| Approve circle stroke | 500ms | `ease` |
| Approve check stroke | 400ms (delay 450ms) | `ease` |
| Approve overlay fade | 1600ms total | (keyframe-shaped) |
| Hover transform/border | 150ms | `ease` |
| Smooth scroll | browser default | `smooth` |
| Progress bar width | 300ms | `ease` |
| Deficit chip pulse | 2400ms loop | `ease-in-out` |

## Edge cases

- **Resource table sticks while user is mid-toggle.** The flash animation runs on a row that may now be hidden behind the sticky table. Acceptable — the resource table itself pulses (F3) so user gets feedback there.
- **Approve fails after celebration starts.** Doesn't happen — celebration is in `onSuccess` only. If error happens later (race), the user sees both the toast and the celebration; not ideal but acceptable.
- **Two approvals fired in quick succession** (button double-click). The mutation is not optimistic for approval; the second click hits «mutation in flight» and is benign. If both succeed, two celebrations queue.
- **Compact mode + role pulse.** Both apply normally; pulse uses `transform: scale` which is independent of cell padding.
- **Deficit chip with role=other.** The role registry has `is_active=true` for `other` but `counts_in_planning=false`. Such a role wouldn't appear in `available_for_backlog_by_role`, so no chip — correct.
- **Diff drawer when no approved scenario exists for the quarter.** Empty state shown, no error.
- **Compare drawer with same scenario picked for A and B.** All items appear in «common»; columns are identical. Acceptable; optionally we may add a soft warning «выбраны одинаковые сценарии» — left as a follow-up if the PM asks.
- **`assignee_role` from Jira display name lookup is wrong.** Possible if two employees share a name. Out of scope: the existing fix (commit `89b2e24`) is the authority.
- **Scenario without team selected.** The page already short-circuits to the team selector. None of these features render. Verified by reading existing PlanningPage flow.
- **Browser without `IntersectionObserver`.** Used only by the existing sticky logic, not by these features. Not a regression.
- **Reduced-motion preference.** Out of scope for this batch — none of the animations are essential to function. A follow-up could wrap each keyframe in `@media (prefers-reduced-motion: no-preference)`.

## Telemetry / metrics

None added. Single-user app, no analytics layer.

## Testing

- Frontend has no unit-test runner. Pure helpers (`computeDeficitByRole`, `diffScenarios`) are verified through their consumer drawers and the deficit chip on screen.
- Existing Playwright E2E (`frontend/e2e/`) tests the navigation and core CRUD flows; running them after this batch confirms no regression. Selector changes (e.g. for the new «Сравнить» button) are not in current test set, so no test updates needed.
- Visual verification via dev server is mandatory before push.

## Rollout

One PR direct to `main` (single-user app, no rollout staging). Per phase commits + push. Feature flags: not needed.

## Follow-ups (NOT in this batch)

- `prefers-reduced-motion` support for all animations.
- Approved-scenario picker in the diff drawer (when multiple exist for a quarter).
- Drag-and-drop priority reordering for backlog items.
- Inline estimate editing.
- Search / quick filters on backlog.
- Keyboard shortcuts (J/K/Space).
- Light theme.
