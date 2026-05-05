# Planning Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calendar planner produces realistic schedules: editable priorities, parallel ОПЭ, Jira-sourced involvement/duration, parallel staffing per role, auto-split for long phases.

**Architecture:**
- Backend: SQLAlchemy 2.0 models + Alembic migrations + FastAPI endpoints
- Solver: PyJobShop CP-SAT, model-rebuild only (no F5/F6/F7 — disabled due to SIGSEGV)
- Frontend: React 19 + AntD 6, inline editing, no new pages

**Tech Stack:** Python 3.10, SQLAlchemy, Alembic, FastAPI, React 19, AntD 6, TanStack Query, PyJobShop.

**Spec:** `docs/superpowers/specs/2026-05-05-planning-improvements-design.md`

**Run all phases sequentially.** Each phase ends with: tests green, build green, commit, push.

---

## Phase 1: Editable Priority

### Task 1.1: Verify backend supports priority patch

**Files:**
- Modify: `app/api/endpoints/backlog.py:600-627`
- Modify: `app/schemas/backlog_schemas.py` (find `BacklogItemUpdate`)
- Test: `tests/test_backlog_endpoints.py`

- [ ] **Step 1.1.1:** Confirm `BacklogItemUpdate` schema has `priority: Optional[int]` field. If missing, add it. Validation: `ge=1, le=10`.

- [ ] **Step 1.1.2:** Add test `test_patch_backlog_priority` — POST `/backlog`, PATCH `priority=3`, GET — assert returned `priority == 3`.

- [ ] **Step 1.1.3:** Add test `test_patch_backlog_priority_clear` — PATCH `priority=null`, assert `priority is None`.

- [ ] **Step 1.1.4:** Add test `test_patch_backlog_priority_validation` — PATCH `priority=15`, assert 422.

- [ ] **Step 1.1.5:** Run `py -3.10 -m pytest tests/test_backlog_endpoints.py::test_patch_backlog_priority tests/test_backlog_endpoints.py::test_patch_backlog_priority_clear tests/test_backlog_endpoints.py::test_patch_backlog_priority_validation -v` — must pass.

### Task 1.2: Inline number editor in /planning row

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx:794-810` (priority badge cell)
- Modify: `frontend/src/hooks/usePlanning.ts` — find or add `usePatchBacklogItem` mutation
- Modify: `frontend/src/api/backlog.ts` (or equivalent)

- [ ] **Step 1.2.1:** In API client add (if missing): `patchBacklogItem(id: string, data: { priority?: number | null }): Promise<BacklogItemResponse>` calling `PATCH /backlog/{id}`.

- [ ] **Step 1.2.2:** Add hook `usePatchBacklogPriority` (TanStack Query mutation). On success — `queryClient.invalidateQueries(['backlog'])` AND `['scenarios']` AND `['scenario-allocations']` (so /planning row re-renders with new priority).

- [ ] **Step 1.2.3:** Replace static priority badge with editable component. Use AntD `<InputNumber min={1} max={10} bordered={false} />` styled to match badge. Width 32px.
   - On blur or Enter — call mutation
   - On Escape — revert
   - Disabled if scenario is approved (`!isDraft`)

- [ ] **Step 1.2.4:** Manually verify — start dev server, open /planning, click priority cell, type 5, blur, observe save + cyan badge if ≤3.

- [ ] **Step 1.2.5:** Run `npm --prefix frontend run lint` and `npm --prefix frontend run build` — must succeed.

- [ ] **Step 1.2.6:** Commit:
```bash
git add app/ tests/ frontend/
git commit -m "feat(planning): editable priority badge in backlog row"
git push origin main
```

---

## Phase 2: ОПЭ Parallel

### Task 2.1: Refactor ОПЭ split — both rows after QA, in parallel

**Files:**
- Modify: `app/services/resource_planning_service.py` near `compute_schedule` (line 168) and `_opo_split` (line 569)
- Test: `tests/test_resource_planning_service.py`

**Current behavior (read first):**
- `compute_schedule` schedules phases in order analyst → dev → qa → opo
- ОПЭ creates 2 rows sequentially: opo_analyst then opo_dev
- Both have `phase="opo"`

**Target behavior:**
- 2 rows of `phase="opo"` start simultaneously after QA ends
- Row 1 belongs to analyst-role employee, hours = total × `opo_analyst_ratio`
- Row 2 belongs to dev-role employee, hours = total × (1 − ratio)

- [ ] **Step 2.1.1:** Write failing test: create plan with 1 backlog item with `estimate_qa_hours=8`, `estimate_opo_hours=16`, `opo_analyst_ratio=0.5`. After `compute_schedule`, assert:
   - 2 rows with `phase="opo"`
   - Both have `start_date` equal to QA's `end_date + 1` (or the same start day)
   - Hours: 8.0 each
   - Different `employee_id` (one analyst-role, one dev-role)

- [ ] **Step 2.1.2:** Refactor `compute_schedule` so when phase="opo" — both `_opo_split` rows are created in parallel using the **same** start cursor (don't advance cursor between them). Set both `start_date = max(qa_end_dates)+1` (skipping weekends as the existing helpers already do).

- [ ] **Step 2.1.3:** Run new test — must pass.

- [ ] **Step 2.1.4:** Verify other ОПЭ tests still pass: `py -3.10 -m pytest tests/test_resource_planning_service.py -v -k opo`.

### Task 2.2: Solver respects parallel ОПЭ

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py:37-42` (PHASE_ROLE_MATCH)
- Test: `tests/test_pyjobshop_solver_service.py`

