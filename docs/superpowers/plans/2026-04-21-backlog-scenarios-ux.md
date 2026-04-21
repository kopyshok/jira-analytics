# Backlog + Scenarios UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 9 UX improvements across Backlog and Scenarios pages: bug fixes for role saving and resource totals, backend extension for resource breakdown, and frontend polish for both pages.

**Architecture:** Two backend changes (С-2 fix is frontend-only; С-5 patches `compute_summary()`; С-4 adds two new fields to `ResourceSummary` dataclass and `ResourceSummaryOut` Pydantic schema). Seven frontend changes spread across three files: `ScenarioResourceSummary.tsx`, `PlanningPage.tsx`, `PlanningCapacityPanel.tsx`, `BacklogPage.tsx`.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy (backend); React 19 + TypeScript + Ant Design 6 + TanStack Query (frontend).

---

## File Map

| File | What changes |
|---|---|
| `app/services/resource_base_service.py` | С-5: filter `subtracts_from_pool` in `compute_summary()`; С-4: add `calendar_gross_by_role` + `absence_days_by_employee` fields + computation |
| `app/api/endpoints/planning.py` | С-4: add new fields to `ResourceSummaryOut` Pydantic schema + mapping in endpoint |
| `frontend/src/types/api.ts` | С-4: add `calendar_gross_by_role` + `absence_days_by_employee` to `ResourceSummaryOut` |
| `frontend/src/components/planning/PlanningCapacityPanel.tsx` | С-2: fix `knownRole`; С-4: Collapse + breakdown table + gauge fix |
| `frontend/src/components/planning/ScenarioResourceSummary.tsx` | С-1: font sizes, role color borders, work type truncation |
| `frontend/src/pages/PlanningPage.tsx` | С-3: remove Risk col, rename + add % to Всего; lift `useScenarioResourceSummary`; pass `summary` to `PlanningCapacityPanel` |
| `frontend/src/pages/BacklogPage.tsx` | Б-1: Исполнитель + Заказчик cols; Б-2: colored role cells + Popover; Б-3: remove Risk, add Всего часов + % |

---

## Task 1: С-5 — Fix `compute_summary()` to only subtract pool-subtracting work types

**Files:**
- Modify: `app/services/resource_base_service.py:407-412`

This bug causes "На бэклог" total in the summary table to differ from "Ресурс команды" gauge. The `compute_summary()` subtracts ALL work type rows from available hours, while `compute()` only subtracts `subtracts_from_pool=True` rows. Fix: add filter.

- [ ] **Step 1: Locate and patch the `available_by_role` computation in `compute_summary()`**

In `app/services/resource_base_service.py`, find lines ~407-412 (inside `compute_summary`):

```python
        # --- доступные часы = валовые − обязательные ---
        available_by_role: dict[str, float] = {}
        for role in roles_ordered:
            gross = gross_by_role.get(role, 0.0)
            mandatory_total = sum(row.hours_by_role.get(role, 0.0) for row in wt_rows)
            available_by_role[role] = round(max(0.0, gross - mandatory_total), 2)
```

Replace with:

```python
        # --- доступные часы = валовые − обязательные (только subtracts_from_pool=True) ---
        available_by_role: dict[str, float] = {}
        for role in roles_ordered:
            gross = gross_by_role.get(role, 0.0)
            mandatory_total = sum(
                row.hours_by_role.get(role, 0.0)
                for row in wt_rows
                if row.subtracts_from_pool
            )
            available_by_role[role] = round(max(0.0, gross - mandatory_total), 2)
```

- [ ] **Step 2: Run backend tests**

```bash
py -3.10 -m pytest tests/ -v -k "resource" --tb=short
```

Expected: all pass (or same failures as pre-existing).

- [ ] **Step 3: Commit**

```bash
git add app/services/resource_base_service.py
git commit -m "fix(planning): compute_summary subtracts only subtracts_from_pool work types (С-5)"
```

---

## Task 2: С-4 Backend — Add `calendar_gross_by_role` and `absence_days_by_employee` to `ResourceSummary`

**Files:**
- Modify: `app/services/resource_base_service.py`
- Modify: `app/api/endpoints/planning.py`

- [ ] **Step 1: Add new fields to `ResourceSummary` dataclass**

In `app/services/resource_base_service.py`, the `ResourceSummary` dataclass (lines ~46-60). Add two fields at the end:

```python
@dataclass
class ResourceSummary:
    """Сводная разбивка ресурса команды по видам обязательных работ и ролям."""

    year: int
    quarter: int
    team: str
    roles: list[str]
    role_employee_names: dict[str, list[str]]
    gross_by_role: dict[str, float]
    gross_total: float
    work_type_rows: list[WorkTypeSummaryRow]
    available_by_role: dict[str, float]
    available_total: float
    external_qa_hours: Optional[float]
    calendar_gross_by_role: dict[str, float]          # production calendar hours, no deductions
    absence_days_by_employee: list[dict]               # [{employee_id, display_name, role, days}]
```

- [ ] **Step 2: Add `calendar_gross_by_role` computation in `compute_summary()`**

In `compute_summary()`, insert a first pass to compute calendar gross (no absence, no mandatory deductions) right before the existing employee loop (`gross_by_emp` computation). Find the comment `# --- валовые часы по сотрудникам (без вычета обязательных) ---` and insert before it:

