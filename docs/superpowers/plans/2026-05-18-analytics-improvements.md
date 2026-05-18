# Analytics Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user grouping reorder, % in group column, foreign counter on aggregated rows, owner team tag, KPI tiles, bar-in-cell to the hierarchical Analytics report. Rename column-settings drawer to "Настройка отчёта".

**Architecture:** Backend extends `NodeTotals` with new aggregated fields; group reorder happens client-side via reshuffling the response by visible level layout. Per-user layout stored in new JSON column `User.analytics_layout_raw` alongside existing `selected_teams_raw`, `analytics_columns_raw`. Frontend `AnalyticsTable` is refactored to a universal layout-driven builder.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic batch migrations. React 19 + TypeScript 6 + Vite 8 + AntD 6 + TanStack Query + `@dnd-kit/core` (already in deps).

**Spec:** [docs/superpowers/specs/2026-05-18-analytics-improvements-design.md](../specs/2026-05-18-analytics-improvements-design.md)

---

## File Structure

### Backend

**Modify:**
- `app/schemas/analytics_report.py` — extend `NodeTotals`
- `app/services/analytics_service.py` — compute `pct_in_group` + `foreign_*` aggregates in `calc_totals` (and equivalent helper at lower levels)
- `app/models/user.py` — add `analytics_layout_raw` column + property
- `app/api/endpoints/users.py` — add `GET/PUT /me/analytics-layout`
- `tests/test_analytics_hierarchical_report.py` (or similar existing file) — new tests

**Create:**
- `alembic/versions/049_user_analytics_layout.py` (number autogen) — adds column

### Frontend

**Modify:**
- `frontend/src/types/api.ts` — extend `NodeTotals`
- `frontend/src/api/analytics.ts` (or where layout API lives) — add layout client
- `frontend/src/pages/AnalyticsPage.tsx` — render KPI tiles + pass `layout` to table; rename "Настройка столбцов" → "Настройка отчёта"
- `frontend/src/components/analytics/AnalyticsTable.tsx` — universal `buildTreeFromLayout`, foreign chip, owner team tag, bar-in-cell, `% в группе` column
- `frontend/src/hooks/useAnalyticsColumns.ts` — add `pct_in_group` to default visible, demote `pct_total` to default-hidden for *new* users
- `frontend/src/components/analytics/AnalyticsColumnSettings.tsx` → rename file → `AnalyticsReportSettings.tsx`, extend with Grouping section

**Create:**
- `frontend/src/hooks/useAnalyticsLayout.ts` — read/write `/me/analytics-layout`
- `frontend/src/components/analytics/AnalyticsKpiTiles.tsx` — 5 KPI tiles above the table
- `frontend/src/components/analytics/GroupingEditor.tsx` — drag-and-drop level reorder/hide with presets (used inside report settings)

---

## Task 1: Extend `NodeTotals` schema

**Files:**
- Modify: `app/schemas/analytics_report.py:8-16`

- [ ] **Step 1: Add new fields to `NodeTotals`**

Replace the `NodeTotals` class with:

```python
class NodeTotals(BaseModel):
    fact_hours: float
    plan_hours: Optional[float] = None
    pct_plan: Optional[float] = None
    pct_total: float
    pct_in_group: Optional[float] = None
    worklog_count: int
    issue_count: int
    employee_count: int
    avg_worklog_minutes: float
    foreign_issue_count: int = 0
    foreign_hours: float = 0.0
    foreign_pct: float = 0.0
```

- [ ] **Step 2: Run pytest to ensure import still works**

Run: `py -3.10 -m pytest tests/test_analytics_report.py -v -x` (or any test that imports the schema).
Expected: existing tests pass (defaults make new fields optional).

- [ ] **Step 3: Commit**

```bash
git add app/schemas/analytics_report.py
git commit -m "feat(analytics): extend NodeTotals with pct_in_group + foreign aggregates"
```

---

## Task 2: Compute `pct_in_group` + foreign aggregates in `AnalyticsService`

**Files:**
- Modify: `app/services/analytics_service.py:51-53, 1445-1462, ~1495-1580`

Backend already aggregates foreign worklogs into a separate `other_foreign` work_type, but doesn't surface counts on aggregated rows. Adding fields below the existing `calc_totals` keeps logic centralized.

- [ ] **Step 1: Update `_empty_totals` helper near line 51**

Find the `_empty_totals` (or `EMPTY_TOTALS`) constant/helper near the top of `analytics_service.py`. Replace its body so the new fields default to 0:

```python
def _empty_totals() -> NodeTotals:
    return NodeTotals(
        fact_hours=0.0,
        plan_hours=None,
        pct_plan=None,
        pct_total=0.0,
        pct_in_group=None,
        worklog_count=0,
        issue_count=0,
        employee_count=0,
        avg_worklog_minutes=0.0,
        foreign_issue_count=0,
        foreign_hours=0.0,
        foreign_pct=0.0,
    )
```

If the constant is `EMPTY_TOTALS` (not a function), update it analogously.

- [ ] **Step 2: Update inner `calc_totals` in `get_hierarchical_report` (~line 1445)**

Replace the existing nested `def calc_totals(...)` with:

```python
def calc_totals(
    rows: list[dict],
    plan_hours: "float | None" = None,
    emp_count: int = 0,
    parent_total: "float | None" = None,
    parent_fact: "float | None" = None,
) -> NodeTotals:
    fact = sum(r["fact_hours"] for r in rows)
    wl = sum(r["wl_count"] for r in rows)
    issues = len({r["issue_id"] for r in rows})
    avg_min = (fact * 60 / wl) if wl else 0.0
    pct_plan = (fact / plan_hours * 100) if plan_hours and plan_hours > 0 else None
    pct_total = (fact / parent_total * 100) if parent_total and parent_total > 0 else 0.0
    pct_in_group = (
        (fact / parent_fact * 100)
        if parent_fact and parent_fact > 0
        else None
    )
    foreign_rows = [r for r in rows if r.get("is_foreign")]
    foreign_hours = sum(r["fact_hours"] for r in foreign_rows)
    foreign_issue_count = len({r["issue_id"] for r in foreign_rows})
    foreign_pct = (foreign_hours / fact * 100) if fact > 0 else 0.0
    return NodeTotals(
        fact_hours=round(fact, 1),
        plan_hours=round(plan_hours, 1) if plan_hours is not None else None,
        pct_plan=round(pct_plan, 1) if pct_plan is not None else None,
        pct_total=round(pct_total, 1),
        pct_in_group=round(pct_in_group, 1) if pct_in_group is not None else None,
        worklog_count=wl,
        issue_count=issues,
        employee_count=emp_count,
        avg_worklog_minutes=round(avg_min, 1),
        foreign_issue_count=foreign_issue_count,
        foreign_hours=round(foreign_hours, 1),
        foreign_pct=round(foreign_pct, 1),
    )
```