**Decision:** keep `phase="opo"` for both rows but distinguish by row's existing `employee_id` (set when plan was built from scenario). If `is_pinned=False` and `employee_id` is null — solver picks any `analyst+dev+ba` role (current `PHASE_ROLE_MATCH["opo"]`).

If row has `employee_id` set, solver already picks only that resource via existing pin logic. So no solver change needed if rows are pre-assigned. **Validate this assumption with a test.**

- [ ] **Step 2.2.1:** Write test `test_solver_keeps_opo_parallel`: 2 rows phase="opo" (one analyst-role employee, one dev-role employee), both pre-assigned, both in same plan after QA. Expected: solver schedules both, neither moves the other, dates overlap (start within 1 day of each other).

- [ ] **Step 2.2.2:** Run test. If fails — investigate solver constraint preventing parallel execution. Likely no fix needed.

- [ ] **Step 2.2.3:** Commit:
```bash
git add app/services/resource_planning_service.py tests/
git commit -m "feat(planning): ОПЭ phase splits into parallel analyst+dev rows"
git push origin main
```

---

## Phase 3: Jira Involvement + Duration in Solver

### Task 3.1: Add involvement + duration fields to BacklogItem

**Files:**
- Create migration: `alembic/versions/XXX_add_involvement_duration_to_backlog_items.py`
- Modify: `app/models/backlog_item.py`
- Modify: `app/schemas/backlog_schemas.py` — `BacklogItemResponse`, `BacklogItemUpdate`

- [ ] **Step 3.1.1:** Generate migration:
```powershell
py -3.10 -m alembic revision -m "add involvement+duration to backlog_items"
```

- [ ] **Step 3.1.2:** In migration, batch_alter_table('backlog_items'): add columns
```python
op.add_column('backlog_items', sa.Column('involvement_analyst', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('involvement_dev', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('involvement_qa', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('involvement_launch', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('duration_analyst_days', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('duration_dev_days', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('duration_qa_days', sa.Float(), nullable=True))
op.add_column('backlog_items', sa.Column('duration_launch_days', sa.Float(), nullable=True))
```

- [ ] **Step 3.1.3:** Add same fields to `BacklogItem` model with `Mapped[Optional[float]] = mapped_column(Float, nullable=True)`.

- [ ] **Step 3.1.4:** Run migration: `py -3.10 -m alembic upgrade head`. Verify tables changed via `sqlite3` quick check.

- [ ] **Step 3.1.5:** Commit migration alone:
```bash
git add alembic/ app/models/backlog_item.py
git commit -m "chore(db): add involvement+duration columns to backlog_items"
```

### Task 3.2: Propagate from Issue to BacklogItem on refresh

**Files:**
- Modify: `app/services/backlog_service.py` — find `refresh_from_jira` or upsert path
- Test: `tests/test_backlog_service.py`

- [ ] **Step 3.2.1:** Find the function in backlog_service.py that copies fields from `Issue` to `BacklogItem`. Add 8 field copies (involvement_analyst/dev/qa/launch + duration_*_days).

- [ ] **Step 3.2.2:** Test: create Issue with involvement_analyst=0.6 + duration_analyst_days=5, link to BacklogItem, call refresh, assert BacklogItem has same values.

