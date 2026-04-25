# Scenario xlsx export redesign — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing 7-sheet decorated scenario xlsx export with a 4-sheet «Бухгалтерия»-style book (Сводка / Включено / Не вошло / Справочник) per `docs/superpowers/specs/2026-04-25-scenario-xlsx-export-redesign.md`.

**Architecture:** Rewrite `app/services/scenario_xlsx_export.py` keeping the `ScenarioXlsxExporter` class shape but replacing all sheet methods. Drop cyan / cards / progress bars; use dark-grey header strips, traffic-light conditional formatting, and dense tables. The first sheet («Сводка») is a one-page dashboard combining metrics + per-role × months + per-employee summary.

**Tech Stack:** Python 3.10, openpyxl 3.x, pytest. No new dependencies.

---

## Pre-flight

- [ ] **Step 0.1: Read both specs end to end.**
  - `docs/superpowers/specs/2026-04-25-scenario-xlsx-export-redesign.md` — the source of truth for this work.
  - `docs/superpowers/specs/2026-04-25-scenario-xlsx-export-design.md` — the previous (rejected) spec; useful as background only. Don't follow it.

- [ ] **Step 0.2: Read existing code.**
  - `app/services/scenario_xlsx_export.py` (~990 lines) — the file you'll rewrite. Note the existing `ScenarioXlsxExporter`, `_Style`, `ScenarioExportContext`, `_load`, helper functions (`_demand_by_role`, `_initiative_row`).
  - `tests/test_scenario_xlsx_export.py` (364 lines) — the existing test file; **most of it gets replaced** since sheet structure changes from 7 to 4.
  - `tests/test_export_service.py:249-291` — `TestScenarioXlsx` (3 tests) needs updating for the new structure.
  - `app/services/export_service.py:380-457` — `export_capacity_xlsx` for the `MONTH_LABELS` constant we'll reuse.
  - `app/services/resource_base_service.py` — `compute()` and `compute_summary()` methods, `EmployeeBase.days[]`, `ResourceSummary` shape.

---

## Task 1: Update `_Style` palette and constants

**Goal:** Replace cyan/dark-blue accents with the «Бухгалтерия» palette: dark-grey `#1F2937` headers, traffic-light fills, no decorative cyan. Update `SHEET_NAMES` to 4 entries.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py:1-200` — `_Style` class, `SHEET_NAMES` constant.

- [ ] **Step 1.1: Replace the `_Style` class body.**

In `app/services/scenario_xlsx_export.py`, find the `class _Style:` block (around line 50–110) and replace its entire body with:

```python
class _Style:
    """Бухгалтерия palette — dark-grey headers, traffic-light data, no cyan."""

    # Palette
    DARK_HEADER = "1F2937"
    SECTION_BG = "F3F4F6"
    TOTALS_BG = "FAFAFA"
    HEAT_LIGHT = "ECFEFF"
    HEAT_MID = "CFFAFE"
    HEAT_DARK = "67E8F9"
    GREEN_FILL = "DCFCE7"
    GREEN_TEXT = "166534"
    YELLOW_FILL = "FEF3C7"
    YELLOW_TEXT = "92400E"
    RED_FILL = "FEE2E2"
    RED_TEXT = "B91C1C"
    PRI1_TEXT = "B91C1C"
    PRI2_TEXT = "B45309"
    GREY_TEXT = "9CA3AF"
    GREY_FILL = "FAFAFA"
    LINK_BLUE = "1D4ED8"

    # Reusable fills
    HEADER_FILL = PatternFill("solid", fgColor=DARK_HEADER)
    SECTION_FILL = PatternFill("solid", fgColor=SECTION_BG)
    TOTALS_FILL = PatternFill("solid", fgColor=TOTALS_BG)
    GREEN_BG = PatternFill("solid", fgColor=GREEN_FILL)
    YELLOW_BG = PatternFill("solid", fgColor=YELLOW_FILL)
    RED_BG = PatternFill("solid", fgColor=RED_FILL)
    GREY_BG = PatternFill("solid", fgColor=GREY_FILL)

    # Reusable fonts
    STRIP_FONT = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    SECTION_FONT = Font(name="Calibri", size=11, bold=True, color="4B5563")
    BOLD_FONT = Font(name="Calibri", size=11, bold=True)
    REGULAR_FONT = Font(name="Calibri", size=11)
    LABEL_FONT = Font(name="Calibri", size=10, color="6B7280")
    ITALIC_GREY_FONT = Font(name="Calibri", size=10, italic=True, color="6B7280")
    PRI1_FONT = Font(name="Calibri", size=11, bold=True, color=PRI1_TEXT)
    PRI2_FONT = Font(name="Calibri", size=11, bold=True, color=PRI2_TEXT)
    LINK_FONT = Font(name="Calibri", size=11, color=LINK_BLUE, underline="single")
    RED_BOLD_FONT = Font(name="Calibri", size=11, bold=True, color=RED_TEXT)
    EXCLUDED_FONT = Font(name="Calibri", size=11, color="6B7280")

    # Borders
    THIN_GREY = Side(style="thin", color="E5E7EB")
    BOTTOM_DARK = Side(style="medium", color=DARK_HEADER)
    TOP_DARK = Side(style="medium", color=DARK_HEADER)
    SECTION_BORDER = Border(bottom=BOTTOM_DARK)
    TOTALS_BORDER = Border(top=TOP_DARK)

    # Alignment
    LEFT = Alignment(horizontal="left", vertical="center")
    RIGHT = Alignment(horizontal="right", vertical="center")
    CENTER = Alignment(horizontal="center", vertical="center")
```

- [ ] **Step 1.2: Update `SHEET_NAMES`.**

Replace the existing `SHEET_NAMES` constant (around line 35) with:

```python
SHEET_NAMES = ["Сводка", "Включено", "Не вошло", "Справочник"]
```

- [ ] **Step 1.3: Update `MONTH_LABELS` constant.**

Add this constant near the top of the module (next to `QUARTER_MONTHS`):

```python
MONTH_LABELS = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
    7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}
```

- [ ] **Step 1.4: Compile-check.**

```bash
py -3.10 -c "from app.services.scenario_xlsx_export import ScenarioXlsxExporter, _Style, SHEET_NAMES, MONTH_LABELS; print(SHEET_NAMES)"
```
Expected: `['Сводка', 'Включено', 'Не вошло', 'Справочник']`.

If it fails because `_Style.SHEET_NAMES` references the wrong number of sheets in `build()`, just continue — Task 2 fixes that.

- [ ] **Step 1.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py
git commit -m "refactor(export): replace _Style palette with Бухгалтерия (dark-grey headers, no cyan)"
```

---

## Task 2: Strip out the old sheet methods, leave 4 stubs

**Goal:** Delete `_sheet_cover`, `_sheet_by_role`, `_sheet_by_employee`, `_sheet_rules`, `_sheet_absences`. Replace with stubs `_sheet_summary`, `_sheet_included`, `_sheet_excluded`, `_sheet_reference`. Update `build()` to call them. After this task the workbook has 4 empty sheets but `build()` runs without crashing.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `build()` method, sheet methods.

- [ ] **Step 2.1: Update `build()` method.**

Find the `build()` method (around line 200) and replace its body with:

```python
def build(self) -> bytes:
    ctx = self._load()
    wb = Workbook()
    wb.remove(wb.active)
    for name in SHEET_NAMES:
        wb.create_sheet(name)

    self._sheet_summary(wb["Сводка"], ctx)
    self._sheet_included(wb["Включено"], ctx)
    self._sheet_excluded(wb["Не вошло"], ctx)
    self._sheet_reference(wb["Справочник"], ctx)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 2.2: Delete old sheet methods, add new stubs.**

Find every method `_sheet_cover`, `_sheet_by_role`, `_sheet_by_employee`, `_sheet_rules`, `_sheet_absences`, `_render_initiatives` and **delete them entirely**. Find the existing stubs `_sheet_included`, `_sheet_excluded` and delete them too — we'll write fresh ones.

Add these four stubs at the end of the class:

```python
def _sheet_summary(self, ws, ctx: ScenarioExportContext) -> None:
    pass

def _sheet_included(self, ws, ctx: ScenarioExportContext) -> None:
    pass

