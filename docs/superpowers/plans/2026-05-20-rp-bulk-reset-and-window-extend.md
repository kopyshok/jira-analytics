# RP Bulk Reset + Window Extend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bulk-reset dropdown to `/resource-planning` header (dates / employees / predecessors / full reset) AND make pinned-start phases auto-extend their `end_date` so the planned hours always fit at the role's involvement %.

**Architecture:**
- **Backend:** One new endpoint `POST /resource-plans/{plan_id}/bulk-clear` with `mode` enum. A new helper `_extend_window_for_hours()` is called both from `patch_assignment` (drag = pin start) and from `compute_schedule` (every existing `pinned_start` phase) so window length always matches hours / daily_cap.
- **Frontend:** New `BulkResetDropdown` component placed after «Сделать копию» in the page header. Each item shows a count, fires confirm modal, calls the bulk endpoint, then auto-triggers `compute`.
- **Tests:** pytest for bulk-clear (per mode) + window-extend (3 cases: fits, doesn't fit, hits q_end). Frontend smoke via existing dev-server flow.

**Tech Stack:** FastAPI + SQLAlchemy 2.0, React 19 + AntD 6 (Dropdown + Modal.confirm + Button), TanStack Query, pytest.

---

## File Structure

**Backend:**
- Modify: `app/api/endpoints/resource_planning.py` — add `POST /resource-plans/{plan_id}/bulk-clear`, extend `patch_assignment` to use `_extend_window_for_hours`, add reset counters to `/gantt-projection`.
- Modify: `app/services/resource_planning_service.py` — add `_extend_window_for_hours(employee_id, phase, start_date, hours, item, q_end) -> (end_date, daily_hours_json)` helper; call it inside the pinned-phase branch of `compute_schedule`.
- Test: `tests/api/test_resource_planning_bulk_clear.py` (new)
- Test: `tests/services/test_resource_planning_window_extend.py` (new)

**Frontend:**
- Create: `frontend/src/components/resource-planning/BulkResetDropdown.tsx`
- Modify: `frontend/src/api/resourcePlanning.ts` — add `bulkClearAssignments(planId, mode)` API call + `BulkResetCounts` type in `GanttResponse`.
- Modify: `frontend/src/hooks/useResourcePlanning.ts` — add `useBulkClear(planId)` mutation that invalidates gantt + auto-triggers compute on success.
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx` — insert `<BulkResetDropdown />` between «Сделать копию» and «Сравнить с базовым».

---

## Task 1: Backend — `_extend_window_for_hours` helper

**Files:**
- Modify: `app/services/resource_planning_service.py` (add helper near other private window helpers; suggest right after `_qa_daily_hours` definition)
- Test: `tests/services/test_resource_planning_window_extend.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_resource_planning_window_extend.py
from datetime import date
from app.services.resource_planning_service import ResourcePlanningService


def test_extend_window_fits_in_window(db_session):
    svc = ResourcePlanningService(db_session)
    # 5 working days * (8 * 0.9) = 36h cap, plan 30h -> fits, end = start+4d
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),  # Mon
        hours=30.0,
        daily_cap=7.2,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 24)  # Fri (4 days later)
    import json
    daily = json.loads(daily_json)
    # Sum of allocated hours equals plan
    assert abs(sum(daily.values()) - 30.0) < 0.01


def test_extend_window_grows_when_hours_exceed_cap(db_session):
    svc = ResourcePlanningService(db_session)
    # 5 days * 7.2 = 36h, but plan = 40h => need 6 days, end = Mon 27.04
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=40.0,
        daily_cap=7.2,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 27)  # Mon
    import json
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 40.0) < 0.01


