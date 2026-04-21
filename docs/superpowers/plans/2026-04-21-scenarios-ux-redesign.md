# Scenarios UX Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Scenarios page with: (1) fix bar/input overflow bugs, (2) new "Правила" tab with copy-from-quarter, (3) full-width resource summary table above allocations.

**Architecture:** Three independent slices — CSS fixes touch only two components; backend adds two new endpoints (`resource-summary`, `copy-rules-from-template`) plus a `compute_summary()` method in `ResourceBaseService`; frontend adds types, hooks, one new component (`ScenarioResourceSummary`), updates `ScenarioRulesEditor` (remove Collapse, add copy), and `PlanningPage` (add Tabs, wire summary).

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 (backend); React 19 / TypeScript / Ant Design 6 / TanStack Query (frontend).

---

## File Map

**Modified:**
- `frontend/src/components/planning/RoleCapacityBar.tsx` — overflow fix
- `frontend/src/components/planning/ExternalQaInput.tsx` — layout fix
- `app/services/resource_base_service.py` — add `WorkTypeSummaryRow`, `ResourceSummary` dataclasses + `compute_summary()`
- `app/api/endpoints/planning.py` — add `WorkTypeRowOut`, `ResourceSummaryOut` schemas + two endpoints
- `frontend/src/types/api.ts` — add `WorkTypeRow`, `ResourceSummaryOut` types
- `frontend/src/hooks/usePlanning.ts` — add `useScenarioResourceSummary`, `useCopyRulesFromTemplate`
- `frontend/src/components/planning/ScenarioRulesEditor.tsx` — remove Collapse wrapper, add "Копировать из квартала"
- `frontend/src/pages/PlanningPage.tsx` — add Tabs + `ScenarioResourceSummary` block

**Created:**
- `frontend/src/components/planning/ScenarioResourceSummary.tsx`
- `tests/test_api_planning_summary.py`

---

## Task 1: Fix RoleCapacityBar overflow

**Files:**
- Modify: `frontend/src/components/planning/RoleCapacityBar.tsx`

The bar container has `overflow: 'visible'` — the amber overflow segment extends outside the card. Fix: set `overflow: 'hidden'`, fill bar goes full amber when over, remove the separate overflow segment div.

- [ ] **Step 1: Open `RoleCapacityBar.tsx`, locate the bar container div (~line 55)**

```tsx
// BEFORE — the container
<div
  style={{
    position: 'relative',
    height: 10,
    background: DARK_THEME.darkAccent,
    borderRadius: 5,
    overflow: 'visible',  // <-- causes bleed
  }}
>
  <div style={{ ..., width: `${fillPct}%`, background: roleColor, ... }} />
  {over && (
    <div style={{ position: 'absolute', left: '100%', ... }} />  // <-- bleeds
  )}
  {/* 100% marker */}
  <div style={{ position: 'absolute', left: '100%', ... }} />
</div>
```

- [ ] **Step 2: Replace the entire bar container block**

```tsx
      <div
        style={{
          position: 'relative',
          height: 10,
          background: DARK_THEME.darkAccent,
          borderRadius: 5,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${fillPct}%`,
            background: over ? DARK_THEME.amber : roleColor,
            borderRadius: 5,
            transition: 'width .2s',
          }}
        />
        {/* 100% marker — stays at right inner edge, visible via overflow:hidden boundary */}
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: -2,
            bottom: -2,
            width: 2,
            background: DARK_THEME.textSecondary,
          }}
        />
      </div>
```

- [ ] **Step 3: Verify visually**

Start frontend dev server (`cd frontend && npm run dev`). Open `/planning`, select a scenario where analyst is overloaded. Confirm the amber bar stops at the card boundary and the "перегруз +N ч" text still appears below the bar.

- [ ] **Step 4: Also verify тестировщик row when capacity=0**

Set external QA hours to blank (capacity=0 for тестировщик). The bar should show full amber bar clipped inside the card, not bleeding out.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/RoleCapacityBar.tsx
git commit -m "fix(planning): clip role capacity bar overflow within card bounds"
```

---

## Task 2: Fix ExternalQaInput layout overflow

**Files:**
- Modify: `frontend/src/components/planning/ExternalQaInput.tsx`

The `Form.Item` renders label + input horizontally. The long label "Часы тестировщика (внешний ресурс) на квартал" pushes the input outside the 460px right panel card. Fix: stack label above input with `Form layout="vertical"`.

- [ ] **Step 1: Replace the return in `ExternalQaInput.tsx`**