- [ ] **Step 3.2.3:** Run pytest. Commit:
```bash
git add app/services/backlog_service.py tests/test_backlog_service.py
git commit -m "feat(backlog): propagate involvement+duration from Issue on refresh"
```

### Task 3.3: Update solver model — duration in days, demand by involvement

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py:200-235` (task building loop)
- Test: `tests/test_pyjobshop_solver_service.py`

**Model change:**
- For each ResourcePlanAssignment with phase=P:
  - involvement = `backlog_item.involvement_<P>` (default 1.0)
  - duration_days = `backlog_item.duration_<P>_days` (default `hours_allocated / 8`)
  - duration_slots = `int(duration_days * HOURS_PER_DAY)` (calendar slots)
  - demand_per_slot = `int(round(involvement * HOURS_PER_DAY))` (capacity units consumed)
- Resource capacity stays 8.

**Phase mapping:**
```python
PHASE_TO_FIELD = {
  "analyst": ("involvement_analyst", "duration_analyst_days"),
  "dev":     ("involvement_dev",     "duration_dev_days"),
  "qa":      ("involvement_qa",      "duration_qa_days"),
  "opo":     ("involvement_launch",  "duration_launch_days"),
}
```

- [ ] **Step 3.3.1:** Write test: 1 backlog item, phase=analyst, involvement=0.5, duration=4 days, hours_allocated=16. After solve, assignment's `end_date - start_date` should span ~4 working days, not 2 (which would be 16h/8=2).

- [ ] **Step 3.3.2:** In solver, replace `duration_slots = max(1, int(a.hours_allocated or 1))` with new formula. Replace `demands=[HOURS_PER_DAY]` with `demands=[max(1, int(round(involvement * HOURS_PER_DAY)))]`.

- [ ] **Step 3.3.3:** Run new test + all existing solver tests: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py -v`. Existing tests should still pass because default involvement=1.0 → behavior unchanged for items without involvement set.

- [ ] **Step 3.3.4:** Test parallel execution: 2 backlog items, same employee, both involvement=0.4 + duration=5 days. Expected: solver schedules them **overlapping** (since 0.4 + 0.4 = 0.8 ≤ 1.0).

- [ ] **Step 3.3.5:** Commit:
```bash
git add app/services/pyjobshop_solver_service.py tests/
git commit -m "feat(solver): duration in days + demand by involvement (parallel tasks per employee)"
git push origin main
```

### Task 3.4: UI — show involvement+duration in backlog row

**Files:**
- Modify: `frontend/src/types/api.ts` — `BacklogItemResponse`
- Modify: `frontend/src/pages/BacklogPage.tsx` (find row layout)
- Modify: `frontend/src/components/planning/BacklogRoleCell.tsx` (if hours displayed there)

- [ ] **Step 3.4.1:** Extend type: add 8 optional fields `involvement_*`, `duration_*_days`.

- [ ] **Step 3.4.2:** In backlog row's hours-by-role tooltip — append "(N days, X% занятость)" if duration/involvement set. Read-only — данные из Jira.

- [ ] **Step 3.4.3:** Build, verify visually. Commit:
```bash
git add frontend/
git commit -m "feat(backlog): show involvement+duration from Jira in tooltips"
git push origin main
```

---

## Phase 4: Parallel Staffing per Role

### Task 4.1: Add parallel_count fields

**Files:**
- Migration: `alembic/versions/XXX_add_parallel_count.py`
- Modify: `app/models/project.py` — add 3 fields
- Modify: `app/models/backlog_item.py` — add 3 override fields (nullable)

- [ ] **Step 4.1.1:** Generate migration. Add to projects: `parallel_count_analyst`, `parallel_count_dev`, `parallel_count_qa` (Integer, nullable, default 1). Same to backlog_items as nullable overrides (NULL = inherit project).

- [ ] **Step 4.1.2:** Add Mapped fields to models.

- [ ] **Step 4.1.3:** Migration run + commit:
```bash
git add alembic/ app/models/
git commit -m "chore(db): add parallel_count_* to projects and backlog_items"
```

