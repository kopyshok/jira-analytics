# Resource Planning audit — fix plan

Date: 2026-05-19
Trigger: PM-driven audit after fixing 8 user-visible bugs on PRJ-10623 (commits 2e7b9b1 → b9c04e9 on main).

User chose option **A**: ship all 21 findings in batches (P0 → P1 → P2). Resume in next session.

---

## Recent fixes already landed (do NOT re-flag)

| Commit | Fix |
|---|---|
| 2e7b9b1 | Data-driven phase arrows; `pinned_employee` no longer freezes dates |
| 58836b4 | PATCH re-finds assignment by (item, phase, part_number) after compute |
| 6d8b5d8 | `predecessors_user_set=True` with empty inbound preds → earliest_start=q_start |
| ea865c0 | `/compute` resets plan status to `stale` on exception |
| 823a393 | `_restore_predecessors` / `_ensure_default_predecessors` seed seen-set from DB |
| 5578e69 | `pinned_split` no longer freezes dates in shift; daily_hours_json shifts with delta |
| 0d9e052 | Granular `?flags=start,employee,split` on DELETE /manual-edit |
| fd877c5 | pinned_split rows redistributed via allocator after shift; pre-deduct skips pinned_split |
| b9c04e9 | split_assignment preserves external predecessor edges; redistribute respects user_touched + topo order |

---

## Working state at handoff

- Branch: `main`
- HEAD: `b9c04e9`
- Working tree: clean of audit-related changes; unrelated WIP exists in `backlog.py`, `mapping_service.py`, frontend backlog/analytics files (NOT my work, leave alone).
- Live plan `348da59b-ad54-4206-a09f-74b5b92f990d` (PRJ-10623, Q2 2026, Команда 1С ERP) computes in 0.2s end-to-end.
- 553 pytest pass; 1 pre-existing fail (`test_pinned_start_preserved_on_recompute` — unrelated, clamp pass regression from 2145b05).

---

## Files touched in fixes so far

- `app/services/resource_planning_service.py`
- `app/api/endpoints/resource_planning.py`
- `frontend/src/components/resource-planning/DependencyArrows.tsx`
- `frontend/src/components/resource-planning/AssignmentSidebar.tsx`
- `frontend/src/api/resourcePlanning.ts`

---

## Audit findings — full list

### P0 (critical, breaks scheduling)

**1. Allocator zero-outs partial day capacity.**
- Location: `app/services/resource_planning_service.py:~1071` (`_allocate_hours_with_breakdown`)
- Symptom: When `daily_capacity` caps take below `avail` (e.g. 4h taken from 8h day due to involvement<100%), code sets `emp_days[d]=0.0` instead of subtracting `used`. Remaining 4h vanish → later phases see phantom-full day → false overloads + cascading shifts.
- Fix: `emp_days[d] -= used` (with `max(0.0, ...)`).
- Acceptance: phases with involvement=0.5 leave half-day capacity for subsequent phases of same employee.

**2. `add_predecessor` commits per call; mid-list cycle leaves DB inconsistent.**
- Location: `app/services/resource_planning_service.py:~1929` + `app/api/endpoints/resource_planning.py:~1349`
- Symptom: PATCH `predecessor_ids: [a, b, c]` calls `add_predecessor` 3 times. If `c` introduces cycle, exception fires after `a` and `b` committed. `db.rollback()` at endpoint level is no-op vs. already-committed rows.
- Fix: do cycle check against the FULL prospective edge set before any insert; insert all in one transaction (no per-call commit inside `add_predecessor`).
- Acceptance: PATCH with cyclic edges leaves DB exactly as before PATCH.

**3. `merge_assignment` drops external successor edges.**
- Location: `app/services/resource_planning_service.py:~1892`
- Symptom: Merge deletes siblings 1..N; their CASCADE drops outbound `PhasePredecessor` rows. If `dev-part-3 → qa-part-3` existed (from cascade-split), it's lost. Only `first.id` outbound edges survive.
- Fix: before deleting siblings, snapshot their outbound edges, re-point successor → `first.id`.
- Acceptance: merge of cascade-split dev preserves dev→qa edges (now from merged-dev to all qa parts, deduped).

**4. RCPSP leveler doesn't update `daily_hours_json` on shift/reassign.**
- Location: `app/services/rcpsp_leveler.py:244-318` (`_try_delay`, `_try_reassign`)
- Symptom: leveler shifts start/end (or changes employee) but daily JSON keys stay on old days. Defensive clamp at `service.py:~972` then snaps start/end back to old JSON keys → leveler shift undone. Overload detection counts both old AND new ranges.
- Fix: in both helpers, shift JSON keys by delta (like 5578e69 does in `_shift_to_obey_predecessors`); on employee change, clear or regenerate JSON.
- Acceptance: leveler-shifted phase shows new dates after compute; clamp doesn't revert.

### P1 (correctness / edge case)