def test_extend_window_clamps_to_quarter_end(db_session):
    svc = ResourcePlanningService(db_session)
    # plan way too big to fit in 2 days; q_end clamps it
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 6, 29),  # Mon
        hours=100.0,
        daily_cap=7.2,
        q_end=date(2026, 6, 30),  # Tue
    )
    assert end == date(2026, 6, 30)
    import json
    daily = json.loads(daily_json)
    # Only 2 days * 7.2 = 14.4h fit; sum capped to that
    assert abs(sum(daily.values()) - 14.4) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/services/test_resource_planning_window_extend.py -v`
Expected: FAIL with `AttributeError: 'ResourcePlanningService' object has no attribute '_extend_window_for_hours'`

- [ ] **Step 3: Implement the helper**

Add inside `class ResourcePlanningService` (place near other private helpers, around line 1500 in the file):

```python
def _extend_window_for_hours(
    self,
    start_date: date,
    hours: float,
    daily_cap: float,
    q_end: date,
) -> tuple[date, str]:
    """Return (end_date, daily_hours_json) such that the segment starting
    at `start_date` fits `hours` at `daily_cap` per working day, capped
    at `q_end`. Weekends/holidays from production calendar are skipped.

    Used when the user pins a start date (drag-in-UI or PATCH): the end
    must auto-extend so the planned hours always fit; we never shrink
    below the requested hours, but we do clamp at q_end (caller may set
    out_of_quarter=True in that case).
    """
    from sqlalchemy import select, and_
    from app.models.production_calendar_day import ProductionCalendarDay
    import json

    cal_rows = self.db.execute(
        select(ProductionCalendarDay).where(
            and_(
                ProductionCalendarDay.date >= start_date,
                ProductionCalendarDay.date <= q_end,
            )
        )
    ).scalars().all()
    cal_anomalies: Dict[date, float] = {r.date: r.hours for r in cal_rows}

    def _day_cap(d: date) -> float:
        anom = cal_anomalies.get(d)
        if anom is not None:
            # production calendar overrides (праздник=0, предпраздничный=7)
            base = anom
        else:
            base = DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0
        # daily_cap уже учитывает involvement; для аномалий шкалируем
        return base * (daily_cap / DEFAULT_HOURS_PER_DAY) if DEFAULT_HOURS_PER_DAY else 0.0

    daily: Dict[date, float] = {}
    remaining = hours
    cursor = start_date
    last_filled = start_date
    while remaining > 0.001 and cursor <= q_end:
        cap = _day_cap(cursor)
        if cap > 0:
            take = min(remaining, cap)
            daily[cursor] = take
            remaining -= take
            last_filled = cursor
        cursor += timedelta(days=1)

    if not daily:
        # No working day available in window — return start_date and empty
        return start_date, json.dumps({})

    daily_json = json.dumps(
        {d.isoformat(): h for d, h in daily.items()}
    )
    return last_filled, daily_json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.10 -m pytest tests/services/test_resource_planning_window_extend.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_resource_planning_window_extend.py
git commit -m "feat(rp/scheduler): add _extend_window_for_hours helper

Returns (end_date, daily_hours_json) that fits the requested hours at
daily_cap per working day, clamped at q_end. Used by drag-in-UI and
compute_schedule to ensure pinned phases always fit their planned hours.
Skips weekends and production-calendar holidays; scales for short days."
```

---

## Task 2: Backend — Call helper from `patch_assignment` on start_date change

**Files:**
- Modify: `app/api/endpoints/resource_planning.py:1340-1370` (the `start_date` branch that currently keeps duration constant)

- [ ] **Step 1: Add an integration test that drags start later and expects auto-extended end**

```python
# tests/api/test_resource_planning_patch_extends_end.py
def test_patch_start_date_extends_end_to_fit_hours(client, seed_plan_with_dev_phase):
    """Plan 40h dev phase at 90% involvement. Drag start to 20.04 (Mon).
    Expected: end auto-extends to 27.04 (Mon) so 6 working days × 7.2 = 43.2h
    accommodates 40h. Old behaviour preserved duration (4 days = 28.8h)."""
    plan_id, assignment_id = seed_plan_with_dev_phase(
        hours=40.0, involvement_pct=90, start=date(2026, 4, 13)
    )
    resp = client.patch(
        f"/api/v1/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"start_date": "2026-04-20"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assignment"]["start_date"] == "2026-04-20"
    assert body["assignment"]["end_date"] == "2026-04-27"
    daily = body["assignment"]["daily_hours"]  # dict day -> hours
    assert abs(sum(daily.values()) - 40.0) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_patch_extends_end.py -v`
Expected: FAIL — `end_date` is `2026-04-22` (preserved 4-day duration) instead of `2026-04-27`.

- [ ] **Step 3: Replace the duration-preserving branch in patch_assignment**

Find this block in `app/api/endpoints/resource_planning.py` (around line 1340):

```python
    if (
        "start_date" in patch
        and a.start_date
        and a.end_date
        and "end_date" not in patch
    ):
        delta_days = (patch["start_date"] - a.start_date).days
        if delta_days != 0:
            from datetime import timedelta as _td

            new_end = a.end_date + _td(days=delta_days)
            patch["end_date"] = new_end