- [ ] **Step 3: Thread `parent_fact` through the tree assembly (lines ~1494-1580)**

In `get_hierarchical_report`, replace the assembly loop so each level passes its OWN fact total down as `parent_fact` to children. The structure already builds bottom-up; rewire the calls (only `calc_totals` invocations change):

Find each `calc_totals(...)` call inside the loops and ensure the right `parent_fact`:

1. **Issue level** (line ~1503): parent_fact = category's fact for now → we don't know it until category is built. Solution: compute category fact first, then build issues with `parent_fact=cat_fact`. Refactor like this:

```python
for cat_code, issues_list in cats_dict.items():
    cat_fact = sum(r["fact_hours"] for r in issues_list)
    cat_label, cat_color, _ = cat_meta.get(
        cat_code or "", (ORPHAN_CAT_LABEL, "#7e94b8", None)
    )
    issues_out: list[AnalyticsIssueNode] = []
    for v in issues_list:
        issues_out.append(AnalyticsIssueNode(
            id=v["issue_id"], key=v["key"], summary=v["summary"],
            status=v["status"], status_category=v["status_category"],
            issue_type=v["issue_type"], category=v["category"],
            last_worklog_at=v["last_at"],
            assignee_name=v.get("assignee_name"),
            is_foreign=v.get("is_foreign", False),
            totals=calc_totals(
                [v],
                parent_total=grand_total_fact,
                parent_fact=cat_fact,
            ),
        ))
    cats_out.append(AnalyticsCategoryNode(
        category_code=cat_code,
        label=cat_label, color=cat_color,
        totals=calc_totals(
            issues_list,
            parent_total=grand_total_fact,
            parent_fact=None,  # set later when work-type fact known
        ),
        issues=sorted(issues_out, key=lambda x: -x.totals.fact_hours),
    ))
    wt_rows.extend(issues_list)
```

2. **WorkType level** — keep aggregation; once `wt_fact` known, build the node and pass to category-build retroactively? Simpler: do two-pass. After building `cats_out` provisionally with `parent_fact=None`, recompute each category's `pct_in_group` and re-emit. Alternative: precompute fact totals for every layer first, then build nodes in one pass.

The cleanest path is **precompute fact totals top-down**, then build nodes. Reorder the build:

```python
# After building `bucket` and `tree`, precompute fact-per-key at every layer.
def _sum_issues(rows): return sum(r["fact_hours"] for r in rows)

# Walk tree once to collect facts by key.
team_fact: dict[str, float] = {}
role_fact: dict[tuple[str, str], float] = {}
emp_fact: dict[tuple[str, str, str], float] = {}
wt_fact: dict[tuple[str, str, str, str], float] = {}
cat_fact: dict[tuple[str, str, str, str, str | None], float] = {}

for team_key, roles_dict in tree.items():
    t_total = 0.0
    for role_key, emps_dict in roles_dict.items():
        r_total = 0.0
        for emp_id, wts_dict in emps_dict.items():
            e_total = 0.0
            for wt_id, cats_dict in wts_dict.items():
                w_total = 0.0
                for cat_code, issues_list in cats_dict.items():
                    c = _sum_issues(issues_list)
                    cat_fact[(team_key, role_key, emp_id, wt_id, cat_code)] = c
                    w_total += c
                wt_fact[(team_key, role_key, emp_id, wt_id)] = w_total
                e_total += w_total
            emp_fact[(team_key, role_key, emp_id)] = e_total
            r_total += e_total
        role_fact[(team_key, role_key)] = r_total
        t_total += r_total
    team_fact[team_key] = t_total
```

Then in the build loop pass the right `parent_fact`:
- Team `parent_fact = None` (root has no parent in group)
- Role `parent_fact = team_fact[team_key]`
- Employee `parent_fact = role_fact[(team_key, role_key)]`
- WorkType `parent_fact = emp_fact[(team_key, role_key, emp_id)]`
- Category `parent_fact = wt_fact[(team_key, role_key, emp_id, wt_id)]`
- Issue `parent_fact = cat_fact[(team_key, role_key, emp_id, wt_id, cat_code)]`

Replace the existing `calc_totals(...)` calls in the assembly loop with these `parent_fact` values.

- [ ] **Step 4: Update `grand_totals` block (line ~1576) to include grand foreign totals**

Replace the grand totals construction:

```python
all_rows = list(bucket.values())
all_foreign = [r for r in all_rows if r.get("is_foreign")]
grand_foreign_hours = sum(r["fact_hours"] for r in all_foreign)
grand_foreign_issues = len({r["issue_id"] for r in all_foreign})
grand_foreign_pct = (
    (grand_foreign_hours / grand_total_fact * 100)
    if grand_total_fact > 0 else 0.0
)
return AnalyticsReportResponse(
    teams=teams_out,
    grand_totals=NodeTotals(
        fact_hours=round(grand_total_fact, 1),
        plan_hours=round(grand_plan, 1) if grand_plan > 0 else None,
        pct_plan=(
            round(grand_total_fact / grand_plan * 100, 1)
            if grand_plan > 0 else None
        ),
        pct_total=100.0 if grand_total_fact > 0 else 0.0,
        pct_in_group=None,
        worklog_count=total_wl,
        issue_count=len({v["issue_id"] for v in bucket.values()}),
        employee_count=len(all_emp_ids),
        avg_worklog_minutes=round(
            (grand_total_fact * 60 / total_wl) if total_wl else 0.0, 1
        ),
        foreign_issue_count=grand_foreign_issues,
        foreign_hours=round(grand_foreign_hours, 1),
        foreign_pct=round(grand_foreign_pct, 1),
    ),
)
```

- [ ] **Step 5: Run the analytics service tests to make sure nothing regressed**

Run: `py -3.10 -m pytest tests/ -k analytics -v -x`
Expected: all existing tests pass (defaults preserve behavior).

- [ ] **Step 6: Commit**

```bash
git add app/services/analytics_service.py
git commit -m "feat(analytics): compute pct_in_group + foreign aggregates per node"
```

---

## Task 3: Add backend tests for new fields

**Files:**
- Create: `tests/test_analytics_pct_in_group.py`

- [ ] **Step 1: Look at existing analytics test patterns**

Run: `py -3.10 -m pytest tests/ -k analytics --collect-only`. Pick the most similar fixture-using file (e.g. `tests/test_analytics_hierarchical.py`) and reuse its fixture wiring.

- [ ] **Step 2: Write failing tests**

Create `tests/test_analytics_pct_in_group.py`:

