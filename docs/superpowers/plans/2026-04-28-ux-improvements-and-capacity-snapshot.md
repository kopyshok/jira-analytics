# UX Improvements + Capacity Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 UI bugs, add archive grouping, make categories editable, and implement capacity snapshot architecture (norm+absence snapshots at approval, diff indicator on scenarios, team filter on dashboard widgets).

**Architecture:** Extend approval flow to snapshot per-employee×month×work_type norms and absences into two new tables. Dashboard reads plan_hours from snapshot instead of dynamic recalc. Scenario page diffs current vs snapshot state and shows amber indicator. All dashboard widgets respect global team filter.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch mode), React 19, TypeScript, AntD 6, TanStack Query

---

## Files Map

**New backend files:**
- `app/models/scenario_norm_snapshot.py` — ORM model for norm snapshot
- `app/models/scenario_absence_snapshot.py` — ORM model for absence snapshot
- `alembic/versions/038_scenario_norm_snapshot.py`
- `alembic/versions/039_scenario_absence_snapshot.py`
- `alembic/versions/040_scenario_capacity_drift_ack.py`
- `tests/test_capacity_snapshot.py` — tests for new approve logic + diff endpoint

**Modified backend files:**
- `app/models/__init__.py` — register 2 new models
- `app/models/scenario_revision.py` — add 2 new relationships
- `app/api/endpoints/planning.py` — extend approve + add diff endpoint
- `app/api/endpoints/analytics.py` — add `teams` param to norm-work + categories
- `app/services/analytics_service.py` — read plan from snapshot; filter fact by teams

**Modified frontend files:**
- `frontend/src/pages/SyncPage.tsx:168` — dynamic table height
- `frontend/src/components/sync/SyncAdvanced.tsx` — remove legacy sync card
- `frontend/src/pages/BacklogPage.tsx` — archive: quarter column + grouping toggle
- `frontend/src/types/api.ts` — add `quarter_label` to BacklogItemResponse; add CapacityDiff types
- `frontend/src/api/analytics.ts` — add `teams` to fetchDashboardNormWork + fetchDashboardCategories
- `frontend/src/hooks/useAnalytics.ts` — pass teams to dashboard hooks
- `frontend/src/pages/DashboardPage.tsx` — pass teamParams to hooks
- `frontend/src/components/dashboard/NormWorkWidget.tsx` — round hours
- `frontend/src/components/dashboard/CategoryWidget.tsx` — round hours
- `frontend/src/api/planning.ts` — add fetchCapacityDiff function
- `frontend/src/hooks/usePlanning.ts` — add useCapacityDiff hook
- `frontend/src/pages/PlanningPage.tsx` — show indicator A3 on approved scenarios

---

## Phase 1 — Quick UI Fixes

### Task 1: Fix table scroll height in CategoryConfigTab

**Files:**
- Modify: `frontend/src/pages/SyncPage.tsx:168`

- [ ] **Step 1: Replace fixed scroll height with dynamic**

In `frontend/src/pages/SyncPage.tsx`, change line 168:

```typescript
// Before:
const tableScroll = { y: 600 };

// After:
const tableScroll = { y: 'calc(100vh - 320px)' };
```

- [ ] **Step 2: Verify visually**

Start dev server. Open /categories. Resize window — list should fill available space without fixed cutoff.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SyncPage.tsx
git commit -m "fix(categories): dynamic table height instead of fixed 600px"
```

---

### Task 2: Remove legacy sync buttons

**Files:**
- Modify: `frontend/src/components/sync/SyncAdvanced.tsx`

- [ ] **Step 1: Write failing test (manual check — no unit test for pure UI removal)**

Open /sync → Дополнительно tab. Verify "Синхронизация задач (legacy)" card is visible before change.

- [ ] **Step 2: Remove legacy card and its handlers**

In `frontend/src/components/sync/SyncAdvanced.tsx`, remove:
1. Lines 105–126: `handleFullSync`, `cancelFullSync`, `handleIncrementalSync`, `cancelIncSync` handlers
2. Lines 106–107: `fullSyncMut` and `incrementalSyncMut` declarations
3. Lines 133–151: entire `<Card title="Синхронизация задач (legacy)" ...>` JSX block
4. Any now-unused imports: `useSyncMutation` (check if used elsewhere in file first)

Also remove unused `fullAbortRef` and `incAbortRef` refs (lines 107).

- [ ] **Step 3: Check TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sync/SyncAdvanced.tsx
git commit -m "fix(sync): remove legacy issue-sync buttons from Advanced tab"
```

---

### Task 3: Investigate and fix RFA-241 missing from Backlog tab

**Files:**
- Modify: `app/api/endpoints/backlog.py` (after investigation)

- [ ] **Step 1: Investigate the discrepancy**

```bash
py -3.10 -c "
from app.database import SessionLocal
from app.models import BacklogItem, CategoryMapping
db = SessionLocal()

# Check if RFA-241 has a backlog item
from app.models import Issue
issue = db.query(Issue).filter(Issue.key == 'RFA-241').first()
print('Issue:', issue)
if issue:
    bi = db.query(BacklogItem).filter(BacklogItem.issue_id == issue.id).first()
    print('BacklogItem:', bi)
    cm = db.query(CategoryMapping).filter(CategoryMapping.entity_id == issue.id).first()
    print('CategoryMapping:', cm)
db.close()
"
```

- [ ] **Step 2: Based on result, apply fix**

**Case A — no BacklogItem exists:** RFA-241 has category `initiatives_rfa` but was never synced to backlog. Check `app/services/backlog_service.py` method that creates backlog items from initiatives — verify it handles this issue type.

**Case B — BacklogItem exists but filtered out:** Check the backlog API filter for `view='active'`. The item may have `archived_at` set or `in_work=True` unexpectedly. Fix the filter condition.

**Case C — category mismatch:** The category detection logic may need a re-run. Call `POST /mapping/recalculate` and recheck.

- [ ] **Step 3: Write regression test**

```python
# tests/test_backlog.py — add test
def test_backlog_active_returns_all_initiatives_rfa(client, db_session):
    """All issues with category initiatives_rfa must appear in active backlog."""
    # Create issue + category mapping + backlog item
    from app.models import Issue, BacklogItem, CategoryMapping
    issue = Issue(id="test-rfa-1", key="RFA-999", summary="Test initiative", ...)
    db_session.add(issue)
    bi = BacklogItem(id="test-bi-1", title="Test initiative", issue_id="test-rfa-1")
    db_session.add(bi)
    db_session.flush()
    resp = client.get("/api/v1/backlog?view=active")
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert "test-bi-1" in ids
```

