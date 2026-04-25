# Scenario xlsx export — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-sheet scenario xlsx export with a 7-sheet workbook (cover + included + excluded + by-role + by-employee + rules + absences), styled per `docs/superpowers/specs/2026-04-25-scenario-xlsx-export-design.md`.

**Architecture:** New module `app/services/scenario_xlsx_export.py` with `ScenarioXlsxExporter` class. `_load()` builds a single `ScenarioExportContext` dataclass (no N+1). One method per sheet, shared `_Style` helpers for fills/fonts/conditional formatting. `ExportService.build_scenario_xlsx` becomes a 1-line adapter that delegates.

**Tech Stack:** Python 3.10, SQLAlchemy 2.0 ORM, openpyxl 3.x (already a dependency), pytest.

---

## Pre-flight

- [ ] **Step 0.1: Read the spec.** Before writing any code, read `docs/superpowers/specs/2026-04-25-scenario-xlsx-export-design.md` end to end. Every layout question is answered there. Refer back when in doubt.

- [ ] **Step 0.2: Read existing code patterns.** Read these files to internalise the project's style:
  - `app/services/export_service.py:370-457` — `export_capacity_xlsx` (reference for openpyxl idioms in this project: grouping, fills, formulas).
  - `app/services/resource_base_service.py:1-260` — service interface used by the exporter (`compute`, `compute_summary`).
  - `tests/test_export_service.py:93-178` — `scenario_seed` fixture pattern (we'll extend it).
  - `app/models/__init__.py` — list of available model classes.

---

## Task 1: Scaffold module + load context

**Goal:** Create `scenario_xlsx_export.py` with the `ScenarioExportContext` dataclass, `_Style` constants, and `_load()` that fetches everything in one go. No sheet logic yet — just plumbing and a workbook with 7 named-but-empty sheets.

**Files:**
- Create: `app/services/scenario_xlsx_export.py`
- Test: `tests/test_scenario_xlsx_export.py`

- [ ] **Step 1.1: Create test file with smoke test.**

```python
# tests/test_scenario_xlsx_export.py
"""Tests for ScenarioXlsxExporter — 7-sheet beautiful scenario export."""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import (
    BacklogItem, Employee, EmployeeTeam, MandatoryWorkType,
    PlanningScenario, ScenarioAllocation, Role,
)
from app.services.scenario_xlsx_export import ScenarioXlsxExporter


EXPECTED_SHEETS = [
    "Обложка",
    "Включено",
    "Не вошло",
    "По ролям",
    "По сотрудникам",
    "Правила",
    "Отсутствия",
]


@pytest.fixture
def minimal_scenario(db_session):
    """Минимальный сценарий: команда, один сотрудник, одна задача."""
    db_session.add_all([
        Role(code="dev", label="Разработчик", color="#1890FF",
             is_active=True, counts_in_planning=True),
        MandatoryWorkType(code="org", label="Орг. вопросы",
                          is_active=True, subtracts_from_pool=True),
    ])
    db_session.flush()

    emp = Employee(
        jira_account_id="d1", display_name="Dave", role="dev", is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(
        employee_id=emp.id, team="Alpha", is_primary=True,
    ))

    item = BacklogItem(
        title="Build feature", priority=1,
        estimate_hours=80, estimate_dev_hours=80,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="Q2 2026 Alpha Base", year=2026, quarter="Q2",
        team="Alpha", status="draft",
    )
    db_session.add(scenario)
    db_session.flush()

    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id,
        included_flag=True, planned_hours=80.0,
    ))
    db_session.flush()

    class _R:
        pass
    r = _R()
    r.scenario_id = scenario.id
    return r


class TestScaffold:
    def test_workbook_has_seven_sheets_in_order(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == EXPECTED_SHEETS

    def test_unknown_scenario_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ScenarioXlsxExporter(db_session, "no-such-id").build()
```

- [ ] **Step 1.2: Run the test — expect ImportError.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py::TestScaffold -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.scenario_xlsx_export'`.

- [ ] **Step 1.3: Create the module skeleton.**

```python
# app/services/scenario_xlsx_export.py
"""7-sheet xlsx export for planning scenarios.

See docs/superpowers/specs/2026-04-25-scenario-xlsx-export-design.md
for layout, colours and contents of each sheet.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Absence, AbsenceReason, AppSetting, BacklogItem, Employee, EmployeeTeam,
    MandatoryWorkType, PlanningScenario, ProductionCalendarDay, Role,
    ScenarioAllocation, ScenarioRule,
)
from app.services.resource_base_service import (
    ResourceBaseService, ResourceBase, ResourceSummary,
)


SHEET_NAMES = [
    "Обложка",
    "Включено",
    "Не вошло",
    "По ролям",
    "По сотрудникам",
    "Правила",
    "Отсутствия",
]

QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


class _Style:
    """Centralised styling constants — colours, fonts, fills."""

    # Palette (from spec § "Стилистическая база")
    DARK_HEADER = "0F2340"
    CYAN_ACCENT = "00C9C8"
    GREEN_TEXT = "52C41A"
    GREEN_FILL = "F6FFED"
    YELLOW_TEXT = "FAAD14"
    YELLOW_FILL = "FFFBE6"
    ORANGE_FILL = "FFF7E6"
    RED_TEXT = "FF4D4F"
    RED_FILL = "FFF1F0"
    GREY_TEXT = "8C8C8C"
    GREY_FILL = "FAFAFA"
    CYAN_LIGHT = "F0F9FF"
    CYAN_MID = "BAE7FF"
    CYAN_DARK = "69C0FF"

    # Reusable fills
    HEADER_FILL = PatternFill("solid", fgColor=DARK_HEADER)
    GREEN_BG = PatternFill("solid", fgColor=GREEN_FILL)
    YELLOW_BG = PatternFill("solid", fgColor=YELLOW_FILL)
    RED_BG = PatternFill("solid", fgColor=RED_FILL)
    GREY_BG = PatternFill("solid", fgColor=GREY_FILL)
    ACCENT_BG = PatternFill("solid", fgColor=CYAN_ACCENT)
    CYAN_LIGHT_BG = PatternFill("solid", fgColor=CYAN_LIGHT)

    # Reusable fonts
    HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    METRIC_FONT = Font(name="Calibri", size=28, bold=True)
    METRIC_LABEL_FONT = Font(name="Calibri", size=10, color=GREY_TEXT)
    METRIC_HINT_FONT = Font(name="Calibri", size=9, color=GREY_TEXT)
    BOLD_FONT = Font(name="Calibri", size=11, bold=True)
    ITALIC_FONT = Font(name="Calibri", size=11, italic=True, color=GREY_TEXT)
    TITLE_FONT = Font(name="Calibri", size=24, bold=True, color="FFFFFF")
    BADGE_GREEN_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    BADGE_GREY_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    THIN_BORDER = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    CENTER = Alignment(horizontal="center", vertical="center", wrap_text=False)
    LEFT = Alignment(horizontal="left", vertical="center")
    RIGHT = Alignment(horizontal="right", vertical="center")


@dataclass
class ScenarioExportContext:
    """Single in-memory snapshot used across all 7 sheets."""

    scenario: PlanningScenario
    allocations: list[ScenarioAllocation]
    resource_summary: ResourceSummary
    resource_base: ResourceBase
    scenario_rules: list[ScenarioRule]
    work_types: list[MandatoryWorkType]
    employees: list[Employee]
    roles_by_code: dict[str, Role]
    absences: list[Absence]
    calendar_by_date: dict[date, float]
    jira_base_url: str
    generated_at: datetime
    period_start: date
    period_end: date  # exclusive


class ScenarioXlsxExporter:
    """Build a 7-sheet xlsx for a planning scenario.

    Public API:
        ScenarioXlsxExporter(db, scenario_id).build() -> bytes
    """

    def __init__(self, db: Session, scenario_id: str) -> None:
        self.db = db
        self.scenario_id = scenario_id

    def build(self) -> bytes:
        ctx = self._load()
        wb = Workbook()
        wb.remove(wb.active)
        for name in SHEET_NAMES:
            wb.create_sheet(name)

        self._sheet_cover(wb["Обложка"], ctx)
        self._sheet_included(wb["Включено"], ctx)
        self._sheet_excluded(wb["Не вошло"], ctx)
        self._sheet_by_role(wb["По ролям"], ctx)
        self._sheet_by_employee(wb["По сотрудникам"], ctx)
        self._sheet_rules(wb["Правила"], ctx)
        self._sheet_absences(wb["Отсутствия"], ctx)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # === Loading ===

    def _load(self) -> ScenarioExportContext:
        scenario = self.db.get(PlanningScenario, self.scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {self.scenario_id} not found")

        q = int(str(scenario.quarter or "Q1").replace("Q", ""))
        year = scenario.year or datetime.utcnow().year
        months = QUARTER_MONTHS[q]
        period_start = date(year, months[0], 1)
        last_m = months[-1]
        next_year = year + 1 if last_m == 12 else year
        next_month = 1 if last_m == 12 else last_m + 1
        period_end = date(next_year, next_month, 1)

        allocations = (
            self.db.query(ScenarioAllocation)
            .options(
                joinedload(ScenarioAllocation.backlog_item)
                    .joinedload(BacklogItem.issue),
                joinedload(ScenarioAllocation.backlog_item)
                    .joinedload(BacklogItem.project),
            )
            .filter(ScenarioAllocation.scenario_id == self.scenario_id)
            .all()
        )

        rb_service = ResourceBaseService(self.db)
        resource_base = rb_service.compute(scenario)
        resource_summary = rb_service.compute_summary(scenario)

        scenario_rules = (
            self.db.query(ScenarioRule)
            .filter(ScenarioRule.scenario_id == self.scenario_id)
            .all()
        )

        work_types = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active == True)  # noqa: E712
            .order_by(MandatoryWorkType.sort_order.asc())
            .all()
        )

        emp_ids = [
            r[0]
            for r in self.db.query(EmployeeTeam.employee_id)
                .filter(EmployeeTeam.team == scenario.team)
                .all()
        ]
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active == True)  # noqa: E712
            .all()
        ) if emp_ids else []

        roles_by_code = {r.code: r for r in self.db.query(Role).all()}

        absences = (
            self.db.query(Absence)
            .options(joinedload(Absence.reason))
            .filter(
                Absence.employee_id.in_(emp_ids) if emp_ids else False,
                Absence.start_date < period_end,
                Absence.end_date >= period_start,
            )
            .all()
        ) if emp_ids else []

        calendar_by_date = {
            row.date: float(row.hours)
            for row in self.db.query(ProductionCalendarDay).filter(
                ProductionCalendarDay.date >= period_start,
                ProductionCalendarDay.date < period_end,
            ).all()
        }

        base_url_setting = self.db.get(AppSetting, "jira_base_url")
        jira_base_url = (base_url_setting.value if base_url_setting else "") or ""

        return ScenarioExportContext(
            scenario=scenario,
            allocations=allocations,
            resource_summary=resource_summary,
            resource_base=resource_base,
            scenario_rules=scenario_rules,
            work_types=work_types,
            employees=employees,
            roles_by_code=roles_by_code,
            absences=absences,
            calendar_by_date=calendar_by_date,
            jira_base_url=jira_base_url,
            generated_at=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
        )

    # === Sheets — empty stubs, filled in subsequent tasks ===

    def _sheet_cover(self, ws, ctx): ...
    def _sheet_included(self, ws, ctx): ...
    def _sheet_excluded(self, ws, ctx): ...
    def _sheet_by_role(self, ws, ctx): ...
    def _sheet_by_employee(self, ws, ctx): ...
    def _sheet_rules(self, ws, ctx): ...
    def _sheet_absences(self, ws, ctx): ...
```

- [ ] **Step 1.4: Run the test — expect both pass.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py::TestScaffold -v
```
Expected: 2 passed.

- [ ] **Step 1.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scaffold 7-sheet scenario exporter (no content yet)"
```

---

## Task 2: Sheet «Включено» — included initiatives table

**Goal:** Render the full allocation table for `included_flag=True`. Establishes patterns for headers, autofilter, freeze, totals, conditional formatting — reused by other sheets.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_included`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestIncludedSheet`.

**Spec reference:** § "Лист 2: Инициативы — включено".

- [ ] **Step 2.1: Add the test.**

```python
# Append to tests/test_scenario_xlsx_export.py

INCLUDED_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик", "Тип затрат",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч", "ОПЭ → аналитик",
    "Итого, ч", "План, ч", "Коэф. вовлеч.", "Цели",
]


class TestIncludedSheet:
    def test_headers_and_one_row(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]

        header = [ws.cell(row=1, column=c).value for c in range(1, len(INCLUDED_HEADERS) + 1)]
        assert header == INCLUDED_HEADERS

        # Row 2: our single included BacklogItem "Build feature"
        assert ws.cell(row=2, column=2).value == "Build feature"
        assert ws.cell(row=2, column=3).value == 1   # priority
        assert ws.cell(row=2, column=7).value == pytest.approx(80.0)  # dev hours
        assert ws.cell(row=2, column=11).value == pytest.approx(80.0)  # total
        assert ws.cell(row=2, column=12).value == pytest.approx(80.0)  # planned

    def test_totals_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        # Last data row + 1 = totals row, label "Σ ИТОГО" in column A
        last = ws.max_row
        assert ws.cell(row=last, column=1).value == "Σ ИТОГО"
        assert ws.cell(row=last, column=11).value == pytest.approx(80.0)

    def test_autofilter_set(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        assert ws.auto_filter.ref is not None

    def test_freeze_top_row(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        assert ws.freeze_panes == "A2"
```

- [ ] **Step 2.2: Run the test — expect failure (`Σ ИТОГО` not present, headers empty).**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py::TestIncludedSheet -v
```
Expected: 4 fails (sheet is empty).

- [ ] **Step 2.3: Implement `_sheet_included` and a shared helper for the initiatives table.**

Add to `app/services/scenario_xlsx_export.py` (replace the `_sheet_included` stub):

```python
INITIATIVES_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик", "Тип затрат",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч", "ОПЭ → аналитик",
    "Итого, ч", "План, ч", "Коэф. вовлеч.", "Цели",
]
INITIATIVES_WIDTHS = [14, 60, 10, 24, 16, 12, 14, 10, 10, 14, 12, 12, 14, 30]