```python
"""Тесты для новых полей NodeTotals: pct_in_group + foreign_*."""
from datetime import datetime, timezone

import pytest

from app.services.analytics_service import AnalyticsService


def test_pct_in_group_root_is_none(client, seeded_data):
    """На корневых строках (Team) pct_in_group = None — нет родителя в группе."""
    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2},
    )
    assert response.status_code == 200
    data = response.json()
    for team in data["teams"]:
        assert team["totals"]["pct_in_group"] is None


def test_pct_in_group_child_sums_to_100(client, seeded_data):
    """Сумма pct_in_group у детей одного родителя должна быть ~100% (если факт > 0)."""
    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2},
    )
    data = response.json()
    for team in data["teams"]:
        if team["totals"]["fact_hours"] == 0:
            continue
        total = sum(
            r["totals"]["pct_in_group"] or 0 for r in team["roles"]
        )
        assert 99.0 <= total <= 101.0, f"team {team['team']}: {total}"


def test_foreign_aggregation_propagates(client, seeded_foreign_data):
    """foreign_issue_count / foreign_hours агрегируются снизу вверх."""
    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2},
    )
    data = response.json()
    grand = data["grand_totals"]
    # The fixture seeds at least one foreign worklog
    assert grand["foreign_issue_count"] >= 1
    assert grand["foreign_hours"] > 0


def test_foreign_pct_correct_at_employee_level(client, seeded_foreign_data):
    """foreign_pct сотрудника = его чужие часы / все часы * 100."""
    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2},
    )
    data = response.json()
    for team in data["teams"]:
        for role in team["roles"]:
            for emp in role["employees"]:
                t = emp["totals"]
                if t["fact_hours"] == 0:
                    continue
                expected = round(t["foreign_hours"] / t["fact_hours"] * 100, 1)
                assert abs(t["foreign_pct"] - expected) < 0.2, (
                    f"emp {emp['name']}: got {t['foreign_pct']}, expected {expected}"
                )
```

If the existing test suite already has a fixture `seeded_data` or `seeded_foreign_data`, reuse it. Otherwise add a minimal fixture at the top of the file:

```python
@pytest.fixture
def seeded_foreign_data(db_session):
    # Seed 2 teams, 2 employees, 1 worklog on own task + 1 on foreign task.
    # Use existing factory helpers if present, otherwise create models inline.
    ...
```

- [ ] **Step 3: Run tests to confirm they pass**

Run: `py -3.10 -m pytest tests/test_analytics_pct_in_group.py -v -x`
Expected: PASS.

If a fixture is missing, write a minimal in-line `seeded_foreign_data` that constructs Employee, EmployeeTeam, Project, Issue (one with `team="Core"`, one with `team="Other"`), and two Worklog records. The employee should have a primary team of "Core" so the second worklog is classified as foreign.

- [ ] **Step 4: Commit**

```bash
git add tests/test_analytics_pct_in_group.py
git commit -m "test(analytics): pct_in_group + foreign aggregates"
```

---

## Task 4: Add `User.analytics_layout_raw` column

**Files:**
- Modify: `app/models/user.py:30-46, 80-90`
- Create: `alembic/versions/<auto>_user_analytics_layout.py`

- [ ] **Step 1: Add column + property accessor in `User`**

In `app/models/user.py`, add after `analytics_columns_raw` (around line 39):

```python
analytics_layout_raw: Mapped[str] = mapped_column(
    "analytics_layout", Text, nullable=False, default="{}", server_default="{}"
)
```

Add property + setter after the existing `analytics_columns` accessor (around line 78):

```python
@property
def analytics_layout(self) -> dict:
    try:
        return json.loads(self.analytics_layout_raw or "{}")
    except (TypeError, ValueError):
        return {}

@analytics_layout.setter
def analytics_layout(self, value: dict) -> None:
    self.analytics_layout_raw = json.dumps(value or {})
```

- [ ] **Step 2: Generate migration**

Run: `py -3.10 -m alembic revision --autogenerate -m "user_analytics_layout"`

Open the generated file under `alembic/versions/`. Verify it adds the column inside a batch operation (SQLite):

```python
def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "analytics_layout",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )

def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("analytics_layout")
```

If autogenerate produced something else (or wrapped in `op.add_column` without batch), rewrite to match the example above.

- [ ] **Step 3: Apply migration**

Run: `py -3.10 -m alembic upgrade head`
Expected: migration applies cleanly.

- [ ] **Step 4: Sanity-check model loads**

Run: `py -3.10 -c "from app.models.user import User; print(User.analytics_layout_raw.property.columns[0].name)"`
Expected output: `analytics_layout`.

- [ ] **Step 5: Commit**

```bash
git add app/models/user.py alembic/versions/*_user_analytics_layout.py
git commit -m "feat(model): User.analytics_layout JSON column + property"
```

---

## Task 5: Add `/me/analytics-layout` endpoints

**Files:**
- Modify: `app/api/endpoints/users.py:1-103`

- [ ] **Step 1: Add payload schema + endpoints**

Append at the bottom of `app/api/endpoints/users.py`:

```python
class AnalyticsLayoutPayload(BaseModel):
    layout: dict


@router.get("/me/analytics-layout")
def get_my_analytics_layout(current_user: User = Depends(get_current_user)):
    return {"layout": current_user.analytics_layout}


@router.put("/me/analytics-layout")
def set_my_analytics_layout(
    payload: AnalyticsLayoutPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.analytics_layout = payload.layout
    db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Write endpoint test**

Add to `tests/test_users_self_service.py` (or create new file `tests/test_analytics_layout_endpoint.py`):

```python
def test_get_default_analytics_layout(authed_client):
    response = authed_client.get("/api/v1/users/me/analytics-layout")
    assert response.status_code == 200
    assert response.json() == {"layout": {}}


def test_put_then_get_layout(authed_client):
    payload = {
        "layout": {
            "group_order": ["employee", "category", "issue"],
            "hidden_levels": ["team", "role", "work_type"],
            "active_preset": "people",
        }
    }
    put = authed_client.put("/api/v1/users/me/analytics-layout", json=payload)
    assert put.status_code == 200
    got = authed_client.get("/api/v1/users/me/analytics-layout")
    assert got.json()["layout"] == payload["layout"]
```

If `authed_client` fixture doesn't exist, reuse the pattern from existing user-endpoint tests (`tests/test_users_columns.py` or similar).

- [ ] **Step 3: Run test**

Run: `py -3.10 -m pytest tests/test_analytics_layout_endpoint.py -v -x`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/users.py tests/test_analytics_layout_endpoint.py
git commit -m "feat(api): GET/PUT /me/analytics-layout for per-user grouping"
```

---

## Task 6: Update frontend types

**Files:**
- Modify: `frontend/src/types/api.ts` (find the `NodeTotals` interface)

- [ ] **Step 1: Extend `NodeTotals` interface**

Find `NodeTotals` (or analogous) in `frontend/src/types/api.ts`. Replace with:

