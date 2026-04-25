# Planning Page UX Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 12 visual/UX improvements to the Planning page — animated transitions, capacity visualizations, scenario comparison views — to elevate it from functional to polished.

**Architecture:** Pure-frontend feature batch. Reuses existing keyframe pattern in `index.css`. Most tasks are CSS classes + minor React state. Two new components for scenario comparison. No backend changes needed (existing endpoints `/planning/scenarios` + `/scenarios/{id}/allocations` cover both diff and side-by-side modes via client-side comparison).

**Tech Stack:** React 19 + TypeScript, Ant Design 6 (icons, Drawer, Modal), inline-styles + CSS keyframes, TanStack Query (no new endpoints), no new deps.

---

## Files Overview

**Modify:**
- `frontend/src/index.css` — add keyframes (cyan-flash, role-pulse, check-circle, check-mark, deficit-pulse)
- `frontend/src/pages/PlanningPage.tsx` — backlog rows: hover/flash/scroll/color-coding, compact mode, deficit badge, approve overlay, comparison drawer entry points
- `frontend/src/components/planning/ScenarioResourceSummary.tsx` — smooth collapse animation, progress bars in На бэклог cells, role-pulse classes on toggle
- `frontend/src/utils/planning.ts` — `computeDeficitByRole` helper
- `frontend/src/types/api.ts` — no new fields

**Create:**
- `frontend/src/components/planning/ScenarioDeficitBadge.tsx` — chip cluster shown next to scenario name
- `frontend/src/components/planning/ApproveCelebration.tsx` — full-screen overlay with animated check
- `frontend/src/components/planning/ScenarioDiffPanel.tsx` — drawer showing draft-vs-last-approved diff
- `frontend/src/components/planning/ScenarioCompareDrawer.tsx` — drawer showing two arbitrary scenarios side-by-side
- `frontend/src/utils/scenarioDiff.ts` — pure diff logic (added / removed / unchanged)

---

## Conventions (read first)