def _demand_by_role(item: BacklogItem) -> tuple[float, float, float]:
    """Hours by (analyst, dev, qa) accounting for ОПЭ split."""
    ea = item.estimate_analyst_hours or 0.0
    ed = item.estimate_dev_hours or 0.0
    eq = item.estimate_qa_hours or 0.0
    eo = item.estimate_opo_hours or 0.0
    r = item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
    return ea + eo * r, ed + eo * (1.0 - r), eq


def _initiative_row(alloc: ScenarioAllocation, ctx: ScenarioExportContext) -> list:
    item: BacklogItem = alloc.backlog_item
    issue = item.issue
    key = issue.key if issue else ""
    analyst, dev, qa = _demand_by_role(item)
    total = round(analyst + dev + qa, 1)
    goals = (issue.goals or "") if issue else ""
    return [
        key,
        item.title,
        item.priority,
        item.customer or "",
        item.cost_type or "",
        round(analyst, 1),
        round(dev, 1),
        round(qa, 1),
        round(item.estimate_opo_hours or 0.0, 1),
        item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5,
        total,
        round(alloc.planned_hours or 0.0, 1),
        alloc.involvement_coefficient,
        goals,
    ]
```

Then implement the sheet:

```python
def _sheet_included(self, ws, ctx: ScenarioExportContext) -> None:
    self._render_initiatives(ws, ctx, included=True)

def _sheet_excluded(self, ws, ctx: ScenarioExportContext) -> None:
    self._render_initiatives(ws, ctx, included=False)