```typescript
export interface NodeTotals {
  fact_hours: number;
  plan_hours: number | null;
  pct_plan: number | null;
  pct_total: number;
  pct_in_group: number | null;
  worklog_count: number;
  issue_count: number;
  employee_count: number;
  avg_worklog_minutes: number;
  foreign_issue_count: number;
  foreign_hours: number;
  foreign_pct: number;
}
```

- [ ] **Step 2: Run typescript build**

Run: `cd frontend && npm run build`
Expected: build succeeds. Existing usages of `NodeTotals` only read fields, new fields are optional add-ons.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(analytics-fe): extend NodeTotals types with pct_in_group + foreign"
```

---

## Task 7: Create `useAnalyticsLayout` hook + API client

**Files:**
- Create: `frontend/src/hooks/useAnalyticsLayout.ts`
- Modify: `frontend/src/api/analytics.ts` (or wherever analytics API calls live)

- [ ] **Step 1: Add API client functions**

In the analytics API client file (find it via `grep -r "analytics/report" frontend/src/api`), append:

```typescript
export interface AnalyticsLayout {
  group_order?: AnalyticsLevel[];
  hidden_levels?: AnalyticsLevel[];
  active_preset?: string;
  saved_presets?: { name: string; group_order: AnalyticsLevel[]; hidden_levels: AnalyticsLevel[] }[];
}

export type AnalyticsLevel = 'team' | 'role' | 'employee' | 'work_type' | 'category' | 'issue';

export async function fetchAnalyticsLayout(): Promise<AnalyticsLayout> {
  const res = await api.get<{ layout: AnalyticsLayout }>('users/me/analytics-layout');
  return res.layout ?? {};
}

export async function saveAnalyticsLayout(layout: AnalyticsLayout): Promise<void> {
  await api.put('users/me/analytics-layout', { layout });
}
```

If the existing API helper uses a different signature, adapt accordingly. Path prefix `users/me/...` should match how other `/me/...` calls are made in the codebase.

- [ ] **Step 2: Create the hook**

Create `frontend/src/hooks/useAnalyticsLayout.ts`:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAnalyticsLayout, saveAnalyticsLayout, type AnalyticsLayout, type AnalyticsLevel } from '../api/analytics';

export const DEFAULT_LAYOUT: Required<Pick<AnalyticsLayout, 'group_order' | 'hidden_levels'>> = {
  group_order: ['team', 'role', 'employee', 'work_type', 'category', 'issue'],
  hidden_levels: [],
};

export const ALL_LEVELS: AnalyticsLevel[] = ['team', 'role', 'employee', 'work_type', 'category', 'issue'];

export const LEVEL_LABELS: Record<AnalyticsLevel, string> = {
  team: 'Команда',
  role: 'Роль',
  employee: 'Сотрудник',
  work_type: 'Вид работ',
  category: 'Категория',
  issue: 'Задача',
};

export interface ResolvedLayout {
  visibleLevels: AnalyticsLevel[];
  hiddenLevels: AnalyticsLevel[];
  activePreset?: string;
}

export function resolveLayout(layout: AnalyticsLayout | undefined): ResolvedLayout {
  const order = layout?.group_order && layout.group_order.length > 0
    ? layout.group_order
    : DEFAULT_LAYOUT.group_order;
  const hidden = new Set(layout?.hidden_levels ?? []);
  hidden.delete('issue'); // issue is always visible
  const visibleLevels = order.filter((l) => !hidden.has(l));
  // Always ensure 'issue' is the last visible level
  if (!visibleLevels.includes('issue')) visibleLevels.push('issue');
  return {
    visibleLevels,
    hiddenLevels: Array.from(hidden),
    activePreset: layout?.active_preset,
  };
}

export function useAnalyticsLayout() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['analytics-layout'],
    queryFn: fetchAnalyticsLayout,
    staleTime: 5 * 60_000,
  });
  const mutate = useMutation({
    mutationFn: saveAnalyticsLayout,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics-layout'] }),
  });
  const resolved = resolveLayout(query.data);
  return {
    layout: query.data ?? {},
    resolved,
    isLoading: query.isLoading,
    save: mutate.mutateAsync,
    isSaving: mutate.isPending,
  };
}
```

- [ ] **Step 3: Build to check types**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useAnalyticsLayout.ts frontend/src/api/analytics.ts
git commit -m "feat(analytics-fe): useAnalyticsLayout hook + API client"
```

---

## Task 8: Refactor `AnalyticsTable` to a layout-driven builder

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

The existing builder hardcodes 6 levels. Replace it with one universal `buildTreeFromLayout(data, layout)` that walks the response and pivots rows by the chosen layout.

- [ ] **Step 1: Add a flat-row extractor + new builder at the top of the file**

Add inside `AnalyticsTable.tsx`, before the existing build functions:

```typescript
import type { AnalyticsLevel } from '../../hooks/useAnalyticsLayout';

interface FlatRow {
  team: string;
  team_label: string;
  role: string | null;
  role_label: string;
  role_color: string;
  employee_id: string;
  employee_name: string;
  employee_initials: string;
  work_type_id: string;
  work_type_label: string;
  category_code: string | null;
  category_label: string;
  category_color: string;
  issue: AnalyticsIssueNode;
}

function flattenResponse(data: AnalyticsReportResponse): FlatRow[] {
  const out: FlatRow[] = [];
  for (const t of data.teams) {
    const teamKey = t.team ?? '__no_team__';
    const teamLabel = t.team ?? 'Без команды';
    for (const r of t.roles) {
      for (const e of r.employees) {
        for (const w of e.work_types) {
          for (const c of w.categories) {
            for (const i of c.issues) {
              out.push({
                team: teamKey, team_label: teamLabel,
                role: r.role_code, role_label: r.role_label, role_color: r.role_color,
                employee_id: e.employee_id, employee_name: e.name, employee_initials: e.initials,
                work_type_id: w.work_type_id, work_type_label: w.label,
                category_code: c.category_code, category_label: c.label, category_color: c.color,
                issue: i,
              });
            }
          }
        }
      }
    }
  }
  return out;
}

function keyOf(level: AnalyticsLevel, row: FlatRow): string {
  switch (level) {
    case 'team': return row.team;
    case 'role': return `${row.team}|${row.role ?? '_none'}`;
    case 'employee': return row.employee_id;
    case 'work_type': return row.work_type_id;
    case 'category': return row.category_code ?? '_none';
    case 'issue': return row.issue.id;
  }
}