- Existing keyframe naming: kebab-case classes (`flag-wave`, `icon-pulse`, …). Continue this style.
- Inline styles dominate this codebase — keep new styles inline; CSS file is keyframes-only.
- Colors come from `DARK_THEME` in `frontend/src/utils/constants.ts`. Existing palette: `cyanPrimary` (#00c9c8), `amber` (~#fa8c16), `textHint`, `textMuted`, etc. Don't introduce new colors.
- Russian labels everywhere user-facing; English for code identifiers.
- Use `App.useApp().notification` for toasts (not `notification` import — global instance is configured in `main.tsx`).
- `npm run build` is the lint+typecheck source of truth. Run after each task.
- After each task: `git add <files>` then `git commit` with conventional message. Do NOT push between tasks — push at end of each phase.

---

## Phase 1 — Foundation animations (4 tasks)

### Task 1: Add CSS keyframes for new animations

**Files:**
- Modify: `frontend/src/index.css` (append after existing `.icon-wiggle` block)

- [ ] **Step 1: Append keyframes**

Open `frontend/src/index.css`. Append at end of file:

```css
/* Backlog row toggle highlight */
@keyframes cyan-flash {
  0%   { background-color: rgba(0, 201, 200, 0.35); }
  100% { background-color: transparent; }
}
.cyan-flash {
  animation: cyan-flash 0.6s ease-out;
}

/* Pulse on role columns when their demand changes */
@keyframes role-pulse {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.18); text-shadow: 0 0 12px rgba(0, 201, 200, 0.6); }
}
.role-pulse {
  display: inline-block;
  animation: role-pulse 0.55s ease-in-out;
}

/* Approve celebration: SVG circle + checkmark draw-in */
@keyframes check-circle-draw {
  from { stroke-dashoffset: 226; }
  to   { stroke-dashoffset: 0; }
}
@keyframes check-mark-draw {
  from { stroke-dashoffset: 60; }
  to   { stroke-dashoffset: 0; }
}
@keyframes celebration-fade {
  0%   { opacity: 0; transform: scale(0.85); }
  20%  { opacity: 1; transform: scale(1); }
  80%  { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(0.95); }
}

/* Deficit badge subtle pulse to draw attention */
@keyframes deficit-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(250, 140, 22, 0.0); }
  50%      { box-shadow: 0 0 0 4px rgba(250, 140, 22, 0.15); }
}
.deficit-pulse {
  animation: deficit-pulse 2.4s ease-in-out infinite;
}

/* Hover effect on backlog rows: nudge right + cyan border */
.backlog-row {
  border-left: 3px solid transparent;
  transition: transform 0.15s ease, border-left-color 0.15s ease, background-color 0.15s ease;
}
.backlog-row:hover {
  transform: translateX(2px);
  border-left-color: #00c9c8;
}
/* Color coding overrides border-left when row is in a special state */
.backlog-row.row-state-no-estimates { border-left-color: #fa8c16; }
.backlog-row.row-state-deficit      { border-left-color: #f5222d; }
.backlog-row.row-state-in-work      { border-left-color: #1d9e75; }
.backlog-row.row-state-no-estimates:hover { border-left-color: #fa8c16; }
.backlog-row.row-state-deficit:hover      { border-left-color: #f5222d; }
.backlog-row.row-state-in-work:hover      { border-left-color: #1d9e75; }
```

- [ ] **Step 2: Build to confirm CSS file is valid**

Run from `frontend/`:
```bash
npm run build
```
Expected: build succeeds, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style(planning): add keyframes for row flash, role pulse, approve celebration, hover"
```

---

### Task 2: Smooth collapse transition for resource table

**Files:**
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

**Goal:** When user toggles collapsed/expanded (manually or via scroll-stuck), animate the height change instead of an instant swap.

**Approach:** Wrap the rendered Card in a `<div>` with `transition: max-height 0.28s cubic-bezier(0.4, 0, 0.2, 1)`. Use `max-height: 44px` collapsed, `max-height: 800px` expanded.

- [ ] **Step 1: Modify the `stickyWrap` helper to add transition wrapper**

In `frontend/src/components/planning/ScenarioResourceSummary.tsx`, find the `stickyWrap` function (added in previous commit) and replace it:

```tsx
const stickyWrap = (children: React.ReactNode) => (
  <>
    <div ref={sentinelRef} aria-hidden style={{ height: 1, marginBottom: -1 }} />
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        transition: 'box-shadow .2s ease',
        boxShadow: isStuck ? '0 6px 16px rgba(0,0,0,0.45)' : 'none',
      }}
    >
      <div
        style={{
          maxHeight: collapsed ? 44 : 800,
          overflow: 'hidden',
          transition: 'max-height 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {children}
      </div>
    </div>
  </>
);
```

- [ ] **Step 2: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 3: Manual smoke check**

Start dev server in another shell (`cd frontend && npm run dev`). Open `/planning`, click the «↑ Свернуть» / «↓ Развернуть» toggles. The height change should ease, not jump. Scroll the page; sticky entry should also animate smoothly. (No automated test for this — purely visual.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): animate resource-table collapse/expand height transition"
```

---

### Task 3: Backlog row hover effect

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** Add `backlog-row` class to each row in the backlog list. CSS in Task 1 already provides hover effect.

- [ ] **Step 1: Add class to row container**

In `frontend/src/pages/PlanningPage.tsx`, find the row rendering inside the backlog list (look for `(allocations ?? []).map((a) =>` and the wrapping `<div key={a.id} onClick={...}` element). Add `className="backlog-row"`:

```tsx
return (
  <div
    key={a.id}
    className="backlog-row"
    onClick={() => toggleAllocation(a)}
    style={{
      display: 'grid',
      gridTemplateColumns: GRID,
      columnGap: GRID_GAP,
      padding: '12px 14px',
      borderBottom: `1px solid ${DARK_THEME.border}`,
      alignItems: 'center',
      cursor: isDraft ? 'pointer' : 'default',
      background: a.included ? 'rgba(0,201,200,0.06)' : 'transparent',
      opacity: a.included ? 1 : 0.7,
      // Note: removed `transition: 'background .15s'` from inline — class now handles transitions.
    }}
  >
```

Remove the inline `transition: 'background .15s'` that previously existed on this element (it's now in the class).

- [ ] **Step 2: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 3: Manual smoke**

In dev server, hover a backlog row. Should nudge right by 2px and gain a cyan left border.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): backlog-row hover nudge + cyan accent border"
```

---

### Task 4: Compact mode toggle

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** Toggle button that shrinks backlog row padding from 12px → 4px and font size from 14 → 13. Persist in localStorage.

- [ ] **Step 1: Add state + toggle button**

Near the top of `PlanningPage` component (after existing `useState` hooks), add:

```tsx
const [compact, setCompact] = useState<boolean>(
  () => localStorage.getItem('planning_backlog_compact') === 'true',
);
const toggleCompact = () => {
  setCompact((prev) => {
    const next = !prev;
    localStorage.setItem('planning_backlog_compact', String(next));
    return next;
  });
};
```

- [ ] **Step 2: Render toggle in the backlog Card `extra` prop**

Find the backlog `<Card title="Элементы бэклога" ... extra={...}>`. Replace the existing `extra` content (currently a single `<span>`) with a flex row containing both the existing hint and the new toggle:

```tsx
extra={
  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
    <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
      {isApproved
        ? 'сценарий утверждён — отметки заблокированы'
        : 'клик по строке переключает включение'}
    </span>
    <Button
      size="small"
      type={compact ? 'primary' : 'default'}
      icon={<CompressOutlined />}
      onClick={toggleCompact}
      title={compact ? 'Обычный режим' : 'Компактный режим'}
    >
      {compact ? 'Компактный' : 'Обычный'}
    </Button>
  </div>
}
```

Add to the icon import line at top of file:
```tsx
import {
  CheckCircleOutlined, CheckSquareTwoTone, ClockCircleOutlined, CompressOutlined,
  DeleteOutlined, FlagFilled, PlusOutlined, ReloadOutlined, RollbackOutlined,
  ShopOutlined, UserOutlined,
} from '@ant-design/icons';
```

- [ ] **Step 3: Apply compact padding/font to row**

Find the row `<div className="backlog-row" ...>` from Task 3. Modify its style:

```tsx
style={{
  display: 'grid',
  gridTemplateColumns: GRID,
  columnGap: GRID_GAP,
  padding: compact ? '4px 14px' : '12px 14px',
  fontSize: compact ? 13 : 14,
  borderBottom: `1px solid ${DARK_THEME.border}`,
  alignItems: 'center',
  cursor: isDraft ? 'pointer' : 'default',
  background: a.included ? 'rgba(0,201,200,0.06)' : 'transparent',
  opacity: a.included ? 1 : 0.7,
}}
```

Also update header row padding to match (header is a separate `<div>` with `padding: '8px 14px'`):
```tsx
padding: compact ? '4px 14px' : '8px 14px',
```

- [ ] **Step 4: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 5: Manual smoke**

Click the toggle. Rows shrink visibly. Refresh page — state persists.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): compact mode toggle for backlog rows"
```

---

## Phase 2 — Toggle interactions (4 tasks)

### Task 5: Cyan flash on row toggle

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** When the user clicks a row to include/exclude, briefly flash the row in cyan.

**Approach:** Track a `Set<string>` of recently-toggled allocation IDs. Apply `cyan-flash` class to those rows for 600ms, then auto-clear.

- [ ] **Step 1: Add state for flashing rows**

Inside `PlanningPage`, near other `useState`:

```tsx
const [flashingIds, setFlashingIds] = useState<Set<string>>(() => new Set());

const flashRow = (allocId: string) => {
  setFlashingIds((prev) => {
    const next = new Set(prev);
    next.add(allocId);
    return next;
  });
  setTimeout(() => {
    setFlashingIds((prev) => {
      const next = new Set(prev);
      next.delete(allocId);
      return next;
    });
  }, 650);
};
```

- [ ] **Step 2: Trigger flash from `toggleAllocation`**

Find `toggleAllocation`:

```tsx
const toggleAllocation = (alloc: AllocationResponse) => {
  if (!scenarioId || !isDraft) return;
  flashRow(alloc.id);
  patchAlloc.mutate(
    { scenarioId, allocId: alloc.id, data: { included: !alloc.included } },
    { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
  );
};
```

- [ ] **Step 3: Apply class to flashing rows**

In the row `<div className="...">`, build the className conditionally:

```tsx
className={`backlog-row${flashingIds.has(a.id) ? ' cyan-flash' : ''}`}
```

- [ ] **Step 4: Build**

```bash
npm run build
```

- [ ] **Step 5: Manual smoke**

Click rows. Each click flashes the row cyan for ~0.6s.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): cyan-flash backlog rows on include/exclude toggle"
```

---

### Task 6: Pulse role-column numbers on toggle

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx` (track which roles to pulse)
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx` (consume pulse signal)

**Goal:** When a task is toggled, the role columns in «На бэклог» that received hours pulse briefly.

**Approach:** Lift a `pulsedRoles: Set<string>` state to PlanningPage. Pass into `ScenarioResourceSummary` as a prop. The component applies `role-pulse` class to the matching number span.

- [ ] **Step 1: Lift state in PlanningPage**

Below the `flashingIds` block from Task 5, add:

```tsx
const [pulsedRoles, setPulsedRoles] = useState<Set<string>>(() => new Set());