```tsx
  return (
    <Form layout="vertical">
      <Form.Item
        label="Часы тестировщика (внешний ресурс) на квартал"
        tooltip="Если тестирование отдаётся внешнему исполнителю, задайте число часов. При пустом значении используются часы штатных QA."
        style={{ margin: 0 }}
      >
        <InputNumber
          value={draft ?? undefined}
          onChange={(v) => setDraft(typeof v === 'number' ? v : null)}
          onBlur={handleBlur}
          min={0}
          step={10}
          precision={0}
          placeholder="не задано"
          disabled={disabled || update.isPending}
          style={{ width: '100%' }}
          addonAfter="ч"
        />
      </Form.Item>
    </Form>
  );
```

Add `Form` to the `antd` import at top of file.

- [ ] **Step 2: Verify**

In browser, the card containing the input should now show label on one line above the full-width number input. No horizontal overflow.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/planning/ExternalQaInput.tsx
git commit -m "fix(planning): stack external QA hours label above input to prevent overflow"
```

---

## Task 3: Add ResourceSummary dataclasses + compute_summary() to ResourceBaseService

**Files:**
- Modify: `app/services/resource_base_service.py`

- [ ] **Step 1: Add dataclasses after existing `ResourceBase` dataclass (around line 50)**

```python
ROLE_PREFERRED_ORDER = ['analyst', 'dev', 'qa', 'consultant', 'project_manager']


@dataclass
class WorkTypeSummaryRow:
    """Строка разбивки по одному виду обязательных работ."""

    work_type_id: str
    work_type_label: str
    hours_by_role: dict[str, float]           # role_code -> часы (0 если нет правила)
    pct_by_role: dict[str, Optional[float]]   # role_code -> % (None если нет правила)
    total_hours: float


@dataclass
class ResourceSummary:
    """Сводная разбивка ресурса команды по видам обязательных работ и ролям."""

    year: int
    quarter: int
    team: str
    roles: list[str]                           # упорядоченные коды ролей в команде
    role_employee_names: dict[str, list[str]]  # role_code -> отсортированные имена
    gross_by_role: dict[str, float]            # норма-часы до вычета обязательных
    gross_total: float
    work_type_rows: list[WorkTypeSummaryRow]   # только subtracts_from_pool=True
    available_by_role: dict[str, float]        # после вычета обязательных
    available_total: float
    external_qa_hours: Optional[float]