**5. Default chain seeds only one OPO row.**
- Location: `app/services/resource_planning_service.py:~1489` (`_ensure_default_predecessors`)
- Symptom: `by_item[item_id][phase] = a` overwrites for OPO (analyst-opo + dev-opo share `phase='opo'`). Only the last-iterated OPO row gets the default `qa→opo` edge.
- Fix: special-case OPO — seed edges to BOTH OPO rows (use `employee_role` to distinguish).
- Acceptance: both OPO rows have inbound qa→opo edge by default.

**6. Shift past q_end doesn't trim daily_hours_json.**
- Location: `app/services/resource_planning_service.py:~1605-1634` (`_shift_to_obey_predecessors`)
- Symptom: `new_start = q_end` clamp + `new_end = new_start + duration` re-clamp don't drop JSON keys outside `[new_start, new_end]`. Bar visually overflows.
- Fix: after shift, filter daily_hours_json to keys within `[new_start, new_end]`.
- Acceptance: bar boundaries match JSON key range.

**7. `_cascade_split` silently skips already-split downstream phases.**
- Location: `app/services/resource_planning_service.py:~1787`
- Symptom: `if len(existing) != 1: continue`. User splits dev first, then cascade-splits analyst — dev ratios out of sync, no warning.
- Fix: surface via PlanConflict or 422 with explanatory message; OR force re-cascade (split each existing downstream into proportional parts).
- Acceptance: cascade with already-split downstream either errors with clear message or correctly re-proportions.

**8. Quarter spillover always marked critical path.**
- Location: `app/services/resource_planning_service.py:~1310` (`_compute_cpm`) + `~2089` (LATE_START detection)
- Symptom: CPM deadline = q_end_extended (+1 month). Spillover phases get negative slack vs q_end → `is_on_critical_path=True` + LATE_START conflict. Spillover is BY DESIGN (`q_end_extended = q_end + relativedelta(months=1)`).
- Fix: CPM deadline = q_end_extended for slack; LATE_START fires only if end > q_end_extended; `is_on_critical_path` decoupled from spillover (use proper path analysis, not slack<0).
- Acceptance: phases ending between q_end and q_end_extended don't get red critical-path tag.

**9. Pinned_split redistribute ignores phases_with_inbound_pred.**
- Location: `app/services/resource_planning_service.py:~903-949` (pinned_split redistribute pass)
- Symptom: redistribute uses `a.start_date` if no preds and not in user_touched. Should mirror main-loop logic at lines 575-578 (user_touched + no inbound = q_start).
- Fix: check `phases_with_inbound_pred` set; if user_touched and phase not in that set → earliest = q_start.
- Acceptance: pinned_split phase in user_touched item with no inbound preds starts at q_start (or earliest workday).

**10. pinned_employee lost when pinned_start cleared via flags=start.**
- Location: `app/services/resource_planning_service.py:~384-399` (pinned_employee_phase_snapshot filter)
- Symptom: snapshot filters `pinned_start == False AND pinned_split == False`. Rows with both pinned_employee + pinned_start aren't captured. If user later clears pinned_start via `/manual-edit?flags=start`, pinned_employee is on the row but next compute doesn't snapshot it → allocator reassigns.
- Fix: snapshot pinned_employee=True regardless of other flags; only skip restoration if the row was preserved as date-pinned (already has the flag).
- Acceptance: chain «change employee → manual date pin → clear date → recompute» keeps the manual employee.

**11. `_restore_predecessors` drops edges when employee changes.**
- Location: `app/services/resource_planning_service.py:~1414` (`_restore_predecessors`)
- Symptom: snapshot key = `(item, phase, part_number, employee_id)`. If non-pinned phase moves to different employee on recompute (avail changed → auto-pick different person), `by_key` lookup misses → edge silently dropped.
- Fix: drop `employee_id` from snapshot key when row isn't pinned; keep `employee_id` only as tie-breaker for OPO duplicates.
- Acceptance: edges survive auto-reassignment of non-pinned phases.

**12. PATCH sets `pinned_start=True` even when value unchanged.**
- Location: `app/api/endpoints/resource_planning.py:~1325-1331`
- Symptom: `if "start_date" in patch: a.pinned_start = True` fires even when patch value equals current `a.start_date`. Creates phantom pins from form re-submits.
- Fix: only flip pin if value actually differs; also skip implicit end_date shift when delta=0.
- Acceptance: PATCH with start_date=current value doesn't change pin flags.

**13. Force-employee + start_date in one PATCH inconsistent.**
- Location: `app/api/endpoints/resource_planning.py:~1366-1396`
- Symptom: if PATCH carries both employee_id + start_date, row gets pinned_start=True before compute_schedule. Falls into date-pinned branch with NEW employee + OLD coordinates. Pre-deduct uses wrong dates.
- Fix: when force=true present, defer start_date application until AFTER compute; OR disallow combining the two in one PATCH (422 if both present with force=true).
- Acceptance: force-employee PATCH with explicit date results in clean schedule, no double-counting.

**14. Leveler overload fallback exceeds involvement cap.**
- Location: `app/services/rcpsp_leveler.py:~50` (`_per_day_hours` fallback)
- Symptom: when daily_hours_json absent, fallback = `hours_allocated / len(working)`. For phases with involvement<1, allocator capped per-day below 8h, but fallback assumes uniform and may exceed `8h × involvement` → false overload.
- Fix: fallback cap = `min(per, daily_max)` where daily_max derived from phase's involvement.
- Acceptance: phases without daily_hours_json don't trigger spurious overload.