function labelOf(level: AnalyticsLevel, row: FlatRow): { label: React.ReactNode; meta?: { color?: string } } {
  switch (level) {
    case 'team':
      return { label: <b>{row.team_label}</b> };
    case 'role':
      return {
        label: (
          <span style={{ color: row.role_color, fontWeight: 600 }}>{row.role_label}</span>
        ),
        meta: { color: row.role_color },
      };
    case 'employee':
      return { label: <span>{row.employee_name}</span> };
    case 'work_type':
      return { label: <span style={{ fontWeight: 500 }}>{row.work_type_label}</span> };
    case 'category':
      return {
        label: (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: row.category_color }} />
            {row.category_label}
          </span>
        ),
      };
    case 'issue':
      throw new Error('issue is a leaf, not a group level');
  }
}
```

- [ ] **Step 2: Write `buildTreeFromLayout`**

Add below the helpers above:

```typescript
function aggregateTotals(rows: FlatRow[], parentFact: number | null, grandFact: number): NodeTotals {
  const fact = rows.reduce((s, r) => s + r.issue.totals.fact_hours, 0);
  const issueIds = new Set(rows.map((r) => r.issue.id));
  const empIds = new Set(rows.map((r) => r.employee_id));
  const foreignRows = rows.filter((r) => r.issue.is_foreign);
  const foreignHours = foreignRows.reduce((s, r) => s + r.issue.totals.fact_hours, 0);
  const foreignIssues = new Set(foreignRows.map((r) => r.issue.id));
  const wl = rows.reduce((s, r) => s + r.issue.totals.worklog_count, 0);
  return {
    fact_hours: Math.round(fact * 10) / 10,
    plan_hours: null,
    pct_plan: null,
    pct_total: grandFact > 0 ? Math.round((fact / grandFact) * 1000) / 10 : 0,
    pct_in_group: parentFact && parentFact > 0 ? Math.round((fact / parentFact) * 1000) / 10 : null,
    worklog_count: wl,
    issue_count: issueIds.size,
    employee_count: empIds.size,
    avg_worklog_minutes: wl > 0 ? Math.round((fact * 60 / wl) * 10) / 10 : 0,
    foreign_issue_count: foreignIssues.size,
    foreign_hours: Math.round(foreignHours * 10) / 10,
    foreign_pct: fact > 0 ? Math.round((foreignHours / fact) * 1000) / 10 : 0,
  };
}

function buildTreeFromLayout(
  data: AnalyticsReportResponse,
  layout: AnalyticsLevel[],
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
  navigate: ReturnType<typeof useNavigate>,
  thematicParams: URLSearchParams | null,
): TreeNode[] {
  const flat = flattenResponse(data);
  const grandFact = flat.reduce((s, r) => s + r.issue.totals.fact_hours, 0);

  function group(
    rows: FlatRow[],
    levels: AnalyticsLevel[],
    depth: number,
    keyPrefix: string,
    parentFact: number | null,
  ): TreeNode[] {
    if (rows.length === 0) return [];
    if (levels.length === 0) return [];
    const [head, ...rest] = levels;

    if (head === 'issue') {
      // Render each unique issue once with hours summed across (already pre-summed in response,
      // but a single issue may appear multiple times if employee dim collapsed). Aggregate by issue.id.
      const byId = new Map<string, FlatRow[]>();
      for (const r of rows) {
        const arr = byId.get(r.issue.id) ?? [];
        arr.push(r);
        byId.set(r.issue.id, arr);
      }
      const nodes: TreeNode[] = [];
      for (const [, group] of byId.entries()) {
        const sample = group[0];
        const totals = aggregateTotals(group, parentFact, grandFact);
        const issueLikeRow: AnalyticsIssueNode = {
          ...sample.issue,
          totals,
        };
        const node = buildIssueNode(
          issueLikeRow,
          keyPrefix,
          depth,
          worklogMode,
          periodStart,
          periodEnd,
          navigate,
        );
        nodes.push(node);
      }
      return nodes.sort((a, b) => b.totals.fact_hours - a.totals.fact_hours);
    }

    // Group by head
    const groups = new Map<string, FlatRow[]>();
    for (const r of rows) {
      const k = keyOf(head, r);
      const arr = groups.get(k) ?? [];
      arr.push(r);
      groups.set(k, arr);
    }

    const nodes: TreeNode[] = [];
    for (const [k, rs] of groups.entries()) {
      const sample = rs[0];
      const { label } = labelOf(head, sample);
      const totals = aggregateTotals(rs, parentFact, grandFact);
      const children = group(rs, rest, depth + 1, `${keyPrefix}/${head}:${k}`, totals.fact_hours);
      nodes.push({
        key: `${keyPrefix}/${head}:${k}`,
        kind: kindOfLevel(head),
        depth,
        label: indent(depth, label),
        totals,
        children: children.length > 0 ? children : undefined,
      });
    }
    return nodes.sort((a, b) => b.totals.fact_hours - a.totals.fact_hours);
  }

  return group(flat, layout, 0, 'root', null);
}

function kindOfLevel(level: AnalyticsLevel): RowKind {
  switch (level) {
    case 'team': return 'team';
    case 'role': return 'role';
    case 'employee': return 'emp';
    case 'work_type': return 'wt';
    case 'category': return 'cat';
    case 'issue': return 'issue';
  }
}
```

- [ ] **Step 3: Wire `buildTreeFromLayout` into the component**

In the `AnalyticsTable` component, replace the existing tableData construction (around lines 489-496) with:

```typescript
const { resolved } = useAnalyticsLayout();
const layout = useMemo(() => {
  // Drop hidden + ensure 'issue' is last
  let levels = resolved.visibleLevels;
  if (selectedTeam !== 'all') {
    // when a single team is selected, drop 'team' from grouping (single value anyway)
    levels = levels.filter((l) => l !== 'team');
  }
  if (!levels.includes('issue')) levels.push('issue');
  return levels;
}, [resolved.visibleLevels, selectedTeam]);

const filteredData: AnalyticsReportResponse = useMemo(() => {
  if (selectedTeam === 'all') return data;
  return {
    ...data,
    teams: data.teams.filter((t) => (t.team || '_none_') === selectedTeam),
  };
}, [data, selectedTeam]);

const tableData: TreeNode[] = useMemo(
  () => buildTreeFromLayout(
    filteredData,
    layout,
    worklogMode,
    periodStart,
    periodEnd,
    navigate,
    thematicBaseParams,
  ),
  [filteredData, layout, worklogMode, periodStart, periodEnd, navigate, thematicBaseParams],
);
```

Remove the old fixed builder helpers (`buildTeamNode`, `buildRoleNode`, `buildEmployeeNode`, `buildWorkTypeNode`, `buildCategoryNode`) — keep ONLY `buildIssueNode` since the new code reuses it.

- [ ] **Step 4: Run build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS.

- [ ] **Step 5: Manual smoke**

Start backend and frontend, open `/analytics`. Confirm default 6-level hierarchy still renders identically to before (use existing data).

```bash
# Backend (Windows)
py -3.10 -m uvicorn app.main:app --reload --port 8000
# Frontend
cd frontend && npm run dev
```

If anything looks broken, fix before commit.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "refactor(analytics-fe): universal buildTreeFromLayout driven by user layout"
```