```python
        # --- брутто: производственный календарь × сотрудники (без любых вычетов) ---
        calendar_gross_by_role: dict[str, float] = {}
        for e in employees:
            total_cal = 0.0
            cur = period_start
            while cur < period_end:
                total_cal += day_hours(cur)
                cur += timedelta(days=1)
            if e.role:
                calendar_gross_by_role[e.role] = (
                    calendar_gross_by_role.get(e.role, 0.0) + round(total_cal, 2)
                )
```

- [ ] **Step 3: Add `absence_days_by_employee` computation in `compute_summary()`**

Insert after the `gross_by_emp` loop (after `emp_name[e.id] = e.display_name`). Add within the same employee loop that computes `gross_by_emp`:

```python
        # --- дни отсутствия по сотрудникам ---
        absence_days_by_employee: list[dict] = []
        for e in employees:
            abs_ranges = (
                self.db.query(Absence)
                .filter(
                    Absence.employee_id == e.id,
                    Absence.start_date < period_end,
                    Absence.end_date >= period_start,
                )
                .all()
            )
            days_count = 0.0
            cur = period_start
            while cur < period_end:
                if day_hours(cur) > 0:
                    if any(a.start_date <= cur <= a.end_date for a in abs_ranges):
                        days_count += 1.0
                cur += timedelta(days=1)
            if days_count > 0:
                absence_days_by_employee.append({
                    "employee_id": e.id,
                    "display_name": e.display_name,
                    "role": e.role,
                    "days": days_count,
                })
```

NOTE: The `abs_ranges` query in the existing `gross_by_emp` loop already runs per-employee — place this `absence_days_by_employee` block after the existing loop (not inside it) to avoid N+1 duplication. Read the existing code structure before inserting.

- [ ] **Step 4: Pass new fields in `return ResourceSummary(...)`**

At the end of `compute_summary()`, update the `return ResourceSummary(...)` call to include:

```python
        return ResourceSummary(
            year=year,
            quarter=q,
            team=team,
            roles=list(roles_ordered),
            role_employee_names=role_employee_names,
            gross_by_role=gross_by_role,
            gross_total=gross_total,
            work_type_rows=wt_rows,
            available_by_role=available_by_role,
            available_total=available_total,
            external_qa_hours=scenario.external_qa_hours,
            calendar_gross_by_role=calendar_gross_by_role,
            absence_days_by_employee=absence_days_by_employee,
        )
```

- [ ] **Step 5: Add new fields to `ResourceSummaryOut` Pydantic schema**

In `app/api/endpoints/planning.py`, the `ResourceSummaryOut` class (line ~160):

```python
class ResourceSummaryOut(BaseModel):
    year: int
    quarter: int
    team: str
    roles: List[str]
    role_employee_names: Dict[str, List[str]]
    total_by_role: Dict[str, float]
    total: float
    work_type_rows: List[WorkTypeRowOut]
    available_for_backlog_by_role: Dict[str, float]
    available_for_backlog_total: float
    external_qa_hours: Optional[float] = None
    calendar_gross_by_role: Dict[str, float] = {}
    absence_days_by_employee: List[Dict] = []
```

- [ ] **Step 6: Map new fields in the endpoint**

In the `/scenarios/{scenario_id}/resource-summary` endpoint (line ~645), find the `return ResourceSummaryOut(...)` call and add:

```python
        calendar_gross_by_role=summary.calendar_gross_by_role,
        absence_days_by_employee=summary.absence_days_by_employee,
```

- [ ] **Step 7: Run backend tests**

```bash
py -3.10 -m pytest tests/ -v -k "resource or planning" --tb=short
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app/services/resource_base_service.py app/api/endpoints/planning.py
git commit -m "feat(planning): add calendar_gross_by_role + absence_days_by_employee to ResourceSummary (С-4 backend)"
```

---

## Task 3: С-4 Frontend types

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add new fields to `ResourceSummaryOut` interface**

In `frontend/src/types/api.ts`, the `ResourceSummaryOut` interface (line ~469):

```typescript
export interface ResourceSummaryOut {
  year: number;
  quarter: number;
  team: string;
  roles: string[];
  role_employee_names: Record<string, string[]>;
  total_by_role: Record<string, number>;
  total: number;
  work_type_rows: WorkTypeRow[];
  available_for_backlog_by_role: Record<string, number>;
  available_for_backlog_total: number;
  external_qa_hours: number | null;
  calendar_gross_by_role: Record<string, number>;
  absence_days_by_employee: Array<{ employee_id: string; display_name: string; role: string | null; days: number }>;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(planning): add calendar_gross_by_role + absence_days_by_employee to frontend types"
```

---

## Task 4: С-2 — Fix role not saving in «По сотрудникам»

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx:229`

The bug: `knownRole` only treats `analyst`, `dev`, `qa` as known; `project_manager`, `consultant`, etc. return `null`, so the role Select keeps appearing even after save.

- [ ] **Step 1: Fix `knownRole` derivation**

In `PlanningCapacityPanel.tsx`, find line ~229:

```typescript
            const knownRole = e.role && (CORE_ROLE_KEYS as readonly string[]).includes(e.role) ? e.role : null;
```

Replace with:

```typescript
            const knownRole = e.role && roles.some(r => r.code === e.role && r.is_active) ? e.role : null;