```

- [ ] **Step 2: Add `compute_summary()` method to `ResourceBaseService` class (after existing `compute()` method)**

```python
    def compute_summary(self, scenario: PlanningScenario) -> ResourceSummary:
        """Сводная разбивка: норма-часы → обязательные работы → на бэклог, по ролям."""
        year = scenario.year
        q = int(str(scenario.quarter).replace("Q", ""))
        team = scenario.team
        months = self.QUARTER_MONTHS[q]
        period_start = date(year, months[0], 1)
        last_m = months[-1]
        next_year = year + 1 if last_m == 12 else year
        next_month = 1 if last_m == 12 else last_m + 1
        period_end = date(next_year, next_month, 1)

        # --- сотрудники команды ---
        emp_ids = [
            r[0]
            for r in self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == team)
            .all()
        ]
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        )

        # --- производственный календарь ---
        cal_overrides: dict[date, float] = {
            row.date: float(row.hours)
            for row in self.db.query(ProductionCalendarDay).filter(
                ProductionCalendarDay.date >= period_start,
                ProductionCalendarDay.date < period_end,
            ).all()
        }

        def day_hours(d: date) -> float:
            if d in cal_overrides:
                return cal_overrides[d]
            return DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0

        # --- виды обязательных работ (subtracts_from_pool=True) ---
        work_types = (
            self.db.query(MandatoryWorkType)
            .filter(
                MandatoryWorkType.subtracts_from_pool == True,  # noqa: E712
                MandatoryWorkType.is_active == True,            # noqa: E712
            )
            .order_by(MandatoryWorkType.sort_order.asc().nullsfirst())  # если поля нет — заменить на .order_by(MandatoryWorkType.label)
            .all()
        )
        wt_ids = {wt.id for wt in work_types}

        # --- правила сценария для этих видов работ ---
        rules: list[ScenarioRule] = []
        if wt_ids:
            rules = (
                self.db.query(ScenarioRule)
                .filter(
                    ScenarioRule.scenario_id == scenario.id,
                    ScenarioRule.work_type_id.in_(wt_ids),
                )
                .all()
            )

        # Словарь: (work_type_id, role_or_None) -> pct
        rule_lookup: dict[tuple[str, Optional[str]], float] = {}
        for r in rules:
            key = (r.work_type_id, r.role)
            rule_lookup[key] = rule_lookup.get(key, 0.0) + r.percent_of_norm

        def wt_pct_for_role(wt_id: str, role: Optional[str]) -> Optional[float]:
            if role and (wt_id, role) in rule_lookup:
                return rule_lookup[(wt_id, role)]
            if (wt_id, None) in rule_lookup:
                return rule_lookup[(wt_id, None)]
            return None

        # --- валовые часы по сотрудникам (без вычета обязательных) ---
        gross_by_emp: dict[str, float] = {}
        emp_role: dict[str, Optional[str]] = {}
        emp_name: dict[str, str] = {}

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
            total = 0.0
            cur = period_start
            while cur < period_end:
                norm = day_hours(cur)
                if norm > 0:
                    on_absence = any(a.start_date <= cur <= a.end_date for a in abs_ranges)
                    if not on_absence:
                        total += norm
                cur += timedelta(days=1)

            gross_by_emp[e.id] = round(total, 2)
            emp_role[e.id] = e.role
            emp_name[e.id] = e.display_name

        # --- агрегация по ролям ---
        role_employee_names: dict[str, list[str]] = {}
        gross_by_role: dict[str, float] = {}
        for emp_id, gross in gross_by_emp.items():
            role = emp_role[emp_id]
            if role:
                gross_by_role[role] = gross_by_role.get(role, 0.0) + gross
                role_employee_names.setdefault(role, []).append(emp_name[emp_id])

        for names in role_employee_names.values():
            names.sort()

        # Упорядочиваем роли по предпочтительному порядку
        roles_ordered = sorted(
            gross_by_role.keys(),
            key=lambda r: (
                ROLE_PREFERRED_ORDER.index(r)
                if r in ROLE_PREFERRED_ORDER
                else len(ROLE_PREFERRED_ORDER)
            ),
        )

        # --- строки по видам работ ---
        wt_rows: list[WorkTypeSummaryRow] = []
        for wt in work_types:
            hours_by_role: dict[str, float] = {}
            pct_by_role: dict[str, Optional[float]] = {}
            total_wt = 0.0
            for role in roles_ordered:
                pct = wt_pct_for_role(wt.id, role)
                pct_by_role[role] = pct
                h = round(gross_by_role.get(role, 0.0) * (pct or 0.0) / 100.0, 2)
                hours_by_role[role] = h
                total_wt += h
            wt_rows.append(
                WorkTypeSummaryRow(
                    work_type_id=wt.id,
                    work_type_label=wt.label,
                    hours_by_role=hours_by_role,
                    pct_by_role=pct_by_role,
                    total_hours=round(total_wt, 2),
                )
            )

        # --- доступные часы = валовые − обязательные ---
        available_by_role: dict[str, float] = {}
        for role in roles_ordered:
            gross = gross_by_role.get(role, 0.0)
            mandatory_total = sum(row.hours_by_role.get(role, 0.0) for row in wt_rows)
            available_by_role[role] = round(max(0.0, gross - mandatory_total), 2)

        # external_qa_hours переопределяет доступные часы для роли qa
        if scenario.external_qa_hours is not None:
            available_by_role["qa"] = scenario.external_qa_hours

        gross_total = round(sum(gross_by_role.values()), 2)
        available_total = round(sum(available_by_role.values()), 2)

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
        )
```

- [ ] **Step 3: Write failing test**

Create `tests/test_api_planning_summary.py`:

```python
"""Tests for /scenarios/{id}/resource-summary and copy-rules-from-template."""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ScenarioRule,
)

client = TestClient(app)
TEAM = "test-team-summary"


def _emp(db, role: str, name: str) -> Employee:
    e = Employee(
        id=str(uuid.uuid4()),
        display_name=name,
        email=f"{name.lower()}@test.com",
        role=role,
        is_active=True,
        hours_per_day=8.0,
    )
    db.add(e)
    db.add(EmployeeTeam(employee_id=e.id, team=TEAM, is_primary=True))
    return e


def _wt(db, label: str, code: str) -> MandatoryWorkType:
    wt = MandatoryWorkType(
        id=str(uuid.uuid4()),
        code=code,
        label=label,
        is_active=True,
        sort_order=1,
        subtracts_from_pool=True,
    )
    db.add(wt)
    return wt