---

## Task 9: Add «% в группе» column

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`
- Modify: `frontend/src/hooks/useAnalyticsColumns.ts`

- [ ] **Step 1: Add new column to `allColumns`**

In `AnalyticsTable.tsx`, find the `allColumns` array (around line 500). Insert a new column right BEFORE the existing `pct_total`:

```typescript
{
  title: '% в группе',
  key: 'pct_in_group',
  render: (_, r) =>
    isBlock(r)
      ? null
      : r.totals.pct_in_group != null
        ? `${r.totals.pct_in_group.toFixed(1)}%`
        : '—',
  width: 100,
  align: 'right',
},
```

- [ ] **Step 2: Update `useAnalyticsColumns` default visible set**

Open `frontend/src/hooks/useAnalyticsColumns.ts`. Find the default columns list. Add `'pct_in_group'` to defaults-visible, demote `'pct_total'` to defaults-hidden:

If the file uses a constant like `DEFAULT_VISIBLE = ['fact_hours', 'plan_hours', 'pct_plan', 'pct_total', ...]`, update to:

```typescript
const DEFAULT_VISIBLE = [
  'fact_hours',
  'plan_hours',
  'pct_plan',
  'pct_in_group',
  // pct_total intentionally not in defaults — show via settings
  'worklog_count',
  'issue_count',
  'employee_count',
  'avg_min',
];
```

If the hook stores in localStorage and falls back to defaults, this only affects new users. Existing users' settings stay as they were.

- [ ] **Step 3: Build + smoke**

Run: `cd frontend && npm run build`
Expected: PASS.

Open `/analytics`. Confirm the new column shows percentages of each row relative to its parent.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsTable.tsx frontend/src/hooks/useAnalyticsColumns.ts
git commit -m "feat(analytics-fe): % в группе column (default visible)"
```

---

## Task 10: Foreign chip on aggregated rows

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

- [ ] **Step 1: Add a small `ForeignChip` component above the main component**

In `AnalyticsTable.tsx`, near the helpers at the top:

```typescript
function ForeignChip({ totals }: { totals: NodeTotals }) {
  if (!totals.foreign_issue_count || totals.foreign_issue_count === 0) return null;
  return (
    <Tooltip title={`Чужие задачи под этим узлом: ${totals.foreign_issue_count} зад. · ${totals.foreign_hours.toFixed(1)}ч · ${totals.foreign_pct.toFixed(1)}% от факта`}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          marginLeft: 8,
          padding: '2px 8px',
          borderRadius: 999,
          fontSize: 11,
          fontWeight: 600,
          background: 'rgba(255, 156, 74, 0.12)',
          color: '#ff9c4a',
          border: '1px solid rgba(255, 156, 74, 0.35)',
        }}
      >
        ⚠ {totals.foreign_issue_count} · {totals.foreign_hours.toFixed(0)}ч · {totals.foreign_pct.toFixed(0)}%
      </span>
    </Tooltip>
  );
}
```

- [ ] **Step 2: Render the chip inside the `Часы факт` cell renderer for aggregated rows**

In `allColumns`, find the `fact_hours` render and extend:

```typescript
{
  title: 'Часы факт',
  key: 'fact_hours',
  render: (_, r) =>
    isBlock(r) ? null : (
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
          {r.totals.fact_hours.toFixed(1)}
        </span>
        {r.kind !== 'issue' && <ForeignChip totals={r.totals} />}
      </span>
    ),
  width: 200, // widen since the chip lives inside
  align: 'right',
},
```

- [ ] **Step 3: Build + smoke**

Run: `cd frontend && npm run build`
Open `/analytics`, drill into a team that has foreign work (e.g. employees with worklogs on tasks of other teams). Confirm the orange chip appears next to facts on Team / Role / Employee / WorkType / Category rows. Skip on issue rows.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(analytics-fe): foreign chip on aggregated rows"
```

---

## Task 11: Owner team tag on foreign issue rows

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

- [ ] **Step 1: Add team-color helper**

If a `teamColor` helper exists in `frontend/src/utils/`, reuse it. Otherwise add at top of file:

```typescript
const TEAM_COLOR_PALETTE = [
  '#9c6bff', '#22d3ee', '#f97316', '#10b981',
  '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4',
];

function teamColor(name: string | null | undefined): string {
  if (!name) return '#7e94b8';
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return TEAM_COLOR_PALETTE[Math.abs(h) % TEAM_COLOR_PALETTE.length];
}
```

- [ ] **Step 2: Render owner team tag in `buildIssueNode`**

In `buildIssueNode`, after the `is_foreign` orange tag, add a second outlined tag with the team name. Note: the response includes `i.team` on `AnalyticsIssueNode`? Check the schema. **If `team` is not on `AnalyticsIssueNode` yet**, add it backend-side first:

- In `app/schemas/analytics_report.py`, on `AnalyticsIssueNode` add: `team: Optional[str] = None`
- In `app/services/analytics_service.py` where the issue row is constructed (search for `AnalyticsIssueNode(`), include `team=v["team"]`. Make sure the bucket dict captured `team` earlier from `Issue.team`.

Then in `frontend/src/types/api.ts`, add `team: string | null` to `AnalyticsIssueNode`.

Then in `buildIssueNode` (TSX):

```typescript
{i.is_foreign && (
  <Tag color="orange" style={{ marginInlineEnd: 0, flexShrink: 0 }}>Чужая</Tag>
)}
{i.is_foreign && i.team && (
  <Tag
    style={{
      marginInlineEnd: 0,
      flexShrink: 0,
      background: 'transparent',
      border: `1px solid ${teamColor(i.team)}`,
      color: teamColor(i.team),
    }}
  >
    {i.team}
  </Tag>
)}
```

- [ ] **Step 3: Run backend tests + frontend build**

```bash
py -3.10 -m pytest tests/ -k analytics -v -x
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Smoke**

Open `/analytics`, find a foreign issue row. Confirm both tags render: orange «Чужая» and a coloured outline tag with the owning team's name.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/analytics_report.py app/services/analytics_service.py frontend/src/types/api.ts frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(analytics): owner team tag on foreign issue rows"
```

---

## Task 12: Bar-in-cell for «Часы факт»

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`

- [ ] **Step 1: Replace the fact_hours render to include a bar**

Extend the `fact_hours` column render (built in Task 10):

```typescript
{
  title: 'Часы факт',
  key: 'fact_hours',
  render: (_, r) => {
    if (isBlock(r)) return null;
    const pct = r.depth === 0
      ? r.totals.pct_total
      : (r.totals.pct_in_group ?? 0);
    const barWidth = Math.min(100, Math.max(0, pct));
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
            {r.totals.fact_hours.toFixed(1)}
          </span>
          {r.kind !== 'issue' && <ForeignChip totals={r.totals} />}
        </span>
        {r.kind !== 'issue' && (
          <div
            style={{
              width: '100%',
              height: 3,
              background: 'rgba(255,255,255,0.06)',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${barWidth}%`,
                height: '100%',
                background: '#00c9c8',
                opacity: 0.85,
              }}
            />
          </div>
        )}
      </div>
    );
  },
  width: 220,
  align: 'right',
},
```

- [ ] **Step 2: Build + smoke**

Run: `cd frontend && npm run build`
Open `/analytics`. Confirm bars appear under numbers on aggregated rows, scaled by share of parent.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsTable.tsx
git commit -m "feat(analytics-fe): bar-in-cell for Часы факт"
```