const pulseRoles = (roles: string[]) => {
  if (roles.length === 0) return;
  setPulsedRoles((prev) => {
    const next = new Set(prev);
    roles.forEach((r) => next.add(r));
    return next;
  });
  setTimeout(() => {
    setPulsedRoles((prev) => {
      const next = new Set(prev);
      roles.forEach((r) => next.delete(r));
      return next;
    });
  }, 600);
};
```

- [ ] **Step 2: Compute affected roles in `toggleAllocation`**

The role mapping mirrors `demandByAssigneeRole`. Add this helper near the top of `PlanningPage` (after imports, before the component):

```tsx
function rolesAffectedByAllocation(
  a: AllocationResponse,
  employees: { employee_id: string; role: string | null }[] | undefined,
): string[] {
  const ea = a.estimate_analyst_hours ?? 0;
  const ed = a.estimate_dev_hours ?? 0;
  const eq = a.estimate_qa_hours ?? 0;
  const eo = a.estimate_opo_hours ?? 0;
  const r = a.opo_analyst_ratio ?? 0.5;
  const emp = employees?.find((e) => e.employee_id === a.assignee_employee_id);
  const role = emp?.role ?? a.assignee_role ?? null;
  const isAnalystSubstitute =
    role === 'RP' || role === 'project_manager' || role === 'consultant';
  const analystTarget = isAnalystSubstitute ? (role as string) : 'analyst';
  const out: string[] = [];
  if (ea + eo * r > 0) out.push(analystTarget);
  if (ed + eo * (1 - r) > 0) out.push('dev');
  if (eq > 0) out.push('qa');
  return out;
}
```

Then in `toggleAllocation`, after `flashRow`:

```tsx
const toggleAllocation = (alloc: AllocationResponse) => {
  if (!scenarioId || !isDraft) return;
  flashRow(alloc.id);
  pulseRoles(rolesAffectedByAllocation(alloc, resourceBase?.employees));
  patchAlloc.mutate(
    { scenarioId, allocId: alloc.id, data: { included: !alloc.included } },
    { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
  );
};
```

- [ ] **Step 3: Pass `pulsedRoles` to ScenarioResourceSummary**

In `<ScenarioResourceSummary ...>`, add the prop:

```tsx
<ScenarioResourceSummary
  scenarioId={scenarioId}
  enabled={!!scenario.team}
  allocations={allocations ?? []}
  employees={resourceBase?.employees}
  pulsedRoles={pulsedRoles}
/>
```

- [ ] **Step 4: Accept and use the prop in ScenarioResourceSummary**

In `frontend/src/components/planning/ScenarioResourceSummary.tsx`, extend `Props`:

```tsx
interface Props {
  scenarioId: string;
  enabled: boolean;
  allocations?: AllocationResponse[];
  employees?: ResourceEmployee[];
  pulsedRoles?: Set<string>;
}
```

Add to destructured args:
```tsx
export default function ScenarioResourceSummary({ scenarioId, enabled, allocations, employees, pulsedRoles }: Props) {
```

In the «На бэклог» row, find the role mapping (`{summary.roles.map((role) => { ... return <div ...><...> ... )` — there are TWO places: collapsed view and expanded view). For each role's number `<span>`/`<div>`, conditionally add the `role-pulse` class. Also make sure the same applies for `analystTarget` synonyms (analyst, RP, consultant, project_manager).

In the **expanded** row, the cell currently looks like:
```tsx
<div
  key={role}
  style={{ ...CELL, ...roleBorderStyle(role), background: ..., color: ..., fontWeight: 700, fontSize: 17, whiteSpace: 'nowrap' }}
>
  {hasUsed ? (
    <>
      {remaining.toLocaleString('ru')}
      <span style={{ fontSize: 12, ... }}>из {Math.round(avail).toLocaleString('ru')}</span>
    </>
  ) : (
    Math.round(avail).toLocaleString('ru')
  )}
  ...
</div>
```

Wrap the numeric content in a span with conditional class:

```tsx
<div key={role} style={{ ...CELL, ...roleBorderStyle(role), background: ..., color: ..., fontWeight: 700, fontSize: 17, whiteSpace: 'nowrap' }}>
  <span className={pulsedRoles?.has(role) ? 'role-pulse' : undefined}>
    {hasUsed ? (
      <>
        {remaining.toLocaleString('ru')}
        <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
          из {Math.round(avail).toLocaleString('ru')}
        </span>
      </>
    ) : (
      Math.round(avail).toLocaleString('ru')
    )}
  </span>
  {isExternal && (
    <span style={{ fontSize: 11, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
      внешний
    </span>
  )}
</div>
```

In the **collapsed** row, the cell looks like:
```tsx
<span style={{ fontSize: 14, fontWeight: 700, fontFamily: FONTS.mono, color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}>
  {hasUsed ? remaining : Math.round(avail)} ч
</span>
```

Wrap with class:
```tsx
<span
  className={pulsedRoles?.has(role) ? 'role-pulse' : undefined}
  style={{ fontSize: 14, fontWeight: 700, fontFamily: FONTS.mono, color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}
>
  {hasUsed ? remaining : Math.round(avail)} ч
</span>
```

- [ ] **Step 5: Build**

```bash
npm run build
```

- [ ] **Step 6: Manual smoke**

Toggle a backlog item. The role columns it impacts pulse briefly.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): pulse role-column numbers when their demand changes"
```

---

### Task 7: Smooth-scroll to toggled row if out of viewport

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** When `toggleAllocation` runs and the row is outside the visible scroll area, scroll it into view smoothly.

- [ ] **Step 1: Add ref map for rows**

Inside `PlanningPage`, near other `useRef`:

```tsx
const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
```

- [ ] **Step 2: Attach refs to rows**

In the row JSX:

```tsx
<div
  key={a.id}
  ref={(el) => {
    if (el) rowRefs.current.set(a.id, el);
    else rowRefs.current.delete(a.id);
  }}
  className={`backlog-row${flashingIds.has(a.id) ? ' cyan-flash' : ''}`}
  ...
>
```

- [ ] **Step 3: Scroll into view on toggle**

Add helper:
```tsx
const scrollRowIntoView = (allocId: string) => {
  const el = rowRefs.current.get(allocId);
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const fullyVisible = rect.top >= 60 && rect.bottom <= window.innerHeight - 20;
  if (!fullyVisible) {
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
};
```

Call from `toggleAllocation` (after `pulseRoles`):
```tsx
scrollRowIntoView(alloc.id);
```

- [ ] **Step 4: Build**

- [ ] **Step 5: Manual smoke**

Scroll backlog so first row is offscreen above. Click a row that's barely visible at the bottom edge — it should smooth-scroll into view.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): smooth-scroll toggled row into view if clipped"
```

---

### Task 8: Approve animation overlay

**Files:**
- Create: `frontend/src/components/planning/ApproveCelebration.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** When the user clicks «Утвердить» and the mutation succeeds, show a 1.6s full-screen overlay with an SVG checkmark drawing in.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/planning/ApproveCelebration.tsx`:

```tsx
import { DARK_THEME } from '../../utils/constants';

interface Props {
  visible: boolean;
}

export default function ApproveCelebration({ visible }: Props) {
  if (!visible) return null;
  return (
    <div
      aria-hidden
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        background: 'rgba(13, 28, 51, 0.78)',
        backdropFilter: 'blur(2px)',
        animation: 'celebration-fade 1.6s ease forwards',
        pointerEvents: 'none',
      }}
    >
      <svg width="120" height="120" viewBox="0 0 80 80">
        <circle
          cx="40"
          cy="40"
          r="36"
          fill="none"
          stroke={DARK_THEME.cyanPrimary}
          strokeWidth="3"
          strokeDasharray="226"
          strokeDashoffset="226"
          style={{ animation: 'check-circle-draw 0.5s ease forwards' }}
        />
        <path
          d="M22 40 L36 54 L60 28"
          fill="none"
          stroke={DARK_THEME.cyanPrimary}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="60"
          strokeDashoffset="60"
          style={{ animation: 'check-mark-draw 0.4s ease 0.45s forwards' }}
        />
      </svg>
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: DARK_THEME.cyanPrimary,
          letterSpacing: 0.5,
        }}
      >
        Сценарий утверждён
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire into PlanningPage**

Add import in `PlanningPage.tsx`:

```tsx
import ApproveCelebration from '../components/planning/ApproveCelebration';
```

Add state:
```tsx
const [celebrate, setCelebrate] = useState(false);
```

Find the `handleApprove` function (or the inline `onClick` of the «Утвердить» button — look at the call to `approve.mutate`). Modify the success callback:

```tsx
const handleApprove = () => {
  if (!scenarioId) return;
  approve.mutate(scenarioId, {
    onSuccess: () => {
      setCelebrate(true);
      setTimeout(() => setCelebrate(false), 1700);
      notification.success({ title: 'Сценарий утверждён' });
    },
    onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
  });
};
```

(If `handleApprove` doesn't exist as a named function, locate the existing approve invocation and adapt.)

Render the overlay anywhere in the return tree (top-level, e.g., right before the closing `</>`):

```tsx
<ApproveCelebration visible={celebrate} />
```

- [ ] **Step 3: Build**

- [ ] **Step 4: Manual smoke**

Approve a draft scenario. The cyan check draws in for ~1.5s, then fades.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/ApproveCelebration.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): animated checkmark celebration on scenario approval"
```

---

## Phase 3 — Capacity visualizations (4 tasks)

### Task 9: `computeDeficitByRole` helper

**Files:**
- Modify: `frontend/src/utils/planning.ts`

**Goal:** Pure function: given `summary.available_for_backlog_by_role` and `roleDemand`, return `{ role: deficitHours }` for roles with negative remaining.

(Note: frontend has no unit-test runner — only Playwright E2E. Skip writing tests for this helper; correctness is verified through the consumer in Task 10. If you want, add a short doctest-style example block in the JSDoc.)

- [ ] **Step 1: Implement**

Append to `frontend/src/utils/planning.ts`:

```ts
/**
 * Возвращает дефицит по ролям: для ролей, где demand > avail, вернёт
 * положительное число часов недостачи. Роли без дефицита в результате
 * не присутствуют. Округляет до целого.
 *
 * @example
 *   computeDeficitByRole({ analyst: 100 }, { analyst: 120 }) // { analyst: 20 }
 *   computeDeficitByRole({ analyst: 100 }, { analyst: 80 })  // {}
 */
export function computeDeficitByRole(
  available: Record<string, number>,
  demand: Record<string, number>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const role of Object.keys(available)) {
    const used = demand[role] ?? 0;
    const remaining = available[role] - used;
    if (remaining < 0) {
      out[role] = Math.round(-remaining);
    }
  }
  return out;
}
```

- [ ] **Step 2: Build to confirm types compile**

```bash
npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/planning.ts
git commit -m "feat(planning): computeDeficitByRole helper"
```

---

### Task 10: Deficit badge next to scenario name

**Files:**
- Create: `frontend/src/components/planning/ScenarioDeficitBadge.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** Show small chips like `−45ч АН`, `−10ч РП` next to the scenario name in the header card. Hidden if no deficit.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/planning/ScenarioDeficitBadge.tsx`:

```tsx
import { Tooltip } from 'antd';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';

interface Props {
  deficit: Record<string, number>; // role_code -> hours short
}

export default function ScenarioDeficitBadge({ deficit }: Props) {
  const { data: roles = [] } = useRoles();
  const entries = Object.entries(deficit);
  if (entries.length === 0) return null;
  return (
    <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      {entries.map(([role, hours]) => {
        const color = getRoleColor(roles, role);
        const label = getRoleLabel(roles, role);
        const shortLabel =
          role === 'RP' ? 'РП' :
          role === 'project_manager' ? 'РП' :
          role === 'analyst' ? 'АН' :
          role === 'dev' ? 'ПР' :
          role === 'qa' ? 'ТС' :
          role === 'consultant' ? 'КС' :
          (label || role).slice(0, 2);
        return (
          <Tooltip key={role} title={`${label}: дефицит ${hours} ч`}>
            <span
              className="deficit-pulse"
              style={{
                fontFamily: FONTS.mono,
                fontSize: 11,
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 10,
                background: 'rgba(245, 34, 45, 0.12)',
                color: '#ff7875',
                border: `1px solid ${color}40`,
                whiteSpace: 'nowrap',
              }}
            >
              −{hours}ч {shortLabel}
            </span>
          </Tooltip>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Wire into PlanningPage**

Add import:
```tsx
import ScenarioDeficitBadge from '../components/planning/ScenarioDeficitBadge';
import { computeDeficitByRole, demandByAssigneeRole, demandByRole } from '../utils/planning';
```

(If `demandByAssigneeRole`/`demandByRole` are not yet imported in PlanningPage, add them.)

Inside `PlanningPage` after `resourceSummary` is defined, compute deficit:

```tsx
const deficit = useMemo(() => {
  if (!resourceSummary || !allocations) return {};
  const demand =
    resourceBase?.employees && resourceBase.employees.length > 0
      ? demandByAssigneeRole(allocations, resourceBase.employees)
      : demandByRole(allocations);
  return computeDeficitByRole(resourceSummary.available_for_backlog_by_role, demand);
}, [resourceSummary, allocations, resourceBase]);
```

(Make sure `useMemo` is in imports from `react`.)

In the scenario header card, find the existing `<Badge status=... text=... />` (which shows «Утверждён» / «Черновик»). Right after it, render the deficit badge:

```tsx
<Badge
  status={isApproved ? 'success' : 'processing'}
  text={isApproved ? 'Утверждён' : 'Черновик'}
/>
<ScenarioDeficitBadge deficit={deficit} />
```

- [ ] **Step 3: Build**

- [ ] **Step 4: Manual smoke**

Add a backlog item that exceeds capacity (or include enough items). Chip(s) should appear next to «Черновик», pulsing subtly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/ScenarioDeficitBadge.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): deficit chips next to scenario name (-45ч РП style)"
```

---

### Task 11: Progress bars in «На бэклог» cells

**Files:**
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

**Goal:** Inside each role cell of the «На бэклог» row (expanded view only), render a thin horizontal bar at the bottom showing utilization (`used / available`). Cyan when ≤100%, amber 100-110%, red >110%.

- [ ] **Step 1: Add the bar to each role cell**

In the **expanded** «На бэклог» row, find `{summary.roles.map((role) => { ... return <div key={role} style={{ ...CELL, ...roleBorderStyle(role), background: ... }} >`. Replace its contents to include a bar at the bottom:

```tsx
{summary.roles.map((role) => {
  const avail = summary.available_for_backlog_by_role[role] ?? 0;
  const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
  const remaining = Math.round(avail - used);
  const isDeficit = remaining < 0;
  const isExternal = role === 'qa' && summary.external_qa_hours != null;
  const hasUsed = used > 0;
  const utilPct = avail > 0 ? Math.min(150, (used / avail) * 100) : 0;
  const barColor =
    utilPct > 110 ? '#f5222d' :
    utilPct > 100 ? '#fa8c16' :
    DARK_THEME.cyanPrimary;
  return (
    <div
      key={role}
      style={{
        ...CELL,
        ...roleBorderStyle(role),
        background: isDeficit ? 'rgba(255,165,0,0.08)' : 'rgba(0,201,200,0.1)',
        color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
        fontWeight: 700,
        fontSize: 17,
        whiteSpace: 'nowrap' as const,
        position: 'relative' as const,
        paddingBottom: 12, // make room for bar
      }}
    >
      <span className={pulsedRoles?.has(role) ? 'role-pulse' : undefined}>
        {hasUsed ? (
          <>
            {remaining.toLocaleString('ru')}
            <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
              из {Math.round(avail).toLocaleString('ru')}
            </span>
          </>
        ) : (
          Math.round(avail).toLocaleString('ru')
        )}
      </span>
      {isExternal && (
        <span style={{ fontSize: 11, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
          внешний
        </span>
      )}
      {hasUsed && (
        <div
          style={{
            position: 'absolute',
            bottom: 4,
            left: 8,
            right: 8,
            height: 4,
            background: 'rgba(255,255,255,0.06)',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${Math.min(100, utilPct)}%`,
              background: barColor,
              transition: 'width 0.3s ease, background-color 0.3s ease',
            }}
          />
        </div>
      )}
    </div>
  );
})}
```

(This task assumes Task 6 has already wrapped numeric content in a `<span className={pulsedRoles ...}>`. If task ordering swapped, merge accordingly.)

- [ ] **Step 2: Build**

- [ ] **Step 3: Manual smoke**

Toggle items to put the team near or over capacity in some role. Bar fills to that percentage, color shifts amber/red.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): utilization progress bars in На-бэклог cells"
```

---

### Task 12: Color coding for backlog rows

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** Add state-based class to each row:
- `row-state-no-estimates` (yellow) — task has zero total estimate
- `row-state-deficit` (red) — task is included AND scenario has any role in deficit
- `row-state-in-work` (green) — task has source_category === 'quarterly_tasks' (the existing «В работе» badge)

Priority (highest wins): no_estimates > deficit > in_work.

- [ ] **Step 1: Add helper to compute row class**

Inside `PlanningPage`, after `deficit` from Task 10:

```tsx
const hasAnyDeficit = Object.keys(deficit).length > 0;

const rowStateClass = (a: AllocationResponse): string => {
  const total =
    (a.estimate_analyst_hours ?? 0) +
    (a.estimate_dev_hours ?? 0) +
    (a.estimate_qa_hours ?? 0) +
    (a.estimate_opo_hours ?? 0);
  if (total <= 0) return 'row-state-no-estimates';
  if (a.included && hasAnyDeficit) return 'row-state-deficit';
  if (a.source_category === 'quarterly_tasks') return 'row-state-in-work';
  return '';
};
```

- [ ] **Step 2: Apply class to row**

Update the row's className to include the state class:

```tsx
className={[
  'backlog-row',
  flashingIds.has(a.id) ? 'cyan-flash' : '',
  rowStateClass(a),
].filter(Boolean).join(' ')}
```

- [ ] **Step 3: Build**

- [ ] **Step 4: Manual smoke**

Verify left-border colors:
- An item without any АН/ПР/ТС/ОПЭ estimate shows yellow border.
- A "В работе" item with normal estimates shows green.
- When scenario is in deficit, all included rows show red (overrides green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): color-code backlog rows (no-estimates / deficit / in-work)"
```

---

### Phase 3 push

After Tasks 9-12 are committed:

```bash
git push origin main
```

---

## Phase 4 — Comparison views (3 tasks)

### Task 13: `scenarioDiff` utility

**Files:**
- Create: `frontend/src/utils/scenarioDiff.ts`

**Goal:** Pure function: given two arrays of `AllocationResponse` (each scenario's included items), return `{ onlyInA, onlyInB, common }` keyed by `backlog_item_id`. Used by Tasks 14 and 15.

(Note: frontend has no unit-test runner — only Playwright E2E. The function is consumed by visible drawers, so correctness is verified by smoke-testing those.)

- [ ] **Step 1: Implement**

Create `frontend/src/utils/scenarioDiff.ts`:

```ts
import type { AllocationResponse } from '../types/api';

export interface ScenarioDiffResult {
  onlyInA: AllocationResponse[];
  onlyInB: AllocationResponse[];
  common: { left: AllocationResponse; right: AllocationResponse }[];
}

/**
 * Сравнивает два списка раскладок по `backlog_item_id`. Учитываются только
 * включённые в сценарий элементы (`included === true`).
 *
 * Returns:
 *   - onlyInA  — присутствуют только в `left`
 *   - onlyInB  — присутствуют только в `right`
 *   - common   — пары (left, right) с одинаковым backlog_item_id
 */
export function diffScenarios(
  left: AllocationResponse[],
  right: AllocationResponse[],
): ScenarioDiffResult {
  const leftIncluded = left.filter((a) => a.included);
  const rightIncluded = right.filter((a) => a.included);
  const rightMap = new Map(rightIncluded.map((a) => [a.backlog_item_id, a]));
  const onlyInA: AllocationResponse[] = [];
  const common: { left: AllocationResponse; right: AllocationResponse }[] = [];
  const seen = new Set<string>();
  for (const l of leftIncluded) {
    const r = rightMap.get(l.backlog_item_id);
    if (r) {
      common.push({ left: l, right: r });
      seen.add(l.backlog_item_id);
    } else {
      onlyInA.push(l);
    }
  }
  const onlyInB = rightIncluded.filter((a) => !seen.has(a.backlog_item_id));
  return { onlyInA, onlyInB, common };
}
```

- [ ] **Step 2: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/scenarioDiff.ts
git commit -m "feat(planning): scenarioDiff utility"
```

---

### Task 14: Diff-with-last-approved drawer

**Files:**
- Create: `frontend/src/components/planning/ScenarioDiffPanel.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** When viewing a draft scenario, show a button «Diff с утверждённым». Clicking opens a Drawer with three sections: «Добавлено в черновик», «Удалено в черновике», «Без изменений».

- [ ] **Step 1: Create the panel component**

Create `frontend/src/components/planning/ScenarioDiffPanel.tsx`:

```tsx
import { Drawer, Empty, Spin, Tag } from 'antd';
import { useMemo } from 'react';
import { useScenarios, useScenarioAllocations } from '../../hooks/usePlanning';
import { diffScenarios } from '../../utils/scenarioDiff';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, ScenarioResponse } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  draftScenario: ScenarioResponse;
  draftAllocations: AllocationResponse[];
}

const SECTION: React.CSSProperties = {
  marginTop: 18,
};
const SECTION_TITLE: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: DARK_THEME.textMuted,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 8,
};

export default function ScenarioDiffPanel({
  open, onClose, draftScenario, draftAllocations,
}: Props) {
  // Take the most-recently-created approved scenario for same year+quarter.
  const { data: approvedList } = useScenarios(
    String(draftScenario.year),
    draftScenario.quarter,
    'approved',
  );
  const lastApproved = useMemo(() => {
    if (!approvedList || approvedList.length === 0) return null;
    // Backend currently sorts by created_at desc by default in /scenarios; if
    // that changes, sort here. For safety: pick first.
    return approvedList[0];
  }, [approvedList]);
  const { data: approvedAllocs, isLoading } = useScenarioAllocations(
    lastApproved?.id ?? null,
  );

  const diff = useMemo(() => {
    if (!approvedAllocs) return null;
    // A = draft, B = approved
    return diffScenarios(draftAllocations, approvedAllocs);
  }, [draftAllocations, approvedAllocs]);

  return (
    <Drawer
      title={`Diff: «${draftScenario.name}» vs последний утверждённый`}
      open={open}
      onClose={onClose}
      width={620}
    >
      {!lastApproved ? (
        <Empty description="Утверждённых сценариев на этот квартал ещё нет" />
      ) : isLoading || !diff ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
            Сравниваем с: <strong style={{ color: DARK_THEME.textPrimary }}>{lastApproved.name}</strong>
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag color="green">Добавлено в черновик</Tag> {diff.onlyInA.length}
            </div>
            {diff.onlyInA.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.onlyInA.map((a) => <DiffRow key={a.id} alloc={a} />)
            )}
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag color="red">Удалено в черновике</Tag> {diff.onlyInB.length}
            </div>
            {diff.onlyInB.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.onlyInB.map((a) => <DiffRow key={a.id} alloc={a} />)
            )}
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag>Без изменений</Tag> {diff.common.length}
            </div>
            {diff.common.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.common.map(({ left }) => <DiffRow key={left.id} alloc={left} muted />)
            )}
          </div>
        </>
      )}
    </Drawer>
  );
}

function DiffRow({ alloc, muted }: { alloc: AllocationResponse; muted?: boolean }) {
  return (
    <div
      style={{
        padding: '8px 10px',
        marginBottom: 4,
        background: muted ? 'transparent' : 'rgba(255,255,255,0.03)',
        borderRadius: 4,
        opacity: muted ? 0.65 : 1,
        fontSize: 13,
      }}
    >
      <div style={{ color: DARK_THEME.textPrimary }}>
        {alloc.title}
      </div>
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: DARK_THEME.textMuted, marginTop: 2 }}>
        {alloc.jira_key && <span style={{ fontFamily: FONTS.mono }}>{alloc.jira_key}</span>}
        {alloc.estimate_hours != null && <span>{Math.round(alloc.estimate_hours)} ч</span>}
        {alloc.assignee_display_name && <span>· {alloc.assignee_display_name}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire button + drawer in PlanningPage**

In `PlanningPage.tsx` add import:
```tsx
import ScenarioDiffPanel from '../components/planning/ScenarioDiffPanel';
import { DiffOutlined } from '@ant-design/icons';
```

Add state:
```tsx
const [diffOpen, setDiffOpen] = useState(false);
```

In the scenario header card's `<Space>` (the one with «Синк», «Утвердить», «Экспорт», «Удалить»), insert before «Экспорт»:

```tsx
{isDraft && (
  <Tooltip title="Сравнить с последним утверждённым">
    <Button
      icon={<DiffOutlined />}
      size="small"
      onClick={() => setDiffOpen(true)}
    >
      Diff
    </Button>
  </Tooltip>
)}
```

Render the drawer at the bottom of the page tree:
```tsx
{scenario && allocations && (
  <ScenarioDiffPanel
    open={diffOpen}
    onClose={() => setDiffOpen(false)}
    draftScenario={scenario}
    draftAllocations={allocations}
  />
)}
```

- [ ] **Step 3: Build**

- [ ] **Step 4: Manual smoke**

Approve a scenario, create a new draft for same quarter, modify items, click «Diff». Drawer shows added/removed/common.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/ScenarioDiffPanel.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): drawer showing diff between draft and last approved scenario"
```

---

### Task 15: Side-by-side scenario comparison drawer

**Files:**
- Create: `frontend/src/components/planning/ScenarioCompareDrawer.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx`

**Goal:** «Сравнить» button in the page header (next to the scenario selector). Opens a Drawer where the user picks ANY two scenarios from the list and views them side-by-side: two columns of allocations, with rows that exist in only one side highlighted (green / red).

- [ ] **Step 1: Create the drawer**

Create `frontend/src/components/planning/ScenarioCompareDrawer.tsx`:

```tsx
import { Drawer, Empty, Select, Spin, Tag } from 'antd';
import { useMemo, useState } from 'react';
import { useScenarios, useScenarioAllocations } from '../../hooks/usePlanning';
import { diffScenarios } from '../../utils/scenarioDiff';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  initialScenarioId?: string;
}

const COL: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: 8,
};

export default function ScenarioCompareDrawer({ open, onClose, initialScenarioId }: Props) {
  const { data: scenarios = [] } = useScenarios();
  const [aId, setAId] = useState<string | undefined>(initialScenarioId);
  const [bId, setBId] = useState<string | undefined>();
  const { data: allocsA, isLoading: la } = useScenarioAllocations(aId ?? null);
  const { data: allocsB, isLoading: lb } = useScenarioAllocations(bId ?? null);

  const diff = useMemo(() => {
    if (!allocsA || !allocsB) return null;
    return diffScenarios(allocsA, allocsB);
  }, [allocsA, allocsB]);

  const sceneOptions = scenarios.map((s) => ({
    label: `${s.name} · ${s.quarter} ${s.year}${s.status === 'approved' ? ' ✓' : ''}`,
    value: s.id,
  }));

  const ready = !!aId && !!bId && !la && !lb && !!diff;

  return (
    <Drawer
      title="Сравнение сценариев"
      open={open}
      onClose={onClose}
      width="80vw"
    >
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Сценарий A</div>
          <Select
            style={{ width: '100%' }}
            placeholder="Выберите сценарий"
            value={aId}
            onChange={setAId}
            options={sceneOptions}
            showSearch
            filterOption={(input, opt) =>
              String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Сценарий B</div>
          <Select
            style={{ width: '100%' }}
            placeholder="Выберите сценарий"
            value={bId}
            onChange={setBId}
            options={sceneOptions}
            showSearch
            filterOption={(input, opt) =>
              String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </div>
      </div>

      {!aId || !bId ? (
        <Empty description="Выберите оба сценария для сравнения" />
      ) : !ready ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={COL}>
            <ColumnHeader title="A" count={(allocsA ?? []).filter((x) => x.included).length} />
            {[...diff!.common.map((c) => ({ alloc: c.left, state: 'common' as const })),
              ...diff!.onlyInA.map((alloc) => ({ alloc, state: 'onlyA' as const }))]
              .map((row) => (
                <CompareRow key={row.alloc.id} alloc={row.alloc} state={row.state} />
              ))}
          </div>
          <div style={COL}>
            <ColumnHeader title="B" count={(allocsB ?? []).filter((x) => x.included).length} />
            {[...diff!.common.map((c) => ({ alloc: c.right, state: 'common' as const })),
              ...diff!.onlyInB.map((alloc) => ({ alloc, state: 'onlyB' as const }))]
              .map((row) => (
                <CompareRow key={row.alloc.id} alloc={row.alloc} state={row.state} />
              ))}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function ColumnHeader({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, paddingBottom: 8, borderBottom: `1px solid ${DARK_THEME.border}` }}>
      <Tag color="cyan">{title}</Tag>
      <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>{count} включено</span>
    </div>
  );
}

function CompareRow({ alloc, state }: { alloc: AllocationResponse; state: 'common' | 'onlyA' | 'onlyB' }) {
  const bg =
    state === 'onlyA' ? 'rgba(29,158,117,0.10)' :
    state === 'onlyB' ? 'rgba(245,34,45,0.10)' :
    'transparent';
  const border =
    state === 'onlyA' ? '#1d9e75' :
    state === 'onlyB' ? '#f5222d' :
    'transparent';
  return (
    <div
      style={{
        padding: '8px 10px',
        marginBottom: 4,
        background: bg,
        borderLeft: `3px solid ${border}`,
        borderRadius: 4,
        fontSize: 13,
      }}
    >
      <div style={{ color: DARK_THEME.textPrimary }}>{alloc.title}</div>
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: DARK_THEME.textMuted, marginTop: 2 }}>
        {alloc.jira_key && <span style={{ fontFamily: FONTS.mono }}>{alloc.jira_key}</span>}
        {alloc.estimate_hours != null && <span>{Math.round(alloc.estimate_hours)} ч</span>}
        {alloc.assignee_display_name && <span>· {alloc.assignee_display_name}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire button + drawer in PlanningPage**

Add import:
```tsx
import ScenarioCompareDrawer from '../components/planning/ScenarioCompareDrawer';
import { SwapOutlined } from '@ant-design/icons';
```

Add state:
```tsx
const [compareOpen, setCompareOpen] = useState(false);
```

In the page header `extra` (where «Новый сценарий» button lives — see `PageHeader` `extra` prop), add a button:

```tsx
extra={
  <Space>
    <Tooltip title="Сравнить два сценария">
      <Button icon={<SwapOutlined />} onClick={() => setCompareOpen(true)}>
        Сравнить
      </Button>
    </Tooltip>
    <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
      Новый сценарий
    </Button>
  </Space>
}
```

Render the drawer at end of return tree (alongside ApproveCelebration):
```tsx
<ScenarioCompareDrawer
  open={compareOpen}
  onClose={() => setCompareOpen(false)}
  initialScenarioId={scenarioId ?? undefined}
/>
```

- [ ] **Step 3: Build**

- [ ] **Step 4: Manual smoke**

Click «Сравнить». Pick two scenarios. The drawer shows two columns, with onlyA (green tint left border), onlyB (red tint), common (neutral).

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/components/planning/ScenarioCompareDrawer.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): side-by-side scenario comparison drawer"
git push origin main
```

---

## Final review

- [ ] Run `npm run build` from `frontend/` — succeeds.
- [ ] Spot-check each feature in dev server (`npm run dev`):
   - Sticky table collapses smoothly when scrolling
   - Hover backlog row → cyan border + 2px slide
   - Toggle row → cyan flash + role-column pulse + smooth-scroll if clipped
   - Approve scenario → full-screen check animates and fades
   - Compact toggle → row height shrinks, persists across reload
   - Deficit chips appear next to «Черновик» when over-allocated
   - Progress bars in На-бэклог cells fill and color-shift as items toggled
   - Color-coded left borders: yellow (no estimates), red (deficit), green (in-work)
   - «Diff» button → drawer shows added/removed/unchanged vs last approved
   - «Сравнить» button → drawer shows two scenarios side-by-side
- [ ] Existing E2E tests still pass: `cd frontend && npm run e2e` (Playwright). If any fail because of selector changes, adjust the test rather than reverting features.
- [ ] Final push (already done at end of Phase 4).

## Notes for the implementer

- **No frontend unit-test runner.** The project only has Playwright E2E (`npm run e2e`). Don't add Vitest/Jest. Helper utilities are verified through their consumers in dev server.
- **`npm run build` is the source of truth** for typecheck + lint.
- **`npm run lint` shows pre-existing errors in `SyncPage.tsx`** (unrelated). New code should not add lint errors of its own; existing ones can stay.
- **Don't refactor.** Keep changes surgical. If a file is hard to understand, add a short comment but resist restructuring beyond what each task demands.
- **Russian in user-facing text only.** All identifiers, types, props in English.
- **`scrollIntoView` block: 'nearest'** is intentional — it doesn't yank the page if the row is already visible.
- **Sticky + transition gotcha:** `position: sticky` plus `max-height` transition can interact awkwardly. The sticky wrapper stays the same; only the inner `max-height` div animates. If the sticky height includes the animation, the layout reflows during transition. If problems arise, set `min-height: 44px` on the sticky outer to reduce reflow.
- **`assignee_role` is now backend-resolved**, including via Jira display name lookup (commit 89b2e24). `rolesAffectedByAllocation` (Task 6) relies on this.
- **`useScenarios` does not currently sort** by `created_at`. Task 14 picks `approvedList[0]`. If multiple approved scenarios exist for the same year+quarter and the picked one is wrong, sort client-side by `created_at` desc — but verify the API response shape first; `ScenarioResponse` doesn't currently expose `created_at`. If absent, accept the first one and add a small dropdown to pick which approved scenario to diff against (defer to follow-up if needed).
- **`ScenarioResponse` shape:** check `frontend/src/types/api.ts` before assuming fields exist. The plan references `s.id`, `s.name`, `s.quarter`, `s.year`, `s.status` — all known to exist.
- **`hooks/useRoles` exports `data: roles`**, with each role having `code`, `label`, `color`. `getRoleLabel(roles, code)` and `getRoleColor(roles, code)` from `utils/roles.ts` are the helpers to use.