```

- [ ] **Step 2: Fix `roleShort` to handle non-core roles**

The `roleShort` fallback below `knownRole` already works (uses `ROLE_SHORT_LOCAL[knownRole] ?? knownRole.slice(0, 2).toUpperCase()`), but add `project_manager` to `ROLE_SHORT_LOCAL` map. Find the `ROLE_SHORT_LOCAL` constant near the top of the file (~line 19):

```typescript
const ROLE_SHORT_LOCAL: Record<string, string> = {
  analyst: 'АН',
  dev: 'ПР',
  qa: 'ТС',
  consultant: 'КН',
  project_manager: 'РП',
  other: 'ДР',
};
```

- [ ] **Step 3: Build to check for type errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx
git commit -m "fix(planning): knownRole uses roles registry — consultant/РП badges now show after save (С-2)"
```

---

## Task 5: С-1 — ScenarioResourceSummary font, role colors, truncation

**Files:**
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

- [ ] **Step 1: Update font sizes and add `getRoleColor` import**

In `ScenarioResourceSummary.tsx`:

1. Add `getRoleColor` to import from `'../../utils/roles'`:
```typescript
import { getRoleLabel, getRoleColor } from '../../utils/roles';
```

2. Update `CELL` constant (font 12 → 14) and `CELL_LABEL` constant (font 12 → 13):
```typescript
const CELL: React.CSSProperties = {
  padding: '7px 10px',
  textAlign: 'right' as const,
  fontFamily: FONTS.mono,
  fontSize: 14,
};

const CELL_LABEL: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  color: DARK_THEME.textMuted,
};
```

- [ ] **Step 2: Add role color borders and tinted bg to role columns (Variant В)**

In the `return` JSX, each role column cell is rendered via `summary.roles.map((role) => ...)` in both the header and data rows. After defining `gridCols`, add a helper:

```typescript
  const roleCellStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
      background: `${color}08`,
    };
  };
```

- [ ] **Step 3: Apply `roleCellStyle` to header role cells**

Find the header `<Tooltip>` block that renders each role. Update the inner `<div>`:

```tsx
            <Tooltip
              key={role}
              title={
                names.length > 0 ? (
                  <div>{names.map((n) => <div key={n}>{n}</div>)}</div>
                ) : 'Нет сотрудников'
              }
            >
              <div
                style={{
                  ...CELL,
                  ...roleCellStyle(role),
                  textAlign: 'center',
                  color: DARK_THEME.textSecondary,
                  cursor: 'default',
                  paddingTop: 10,
                }}
              >
                <div style={{ fontWeight: 600, color: getRoleColor(roles, role) }}>{label}</div>
                <div
                  style={{
                    height: 3,
                    background: getRoleColor(roles, role),
                    borderRadius: 2,
                    margin: '4px auto',
                    width: '80%',
                  }}
                />
                <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 2 }}>
                  {names.length} чел. ⓘ
                </div>
              </div>
            </Tooltip>
```

- [ ] **Step 4: Apply `roleCellStyle` to all data row role cells**

For all data rows (`Всего норма-часов`, `work_type_rows`, `На бэклог`), merge `roleCellStyle(role)` into each role cell's style:

In the **Всего норма-часов** row:
```tsx
        {summary.roles.map((role) => (
          <div key={role} style={{ ...CELL, ...roleCellStyle(role), fontWeight: 600 }}>
            {Math.round(summary.total_by_role[role] ?? 0).toLocaleString('ru')}
          </div>
        ))}
```

In the **work_type_rows** row:
```tsx
              <div key={role} style={{ ...CELL, ...roleCellStyle(role), color: DARK_THEME.textMuted }}>
```

In the **На бэклог** row:
```tsx
            <div
              key={role}
              style={{
                ...CELL,
                ...roleCellStyle(role),
                background: 'rgba(0,201,200,0.1)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
              }}
            >
```

Note: for «На бэклог», the tinted background from `roleCellStyle` is `${color}08` but gets overridden by `rgba(0,201,200,0.1)`. Keep the explicit background override but keep border styles from `roleCellStyle`:

```typescript
  const roleBorderStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
    };
  };
```

Use `roleBorderStyle` for the «На бэклог» row cells so the explicit cyan background isn't overridden.

- [ ] **Step 5: Work type label truncation**

Find the work type label cell in `work_type_rows.map(...)`:

```tsx
          <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }}>
            — {row.work_type_label}
          </div>
```

Replace with:

```tsx
          <Tooltip title={row.work_type_label}>
            <div
              style={{
                ...CELL_LABEL,
                background: DARK_THEME.darkAccent,
                maxWidth: 140,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              — {row.work_type_label}
            </div>
          </Tooltip>
```

- [ ] **Step 6: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): ScenarioResourceSummary — font 14px, role color borders, work type truncation (С-1)"
```

---

## Task 6: С-3 — PlanningPage: remove Risk, rename Всего + %, lift summary fetch

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 1: Add `useScenarioResourceSummary` import and call**

In `PlanningPage.tsx`, add `useScenarioResourceSummary` to the import from `'../hooks/usePlanning'`:

```typescript
import {
  useScenarios,
  useScenario,
  useScenarioAllocations,
  usePatchAllocation,
  useDeleteScenario,
  useApproveScenario,
  useRevertScenario,
  useSyncScenarioBacklog,
  useScenarioResource,
  useUpdateScenario,
  usePatchAllocationAssignee,
  useScenarioResourceSummary,
} from '../hooks/usePlanning';
```

After the existing `useScenarioResource` call (~line 106), add:

```typescript
  const { data: resourceSummary } = useScenarioResourceSummary(
    scenarioId ?? '',
    !!scenario?.team,
  );