---

## Task 13: KPI tiles above the table

**Files:**
- Create: `frontend/src/components/analytics/AnalyticsKpiTiles.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 1: Create the component**

```typescript
// frontend/src/components/analytics/AnalyticsKpiTiles.tsx
import type { NodeTotals } from '../../types/api';

interface Props {
  totals: NodeTotals;
}

const TILE: React.CSSProperties = {
  background: '#0f2340',
  borderRadius: 8,
  padding: '14px 18px',
  flex: '1 1 0',
  minWidth: 0,
  border: '1px solid rgba(255,255,255,0.04)',
};

const LABEL: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  color: '#7e94b8',
  marginBottom: 4,
};

const VALUE: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 600,
  color: '#e6edf7',
  lineHeight: 1.1,
};

export default function AnalyticsKpiTiles({ totals }: Props) {
  const pct = totals.plan_hours && totals.plan_hours > 0
    ? (totals.fact_hours / totals.plan_hours) * 100
    : null;
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
      <div style={TILE}>
        <div style={LABEL}>Σ Часов факт</div>
        <div style={VALUE}>{totals.fact_hours.toFixed(1)}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Σ Часов план</div>
        <div style={VALUE}>
          {totals.plan_hours != null ? totals.plan_hours.toFixed(0) : '—'}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>% Выполнения</div>
        <div style={{ ...VALUE, color: pct == null ? '#e6edf7' : pct > 110 ? '#ff4d4f' : pct >= 70 ? '#faad14' : '#67d68d' }}>
          {pct == null ? '—' : `${pct.toFixed(0)}%`}
        </div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Сотрудников</div>
        <div style={VALUE}>{totals.employee_count}</div>
      </div>
      <div style={TILE}>
        <div style={LABEL}>Чужих часов</div>
        <div style={{ ...VALUE, color: totals.foreign_hours > 0 ? '#ff9c4a' : '#e6edf7' }}>
          {totals.foreign_hours.toFixed(1)}
          {totals.foreign_hours > 0 && (
            <span style={{ fontSize: 13, marginLeft: 6, color: '#ff9c4a', fontWeight: 500 }}>
              ({totals.foreign_pct.toFixed(0)}%)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire into `AnalyticsPage`**

Open `frontend/src/pages/AnalyticsPage.tsx`. Import the component:

```typescript
import AnalyticsKpiTiles from '../components/analytics/AnalyticsKpiTiles';
```

In the classic-view branch (around line 218-238), insert the tiles above the grid:

```typescript
) : viewMode === 'detail' ? (
  // ... existing detail branch
) : (
  <>
    <AnalyticsKpiTiles totals={data.grand_totals} />
    <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
      {/* ... existing markup */}
    </div>
  </>
)
```

- [ ] **Step 3: Build + smoke**

Run: `cd frontend && npm run build`
Open `/analytics`. Confirm 5 tiles appear above the table and update with filter / period / team-selection.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsKpiTiles.tsx frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(analytics-fe): KPI tiles above hierarchical table"
```

---

## Task 14: Rename to «Настройка отчёта» + add Grouping editor

**Files:**
- Rename: `frontend/src/components/analytics/AnalyticsColumnSettings.tsx` → `AnalyticsReportSettings.tsx`
- Create: `frontend/src/components/analytics/GroupingEditor.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx` (button label + import)

- [ ] **Step 1: Rename the file and exported component**

```bash
git mv frontend/src/components/analytics/AnalyticsColumnSettings.tsx frontend/src/components/analytics/AnalyticsReportSettings.tsx
```

Inside the new file, rename the default export `AnalyticsColumnSettings` → `AnalyticsReportSettings`. Update the drawer/modal title from «Настройка столбцов» → «Настройка отчёта».

Update the import in `AnalyticsPage.tsx`:

```typescript
import AnalyticsReportSettings from '../components/analytics/AnalyticsReportSettings';
```

Replace usage `<AnalyticsColumnSettings ... />` with `<AnalyticsReportSettings ... />`. Update the button label:

```typescript
<Button icon={<SettingOutlined />} onClick={() => setColumnSettingsOpen(true)}>
  Настройка отчёта
</Button>
```

- [ ] **Step 2: Create `GroupingEditor` component**

```typescript
// frontend/src/components/analytics/GroupingEditor.tsx
import { useMemo } from 'react';
import { Button, Tooltip } from 'antd';
import { EyeOutlined, EyeInvisibleOutlined, DragOutlined } from '@ant-design/icons';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  useAnalyticsLayout,
  DEFAULT_LAYOUT,
  ALL_LEVELS,
  LEVEL_LABELS,
  type AnalyticsLevel,
} from '../../hooks/useAnalyticsLayout';

const PRESETS: { key: string; label: string; order: AnalyticsLevel[]; hidden: AnalyticsLevel[] }[] = [
  {
    key: 'default',
    label: 'Стандарт',
    order: ['team', 'role', 'employee', 'work_type', 'category', 'issue'],
    hidden: [],
  },
  {
    key: 'people',
    label: 'По людям',
    order: ['employee', 'category', 'issue'],
    hidden: ['team', 'role', 'work_type'],
  },
  {
    key: 'categories',
    label: 'По категориям',
    order: ['category', 'work_type', 'issue'],
    hidden: ['team', 'role', 'employee'],
  },
  {
    key: 'work_types',
    label: 'По видам работ',
    order: ['work_type', 'category', 'issue'],
    hidden: ['team', 'role', 'employee'],
  },
];

interface SortableLevelProps {
  level: AnalyticsLevel;
  hidden: boolean;
  onToggleVisible: (level: AnalyticsLevel) => void;
}

function SortableLevel({ level, hidden, onToggleVisible }: SortableLevelProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: level });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    background: hidden ? 'rgba(68, 90, 130, 0.18)' : '#162f54',
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 6,
    padding: '8px 12px',
    marginBottom: 6,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    opacity: hidden ? 0.55 : 1,
    cursor: isDragging ? 'grabbing' : 'default',
  };
  return (
    <div ref={setNodeRef} style={style}>
      <span {...attributes} {...listeners} style={{ cursor: 'grab', color: '#7e94b8' }}>
        <DragOutlined />
      </span>
      <span style={{ flex: 1, color: '#e6edf7' }}>{LEVEL_LABELS[level]}</span>
      <Tooltip title={hidden ? 'Показать уровень' : 'Скрыть уровень'}>
        <Button
          type="text"
          size="small"
          icon={hidden ? <EyeInvisibleOutlined /> : <EyeOutlined />}
          onClick={() => onToggleVisible(level)}
          disabled={level === 'issue'}
        />
      </Tooltip>
    </div>
  );
}