```

Replace with:

```python
    if (
        "start_date" in patch
        and a.hours_allocated
        and "end_date" not in patch
    ):
        # When the user drags the start date, recompute the end to fit
        # hours_allocated at the role's involvement %. Old behaviour
        # preserved duration which silently truncated planned hours.
        plan_obj = db.get(ResourcePlan, plan_id)
        bi = db.get(BacklogItem, a.backlog_item_id)
        if plan_obj and bi:
            svc = ResourcePlanningService(db)
            inv = svc._involvement_for_phase(bi, a.phase) or 1.0
            daily_cap = 8.0 * inv  # DEFAULT_HOURS_PER_DAY × involvement
            q_end = svc._quarter_window(plan_obj.year, plan_obj.quarter)[1]
            new_end, daily_json = svc._extend_window_for_hours(
                start_date=patch["start_date"],
                hours=a.hours_allocated,
                daily_cap=daily_cap,
                q_end=q_end,
            )
            patch["end_date"] = new_end
            a.daily_hours_json = daily_json
            a.out_of_quarter = new_end > q_end
```

(Also remove the no-longer-needed `from datetime import timedelta as _td` line if it was inside the deleted block.)

- [ ] **Step 4: Run all RP api tests to catch regressions**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_patch_extends_end.py tests/api/test_resource_planning*.py -v`
Expected: new test PASS; no regressions in existing patch tests. If any prior tests asserted the old "duration-preserved" behaviour, update them — that behaviour was a bug.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_resource_planning_patch_extends_end.py
git commit -m "fix(rp/patch): drag start_date auto-extends end to fit hours

Old behaviour preserved duration on drag, silently truncating planned
hours (e.g. 40h × 90% inv needs 6 working days, but drag kept only 5).
Now calls _extend_window_for_hours so end + daily_hours_json reflect the
hours actually required; out_of_quarter set if end >= q_end."
```

---

## Task 3: Backend — Re-extend windows in `compute_schedule` for existing pinned_start

**Files:**
- Modify: `app/services/resource_planning_service.py:486-521` (the `for a in pinned_existing` loop that pre-subtracts hours)

- [ ] **Step 1: Add a scheduler test**

```python
# tests/services/test_compute_schedule_extends_pinned.py
def test_compute_schedule_extends_pinned_start_window(db_session, seed_plan_with_pinned_dev):
    """A previously-pinned phase whose end was set when involvement=100%
    must auto-extend when involvement is later lowered to 90%."""
    plan_id, assignment_id = seed_plan_with_pinned_dev(
        hours=40.0, start=date(2026, 4, 20), end=date(2026, 4, 24), involvement=100
    )
    # Lower involvement; recompute
    set_role_involvement(db_session, role="dev", pct=90)
    ResourcePlanningService(db_session).compute_schedule(plan_id)
    a = db_session.get(ResourcePlanAssignment, assignment_id)
    assert a.start_date == date(2026, 4, 20)  # pinned start untouched
    assert a.end_date == date(2026, 4, 27)    # extended +1 working day
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.10 -m pytest tests/services/test_compute_schedule_extends_pinned.py -v`
Expected: FAIL — end_date stays at 2026-04-24.

- [ ] **Step 3: Patch the pinned-pre-subtract block**

Edit `app/services/resource_planning_service.py:493-521`. Replace the `for a in pinned_existing: if not a.pinned_start: continue ...` block with:

```python
        for a in pinned_existing:
            if not a.pinned_start:
                continue
            if not (a.employee_id and a.start_date and a.hours_allocated):
                continue
            # Recompute end + daily_hours_json so the pinned window always
            # holds the planned hours at the current involvement %.
            bi = self.db.get(BacklogItem, a.backlog_item_id)
            inv = self._involvement_for_phase(bi, a.phase) if bi else 1.0
            daily_cap = DEFAULT_HOURS_PER_DAY * (inv or 1.0)
            new_end, daily_json = self._extend_window_for_hours(
                start_date=a.start_date,
                hours=a.hours_allocated,
                daily_cap=daily_cap,
                q_end=q_end,
            )
            a.end_date = new_end
            a.daily_hours_json = daily_json
            a.out_of_quarter = new_end > q_end

            # ... existing remaining-subtraction logic stays below ...
            if a.employee_id in remaining:
                days_in_seg = [
                    d for d in remaining[a.employee_id]
                    if a.start_date <= d <= a.end_date
                    and remaining[a.employee_id][d] > 0
                ]
                if days_in_seg:
                    per_day = a.hours_allocated / len(days_in_seg)
                    for d in days_in_seg:
                        remaining[a.employee_id][d] = max(
                            0.0, remaining[a.employee_id][d] - per_day
                        )
                if a.phase in PREEMPTING_PHASES:
                    locked_set = preempt_locked.setdefault(a.employee_id, set())
                    d_lock = a.start_date
                    while d_lock <= a.end_date:
                        locked_set.add(d_lock)
                        d_lock += timedelta(days=1)