def test_resource_summary_basic(db_session):
    e = _emp(db_session, "analyst", "Аналитик А")
    wt = _wt(db_session, "Орг. работы", "org")
    sc = PlanningScenario(
        id=str(uuid.uuid4()),
        name="Test",
        year=2026,
        quarter="Q2",
        status="draft",
        team=TEAM,
    )
    db_session.add(sc)
    db_session.flush()
    db_session.add(ScenarioRule(
        id=str(uuid.uuid4()),
        scenario_id=sc.id,
        role="analyst",
        work_type_id=wt.id,
        percent_of_norm=15.0,
    ))
    db_session.commit()

    resp = client.get(f"/api/v1/scenarios/{sc.id}/resource-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "analyst" in data["roles"]
    assert data["gross_by_role"]["analyst"] > 0
    wt_row = data["work_type_rows"][0]
    assert wt_row["work_type_label"] == "Орг. работы"
    assert wt_row["pct_by_role"]["analyst"] == 15.0
    # available = gross - 15%
    gross = data["gross_by_role"]["analyst"]
    expected_avail = round(max(0, gross - gross * 0.15), 2)
    assert abs(data["available_by_role"]["analyst"] - expected_avail) < 1.0
```

Run: `py -3.10 -m pytest tests/test_api_planning_summary.py::test_resource_summary_basic -v`

Expected: FAIL with 404 (endpoint doesn't exist yet).

- [ ] **Step 4: Commit service changes**

```bash
git add app/services/resource_base_service.py
git commit -m "feat(planning): add ResourceSummary dataclass + compute_summary() to ResourceBaseService"
```

---

## Task 4: Add GET /scenarios/{id}/resource-summary endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Test: `tests/test_api_planning_summary.py`

- [ ] **Step 1: Add Pydantic schemas in `planning.py` after `ResourceBaseOut`**

```python
class WorkTypeRowOut(BaseModel):
    work_type_id: str
    work_type_label: str
    hours_by_role: Dict[str, float]
    pct_by_role: Dict[str, Optional[float]]
    total_hours: float


class ResourceSummaryOut(BaseModel):
    year: int
    quarter: int
    team: str
    roles: List[str]
    role_employee_names: Dict[str, List[str]]
    gross_by_role: Dict[str, float]
    gross_total: float
    work_type_rows: List[WorkTypeRowOut]
    available_by_role: Dict[str, float]
    available_total: float
    external_qa_hours: Optional[float] = None
```

- [ ] **Step 2: Add the endpoint in `planning.py` right after `scenario_resource`**

```python
@router.get("/scenarios/{scenario_id}/resource-summary", response_model=ResourceSummaryOut)
async def scenario_resource_summary(
    scenario_id: str,
    db: Session = Depends(get_db),
):
    """Разбивка ресурса команды: норма-часы → обязательные работы → доступно на бэклог."""
    sc = db.get(PlanningScenario, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    if not sc.team:
        raise HTTPException(status_code=400, detail="Команда у сценария не выбрана")
    if not sc.year or not sc.quarter:
        raise HTTPException(status_code=400, detail="Год/квартал у сценария не заданы")

    summary = ResourceBaseService(db).compute_summary(sc)
    return ResourceSummaryOut(
        year=summary.year,
        quarter=summary.quarter,
        team=summary.team,
        roles=summary.roles,
        role_employee_names=summary.role_employee_names,
        gross_by_role=summary.gross_by_role,
        gross_total=summary.gross_total,
        work_type_rows=[
            WorkTypeRowOut(
                work_type_id=row.work_type_id,
                work_type_label=row.work_type_label,
                hours_by_role=row.hours_by_role,
                pct_by_role=row.pct_by_role,
                total_hours=row.total_hours,
            )
            for row in summary.work_type_rows
        ],
        available_by_role=summary.available_by_role,
        available_total=summary.available_total,
        external_qa_hours=summary.external_qa_hours,
    )
```

Also add `ResourceSummary` to the import from `resource_base_service`:
```python
from app.services.resource_base_service import ResourceBaseService
```
(No change needed — `ResourceSummary` is internal to the service; only `ResourceBaseService` is imported.)

- [ ] **Step 3: Run test**

```bash
py -3.10 -m pytest tests/test_api_planning_summary.py::test_resource_summary_basic -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_planning_summary.py
git commit -m "feat(planning): GET /scenarios/{id}/resource-summary endpoint"
```

---

## Task 5: Add POST /scenarios/{id}/copy-rules-from-template endpoint

**Files:**
- Modify: `app/api/endpoints/planning.py`
- Test: `tests/test_api_planning_summary.py`

- [ ] **Step 1: Write failing test (append to `test_api_planning_summary.py`)**

```python
def test_copy_rules_from_template(db_session):
    from app.models import RoleCapacityRule
    wt = _wt(db_session, "Орг. работы", "org2")
    sc = PlanningScenario(
        id=str(uuid.uuid4()),
        name="Copy test",
        year=2026,
        quarter="Q2",
        status="draft",
        team=TEAM,
    )
    db_session.add(sc)
    # Template rule for Q1
    rcr = RoleCapacityRule(
        id=str(uuid.uuid4()),
        year=2026,
        quarter=1,
        role="analyst",
        work_type_id=wt.id,
        percent_of_norm=20.0,
    )
    db_session.add(rcr)
    db_session.commit()

    resp = client.post(
        f"/api/v1/scenarios/{sc.id}/copy-rules-from-template?year=2026&quarter=1"
    )
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 1
    assert rules[0]["role"] == "analyst"
    assert rules[0]["percent_of_norm"] == 20.0
```

Run: `py -3.10 -m pytest tests/test_api_planning_summary.py::test_copy_rules_from_template -v`

Expected: FAIL (endpoint not found).

- [ ] **Step 2: Add endpoint to `planning.py` right after `replace_scenario_rules`**

```python
@router.post(
    "/scenarios/{scenario_id}/copy-rules-from-template",
    response_model=List[ScenarioRuleOut],
)
async def copy_rules_from_template(
    scenario_id: str,
    year: int = Query(..., description="Год шаблона"),
    quarter: int = Query(..., ge=1, le=4, description="Квартал шаблона"),
    db: Session = Depends(get_db),
):
    """Заменить правила сценария шаблонными правилами role_capacity_rules за год/квартал."""
    sc = db.get(PlanningScenario, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    _require_draft(sc)

    template_rules = (
        db.query(RoleCapacityRule)
        .filter(RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter)
        .all()
    )
    db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).delete()
    for rcr in template_rules:
        db.add(
            ScenarioRule(
                scenario_id=scenario_id,
                role=rcr.role,
                work_type_id=rcr.work_type_id,
                percent_of_norm=rcr.percent_of_norm,
            )
        )
    db.commit()
    return db.query(ScenarioRule).filter(ScenarioRule.scenario_id == scenario_id).all()
```

- [ ] **Step 3: Run both tests**

```bash
py -3.10 -m pytest tests/test_api_planning_summary.py -v
```

Expected: both PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/planning.py tests/test_api_planning_summary.py
git commit -m "feat(planning): POST /scenarios/{id}/copy-rules-from-template"
```

---

## Task 6: Add TypeScript types for ResourceSummaryOut

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Find where `ResourceBase` type is defined in `api.ts`, add after it**

```typescript
export interface WorkTypeRow {
  work_type_id: string;
  work_type_label: string;
  hours_by_role: Record<string, number>;
  pct_by_role: Record<string, number | null>;
  total_hours: number;
}

export interface ResourceSummaryOut {
  year: number;
  quarter: number;
  team: string;
  roles: string[];
  role_employee_names: Record<string, string[]>;
  gross_by_role: Record<string, number>;
  gross_total: number;
  work_type_rows: WorkTypeRow[];
  available_by_role: Record<string, number>;
  available_total: number;
  external_qa_hours: number | null;
}
```

- [ ] **Step 2: Run TS check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(planning): add ResourceSummaryOut + WorkTypeRow TypeScript types"
```

---

## Task 7: Add hooks — useScenarioResourceSummary + useCopyRulesFromTemplate

**Files:**
- Modify: `frontend/src/hooks/usePlanning.ts`

- [ ] **Step 1: Find where `useScenarioResource` is defined in `usePlanning.ts`, add the two new hooks after it**

```typescript
export function useScenarioResourceSummary(
  scenarioId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: ['scenario-resource-summary', scenarioId],
    queryFn: () =>
      api.get<ResourceSummaryOut>(`/scenarios/${scenarioId}/resource-summary`),
    enabled: enabled && !!scenarioId,
    staleTime: 30_000,
  });
}