```

- [ ] **Step 2: Update `GRID` constant — remove last 95px (Risk column)**

Find line 43:
```typescript
const GRID = '40px 60px 1fr 150px 120px 280px 75px 100px 95px';
```

Replace with:
```typescript
const GRID = '40px 60px 1fr 150px 120px 280px 90px 100px';
```

- [ ] **Step 3: Remove Risk header span**

Find the header row div (the grid with `padding: '8px 14px'`). Remove `<span>Риск</span>`:

```tsx
                        <span>✓</span>
                        <span>Прио</span>
                        <span>Идея</span>
                        <span>Исполнитель</span>
                        <span>Заказчик</span>
                        <span>АН / ПР / ТС / ОПЭ</span>
                        <span style={{ textAlign: 'right' }}>Всего часов</span>
                        <span>Влияние</span>
```

(Remove the `<span>Риск</span>` line and rename `Всего` → `Всего часов`.)

- [ ] **Step 4: Remove Risk cell from allocation row, update total cell**

In the allocation row render (~line 500-513), find:

```tsx
                              <span style={{ textAlign: 'right', fontFamily: FONTS.mono, fontSize: 14, color: DARK_THEME.textPrimary }}>
                                {Math.round(total)} ч
                              </span>
                              <div>
                                {a.impact ? (
                                  <Tag color={IMPACT_COLORS[a.impact]}>{IMPACT_LABELS[a.impact]}</Tag>
                                ) : (
                                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                                )}
                              </div>
                              <div>
                                {a.risk ? (
                                  <Tag color={RISK_COLORS[a.risk]}>{RISK_LABELS[a.risk]}</Tag>
                                ) : (
                                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                                )}
                              </div>
```

Replace with (remove Risk div, add % line under hours):

```tsx
                              <div style={{ textAlign: 'right' }}>
                                <span style={{ fontFamily: FONTS.mono, fontSize: 14, color: DARK_THEME.textPrimary }}>
                                  {Math.round(total)} ч
                                </span>
                                {resourceSummary && resourceSummary.available_for_backlog_total > 0 && (
                                  <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 1 }}>
                                    {Math.round((total / resourceSummary.available_for_backlog_total) * 100)}% ресурса
                                  </div>
                                )}
                              </div>
                              <div>
                                {a.impact ? (
                                  <Tag color={IMPACT_COLORS[a.impact]}>{IMPACT_LABELS[a.impact]}</Tag>
                                ) : (
                                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                                )}
                              </div>
```

- [ ] **Step 5: Pass `summary` prop to `PlanningCapacityPanel`**

Find the `<PlanningCapacityPanel .../>` JSX (~line 545):

```tsx
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
              />
```

Replace with:

```tsx
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                summary={resourceSummary}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
              />
```

- [ ] **Step 6: Remove unused RISK_COLORS / RISK_LABELS constants**

Find lines ~40-41:
```typescript
const RISK_COLORS: Record<BacklogImpactRisk, string> = { low: 'green', medium: 'default', high: 'warning' };
const RISK_LABELS: Record<BacklogImpactRisk, string> = { low: 'низкий', medium: 'средний', high: 'высокий' };
```

Delete both lines. Also remove `BacklogImpactRisk` from the import if `IMPACT_COLORS`/`IMPACT_LABELS` still use it — keep it if so (it's still used).

- [ ] **Step 7: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: no TypeScript errors. If `BacklogImpactRisk` import error appears, ensure it's still used by `IMPACT_COLORS`/`IMPACT_LABELS`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): remove Risk col, add Всего часов + % ресурса, lift summary to PlanningPage (С-3)"
```

---

## Task 7: С-4 Frontend — `PlanningCapacityPanel` Collapse + breakdown + gauge fix

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1: Add `Collapse` to AntD imports and `ResourceSummaryOut` to type imports**

```typescript
import { Card, Collapse, Select, Skeleton, Tag, Tooltip } from 'antd';
import type { AllocationResponse, ResourceBase, ResourceSummaryOut } from '../../types/api';
```

- [ ] **Step 2: Add `summary` to the `Props` interface**

```typescript
interface Props {
  resourceBase: ResourceBase | undefined;
  summary: ResourceSummaryOut | undefined;
  allocations: AllocationResponse[];
  quarter: string;
  scenarioId: string;
}
```

Update the function signature:
```typescript
export default function PlanningCapacityPanel({ resourceBase, summary, allocations, quarter, scenarioId }: Props) {
```

- [ ] **Step 3: Fix `totalCapacity` to sum ALL roles in `role_totals`**

Find line ~107:
```typescript
  const totalCapacity = CORE_ROLE_KEYS.reduce((s, r) => s + capacityByRole[r], 0);
```

Replace with:
```typescript
  const totalCapacity = Object.values(resourceBase.role_totals).reduce((s, v) => s + v, 0);
```

Also update `overallOver` and `totalDemand` to be based on all roles with demand. The existing logic uses `CORE_ROLE_KEYS` for demand. Keep `totalDemand` as CORE roles demand (demand only exists for analyst/dev/qa/consultant — where estimates exist). The gauge shows demand vs total capacity (all roles).