```

- [ ] **Step 4: Run all scheduler tests**

Run: `py -3.10 -m pytest tests/services/test_compute_schedule_extends_pinned.py tests/services/test_resource_planning*.py -v`
Expected: new test PASS; **all existing pinned-phase tests still PASS** — we only extend, never shrink.

- [ ] **Step 5: Commit**

```bash
git add app/services/resource_planning_service.py tests/services/test_compute_schedule_extends_pinned.py
git commit -m "fix(rp/scheduler): compute_schedule re-extends pinned_start windows

When involvement % changes or hours_allocated grows after a phase was
pinned, the stored end_date can no longer hold the hours. Re-run
_extend_window_for_hours for every pinned_start phase so the window
always accommodates planned hours at current involvement."
```

---

## Task 4: Backend — Bulk-clear endpoint

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (add new endpoint after the existing per-assignment `DELETE …/manual-edit` around line 1620)
- Test: `tests/api/test_resource_planning_bulk_clear.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_resource_planning_bulk_clear.py
import pytest

@pytest.mark.parametrize("mode,assertion", [
    (
        "dates",
        lambda assignments: all(not a.pinned_start for a in assignments),
    ),
    (
        "employees",
        lambda assignments: all(not a.pinned_employee for a in assignments),
    ),
    (
        "predecessors",
        lambda assignments: all(not a.predecessors_user_set for a in assignments),
    ),
    (
        "all",
        lambda assignments: all(
            not a.pinned_start and not a.pinned_employee
            and not a.pinned_split and not a.predecessors_user_set
            for a in assignments
        ),
    ),
])
def test_bulk_clear_mode(client, db_session, seed_pinned_plan, mode, assertion):
    plan_id = seed_pinned_plan()  # plan with pinned_start, pinned_employee, edited preds
    resp = client.post(
        f"/api/v1/resource-plans/{plan_id}/bulk-clear",
        json={"mode": mode},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared_count"] > 0
    db_session.expire_all()
    assignments = (
        db_session.query(ResourcePlanAssignment)
        .filter(ResourcePlanAssignment.plan_id == plan_id)
        .all()
    )
    assert assertion(assignments)


def test_bulk_clear_all_also_drops_predecessor_rows(client, db_session, seed_pinned_plan):
    plan_id = seed_pinned_plan()
    pred_rows_before = db_session.query(ResourcePlanPredecessor).filter(
        ResourcePlanPredecessor.successor_id.in_(
            db_session.query(ResourcePlanAssignment.id).filter_by(plan_id=plan_id)
        )
    ).count()
    assert pred_rows_before > 0
    resp = client.post(
        f"/api/v1/resource-plans/{plan_id}/bulk-clear",
        json={"mode": "predecessors"},
    )
    assert resp.status_code == 200
    pred_rows_after = db_session.query(ResourcePlanPredecessor).filter(
        ResourcePlanPredecessor.successor_id.in_(
            db_session.query(ResourcePlanAssignment.id).filter_by(plan_id=plan_id)
        ),
        ResourcePlanPredecessor.is_user_set == True,  # noqa: E712
    ).count()
    assert pred_rows_after == 0


def test_bulk_clear_rejects_unknown_mode(client, seed_pinned_plan):
    plan_id = seed_pinned_plan()
    resp = client.post(
        f"/api/v1/resource-plans/{plan_id}/bulk-clear",
        json={"mode": "frobnicate"},
    )
    assert resp.status_code == 422
```

(If `seed_pinned_plan` / `ResourcePlanPredecessor.is_user_set` aren't yet available, define the fixture in `tests/conftest.py` and replace the predecessor cleanup assertion with whatever signals "user-set predecessor edges were removed" in the current schema. Verify via Grep that `ResourcePlanPredecessor` model exists; if not, drop the second test and rely on `predecessors_user_set` flag check only.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_bulk_clear.py -v`
Expected: 404 / endpoint not found.

- [ ] **Step 3: Implement the endpoint**

Add to `app/api/endpoints/resource_planning.py` (after `clear_manual_edits` around line 1620):

```python
class BulkClearPayload(BaseModel):
    mode: Literal["dates", "employees", "predecessors", "all"]


@router.post("/resource-plans/{plan_id}/bulk-clear")
def bulk_clear(
    plan_id: str,
    payload: BulkClearPayload,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    plan = db.get(ResourcePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    assignments = (
        db.query(ResourcePlanAssignment)
        .filter(ResourcePlanAssignment.plan_id == plan_id)
        .all()
    )

    cleared = 0
    mode = payload.mode
    if mode in ("dates", "all"):
        for a in assignments:
            if a.pinned_start:
                a.pinned_start = False
                cleared += 1
    if mode in ("employees", "all"):
        for a in assignments:
            if a.pinned_employee:
                a.pinned_employee = False
                cleared += 1
    if mode in ("predecessors", "all"):
        for a in assignments:
            if a.predecessors_user_set:
                a.predecessors_user_set = False
                cleared += 1
        # Drop user-set predecessor edges; default cascade will be
        # re-established by compute_schedule on next run.
        ResourcePlanningService(db).clear_user_set_predecessors(plan_id)
    if mode == "all":
        for a in assignments:
            a.pinned_split = False
            a.daily_hours_json = None
            a.manual_edit_at = None

    plan.status = "stale"
    db.commit()

    # Auto-recompute so the UI shows fresh state immediately.
    try:
        ResourcePlanningService(db).compute_schedule(plan_id)
    except ValueError as e:
        raise HTTPException(409, f"recompute_failed: {e}")

    return {"cleared_count": cleared, "mode": mode}
```

Also add `clear_user_set_predecessors` to `ResourcePlanningService` if absent:

```python
def clear_user_set_predecessors(self, plan_id: str) -> int:
    """Delete every predecessor edge whose successor belongs to plan_id
    AND was user-set. Returns number of edges deleted."""
    from app.models.resource_plan_predecessor import ResourcePlanPredecessor
    successor_ids = [
        a.id for a in self.db.query(ResourcePlanAssignment)
        .filter(ResourcePlanAssignment.plan_id == plan_id).all()
    ]
    if not successor_ids:
        return 0
    rows = (
        self.db.query(ResourcePlanPredecessor)
        .filter(
            ResourcePlanPredecessor.successor_id.in_(successor_ids),
            ResourcePlanPredecessor.is_user_set == True,  # noqa: E712
        )
        .all()
    )
    for r in rows:
        self.db.delete(r)
    self.db.flush()
    return len(rows)
```

(If `ResourcePlanPredecessor` lacks `is_user_set`, replace the `.filter()` clause with a join on `ResourcePlanAssignment.predecessors_user_set == True` and delete edges belonging to those successors only. Verify the actual schema first with Grep before writing.)

- [ ] **Step 4: Run tests**

Run: `py -3.10 -m pytest tests/api/test_resource_planning_bulk_clear.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py app/services/resource_planning_service.py tests/api/test_resource_planning_bulk_clear.py
git commit -m "feat(rp/api): POST /resource-plans/{id}/bulk-clear endpoint

Single endpoint with mode = dates|employees|predecessors|all clears
pinned flags across every assignment of the plan, drops user-set
predecessor edges, and auto-triggers compute_schedule so the UI gets
fresh state. cleared_count returned for confirmation message."
```

---

## Task 5: Backend — Reset counts in `/gantt-projection`

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (the `/gantt-projection` response builder, around line 946)

- [ ] **Step 1: Write a small test**

```python
# tests/api/test_resource_planning_gantt_counts.py
def test_gantt_projection_returns_reset_counts(client, seed_pinned_plan):
    plan_id = seed_pinned_plan()
    resp = client.get(f"/api/v1/resource-plans/{plan_id}/gantt-projection")
    assert resp.status_code == 200
    body = resp.json()
    counts = body["reset_counts"]
    assert counts["pinned_dates"] >= 1
    assert counts["pinned_employees"] >= 1
    assert counts["edited_predecessors"] >= 0
```

- [ ] **Step 2: Run test**

Expected: FAIL — `reset_counts` key absent.

- [ ] **Step 3: Add counts to projection response**

In the `/gantt-projection` builder, before the final `return` add:

```python
    reset_counts = {
        "pinned_dates": sum(1 for a in assignments_raw if a.pinned_start),
        "pinned_employees": sum(1 for a in assignments_raw if a.pinned_employee),
        "edited_predecessors": sum(
            1 for a in assignments_raw if a.predecessors_user_set
        ),
    }
```

Add `reset_counts=reset_counts` to the `GanttResponse(...)` constructor and add the field to the Pydantic model (near `assignments: List[AssignmentOut]`):

```python
class GanttResponse(BaseModel):
    # ... existing fields ...
    reset_counts: dict = {}
```

- [ ] **Step 4: Run test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/resource_planning.py tests/api/test_resource_planning_gantt_counts.py
git commit -m "feat(rp/gantt): include reset_counts in /gantt-projection

Frontend dropdown shows how many phases each bulk-clear mode will touch."
```

---

## Task 6: Frontend — API client + hook

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts`
- Modify: `frontend/src/hooks/useResourcePlanning.ts`

- [ ] **Step 1: Add API function and types**

Append to `frontend/src/api/resourcePlanning.ts`:

```ts
export type BulkClearMode = 'dates' | 'employees' | 'predecessors' | 'all';

export interface BulkClearResponse {
  cleared_count: number;
  mode: BulkClearMode;
}

export interface ResetCounts {
  pinned_dates: number;
  pinned_employees: number;
  edited_predecessors: number;
}

export async function bulkClearAssignments(
  planId: string,
  mode: BulkClearMode,
): Promise<BulkClearResponse> {
  return api.post(`/resource-plans/${planId}/bulk-clear`, { mode });
}
```

Then extend the `GanttResponse` interface (same file) with `reset_counts: ResetCounts;`.

- [ ] **Step 2: Add hook**

In `frontend/src/hooks/useResourcePlanning.ts`:

```ts
export function useBulkClear(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: BulkClearMode) => {
      if (!planId) throw new Error('No plan selected');
      return bulkClearAssignments(planId, mode);
    },
    onSuccess: () => {
      if (!planId) return;
      // gantt-projection includes fresh data and triggers downstream invalidations
      qc.invalidateQueries({ queryKey: ['rp-gantt', planId] });
      qc.invalidateQueries({ queryKey: ['rp-conflicts', planId] });
    },
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/resourcePlanning.ts frontend/src/hooks/useResourcePlanning.ts
git commit -m "feat(rp/api): bulkClearAssignments + useBulkClear hook"
```

---

## Task 7: Frontend — `BulkResetDropdown` component

**Files:**
- Create: `frontend/src/components/resource-planning/BulkResetDropdown.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { App, Button, Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { ReloadOutlined, DownOutlined } from '@ant-design/icons';
import type { BulkClearMode, ResetCounts } from '../../api/resourcePlanning';
import { useBulkClear } from '../../hooks/useResourcePlanning';

interface Props {
  planId: string | null;
  counts: ResetCounts;
}

const MODE_LABELS: Record<BulkClearMode, string> = {
  dates: 'Сбросить закреплённые даты',
  employees: 'Сбросить закреплённых исполнителей',
  predecessors: 'Сбросить связи предшественников',
  all: 'Сбросить всё к первоначальному виду',
};

const MODE_DESCRIPTIONS: Record<BulkClearMode, string> = {
  dates: 'Снять ручную фиксацию даты у {n} фаз. Планировщик пересчитает окна.',
  employees: 'Снять закрепление исполнителя у {n} фаз. Планировщик подберёт заново.',
  predecessors: 'Удалить ручные связи у {n} фаз. Восстановится стандартная цепочка.',
  all: 'Снять все ручные правки: даты, исполнителей, связи. План пересчитается полностью.',
};

export default function BulkResetDropdown({ planId, counts }: Props) {
  const { message } = App.useApp();
  const bulkClear = useBulkClear(planId);

  const countFor = (mode: BulkClearMode): number => {
    if (mode === 'dates') return counts.pinned_dates;
    if (mode === 'employees') return counts.pinned_employees;
    if (mode === 'predecessors') return counts.edited_predecessors;
    return counts.pinned_dates + counts.pinned_employees + counts.edited_predecessors;
  };

  const handleClick = (mode: BulkClearMode) => {
    const n = countFor(mode);
    Modal.confirm({
      title: MODE_LABELS[mode],
      content: MODE_DESCRIPTIONS[mode].replace('{n}', String(n)),
      okText: 'Сбросить',
      cancelText: 'Отмена',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const res = await bulkClear.mutateAsync(mode);
          message.success(`Снято правок: ${res.cleared_count}`);
        } catch (e) {
          message.error('Ошибка сброса');
        }
      },
    });
  };

  const items: MenuProps['items'] = [
    {
      key: 'dates',
      label: `${MODE_LABELS.dates} (${counts.pinned_dates})`,
      disabled: counts.pinned_dates === 0,
      onClick: () => handleClick('dates'),
    },
    {
      key: 'employees',
      label: `${MODE_LABELS.employees} (${counts.pinned_employees})`,
      disabled: counts.pinned_employees === 0,
      onClick: () => handleClick('employees'),
    },
    {
      key: 'predecessors',
      label: `${MODE_LABELS.predecessors} (${counts.edited_predecessors})`,
      disabled: counts.edited_predecessors === 0,
      onClick: () => handleClick('predecessors'),
    },
    { type: 'divider' },
    {
      key: 'all',
      label: MODE_LABELS.all,
      danger: true,
      onClick: () => handleClick('all'),
    },
  ];

  return (
    <Dropdown menu={{ items }} trigger={['click']} disabled={!planId}>
      <Button size="small" icon={<ReloadOutlined />}>
        Сбросить <DownOutlined />
      </Button>
    </Dropdown>
  );
}
```

- [ ] **Step 2: Wire it into the page header**

In `frontend/src/pages/ResourcePlanningPage.tsx`, after the «Сделать копию» button (around line 194) add:

```tsx
{planId && gantt && (
  <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />
)}
```

Don't forget the import at top:

```tsx
import BulkResetDropdown from '../components/resource-planning/BulkResetDropdown';
```

- [ ] **Step 3: Lint + typecheck**

Run: `cd D:/ClaudeDev/JiraAnalysis/frontend && npx eslint src/components/resource-planning/BulkResetDropdown.tsx src/pages/ResourcePlanningPage.tsx && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/resource-planning/BulkResetDropdown.tsx frontend/src/pages/ResourcePlanningPage.tsx
git commit -m "feat(rp/ui): BulkResetDropdown in /resource-planning header

Dropdown after «Сделать копию» with 4 items: reset dates / employees /
predecessors / full. Each shows phase count, confirm modal, danger style
on 'all'. Disabled items when count = 0."
```

---

## Task 8: Manual smoke + push

- [ ] **Step 1: Restart backend + frontend per project convention (Windows uvicorn --reload hangs)**

```pwsh
# Kill any backend on :8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
  Stop-Process -Id $_.OwningProcess -Force
}
# Start fresh
py -3.10 -m uvicorn app.main:app --port 8000
```

In another shell:

```pwsh
cd frontend
npm run dev
```

- [ ] **Step 2: Browser smoke — golden path**

1. Open `/resource-planning`, select a plan that has at least 1 pinned phase.
2. Click «Сбросить ▾» → menu opens, counts match badge in header.
3. Click «Сбросить закреплённые даты (N)» → confirm modal → ОК.
4. Toast «Снято правок: N» appears.
5. Plan recomputes; previously-pinned bars now have no border / pin icon.
6. Drag a phase start later — bar end auto-extends so the bar width covers full hours.
7. Sidebar «Дни × часы» now shows non-zero `Потрачено` matching the day cap.

- [ ] **Step 3: Push the branch**

```bash
git push origin main
```

(Per repo norm: main, no PR; subagent flow already produced reviewed commits.)

---

## Self-Review Notes (filled before handoff)

- **Spec coverage:** ✅ Tasks 1-3 cover the window-extend behaviour for both drag-in-UI and recompute. Tasks 4-7 cover the bulk-reset dropdown end-to-end (backend endpoint, counts, hook, UI, confirmation).
- **Placeholder scan:** No `TODO` / `TBD` in plan. Two notes flag "verify with Grep before writing" — those are real conditional fallbacks for unknown model fields, not placeholders.
- **Type consistency:** `BulkClearMode`, `ResetCounts`, `_extend_window_for_hours` signature reused identically across Tasks 1, 6, 7. Endpoint path `/resource-plans/{plan_id}/bulk-clear` used in Task 4 (backend) and Task 6 (API client). Hook key `useBulkClear` used in 6 and 7.