export function useCopyRulesFromTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scenarioId,
      year,
      quarter,
    }: {
      scenarioId: string;
      year: number;
      quarter: number;
    }) =>
      api.post(
        `/scenarios/${scenarioId}/copy-rules-from-template?year=${year}&quarter=${quarter}`,
        {},
      ),
    onSuccess: (_data, { scenarioId }) => {
      qc.invalidateQueries({ queryKey: ['scenario-rules', scenarioId] });
    },
  });
}
```

Add `ResourceSummaryOut` to the import from `'../types/api'`.

- [ ] **Step 2: Run TS check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePlanning.ts
git commit -m "feat(planning): add useScenarioResourceSummary + useCopyRulesFromTemplate hooks"
```

---

## Task 8: Create ScenarioResourceSummary component

**Files:**
- Create: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

This is the full-width table that goes above the tabs. Columns = roles (full names via `useRoles()`), rows = Всего, each work type (with %), На бэклог. Role headers have AntD Tooltip showing employee names.

- [ ] **Step 1: Create the file**

```tsx
import { Card, Skeleton, Tooltip } from 'antd';
import { useScenarioResourceSummary } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel } from '../../utils/roles';
import { DARK_THEME, FONTS } from '../../utils/constants';

interface Props {
  scenarioId: string;
  enabled: boolean;
}

const CELL: React.CSSProperties = {
  padding: '7px 10px',
  textAlign: 'right' as const,
  fontFamily: FONTS.mono,
  fontSize: 12,
};

const CELL_LABEL: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 12,
  color: DARK_THEME.textMuted,
};

export default function ScenarioResourceSummary({ scenarioId, enabled }: Props) {
  const { data: summary, isLoading } = useScenarioResourceSummary(scenarioId, enabled);
  const { data: roles = [] } = useRoles();

  if (isLoading) {
    return (
      <Card styles={{ body: { padding: 14 } }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!summary || summary.roles.length === 0) return null;

  const gridCols = `180px repeat(${summary.roles.length}, 1fr) 90px`;

  const headerStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderRadius: '6px 6px 0 0',
    overflow: 'hidden',
  };

  const rowStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
  };

  return (
    <Card
      styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}
    >
      {/* Header row */}
      <div style={headerStyle}>
        <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }} />
        {summary.roles.map((role) => {
          const names = summary.role_employee_names[role] ?? [];
          const label = getRoleLabel(roles, role);
          return (
            <Tooltip
              key={role}
              title={
                names.length > 0 ? (
                  <div>
                    {names.map((n) => (
                      <div key={n}>{n}</div>
                    ))}
                  </div>
                ) : 'Нет сотрудников'
              }
            >
              <div
                style={{
                  ...CELL,
                  background: DARK_THEME.darkAccent,
                  textAlign: 'center',
                  color: DARK_THEME.textSecondary,
                  cursor: 'default',
                  borderBottom: `2px solid ${DARK_THEME.border}`,
                }}
              >
                <div style={{ fontWeight: 600 }}>{label}</div>
                <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 2 }}>
                  {names.length} чел. ⓘ
                </div>
              </div>
            </Tooltip>
          );
        })}
        <div
          style={{
            ...CELL,
            background: DARK_THEME.darkAccent,
            textAlign: 'center',
            color: DARK_THEME.textMuted,
            fontWeight: 600,
          }}
        >
          Итого
        </div>
      </div>

      {/* Всего норма-часов */}
      <div style={rowStyle}>
        <div style={{ ...CELL_LABEL, background: DARK_THEME.cardBg, fontWeight: 600, color: DARK_THEME.textPrimary }}>
          Всего норма-часов
        </div>
        {summary.roles.map((role) => (
          <div key={role} style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 600 }}>
            {Math.round(summary.gross_by_role[role] ?? 0).toLocaleString('ru')}
          </div>
        ))}
        <div style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 700, color: DARK_THEME.textPrimary }}>
          {Math.round(summary.gross_total).toLocaleString('ru')}
        </div>
      </div>

      {/* Обязательные работы */}
      {summary.work_type_rows.map((row) => (
        <div key={row.work_type_id} style={rowStyle}>
          <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }}>
            — {row.work_type_label}
          </div>
          {summary.roles.map((role) => {
            const h = row.hours_by_role[role] ?? 0;
            const pct = row.pct_by_role[role];
            return (
              <div key={role} style={{ ...CELL, background: DARK_THEME.darkAccent, color: DARK_THEME.textMuted }}>
                {h > 0 ? Math.round(h).toLocaleString('ru') : '—'}
                {pct != null && h > 0 && (
                  <span style={{ marginLeft: 4, fontSize: 10, color: DARK_THEME.textHint }}>
                    {pct}%
                  </span>
                )}
              </div>
            );
          })}
          <div style={{ ...CELL, background: DARK_THEME.darkAccent, color: DARK_THEME.textMuted }}>
            {Math.round(row.total_hours).toLocaleString('ru')}
          </div>
        </div>
      ))}

      {/* На бэклог */}
      <div style={{ ...rowStyle, borderTop: `2px solid ${DARK_THEME.cyanPrimary}` }}>
        <div
          style={{
            ...CELL_LABEL,
            background: 'rgba(0,201,200,0.08)',
            color: DARK_THEME.cyanPrimary,
            fontWeight: 700,
            borderLeft: `3px solid ${DARK_THEME.cyanPrimary}`,
          }}
        >
          На бэклог
        </div>
        {summary.roles.map((role) => {
          const avail = summary.available_by_role[role] ?? 0;
          const isExternal = role === 'qa' && summary.external_qa_hours != null;
          return (
            <div
              key={role}
              style={{
                ...CELL,
                background: 'rgba(0,201,200,0.08)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
              }}
            >
              {Math.round(avail).toLocaleString('ru')}
              {isExternal && (
                <div style={{ fontSize: 10, color: DARK_THEME.textHint, fontWeight: 400 }}>
                  внешний
                </div>
              )}
            </div>
          );
        })}
        <div
          style={{
            ...CELL,
            background: 'rgba(0,201,200,0.08)',
            color: DARK_THEME.cyanPrimary,
            fontWeight: 700,
          }}
        >
          {Math.round(summary.available_total).toLocaleString('ru')}
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Run TS check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): ScenarioResourceSummary component — full-width capacity breakdown table"
```