### Task 4.2: Solver halves duration when N>1

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py` — task building loop
- Test: `tests/test_pyjobshop_solver_service.py`

**Logic:**
- Resolve N for each phase: `backlog_item.parallel_count_X ?? project.parallel_count_X ?? 1`
- New `duration_slots = max(1, int(duration_days * HOURS_PER_DAY / N))`
- Eligibility: still 1 employee (CP-SAT picks one mode); we model the speed-up via shorter duration. Future: model N actual people occupying simultaneously.

- [ ] **Step 4.2.1:** Test: 1 backlog with phase=qa, duration=10 days, parallel_count_qa=2. Expected: assignment span ≈ 5 working days.

- [ ] **Step 4.2.2:** Implement helper `_resolve_parallel_count(item, project, phase)`. Apply in duration calc.

- [ ] **Step 4.2.3:** Run tests. Commit:
```bash
git add app/services/pyjobshop_solver_service.py tests/
git commit -m "feat(solver): parallel_count_* shortens phase duration by N"
```

### Task 4.3: UI inputs

**Files:**
- Modify: backlog row card / project detail card

- [ ] **Step 4.3.1:** In project edit form — 3 number inputs (analyst/dev/qa parallel count).

- [ ] **Step 4.3.2:** In backlog item edit — 3 number inputs as nullable overrides ("по умолчанию из проекта").

- [ ] **Step 4.3.3:** Build, lint, commit + push:
```bash
git add frontend/
git commit -m "feat(planning): UI for parallel_count_* on project and backlog item"
git push origin main
```

---

## Phase 5: Auto-Split Long Phases

### Task 5.1: Capacity heuristic + split decision

**Files:**
- Modify: `app/services/pyjobshop_solver_service.py` — new helper `_auto_split_phases(plan, assignments)`
- Test: `tests/test_pyjobshop_solver_service.py`

**Algorithm:**
```
total_demand = sum over assignments: duration_days * involvement * 8
total_capacity = sum over employees: working_days_in_quarter * 8
if total_demand <= total_capacity:
    return assignments  # no split
sort assignments by duration_days desc
for a in assignments:
    if a.phase != "analyst": continue  # only split analyst (it gates dev)
    while a.duration_days > MIN_CHUNK_DAYS:
        a.duration_days /= 2
        if total_demand fits: break
    if fits: break
```

Where `MIN_CHUNK_DAYS = 1` (8h chunk).

**Modeling split in solver:**
- Each split chunk = separate task in CP-SAT, FS-chain among them (1→2→3)
- Dev FS-zависимость → first chunk (not whole phase)

- [ ] **Step 5.1.1:** Write `_auto_split_phases`. Returns list of "virtual assignments" with `parent_assignment_id`, `chunk_index`, `chunks_total`, modified `duration_days`.

- [ ] **Step 5.1.2:** Modify model-build loop: for each split assignment create N tasks, add FS between chunks, redirect outgoing dependencies to first chunk.

- [ ] **Step 5.1.3:** Test: 1 backlog with analyst=80h, dev=40h, only 1 analyst employee with 80h capacity, 1 dev with 40h, quarter = 10 working days. Without split: dev waits 10 days for analyst. With split into 4×20h: dev can start after first 20h (~2.5 days). Assert dev start_date ≤ day 5.

- [ ] **Step 5.1.4:** Test: small plan that fits without split — no split applied (verify by counting solver tasks).

- [ ] **Step 5.1.5:** Run tests. Commit:
```bash
git add app/services/pyjobshop_solver_service.py tests/
git commit -m "feat(solver): auto-split long analyst phases when quarter overflows"
```

### Task 5.2: Frontend — split visualization

**Files:**
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx`

- [ ] **Step 5.2.1:** Backend Gantt response — extend AssignmentOut with `chunk_index?`, `chunks_total?`. Populate when assignment is a split chunk.

- [ ] **Step 5.2.2:** GanttRows: if `chunks_total > 1`, render badge "1/3" on the bar.

- [ ] **Step 5.2.3:** Build, commit + push:
```bash
git add app/ frontend/
git commit -m "feat(planning): visualize split chunks on Gantt"
git push origin main
```

---

## Final verification

- [ ] Run full pytest: `py -3.10 -m pytest tests/test_pyjobshop_solver_service.py tests/test_resource_planning_service.py tests/test_resource_planning_endpoints.py tests/test_resource_planning_v2_endpoints.py tests/test_backlog_endpoints.py tests/test_backlog_service.py -v` — all pass.
- [ ] Frontend build green: `npm --prefix frontend run build`.
- [ ] Lint: `npm --prefix frontend run lint` (only pre-existing errors allowed).
- [ ] Restart uvicorn, manual smoke: edit priority, run optimize, observe Gantt with grouping by assignee + parallel ОПЭ + split badges.
- [ ] Update memory: add fact "Planning improvements shipped 2026-05-05 (5 phases)".