- [ ] **Step 4: Replace the «Ресурс команды» Card with a `Collapse`**

Find the entire Card block starting with `{/* 1. Overall gauge */}` (~line 125) through `</Card>` (~line 195). Replace with:

```tsx
      {/* 1. Overall gauge — expandable resource breakdown */}
      <Collapse
        defaultActiveKey={[]}
        style={{ background: 'transparent', border: 'none' }}
        items={[
          {
            key: 'resource',
            label: (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 }}>
                  Ресурс команды · Q{quarter}
                </span>
                {resourceBase.external_qa_hours != null && (
                  <Tag color="purple" style={{ fontSize: 10, lineHeight: '18px' }}>
                    внешний QA {Math.round(resourceBase.external_qa_hours)} ч
                  </Tag>
                )}
              </div>
            ),
            children: summary ? (
              <ResourceBreakdownTable summary={summary} />
            ) : (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint, padding: '8px 0' }}>
                Загрузка разбивки…
              </div>
            ),
            extra: (
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 42, fontWeight: 700, color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary, fontFamily: FONTS.mono, lineHeight: 1 }}>
                    {Math.round(totalDemand)}
                  </span>
                  <span style={{ fontSize: 16, color: DARK_THEME.textMuted }}>/</span>
                  <span style={{ fontSize: 24, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
                    {Math.round(totalCapacity)} ч
                  </span>
                </div>
                <div style={{ fontSize: 11, color: DARK_THEME.textHint, marginBottom: 10 }}>
                  {overallOver
                    ? 'Перегруз по одной или нескольким ролям — см. ниже'
                    : totalCapacity > 0
                      ? `Запас ${freeHours} ч · ${freePct}% свободно · включено ${includedCount} идей`
                      : 'Нет данных о ёмкости'}
                </div>
                <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkAccent, borderRadius: 7, overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${plannedPct}%`, background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary, transition: 'width .2s' }} />
                </div>
              </div>
            ),
          },
        ]}
      />
