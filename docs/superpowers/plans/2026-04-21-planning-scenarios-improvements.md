# Planning Scenarios Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs in the planning page, apply 3 UI improvements, and add 3 new fields (Исполнитель / Заказчик / Тип затрат) to the backlog list with Jira sync.

**Architecture:** Two phases — Phase 1 is pure frontend/UI with one backend endpoint addition, Phase 2 adds a DB migration and backend sync logic. Both phases commit frequently and can be reviewed independently.

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic (SQLite batch mode) / React 19 / TypeScript / Ant Design 6 / TanStack Query

---

## File Map

**Phase 1 — no new files, modifies:**
- `frontend/src/hooks/usePlanning.ts` — cache invalidation fix
- `frontend/src/components/planning/PlanningCapacityPanel.tsx` — remove duplicate card, add role picker
- `frontend/src/pages/PlanningPage.tsx` — list height, fonts, GRID, stacked bar → role cells
- `frontend/src/components/planning/BacklogRoleCell.tsx` — **NEW** mini role card component

**Phase 2 — backend + frontend:**
- `alembic/versions/030_backlog_item_assignee_customer_costtype.py` — **NEW** migration
- `app/models/backlog_item.py` — 3 new fields + Employee relationship
- `app/api/endpoints/backlog.py` — BacklogItemResponse, refresh_from_jira sync
- `app/api/endpoints/planning.py` — AllocationResponse + PATCH assignee endpoint
- `frontend/src/types/api.ts` — update response types
- `frontend/src/api/planning.ts` — add patchAllocationAssignee
- `frontend/src/hooks/usePlanning.ts` — add usePatchAllocationAssignee
- `frontend/src/pages/PlanningPage.tsx` — 3 new columns, assignee Select
- `frontend/src/components/planning/PlanningCapacityPanel.tsx` — per-employee demand bar

---

## Phase 1

### Task 1: Fix resource summary not updating after rules are saved

**Root cause:** `usePutScenarioRules.onSuccess` invalidates the per-day resource base cache but not the breakdown summary cache. The summary uses a different query key (`['scenario-resource-summary', id]`) than the resource (`['planning', 'scenario', id, 'resource']`).

**Files:**
- Modify: `frontend/src/hooks/usePlanning.ts:211-214`

- [ ] **Step 1: Add missing invalidation**

In `usePlanning.ts`, find `usePutScenarioRules`. The `onSuccess` currently has:
```ts
onSuccess: (_d, vars) => {
  qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.scenarioId, 'rules'] });
  qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.scenarioId, 'resource'] });
  notification.success({ title: 'Правила сохранены' });
},
```

Add the missing summary invalidation so it becomes:
```ts
onSuccess: (_d, vars) => {
  qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.scenarioId, 'rules'] });
  qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.scenarioId, 'resource'] });
  qc.invalidateQueries({ queryKey: ['scenario-resource-summary', vars.scenarioId] });
  notification.success({ title: 'Правила сохранены' });
},
```

- [ ] **Step 2: Verify manually**

Start the dev server. Open a scenario that has a team assigned. Go to the Правила tab, set a rule (e.g. 10% of norm for Организационные работы), click Сохранить. Switch to the Распределение tab — the top table should now show the mandatory work row and the «На бэклог» hours should decrease.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePlanning.ts
git commit -m "fix(planning): invalidate resource-summary cache on rules save"
```

---

### Task 2: Remove "Ёмкость по ролям" duplicate card

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx:299-331`

- [ ] **Step 1: Delete the card**

Find and remove the entire block (lines 299–331 approximately):
```tsx
{/* 4. Ёмкость по ролям — сводка */}
<Card title="Ёмкость по ролям" styles={{ body: { padding: 0 } }}>
  ...
</Card>
```

The file ends at the closing `</div>` before the component `return` closes. After removal the component's return should end with the "По сотрудникам" card.

- [ ] **Step 2: Remove unused KpiRow if only used in that block**

Check if `KpiRow` is used anywhere else in the file. Run:
```bash
grep -n "KpiRow" frontend/src/components/planning/PlanningCapacityPanel.tsx
```
If the only remaining usage is in the deleted block, remove the `KpiRow` definition and its import (if imported from elsewhere).

- [ ] **Step 3: Verify**

