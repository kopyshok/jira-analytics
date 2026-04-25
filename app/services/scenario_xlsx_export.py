"""4-sheet xlsx export for planning scenarios («Бухгалтерия» style).

See docs/superpowers/specs/2026-04-25-scenario-xlsx-export-redesign.md
for layout, colours and contents of each sheet.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Absence, AppSetting, BacklogItem, Employee, EmployeeTeam,
    MandatoryWorkType, PlanningScenario, ProductionCalendarDay, Role,
    ScenarioAllocation, ScenarioRule,
)
from app.services.resource_base_service import (
    ResourceBaseService, ResourceBase, ResourceSummary,
)


SHEET_NAMES = ["Сводка", "Включено", "Не вошло", "Справочник"]

QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}

MONTH_LABELS = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
    7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}


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


@dataclass
class ScenarioExportContext:
    """Single in-memory snapshot used across all 4 sheets."""

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


def _demand_by_role(item: BacklogItem) -> tuple[float, float, float]:
    """Hours by (analyst, dev, qa) accounting for ОПЭ split."""
    ea = item.estimate_analyst_hours or 0.0
    ed = item.estimate_dev_hours or 0.0
    eq = item.estimate_qa_hours or 0.0
    eo = item.estimate_opo_hours or 0.0
    r = item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
    return ea + eo * r, ed + eo * (1.0 - r), eq


def _initiative_row_mid(alloc: ScenarioAllocation, *, included: bool) -> list:
    """Row values for Mid-11 (included) or Mid-10 (excluded) sheets."""
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


def _absence_hours_in_period(absence: Absence, ctx: ScenarioExportContext) -> float:
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


def _absence_days_in_period(absence: Absence, ctx: ScenarioExportContext) -> int:
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
        q = int(str(ctx.scenario.quarter or "Q1").replace("Q", ""))
        months = QUARTER_MONTHS[q]
        ext = float(ctx.scenario.external_qa_hours)
        per_month = round(ext / 3.0, 1)
        out[("qa", months[0])] = per_month
        out[("qa", months[1])] = per_month
        # Last month gets the remainder so the total matches exactly.
        out[("qa", months[2])] = round(ext - per_month * 2, 1)
    return out


class ScenarioXlsxExporter:
    """Build a 4-sheet xlsx for a planning scenario.

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

        self._sheet_summary(wb["Сводка"], ctx)
        self._sheet_included(wb["Включено"], ctx)
        self._sheet_excluded(wb["Не вошло"], ctx)
        self._sheet_reference(wb["Справочник"], ctx)

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
                Absence.employee_id.in_(emp_ids) if emp_ids else False,  # type: ignore[arg-type]
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

    # === Sheets ===

    def _sheet_summary(self, ws, ctx: ScenarioExportContext) -> None:
        pass

    def _sheet_included(self, ws, ctx: ScenarioExportContext) -> None:
        pass

    def _sheet_excluded(self, ws, ctx: ScenarioExportContext) -> None:
        pass

    def _sheet_reference(self, ws, ctx: ScenarioExportContext) -> None:
        pass