---

## Task 9: Update ScenarioRulesEditor — remove Collapse, add "Копировать из квартала"

**Files:**
- Modify: `frontend/src/components/planning/ScenarioRulesEditor.tsx`

Changes:
1. Remove the `Collapse` wrapper — render the table directly
2. Add `useCopyRulesFromTemplate` mutation
3. Add a "Копировать из квартала" button that opens an `AntD Popover` with Year + Quarter `Select`s

- [ ] **Step 1: Update imports at top of `ScenarioRulesEditor.tsx`**

```tsx
import { useEffect, useMemo, useState } from 'react';
import {
  App, Button, InputNumber, Popover, Select, Space, Table, Tooltip,
} from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { useScenarioRules, usePutScenarioRules, useCopyRulesFromTemplate } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { useMandatoryWorkTypes } from '../../hooks/useCapacity';
import type { ScenarioRuleInput } from '../../types/api';
```

- [ ] **Step 2: Add copy state and hook inside the component (after existing `put` declaration)**

```tsx
  const copy = useCopyRulesFromTemplate();
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyYear, setCopyYear] = useState<number>(new Date().getFullYear());
  const [copyQuarter, setCopyQuarter] = useState<number>(1);

  const handleCopy = () => {
    copy.mutate(
      { scenarioId, year: copyYear, quarter: copyQuarter },
      {
        onSuccess: () => {
          setCopyOpen(false);
          setDirty(false);
          notification.success({ title: `Правила скопированы из Q${copyQuarter} ${copyYear}` });
        },
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  const yearOptions = [2025, 2026, 2027].map((y) => ({ value: y, label: String(y) }));
  const quarterOptions = [1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }));

  const copyContent = (
    <Space direction="vertical" size={8} style={{ width: 200 }}>
      <Space>
        <Select
          size="small"
          value={copyYear}
          options={yearOptions}
          onChange={setCopyYear}
          style={{ width: 80 }}
        />
        <Select
          size="small"
          value={copyQuarter}
          options={quarterOptions}
          onChange={setCopyQuarter}
          style={{ width: 70 }}
        />
      </Space>
      <Button
        size="small"
        type="primary"
        block
        loading={copy.isPending}
        onClick={handleCopy}
      >
        Скопировать
      </Button>
    </Space>
  );
```