Right sidebar should show: overall gauge → Ресурс по ролям → По сотрудникам. No "Ёмкость по ролям" below.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx
git commit -m "fix(planning): remove duplicate 'Ёмкость по ролям' card"
```

---

### Task 3: Inline role picker for employees without a role

**Context:** `PATCH /employees/{id}` already exists (takes `{ role: string | null }`). Frontend has `patchEmployee` in `frontend/src/api/employees.ts` and `useSetEmployeeRole` mutation in `useCapacity.ts`. We duplicate the mutation here to avoid importing a capacity-specific hook into the planning panel.

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1: Import what's needed**

At the top of `PlanningCapacityPanel.tsx`, add to imports:
```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Select } from 'antd';
import { patchEmployee } from '../../api/employees';
```

Check existing imports — `useQueryClient` and `Select` may already be imported. Add only what's missing.

- [ ] **Step 2: Add inline mutation**

Inside the `PlanningCapacityPanel` component body (before the return), add:
```tsx
const qc = useQueryClient();
const setRoleMutation = useMutation({
  mutationFn: ({ employeeId, role }: { employeeId: string; role: string }) =>
    patchEmployee(employeeId, { role }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['planning', 'scenario', resourceBase?.team, 'resource'] });
    qc.invalidateQueries({ queryKey: ['employees'] });
  },
});
```

Note: after setting the role, invalidating the resource base re-fetches employee capacity data including the now-set role. The exact query key for the resource is `['planning', 'scenario', sid, 'resource']` — pass `sid` as a prop or use the scenario id. Check the component's props signature to see what's available.

Actually `PlanningCapacityPanel` receives `resourceBase` but not `scenarioId`. Add `scenarioId: string` to its props:

Find the component signature:
```tsx
export default function PlanningCapacityPanel({
  resourceBase,
  allocations,
  quarter,
  roles,
  ...
```

Add `scenarioId`:
```tsx
export default function PlanningCapacityPanel({
  resourceBase,
  allocations,
  quarter,
  roles,
  scenarioId,
  ...
}: {
  ...
  scenarioId: string;
  ...
}) {
```

Then in the mutation:
```tsx
onSuccess: () => {
  qc.invalidateQueries({ queryKey: ['planning', 'scenario', scenarioId, 'resource'] });
  qc.invalidateQueries({ queryKey: ['employees'] });
},
```

Update the call site in `PlanningPage.tsx` to pass `scenarioId={scenarioId}`.

- [ ] **Step 3: Replace "роль не задана" text with a Select**

Find the block that renders `!knownRole && <span>роль не задана</span>`. Replace it:

```tsx
{!e.role ? (
  <Select
    size="small"
    placeholder="роль"
    style={{ width: 110, fontSize: 11 }}
    options={roles
      .filter((r) => r.is_active)
      .map((r) => ({ label: r.label, value: r.code }))}
    loading={setRoleMutation.isPending}
    onChange={(value: string) =>
      setRoleMutation.mutate({ employeeId: e.employee_id, role: value })
    }
    onClick={(ev) => ev.stopPropagation()}
  />
) : null}
```

Also update the condition for the grey "роль не задана" span — remove it since the Select replaces it.

- [ ] **Step 4: Verify**

An employee without a role shows a small Select dropdown instead of "роль не задана". Picking a role saves immediately and the role badge updates.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "fix(planning): add inline role picker for employees without assigned role"
```

---

### Task 4: Create BacklogRoleCell component (Variant C + B colors)

**Design:** Mini card per role. Background = role color at 30% opacity + linear gradient from top. Bottom border = 2px solid role color. Top border + sides = 1px solid role color at 40% opacity. Label small uppercase, number large bold, suffix «ч» with `marginLeft: 3px`, percentage muted below.

**Files:**
- Create: `frontend/src/components/planning/BacklogRoleCell.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { DARK_THEME, FONTS } from '../../utils/constants';

interface BacklogRoleCellProps {
  label: string;       // 'АН' | 'ПР' | 'ТС' | 'ОПЭ'
  hours: number;
  total: number;       // sum of all 4 roles — used to compute pct
  color: string;       // hex role color from getRoleColor()
}

export default function BacklogRoleCell({ label, hours, total, color }: BacklogRoleCellProps) {
  const pct = total > 0 ? Math.round((hours / total) * 100) : 0;
  const empty = hours === 0;

  return (
    <div
      style={{
        flex: 1,
        minWidth: 52,
        borderRadius: 6,
        padding: '5px 6px 4px',
        textAlign: 'center',
        background: `linear-gradient(180deg, ${color}55 0%, ${color}22 100%)`,
        border: `1px solid ${color}66`,
        borderBottom: `2px solid ${color}`,
        opacity: empty ? 0.28 : 1,
        userSelect: 'none',
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          color,
          opacity: 0.85,
          marginBottom: 2,
          fontFamily: FONTS.mono,
        }}
      >
        {label}
      </div>
      <div style={{ lineHeight: 1, marginBottom: 2 }}>
        <span
          style={{
            fontSize: 16,
            fontWeight: 800,
            color: empty ? DARK_THEME.textDim : color,
            fontFamily: FONTS.mono,
          }}
        >
          {empty ? '—' : hours}
        </span>
        {!empty && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              color,
              opacity: 0.65,
              marginLeft: 3,
            }}
          >
            ч
          </span>
        )}
      </div>
      <div
        style={{
          fontSize: 10,
          color: DARK_THEME.textMuted,
          opacity: 0.6,
        }}
      >
        {empty ? '0%' : `${pct}%`}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors related to the new file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/planning/BacklogRoleCell.tsx
git commit -m "feat(planning): add BacklogRoleCell component (gradient + bottom accent)"
```

---

### Task 5: Replace stacked bar with BacklogRoleCell in the allocation table

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Import BacklogRoleCell and add OPO_COLOR reference**

At the top of `PlanningPage.tsx` add:
```tsx
import BacklogRoleCell from '../components/planning/BacklogRoleCell';
```

- [ ] **Step 2: Update the GRID constant**

Change:
```ts
const GRID = '40px 60px 1fr 200px 75px 100px 95px';
```
To:
```ts
const GRID = '40px 60px 1fr 280px 75px 100px 95px';
```
(The role cells column grows from 200px to 280px to accommodate the new card layout.)

- [ ] **Step 3: Update the column header label**

Find `<span>АН / ПР / ТС / ОПЭ</span>` in the header row. Change to `<span>ШКАЛА АН / ПР / ТС / ОПЭ</span>`.

- [ ] **Step 4: Replace the stacked bar block with BacklogRoleCell**

Find the block starting with:
```tsx
<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
  <div style={{ display: 'flex', height: 16, width: 120, borderRadius: 3, ... }}>
    ...
  </div>
  <div style={{ fontFamily: FONTS.mono, fontSize: 10, color: DARK_THEME.textHint, whiteSpace: 'nowrap' }}>
    {an}/{de}/{qa}/{op}
  </div>
</div>
```

Replace the entire block with:
```tsx
<div style={{ display: 'flex', gap: 4 }}>
  <BacklogRoleCell
    label="АН"
    hours={an}
    total={total}
    color={getRoleColor(roles, 'analyst')}
  />
  <BacklogRoleCell
    label="ПР"
    hours={de}
    total={total}
    color={getRoleColor(roles, 'dev')}
  />
  <BacklogRoleCell
    label="ТС"
    hours={qa}
    total={total}
    color={getRoleColor(roles, 'qa')}
  />
  <BacklogRoleCell
    label="ОПЭ"
    hours={op}
    total={total}
    color={OPO_COLOR}
  />
</div>
```

- [ ] **Step 5: Verify visually**

Start the dev server (`cd frontend && npm run dev`), open a scenario, check that each row shows 4 colored mini-cards instead of the horizontal bar.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): replace stacked bar with BacklogRoleCell cards"
```

---

### Task 6: Fix backlog list height (extends to fill screen)

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Remove fixed maxHeight from the list wrapper**

Find:
```tsx
<div style={{ maxHeight: 640, overflowY: 'auto' }}>
```

Replace with:
```tsx
<div style={{ overflowY: 'auto', flex: 1 }}>
```

- [ ] **Step 2: Make the Card body a flex column**

The `Card` wrapping the allocation table needs its body to stretch. Update the Card's `styles` prop:
```tsx
<Card
  title="Элементы бэклога"
  styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1 } }}
  style={{ display: 'flex', flexDirection: 'column', flex: 1 }}
  ...