- [ ] **Step 4: Run tests**

```bash
py -3.10 -m pytest tests/test_backlog.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/ tests/
git commit -m "fix(backlog): ensure all initiatives_rfa items appear in active view"
```

---

### Task 4: Add teams filter to dashboard widgets

**Files:**
- Modify: `app/api/endpoints/analytics.py` — add `teams` param
- Modify: `app/services/analytics_service.py` — filter fact by teams
- Modify: `frontend/src/api/analytics.ts` — pass teams
- Modify: `frontend/src/hooks/useAnalytics.ts` — accept teams
- Modify: `frontend/src/pages/DashboardPage.tsx` — pass teamParams

- [ ] **Step 1: Write failing test**

```python
# tests/test_analytics.py — add test
def test_dashboard_norm_work_filters_by_team(client, db_session, ...):
    """norm-work endpoint must filter fact hours by team when teams param given."""
    # setup: 2 employees, 2 teams, worklogs for each
    # call /analytics/dashboard/norm-work?year=2026&quarter=2&teams=TeamA
    # assert only TeamA worklogs in fact_hours
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2&teams=TeamA")
    assert resp.status_code == 200

def test_dashboard_categories_filters_by_team(client, db_session, ...):
    resp = client.get("/api/v1/analytics/dashboard/categories?year=2026&quarter=2&teams=TeamA")
    assert resp.status_code == 200
```

- [ ] **Step 2: Add `teams` param to backend endpoints**

In `app/api/endpoints/analytics.py`, update both endpoints:

```python
@router.get("/dashboard/norm-work", response_model=DashboardNormWorkResponse)
def dashboard_norm_work(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_norm_work(year=year, quarter=quarter, month=month, teams=parse_teams_csv(teams))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/categories", response_model=DashboardCategoriesResponse)
def dashboard_categories(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_categories(year=year, quarter=quarter, month=month, teams=parse_teams_csv(teams))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

- [ ] **Step 3: Add teams filtering to analytics service**

In `app/services/analytics_service.py`, update `get_dashboard_norm_work` signature and fact query:

```python
def get_dashboard_norm_work(
    self,
    year: int,
    quarter: int,
    month: Optional[int] = None,
    teams: Optional[list[str]] = None,
) -> DashboardNormWorkResponse:
    ...
    # In fact worklog query, add team filter:
    fact_q = (
        self.db.query(...)
        .join(Employee, Worklog.employee_id == Employee.id)
        ...
    )
    if teams:
        from app.models import EmployeeTeam
        emp_ids_in_teams = [
            r[0] for r in
            self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team.in_(teams))
            .all()
        ]
        fact_q = fact_q.filter(Worklog.employee_id.in_(emp_ids_in_teams))
```

Do same for `get_dashboard_categories`.

- [ ] **Step 4: Update frontend API function**

In `frontend/src/api/analytics.ts`:

```typescript
export function fetchDashboardNormWork(
  period: QuarterPeriod,
  teams?: Record<string, string>,
  signal?: AbortSignal,
): Promise<DashboardNormWorkResponse> {
  return api.get<DashboardNormWorkResponse>(
    '/analytics/dashboard/norm-work',
    { ...periodToParams(period), ...(teams ?? {}) },
    signal,
  );
}