export default function GroupingEditor() {
  const { layout, save, isSaving } = useAnalyticsLayout();
  const order = layout.group_order && layout.group_order.length > 0 ? layout.group_order : DEFAULT_LAYOUT.group_order;
  const hidden = new Set(layout.hidden_levels ?? []);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const oldIndex = order.indexOf(active.id as AnalyticsLevel);
    const newIndex = order.indexOf(over.id as AnalyticsLevel);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(order, oldIndex, newIndex);
    save({ ...layout, group_order: next, active_preset: 'custom' });
  };

  const toggleHidden = (level: AnalyticsLevel) => {
    const nextHidden = new Set(hidden);
    if (nextHidden.has(level)) nextHidden.delete(level);
    else nextHidden.add(level);
    save({ ...layout, hidden_levels: Array.from(nextHidden), active_preset: 'custom' });
  };

  const applyPreset = (preset: typeof PRESETS[number]) => {
    save({
      ...layout,
      group_order: preset.order.concat(ALL_LEVELS.filter((l) => !preset.order.includes(l))),
      hidden_levels: preset.hidden,
      active_preset: preset.key,
    });
  };

  const visibleOrder = useMemo(() => order.filter((l) => !hidden.has(l)), [order, hidden]);
  const hiddenOrder = useMemo(() => order.filter((l) => hidden.has(l)), [order, hidden]);

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {PRESETS.map((p) => (
          <Button
            key={p.key}
            size="small"
            type={layout.active_preset === p.key ? 'primary' : 'default'}
            onClick={() => applyPreset(p)}
            disabled={isSaving}
          >
            {p.label}
          </Button>
        ))}
      </div>

      <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', marginBottom: 6 }}>
        Активные уровни
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={visibleOrder} strategy={verticalListSortingStrategy}>
          {visibleOrder.map((l) => (
            <SortableLevel key={l} level={l} hidden={false} onToggleVisible={toggleHidden} />
          ))}
        </SortableContext>
      </DndContext>

      {hiddenOrder.length > 0 && (
        <>
          <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', marginTop: 16, marginBottom: 6 }}>
            Скрытые
          </div>
          {hiddenOrder.map((l) => (
            <SortableLevel key={l} level={l} hidden onToggleVisible={toggleHidden} />
          ))}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire `GroupingEditor` into `AnalyticsReportSettings`**

In the renamed `AnalyticsReportSettings.tsx`, find the existing drawer/modal content and split into two sections — «Группировка» on top, «Столбцы» below. Example layout (Drawer):

```typescript
import GroupingEditor from './GroupingEditor';

// ... inside the drawer body:
<Drawer title="Настройка отчёта" open={open} onClose={onClose} width={440}>
  <h4 style={{ marginTop: 0, color: '#e6edf7' }}>Группировка</h4>
  <GroupingEditor />

  <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '20px 0' }} />

  <h4 style={{ color: '#e6edf7' }}>Столбцы</h4>
  {/* existing column checkboxes */}
</Drawer>
```

- [ ] **Step 4: Build + smoke**

```bash
cd frontend && npm run build
```

Open `/analytics`, click «Настройка отчёта». Drawer opens with two sections. Drag a level — table reorders. Click a preset — table reorders. Click eye to hide a level — it goes to «Скрытые», table collapses.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/analytics/AnalyticsReportSettings.tsx frontend/src/components/analytics/GroupingEditor.tsx frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat(analytics-fe): rename to Настройка отчёта, add Grouping editor with presets + dnd"
```

---

## Task 15: Final verification — smoke + tests + lint

**Files:** none (verification step)

- [ ] **Step 1: Run full backend tests**

Run: `py -3.10 -m pytest tests/ -v -x`
Expected: no regressions; new tests pass.

- [ ] **Step 2: Run frontend build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS.

- [ ] **Step 3: Manual flow**

Start dev servers (kill old uvicorn first if hung — Windows quirk):

```bash
# Kill uvicorn if running
taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*" 2>nul || true
# Start
py -3.10 -m uvicorn app.main:app --reload --port 8000 &
cd frontend && npm run dev
```

Walk through:
1. Open `/analytics` — see KPI tiles + table with `% в группе` + bars.
2. Open «Настройка отчёта» — drag a level, see table reorder; hide a level, see it disappear; pick a preset, see layout switch.
3. Refresh page — layout persists per user.
4. Find a foreign issue — see «Чужая» tag + owner team tag with colored outline.
5. Drill into a team with foreign work — see orange chip on aggregated rows.

- [ ] **Step 4: Commit any forgotten changes & push**

```bash
git status
git push origin main
```

---

## Self-Review

After writing all tasks, re-checked against spec:

- **Section 1 (Grouping reorder)** → Tasks 4, 5, 7, 8, 14. Spec coverage complete: per-user storage (T4, T5), hook (T7), client-side layout-driven rebuild (T8), UI editor with dnd + presets (T14). Saved presets per-user (named) — present in `PRESETS` constant only as built-in presets; user-named presets are not yet editable through UI (out of MVP scope — accept gap for now, expand later if requested).
- **Section 2 (% columns)** → Tasks 1, 2, 6, 9. Backend computes `pct_in_group` per node; frontend adds column with default visibility.
- **Section 3 (Foreign counter)** → Tasks 1, 2, 6, 10. Backend aggregates; frontend renders chip.
- **Section 4 (Owner team tag)** → Task 11. Schema adds `team` to issue node, frontend renders outline tag.
- **Section 5 (Plans)** → deferred per spec, no task.
- **Section 6 (KPI tiles)** → Task 13.
- **Section 7 (Bar-in-cell)** → Task 12.

Placeholder scan: no TBDs, no "add appropriate error handling", every code step has full code.

Type consistency: `NodeTotals` fields match between schema (T1), service (T2), tests (T3), frontend types (T6), and renderers (T9-13).

User-named preset save UI is a gap; built-in presets are wired. Acceptable for v1 — saved-presets data structure is reserved in the type, just no UI yet.