>
```

- [ ] **Step 3: Make the outer tab panel stretch**

The `<Tabs>` component wrapping the distribution card needs to fill available height. In Ant Design 6, set `style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}` on the Tabs and ensure the distribution tab's children are wrapped in a `div` with `flex: 1, display: 'flex', flexDirection: 'column'`.

Find the grid container (the parent of Tabs and PlanningCapacityPanel):
```tsx
<div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'start' }}>
```

Change `alignItems: 'start'` to `alignItems: 'stretch'` so the right panel can also stretch:
```tsx
<div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'stretch' }}>
```

- [ ] **Step 4: Verify**

The backlog list should now extend to the bottom of the viewport. Scrolling within the list should work. No extra white space below the list.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "fix(planning): backlog list fills remaining vertical space"
```

---

### Task 7: Font size increase (+1pt everywhere on the planning page)

**Scope:** `PlanningPage.tsx` and `PlanningCapacityPanel.tsx`. Existing sizes: 13→14, 11→12, 10→11.

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1: PlanningPage.tsx — row title font**

Find `fontSize: 13` in the allocation row title div:
```tsx
<div style={{ color: DARK_THEME.textPrimary, fontSize: 13, marginBottom: 3 }}>
```
Change to `fontSize: 14`.

- [ ] **Step 2: PlanningPage.tsx — Jira key font**