def _render_initiatives(
    self, ws, ctx: ScenarioExportContext, *, included: bool,
) -> None:
    from openpyxl.formatting.rule import ColorScaleRule

    ws.sheet_view.showGridLines = False

    # Header
    for col_idx, h in enumerate(INITIATIVES_HEADERS, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[1].height = 28

    # Data rows
    rows = [a for a in ctx.allocations if bool(a.included_flag) == included]
    rows.sort(key=lambda a: (
        a.backlog_item.priority is None,
        a.backlog_item.priority if a.backlog_item.priority is not None else 0,
        a.backlog_item.title,
    ))
    for r_idx, alloc in enumerate(rows, start=2):
        values = _initiative_row(alloc, ctx)
        for c_idx, val in enumerate(values, start=1):
            c = ws.cell(row=r_idx, column=c_idx, value=val)
            if c_idx == 11:  # «Итого, ч» — bold + light-cyan
                c.font = _Style.BOLD_FONT
                c.fill = _Style.CYAN_LIGHT_BG
        # Jira hyperlink (col 1) if base_url configured
        key = values[0]
        if key and ctx.jira_base_url:
            link = f"{ctx.jira_base_url.rstrip('/')}/browse/{key}"
            ws.cell(row=r_idx, column=1).hyperlink = link
            ws.cell(row=r_idx, column=1).font = Font(
                name="Calibri", color="1890FF", underline="single",
            )
        # Strikethrough excluded sheet rows with grey fill
        if not included:
            for c_idx in range(1, len(INITIATIVES_HEADERS) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = _Style.GREY_BG

    # Totals row
    total_row_idx = len(rows) + 2
    ws.cell(row=total_row_idx, column=1, value="Σ ИТОГО").font = _Style.HEADER_FONT
    ws.cell(row=total_row_idx, column=1).fill = _Style.ACCENT_BG
    sum_cols = [6, 7, 8, 9, 11, 12]  # часы по ролям + итого + план
    for c_idx in sum_cols:
        col_letter = get_column_letter(c_idx)
        if rows:
            formula = f"=SUM({col_letter}2:{col_letter}{total_row_idx - 1})"
        else:
            formula = 0
        c = ws.cell(row=total_row_idx, column=c_idx, value=formula)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.ACCENT_BG

    # Heatmap on hours columns (6-9) — only if there are rows
    if rows:
        for c_idx in (6, 7, 8, 9):
            col = get_column_letter(c_idx)
            rng = f"{col}2:{col}{total_row_idx - 1}"
            ws.conditional_formatting.add(
                rng,
                ColorScaleRule(
                    start_type="min", start_color="F0F9FF",
                    end_type="max", end_color="00C9C8",
                ),
            )

    # Priority column (3) — colour by value
    if rows:
        from openpyxl.formatting.rule import CellIsRule
        rng = f"C2:C{total_row_idx - 1}"
        ws.conditional_formatting.add(
            rng,
            CellIsRule(operator="equal", formula=["1"],
                       font=Font(bold=True, color=_Style.RED_TEXT)),
        )
        ws.conditional_formatting.add(
            rng,
            CellIsRule(operator="equal", formula=["2"],
                       font=Font(bold=True, color=_Style.YELLOW_TEXT)),
        )

    # Column widths
    for c_idx, w in enumerate(INITIATIVES_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    # Autofilter + freeze
    ws.auto_filter.ref = f"A1:{get_column_letter(len(INITIATIVES_HEADERS))}{total_row_idx}"
    ws.freeze_panes = "A2"
```

- [ ] **Step 2.4: Run the tests — expect TestIncludedSheet to pass.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 6 passed.

- [ ] **Step 2.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario sheet «Включено» — full per-role table"
```

---

## Task 3: Sheet «Не вошло» — excluded initiatives

**Goal:** Same shape as «Включено», already rendered via `_render_initiatives(..., included=False)`. We need test coverage and a verification that excluded rows get grey background.

**Files:**
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestExcludedSheet` and extend the seed fixture with one excluded item.

- [ ] **Step 3.1: Extend `minimal_scenario` to include one `included_flag=False` item.**

Replace the fixture with this version:

```python
@pytest.fixture
def minimal_scenario(db_session):
    db_session.add_all([
        Role(code="dev", label="Разработчик", color="#1890FF",
             is_active=True, counts_in_planning=True),
        MandatoryWorkType(code="org", label="Орг. вопросы",
                          is_active=True, subtracts_from_pool=True),
    ])
    db_session.flush()

    emp = Employee(
        jira_account_id="d1", display_name="Dave", role="dev", is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(
        employee_id=emp.id, team="Alpha", is_primary=True,
    ))

    item_in = BacklogItem(
        title="Build feature", priority=1,
        estimate_hours=80, estimate_dev_hours=80,
    )
    item_out = BacklogItem(
        title="Skipped feature", priority=5,
        estimate_hours=200, estimate_dev_hours=200,
    )
    db_session.add_all([item_in, item_out])
    db_session.flush()

    scenario = PlanningScenario(
        name="Q2 2026 Alpha Base", year=2026, quarter="Q2",
        team="Alpha", status="draft",
    )
    db_session.add(scenario)
    db_session.flush()

    db_session.add_all([
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item_in.id,
            included_flag=True, planned_hours=80.0,
        ),
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item_out.id,
            included_flag=False, planned_hours=0.0,
        ),
    ])
    db_session.flush()

    class _R:
        pass
    r = _R()
    r.scenario_id = scenario.id
    return r
```

- [ ] **Step 3.2: Add `TestExcludedSheet`.**

```python
class TestExcludedSheet:
    def test_excluded_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        # Header row 1, data row 2
        assert ws.cell(row=2, column=2).value == "Skipped feature"
        # «Включено» must NOT contain it
        ws_in = wb["Включено"]
        in_titles = {ws_in.cell(row=i, column=2).value for i in range(2, ws_in.max_row + 1)}
        assert "Skipped feature" not in in_titles

    def test_excluded_rows_have_grey_fill(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        cell = ws.cell(row=2, column=2)
        # _Style.GREY_FILL = "FAFAFA"
        assert cell.fill.fgColor.value.upper().endswith("FAFAFA")
```

- [ ] **Step 3.3: Run tests — expect both pass (sheet «Не вошло» is already rendered by `_render_initiatives`).**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 8 passed (including the existing 6).

- [ ] **Step 3.4: Commit.**

```bash
git add tests/test_scenario_xlsx_export.py
git commit -m "test(export): excluded scenario items render on «Не вошло» sheet"
```

---

## Task 4: Sheet «По ролям» — capacity matrix

**Goal:** Per-role table with: gross calendar, absences (planned/unplanned split), mandatory work columns (one per active work type), available, planned, deficit, usage %.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_by_role`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestByRoleSheet`.

**Spec reference:** § "Лист 4: Ресурс по ролям".

- [ ] **Step 4.1: Add the test.**

```python
class TestByRoleSheet:
    def test_role_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["По ролям"]
        # Row 1 = header. Row 2 = first role.
        labels = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
        assert "Разработчик" in labels

    def test_static_columns(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["По ролям"]
        header = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        # Static prefix
        assert header[:6] == [
            "Роль", "Сотрудники в роли", "Норма (календарь), ч",
            "Отсутствия, ч", "Из них планов., ч", "Из них внепл., ч",
        ]
        # Static suffix (last 4)
        assert header[-4:] == [
            "Доступно для инициатив, ч", "Запланировано, ч",
            "Дефицит, ч", "Использование, %",
        ]
        # Sum mandatory column right before suffix
        assert header[-5] == "Σ Обязательные, ч"

    def test_dev_planned_matches_allocations(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["По ролям"]
        # Find row with "Разработчик"
        dev_row = None
        for r in range(2, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Разработчик":
                dev_row = r
                break
        assert dev_row is not None
        # «Запланировано, ч» — second-to-last data column
        planned_col = ws.max_column - 2
        assert ws.cell(row=dev_row, column=planned_col).value == pytest.approx(80.0)
```

- [ ] **Step 4.2: Run — expect failures (sheet empty).**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py::TestByRoleSheet -v
```

- [ ] **Step 4.3: Implement `_sheet_by_role`.**

Replace the `_sheet_by_role` stub:

```python
def _sheet_by_role(self, ws, ctx: ScenarioExportContext) -> None:
    from openpyxl.formatting.rule import CellIsRule

    ws.sheet_view.showGridLines = False
    summary = ctx.resource_summary
    sub_wts = [w for w in ctx.work_types if w.subtracts_from_pool]

    # Build header
    static_prefix = [
        "Роль", "Сотрудники в роли", "Норма (календарь), ч",
        "Отсутствия, ч", "Из них планов., ч", "Из них внепл., ч",
    ]
    wt_headers = [w.label for w in sub_wts]
    static_suffix = [
        "Σ Обязательные, ч",
        "Доступно для инициатив, ч", "Запланировано, ч",
        "Дефицит, ч", "Использование, %",
    ]
    headers = static_prefix + wt_headers + static_suffix
    for c_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[1].height = 28

    # Planned hours per role (from allocations, included only)
    planned_by_role: dict[str, float] = {}
    for a in ctx.allocations:
        if not a.included_flag:
            continue
        analyst, dev, qa = _demand_by_role(a.backlog_item)
        # Allocate proportionally to estimated demand if planned_hours overrides total
        total_est = analyst + dev + qa
        planned = a.planned_hours or 0.0
        if total_est > 0:
            planned_by_role["analyst"] = planned_by_role.get("analyst", 0.0) + planned * analyst / total_est
            planned_by_role["dev"] = planned_by_role.get("dev", 0.0) + planned * dev / total_est
            planned_by_role["qa"] = planned_by_role.get("qa", 0.0) + planned * qa / total_est

    # Planned + unplanned absence hours per role (split by AbsenceReason.is_planned)
    abs_planned_h: dict[str, float] = {}
    abs_unplanned_h: dict[str, float] = {}
    cur = ctx.period_start
    cal = ctx.calendar_by_date
    while cur < ctx.period_end:
        norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
        cur_next = cur
        cur = cur.fromordinal(cur.toordinal() + 1)
        if norm <= 0:
            continue
        for a in ctx.absences:
            if not (a.start_date <= cur_next <= a.end_date):
                continue
            emp = next((e for e in ctx.employees if e.id == a.employee_id), None)
            if emp is None or not emp.role:
                continue
            bucket = abs_planned_h if (a.reason and a.reason.is_planned) else abs_unplanned_h
            bucket[emp.role] = bucket.get(emp.role, 0.0) + norm

    # Render rows
    for r_idx, role in enumerate(summary.roles, start=2):
        role_label = (
            ctx.roles_by_code[role].label if role in ctx.roles_by_code else role
        )
        names = ", ".join(summary.role_employee_names.get(role, []))
        cal_gross = summary.calendar_gross_by_role.get(role, 0.0)
        gross_after_abs = summary.gross_by_role.get(role, 0.0)
        absences_total = round(cal_gross - gross_after_abs, 1)
        abs_p = round(abs_planned_h.get(role, 0.0), 1)
        abs_u = round(abs_unplanned_h.get(role, 0.0), 1)

        ws.cell(row=r_idx, column=1, value=role_label).font = _Style.BOLD_FONT
        ws.cell(row=r_idx, column=2, value=names).font = _Style.ITALIC_FONT
        ws.cell(row=r_idx, column=3, value=round(cal_gross, 1))
        ws.cell(row=r_idx, column=4, value=absences_total)
        ws.cell(row=r_idx, column=5, value=abs_p)
        ws.cell(row=r_idx, column=6, value=abs_u)

        # Per-work-type columns
        col = 7
        sum_mandatory = 0.0
        for wt in sub_wts:
            wt_row = next(
                (x for x in summary.work_type_rows if x.work_type_id == wt.id), None,
            )
            hours = wt_row.hours_by_role.get(role, 0.0) if wt_row else 0.0
            sum_mandatory += hours
            ws.cell(row=r_idx, column=col, value=round(hours, 1))
            col += 1

        ws.cell(row=r_idx, column=col, value=round(sum_mandatory, 1)).font = _Style.BOLD_FONT
        col += 1
        avail = summary.available_by_role.get(role, 0.0)
        ws.cell(row=r_idx, column=col, value=round(avail, 1)).font = _Style.BOLD_FONT
        col += 1
        planned = round(planned_by_role.get(role, 0.0), 1)
        ws.cell(row=r_idx, column=col, value=planned)
        col += 1
        deficit = round(avail - planned, 1)
        ws.cell(row=r_idx, column=col, value=deficit)
        col += 1
        usage_pct = (planned / avail * 100.0) if avail > 0 else 0.0
        ws.cell(row=r_idx, column=col, value=round(usage_pct, 1))

    # Conditional formatting on usage %
    last_row = 1 + len(summary.roles)
    if last_row >= 2:
        usage_col = get_column_letter(len(headers))
        rng = f"{usage_col}2:{usage_col}{last_row}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="lessThan", formula=["80"], fill=_Style.GREEN_BG,
        ))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="between", formula=["80", "100"], fill=_Style.YELLOW_BG,
        ))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="greaterThan", formula=["110"], fill=_Style.RED_BG,
            font=Font(bold=True, color=_Style.RED_TEXT),
        ))
        # Deficit column — red text when negative
        deficit_col = get_column_letter(len(headers) - 1)
        rng = f"{deficit_col}2:{deficit_col}{last_row}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="lessThan", formula=["0"],
            font=Font(bold=True, color=_Style.RED_TEXT),
        ))

    # External QA row, if set
    if ctx.scenario.external_qa_hours is not None:
        r_idx = last_row + 1
        ws.cell(row=r_idx, column=1, value="*Внешний QA").font = _Style.ITALIC_FONT
        ws.cell(row=r_idx, column=3, value=round(ctx.scenario.external_qa_hours, 1))

    # Column widths
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 40
    for c_idx in range(3, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c_idx)].width = 16

    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
```

- [ ] **Step 4.4: Run tests — expect pass.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 11 passed.

- [ ] **Step 4.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario sheet «По ролям» — per-role capacity matrix"
```

---

## Task 5: Sheet «По сотрудникам» — per-employee resource table

**Goal:** Row per employee (sorted by team then name): команда, сотрудник, роль, норма, отсутствия (планов./внепл.), доступно, раб. дней, дней отсутствия. Group rows per team with cyan fill on top.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_by_employee`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestByEmployeeSheet`.

**Spec reference:** § "Лист 5: Ресурс по сотрудникам".

- [ ] **Step 5.1: Add the test.**

```python
EMP_HEADERS = [
    "Команда", "Сотрудник", "Роль",
    "Норма (календарь), ч", "Отсутствия (план.), ч", "Отсутствия (внепл.), ч",
    "Доступно, ч", "Раб. дней в квартале", "Дней отсутствия",
]


class TestByEmployeeSheet:
    def test_headers(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["По сотрудникам"]
        header = [ws.cell(row=1, column=c).value for c in range(1, len(EMP_HEADERS) + 1)]
        assert header == EMP_HEADERS

    def test_employee_row(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["По сотрудникам"]
        # Find row with "Dave"
        names = [ws.cell(row=r, column=2).value for r in range(2, ws.max_row + 1)]
        assert "Dave" in names
```

- [ ] **Step 5.2: Run — expect failures.**

- [ ] **Step 5.3: Implement `_sheet_by_employee`.**

```python
def _sheet_by_employee(self, ws, ctx: ScenarioExportContext) -> None:
    from openpyxl.formatting.rule import CellIsRule

    ws.sheet_view.showGridLines = False
    headers = [
        "Команда", "Сотрудник", "Роль",
        "Норма (календарь), ч", "Отсутствия (план.), ч", "Отсутствия (внепл.), ч",
        "Доступно, ч", "Раб. дней в квартале", "Дней отсутствия",
    ]
    for c_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[1].height = 28

    # Pre-compute per-employee gross calendar hours (no absence subtraction)
    cal = ctx.calendar_by_date

    def employee_calendar_hours() -> float:
        h = 0.0
        cur = ctx.period_start
        while cur < ctx.period_end:
            h += cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
            cur = cur.fromordinal(cur.toordinal() + 1)
        return h

    cal_total = employee_calendar_hours()

    # Map: employee_id -> EmployeeBase from resource_base
    base_by_id = {e.employee_id: e for e in ctx.resource_base.employees}

    rows = []
    for emp in ctx.employees:
        team = "Alpha"  # фактически: primary EmployeeTeam.team. Берём из ctx.scenario.team
        team_name = ctx.scenario.team or "—"
        role_label = (
            ctx.roles_by_code[emp.role].label
            if emp.role and emp.role in ctx.roles_by_code else (emp.role or "—")
        )
        base = base_by_id.get(emp.id)
        available = base.total_hours if base else 0.0
        work_days = sum(1 for d in (base.days if base else []) if d.hours > 0)

        # Absences for this employee
        emp_abs = [a for a in ctx.absences if a.employee_id == emp.id]
        abs_p_h = 0.0
        abs_u_h = 0.0
        abs_days_count = 0
        cur = ctx.period_start
        while cur < ctx.period_end:
            norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
            if norm > 0:
                for a in emp_abs:
                    if a.start_date <= cur <= a.end_date:
                        abs_days_count += 1
                        if a.reason and a.reason.is_planned:
                            abs_p_h += norm
                        else:
                            abs_u_h += norm
                        break
            cur = cur.fromordinal(cur.toordinal() + 1)

        rows.append((team_name, emp.display_name, role_label,
                     round(cal_total, 1), round(abs_p_h, 1), round(abs_u_h, 1),
                     round(available, 1), work_days, abs_days_count))

    rows.sort(key=lambda r: (r[0], r[1]))

    # Render with team grouping rows (cyan accent)
    r_idx = 2
    last_team = None
    for row in rows:
        if row[0] != last_team:
            # Group header
            ws.cell(row=r_idx, column=1, value=row[0]).font = _Style.HEADER_FONT
            ws.cell(row=r_idx, column=1).fill = _Style.ACCENT_BG
            for c_idx in range(2, len(headers) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = _Style.ACCENT_BG
            r_idx += 1
            last_team = row[0]
        for c_idx, val in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=val)
        r_idx += 1

    last_row = r_idx - 1

    # Conditional formatting on «Дней отсутствия» (last column)
    if last_row >= 2:
        col_letter = get_column_letter(len(headers))
        rng = f"{col_letter}2:{col_letter}{last_row}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="between", formula=["6", "15"], fill=_Style.YELLOW_BG,
        ))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="greaterThan", formula=["15"], fill=_Style.RED_BG,
        ))

    # Column widths
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 18
    for c_idx in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c_idx)].width = 14

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
```

- [ ] **Step 5.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 13 passed.

- [ ] **Step 5.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario sheet «По сотрудникам» — per-employee with team groups"
```

---

## Task 6: Sheet «Правила» — scenario rules matrix

**Goal:** Matrix Role × MandatoryWorkType: cells show "X% · Y ч". Plus external QA limit row, plus a small table of non-pool work types below.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_rules`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestRulesSheet`.

**Spec reference:** § "Лист 6: Правила и обязательные работы".

- [ ] **Step 6.1: Add the test.**

```python
class TestRulesSheet:
    def test_rules_sheet_has_headers(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Правила"]
        # Title in A1
        assert "Правила сценария" in (ws.cell(row=1, column=1).value or "")

    def test_external_qa_row_when_set(self, db_session, minimal_scenario):
        # Update scenario with external_qa_hours
        scenario = db_session.get(PlanningScenario, minimal_scenario.scenario_id)
        scenario.external_qa_hours = 120.0
        db_session.flush()

        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Правила"]
        # External QA row appears somewhere — search for label
        found = False
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if v and "Внешний QA" in str(v):
                found = True
                # Hours should be in next column
                assert ws.cell(row=r, column=2).value == pytest.approx(120.0)
        assert found
```

- [ ] **Step 6.2: Run — expect failure.**

- [ ] **Step 6.3: Implement `_sheet_rules`.**

```python
def _sheet_rules(self, ws, ctx: ScenarioExportContext) -> None:
    ws.sheet_view.showGridLines = False
    sub_wts = [w for w in ctx.work_types if w.subtracts_from_pool]
    non_sub_wts = [w for w in ctx.work_types if not w.subtracts_from_pool]

    # Title
    ws.cell(row=1, column=1, value=f"Правила сценария: {ctx.scenario.name}")
    ws.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True)
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=max(2, len(sub_wts) + 2))

    # Matrix header (row 3): Role | wt1 | wt2 | ... | Σ %
    header_row = 3
    ws.cell(row=header_row, column=1, value="Роль").font = _Style.HEADER_FONT
    ws.cell(row=header_row, column=1).fill = _Style.HEADER_FILL
    ws.cell(row=header_row, column=1).alignment = _Style.CENTER
    for c_idx, wt in enumerate(sub_wts, start=2):
        c = ws.cell(row=header_row, column=c_idx, value=wt.label)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    sum_col = len(sub_wts) + 2
    c = ws.cell(row=header_row, column=sum_col, value="Σ % обязательных")
    c.font = _Style.HEADER_FONT
    c.fill = _Style.HEADER_FILL
    c.alignment = _Style.CENTER

    # Rule lookup: (work_type_id, role_or_None) -> percent_of_norm
    rule_lookup: dict[tuple[str, Optional[str]], float] = {}
    for r in ctx.scenario_rules:
        rule_lookup[(r.work_type_id, r.role)] = (
            rule_lookup.get((r.work_type_id, r.role), 0.0) + r.percent_of_norm
        )

    # Rows: roles in scenario.team + a "Все роли" row for NULL rules
    summary = ctx.resource_summary
    r_idx = header_row + 1
    for role in summary.roles + [None]:
        role_label = (
            ctx.roles_by_code[role].label
            if role and role in ctx.roles_by_code else (role or "Все роли")
        )
        ws.cell(row=r_idx, column=1, value=role_label).font = _Style.BOLD_FONT
        sum_pct = 0.0
        gross = summary.gross_by_role.get(role, 0.0) if role else 0.0
        for c_idx, wt in enumerate(sub_wts, start=2):
            pct = rule_lookup.get((wt.id, role))
            if pct is None and role is not None:
                # NULL fallback rule may apply — show as "—" if no role-specific
                cell = ws.cell(row=r_idx, column=c_idx, value=None)
                cell.fill = _Style.GREY_BG
                continue
            if pct is None:
                cell = ws.cell(row=r_idx, column=c_idx, value=None)
                cell.fill = _Style.GREY_BG
                continue
            hours = round(gross * pct / 100.0, 1) if role else None
            text = f"{pct:.0f} %" + (f" · {hours} ч" if hours is not None else "")
            cell = ws.cell(row=r_idx, column=c_idx, value=text)
            sum_pct += pct
            # Heatmap by pct
            if pct >= 50:
                cell.fill = PatternFill("solid", fgColor=_Style.CYAN_DARK)
            elif pct >= 25:
                cell.fill = PatternFill("solid", fgColor=_Style.CYAN_MID)
            elif pct >= 10:
                cell.fill = _Style.CYAN_LIGHT_BG
        sum_cell = ws.cell(row=r_idx, column=sum_col, value=f"{sum_pct:.0f} %")
        if sum_pct > 100:
            sum_cell.font = Font(bold=True, color=_Style.RED_TEXT)
        r_idx += 1

    # External QA row
    r_idx += 1
    ws.cell(row=r_idx, column=1, value="Внешний QA, ч").font = _Style.ITALIC_FONT
    qa_value = ctx.scenario.external_qa_hours
    ws.cell(row=r_idx, column=2, value=qa_value if qa_value is not None else "не задан")

    # Non-pool work types section
    if non_sub_wts:
        r_idx += 2
        ws.cell(row=r_idx, column=1, value="Виды работ, не вычитающие из пула").font = _Style.BOLD_FONT
        r_idx += 1
        ws.cell(row=r_idx, column=1, value="Вид работы").font = _Style.HEADER_FONT
        ws.cell(row=r_idx, column=1).fill = _Style.HEADER_FILL
        ws.cell(row=r_idx, column=2, value="Описание").font = _Style.HEADER_FONT
        ws.cell(row=r_idx, column=2).fill = _Style.HEADER_FILL
        for wt in non_sub_wts:
            r_idx += 1
            ws.cell(row=r_idx, column=1, value=wt.label)
            ws.cell(row=r_idx, column=2,
                    value="не уменьшает доступное время").font = _Style.ITALIC_FONT

    # Column widths
    ws.column_dimensions["A"].width = 24
    for c_idx in range(2, sum_col + 1):
        ws.column_dimensions[get_column_letter(c_idx)].width = 22
```

- [ ] **Step 6.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 15 passed.

- [ ] **Step 6.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario sheet «Правила» — role × work-type matrix"
```

---

## Task 7: Sheet «Отсутствия» — full absence list

**Goal:** Per-row absences for the team in this quarter, sorted by team→employee→start_date. Reason cell coloured per AbsenceReason.color.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_absences`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestAbsencesSheet` with one absence in seed.

**Spec reference:** § "Лист 7: Отсутствия".

- [ ] **Step 7.1: Add the test.**

```python
class TestAbsencesSheet:
    def test_absences_listed_when_present(self, db_session, minimal_scenario):
        from datetime import date as _d
        from app.models import Absence, AbsenceReason
        reason = AbsenceReason(
            code="vac", label="Отпуск", is_planned=True, color="#52C41A",
            sort_order=0,
        )
        db_session.add(reason)
        db_session.flush()
        emp = db_session.query(Employee).filter(Employee.display_name == "Dave").first()
        db_session.add(Absence(
            employee_id=emp.id,
            start_date=_d(2026, 4, 6),
            end_date=_d(2026, 4, 12),
            reason_id=reason.id,
            hours_total=40.0,
        ))
        db_session.flush()

        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Отсутствия"]

        # Header row 1
        header = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        assert header == [
            "Сотрудник", "Команда", "Роль", "Причина", "Тип",
            "Начало", "Конец", "Дней", "Часов потеряно",
        ]
        # First data row
        assert ws.cell(row=2, column=1).value == "Dave"
        assert ws.cell(row=2, column=4).value == "Отпуск"
        assert ws.cell(row=2, column=5).value == "Плановая"

    def test_no_absences_renders_empty_sheet(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Отсутствия"]
        # Just header + summary line, no data rows
        assert ws.cell(row=1, column=1).value == "Сотрудник"
```

- [ ] **Step 7.2: Run — expect failures.**

- [ ] **Step 7.3: Implement `_sheet_absences`.**

```python
def _sheet_absences(self, ws, ctx: ScenarioExportContext) -> None:
    from openpyxl.formatting.rule import CellIsRule

    ws.sheet_view.showGridLines = False
    headers = [
        "Сотрудник", "Команда", "Роль", "Причина", "Тип",
        "Начало", "Конец", "Дней", "Часов потеряно",
    ]
    for c_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[1].height = 28

    cal = ctx.calendar_by_date

    def hours_lost(a: Absence) -> float:
        if a.hours_total is not None:
            return float(a.hours_total)
        # Recompute from calendar
        h = 0.0
        cur = max(a.start_date, ctx.period_start)
        end = min(a.end_date, date(ctx.period_end.year, ctx.period_end.month, ctx.period_end.day) - timedelta(days=0))
        # period_end is exclusive; iterate through end_date inclusive but bounded
        from datetime import timedelta as _td
        while cur <= a.end_date and cur < ctx.period_end:
            norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
            if norm > 0:
                h += norm
            cur = cur + _td(days=1)
        return round(h, 1)

    def days_count(a: Absence) -> int:
        from datetime import timedelta as _td
        cnt = 0
        cur = max(a.start_date, ctx.period_start)
        while cur <= a.end_date and cur < ctx.period_end:
            norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
            if norm > 0:
                cnt += 1
            cur = cur + _td(days=1)
        return cnt

    emp_by_id = {e.id: e for e in ctx.employees}
    rows = []
    for a in ctx.absences:
        emp = emp_by_id.get(a.employee_id)
        if emp is None:
            continue
        role_label = (
            ctx.roles_by_code[emp.role].label
            if emp.role and emp.role in ctx.roles_by_code else (emp.role or "—")
        )
        team = ctx.scenario.team or "—"
        rows.append({
            "emp_name": emp.display_name,
            "team": team,
            "role": role_label,
            "reason": a.reason.label if a.reason else "—",
            "kind": "Плановая" if (a.reason and a.reason.is_planned) else "Внеплановая",
            "start": a.start_date,
            "end": a.end_date,
            "days": days_count(a),
            "hours": hours_lost(a),
            "color": (a.reason.color if a.reason else None),
        })

    rows.sort(key=lambda r: (r["team"], r["emp_name"], r["start"]))

    for r_idx, row in enumerate(rows, start=2):
        ws.cell(row=r_idx, column=1, value=row["emp_name"])
        ws.cell(row=r_idx, column=2, value=row["team"])
        ws.cell(row=r_idx, column=3, value=row["role"])
        reason_cell = ws.cell(row=r_idx, column=4, value=row["reason"])
        if row["color"]:
            color_hex = row["color"].lstrip("#").upper()
            reason_cell.fill = PatternFill("solid", fgColor=color_hex)
            reason_cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        ws.cell(row=r_idx, column=5, value=row["kind"])
        ws.cell(row=r_idx, column=6, value=row["start"]).number_format = "DD.MM.YYYY"
        ws.cell(row=r_idx, column=7, value=row["end"]).number_format = "DD.MM.YYYY"
        ws.cell(row=r_idx, column=8, value=row["days"])
        ws.cell(row=r_idx, column=9, value=row["hours"])

    last_row = max(2, len(rows) + 1)
    if rows:
        # Conditional formatting on hours
        rng = f"I2:I{last_row}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="greaterThan", formula=["80"], fill=_Style.RED_BG,
        ))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="between", formula=["40", "80"], fill=_Style.YELLOW_BG,
        ))

    # Widths
    widths = [22, 16, 18, 20, 14, 14, 14, 10, 16]
    for c_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
