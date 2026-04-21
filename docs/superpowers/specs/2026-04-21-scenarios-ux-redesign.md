# Scenarios UX Redesign

**Date:** 2026-04-21  
**Status:** Approved

## Problem

Five issues reported in the Scenarios section:

1. Mandatory work rules editor is hard to find (hidden in collapsible in right panel) and inconvenient to edit
2. Role capacity bars overflow their container when plan exceeds capacity
3. External QA hours card overflows its container bounds
4. *(Non-issue)* PM hours in analyst pool — confirmed correct behavior, no change needed
5. "Resources by roles" block shows no mandatory work breakdown; user needs drill-down similar to Excel reference

## Solution Overview

Three independent changes:

1. **New "Правила" tab** — move rules editor out of right panel into a dedicated full-width tab
2. **"Сводка ресурсов" block** — new full-width table above allocations showing capacity breakdown by role and work type
3. **CSS overflow fixes** — clamp bars and input cards within their containers

---

## Change 1: Rules Tab

### UI

The scenario page gains two tabs below the scenario header:
- **Распределение** — existing allocations table (default)
- **Правила** — new rules editor

The "ScenarioRulesEditor" collapsible section is removed from the right panel.

### Rules Tab Contents

Full-width table with columns:

| Роль | Вид обязательных работ | % от нормы | (удалить) |
|------|----------------------|------------|-----------|
| Аналитик | Орг. работы | 15 | ✕ |
| Все роли | Орг. работы | 15 | ✕ |

Below table:
- **«+ Добавить правило»** button — appends empty row
- **«Копировать из квартала»** button — opens a small popover with Year + Quarter selectors; on confirm, replaces all current scenario rules with `role_capacity_rules` records matching that year+quarter

Validation (non-blocking warning banner):
- Sum of % per role must not exceed 100
- Duplicate (role, work_type_id) pairs highlighted

### API

Existing endpoints are sufficient:
- `GET /scenarios/{id}/rules` — list
- `PUT /scenarios/{id}/rules` — atomic replace (already exists)
- `GET /capacity/role-rules/batch?year=Y&quarter=Q` context for the "copy from quarter" source — returns template rules to preview before copying

No new backend endpoint needed for the tab itself.

---

## Change 2: "Сводка ресурсов" Block

### Placement

New card between the scenario header row and the allocations/rules tabs. Always visible regardless of which tab is active.

### Table Structure

```
|                         | Аналитики | Программисты | Тестировщики | Консультанты | Рук. проектов | Итого |
|-------------------------|-----------|--------------|--------------|--------------|---------------|-------|
| Всего норма-часов       |   423     |    1 264     |     680      |     461      |      462      | 3 290 |
| — <Work type> (<pct>%)  |    63     |     190      |     102      |      69      |       69      |  493  |
| — <Work type> (<pct>%)  |   127     |      —       |      —       |      —       |        —      |  127  |
| На бэклог               |   233     |    1 074     |     578      |     392      |      393      | 2 670 |
```

Rules:
- Only work types with `subtracts_from_pool=True` appear as rows
- Work type rows show percentage small next to hours: `127 <span>30%</span>`
- If a role has no rule for a work type → show `—`
- External QA: if `external_qa_hours` is set, the Тестировщики column shows that value in "Всего" and "На бэклог" rows, with a note "(внешний)"
- Role header cells: hovering shows an AntD `Tooltip` listing employee names for that role (e.g. "Копышков Н., Петрова А.")

### New Backend Endpoint

`GET /scenarios/{id}/resource-summary`

Response schema `ResourceSummaryOut`:
```python
class WorkTypeRow(BaseModel):
    work_type_id: str
    work_type_label: str
    subtracts_from_pool: bool
    by_role: dict[str, float | None]   # role → hours (None = no rule)
    by_role_pct: dict[str, float | None]  # role → pct
    total: float

class ResourceSummaryOut(BaseModel):
    roles: list[str]                   # ordered role labels
    role_employee_names: dict[str, list[str]]  # role → employee names
    total_by_role: dict[str, float]
    total: float
    work_type_rows: list[WorkTypeRow]  # only subtracts_from_pool=True
    available_for_backlog_by_role: dict[str, float]
    available_for_backlog_total: float
    external_qa_hours: float | None
```

Implementation: reuse `ResourceBaseService` data + join with scenario rules + mandatory work types. No heavy computation — a single query join.

### Frontend

New component `ScenarioResourceSummary` in `frontend/src/components/planning/`.  
Uses `useQuery(['scenario-summary', scenarioId])` → `GET /scenarios/{id}/resource-summary`.  
Invalidated when scenario rules change (same query key pattern as other scenario queries).

---

## Change 3: CSS Overflow Fixes

### RoleCapacityBar

File: `frontend/src/components/planning/RoleCapacityBar.tsx`

The bar container div needs `overflow: hidden` so the filled portion and overflow zone cannot escape the card boundary. The overflow visual indicator (orange tail) must stay within the bar track width — render it as a right-anchored segment inside the track, not as a separate element that extends beyond.

### ExternalQaInput / Тестировщик card

File: `frontend/src/components/planning/ExternalQaInput.tsx` (or its parent card in `PlanningCapacityPanel.tsx`)

Add `maxWidth: '100%'` and `overflow: hidden` to the card wrapper. The input field should not force the card wider than its container.

---

## Out of Scope

- Gantt chart / initiative timeline
- Per-employee capacity drill-down in the summary table
- Editable cells in the summary table (it is read-only)
- Any changes to the allocations table or right-panel employee list

---

## Files Changed

**Frontend (new/modified):**
- `frontend/src/pages/PlanningPage.tsx` — add tabs, render ScenarioResourceSummary
- `frontend/src/components/planning/ScenarioResourceSummary.tsx` — new
- `frontend/src/components/planning/ScenarioRulesEditor.tsx` — move out of panel, add "copy from quarter"
- `frontend/src/components/planning/PlanningCapacityPanel.tsx` — remove ScenarioRulesEditor
- `frontend/src/components/planning/RoleCapacityBar.tsx` — overflow fix
- `frontend/src/components/planning/ExternalQaInput.tsx` — overflow fix
- `frontend/src/types/api.ts` — ResourceSummaryOut, WorkTypeRow types

**Backend (new/modified):**
- `app/api/endpoints/planning.py` — add `GET /scenarios/{id}/resource-summary`
- `app/services/resource_base_service.py` — add `compute_summary()` method or similar