def _sheet_excluded(self, ws, ctx: ScenarioExportContext) -> None:
    pass

def _sheet_reference(self, ws, ctx: ScenarioExportContext) -> None:
    pass
```

Helper functions defined at module level — `_demand_by_role`, `_initiative_row` (and any other module-level helpers) — should remain. We'll reuse them.

- [ ] **Step 2.3: Replace `tests/test_scenario_xlsx_export.py` with the new structure smoke test only.**

Delete the existing content of `tests/test_scenario_xlsx_export.py` and write:

```python
"""Tests for ScenarioXlsxExporter — 4-sheet «Бухгалтерия» layout."""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import (
    BacklogItem, Employee, EmployeeTeam, MandatoryWorkType,
    PlanningScenario, ScenarioAllocation, Role,
)
from app.services.scenario_xlsx_export import ScenarioXlsxExporter


EXPECTED_SHEETS = ["Сводка", "Включено", "Не вошло", "Справочник"]


@pytest.fixture
def minimal_scenario(db_session):
    """Минимальный сценарий: команда, два сотрудника, две задачи (одна вошла, одна нет)."""
    db_session.add_all([
        Role(code="dev", label="Разработчик", color="#1890FF",
             is_active=True, counts_in_planning=True),
        Role(code="analyst", label="Аналитик", color="#722ED1",
             is_active=True, counts_in_planning=True),
        MandatoryWorkType(code="org", label="Орг. вопросы",
                          is_active=True, subtracts_from_pool=True),
    ])
    db_session.flush()

    dave = Employee(
        jira_account_id="d1", display_name="Dave", role="dev", is_active=True,
    )
    alice = Employee(
        jira_account_id="a1", display_name="Alice", role="analyst", is_active=True,
    )
    db_session.add_all([dave, alice])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=dave.id, team="Alpha", is_primary=True),
        EmployeeTeam(employee_id=alice.id, team="Alpha", is_primary=True),
    ])

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