- [ ] **Step 3: Replace the `return` statement — remove `Collapse`, render table directly with copy button**

```tsx
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Table<RuleDraft>
        size="small"
        dataSource={drafts}
        rowKey="_key"
        columns={columns}
        pagination={false}
        locale={{ emptyText: 'Нет правил' }}
      />
      <Space>
        <Button size="small" icon={<PlusOutlined />} onClick={addRow}>
          Добавить правило
        </Button>
        <Popover
          open={copyOpen}
          onOpenChange={setCopyOpen}
          content={copyContent}
          title="Скопировать из шаблона квартала"
          trigger="click"
        >
          <Button size="small" icon={<CopyOutlined />}>
            Из квартала
          </Button>
        </Popover>
        <Tooltip title={hasDuplicates ? 'Есть дубликаты — исправьте перед сохранением' : undefined}>
          <Button
            size="small"
            type="primary"
            icon={<SaveOutlined />}
            disabled={saveDisabled}
            loading={put.isPending}
            onClick={handleSave}
          >
            Сохранить
          </Button>
        </Tooltip>
        {dirty && (
          <Button size="small" onClick={handleReset}>
            Сбросить
          </Button>
        )}
      </Space>
    </Space>
  );
```

Remove unused imports: `Collapse`, `Typography`.