```

Note: The `extra` prop in AntD Collapse Panel shows content outside the collapse area. You may need to restructure so the gauge is always visible and the breakdown table appears only when expanded. Alternative approach: wrap the whole thing in a Card, put gauge always visible, use Collapse with `ghost` style just for the expandable part:

```tsx
      {/* 1. Overall gauge — expandable resource breakdown */}
      <Card styles={{ body: { padding: '12px 16px' } }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <span style={{ fontSize: 11, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Ресурс команды · Q{quarter}
          </span>
          {resourceBase.external_qa_hours != null && (
            <Tag color="purple" style={{ fontSize: 10, lineHeight: '18px' }}>
              внешний QA {Math.round(resourceBase.external_qa_hours)} ч
            </Tag>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 42, fontWeight: 700, color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary, fontFamily: FONTS.mono, lineHeight: 1 }}>
            {Math.round(totalDemand)}
          </span>
          <span style={{ fontSize: 16, color: DARK_THEME.textMuted }}>/</span>
          <span style={{ fontSize: 24, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
            {Math.round(totalCapacity)} ч
          </span>
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textHint, marginBottom: 10 }}>
          {overallOver
            ? 'Перегруз по одной или нескольким ролям — см. ниже'
            : totalCapacity > 0
              ? `Запас ${freeHours} ч · ${freePct}% свободно · включено ${includedCount} идей`
              : 'Нет данных о ёмкости'}
        </div>
        <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkAccent, borderRadius: 7, overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${plannedPct}%`, background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary, transition: 'width .2s' }} />
        </div>
        {summary && (
          <Collapse
            ghost
            items={[{
              key: 'breakdown',
              label: <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>Разбивка по ролям ↓</span>,
              children: <ResourceBreakdownTable summary={summary} />,
            }]}
          />
        )}
      </Card>
```

- [ ] **Step 5: Create the `ResourceBreakdownTable` sub-component**

Add as a named function before `PlanningCapacityPanel` (or at the bottom of the file before the `export default`):

```tsx
function ResourceBreakdownTable({ summary }: { summary: ResourceSummaryOut }) {
  const roles = summary.roles;

  // Vacation hours per role = calendar_gross − gross (gross already excludes absences)
  const vacationByRole: Record<string, number> = {};
  for (const role of roles) {
    const cal = summary.calendar_gross_by_role[role] ?? 0;
    const gross = summary.total_by_role[role] ?? 0;
    vacationByRole[role] = Math.round(cal - gross);
  }

  // Mandatory hours per role (only subtracts_from_pool rows)
  const mandatoryByRole: Record<string, number> = {};
  for (const role of roles) {
    mandatoryByRole[role] = 0;
  }
  for (const row of summary.work_type_rows) {
    if (!row.subtracts_from_pool) continue;  // NOTE: need this field in WorkTypeRow type
    for (const role of roles) {
      mandatoryByRole[role] = (mandatoryByRole[role] ?? 0) + Math.round(row.by_role[role] ?? 0);
    }
  }

  const calTotal = Math.round(Object.values(summary.calendar_gross_by_role).reduce((s, v) => s + v, 0));
  const vacTotal = Math.round(Object.values(vacationByRole).reduce((s, v) => s + v, 0));
  const mandTotal = Math.round(Object.values(mandatoryByRole).reduce((s, v) => s + v, 0));
  const availTotal = Math.round(summary.available_for_backlog_total);

  const cellStyle: React.CSSProperties = {
    padding: '4px 8px',
    textAlign: 'right',
    fontFamily: FONTS.mono,
    fontSize: 12,
    color: DARK_THEME.textSecondary,
  };
  const labelStyle: React.CSSProperties = {
    padding: '4px 8px',
    fontSize: 11,
    color: DARK_THEME.textMuted,
  };

  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 12,
  };

  return (
    <div style={{ marginTop: 4 }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={{ ...labelStyle, textAlign: 'left' }} />
            {roles.map((r) => (
              <th key={r} style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>
                {r.slice(0, 2).toUpperCase()}
              </th>
            ))}
            <th style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>Итого</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={labelStyle}>Брутто</td>
            {roles.map((r) => (
              <td key={r} style={cellStyle}>{Math.round(summary.calendar_gross_by_role[r] ?? 0)}</td>
            ))}
            <td style={{ ...cellStyle, fontWeight: 600, color: DARK_THEME.textPrimary }}>{calTotal}</td>
          </tr>
          <tr>
            <td style={{ ...labelStyle, color: DARK_THEME.textHint }}>− Отпуска</td>
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                {vacationByRole[r] > 0 ? `−${vacationByRole[r]}` : '—'}
              </td>
            ))}
            <td style={{ ...cellStyle, color: DARK_THEME.textHint }}>{vacTotal > 0 ? `−${vacTotal}` : '—'}</td>
          </tr>
          <tr>
            <td style={{ ...labelStyle, color: DARK_THEME.textHint }}>− Обяз. работы</td>
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                {mandatoryByRole[r] > 0 ? `−${mandatoryByRole[r]}` : '—'}
              </td>
            ))}
            <td style={{ ...cellStyle, color: DARK_THEME.textHint }}>{mandTotal > 0 ? `−${mandTotal}` : '—'}</td>
          </tr>
          <tr style={{ borderTop: `1px solid ${DARK_THEME.border}` }}>
            <td style={{ ...labelStyle, color: DARK_THEME.cyanPrimary, fontWeight: 600 }}>= Доступно</td>
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, color: DARK_THEME.cyanPrimary, fontWeight: 600 }}>
                {Math.round(summary.available_for_backlog_by_role[r] ?? 0)}
              </td>
            ))}
            <td style={{ ...cellStyle, color: DARK_THEME.cyanPrimary, fontWeight: 700 }}>{availTotal}</td>
          </tr>
          <tr>
            <td style={{ ...labelStyle, fontSize: 10 }} />
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>
                {(summary.role_employee_names[r] ?? []).length} чел.
              </td>
            ))}
            <td />
          </tr>
        </tbody>
      </table>

      {summary.absence_days_by_employee.length > 0 && (
        <div style={{ marginTop: 10, borderTop: `1px solid ${DARK_THEME.border}`, paddingTop: 8 }}>
          <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Отпуска по сотрудникам
          </div>
          {summary.absence_days_by_employee.map((emp) => (
            <div key={emp.employee_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 3 }}>
              <span>{emp.display_name}</span>
              <span style={{ fontFamily: FONTS.mono }}>
                {emp.role ? emp.role.slice(0, 2).toUpperCase() : '—'} · {emp.days} дн
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

NOTE: `WorkTypeRow` in `api.ts` needs a `subtracts_from_pool` field. Add it in Task 3 (or as a follow-up step here):

In `frontend/src/types/api.ts`, find the `WorkTypeRow` interface and add the field:
```typescript
export interface WorkTypeRow {
  work_type_id: string;
  work_type_label: string;
  by_role: Record<string, number>;
  by_role_pct: Record<string, number | null>;
  total: number;
  subtracts_from_pool: boolean;
}
```

NOTE: `WorkTypeRowOut` in `planning.py` (~line 148-158) already has `subtracts_from_pool: bool` and the endpoint maps `row.subtracts_from_pool` (~line 676). `WorkTypeRow` in `frontend/src/types/api.ts` also already has `subtracts_from_pool: boolean`. No changes needed for this field.

- [ ] **Step 6: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: no errors. Fix any type mismatches found.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx frontend/src/types/api.ts
git commit -m "feat(planning): expandable resource breakdown in PlanningCapacityPanel + gauge all roles (С-4 frontend)"
```

---

## Task 8: Б-1 + Б-3 — BacklogPage: add Исполнитель/Заказчик, remove Risk, add Всего часов + %

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`

These are bundled together since they all modify `baseColumns()`.

- [ ] **Step 1: Add `useEmployees` and `useRoles` imports**

In `BacklogPage.tsx`, add to existing imports:

```typescript
import { useEmployees } from '../hooks/useCapacity';
import { useRoles } from '../hooks/useRoles';
import { getRoleColor } from '../utils/roles';
import { OPO_COLOR } from '../utils/opo';
```

(`useEmployees` lives in `useCapacity.ts` — it wraps `getEmployees()` with TanStack Query.)

- [ ] **Step 2: Call employee/role hooks in `BacklogPage` component**

Inside `BacklogPage()`, add after the existing hook calls:

```typescript
  const { data: employees = [] } = useEmployees();
  const { data: roles = [] } = useRoles();
  const activeEmployees = useMemo(
    () => employees.filter((e) => e.is_active),
    [employees],
  );
```

- [ ] **Step 3: Compute total hours denominator for % ресурса**

```typescript
  const totalHoursAll = useMemo(
    () => (activeRows ?? []).reduce((sum, r) => {
      const an = r.estimate_analyst_hours ?? 0;
      const de = r.estimate_dev_hours ?? 0;
      const qa = r.estimate_qa_hours ?? 0;
      const op = r.estimate_opo_hours ?? 0;
      return sum + (r.estimate_hours ?? an + de + qa + op);
    }, 0),
    [activeRows],
  );
```

- [ ] **Step 4: Remove `renderRoleEstimate` helper and `renderImpactRisk` for Risk**

The existing `renderRoleEstimate` returns either a plain `<span>` (read-only) or `<InputNumber>`. We will replace role columns with colored `BacklogRoleCell` + `Popover` in Task 9. For now keep the helper but note we'll replace columns.

For Risk removal: remove the Risk column from `baseColumns()`. Find in `baseColumns`:
```typescript
    { title: 'Risk', dataIndex: 'risk', width: 110,
      render: renderImpactRisk('risk', editable) },
```
Delete this entry.

- [ ] **Step 5: Add «Всего часов» column to `baseColumns()`**

After the ОПЭ→АН column and before Impact, add:

```typescript
    {
      title: 'Всего часов',
      key: 'total_hours',
      width: 90,
      align: 'right' as const,
      render: (_: unknown, r: BacklogItemResponse) => {
        const an = r.estimate_analyst_hours ?? 0;
        const de = r.estimate_dev_hours ?? 0;
        const qa = r.estimate_qa_hours ?? 0;
        const op = r.estimate_opo_hours ?? 0;
        const total = r.estimate_hours ?? an + de + qa + op;
        const pct = totalHoursAll > 0 ? Math.round((total / totalHoursAll) * 100) : 0;
        return (
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontFamily: 'monospace', fontSize: 14, fontWeight: 700, color: '#e8f4f8' }}>
              {Math.round(total)} ч
            </span>
            {totalHoursAll > 0 && (
              <div style={{ fontSize: 10, color: '#4a6a80', marginTop: 1 }}>
                {pct}% ресурса
              </div>
            )}
          </div>
        );
      },
    },
```

NOTE: `totalHoursAll` is computed in the component body; `baseColumns` is a function called inside the component so it closes over `totalHoursAll`. Verify this pattern works by checking how `renderRoleEstimate` closes over `patch`.

- [ ] **Step 6: Add Исполнитель column to `baseColumns()`**

After the Статус column, insert:

```typescript
    {
      title: 'Исполнитель',
      key: 'assignee',
      width: 140,
      render: (_: unknown, r: BacklogItemResponse) => {
        if (r.issue_id) {
          return <span style={{ fontSize: 12, color: '#8faec8' }}>{r.assignee_display_name ?? '—'}</span>;
        }
        return (
          <Select
            size="small"
            allowClear
            variant="borderless"
            value={r.assignee_employee_id ?? undefined}
            style={{ width: '100%', fontSize: 12 }}
            options={activeEmployees.map((e) => ({ label: e.display_name, value: e.id }))}
            onChange={(val) => patch(r.id, { assignee_employee_id: val ?? null } as Parameters<typeof update.mutate>[0]['data'])}
          />
        );
      },
    },
```

- [ ] **Step 7: Add Заказчик column to `baseColumns()`**

After Исполнитель:

```typescript
    {
      title: 'Заказчик',
      key: 'customer',
      width: 120,
      render: (_: unknown, r: BacklogItemResponse) => {
        if (r.issue_id) {
          return <span style={{ fontSize: 12, color: '#6b8fa8' }}>{r.customer ?? '—'}</span>;
        }
        return (
          <input
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: '1px dashed #1e3a5f',
              color: '#8faec8',
              fontSize: 12,
              padding: '2px 4px',
              width: '100%',
              outline: 'none',
            }}
            defaultValue={r.customer ?? ''}
            placeholder="Заказчик…"
            onBlur={(e) => {
              const next = e.target.value.trim() || null;
              if (next !== (r.customer ?? null)) {
                patch(r.id, { customer: next } as Parameters<typeof update.mutate>[0]['data']);
              }
            }}
          />
        );
      },
    },