```

Add `from datetime import timedelta` at the top of the module if not present.

- [ ] **Step 7.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 17 passed.

- [ ] **Step 7.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario sheet «Отсутствия» — full absence list with reason colours"
```

---

## Task 8: Sheet «Обложка» — presentation summary

**Goal:** Big title, status badge, 6 metric cards (capacity / planned / leftover / included count / excluded count / deficit), usage progress bar, role summary table.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — implement `_sheet_cover`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestCoverSheet`.

**Spec reference:** § "Лист 1: Обложка".

- [ ] **Step 8.1: Add the test.**

```python
class TestCoverSheet:
    def test_title_contains_scenario_name(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Обложка"]
        a1 = ws.cell(row=1, column=1).value or ""
        assert "Q2 2026 Alpha Base" in a1

    def test_status_badge_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Обложка"]
        # Search rows 1-5 for "ЧЕРНОВИК" or "УТВЕРЖДЁН"
        seen = ""
        for r in range(1, 6):
            for c in range(1, 12):
                v = ws.cell(row=r, column=c).value
                if v and ("ЧЕРНОВИК" in str(v) or "УТВЕРЖДЁН" in str(v)):
                    seen = str(v)
        assert seen != ""

    def test_metric_cards_have_labels(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Обложка"]
        all_text: list[str] = []
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                if v is not None:
                    all_text.append(str(v))
        joined = " | ".join(all_text)
        assert "Ёмкость" in joined
        assert "Запланировано" in joined
        assert "Остаток" in joined
        assert "Включено" in joined
        assert "Не вошло" in joined
```

- [ ] **Step 8.2: Run — expect failures.**

- [ ] **Step 8.3: Implement `_sheet_cover`.**

```python
def _sheet_cover(self, ws, ctx: ScenarioExportContext) -> None:
    ws.sheet_view.showGridLines = False
    summary = ctx.resource_summary

    # ---- Title block (row 1-3) ----
    title = ws.cell(row=1, column=1, value=f"СЦЕНАРИЙ · {ctx.scenario.name}")
    title.font = _Style.TITLE_FONT
    title.fill = _Style.HEADER_FILL
    title.alignment = _Style.LEFT
    ws.merge_cells("A1:H1")
    ws.row_dimensions[1].height = 40

    sub = ws.cell(
        row=2, column=1,
        value=f"{ctx.scenario.quarter or ''} · {ctx.scenario.year or ''} · команда «{ctx.scenario.team or '—'}»",
    )
    sub.font = Font(name="Calibri", size=12, color="FFFFFF")
    sub.fill = _Style.HEADER_FILL
    ws.merge_cells("A2:F2")

    # Status badge in G2:H2
    is_approved = ctx.scenario.status == "approved"
    badge_text = "✓ УТВЕРЖДЁН" if is_approved else "✎ ЧЕРНОВИК"
    badge = ws.cell(row=2, column=7, value=badge_text)
    badge_color = _Style.GREEN_TEXT if is_approved else _Style.GREY_TEXT
    badge.fill = PatternFill("solid", fgColor=badge_color)
    badge.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    badge.alignment = _Style.CENTER
    ws.merge_cells("G2:H2")

    # ---- Compute metrics ----
    total_capacity = round(summary.available_total, 1)
    total_planned = round(
        sum(a.planned_hours or 0.0 for a in ctx.allocations if a.included_flag),
        1,
    )
    leftover = round(max(0.0, total_capacity - total_planned), 1)
    included_n = sum(1 for a in ctx.allocations if a.included_flag)
    excluded_n = sum(1 for a in ctx.allocations if not a.included_flag)
    deficit_pct = round(
        max(0.0, (total_planned - total_capacity) / total_capacity * 100.0)
        if total_capacity > 0 else 0.0, 1,
    )
    usage_pct = round(
        (total_planned / total_capacity * 100.0) if total_capacity > 0 else 0.0, 1,
    )

    # ---- 6 cards in two rows of three (rows 4-6 and 8-10) ----
    cards = [
        ("Ёмкость, ч", f"{total_capacity:.0f}", "—"),
        ("Запланировано, ч", f"{total_planned:.0f}", f"{usage_pct:.0f} % исп."),
        ("Остаток, ч", f"{leftover:.0f}", f"{100 - usage_pct:.0f} % своб."),
        ("Включено", f"{included_n}", "задач"),
        ("Не вошло", f"{excluded_n}", "задач"),
        ("Дефицит, %", f"{deficit_pct:.0f}", "от ёмкости"),
    ]

    def render_card(top_row: int, left_col: int, label: str, value: str, hint: str):
        # 3 rows x 2 cols
        ws.cell(row=top_row, column=left_col, value=label).font = _Style.METRIC_LABEL_FONT
        ws.merge_cells(start_row=top_row, start_column=left_col,
                       end_row=top_row, end_column=left_col + 1)
        big = ws.cell(row=top_row + 1, column=left_col, value=value)
        big.font = _Style.METRIC_FONT
        big.alignment = _Style.LEFT
        ws.merge_cells(start_row=top_row + 1, start_column=left_col,
                       end_row=top_row + 1, end_column=left_col + 1)
        ws.cell(row=top_row + 2, column=left_col, value=hint).font = _Style.METRIC_HINT_FONT
        ws.merge_cells(start_row=top_row + 2, start_column=left_col,
                       end_row=top_row + 2, end_column=left_col + 1)
        # Cyan border on entire 3x2 block
        for r in range(top_row, top_row + 3):
            for c in range(left_col, left_col + 2):
                ws.cell(row=r, column=c).border = _Style.THIN_BORDER

    for i, (label, value, hint) in enumerate(cards):
        row = 4 if i < 3 else 8
        col = 1 + (i % 3) * 3  # cols A, D, G
        render_card(row, col, label, value, hint)
        ws.row_dimensions[row].height = 18
        ws.row_dimensions[row + 1].height = 38
        ws.row_dimensions[row + 2].height = 16

    # ---- Usage progress bar (row 12) ----
    ws.cell(row=12, column=1, value="Использование").font = _Style.BOLD_FONT
    bar_total = 20  # cells wide
    filled = int(round(usage_pct / 100.0 * bar_total))
    filled = max(0, min(bar_total, filled))
    for c in range(2, 2 + bar_total):
        cell = ws.cell(row=12, column=c, value=None)
        cell.fill = (
            _Style.ACCENT_BG if (c - 2) < filled
            else PatternFill("solid", fgColor="E6E6E6")
        )
    ws.cell(row=12, column=2 + bar_total, value=f"{usage_pct:.0f} %").font = _Style.BOLD_FONT

    # ---- By-role table (rows 14+) ----
    ws.cell(row=14, column=1, value="По ролям").font = Font(name="Calibri", size=14, bold=True)
    role_headers = ["Роль", "Ёмкость, ч", "Запланировано, ч", "Остаток, ч", "% исп."]
    for c_idx, h in enumerate(role_headers, start=1):
        c = ws.cell(row=15, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER

    # Compute per-role planned (same logic as Sheet 4)
    planned_by_role: dict[str, float] = {}
    for a in ctx.allocations:
        if not a.included_flag:
            continue
        analyst, dev, qa = _demand_by_role(a.backlog_item)
        total_est = analyst + dev + qa
        if total_est <= 0:
            continue
        p = a.planned_hours or 0.0
        planned_by_role["analyst"] = planned_by_role.get("analyst", 0.0) + p * analyst / total_est
        planned_by_role["dev"] = planned_by_role.get("dev", 0.0) + p * dev / total_est
        planned_by_role["qa"] = planned_by_role.get("qa", 0.0) + p * qa / total_est

    r_idx = 16
    for role in summary.roles:
        avail = summary.available_by_role.get(role, 0.0)
        planned = planned_by_role.get(role, 0.0)
        leftover_r = max(0.0, avail - planned)
        usage_r = (planned / avail * 100.0) if avail > 0 else 0.0
        label = ctx.roles_by_code[role].label if role in ctx.roles_by_code else role
        ws.cell(row=r_idx, column=1, value=label).font = _Style.BOLD_FONT
        ws.cell(row=r_idx, column=2, value=round(avail, 1))
        ws.cell(row=r_idx, column=3, value=round(planned, 1))
        ws.cell(row=r_idx, column=4, value=round(leftover_r, 1))
        usage_cell = ws.cell(row=r_idx, column=5, value=round(usage_r, 1))
        if usage_r > 110:
            usage_cell.fill = _Style.RED_BG
            usage_cell.font = Font(bold=True, color=_Style.RED_TEXT)
        elif usage_r > 100:
            usage_cell.fill = _Style.ORANGE_FILL
        elif usage_r > 80:
            usage_cell.fill = _Style.YELLOW_BG
        else:
            usage_cell.fill = _Style.GREEN_BG
        r_idx += 1

    # ---- Footer (generated_at) ----
    r_idx += 1
    footer = ws.cell(
        row=r_idx, column=1,
        value=f"Сформировано: {ctx.generated_at:%Y-%m-%d %H:%M} UTC · Источник: Jira Analysis",
    )
    footer.font = Font(name="Calibri", size=9, italic=True, color=_Style.GREY_TEXT)

    # Column widths (cards each 2 cols wide × 3 = 6 + accent margin)
    for c_idx in range(1, 9):
        ws.column_dimensions[get_column_letter(c_idx)].width = 16

    # Apply dark fill to title row (already done via TITLE_FONT but rows 1-2)
    for col in range(1, 9):
        for r in (1, 2):
            cell = ws.cell(row=r, column=col)
            if cell.fill.fgColor.value not in {_Style.GREEN_TEXT, _Style.GREY_TEXT}:
                cell.fill = _Style.HEADER_FILL
```

**Note on `ORANGE_FILL`:** add to `_Style`:

```python
ORANGE_FILL_BG = PatternFill("solid", fgColor="FFF7E6")
```

…or use an inline `PatternFill`. Above I used `_Style.ORANGE_FILL` — change to `_Style.ORANGE_FILL_BG` or define `ORANGE_FILL` consistently with other `*_BG` fills. Decide: rename `ORANGE_FILL` to `ORANGE_BG` and use it. Update other references if any.

Actually, simpler: just add this attribute next to `GREEN_BG`/`YELLOW_BG`/`RED_BG`:

```python
ORANGE_BG = PatternFill("solid", fgColor="FFF7E6")
```

And reference `_Style.ORANGE_BG` in `_sheet_cover`. Apply this small refactor.

- [ ] **Step 8.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 20 passed.

- [ ] **Step 8.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario «Обложка» — presentation cover with metric cards"
```

---

## Task 9: Wire up `ExportService` + filename + remove old impl

**Goal:** Replace the body of `ExportService.build_scenario_xlsx` with a call to the new exporter. Update the endpoint to use a richer `Content-Disposition` filename. Delete the old inline `_load_scenario_rows` / dataclass if `build_scenario_pptx` no longer needs them — but it does, so keep them.

**Files:**
- Modify: `app/services/export_service.py:461-544` — replace body.
- Modify: `app/api/endpoints/exports.py:126-140` — better filename.
- Modify: `tests/test_export_service.py:249-291` — update `TestScenarioXlsx` to expect new sheet structure.

- [ ] **Step 9.1: Replace `build_scenario_xlsx` body.**

In `app/services/export_service.py`, replace lines 461-544 with:

```python
def build_scenario_xlsx(self, scenario_id: str) -> bytes:
    """Собрать xlsx со сценарием — делегирует в ScenarioXlsxExporter."""
    from app.services.scenario_xlsx_export import ScenarioXlsxExporter

    return ScenarioXlsxExporter(self.db, scenario_id).build()
```

Keep `_load_scenario_rows`, `ScenarioExportRow`, and the imports they need — they still serve `build_scenario_pptx`.

- [ ] **Step 9.2: Update endpoint filename.**

In `app/api/endpoints/exports.py:139`, change to:

```python
    scenario = db.get(__import__("app.models", fromlist=["PlanningScenario"]).PlanningScenario, scenario_id)
    if scenario is None:
        # build_scenario_xlsx raises 404 already; we won't reach here
        raise HTTPException(status_code=404)
    slug = "".join(c if c.isalnum() else "-" for c in (scenario.name or "scenario")).lower().strip("-")[:40]
    fn = f"scenario_{scenario.quarter or 'Q?'}_{scenario.year or 'YYYY'}_{slug}_{datetime.utcnow():%Y-%m-%d}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers=_attachment_headers(fn),
    )
```

Cleaner — add proper imports at top of `exports.py`:
```python
from datetime import datetime
from app.models import PlanningScenario
```

…and rewrite the function:

```python
async def export_scenario_xlsx(
    scenario_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Скачать xlsx со сводкой и раскладкой сценария."""
    service = ExportService(db)
    try:
        data = service.build_scenario_xlsx(scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    scenario = db.get(PlanningScenario, scenario_id)
    slug = "".join(
        c if c.isalnum() else "-" for c in (scenario.name or "scenario")
    ).lower().strip("-")[:40]
    fn = (
        f"scenario_{scenario.quarter or 'Q'}"
        f"_{scenario.year or 'YYYY'}"
        f"_{slug}"
        f"_{datetime.utcnow():%Y-%m-%d}.xlsx"
    )
    return Response(content=data, media_type=XLSX_MIME, headers=_attachment_headers(fn))
```

- [ ] **Step 9.3: Update `TestScenarioXlsx` in `tests/test_export_service.py`.**

Replace `test_sheet_has_summary_and_rows` (lines ~250-286) with:

```python
class TestScenarioXlsx:
    def test_workbook_has_seven_sheets(self, db_session, scenario_seed):
        from openpyxl import load_workbook

        data = ExportService(db_session).build_scenario_xlsx(
            scenario_seed.scenario_id
        )
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == [
            "Обложка", "Включено", "Не вошло",
            "По ролям", "По сотрудникам", "Правила", "Отсутствия",
        ]

    def test_included_titles_present(self, db_session, scenario_seed):
        from openpyxl import load_workbook

        data = ExportService(db_session).build_scenario_xlsx(
            scenario_seed.scenario_id
        )
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        titles = {ws.cell(row=i, column=2).value for i in range(2, ws.max_row + 1)}
        assert "Redesign login" in titles
        assert "Payments v2" in titles
        # "Overflow feature" должен быть в "Не вошло"
        assert "Overflow feature" not in titles
        ws_out = wb["Не вошло"]
        out_titles = {ws_out.cell(row=i, column=2).value for i in range(2, ws_out.max_row + 1)}
        assert "Overflow feature" in out_titles

    def test_unknown_scenario_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ExportService(db_session).build_scenario_xlsx("nope")
```

- [ ] **Step 9.4: The `scenario_seed` fixture currently doesn't create a `team` for the scenario.** Update it (around line 157) to add a team and EmployeeTeam memberships, otherwise `ResourceBaseService.compute()` will see an empty team and `summary.roles` will be empty.

Replace the scenario creation section in `scenario_seed`:

```python
    # Manual scenario + allocations (replaces the old greedy generate_scenario).
    from app.models import PlanningScenario, ScenarioAllocation, EmployeeTeam, Role
    db_session.add(Role(
        code="dev", label="Разработчик", color="#1890FF",
        is_active=True, counts_in_planning=True,
    ))
    db_session.add_all([
        EmployeeTeam(employee_id=alice.id, team="DevTeam", is_primary=True),
        EmployeeTeam(employee_id=bob.id, team="DevTeam", is_primary=True),
    ])
    db_session.flush()
    scenario = PlanningScenario(
        name="Q1 baseline", year=2026, quarter="Q1", status="draft", team="DevTeam",
    )
```

- [ ] **Step 9.5: Run all export-related tests.**

```bash
py -3.10 -m pytest tests/test_export_service.py tests/test_scenario_xlsx_export.py -v
```
Expected: all pass (the 4 PPTX tests still expect 4 slides — those still work because we didn't touch `build_scenario_pptx`).

- [ ] **Step 9.6: Commit.**

```bash
git add app/services/export_service.py app/api/endpoints/exports.py tests/test_export_service.py
git commit -m "feat(export): wire scenario xlsx through new exporter; richer filename"
```

---

## Task 10: Empty-data resilience

**Goal:** Verify the workbook generates without crashing when various data slices are empty (no allocations, no rules, no absences, no employees). Already partially covered by `minimal_scenario` but make sure each sheet handles empty input gracefully.

**Files:**
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestEmpty`.

- [ ] **Step 10.1: Add empty-state tests.**

```python
@pytest.fixture
def empty_scenario(db_session):
    """Сценарий без сотрудников, без правил, без аллокаций, без отсутствий."""
    scenario = PlanningScenario(
        name="Empty", year=2026, quarter="Q3", team="Ghost", status="draft",
    )
    db_session.add(scenario)
    db_session.flush()

    class _R:
        pass
    r = _R()
    r.scenario_id = scenario.id
    return r


class TestEmpty:
    def test_build_does_not_crash(self, db_session, empty_scenario):
        data = ScenarioXlsxExporter(db_session, empty_scenario.scenario_id).build()
        assert data[:2] == b"PK"  # xlsx is a ZIP archive
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == EXPECTED_SHEETS

    def test_included_sheet_has_only_header_and_totals(self, db_session, empty_scenario):
        data = ScenarioXlsxExporter(db_session, empty_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        # Row 1: header. Row 2: Σ ИТОГО (no data rows).
        assert ws.cell(row=2, column=1).value == "Σ ИТОГО"
```

- [ ] **Step 10.2: Run.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: all pass.

- [ ] **Step 10.3: If any sheet fails on empty input, fix the implementation in `app/services/scenario_xlsx_export.py`** (most likely cause: trying to render conditional formatting on an empty range, which `openpyxl` rejects). Wrap each `conditional_formatting.add` and `auto_filter.ref = ...` in `if last_row >= 2:` guards. Do NOT skip the empty test — make it pass.

- [ ] **Step 10.4: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): scenario xlsx handles empty allocations/employees/absences"
```

---

## Task 11: Manual smoke check + final polish

**Goal:** Run the full backend test suite to make sure nothing else broke, then optionally do a real-Excel sanity check.

- [ ] **Step 11.1: Run the full backend test suite.**

```bash
py -3.10 -m pytest tests/ -q
```
Expected: all tests that were passing on `main` before this branch still pass. New tests pass.

- [ ] **Step 11.2: Lint.**

```bash
ruff check app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
```
Fix anything ruff flags (most likely: unused imports, line length).

- [ ] **Step 11.3: Mypy.**

```bash
mypy app/services/scenario_xlsx_export.py
```
Fix typing errors. If openpyxl typing complains, `# type: ignore[no-untyped-call]` is acceptable for `Workbook()` constructors and similar.

- [ ] **Step 11.4: Manual check (optional, recommended).**

Start the backend, hit the endpoint, save the response, open in Excel:

```bash
uvicorn app.main:app --port 8000 &
# Find an existing scenario id via /api/v1/planning/scenarios
curl -o /tmp/scenario.xlsx "http://localhost:8000/api/v1/exports/scenarios/<scenario_id>.xlsx"
```

Open in Excel + LibreOffice. Verify:
- 7 sheets in correct order.
- Cover sheet renders cards and progress bar.
- Included sheet has heatmap and autofilter.
- Conditional formatting actually triggers (try a scenario with usage > 110 %).

- [ ] **Step 11.5: If anything looks broken visually, fix and amend the relevant earlier task's commit (or add a polish commit).** Do NOT loosen tests.

- [ ] **Step 11.6: Final commit (if any polish).**

```bash
git add -A
git commit -m "polish(export): visual fixes after Excel smoke check"
```

---

## Self-review checklist (run after writing the plan, before handing off)

- [x] Every spec section covered: 7 sheets → 7 task groups (2-8), wiring (9), resilience (10), polish (11).
- [x] No `TBD` / `TODO` / `implement later` placeholders.
- [x] Type names consistent: `ScenarioExportContext`, `ScenarioXlsxExporter`, `_Style`, `INITIATIVES_HEADERS`.
- [x] Tests use the same fixture (`minimal_scenario`) extended progressively, not redefined per task.
- [x] Each task has: failing test → run-and-see-it-fail → implementation → run-and-see-it-pass → commit.
- [x] `_Style.ORANGE_BG` consistency note included in Task 8.
- [x] Out-of-scope items from spec (sparklines, scenario comparison, PPTX changes) explicitly skipped — no plan task touches them.