export function fetchDashboardCategories(
  period: QuarterPeriod,
  teams?: Record<string, string>,
  signal?: AbortSignal,
): Promise<DashboardCategoriesResponse> {
  return api.get<DashboardCategoriesResponse>(
    '/analytics/dashboard/categories',
    { ...periodToParams(period), ...(teams ?? {}) },
    signal,
  );
}
```

- [ ] **Step 5: Update hooks**

In `frontend/src/hooks/useAnalytics.ts`:

```typescript
export function useDashboardNormWork(period: QuarterPeriod, teams?: Record<string, string>) {
  return useQuery({
    queryKey: ['dashboard-norm-work', period, teams],
    queryFn: ({ signal }) => fetchDashboardNormWork(period, teams, signal),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDashboardCategories(period: QuarterPeriod, teams?: Record<string, string>) {
  return useQuery({
    queryKey: ['dashboard-categories', period, teams],
    queryFn: ({ signal }) => fetchDashboardCategories(period, teams, signal),
    staleTime: 30_000,
    retry: 1,
  });
}
```

- [ ] **Step 6: Pass teamParams in DashboardPage**

In `frontend/src/pages/DashboardPage.tsx`:

```typescript
const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period, teamParams);
const { data: categories, isLoading: catLoading } = useDashboardCategories(period, teamParams);
```

- [ ] **Step 7: Run tests**

```bash
py -3.10 -m pytest tests/test_analytics.py -v
```

- [ ] **Step 8: Commit**

```bash
git add app/ frontend/src/
git commit -m "feat(dashboard): apply global team filter to norm-work and categories widgets"
```

---

### Task 5: Round hours to integers in dashboard widgets

**Files:**
- Modify: `frontend/src/components/dashboard/NormWorkWidget.tsx`
- Modify: `frontend/src/components/dashboard/CategoryWidget.tsx`

- [ ] **Step 1: Update NormWorkWidget**

In `NormWorkWidget.tsx`, find all `formatHours` calls and `toFixed` on hour values. Replace with `Math.round`:

```typescript
// In BulletBar and summary row, wherever plan_hours/fact_hours displayed:
// Before: {formatHours(item.plan_hours)} or {item.plan_hours.toFixed(1)}
// After:
{Math.round(item.plan_hours)} ч
// and
{Math.round(item.fact_hours)} ч
```

Also update summary totals (`total_plan`, `total_fact`):
```typescript
// Before: {formatHours(data.total_plan)}
// After: {Math.round(data.total_plan)} ч
```

- [ ] **Step 2: Update CategoryWidget**

In `CategoryWidget.tsx`, same approach — wrap all `hours` display values in `Math.round(...)`.

- [ ] **Step 3: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/
git commit -m "fix(dashboard): round hours to integers in NormWork and Category widgets"
```

---

## Phase 2 — Archive Tab: Quarter Column + Grouping

### Task 6: Add quarter_label to backlog API response

**Files:**
- Modify: `app/api/endpoints/backlog.py` — add quarter_label to serialization
- Modify: `frontend/src/types/api.ts` — add field to BacklogItemResponse

- [ ] **Step 1: Write failing test**

```python
# tests/test_backlog.py
def test_archived_backlog_item_has_quarter_label(client, db_session):
    """Archived backlog items must include quarter_label from their approved scenario."""
    # setup: BacklogItem archived, ScenarioAllocation → PlanningScenario(quarter='Q1', year=2026, status='approved')
    resp = client.get("/api/v1/backlog?view=archived")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    # item with allocation has quarter_label
    item_with_q = next((i for i in items if i.get("approved_scenarios")), None)
    assert item_with_q is not None
    assert "quarter_label" in item_with_q
```

- [ ] **Step 2: Add quarter_label to backlog serialization**

In `app/api/endpoints/backlog.py` (or relevant schema), find `BacklogItemResponse` serialization. Add:

```python
# In the function that builds BacklogItemResponse:
# After building approved_scenarios list:
quarter_label: str | None = None
if item.allocations:
    approved = next(
        (a.scenario for a in item.allocations
         if a.scenario and a.scenario.status == "approved"),
        None
    )
    if approved and approved.quarter and approved.year:
        q_num = approved.quarter.replace("Q", "")
        quarter_label = f"{q_num} кв. {approved.year}"
```

Add `quarter_label: str | None` to the Pydantic response schema for backlog items.

- [ ] **Step 3: Run test**

```bash
py -3.10 -m pytest tests/test_backlog.py::test_archived_backlog_item_has_quarter_label -v
```

Expected: PASS.

- [ ] **Step 4: Update frontend type**

In `frontend/src/types/api.ts`, add to `BacklogItemResponse`:

```typescript
export interface BacklogItemResponse {
  // ... existing fields ...
  quarter_label: string | null;  // e.g. "2 кв. 2026" or null
}
```

- [ ] **Step 5: Commit**

```bash
git add app/ frontend/src/types/api.ts
git commit -m "feat(backlog): add quarter_label to archived backlog item response"
```

---

### Task 7: Archive tab — quarter column and grouping toggle

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`

- [ ] **Step 1: Add quarter column to archive table**

In `BacklogPage.tsx`, find the archive tab columns definition. Add a "Квартал" column after "Статус":

```typescript
{
  title: 'Квартал',
  key: 'quarter_label',
  width: 110,
  sorter: (a: BacklogItemResponse, b: BacklogItemResponse) => {
    if (!a.quarter_label && !b.quarter_label) return 0;
    if (!a.quarter_label) return 1;
    if (!b.quarter_label) return -1;
    return b.quarter_label.localeCompare(a.quarter_label);
  },
  defaultSortOrder: 'ascend' as const,
  render: (v: unknown, r: BacklogItemResponse) =>
    r.quarter_label
      ? <Tag color="purple" style={{ marginInlineEnd: 0 }}>{r.quarter_label}</Tag>
      : <span style={{ color: '#4a6a80' }}>—</span>,
},
```

- [ ] **Step 2: Add grouping toggle state**

At the top of the `BacklogPage` component, add:

```typescript
const [groupByQuarter, setGroupByQuarter] = useState<boolean>(() => {
  return localStorage.getItem('backlog-archive-group') === 'true';
});

const toggleGroupByQuarter = (val: boolean) => {
  setGroupByQuarter(val);
  localStorage.setItem('backlog-archive-group', String(val));
};
```

- [ ] **Step 3: Add toggle button to archive tab toolbar**

In the archive tab `tabBarExtraContent` or above the table, add:

```tsx
<Button
  size="small"
  type={groupByQuarter ? 'primary' : 'default'}
  ghost={groupByQuarter}
  onClick={() => toggleGroupByQuarter(!groupByQuarter)}
>
  Группировать по кварталам
</Button>
```

- [ ] **Step 4: Implement grouped rendering**

When `groupByQuarter` is true, render grouped sections instead of a flat table:

```tsx
// Helper to group items
function groupArchiveByQuarter(items: BacklogItemResponse[]) {
  const groups: Map<string, BacklogItemResponse[]> = new Map();
  for (const item of items) {
    const key = item.quarter_label ?? '__none__';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(item);
  }
  // Sort: newest quarter first, null last
  const sorted = [...groups.entries()].sort(([a], [b]) => {
    if (a === '__none__') return 1;
    if (b === '__none__') return -1;
    return b.localeCompare(a);
  });
  return sorted;
}
```

Render as:
```tsx
{groupByQuarter ? (
  groupArchiveByQuarter(archivedItems).map(([key, rows]) => (
    <div key={key} style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        {key === '__none__'
          ? <span style={{ color: '#4a6a80', fontWeight: 600 }}>Без квартала</span>
          : <Tag color="purple">{key}</Tag>
        }
        <span style={{ color: '#4a6a80', fontSize: 12 }}>{rows.length} задач</span>
      </div>
      <Table
        dataSource={rows}
        columns={archiveColumns}
        rowKey="id"
        size="small"
        pagination={false}
        scroll={{ x: true }}
      />
    </div>
  ))
) : (
  <Table
    dataSource={archivedItems}
    columns={archiveColumns}
    rowKey="id"
    size="small"
    pagination={{ pageSize: 50 }}
    scroll={{ x: true }}
  />
)}
```

- [ ] **Step 5: Check TypeScript and test visually**

```bash
cd frontend && npx tsc --noEmit
```

Open /backlog → Архив. Verify quarter column shows. Toggle grouping — groups appear with "Без квартала" last.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx
git commit -m "feat(backlog): archive tab quarter column and grouping toggle"
```

---

## Phase 3 — Settings: Editable Work Categories

### Task 8: Make CategoriesTab editable

**Files:**
- Modify: `frontend/src/components/settings/CategoriesTab.tsx` (or `SettingsPage.tsx` categories tab)

- [ ] **Step 1: Read current CategoriesTab implementation**

```bash
cat frontend/src/components/settings/CategoriesTab.tsx
```

Identify: what data it shows, what API it calls, whether it's read-only.

- [ ] **Step 2: Add inline editing**

Replace read-only display with an AntD editable table. For each category row, allow:

```typescript
// Editable fields per row:
// - label: Typography.Text with editable=true (double-click to edit)
// - color: ColorPicker (AntD 6 has ColorPicker component)
// - sort_order: managed by drag handle (DndKit, same pattern as backlog)
// - delete: Popconfirm → DELETE /api/v1/categories/{id} (only if !is_system)
// - add: "+ Добавить категорию" button at bottom

// Use useUpdateCategory, useDeleteCategory hooks (or create them)
```

API calls to use:
- `PUT /api/v1/categories/{id}` with `{ label, color, sort_order }`
- `DELETE /api/v1/categories/{id}`
- `POST /api/v1/categories` with `{ code, label, color, sort_order }`

Hooks pattern (add to `frontend/src/hooks/useCategories.ts` or similar existing file):

```typescript
export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; label?: string; color?: string; sort_order?: number }) =>
      api.put(`/categories/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/categories/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { code: string; label: string; color?: string; sort_order?: number }) =>
      api.post('/categories', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}
```

System categories (`is_system=true`) show a lock icon instead of delete button.

- [ ] **Step 3: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Test visually**

Open /settings → вкладка "Категории работ". Edit a label, change color, drag to reorder, add new, delete non-system.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat(settings): make work categories tab editable"
```

---

## Phase 4 — Capacity Snapshot Architecture

### Task 9: Migration 038 — scenario_norm_snapshot table

**Files:**
- Create: `alembic/versions/038_scenario_norm_snapshot.py`

- [ ] **Step 1: Generate migration**

```bash
alembic revision --autogenerate -m "scenario_norm_snapshot"
```

Rename generated file to `038_scenario_norm_snapshot.py`.

- [ ] **Step 2: Verify migration content**

Check that the generated migration creates `scenario_norm_snapshots` table. If autogenerate misses columns (model not yet created — see Task 11), write manually:

```python
def upgrade() -> None:
    op.create_table(
        "scenario_norm_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("work_type_id", sa.String(36),
                  sa.ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("work_type_label", sa.String(255), nullable=False),
        sa.Column("norm_hours", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

def downgrade() -> None:
    op.drop_table("scenario_norm_snapshots")
```

- [ ] **Step 3: Run migration**

```bash
alembic upgrade head
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "migration(038): scenario_norm_snapshots table"
```

---

### Task 10: Migration 039 — scenario_absence_snapshot table

**Files:**
- Create: `alembic/versions/039_scenario_absence_snapshot.py`

- [ ] **Step 1: Create migration**

```bash
alembic revision -m "scenario_absence_snapshot"
```

Rename to `039_scenario_absence_snapshot.py`. Write content:

```python
def upgrade() -> None:
    op.create_table(
        "scenario_absence_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36),
                  sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("employee_id", sa.String(36),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("original_absence_id", sa.String(36), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("reason_id", sa.String(36), nullable=True),
        sa.Column("reason_label", sa.String(255), nullable=True),
        sa.Column("hours_total", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

def downgrade() -> None:
    op.drop_table("scenario_absence_snapshots")
```

- [ ] **Step 2: Run migration**

```bash
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "migration(039): scenario_absence_snapshots table"
```

---

### Task 11: Migration 040 — capacity_drift_acknowledged_at on planning_scenario

**Files:**
- Create: `alembic/versions/040_scenario_capacity_drift_ack.py`

- [ ] **Step 1: Create migration**

```bash
alembic revision -m "scenario_capacity_drift_ack"
```

Rename to `040_scenario_capacity_drift_ack.py`. Write:

```python
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    with op.batch_alter_table("planning_scenarios") as batch_op:
        batch_op.add_column(
            sa.Column("capacity_drift_acknowledged_at", sa.DateTime, nullable=True)
        )

def downgrade() -> None:
    with op.batch_alter_table("planning_scenarios") as batch_op:
        batch_op.drop_column("capacity_drift_acknowledged_at")
```

- [ ] **Step 2: Run migration**

```bash
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "migration(040): capacity_drift_acknowledged_at on planning_scenario"
```

---

### Task 12: ORM models for new snapshot tables

**Files:**
- Create: `app/models/scenario_norm_snapshot.py`
- Create: `app/models/scenario_absence_snapshot.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/scenario_revision.py`
- Modify: `app/models/planning_scenario.py`

- [ ] **Step 1: Create ScenarioNormSnapshot model**

```python
# app/models/scenario_norm_snapshot.py
"""ScenarioNormSnapshot — per-employee/month/work_type norm at approval time."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee
    from app.models.mandatory_work_type import MandatoryWorkType


class ScenarioNormSnapshot(Base, TimestampMixin):
    """Норма сотрудника по виду работ за месяц на момент утверждения.

    Позволяет читать плановые часы с дашборда без пересчёта и сравнивать
    по ролям/сотрудникам в будущей аналитике.
    """

    __tablename__ = "scenario_norm_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    work_type_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_type_label: Mapped[str] = mapped_column(String(255), nullable=False)
    norm_hours: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="norm_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioNormSnapshot emp={self.employee_name} {self.year}-{self.month:02d} wt={self.work_type_label}>"
```

- [ ] **Step 2: Create ScenarioAbsenceSnapshot model**

```python
# app/models/scenario_absence_snapshot.py
"""ScenarioAbsenceSnapshot — copy of employee absences at approval time."""
from datetime import date
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.employee import Employee


class ScenarioAbsenceSnapshot(Base, TimestampMixin):
    """Копия отсутствия сотрудника на момент утверждения сценария.

    Хранит original_absence_id для идентификации отсутствий,
    удалённых или изменённых после утверждения.
    """

    __tablename__ = "scenario_absence_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_absence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reason_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hours_total: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="absence_snapshots")
    employee: Mapped[Optional["Employee"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioAbsenceSnapshot emp={self.employee_name} {self.start_date}–{self.end_date}>"
```

- [ ] **Step 3: Register models in `app/models/__init__.py`**

Add imports and `__all__` entries:

```python
from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
```

Add to `__all__`: `"ScenarioNormSnapshot"`, `"ScenarioAbsenceSnapshot"`.

- [ ] **Step 4: Add relationships to ScenarioRevision**

In `app/models/scenario_revision.py`, add to TYPE_CHECKING imports and relationships:

```python
if TYPE_CHECKING:
    ...
    from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
    from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot

# In class body, after capacity_snapshots relationship:
norm_snapshots: Mapped[List["ScenarioNormSnapshot"]] = relationship(
    back_populates="revision", cascade="all, delete-orphan"
)
absence_snapshots: Mapped[List["ScenarioAbsenceSnapshot"]] = relationship(
    back_populates="revision", cascade="all, delete-orphan"
)
```

- [ ] **Step 5: Add capacity_drift_acknowledged_at to PlanningScenario**

In `app/models/planning_scenario.py`:

```python
from datetime import datetime
from sqlalchemy import DateTime

# In class body, after external_qa_hours:
capacity_drift_acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime, nullable=True
)
```

- [ ] **Step 6: Run existing tests to verify no regressions**

```bash
py -3.10 -m pytest tests/ -v -x
```

Expected: all pass (new tables exist, no FK errors).

- [ ] **Step 7: Commit**

```bash
git add app/models/
git commit -m "feat(models): ScenarioNormSnapshot, ScenarioAbsenceSnapshot, drift_ack field"
```

---

### Task 13: Extend approve endpoint to create norm + absence snapshots

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Create: `tests/test_capacity_snapshot.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_capacity_snapshot.py
import pytest
from datetime import date
from app.models import (
    PlanningScenario, ScenarioRevision, ScenarioNormSnapshot,
    ScenarioAbsenceSnapshot, Employee, EmployeeTeam, Absence,
    MandatoryWorkType, ScenarioRule,
)


def test_approve_creates_norm_snapshots(client, db_session):
    """Approving scenario must create ScenarioNormSnapshot rows per employee×month×work_type."""
    # Setup: scenario, employee with role, work type, scenario rule, scenario in draft
    wt = MandatoryWorkType(id="wt-1", code="projects", label="Проекты", is_active=True, sort_order=1, subtracts_from_pool=False)
    db_session.add(wt)
    emp = Employee(id="emp-1", jira_account_id="acc-1", display_name="Тест", is_active=True, role="analyst")
    db_session.add(emp)
    from app.models import EmployeeTeam
    db_session.add(EmployeeTeam(employee_id="emp-1", team="TeamA"))
    scenario = PlanningScenario(id="sc-1", name="Q2 Test", quarter="Q2", year=2026, status="draft", team="TeamA")
    db_session.add(scenario)
    rule = ScenarioRule(id="sr-1", scenario_id="sc-1", role="analyst", work_type_id="wt-1", percent_of_norm=30.0)
    db_session.add(rule)
    db_session.commit()

    resp = client.post("/api/v1/planning/scenarios/sc-1/approve")
    assert resp.status_code == 200

    norms = db_session.query(ScenarioNormSnapshot).all()
    assert len(norms) > 0
    # Each norm row has work_type_label set
    assert all(n.work_type_label for n in norms)


def test_approve_creates_absence_snapshots(client, db_session):
    """Approving scenario must snapshot all absences for team employees in quarter."""
    emp = Employee(id="emp-2", jira_account_id="acc-2", display_name="Тест2", is_active=True)
    db_session.add(emp)
    db_session.add(EmployeeTeam(employee_id="emp-2", team="TeamB"))
    absence = Absence(
        id="abs-1", employee_id="emp-2",
        start_date=date(2026, 4, 14), end_date=date(2026, 4, 18), hours_total=40.0,
    )
    db_session.add(absence)
    scenario = PlanningScenario(id="sc-2", name="Q2 B", quarter="Q2", year=2026, status="draft", team="TeamB")
    db_session.add(scenario)
    db_session.commit()

    resp = client.post("/api/v1/planning/scenarios/sc-2/approve")
    assert resp.status_code == 200

    snaps = db_session.query(ScenarioAbsenceSnapshot).all()
    assert len(snaps) == 1
    assert snaps[0].original_absence_id == "abs-1"
    assert snaps[0].hours_total == 40.0
```

- [ ] **Step 2: Run to verify tests fail**

```bash
py -3.10 -m pytest tests/test_capacity_snapshot.py -v
```

Expected: FAIL (norm/absence snapshots not created yet).

- [ ] **Step 3: Extend approve endpoint**

In `app/api/endpoints/planning.py`, after the existing capacity snapshot loop (lines ~511–520), add:

```python
    # --- Снапшот норм по видам работ ---
    if scenario.team and scenario.year and scenario.quarter:
        # Load scenario rules
        rules = (
            db.query(ScenarioRule)
            .filter(ScenarioRule.scenario_id == scenario_id)
            .all()
        )
        # Load work type labels
        wt_ids = list({r.work_type_id for r in rules})
        work_types = {
            wt.id: wt.label
            for wt in db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(wt_ids)).all()
        }
        for emp in employees:
            for month in months:
                mc = capacity_svc.monthly_capacity(emp.id, scenario.year, month)
                emp_rules = [
                    r for r in rules
                    if r.role is None or r.role == emp.role
                ]
                for rule in emp_rules:
                    norm_h = round(mc.norm_hours * rule.percent_of_norm / 100, 2)
                    db.add(ScenarioNormSnapshot(
                        revision_id=revision.id,
                        employee_id=emp.id,
                        employee_name=emp.display_name,
                        role=emp.role,
                        year=scenario.year,
                        month=month,
                        work_type_id=rule.work_type_id,
                        work_type_label=work_types.get(rule.work_type_id, ""),
                        norm_hours=norm_h,
                    ))

    # --- Снапшот отсутствий ---
    if scenario.team and scenario.year and scenario.quarter:
        q_num = int(str(scenario.quarter).replace("Q", ""))
        q_months = QUARTER_MONTHS[q_num]
        from datetime import date as date_t
        quarter_start = date_t(scenario.year, q_months[0], 1)
        import calendar
        last_month = q_months[-1]
        last_day = calendar.monthrange(scenario.year, last_month)[1]
        quarter_end = date_t(scenario.year, last_month, last_day)

        absences = (
            db.query(Absence)
            .filter(
                Absence.employee_id.in_([emp.id for emp in employees]),
                Absence.start_date <= quarter_end,
                Absence.end_date >= quarter_start,
            )
            .all()
        )
        # Load reason labels
        reason_ids = list({a.reason_id for a in absences if a.reason_id})
        from app.models import AbsenceReason
        reasons = {
            r.id: r.label
            for r in db.query(AbsenceReason).filter(AbsenceReason.id.in_(reason_ids)).all()
        } if reason_ids else {}
        emp_names = {emp.id: emp.display_name for emp in employees}

        for ab in absences:
            db.add(ScenarioAbsenceSnapshot(
                revision_id=revision.id,
                employee_id=ab.employee_id,
                employee_name=emp_names.get(ab.employee_id, ""),
                original_absence_id=ab.id,
                start_date=ab.start_date,
                end_date=ab.end_date,
                reason_id=ab.reason_id,
                reason_label=reasons.get(ab.reason_id) if ab.reason_id else None,
                hours_total=ab.hours_total,
            ))
```

Add missing imports at top of file:
```python
from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
from app.models import AbsenceReason
```

- [ ] **Step 4: Run tests**

```bash
py -3.10 -m pytest tests/test_capacity_snapshot.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
py -3.10 -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add app/ tests/
git commit -m "feat(planning): snapshot norms and absences at scenario approval"
```

---

### Task 14: Capacity diff endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py` — add GET endpoint
- Modify: `app/api/endpoints/planning.py` — add PATCH endpoint for acknowledge
- Modify: `tests/test_capacity_snapshot.py` — add diff tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_capacity_snapshot.py

def test_capacity_diff_no_changes(client, db_session):
    """Diff endpoint returns has_changes=False when absences unchanged since approval."""
    # Setup: approve scenario, don't modify absences
    # ... setup code ...
    resp = client.get("/api/v1/planning/scenarios/sc-3/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is False
    assert data["changed_employees"] == []


def test_capacity_diff_detects_removed_absence(client, db_session):
    """Diff endpoint detects absence removed after approval."""
    # Setup: approve scenario with 1 absence, then delete absence
    # ... setup code ...
    # After approval, delete the absence:
    db_session.delete(absence)
    db_session.commit()

    resp = client.get("/api/v1/planning/scenarios/sc-4/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is True
    assert len(data["changed_employees"]) == 1
    changes = data["changed_employees"][0]["months"][0]["absence_changes"]
    assert len(changes) == 1
    assert changes[0]["type"] == "removed"
```

- [ ] **Step 2: Add Pydantic schemas for diff response**

In `app/schemas/planning.py` (or create `app/schemas/capacity_diff.py`):

```python
from pydantic import BaseModel
from datetime import date

class AbsenceChange(BaseModel):
    type: str            # "added" | "removed"
    start_date: date
    end_date: date
    reason: str | None
    hours: float

class MonthDiff(BaseModel):
    year: int
    month: int
    snapshot_available_hours: float
    current_available_hours: float
    delta_hours: float
    absence_changes: list[AbsenceChange]

class EmployeeDiff(BaseModel):
    employee_id: str
    employee_name: str
    months: list[MonthDiff]

class CapacityDiffResponse(BaseModel):
    has_changes: bool
    changed_employees: list[EmployeeDiff]
```

- [ ] **Step 3: Implement diff endpoint**

In `app/api/endpoints/planning.py`, add after approve endpoint:

```python
@router.get("/scenarios/{scenario_id}/capacity-diff", response_model=CapacityDiffResponse)
def get_capacity_diff(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Diff текущих отсутствий vs снапшот на момент утверждения."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario or scenario.status != "approved":
        raise HTTPException(status_code=404, detail="Approved scenario not found")

    # Latest revision
    revision = (
        db.query(ScenarioRevision)
        .filter(ScenarioRevision.scenario_id == scenario_id)
        .order_by(ScenarioRevision.revision_number.desc())
        .first()
    )
    if not revision:
        return CapacityDiffResponse(has_changes=False, changed_employees=[])

    # Load absence snapshots
    snaps = (
        db.query(ScenarioAbsenceSnapshot)
        .filter(ScenarioAbsenceSnapshot.revision_id == revision.id)
        .all()
    )
    # Load capacity snapshots for available_hours comparison
    cap_snaps = {
        (s.employee_id, s.year, s.month): s.available_hours
        for s in db.query(ScenarioCapacitySnapshot)
        .filter(ScenarioCapacitySnapshot.revision_id == revision.id)
        .all()
    }

    # Get employee ids from snaps + capacity snaps
    emp_ids = list({s.employee_id for s in snaps if s.employee_id}
                   | {k[0] for k in cap_snaps if k[0]})
    if not emp_ids:
        return CapacityDiffResponse(has_changes=False, changed_employees=[])

    # Quarter date range
    q_num = int(str(scenario.quarter).replace("Q", ""))
    q_months = QUARTER_MONTHS[q_num]
    import calendar as cal_mod
    from datetime import date as date_t
    quarter_start = date_t(scenario.year, q_months[0], 1)
    quarter_end = date_t(scenario.year, q_months[-1],
                         cal_mod.monthrange(scenario.year, q_months[-1])[1])

    # Current absences
    current_absences = (
        db.query(Absence)
        .filter(
            Absence.employee_id.in_(emp_ids),
            Absence.start_date <= quarter_end,
            Absence.end_date >= quarter_start,
        )
        .all()
    )
    current_by_id = {a.id: a for a in current_absences}

    # Snapshot absence ids per employee
    snap_by_emp: dict[str, list[ScenarioAbsenceSnapshot]] = {}
    for s in snaps:
        snap_by_emp.setdefault(s.employee_id, []).append(s)

    # Current absence ids per employee
    current_by_emp: dict[str, list[Absence]] = {}
    for a in current_absences:
        current_by_emp.setdefault(a.employee_id, []).append(a)

    # Load employee names
    employees = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()}

    # Reason labels for current absences
    reason_ids = [a.reason_id for a in current_absences if a.reason_id]
    reasons = {}
    if reason_ids:
        from app.models import AbsenceReason
        reasons = {r.id: r.label for r in db.query(AbsenceReason).filter(AbsenceReason.id.in_(reason_ids)).all()}

    capacity_svc = CapacityService(db)
    changed_employees: list[EmployeeDiff] = []

    for emp_id in emp_ids:
        month_diffs: list[MonthDiff] = []
        snapped = {s.original_absence_id: s for s in snap_by_emp.get(emp_id, []) if s.original_absence_id}
        current_ids = {a.id for a in current_by_emp.get(emp_id, [])}

        for month in q_months:
            snap_avail = cap_snaps.get((emp_id, scenario.year, month))
            if snap_avail is None:
                continue
            mc = capacity_svc.monthly_capacity(emp_id, scenario.year, month)
            current_avail = mc.available_hours
            delta = round(current_avail - snap_avail, 2)

            # Absence-level changes
            absence_changes: list[AbsenceChange] = []
            # Removed: in snapshot but not in current
            for orig_id, snap_ab in snapped.items():
                if orig_id not in current_ids:
                    if snap_ab.start_date.month == month or snap_ab.end_date.month == month:
                        absence_changes.append(AbsenceChange(
                            type="removed",
                            start_date=snap_ab.start_date,
                            end_date=snap_ab.end_date,
                            reason=snap_ab.reason_label,
                            hours=snap_ab.hours_total,
                        ))
            # Added: in current but not in snapshot
            for cur_ab in current_by_emp.get(emp_id, []):
                if cur_ab.id not in snapped:
                    if cur_ab.start_date.month == month or cur_ab.end_date.month == month:
                        absence_changes.append(AbsenceChange(
                            type="added",
                            start_date=cur_ab.start_date,
                            end_date=cur_ab.end_date,
                            reason=reasons.get(cur_ab.reason_id) if cur_ab.reason_id else None,
                            hours=cur_ab.hours_total,
                        ))

            if abs(delta) > 0.1 or absence_changes:
                month_diffs.append(MonthDiff(
                    year=scenario.year,
                    month=month,
                    snapshot_available_hours=snap_avail,
                    current_available_hours=current_avail,
                    delta_hours=delta,
                    absence_changes=absence_changes,
                ))

        if month_diffs:
            emp = employees.get(emp_id)
            changed_employees.append(EmployeeDiff(
                employee_id=emp_id,
                employee_name=emp.display_name if emp else emp_id,
                months=month_diffs,
            ))

    return CapacityDiffResponse(
        has_changes=len(changed_employees) > 0,
        changed_employees=changed_employees,
    )


@router.patch("/scenarios/{scenario_id}/acknowledge-drift")
async def acknowledge_capacity_drift(
    scenario_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Пометить изменения доступности как просмотренные."""
    scenario = db.get(PlanningScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.capacity_drift_acknowledged_at = datetime.utcnow()
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["planning"]})
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```bash
py -3.10 -m pytest tests/test_capacity_snapshot.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ tests/
git commit -m "feat(planning): capacity diff endpoint + acknowledge drift"
```

---

### Task 15: Dashboard norm-work reads from snapshot

**Files:**
- Modify: `app/services/analytics_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_analytics.py — add
def test_norm_work_reads_plan_from_snapshot(client, db_session):
    """norm-work plan_hours must come from ScenarioNormSnapshot, not dynamic recalc."""
    # Setup: approved scenario + ScenarioNormSnapshot rows with known norm_hours
    from app.models import ScenarioNormSnapshot, ScenarioRevision, PlanningScenario
    scenario = PlanningScenario(id="sc-dash", name="Q2 dash", quarter="Q2", year=2026, status="approved", team="T1")
    revision = ScenarioRevision(id="rev-dash", scenario_id="sc-dash", revision_number=1, approved_at=datetime.utcnow())
    db_session.add_all([scenario, revision])
    wt = MandatoryWorkType(id="wt-dash", code="projects", label="Проекты", is_active=True, sort_order=1, subtracts_from_pool=False)
    db_session.add(wt)
    snap = ScenarioNormSnapshot(
        id="ns-1", revision_id="rev-dash", employee_id=None, employee_name="X",
        role="analyst", year=2026, month=4, work_type_id="wt-dash", work_type_label="Проекты", norm_hours=42.0,
    )
    db_session.add(snap)
    db_session.commit()

    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    item = next((i for i in data["items"] if i["work_type_id"] == "wt-dash"), None)
    assert item is not None
    assert item["plan_hours"] == 42.0
```

- [ ] **Step 2: Update get_dashboard_norm_work to read from snapshot**

In `app/services/analytics_service.py`, replace the `plan_by_work_type` computation block (currently uses `ResourceBaseService.compute_summary`) with snapshot read:

```python
def get_dashboard_norm_work(
    self,
    year: int,
    quarter: int,
    month: Optional[int] = None,
    teams: Optional[list[str]] = None,
) -> DashboardNormWorkResponse:
    ...
    # 3. План из снапшота утверждённого сценария
    plan_by_work_type: dict[str, float] = {}
    backlog_plan_hours: float = 0.0

    if approved_scenario:
        latest_revision = (
            self.db.query(ScenarioRevision)
            .filter(ScenarioRevision.scenario_id == approved_scenario.id)
            .order_by(ScenarioRevision.revision_number.desc())
            .first()
        )
        if latest_revision:
            snap_q = (
                self.db.query(
                    ScenarioNormSnapshot.work_type_id,
                    func.sum(ScenarioNormSnapshot.norm_hours).label("total"),
                )
                .filter(ScenarioNormSnapshot.revision_id == latest_revision.id)
                .filter(ScenarioNormSnapshot.year == year)
            )
            if month:
                snap_q = snap_q.filter(ScenarioNormSnapshot.month == month)
            else:
                snap_q = snap_q.filter(ScenarioNormSnapshot.month.in_(QUARTER_MONTHS[quarter]))

            if teams:
                from app.models import EmployeeTeam
                emp_ids_in_teams = [
                    r[0] for r in
                    self.db.query(EmployeeTeam.employee_id)
                    .filter(EmployeeTeam.team.in_(teams))
                    .all()
                ]
                snap_q = snap_q.filter(ScenarioNormSnapshot.employee_id.in_(emp_ids_in_teams))

            for wt_id, total in snap_q.group_by(ScenarioNormSnapshot.work_type_id).all():
                if wt_id:
                    plan_by_work_type[wt_id] = round(total, 2)

        # backlog plan hours (keep existing logic)
        ...
```

Add missing import at top: `from app.models.scenario_norm_snapshot import ScenarioNormSnapshot`

- [ ] **Step 3: Run tests**

```bash
py -3.10 -m pytest tests/test_analytics.py -v
```

- [ ] **Step 4: Commit**

```bash
git add app/services/analytics_service.py
git commit -m "feat(analytics): norm-work reads plan from ScenarioNormSnapshot"
```

---

### Task 16: Frontend — scenario capacity drift indicator (A3)

**Files:**
- Modify: `frontend/src/api/planning.ts`
- Modify: `frontend/src/hooks/usePlanning.ts`
- Modify: `frontend/src/pages/PlanningPage.tsx`
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add CapacityDiff types to api.ts**

In `frontend/src/types/api.ts`, add:

```typescript
export interface AbsenceChange {
  type: 'added' | 'removed';
  start_date: string;
  end_date: string;
  reason: string | null;
  hours: number;
}

export interface MonthDiff {
  year: number;
  month: number;
  snapshot_available_hours: number;
  current_available_hours: number;
  delta_hours: number;
  absence_changes: AbsenceChange[];
}

export interface EmployeeDiff {
  employee_id: string;
  employee_name: string;
  months: MonthDiff[];
}

export interface CapacityDiffResponse {
  has_changes: boolean;
  changed_employees: EmployeeDiff[];
}
```

- [ ] **Step 2: Add API functions to planning.ts**

In `frontend/src/api/planning.ts`, add:

```typescript
export function fetchCapacityDiff(scenarioId: string, signal?: AbortSignal): Promise<CapacityDiffResponse> {
  return api.get<CapacityDiffResponse>(`/planning/scenarios/${scenarioId}/capacity-diff`, {}, signal);
}

export function acknowledgeDrift(scenarioId: string): Promise<{ ok: boolean }> {
  return api.patch<{ ok: boolean }>(`/planning/scenarios/${scenarioId}/acknowledge-drift`, {});
}
```

- [ ] **Step 3: Add hook to usePlanning.ts**

In `frontend/src/hooks/usePlanning.ts`, add:

```typescript
export function useCapacityDiff(scenarioId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['capacity-diff', scenarioId],
    queryFn: ({ signal }) => fetchCapacityDiff(scenarioId!, signal),
    enabled: enabled && !!scenarioId,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useAcknowledgeDrift() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scenarioId: string) => acknowledgeDrift(scenarioId),
    onSuccess: (_, scenarioId) => {
      qc.invalidateQueries({ queryKey: ['capacity-diff', scenarioId] });
      qc.invalidateQueries({ queryKey: ['scenarios'] });
    },
  });
}
```

- [ ] **Step 4: Create CapacityDriftIndicator component inline in PlanningPage**

In `frontend/src/pages/PlanningPage.tsx`, add a component `CapacityDriftIndicator`:

```tsx
const MONTH_NAMES = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

function CapacityDriftIndicator({ scenarioId }: { scenarioId: string }) {
  const [expanded, setExpanded] = useState(false);
  const { data: diff } = useCapacityDiff(scenarioId, true);
  const acknowledge = useAcknowledgeDrift();

  if (!diff?.has_changes) return null;

  const totalAffected = diff.changed_employees.length;

  return (
    <div style={{
      border: '1px solid rgba(245,158,11,0.5)',
      borderRadius: 8,
      background: 'rgba(245,158,11,0.04)',
      padding: '8px 12px',
      marginTop: 8,
    }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
      >
        <span style={{ color: '#f59e0b' }}>⚠</span>
        <span style={{ fontSize: 12, color: '#f59e0b', fontWeight: 600 }}>
          Доступность изменилась ({totalAffected} {totalAffected === 1 ? 'чел.' : 'чел.'})
        </span>
        <span style={{ color: '#64748b', fontSize: 11, marginLeft: 'auto' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: 8 }}>
          {diff.changed_employees.map(emp => (
            <div key={emp.employee_id} style={{ marginBottom: 6 }}>
              {emp.months.map(m => (
                <div key={`${m.year}-${m.month}`} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '4px 6px', background: 'rgba(245,158,11,0.07)',
                  borderRadius: 5, fontSize: 12, marginBottom: 3,
                }}>
                  <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{emp.employee_name}</span>
                  <span style={{ color: '#64748b' }}>|</span>
                  <span style={{ color: '#94a3b8' }}>{MONTH_NAMES[m.month]}:</span>
                  <span style={{ color: '#94a3b8' }}>{Math.round(m.snapshot_available_hours)} → {Math.round(m.current_available_hours)} ч</span>
                  {m.delta_hours > 0
                    ? <span style={{ color: '#22c55e', fontWeight: 700 }}>+{Math.round(m.delta_hours)} ч</span>
                    : <span style={{ color: '#f87171', fontWeight: 700 }}>{Math.round(m.delta_hours)} ч</span>
                  }
                  {m.absence_changes.map((ac, i) => (
                    <span key={i} style={{ color: '#64748b', fontSize: 11 }}>
                      {ac.type === 'removed' ? 'Удалено' : 'Добавлено'}: {ac.reason ?? 'отсутствие'} {ac.start_date}–{ac.end_date} ({Math.round(ac.hours)} ч)
                    </span>
                  ))}
                </div>
              ))}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <Button size="small" type="default" style={{ borderColor: '#f59e0b', color: '#f59e0b' }}>
              Пересмотреть сценарий
            </Button>
            <Button
              size="small"
              style={{ color: '#64748b', borderColor: 'rgba(255,255,255,0.15)' }}
              loading={acknowledge.isPending}
              onClick={() => acknowledge.mutate(scenarioId)}
            >
              Игнорировать
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Render indicator on approved scenarios**

In `PlanningPage.tsx`, find where approved scenario cards/headers are rendered. After the status badge, add:

```tsx
{scenario.status === 'approved' && (
  <CapacityDriftIndicator scenarioId={scenario.id} />
)}
```

- [ ] **Step 6: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 7: Test visually**

1. Open /planning, find an approved scenario
2. Go to /resources → Absences, delete an absence for a team member
3. Return to /planning → amber indicator should appear on the approved scenario
4. Expand indicator → see employee name, month, delta hours, and absence change detail
5. Click "Игнорировать" → indicator disappears

- [ ] **Step 8: Commit**

```bash
git add frontend/src/
git commit -m "feat(planning): capacity drift indicator A3 on approved scenarios"
```

---

## Phase 5 — Final Checks

### Task 17: Push and verify CI

- [ ] **Step 1: Run full test suite**

```bash
py -3.10 -m pytest tests/ -v
```

Expected: all pass (or only pre-existing failures).

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Lint**

```bash
ruff check app/ tests/
```

- [ ] **Step 4: Push**

```bash
git push origin main
```

- [ ] **Step 5: Monitor CI**

Check GitHub Actions. Expected: green on Python tests and frontend build.