```

- [ ] **Step 8: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Fix any type errors (especially `assignee_employee_id` / `customer` in PATCH payload type).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx
git commit -m "feat(backlog): add Исполнитель + Заказчик cols, remove Risk, add Всего часов + % (Б-1 Б-3)"
```

---

## Task 9: Б-2 — BacklogPage colored role cells + Popover

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`

- [ ] **Step 1: Add `BacklogRoleCell` and `Popover` imports**

```typescript
import BacklogRoleCell from '../components/planning/BacklogRoleCell';
import { Popover } from 'antd';
```

(Add `Popover` to existing antd import line.)

- [ ] **Step 2: Replace АН/ПР/ТС/ОПЭ columns in `baseColumns()` with colored cells**

Remove the four existing plain columns:
```typescript
    { title: 'АН ч', dataIndex: 'estimate_analyst_hours', width: 80, ... },
    { title: 'ПР ч', dataIndex: 'estimate_dev_hours', width: 80, ... },
    { title: 'ТС ч', dataIndex: 'estimate_qa_hours', width: 80, ... },
    { title: 'ОПЭ ч', dataIndex: 'estimate_opo_hours', width: 80, ... },
```

Replace all four with a single combined column:

```typescript
    {
      title: 'АН / ПР / ТС / ОПЭ',
      key: 'roles',
      width: 280,
      render: (_: unknown, r: BacklogItemResponse) => {
        const an = r.estimate_analyst_hours ?? 0;
        const de = r.estimate_dev_hours ?? 0;
        const qa = r.estimate_qa_hours ?? 0;
        const op = r.estimate_opo_hours ?? 0;
        const total = r.estimate_hours ?? an + de + qa + op;
        const isEditable = !r.issue_id;

        const makeCell = (
          label: string,
          hours: number,
          field: 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours',
          color: string,
        ) => {
          const cell = <BacklogRoleCell label={label} hours={hours} total={total} color={color} />;
          if (!isEditable) return cell;
          return (
            <Popover
              key={field}
              trigger="click"
              content={
                <InputNumber
                  autoFocus
                  min={0}
                  defaultValue={hours || undefined}
                  size="small"
                  style={{ width: 100 }}
                  onBlur={(e) => {
                    const raw = e.currentTarget.value.trim();
                    const next = raw === '' ? null : Number(raw);
                    if (next !== hours) {
                      patch(r.id, { [field]: next } as Parameters<typeof update.mutate>[0]['data']);
                    }
                  }}
                  onPressEnter={(e) => {
                    const raw = (e.target as HTMLInputElement).value.trim();
                    const next = raw === '' ? null : Number(raw);
                    if (next !== hours) {
                      patch(r.id, { [field]: next } as Parameters<typeof update.mutate>[0]['data']);
                    }
                  }}
                />
              }
            >
              <span style={{ cursor: 'pointer' }}>{cell}</span>
            </Popover>
          );
        };

        return (
          <div style={{ display: 'flex', gap: 4 }}>
            {makeCell('АН', an, 'estimate_analyst_hours', getRoleColor(roles, 'analyst'))}
            {makeCell('ПР', de, 'estimate_dev_hours', getRoleColor(roles, 'dev'))}
            {makeCell('ТС', qa, 'estimate_qa_hours', getRoleColor(roles, 'qa'))}
            {makeCell('ОПЭ', op, 'estimate_opo_hours', OPO_COLOR)}
          </div>
        );
      },
    },