Find `fontSize: 10` on the Jira key spans (both the `<a>` and `<span>` variants). Change both to `fontSize: 11`.

- [ ] **Step 3: PlanningPage.tsx — total hours column**

Find `fontSize: 13` on the total hours span:
```tsx
<span style={{ textAlign: 'right', fontFamily: FONTS.mono, fontSize: 13, ... }}>
```
Change to `fontSize: 14`.

- [ ] **Step 4: PlanningPage.tsx — header labels**

Find the header row `fontSize: 10` and change to `fontSize: 11`.

- [ ] **Step 5: PlanningCapacityPanel.tsx — employee name**

Find `fontSize: 12` on `e.display_name` span. Change to `fontSize: 13`.

- [ ] **Step 6: PlanningCapacityPanel.tsx — employee hours**

Find `fontSize: 11` on the `{Math.round(e.total_hours)} ч` span. Change to `fontSize: 12`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx frontend/src/components/planning/PlanningCapacityPanel.tsx
git commit -m "fix(planning): increase font sizes by 1pt across planning page"
```

---

## Phase 2

### Task 8: Database migration — add 3 fields to BacklogItem

**Files:**
- Create: `alembic/versions/030_backlog_item_assignee_customer_costtype.py`

- [ ] **Step 1: Generate migration**

```bash
alembic revision -m "backlog_item_assignee_customer_costtype"
```

This creates a new file in `alembic/versions/`. Open it and replace the `upgrade` / `downgrade` functions with:

```python
def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.add_column(sa.Column(
            "assignee_employee_id",
            sa.String(36),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ))
        batch_op.add_column(sa.Column("customer", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cost_type", sa.String(50), nullable=True))
        batch_op.create_index(
            "ix_backlog_items_assignee_employee_id",
            ["assignee_employee_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.drop_index("ix_backlog_items_assignee_employee_id")
        batch_op.drop_column("assignee_employee_id")
        batch_op.drop_column("customer")
        batch_op.drop_column("cost_type")
```

Add the required imports at the top of the migration file (copy from an existing migration):
```python
import sqlalchemy as sa
from alembic import op
```

- [ ] **Step 2: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> 030...`

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): migration 030 — add assignee/customer/cost_type to backlog_items"
```

---

### Task 9: Update BacklogItem model

**Files:**
- Modify: `app/models/backlog_item.py`

- [ ] **Step 1: Add new fields and relationship**

In `backlog_item.py`, after the `archived_at` field and before `# Relationships`, add:

```python
# Phase 2 fields — synced from Jira on refresh.
assignee_employee_id: Mapped[Optional[str]] = mapped_column(
    String(36),
    ForeignKey("employees.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
customer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
cost_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
```

In the `if TYPE_CHECKING:` block, add:
```python
from app.models.employee import Employee
```

In the `# Relationships` section, add:
```python
assignee: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys=[assignee_employee_id])
```

- [ ] **Step 2: Verify import works**

```bash
py -3.10 -c "from app.models.backlog_item import BacklogItem; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/models/backlog_item.py
git commit -m "feat(model): add assignee_employee_id/customer/cost_type to BacklogItem"
```

---

### Task 10: Update BacklogItemResponse schema and refresh_from_jira sync

**Context:** `refresh_from_jira` already calls `JiraClient.from_db(db)` and `refresh_issues_by_keys`. We add a second Jira fetch after that to get the 3 new fields for backlog issues. For assignee: standard Jira `assignee` field (accountId) → matched to `Employee.jira_account_id`. For customer/cost_type: custom fields discovered by name from `GET /rest/api/3/field`.

**Files:**
- Modify: `app/api/endpoints/backlog.py`

- [ ] **Step 1: Add new fields to BacklogItemResponse**

In `BacklogItemResponse`, add after the existing fields:
```python
assignee_employee_id: Optional[str] = None
assignee_display_name: Optional[str] = None  # denormalized for display
customer: Optional[str] = None
cost_type: Optional[str] = None
```

- [ ] **Step 2: Update `_to_response` helper**

Find the `_to_response` function (or the inline response construction). It needs to populate the new fields. Find where `BacklogItemResponse` is constructed and add:

```python
assignee_employee_id=item.assignee_employee_id,
assignee_display_name=item.assignee.display_name if item.assignee else None,
customer=item.customer,
cost_type=item.cost_type,
```

Ensure `item.assignee` is eagerly loaded where `_to_response` is called. In any query that fetches `BacklogItem` for a response, add `joinedload(BacklogItem.assignee)` alongside existing `joinedload(BacklogItem.issue)`.

- [ ] **Step 3: Add helper to discover a custom field ID by name**

Add this function at module level in `backlog.py` (after `_get_setting_value`):

```python
async def _discover_field_id(jira: "JiraClient", db: Session, setting_key: str, field_name: str) -> Optional[str]:
    """Return the Jira custom field ID for `field_name`, caching in AppSetting."""
    cached = _get_setting_value(db, setting_key)
    if cached:
        return cached
    try:
        fields = await jira.get_fields()
    except Exception:
        return None
    for f in fields:
        if f.get("name", "").strip().lower() == field_name.strip().lower():
            fid = f["id"]
            row = db.query(AppSetting).filter(AppSetting.key == setting_key).first()
            if row:
                row.value = fid
            else:
                db.add(AppSetting(key=setting_key, value=fid))
            db.flush()
            return fid
    return None
```

Check `JiraClient` for `get_fields()` — it's likely already there since the JiraFieldsCard uses it. If the method doesn't exist, look at the Jira fields endpoint:

```bash
grep -n "get_fields\|/field" app/connectors/jira_client.py | head -20
```

If it uses a different method name, use that instead.

- [ ] **Step 4: Add Jira sync in refresh_from_jira**

In the `refresh_from_jira` endpoint, after the block that calls `refresh_issues_by_keys` and before step 3 (`candidates = db.query(Issue)...`), add a new Jira fetch for the extra fields:

```python
# Extra: sync assignee / customer / cost_type for backlog items.
if candidate_keys and jira_configured:
    try:
        async with JiraClient.from_db(db) as jira:
            customer_field_id = await _discover_field_id(
                jira, db, "jira_customer_field_id", "Заказчик (user)"
            )
            cost_type_field_id = await _discover_field_id(
                jira, db, "jira_cost_type_field_id", "Тип затрат"
            )
            extra_fields_to_fetch = ["assignee"]
            if customer_field_id:
                extra_fields_to_fetch.append(customer_field_id)
            if cost_type_field_id:
                extra_fields_to_fetch.append(cost_type_field_id)

            BATCH = 100
            for i in range(0, len(candidate_keys), BATCH):
                batch = candidate_keys[i:i + BATCH]
                keys_jql = ", ".join(f'"{k}"' for k in batch)
                jql = f"key in ({keys_jql})"

                async for jira_issue in jira.iter_issues(
                    jql=jql,
                    max_results=BATCH,
                    fields=extra_fields_to_fetch,
                ):
                    # Match issue key → BacklogItem via Issue.key
                    issue_row = (
                        db.query(Issue)
                        .filter(Issue.key == jira_issue.key)
                        .one_or_none()
                    )
                    if not issue_row:
                        continue
                    backlog_item = (
                        db.query(BacklogItem)
                        .filter(BacklogItem.issue_id == issue_row.id)
                        .one_or_none()
                    )
                    if not backlog_item:
                        continue

                    # Assignee: match Jira accountId → Employee
                    assignee_data = getattr(jira_issue.fields, "assignee", None)
                    if assignee_data and hasattr(assignee_data, "accountId"):
                        account_id = assignee_data.accountId
                        emp = (
                            db.query(Employee)
                            .filter(Employee.jira_account_id == account_id)
                            .one_or_none()
                        )
                        backlog_item.assignee_employee_id = emp.id if emp else None
                    else:
                        backlog_item.assignee_employee_id = None

                    # Customer
                    if customer_field_id:
                        raw = (jira_issue.fields._extra or {}).get(customer_field_id)
                        if raw and isinstance(raw, dict):
                            backlog_item.customer = raw.get("displayName") or raw.get("name")
                        else:
                            backlog_item.customer = None

                    # Cost type
                    if cost_type_field_id:
                        raw = (jira_issue.fields._extra or {}).get(cost_type_field_id)
                        if raw and isinstance(raw, dict):
                            backlog_item.cost_type = raw.get("value") or raw.get("name")
                        elif isinstance(raw, str):
                            backlog_item.cost_type = raw
                        else:
                            backlog_item.cost_type = None

            db.commit()
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="Refresh cancelled by client")
    except Exception:
        pass  # Extra field sync is best-effort — don't fail the whole refresh
```

Import `Employee` at the top of `backlog.py` if not already imported:
```python
from app.models import AppSetting, BacklogItem, Employee, Issue, PlanningScenario, ScenarioAllocation
```

- [ ] **Step 5: Verify backend starts without errors**

```bash
py -3.10 -m uvicorn app.main:app --port 8001 --no-access-log
```

Hit Ctrl+C after it starts. Expected: no import errors.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/backlog.py app/models/backlog_item.py
git commit -m "feat(backlog): add assignee/customer/cost_type sync from Jira in refresh_from_jira"
```

---

### Task 11: Update AllocationResponse + add PATCH assignee endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`

- [ ] **Step 1: Add new fields to AllocationResponse**

In `AllocationResponse` (around line 96), add after `risk`:
```python
assignee_employee_id: Optional[str] = None
assignee_display_name: Optional[str] = None
customer: Optional[str] = None
cost_type: Optional[str] = None
```

- [ ] **Step 2: Update `_to_allocation_resp` helper**

In `_to_allocation_resp(alloc, item)`, add to the `AllocationResponse(...)` call:
```python
assignee_employee_id=item.assignee_employee_id,
assignee_display_name=item.assignee.display_name if item.assignee else None,
customer=item.customer,
cost_type=item.cost_type,
```

Find all queries that fetch `BacklogItem` for allocations and add `joinedload(BacklogItem.assignee)` alongside `joinedload(BacklogItem.issue)`. Search for `joinedload(BacklogItem.issue)` in `planning.py` — add the assignee join to the same queries.

- [ ] **Step 3: Add PATCH assignee endpoint**

Add the schema class near the other patch schemas:
```python
class AllocationAssigneePatch(BaseModel):
    assignee_employee_id: Optional[str] = None
```

Add the endpoint:
```python
@router.patch("/scenarios/{scenario_id}/allocations/{alloc_id}/assignee", response_model=AllocationResponse)
async def patch_allocation_assignee(
    scenario_id: str,
    alloc_id: str,
    data: AllocationAssigneePatch,
    db: Session = Depends(get_db),
):
    """Сменить исполнителя на конкретной идее в сценарии."""
    alloc = (
        db.query(ScenarioAllocation)
        .filter(
            ScenarioAllocation.id == alloc_id,
            ScenarioAllocation.scenario_id == scenario_id,
        )
        .first()
    )
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")

    scenario = db.query(PlanningScenario).filter(PlanningScenario.id == scenario_id).first()
    _require_draft(scenario)

    backlog_item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == alloc.backlog_item_id)
        .first()
    )
    if not backlog_item:
        raise HTTPException(status_code=404, detail="BacklogItem not found")

    if data.assignee_employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == data.assignee_employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        backlog_item.assignee_employee_id = data.assignee_employee_id
    else:
        backlog_item.assignee_employee_id = None

    db.commit()
    db.refresh(backlog_item)
    # Reload relationship
    backlog_item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == backlog_item.id)
        .first()
    )
    return _to_allocation_resp(alloc, backlog_item)
```

- [ ] **Step 4: Write a test**

```bash
# tests/test_api_planning_assignee.py
```

```python
"""Test PATCH assignee on allocation."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db

client = TestClient(app)

def test_patch_assignee_not_found(db_session):
    resp = client.patch(
        "/api/v1/planning/scenarios/nonexistent/allocations/nonexistent/assignee",
        json={"assignee_employee_id": None},
    )
    assert resp.status_code == 404
```

Run:
```bash
py -3.10 -m pytest tests/test_api_planning_assignee.py -v
```

Expected: PASS (404 for missing allocation).

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_planning_assignee.py
git commit -m "feat(planning): AllocationResponse adds assignee/customer/cost_type; PATCH assignee endpoint"
```

---

### Task 12: Frontend — types, API function, hook

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/planning.ts`
- Modify: `frontend/src/hooks/usePlanning.ts`

- [ ] **Step 1: Update AllocationResponse in types/api.ts**

Find the `AllocationResponse` interface and add after `risk`:
```ts
assignee_employee_id: string | null;
assignee_display_name: string | null;
customer: string | null;
cost_type: string | null;
```

- [ ] **Step 2: Add API function in api/planning.ts**

```ts
export const patchAllocationAssignee = (
  scenarioId: string,
  allocId: string,
  assigneeEmployeeId: string | null,
) =>
  api.patch<AllocationResponse>(
    `/planning/scenarios/${scenarioId}/allocations/${allocId}/assignee`,
    { assignee_employee_id: assigneeEmployeeId },
  );
```

Add the import for `AllocationResponse` if not already present.

- [ ] **Step 3: Add hook in hooks/usePlanning.ts**

```ts
export const usePatchAllocationAssignee = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  return useMutation<
    AllocationResponse,
    Error,
    { scenarioId: string; allocId: string; assigneeEmployeeId: string | null }
  >({
    mutationFn: ({ scenarioId, allocId, assigneeEmployeeId }) =>
      patchAllocationAssignee(scenarioId, allocId, assigneeEmployeeId),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
    },
    onError: () => {
      notification.error({ title: 'Не удалось сменить исполнителя' });
    },
  });
};
```

Import `patchAllocationAssignee` at the top.

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/planning.ts frontend/src/hooks/usePlanning.ts
git commit -m "feat(planning): add patchAllocationAssignee API + usePatchAllocationAssignee hook"
```

---

### Task 13: Frontend — Исполнитель / Заказчик / Тип затрат columns in backlog list

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Update GRID to add two new columns**

Change:
```ts
const GRID = '40px 60px 1fr 280px 75px 100px 95px';
```
To:
```ts
const GRID = '40px 60px 1fr 150px 120px 280px 75px 100px 95px';
```

Columns: ✓ | Прио | Идея | Исполнитель | Заказчик | АН/ПР/ТС/ОПЭ | Итого | Влияние | Риск

(Remove the separate Риск column if the table becomes too wide — adjust as needed after visual check.)

- [ ] **Step 2: Update column header row**

Add the two new header spans:
```tsx
<span>✓</span>
<span>Прио</span>
<span>Идея</span>
<span>Исполнитель</span>
<span>Заказчик</span>
<span>АН / ПР / ТС / ОПЭ</span>
<span style={{ textAlign: 'right' }}>Всего</span>
<span>Влияние</span>
<span>Риск</span>
```

- [ ] **Step 3: Add Тип затрат tag inside the Идея cell**

Inside the allocation row, in the Идея cell (after the Jira key link), add:
```tsx
{a.cost_type && (
  <Tag
    color={a.cost_type.toLowerCase().includes('change') ? 'blue' : 'green'}
    style={{ fontSize: 10, padding: '0 4px', marginLeft: 4 }}
  >
    {a.cost_type}
  </Tag>
)}
```

- [ ] **Step 4: Import usePatchAllocationAssignee and add Исполнитель cell**

In `PlanningPage.tsx`, import:
```tsx
import { ..., usePatchAllocationAssignee } from '../hooks/usePlanning';
```

In the component body, add:
```tsx
const patchAssignee = usePatchAllocationAssignee();
```

Add the Исполнитель cell in each allocation row (after the Идея cell, before the АН/ПР/ТС/ОПЭ cells):

```tsx
{/* Исполнитель */}
<div onClick={(e) => e.stopPropagation()}>
  <Select
    size="small"
    value={a.assignee_employee_id ?? undefined}
    placeholder="—"
    allowClear
    disabled={!isDraft}
    style={{ width: '100%', fontSize: 12 }}
    options={
      resourceBase?.employees.map((e) => ({
        label: e.display_name,
        value: e.employee_id,
      })) ?? []
    }
    onChange={(value: string | undefined) =>
      patchAssignee.mutate({
        scenarioId: scenarioId!,
        allocId: a.id,
        assigneeEmployeeId: value ?? null,
      })
    }
  />
</div>
```

- [ ] **Step 5: Add Заказчик cell**

After the Исполнитель cell:
```tsx
{/* Заказчик */}
<div style={{ fontSize: 12, color: DARK_THEME.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
  {a.customer ?? '—'}
</div>
```

- [ ] **Step 6: Verify visually**

Open the planning page, check that the new columns appear. The Исполнитель Select should show team members from the scenario. Changing it should save immediately and the value should persist on reload.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): add Исполнитель/Заказчик/Тип затрат columns to backlog list"
```

---

### Task 14: Per-employee demand bars in the capacity panel

**Context:** Currently the "По сотрудникам" bar is decorative (always full width). Now that each allocation can have an `assignee_employee_id`, we can compute per-employee demand = sum of the employee's role-specific hours across their assigned, included allocations.

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1: Add demandByEmployee computation**

In `PlanningCapacityPanel.tsx`, add a new memoized value after the existing `demand = useMemo(...)`:

```tsx
const demandByEmployee = useMemo(() => {
  const result: Record<string, number> = {};
  for (const alloc of allocations) {
    if (!alloc.included || !alloc.assignee_employee_id) continue;
    const emp = resourceBase?.employees.find(
      (e) => e.employee_id === alloc.assignee_employee_id,
    );
    if (!emp?.role) continue;
    const hours =
      emp.role === 'analyst'
        ? (alloc.estimate_analyst_hours ?? 0)
        : emp.role === 'dev'
          ? (alloc.estimate_dev_hours ?? 0)
          : emp.role === 'qa'
            ? (alloc.estimate_qa_hours ?? 0)
            : emp.role === 'consultant'
              ? (alloc.estimate_opo_hours ?? 0)
              : 0;
    result[alloc.assignee_employee_id] = (result[alloc.assignee_employee_id] ?? 0) + hours;
  }
  return result;
}, [allocations, resourceBase]);
```

Note: this mapping assumes standard role codes. The `consultant` role maps to OPO hours; `analyst` to analyst hours. If other roles exist (e.g. `manager`/`pm`), they'll get 0 demand — acceptable because demand calculation is best-effort.

- [ ] **Step 2: Update the employee bar to show demand**

Find the "Simple capacity bar" block:
```tsx
{/* Simple capacity bar */}
<div style={{ display: 'flex', height: 4, background: DARK_THEME.darkAccent, borderRadius: 2, overflow: 'hidden', marginTop: 4 }}>
  <div style={{ width: '100%', background: roleColor, opacity: 0.4 }} />
</div>
```

Replace with a demand/capacity bar:
```tsx
{(() => {
  const empDemand = demandByEmployee[e.employee_id] ?? 0;
  const empCapacity = e.total_hours;
  const pct = empCapacity > 0 ? Math.min((empDemand / empCapacity) * 100, 100) : 0;
  const over = empDemand > empCapacity && empCapacity > 0;
  return (
    <>
      <div
        style={{
          display: 'flex',
          height: 5,
          background: DARK_THEME.darkAccent,
          borderRadius: 2,
          overflow: 'hidden',
          marginTop: 4,
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            background: over ? DARK_THEME.amber : roleColor,
            transition: 'width 0.2s',
          }}
        />
      </div>
      {empDemand > 0 && (
        <div
          style={{
            fontSize: 10,
            color: over ? DARK_THEME.amber : DARK_THEME.textDim,
            marginTop: 1,
            textAlign: 'right',
            fontFamily: FONTS.mono,
          }}
        >
          {Math.round(empDemand)} / {Math.round(empCapacity)} ч
        </div>
      )}
    </>
  );
})()}
```

- [ ] **Step 3: Verify**

Assign a few initiatives to an analyst. The analyst's bar in "По сотрудникам" should show demand proportional to the assigned hours. If demand > capacity, the bar turns amber.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx
git commit -m "feat(planning): show per-employee demand bar based on assigned allocations"
```

---

### Task 15: Push everything to origin

- [ ] **Step 1: Final type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint 2>&1 | tail -20
py -3.10 -m ruff check app/ tests/
```

Expected: no errors (pre-existing CI failures are documented as known).

- [ ] **Step 2: Push**

```bash
git push origin main
```

---

## Self-Review Checklist

- [x] Spec § bugs 1&3 (rules table) → Task 1
- [x] Spec § bug 2 (remove "Ёмкость по ролям") → Task 2
- [x] Spec § bug 4 (role not set) → Task 3
- [x] Spec § bug 5 (role cells visual) → Tasks 4+5
- [x] Spec § bug 6 (list height) → Task 6
- [x] Spec § bug 7 (font size) → Task 7
- [x] Spec § Исполнитель — DB + backend sync → Tasks 8+9+10
- [x] Spec § Исполнитель — AllocationResponse → Task 11
- [x] Spec § Исполнитель — frontend column + select + capacity effect → Tasks 12+13+14
- [x] Spec § Заказчик — DB + Jira sync + column → Tasks 8+10+13
- [x] Spec § Тип затрат — DB + Jira sync + tag → Tasks 8+10+13
- [x] No placeholder steps — all code is complete
- [x] Type names consistent: `AllocationResponse`, `ResourceEmployee`, `BacklogRoleCell` — used consistently