class TestStructure:
    def test_workbook_has_four_sheets_in_order(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == EXPECTED_SHEETS

    def test_unknown_scenario_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ScenarioXlsxExporter(db_session, "no-such-id").build()
```

- [ ] **Step 2.4: Run.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 2 passed. The 4 sheets exist (empty) and the workbook saves.

If `test_export_service.py::TestScenarioXlsx` runs and fails (it will — it expects 7 sheets), that's fine; we fix it in Task 7.

- [ ] **Step 2.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "refactor(export): collapse to 4 empty sheet stubs (Бухгалтерия structure)"
```

---

## Task 3: Implement `_sheet_summary` — section 1 «Сводка»

**Goal:** First section of the Сводка sheet — title strip, subtitle, and the 2×8 metrics table. Don't touch sections 2 and 3 yet.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `_sheet_summary`, possibly add helper for section headers.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestSummaryHeader`.

**Spec reference:** § "Лист 1: Сводка" → "Раздел «Сводка»".

- [ ] **Step 3.1: Add the test.**

Append to `tests/test_scenario_xlsx_export.py`:

```python
class TestSummaryHeader:
    def test_title_strip_in_a1(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        a1 = ws.cell(row=1, column=1).value or ""
        assert "Q2 2026 Alpha Base" in a1
        assert "черновик" in a1

    def test_subtitle_in_a2(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        a2 = ws.cell(row=2, column=1).value or ""
        assert "Q2" in a2
        assert "2026" in a2
        assert "Alpha" in a2
        assert "сформировано" in a2.lower()

    def test_summary_section_header_at_a4(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        assert ws.cell(row=4, column=1).value == "СВОДКА"

    def test_summary_metrics_table(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        # Row 5 labels
        assert ws.cell(row=5, column=1).value == "Ёмкость, ч"
        assert ws.cell(row=5, column=3).value == "План, ч"
        assert ws.cell(row=5, column=5).value == "Остаток, ч"
        assert ws.cell(row=5, column=7).value == "Использование"
        # Row 6 labels
        assert ws.cell(row=6, column=1).value == "Включено, шт."
        assert ws.cell(row=6, column=3).value == "Не вошло, шт."
        assert ws.cell(row=6, column=5).value == "QA дефицит, ч"
        assert ws.cell(row=6, column=7).value == "Отсутствия, ч"
        # Counts (row 6 col 2 — included = 1, col 4 — excluded = 1)
        assert ws.cell(row=6, column=2).value == 1
        assert ws.cell(row=6, column=4).value == 1
```

- [ ] **Step 3.2: Run — expect failures.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py::TestSummaryHeader -v
```
Expected: 4 failures (sheet is empty).

- [ ] **Step 3.3: Add a helper for the title strip and section headers.**

Add at the module level (next to the existing helpers):

```python
def _write_title_strip(ws, text: str, *, columns: int = 8) -> None:
    """Dark-grey header strip merged across N columns, white bold text."""
    cell = ws.cell(row=1, column=1, value=text)
    cell.font = _Style.STRIP_FONT
    cell.fill = _Style.HEADER_FILL
    cell.alignment = _Style.LEFT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    ws.row_dimensions[1].height = 22


def _write_subtitle(ws, text: str, *, row: int = 2, columns: int = 8) -> None:
    """Light-grey subtitle row below the title strip."""
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = _Style.LABEL_FONT
    cell.fill = _Style.SECTION_FILL
    cell.alignment = _Style.LEFT
    ws.merge_cells(
        start_row=row, start_column=1, end_row=row, end_column=columns,
    )


def _write_section_header(ws, row: int, text: str, *, columns: int = 8) -> None:
    """`СЕКЦИЯ` row with grey fill + dark bottom border, merged."""
    cell = ws.cell(row=row, column=1, value=text.upper())
    cell.font = _Style.SECTION_FONT
    cell.fill = _Style.SECTION_FILL
    cell.alignment = _Style.LEFT
    cell.border = _Style.SECTION_BORDER
    ws.merge_cells(
        start_row=row, start_column=1, end_row=row, end_column=columns,
    )
```

- [ ] **Step 3.4: Implement `_sheet_summary` (section 1 only).**

Replace the `_sheet_summary` stub:

```python
def _sheet_summary(self, ws, ctx: ScenarioExportContext) -> None:
    ws.sheet_view.showGridLines = False
    summary = ctx.resource_summary

    # --- Title strip + subtitle ---
    status_label = "утверждён" if ctx.scenario.status == "approved" else "черновик"
    title = f"Сценарий: {ctx.scenario.name} — {status_label}"
    _write_title_strip(ws, title, columns=8)

    subtitle = (
        f"{ctx.scenario.quarter or ''} "
        f"{ctx.scenario.year or ''} · команда «{ctx.scenario.team or '—'}» · "
        f"сформировано {ctx.generated_at:%d.%m.%Y}"
    ).strip()
    _write_subtitle(ws, subtitle, row=2, columns=8)

    # --- Section 1: Сводка metrics 2×8 ---
    _write_section_header(ws, row=4, text="Сводка", columns=8)

    # Compute metrics
    total_capacity = round(summary.available_total, 1)
    planned_by_role = self._planned_hours_by_role(ctx)
    total_planned = round(sum(planned_by_role.values()), 1)
    leftover = round(max(0.0, total_capacity - total_planned), 1)
    included_n = sum(1 for a in ctx.allocations if a.included_flag)
    excluded_n = sum(1 for a in ctx.allocations if not a.included_flag)
    qa_avail = summary.available_by_role.get("qa", 0.0)
    qa_planned = planned_by_role.get("qa", 0.0)
    qa_deficit = round(min(0.0, qa_avail - qa_planned), 1)
    usage_pct = (
        round(total_planned / total_capacity, 4) if total_capacity > 0 else 0.0
    )
    absences_total_hours = round(
        sum(_absence_hours_in_period(a, ctx) for a in ctx.absences), 1,
    )

    # Row 5
    pairs_5 = [
        ("Ёмкость, ч", total_capacity, "#,##0"),
        ("План, ч", total_planned, "#,##0"),
        ("Остаток, ч", leftover, "#,##0"),
        ("Использование", usage_pct, "0%"),
    ]
    for i, (label, value, fmt) in enumerate(pairs_5):
        col = 1 + i * 2
        l = ws.cell(row=5, column=col, value=label)
        l.font = _Style.LABEL_FONT
        l.alignment = _Style.LEFT
        v = ws.cell(row=5, column=col + 1, value=value)
        v.font = _Style.BOLD_FONT
        v.alignment = _Style.RIGHT
        v.number_format = fmt
    # Usage % conditional fill (col 8)
    if total_capacity > 0:
        v = ws.cell(row=5, column=8)
        if usage_pct < 0.8:
            v.fill = _Style.GREEN_BG
        elif usage_pct <= 1.10:
            v.fill = _Style.YELLOW_BG
        else:
            v.fill = _Style.RED_BG
            v.font = _Style.RED_BOLD_FONT

    # Row 6
    pairs_6 = [
        ("Включено, шт.", included_n, "#,##0"),
        ("Не вошло, шт.", excluded_n, "#,##0"),
        ("QA дефицит, ч", qa_deficit, "#,##0"),
        ("Отсутствия, ч", absences_total_hours, "#,##0"),
    ]
    for i, (label, value, fmt) in enumerate(pairs_6):
        col = 1 + i * 2
        l = ws.cell(row=6, column=col, value=label)
        l.font = _Style.LABEL_FONT
        l.alignment = _Style.LEFT
        v = ws.cell(row=6, column=col + 1, value=value)
        v.font = _Style.BOLD_FONT
        v.alignment = _Style.RIGHT
        v.number_format = fmt
    # QA дефицит red bold if negative
    if qa_deficit < 0:
        ws.cell(row=6, column=6).font = _Style.RED_BOLD_FONT

    # --- Column widths (preliminary; sections 2-3 will override if needed) ---
    widths = [16, 12, 16, 12, 16, 12, 16, 12]
    for c_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ws.freeze_panes = "A4"
```

- [ ] **Step 3.5: Add helpers `_planned_hours_by_role` and `_absence_hours_in_period`.**

Add these as module-level functions (or as `@staticmethod` on the class — module-level is simpler):

```python
def _planned_hours_by_role(ctx: ScenarioExportContext) -> dict[str, float]:
    """Запланированные часы по ролям (analyst / dev / qa) — пропорция от _demand_by_role."""
    out: dict[str, float] = {}
    for a in ctx.allocations:
        if not a.included_flag:
            continue
        analyst, dev, qa = _demand_by_role(a.backlog_item)
        total_est = analyst + dev + qa
        if total_est <= 0:
            continue
        p = a.planned_hours or 0.0
        out["analyst"] = out.get("analyst", 0.0) + p * analyst / total_est
        out["dev"] = out.get("dev", 0.0) + p * dev / total_est
        out["qa"] = out.get("qa", 0.0) + p * qa / total_est
    return out


def _absence_hours_in_period(absence, ctx: ScenarioExportContext) -> float:
    """Часов отсутствия, попадающих в квартал. Использует hours_total если задано."""
    if absence.hours_total is not None:
        return float(absence.hours_total)
    h = 0.0
    cur = max(absence.start_date, ctx.period_start)
    while cur <= absence.end_date and cur < ctx.period_end:
        norm = ctx.calendar_by_date.get(
            cur, 8.0 if cur.weekday() < 5 else 0.0,
        )
        if norm > 0:
            h += norm
        cur = cur + timedelta(days=1)
    return round(h, 1)
```

`_planned_hours_by_role` is a module-level function but `_sheet_summary` calls it as `self._planned_hours_by_role(ctx)`. Fix: change the call to `_planned_hours_by_role(ctx)` (no self).

- [ ] **Step 3.6: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 6 passed (Structure × 2 + SummaryHeader × 4).

- [ ] **Step 3.7: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): Сводка sheet — title strip + subtitle + metrics table (2x8)"
```

---

## Task 4: Implement `_sheet_summary` — section 2 «По ролям × месяцам»

**Goal:** Add the role × months matrix to the Сводка sheet (rows 8 onwards, dynamically positioned).

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — extend `_sheet_summary`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestSummaryByRoleMonths`.

**Spec reference:** § "Раздел «По ролям × месяцам»".

- [ ] **Step 4.1: Add the test.**

```python
class TestSummaryByRoleMonths:
    def test_section_header_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        # Search for "ПО РОЛЯМ × МЕСЯЦАМ" in column A
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert any(v and "ПО РОЛЯМ" in str(v) and "МЕСЯЦАМ" in str(v) for v in labels)

    def test_role_table_headers_for_q2(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        # Find row containing the header "Роль"
        header_row = None
        for r in range(1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Роль":
                header_row = r
                break
        assert header_row is not None
        # Q2 → Apr, May, Jun
        headers = [ws.cell(row=header_row, column=c).value for c in range(1, 9)]
        assert headers == ["Роль", "Апр", "Май", "Июн", "Σ Ёмкость", "План", "Остаток", "% исп."]

    def test_role_row_dev_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        # Search column A for "Разработчик"
        found = False
        for r in range(1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Разработчик":
                found = True
                # planned column (col 6) should be 80.0 (single allocation)
                assert ws.cell(row=r, column=6).value == pytest.approx(80.0)
                break
        assert found

    def test_totals_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        # Search for "ИТОГО" in column A
        labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "ИТОГО" in [str(v) for v in labels if v is not None]
```

- [ ] **Step 4.2: Run — expect 4 failures.**

- [ ] **Step 4.3: Add helper for per-role × month aggregation.**

Module-level:

```python
def _per_role_per_month(ctx: ScenarioExportContext) -> dict[tuple[str, int], float]:
    """role_code -> month -> доступные часы (после вычета отсутствий)."""
    out: dict[tuple[str, int], float] = {}
    for emp in ctx.resource_base.employees:
        if not emp.role:
            continue
        for d in emp.days:
            key = (emp.role, d.date.month)
            out[key] = out.get(key, 0.0) + d.hours
    # External QA override: spread evenly across the quarter's 3 months.
    if ctx.scenario.external_qa_hours is not None:
        months = QUARTER_MONTHS[ctx.resource_base.quarter]
        ext = float(ctx.scenario.external_qa_hours)
        per_month = round(ext / 3.0, 1)
        out[("qa", months[0])] = per_month
        out[("qa", months[1])] = per_month
        # Last month gets the remainder so the total matches exactly.
        out[("qa", months[2])] = round(ext - per_month * 2, 1)
    return out
```

- [ ] **Step 4.4: Extend `_sheet_summary` to render section 2.**

At the end of the existing `_sheet_summary` (right before `ws.freeze_panes = "A4"`), insert:

```python
    # --- Section 2: По ролям × месяцам ---
    section2_row = 8
    _write_section_header(ws, row=section2_row, text="По ролям × месяцам", columns=8)

    months = QUARTER_MONTHS[int(str(ctx.scenario.quarter or "Q1").replace("Q", ""))]
    month_labels = [MONTH_LABELS[m] for m in months]

    header_row = section2_row + 1
    headers_2 = ["Роль", *month_labels, "Σ Ёмкость", "План", "Остаток", "% исп."]
    for c_idx, h in enumerate(headers_2, start=1):
        c = ws.cell(row=header_row, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER if c_idx > 1 else _Style.LEFT

    role_month = _per_role_per_month(ctx)
    planned_by_role = _planned_hours_by_role(ctx)

    # Sum totals for the ИТОГО row
    total_per_month = [0.0, 0.0, 0.0]
    total_capacity_sum = 0.0
    total_planned_sum = 0.0

    r_idx = header_row + 1
    for role in summary.roles:
        role_label = (
            ctx.roles_by_code[role].label if role in ctx.roles_by_code else role
        )
        ws.cell(row=r_idx, column=1, value=role_label).font = _Style.BOLD_FONT

        # Monthly columns
        m_sum = 0.0
        for i, m in enumerate(months):
            v = round(role_month.get((role, m), 0.0), 1)
            cell = ws.cell(row=r_idx, column=2 + i, value=v)
            cell.alignment = _Style.RIGHT
            cell.number_format = "#,##0"
            m_sum += v
            total_per_month[i] += v

        capacity = summary.available_by_role.get(role, 0.0)
        ws.cell(row=r_idx, column=5, value=round(capacity, 1)).number_format = "#,##0"
        ws.cell(row=r_idx, column=5).font = _Style.BOLD_FONT
        ws.cell(row=r_idx, column=5).alignment = _Style.RIGHT
        total_capacity_sum += capacity

        planned = round(planned_by_role.get(role, 0.0), 1)
        ws.cell(row=r_idx, column=6, value=planned).number_format = "#,##0"
        ws.cell(row=r_idx, column=6).alignment = _Style.RIGHT
        total_planned_sum += planned

        leftover = round(capacity - planned, 1)
        leftover_cell = ws.cell(row=r_idx, column=7, value=leftover)
        leftover_cell.number_format = "#,##0"
        leftover_cell.alignment = _Style.RIGHT
        if leftover < 0:
            leftover_cell.font = _Style.RED_BOLD_FONT

        usage = (planned / capacity) if capacity > 0 else 0.0
        usage_cell = ws.cell(row=r_idx, column=8, value=round(usage, 4))
        usage_cell.number_format = "0%"
        usage_cell.alignment = _Style.RIGHT
        if usage < 0.8:
            usage_cell.fill = _Style.GREEN_BG
        elif usage <= 1.10:
            usage_cell.fill = _Style.YELLOW_BG
        else:
            usage_cell.fill = _Style.RED_BG
            usage_cell.font = _Style.RED_BOLD_FONT

        r_idx += 1

    # ИТОГО row
    total_row_idx = r_idx
    total_cell = ws.cell(row=total_row_idx, column=1, value="ИТОГО")
    total_cell.font = _Style.BOLD_FONT
    total_cell.fill = _Style.TOTALS_FILL
    total_cell.border = _Style.TOTALS_BORDER
    for i, v in enumerate(total_per_month):
        c = ws.cell(row=total_row_idx, column=2 + i, value=round(v, 1))
        c.font = _Style.BOLD_FONT
        c.fill = _Style.TOTALS_FILL
        c.border = _Style.TOTALS_BORDER
        c.number_format = "#,##0"
        c.alignment = _Style.RIGHT
    for c_idx, value in [
        (5, round(total_capacity_sum, 1)),
        (6, round(total_planned_sum, 1)),
        (7, round(total_capacity_sum - total_planned_sum, 1)),
    ]:
        c = ws.cell(row=total_row_idx, column=c_idx, value=value)
        c.font = _Style.BOLD_FONT
        c.fill = _Style.TOTALS_FILL
        c.border = _Style.TOTALS_BORDER
        c.number_format = "#,##0"
        c.alignment = _Style.RIGHT
    total_usage = (
        total_planned_sum / total_capacity_sum if total_capacity_sum > 0 else 0.0
    )
    c = ws.cell(row=total_row_idx, column=8, value=round(total_usage, 4))
    c.font = _Style.BOLD_FONT
    c.fill = _Style.TOTALS_FILL
    c.border = _Style.TOTALS_BORDER
    c.number_format = "0%"
    c.alignment = _Style.RIGHT

    # Stash the next free row in a local variable for section 3
    self._summary_next_row = total_row_idx + 2  # blank gap then section 3
```

(The trailing `self._summary_next_row` lets section 3 know where to start. We'll use it in Task 5.)

- [ ] **Step 4.5: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 10 passed.

- [ ] **Step 4.6: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): Сводка sheet — section «По ролям × месяцам» with totals"
```

---

## Task 5: Implement `_sheet_summary` — section 3 «По сотрудникам»

**Goal:** Add the per-employee table to the Сводка sheet, sorted by team → role → name.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — extend `_sheet_summary`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestSummaryByEmployee`.

**Spec reference:** § "Раздел «По сотрудникам»".

- [ ] **Step 5.1: Add the test.**

```python
class TestSummaryByEmployee:
    def test_section_header_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        labels = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
        assert any("ПО СОТРУДНИКАМ" in l for l in labels)

    def test_employee_table_headers(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        emp_header_row = None
        for r in range(1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Сотрудник":
                emp_header_row = r
                break
        assert emp_header_row is not None
        headers = [ws.cell(row=emp_header_row, column=c).value for c in range(1, 7)]
        assert headers == [
            "Сотрудник", "Роль", "Норма, ч", "Отсутствия, ч",
            "Доступно, ч", "Дней отсутствия",
        ]

    def test_dave_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Сводка"]
        found = False
        for r in range(1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Dave":
                found = True
                assert ws.cell(row=r, column=2).value == "Разработчик"
                # Available hours > 0 (we have a calendar fallback to 8h Mon-Fri)
                assert (ws.cell(row=r, column=5).value or 0) > 0
                break
        assert found
```

- [ ] **Step 5.2: Run — expect failures.**

- [ ] **Step 5.3: Extend `_sheet_summary` with section 3.**

Append to the body of `_sheet_summary`, right before the existing `ws.freeze_panes = "A4"` line (and remove the stashed `self._summary_next_row` write — use a local variable instead):

Replace the trailing `self._summary_next_row = total_row_idx + 2` with:

```python
    # --- Section 3: По сотрудникам ---
    section3_row = total_row_idx + 2
    _write_section_header(ws, row=section3_row, text="По сотрудникам", columns=8)

    emp_header_row = section3_row + 1
    emp_headers = [
        "Сотрудник", "Роль", "Норма, ч", "Отсутствия, ч",
        "Доступно, ч", "Дней отсутствия",
    ]
    for c_idx, h in enumerate(emp_headers, start=1):
        c = ws.cell(row=emp_header_row, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER if c_idx > 1 else _Style.LEFT

    base_by_id = {e.employee_id: e for e in ctx.resource_base.employees}

    rows = []
    for emp in ctx.employees:
        role_label = (
            ctx.roles_by_code[emp.role].label
            if emp.role and emp.role in ctx.roles_by_code else (emp.role or "—")
        )
        base = base_by_id.get(emp.id)
        # Calendar gross for this employee
        cal_gross = 0.0
        cur = ctx.period_start
        while cur < ctx.period_end:
            cal_gross += ctx.calendar_by_date.get(
                cur, 8.0 if cur.weekday() < 5 else 0.0,
            )
            cur = cur + timedelta(days=1)

        available = base.total_hours if base else 0.0
        # Absence days = working days in period overlapping any absence
        emp_abs = [a for a in ctx.absences if a.employee_id == emp.id]
        abs_days = 0
        cur = ctx.period_start
        while cur < ctx.period_end:
            norm = ctx.calendar_by_date.get(
                cur, 8.0 if cur.weekday() < 5 else 0.0,
            )
            if norm > 0:
                if any(a.start_date <= cur <= a.end_date for a in emp_abs):
                    abs_days += 1
            cur = cur + timedelta(days=1)
        absence_hours = round(cal_gross - available, 1)

        rows.append({
            "name": emp.display_name,
            "role": role_label,
            "norm": round(cal_gross, 1),
            "absence": absence_hours,
            "available": round(available, 1),
            "abs_days": abs_days,
        })

    rows.sort(key=lambda r: (r["role"], r["name"]))

    r_idx = emp_header_row + 1
    for row in rows:
        ws.cell(row=r_idx, column=1, value=row["name"])
        ws.cell(row=r_idx, column=2, value=row["role"])
        for c_idx, key, fmt in [
            (3, "norm", "#,##0"),
            (4, "absence", "#,##0"),
            (5, "available", "#,##0"),
        ]:
            c = ws.cell(row=r_idx, column=c_idx, value=row[key])
            c.number_format = fmt
            c.alignment = _Style.RIGHT
        ws.cell(row=r_idx, column=5).font = _Style.BOLD_FONT
        days_cell = ws.cell(row=r_idx, column=6, value=row["abs_days"])
        days_cell.alignment = _Style.RIGHT
        if 6 <= row["abs_days"] <= 15:
            days_cell.fill = _Style.YELLOW_BG
        elif row["abs_days"] > 15:
            days_cell.fill = _Style.RED_BG
        r_idx += 1
```

- [ ] **Step 5.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 13 passed.

- [ ] **Step 5.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): Сводка sheet — section «По сотрудникам» (norm/absence/available/days)"
```

---

## Task 6: Implement `_sheet_included` — Mid-11 columns

**Goal:** Render the included initiatives table with 11 columns (no `cost_type` / `opo_analyst_ratio` / `involvement_coefficient`), heatmap on hours, totals row, autofilter.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `_sheet_included`, helper `_initiative_row_mid` (Mid-11 version).
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestIncludedSheet`.

**Spec reference:** § "Лист 2: Включено — Mid-11".

- [ ] **Step 6.1: Add the test.**

```python
INCLUDED_HEADERS_MID = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "План, ч", "Цели",
]


class TestIncludedSheet:
    def test_title_strip(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        a1 = ws.cell(row=1, column=1).value or ""
        assert "Q2 2026 Alpha Base" in a1
        assert "Включено" in a1
        assert "1" in a1  # the count "(1 задач)"

    def test_headers_in_row_2(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        header = [ws.cell(row=2, column=c).value for c in range(1, 12)]
        assert header == INCLUDED_HEADERS_MID

    def test_data_row_for_build_feature(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        # Row 3 = first data row
        assert ws.cell(row=3, column=2).value == "Build feature"
        assert ws.cell(row=3, column=3).value == 1
        assert ws.cell(row=3, column=6).value == pytest.approx(80.0)
        assert ws.cell(row=3, column=9).value == pytest.approx(80.0)  # Итого
        assert ws.cell(row=3, column=10).value == pytest.approx(80.0)  # План

    def test_totals_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        last = ws.max_row
        assert "ИТОГО" in str(ws.cell(row=last, column=1).value or "")
        assert ws.cell(row=last, column=9).value == pytest.approx(80.0)

    def test_autofilter_set(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        assert ws.auto_filter.ref is not None

    def test_freeze_panes_a3(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Включено"]
        # Title strip in row 1, headers in row 2 → freeze at A3 so both stay
        assert ws.freeze_panes == "A3"
```

- [ ] **Step 6.2: Run — expect failures.**

- [ ] **Step 6.3: Add `_initiative_row_mid` helper.**

Module-level (replacing or alongside the old `_initiative_row` — old one can stay if it's used elsewhere; check, then keep or delete):

```python
INCLUDED_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "План, ч", "Цели",
]
INCLUDED_WIDTHS = [14, 50, 8, 18, 11, 11, 11, 11, 12, 12, 28]

EXCLUDED_HEADERS = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "Цели",
]
EXCLUDED_WIDTHS = [14, 50, 8, 18, 11, 11, 11, 11, 12, 28]


def _initiative_row_mid(alloc, *, included: bool) -> list:
    item = alloc.backlog_item
    issue = getattr(item, "issue", None)
    key = issue.key if issue else ""
    analyst, dev, qa = _demand_by_role(item)
    opo = item.estimate_opo_hours or 0.0
    total = round(analyst + dev + qa + opo, 1)
    goals = (issue.goals or "") if issue else ""
    base = [
        key,
        item.title,
        item.priority,
        item.customer or "",
        round(analyst, 1),
        round(dev, 1),
        round(qa, 1),
        round(opo, 1),
        total,
    ]
    if included:
        base.append(round(alloc.planned_hours or 0.0, 1))
    base.append(goals)
    return base
```

- [ ] **Step 6.4: Implement `_sheet_included`.**

Replace the `_sheet_included` stub:

```python
def _sheet_included(self, ws, ctx: ScenarioExportContext) -> None:
    from openpyxl.formatting.rule import ColorScaleRule, CellIsRule

    ws.sheet_view.showGridLines = False

    rows = sorted(
        [a for a in ctx.allocations if a.included_flag],
        key=lambda a: (
            a.backlog_item.priority is None,
            a.backlog_item.priority if a.backlog_item.priority is not None else 0,
            a.backlog_item.title,
        ),
    )

    # Title strip
    status = "утверждён" if ctx.scenario.status == "approved" else "черновик"
    title = (
        f"Сценарий: {ctx.scenario.name} — {status} · "
        f"Включено ({len(rows)} задач)"
    )
    _write_title_strip(ws, title, columns=len(INCLUDED_HEADERS))

    # Header row at row 2
    for c_idx, h in enumerate(INCLUDED_HEADERS, start=1):
        c = ws.cell(row=2, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[2].height = 22

    # Data rows
    for r_idx, alloc in enumerate(rows, start=3):
        values = _initiative_row_mid(alloc, included=True)
        for c_idx, val in enumerate(values, start=1):
            c = ws.cell(row=r_idx, column=c_idx, value=val)
            if c_idx in (5, 6, 7, 8):
                c.number_format = "#,##0.#"
                c.alignment = _Style.RIGHT
            elif c_idx == 3:
                c.alignment = _Style.CENTER
                if val == 1:
                    c.font = _Style.PRI1_FONT
                elif val == 2:
                    c.font = _Style.PRI2_FONT
            elif c_idx == 9:
                c.font = _Style.BOLD_FONT
                c.number_format = "#,##0.#"
                c.alignment = _Style.RIGHT
                c.fill = PatternFill("solid", fgColor="EFF6FF")
            elif c_idx == 10:
                c.font = _Style.BOLD_FONT
                c.number_format = "#,##0.#"
                c.alignment = _Style.RIGHT

        # Hyperlink on key column
        key = values[0]
        if key and ctx.jira_base_url:
            link = f"{ctx.jira_base_url.rstrip('/')}/browse/{key}"
            ws.cell(row=r_idx, column=1).hyperlink = link
            ws.cell(row=r_idx, column=1).font = _Style.LINK_FONT

    # Totals row
    total_row_idx = len(rows) + 3
    total_label = ws.cell(row=total_row_idx, column=1, value=f"Σ ИТОГО ({len(rows)} задач)")
    total_label.font = _Style.HEADER_FONT
    total_label.fill = _Style.HEADER_FILL
    ws.merge_cells(
        start_row=total_row_idx, start_column=1,
        end_row=total_row_idx, end_column=4,
    )
    sum_cols = [5, 6, 7, 8, 9, 10]
    for c_idx in sum_cols:
        if rows:
            total = sum(_initiative_row_mid(a, included=True)[c_idx - 1] for a in rows)
        else:
            total = 0
        c = ws.cell(row=total_row_idx, column=c_idx, value=round(total, 1))
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.number_format = "#,##0.#"
        c.alignment = _Style.RIGHT
    # Empty cell for "Цели" column to keep the strip continuous
    c = ws.cell(row=total_row_idx, column=11, value="")
    c.fill = _Style.HEADER_FILL

    # Heatmap on hours columns 5-8 (only if there are rows)
    if rows:
        for c_idx in (5, 6, 7, 8):
            col = get_column_letter(c_idx)
            rng = f"{col}3:{col}{total_row_idx - 1}"
            ws.conditional_formatting.add(
                rng,
                ColorScaleRule(
                    start_type="min", start_color=_Style.HEAT_LIGHT,
                    end_type="max", end_color=_Style.HEAT_DARK,
                ),
            )

    # Column widths
    for c_idx, w in enumerate(INCLUDED_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ws.freeze_panes = "A3"
    if rows:
        ws.auto_filter.ref = f"A2:{get_column_letter(len(INCLUDED_HEADERS))}{total_row_idx}"
    else:
        # Empty case — still set autofilter on header + totals row, no data rows
        ws.auto_filter.ref = f"A2:{get_column_letter(len(INCLUDED_HEADERS))}2"
```

- [ ] **Step 6.5: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 19 passed.

- [ ] **Step 6.6: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): «Включено» sheet — Mid-11 columns + heatmap + totals strip"
```

---

## Task 7: Implement `_sheet_excluded` — Mid-10 columns

**Goal:** Render the excluded initiatives table — same as `_sheet_included` but without the «План, ч» column, all data rows get grey fill (`#FAFAFA`), text in «Название» / «Цели» columns is grey.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `_sheet_excluded`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestExcludedSheet`.

**Spec reference:** § "Лист 3: Не вошло".

- [ ] **Step 7.1: Add the test.**

```python
EXCLUDED_HEADERS_EXPECTED = [
    "Ключ Jira", "Название", "Приоритет", "Заказчик",
    "Аналитик, ч", "Разработка, ч", "QA, ч", "ОПЭ, ч",
    "Итого, ч", "Цели",
]


class TestExcludedSheet:
    def test_title_strip(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        a1 = ws.cell(row=1, column=1).value or ""
        assert "Не вошло" in a1
        assert "1" in a1

    def test_headers_no_plan_column(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        header = [ws.cell(row=2, column=c).value for c in range(1, 11)]
        assert header == EXCLUDED_HEADERS_EXPECTED

    def test_excluded_row_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        assert ws.cell(row=3, column=2).value == "Skipped feature"

    def test_data_rows_have_grey_fill(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Не вошло"]
        cell = ws.cell(row=3, column=2)
        assert cell.fill.fgColor.value.upper().endswith("FAFAFA")
```

- [ ] **Step 7.2: Run — expect failures.**

- [ ] **Step 7.3: Implement `_sheet_excluded`.**

Replace the `_sheet_excluded` stub:

```python
def _sheet_excluded(self, ws, ctx: ScenarioExportContext) -> None:
    from openpyxl.formatting.rule import ColorScaleRule

    ws.sheet_view.showGridLines = False

    rows = sorted(
        [a for a in ctx.allocations if not a.included_flag],
        key=lambda a: (
            a.backlog_item.priority is None,
            a.backlog_item.priority if a.backlog_item.priority is not None else 0,
            a.backlog_item.title,
        ),
    )

    title = f"Сценарий: {ctx.scenario.name} · Не вошло ({len(rows)} задач)"
    _write_title_strip(ws, title, columns=len(EXCLUDED_HEADERS))

    for c_idx, h in enumerate(EXCLUDED_HEADERS, start=1):
        c = ws.cell(row=2, column=c_idx, value=h)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    ws.row_dimensions[2].height = 22

    for r_idx, alloc in enumerate(rows, start=3):
        values = _initiative_row_mid(alloc, included=False)
        for c_idx, val in enumerate(values, start=1):
            c = ws.cell(row=r_idx, column=c_idx, value=val)
            c.fill = _Style.GREY_BG
            if c_idx in (5, 6, 7, 8):
                c.number_format = "#,##0.#"
                c.alignment = _Style.RIGHT
            elif c_idx == 3:
                c.alignment = _Style.CENTER
            elif c_idx == 9:
                c.font = _Style.BOLD_FONT
                c.number_format = "#,##0.#"
                c.alignment = _Style.RIGHT
            elif c_idx in (2, 10):
                # Title and goals — grey text for excluded rows
                c.font = _Style.EXCLUDED_FONT
        # Hyperlink on key column
        key = values[0]
        if key and ctx.jira_base_url:
            link = f"{ctx.jira_base_url.rstrip('/')}/browse/{key}"
            ws.cell(row=r_idx, column=1).hyperlink = link
            ws.cell(row=r_idx, column=1).font = _Style.LINK_FONT

    # Totals row
    total_row_idx = len(rows) + 3
    total_label = ws.cell(
        row=total_row_idx, column=1,
        value=f"Σ ИТОГО ({len(rows)} задач не вошло)",
    )
    total_label.font = _Style.HEADER_FONT
    total_label.fill = _Style.HEADER_FILL
    ws.merge_cells(
        start_row=total_row_idx, start_column=1,
        end_row=total_row_idx, end_column=4,
    )
    sum_cols = [5, 6, 7, 8, 9]
    for c_idx in sum_cols:
        if rows:
            total = sum(_initiative_row_mid(a, included=False)[c_idx - 1] for a in rows)
        else:
            total = 0
        c = ws.cell(row=total_row_idx, column=c_idx, value=round(total, 1))
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.number_format = "#,##0.#"
        c.alignment = _Style.RIGHT
    c = ws.cell(row=total_row_idx, column=10, value="")
    c.fill = _Style.HEADER_FILL

    # Heatmap on hours
    if rows:
        for c_idx in (5, 6, 7, 8):
            col = get_column_letter(c_idx)
            rng = f"{col}3:{col}{total_row_idx - 1}"
            ws.conditional_formatting.add(
                rng,
                ColorScaleRule(
                    start_type="min", start_color=_Style.HEAT_LIGHT,
                    end_type="max", end_color=_Style.HEAT_DARK,
                ),
            )

    for c_idx, w in enumerate(EXCLUDED_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ws.freeze_panes = "A3"
    if rows:
        ws.auto_filter.ref = f"A2:{get_column_letter(len(EXCLUDED_HEADERS))}{total_row_idx}"
    else:
        ws.auto_filter.ref = f"A2:{get_column_letter(len(EXCLUDED_HEADERS))}2"
```

- [ ] **Step 7.4: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 23 passed.

- [ ] **Step 7.5: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): «Не вошло» sheet — Mid-10 columns with grey row fill"
```

---

## Task 8: Implement `_sheet_reference` — three-section reference page

**Goal:** Implement the Справочник sheet with three sections: rules matrix, external QA, absences.

**Files:**
- Modify: `app/services/scenario_xlsx_export.py` — `_sheet_reference`.
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestReferenceSheet`.

**Spec reference:** § "Лист 4: Справочник".

- [ ] **Step 8.1: Add the test.**

```python
class TestReferenceSheet:
    def test_three_section_headers_present(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Справочник"]
        labels = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
        joined = " ".join(labels)
        assert "ПРАВИЛА" in joined
        assert "ВНЕШНИЙ QA" in joined
        assert "ОТСУТСТВИЯ" in joined

    def test_external_qa_when_set(self, db_session, minimal_scenario):
        scenario = db_session.get(PlanningScenario, minimal_scenario.scenario_id)
        scenario.external_qa_hours = 120.0
        db_session.flush()

        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Справочник"]
        # Find the row where col B has the QA hours value
        qa_value_seen = False
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=2).value
            if v == 120 or v == 120.0 or (isinstance(v, str) and "120" in v):
                qa_value_seen = True
        assert qa_value_seen

    def test_external_qa_when_not_set(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Справочник"]
        all_text = " ".join(
            str(ws.cell(row=r, column=c).value or "")
            for r in range(1, ws.max_row + 1) for c in range(1, 9)
        )
        assert "не задан" in all_text

    def test_no_absences_message(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        ws = wb["Справочник"]
        all_text = " ".join(
            str(ws.cell(row=r, column=c).value or "")
            for r in range(1, ws.max_row + 1) for c in range(1, 9)
        )
        assert "Отсутствий в квартале нет" in all_text

    def test_absences_table_when_present(self, db_session, minimal_scenario):
        from datetime import date as _d
        from app.models import Absence, AbsenceReason
        reason = AbsenceReason(
            code="vac", label="Отпуск", is_planned=True, color="#16A34A",
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
        ws = wb["Справочник"]

        # Find the row with "Dave" in column A
        found = False
        for r in range(1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == "Dave":
                found = True
                # Reason column (3) should say "Отпуск"
                assert ws.cell(row=r, column=3).value == "Отпуск"
        assert found
```

- [ ] **Step 8.2: Run — expect failures.**

- [ ] **Step 8.3: Implement `_sheet_reference`.**

Replace the `_sheet_reference` stub:

```python
def _sheet_reference(self, ws, ctx: ScenarioExportContext) -> None:
    ws.sheet_view.showGridLines = False
    summary = ctx.resource_summary
    sub_wts = [w for w in ctx.work_types if w.subtracts_from_pool]

    # --- Title strip ---
    title = (
        f"Справочник · {ctx.scenario.quarter or ''} {ctx.scenario.year or ''} · "
        f"{ctx.scenario.team or '—'}"
    )
    _write_title_strip(ws, title, columns=8)
    ws.cell(row=2, column=1).value = ""  # blank row 2 for spacing

    # --- Section 1: Правила распределения часов ---
    sec1_row = 4
    _write_section_header(
        ws, row=sec1_row,
        text="1 · Правила распределения часов на обязательные работы",
        columns=8,
    )
    hint = ws.cell(row=sec1_row + 1, column=1, value=(
        "Сколько процентов нормы каждой роли резервируется на обязательные виды работ. "
        "Остаток уходит на инициативы."
    ))
    hint.font = _Style.ITALIC_GREY_FONT
    hint.alignment = _Style.LEFT
    ws.merge_cells(
        start_row=sec1_row + 1, start_column=1,
        end_row=sec1_row + 1, end_column=8,
    )

    # Matrix header
    matrix_header_row = sec1_row + 2
    ws.cell(row=matrix_header_row, column=1, value="Роль").font = _Style.HEADER_FONT
    ws.cell(row=matrix_header_row, column=1).fill = _Style.HEADER_FILL
    ws.cell(row=matrix_header_row, column=1).alignment = _Style.LEFT
    for c_idx, wt in enumerate(sub_wts, start=2):
        c = ws.cell(row=matrix_header_row, column=c_idx, value=wt.label)
        c.font = _Style.HEADER_FONT
        c.fill = _Style.HEADER_FILL
        c.alignment = _Style.CENTER
    sum_col_idx = len(sub_wts) + 2
    c = ws.cell(row=matrix_header_row, column=sum_col_idx, value="Σ обязат.")
    c.font = _Style.HEADER_FONT
    c.fill = _Style.HEADER_FILL
    c.alignment = _Style.CENTER

    # Rule lookup
    rule_lookup: dict[tuple[str, str | None], float] = {}
    for r in ctx.scenario_rules:
        key = (r.work_type_id, r.role)
        rule_lookup[key] = rule_lookup.get(key, 0.0) + r.percent_of_norm

    r_idx = matrix_header_row + 1
    roles_to_render = list(summary.roles)
    has_null_rule = any(rule.role is None for rule in ctx.scenario_rules)
    if has_null_rule:
        roles_to_render.append(None)

    for role in roles_to_render:
        role_label = (
            ctx.roles_by_code[role].label
            if role and role in ctx.roles_by_code else (role or "Все роли")
        )
        ws.cell(row=r_idx, column=1, value=role_label).font = _Style.BOLD_FONT
        sum_pct = 0.0
        gross = summary.gross_by_role.get(role, 0.0) if role else 0.0
        for c_idx, wt in enumerate(sub_wts, start=2):
            pct = rule_lookup.get((wt.id, role))
            if pct is None:
                cell = ws.cell(row=r_idx, column=c_idx, value=None)
                cell.fill = _Style.GREY_BG
                continue
            hours = round(gross * pct / 100.0, 1) if role else None
            text = f"{pct:.0f}%" + (f" · {hours:.0f} ч" if hours is not None else "")
            cell = ws.cell(row=r_idx, column=c_idx, value=text)
            cell.alignment = _Style.RIGHT
            sum_pct += pct
            if pct >= 50:
                cell.fill = PatternFill("solid", fgColor=_Style.HEAT_DARK)
            elif pct >= 25:
                cell.fill = PatternFill("solid", fgColor=_Style.HEAT_MID)
            elif pct >= 10:
                cell.fill = PatternFill("solid", fgColor=_Style.HEAT_LIGHT)
        sum_cell = ws.cell(row=r_idx, column=sum_col_idx, value=f"{sum_pct:.0f}%")
        sum_cell.alignment = _Style.RIGHT
        sum_cell.font = _Style.BOLD_FONT
        if sum_pct > 100:
            sum_cell.font = _Style.RED_BOLD_FONT
        r_idx += 1

    # --- Section 2: Внешний QA-лимит ---
    sec2_row = r_idx + 1
    _write_section_header(ws, row=sec2_row, text="2 · Внешний QA-лимит", columns=8)
    qa_label_cell = ws.cell(
        row=sec2_row + 1, column=1,
        value="Часы внешнего QA, фиксированный лимит на квартал",
    )
    qa_label_cell.alignment = _Style.LEFT
    qa_value = ctx.scenario.external_qa_hours
    if qa_value is None:
        v = ws.cell(row=sec2_row + 1, column=2, value="не задан")
        v.font = _Style.ITALIC_GREY_FONT
    else:
        v = ws.cell(row=sec2_row + 1, column=2, value=round(float(qa_value), 1))
        v.font = _Style.BOLD_FONT
        v.number_format = "#,##0"
    v.alignment = _Style.RIGHT
    note = ws.cell(
        row=sec2_row + 2, column=1,
        value="Замещает суммарную ёмкость штатных QA, если задано",
    )
    note.font = _Style.ITALIC_GREY_FONT

    # --- Section 3: Отсутствия команды ---
    sec3_row = sec2_row + 4
    _write_section_header(
        ws, row=sec3_row, text="3 · Отсутствия команды в квартале", columns=8,
    )

    # Sort absences team → employee → start_date
    emp_by_id = {e.id: e for e in ctx.employees}
    abs_rows = []
    for a in ctx.absences:
        emp = emp_by_id.get(a.employee_id)
        if emp is None:
            continue
        role_label = (
            ctx.roles_by_code[emp.role].label
            if emp.role and emp.role in ctx.roles_by_code else (emp.role or "—")
        )
        abs_rows.append({
            "name": emp.display_name,
            "role": role_label,
            "reason": a.reason.label if a.reason else "—",
            "color": a.reason.color if a.reason else None,
            "kind": "Плановая" if (a.reason and a.reason.is_planned) else "Внеплановая",
            "is_planned": bool(a.reason and a.reason.is_planned),
            "start": a.start_date,
            "end": a.end_date,
            "days": _absence_days_in_period(a, ctx),
            "hours": _absence_hours_in_period(a, ctx),
        })
    abs_rows.sort(key=lambda r: (r["name"], r["start"]))

    if not abs_rows:
        msg_cell = ws.cell(
            row=sec3_row + 1, column=1, value="Отсутствий в квартале нет",
        )
        msg_cell.font = _Style.ITALIC_GREY_FONT
    else:
        # Header
        abs_header_row = sec3_row + 1
        abs_headers = ["Сотрудник", "Роль", "Причина", "Тип",
                       "Начало", "Конец", "Дней", "Часов"]
        for c_idx, h in enumerate(abs_headers, start=1):
            c = ws.cell(row=abs_header_row, column=c_idx, value=h)
            c.font = _Style.HEADER_FONT
            c.fill = _Style.HEADER_FILL
            c.alignment = _Style.CENTER if c_idx > 1 else _Style.LEFT

        r_idx = abs_header_row + 1
        for row in abs_rows:
            ws.cell(row=r_idx, column=1, value=row["name"])
            ws.cell(row=r_idx, column=2, value=row["role"])
            reason_cell = ws.cell(row=r_idx, column=3, value=row["reason"])
            if row["color"]:
                color_hex = str(row["color"]).lstrip("#").upper()
                reason_cell.fill = PatternFill("solid", fgColor=color_hex)
                reason_cell.font = Font(
                    name="Calibri", size=11, bold=True, color="FFFFFF",
                )
                reason_cell.alignment = _Style.CENTER
            kind_cell = ws.cell(row=r_idx, column=4, value=row["kind"])
            kind_cell.fill = _Style.GREEN_BG if row["is_planned"] else _Style.RED_BG
            kind_cell.alignment = _Style.CENTER
            ws.cell(row=r_idx, column=5, value=row["start"]).number_format = "DD.MM.YYYY"
            ws.cell(row=r_idx, column=6, value=row["end"]).number_format = "DD.MM.YYYY"
            d = ws.cell(row=r_idx, column=7, value=row["days"])
            d.number_format = "#,##0"
            d.alignment = _Style.RIGHT
            h = ws.cell(row=r_idx, column=8, value=row["hours"])
            h.number_format = "#,##0"
            h.alignment = _Style.RIGHT
            if row["hours"] > 80:
                h.fill = _Style.RED_BG
            elif row["hours"] > 40:
                h.fill = _Style.YELLOW_BG
            r_idx += 1
        # Totals row
        total = ws.cell(
            row=r_idx, column=1,
            value=f"Σ ИТОГО ({len(abs_rows)} отсутствий)",
        )
        total.font = _Style.BOLD_FONT
        total.fill = _Style.TOTALS_FILL
        ws.merge_cells(
            start_row=r_idx, start_column=1, end_row=r_idx, end_column=6,
        )
        days_total = sum(r["days"] for r in abs_rows)
        hours_total = sum(r["hours"] for r in abs_rows)
        c = ws.cell(row=r_idx, column=7, value=days_total)
        c.font = _Style.BOLD_FONT
        c.fill = _Style.TOTALS_FILL
        c.alignment = _Style.RIGHT
        c.number_format = "#,##0"
        c = ws.cell(row=r_idx, column=8, value=round(hours_total, 1))
        c.font = _Style.BOLD_FONT
        c.fill = _Style.TOTALS_FILL
        c.alignment = _Style.RIGHT
        c.number_format = "#,##0"

    # --- Column widths ---
    widths = [22, 14, 18, 14, 12, 12, 8, 12]
    for c_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ws.freeze_panes = "A2"
```

- [ ] **Step 8.4: Add `_absence_days_in_period` helper.**

Module-level (next to `_absence_hours_in_period`):

```python
def _absence_days_in_period(absence, ctx: ScenarioExportContext) -> int:
    """Рабочих дней отсутствия, попадающих в квартал."""
    cnt = 0
    cur = max(absence.start_date, ctx.period_start)
    while cur <= absence.end_date and cur < ctx.period_end:
        norm = ctx.calendar_by_date.get(
            cur, 8.0 if cur.weekday() < 5 else 0.0,
        )
        if norm > 0:
            cnt += 1
        cur = cur + timedelta(days=1)
    return cnt
```

- [ ] **Step 8.5: Run tests.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 28 passed.

- [ ] **Step 8.6: Commit.**

```bash
git add app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py
git commit -m "feat(export): «Справочник» sheet — rules matrix + external QA + absences"
```

---

## Task 9: Update `tests/test_export_service.py::TestScenarioXlsx`

**Goal:** Update the legacy ExportService tests to expect the 4-sheet structure.

**Files:**
- Modify: `tests/test_export_service.py:249-291`.

- [ ] **Step 9.1: Replace the `TestScenarioXlsx` class.**

Find `class TestScenarioXlsx:` in `tests/test_export_service.py` and replace the whole class with:

```python
class TestScenarioXlsx:
    def test_workbook_has_four_sheets(self, db_session, scenario_seed):
        from openpyxl import load_workbook

        data = ExportService(db_session).build_scenario_xlsx(
            scenario_seed.scenario_id
        )
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == [
            "Сводка", "Включено", "Не вошло", "Справочник",
        ]

    def test_included_titles_present(self, db_session, scenario_seed):
        from openpyxl import load_workbook

        data = ExportService(db_session).build_scenario_xlsx(
            scenario_seed.scenario_id
        )
        wb = load_workbook(BytesIO(data))
        ws_in = wb["Включено"]
        # Header row 2, data starts row 3
        in_titles = {
            ws_in.cell(row=i, column=2).value
            for i in range(3, ws_in.max_row + 1)
        }
        assert "Redesign login" in in_titles
        assert "Payments v2" in in_titles
        assert "Overflow feature" not in in_titles

        ws_out = wb["Не вошло"]
        out_titles = {
            ws_out.cell(row=i, column=2).value
            for i in range(3, ws_out.max_row + 1)
        }
        assert "Overflow feature" in out_titles

    def test_unknown_scenario_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ExportService(db_session).build_scenario_xlsx("nope")
```

- [ ] **Step 9.2: Run.**

```bash
py -3.10 -m pytest tests/test_export_service.py::TestScenarioXlsx -v
```
Expected: 3 passed.

- [ ] **Step 9.3: Commit.**

```bash
git add tests/test_export_service.py
git commit -m "test(export): update TestScenarioXlsx for 4-sheet Бухгалтерия layout"
```

---

## Task 10: Empty-state resilience

**Goal:** Verify `build()` doesn't crash when the scenario has no allocations / employees / absences / rules.

**Files:**
- Modify: `tests/test_scenario_xlsx_export.py` — add `TestEmpty`.

- [ ] **Step 10.1: Add the test.**

```python
@pytest.fixture
def empty_scenario(db_session):
    """Сценарий-пустышка."""
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
        assert data[:2] == b"PK"
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == EXPECTED_SHEETS

    def test_empty_sections_render_safely(self, db_session, empty_scenario):
        data = ScenarioXlsxExporter(db_session, empty_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        # Сводка — title strip + section headers should still be there
        ws = wb["Сводка"]
        assert ws.cell(row=4, column=1).value == "СВОДКА"
        # Справочник — "Отсутствий в квартале нет" message
        ws_ref = wb["Справочник"]
        all_text = " ".join(
            str(ws_ref.cell(row=r, column=c).value or "")
            for r in range(1, ws_ref.max_row + 1) for c in range(1, 9)
        )
        assert "Отсутствий в квартале нет" in all_text
```

- [ ] **Step 10.2: Run.**

```bash
py -3.10 -m pytest tests/test_scenario_xlsx_export.py -v
```
Expected: 30 passed.

If any sheet crashes on empty input, fix the implementation in `app/services/scenario_xlsx_export.py` — wrap any conditional formatting / autofilter in `if rows:` guards. Do NOT skip the empty test.

- [ ] **Step 10.3: Commit.**

```bash
git add tests/test_scenario_xlsx_export.py app/services/scenario_xlsx_export.py
git commit -m "test(export): empty scenario builds 4-sheet workbook without crashing"
```

---

## Task 11: Final verification

- [ ] **Step 11.1: Full backend test suite.**

```bash
py -3.10 -m pytest tests/ -q
```
Expected: only the 3 pre-existing failures (`test_api_capacity_rules_v2::test_copy_to_quarter_*` × 2, `test_sync_service::test_subtask_before_parent_*`). Zero new failures.

- [ ] **Step 11.2: Lint.**

```bash
ruff check app/services/scenario_xlsx_export.py tests/test_scenario_xlsx_export.py tests/test_export_service.py
```
Fix anything ruff flags.

- [ ] **Step 11.3: Mypy.**

```bash
mypy app/services/scenario_xlsx_export.py
```
Fix typing errors. `# type: ignore[no-untyped-call]` on openpyxl `Workbook()`/`PatternFill()` constructors is acceptable.

- [ ] **Step 11.4: Manual smoke check (optional but recommended).**

Generate a real xlsx from the live DB and open in Excel:

```bash
py -3.10 -c "
from io import BytesIO
from app.database import SessionLocal
from app.services.scenario_xlsx_export import ScenarioXlsxExporter
from app.models import PlanningScenario

db = SessionLocal()
s = db.query(PlanningScenario).first()
if s:
    data = ScenarioXlsxExporter(db, s.id).build()
    open('d:/ClaudeDev/JiraAnalysis/.scratch_redesign.xlsx', 'wb').write(data)
    print('Saved', len(data), 'bytes')
"
```

Open `.scratch_redesign.xlsx` in Excel + LibreOffice. Verify:
- 4 sheets (Сводка / Включено / Не вошло / Справочник).
- Сводка fits on one screen, all three sections visible.
- Title strip is dark grey with white text (not cyan).
- Conditional formatting works (try a scenario with QA over 110 % usage).

Delete the scratch file when done:

```bash
rm d:/ClaudeDev/JiraAnalysis/.scratch_redesign.xlsx
```

- [ ] **Step 11.5: Final commit if anything was polished.**

```bash
git add -A
git commit -m "polish(export): visual fixes after Excel smoke check"
```

(Skip if no polish needed.)

---

## Self-review checklist

- [x] Spec coverage:
  - § Стилистическая база → Task 1.
  - § Структура книги → Task 2.
  - § Лист 1: Сводка → Tasks 3–5.
  - § Лист 2: Включено → Task 6.
  - § Лист 3: Не вошло → Task 7.
  - § Лист 4: Справочник → Task 8.
  - § Не делаем → covered by omission (no graphs / sparklines / comparison sheet are added).
- [x] No `TBD` / placeholders.
- [x] Type names consistent: `ScenarioExportContext`, `_Style`, `INCLUDED_HEADERS`, `EXCLUDED_HEADERS`, `_initiative_row_mid`, `_per_role_per_month`, `_planned_hours_by_role`, `_absence_hours_in_period`, `_absence_days_in_period`.
- [x] Each task is TDD-style (test → red → impl → green → commit).
- [x] Dropped helpers (`_initiative_row` from prior plan) covered by Task 2 explicit deletion of old methods.
- [x] Empty-state guards required by Task 10 — engineer adds them where needed.