### P2 (cleanup / minor)

**15. Dead code: legacy split map + OPO placeholder in `_assign_employees`.**
- Location: `app/services/resource_planning_service.py:~1264, ~1288, 533-534, 740-790`
- Symptom: `_compute_legacy_split_map` returns `{}` always; downstream chunk handling unreachable. `_assign_employees` writes `result["opo"]` which is never read.
- Fix: delete dead branches; remove unused fields.

**16. `_topological_order` is O(N·E).**
- Location: `app/services/resource_planning_service.py:~1535-1562`
- Symptom: inner loop scans `preds.items()` per dequeued node. Hundreds of phases × deps noticeable.
- Fix: precompute successor adjacency list, walk in O(N+E).

**17. `split_assignment` defense gap.**
- Location: `app/services/resource_planning_service.py:~1655-1669`
- Symptom: rejects part_number≠1 but not rows where pinned_split=True already.
- Fix: additional guard `if a.pinned_split: raise ValueError(...)`.

**18. `_quarter_bounds` 500 on malformed quarter.**
- Location: `app/api/endpoints/resource_planning.py:~1176`
- Symptom: `int(str(plan.quarter).replace("Q",""))` raises ValueError → 500.
- Fix: try/except → 422 with detail.

**19. Fork doesn't copy manual edit state.**
- Location: `app/api/endpoints/resource_planning.py:~2535-2549` (`fork_plan`)
- Symptom: clone misses `pinned_*` flags, `predecessors_user_set`, `daily_hours_json`, `out_of_quarter`, `manual_edit_at`. Forked plan is effectively fresh.
- Fix: copy these columns in the fork insert.
- Acceptance: forked plan's bars match original on first view.

**20. Muted conflicts never re-evaluated.**
- Location: `app/services/resource_planning_service.py:~2026-2028` + `_persist_conflicts`
- Symptom: user mutes an OVERLOAD, conflict no longer reproduces → muted row stays forever.
- Fix: on persist, drop muted rows whose `detection_key` isn't in current `detected` set.
- Acceptance: muted conflict disappears when underlying cause resolved.

**21. N+1 employee name lookup in conflict_aggregator.**
- Location: `app/services/conflict_aggregator.py:~74-102` (`_resolve_employee_name`)
- Symptom: per-conflict `db.get(Employee, id)`. For plans with many overloads → N round-trips.
- Fix: bulk-load employees once into dict, look up from there.

---

## Execution plan (batches)

### Batch 1 — P0 (4 fixes) ✅ e8e1ab1
1. ✅ Allocator partial-day capacity (finding 1)
2. ✅ add_predecessor atomic cycle check (finding 2)
3. ✅ merge preserve external successors (finding 3)
4. ✅ Leveler daily JSON sync (finding 4)

### Batch 2 — P1 group A (5 fixes) ✅ 85f634b
5. ✅ OPO dual-row default chain
6. ✅ Shift daily JSON trim
8. ✅ Quarter spillover not critical (slack < 0)
9. ✅ Redistribute respects phases_with_inbound_pred
10. ✅ pinned_employee snapshot regardless of other flags

### Batch 3 — P1 group B (5 fixes) ✅ 277726d
7. ✅ split_assignment pre-check blocks cascade on already-split downstream
11. ✅ _restore_predecessors 4-tuple → 3-tuple fallback
12. ✅ PATCH no-op start_date doesn't pin
13. ✅ Force-employee + start_date combo → 422
14. ✅ Leveler fallback daily cap

### Batch 4 — P2 (7 fixes) ✅ 2c40263
15. ✅ Dead code cleanup (legacy split map + opo placeholder)
16. ✅ _topological_order O(N+E) via adjacency list
17. ✅ split_assignment guards pinned_split
18. ✅ _quarter_bounds raises ValueError → 422
19. ✅ fork copies manual-edit state
20. ✅ muted conflicts re-evaluated
21. ✅ N+1 employee/item lookup → bulk

Все 21 финдинг закрыты. Test suite: 977 passed (+1 pre-existing fail
`test_pinned_start_preserved_on_recompute` из 2145b05, не связан).

---

## Verification per fix

Each batch ends with:
- `py -3.10 -m pytest tests/test_resource_planning_service.py tests/test_api_assignment_patch.py tests/test_resource_planning_endpoints.py tests/test_api_assignment_split.py tests/services/test_rp_pinned_edits.py tests/services/test_rp_predecessor_graph.py tests/test_resource_planning_assignment_logic.py`
- Direct compute of live plan `348da59b-...` via Python: should run in <0.5s, no IntegrityError.
- Manual UI check: open `/resource-planning?plan_id=348da59b...`, hit «Распределить», inspect PRJ-10623 dev (split case from this session).

---

## How to resume

In next session, open this file + read MEMORY index. Start at Batch 1. Commit each batch separately; push after each commit (per memory `feedback_commit_push_after_batch`).

If user adds new findings during execution, append to the appropriate batch and renumber as needed.