```

Also remove the `ОПЭ→АН` column (Б-3 cleanup — this ratio column is not in the spec's target design):

Actually, per spec only `Risk` is removed. Keep `ОПЭ→АН`. Remove the four individual role columns and replace with one combined.

- [ ] **Step 3: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx
git commit -m "feat(backlog): colored BacklogRoleCell + Popover editor for manual items (Б-2)"
```

---

## Task 10: Push and verify

- [ ] **Step 1: Run full frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: 0 errors.

- [ ] **Step 2: Run backend tests**

```bash
py -3.10 -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: same or better pass rate vs pre-existing.

- [ ] **Step 3: Push to origin**

```bash
git push origin main
```

---

## Self-Review

### Spec coverage check

| Spec item | Task |
|---|---|
| С-2: fix `knownRole` | Task 4 |
| С-5: fix `compute_summary()` available_by_role | Task 1 |
| С-4 backend: `calendar_gross_by_role` + `absence_days_by_employee` | Task 2 |
| С-4 API schema | Task 2 step 5-6 |
| С-4 frontend types | Task 3 + Task 7 step 5 |
| С-1: font size, role color borders, work type truncation | Task 5 |
| С-3: remove Risk, rename Всего часов + %, lift summary | Task 6 |
| С-4 frontend: Collapse + breakdown table + gauge fix | Task 7 |
| Б-1: Исполнитель + Заказчик columns | Task 8 |
| Б-2: colored cells + Popover | Task 9 |
| Б-3: remove Risk, Всего часов + % | Task 8 |

All 9 spec items covered. ✓

### Type consistency check
- `ResourceSummaryOut` gets `calendar_gross_by_role` and `absence_days_by_employee` added in both backend (Task 2) and frontend types (Task 3). ✓
- `WorkTypeRow` needs `subtracts_from_pool: boolean` — noted in Task 7 step 5 with a check. ✓
- `ResourceBreakdownTable` uses `summary.calendar_gross_by_role`, `summary.total_by_role`, `summary.available_for_backlog_by_role`, `summary.available_for_backlog_total` — all already in `ResourceSummaryOut`. ✓
- `PlanningCapacityPanel` receives `summary: ResourceSummaryOut | undefined` — matches Task 6 which passes `resourceSummary` (type `ResourceSummaryOut | undefined`). ✓
- `BacklogPage`: `patch()` uses `Parameters<typeof update.mutate>[0]['data']` — need to verify `assignee_employee_id` and `customer` are in the PATCH payload type. If not, add them in `BacklogItemUpdateRequest` in `api.ts`. Check before coding Task 8.

### Placeholder scan
- Task 7 step 5 references `row.subtracts_from_pool` on `WorkTypeRow` — flagged as needing a type check in the same step. ✓
- Task 8 step 1: `useEmployees` is exported from `frontend/src/hooks/useCapacity.ts` (line 28). Import: `import { useEmployees } from '../hooks/useCapacity';`. ✓