- [ ] **Step 4: Run TS check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planning/ScenarioRulesEditor.tsx
git commit -m "feat(planning): ScenarioRulesEditor — remove Collapse wrapper, add copy-from-quarter"
```

---

## Task 10: Update PlanningPage — add Tabs + ScenarioResourceSummary

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

Changes:
1. Add `Tabs` to the left column: tab "Распределение" (existing allocations card) + tab "Правила" (`ScenarioRulesEditor`)
2. Remove `ScenarioRulesEditor` from the right column
3. Add `ScenarioResourceSummary` between the scenario header card and the two-column grid
4. Pass correct `enabled` prop to summary (only when team is selected)

- [ ] **Step 1: Update imports in `PlanningPage.tsx`**

Add `Tabs` to the antd import:
```tsx
import {
  Alert, App, Badge, Button, Card, Checkbox, Popconfirm, Select, Space, Tabs, Tag, Tooltip,
} from 'antd';
```

Add the new component import (the summary fetches its own data — no hook import needed in the page):
```tsx
import ScenarioResourceSummary from '../components/planning/ScenarioResourceSummary';
```

`ScenarioRulesEditor` import stays — it moves into the "Правила" tab children.

- [ ] **Step 2: Inside the `{scenarioId && scenario && !!scenario.team && (...)}` block, restructure the layout**

Find the current layout:
```tsx
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', ... }}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {/* header card */}
            <Card title="Элементы бэклога" ...>...</Card>
          </Space>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <PlanningCapacityPanel ... />
            <Card size="small"><ExternalQaInput ... /></Card>
            <ScenarioRulesEditor scenarioId={scenarioId} />
          </Space>
        </div>
```

Replace the outer `<div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px' ... }}>` with a `<Space direction="vertical">` wrapper. **The scenario header card JSX is unchanged — move it as-is.** The full replacement structure:

```tsx
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {/* === Scenario header card — copy here verbatim, no changes === */}

          {/* Full-width resource summary table */}
          <ScenarioResourceSummary scenarioId={scenarioId} enabled={!!scenario.team} />

          {/* Two-column grid: left = tabs, right = capacity panel */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) 460px',
              gap: 16,
              alignItems: 'start',
            }}
          >
            {/* Left column: Tabs */}
            <Tabs
              defaultActiveKey="distribution"
              items={[
                {
                  key: 'distribution',
                  label: 'Распределение',
                  children: (
                    <Card
                      title="Элементы бэклога"
                      styles={{ body: { padding: 0 } }}
                      loading={allocLoading}
                      extra={
                        <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                          {isApproved
                            ? 'сценарий утверждён — отметки заблокированы'
                            : 'клик по строке переключает включение'}
                        </span>
                      }
                    >
                      {/* === allocations header div and list div — copy here verbatim, no changes === */}
                    </Card>
                  ),
                },
                {
                  key: 'rules',
                  label: 'Правила',
                  children: (
                    <Card
                      title="Правила обязательных работ"
                      styles={{ body: { padding: 14 } }}
                      style={{ background: DARK_THEME.cardBg }}
                    >
                      <ScenarioRulesEditor scenarioId={scenarioId} />
                    </Card>
                  ),
                },
              ]}
            />

            {/* Right column: capacity panel + external QA */}
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
              />
              <Card size="small" styles={{ body: { padding: 12 } }}>
                <ExternalQaInput
                  scenarioId={scenarioId}
                  value={scenario.external_qa_hours}
                  disabled={!isDraft}
                />
              </Card>
            </Space>
          </div>
        </Space>
```

> **Note:** Keep the scenario header card content exactly as it was — just move it inside the new outer `Space`. The allocations table content is unchanged — move it as-is into the "Распределение" tab children.

- [ ] **Step 4: Remove the old `<ScenarioRulesEditor>` from the right column (it's now in the tab)**

The right `Space` should only contain `PlanningCapacityPanel` and `ExternalQaInput`.

- [ ] **Step 5: Run TS check + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: no errors.

- [ ] **Step 6: Verify in browser**

Start the dev server (`cd frontend && npm run dev`). Open `/planning`, select a scenario with a team:
- Confirm the "Сводка ресурсов" table appears above the tabs with role columns and work type rows
- Switch to "Правила" tab — the rules table appears, no Collapse, can add/remove rows, "Из квартала" button opens popover
- Switch back to "Распределение" — allocations table is intact
- Right panel: capacity bars and external QA input visible, no ScenarioRulesEditor

- [ ] **Step 7: Verify overflow fixes**

In the "Ресурс по ролям" block on the right: overloaded role bars (e.g. Аналитик) should stop at the card edge. External QA card: label is stacked above the input field.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): add tabs (Распределение/Правила) + ScenarioResourceSummary block"
```

---

## Post-implementation

- [ ] **Run full test suite**

```bash
py -3.10 -m pytest tests/ -v
cd frontend && npm run build
```

Expected: no new failures. Frontend build succeeds.

- [ ] **Push to origin**

```bash
git push origin main
```
