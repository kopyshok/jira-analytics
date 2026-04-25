"""7-sheet xlsx export for planning scenarios.

See docs/superpowers/specs/2026-04-25-scenario-xlsx-export-design.md
for layout, colours and contents of each sheet.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    ORANGE_BG = PatternFill("solid", fgColor=ORANGE_FILL)
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

    # === Sheets ===

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
                usage_cell.fill = _Style.ORANGE_BG
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

    def _sheet_included(self, ws, ctx: ScenarioExportContext) -> None:
        self._render_initiatives(ws, ctx, included=True)

    def _sheet_excluded(self, ws, ctx: ScenarioExportContext) -> None:
        self._render_initiatives(ws, ctx, included=False)

    def _render_initiatives(
        self, ws, ctx: ScenarioExportContext, *, included: bool,
    ) -> None:
        from openpyxl.formatting.rule import ColorScaleRule, CellIsRule

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
            # Grey fill for excluded sheet rows
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
        if last_row >= 2:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"

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
        if last_row >= 2:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"

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
            while cur <= a.end_date and cur < ctx.period_end:
                norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
                if norm > 0:
                    h += norm
                cur = cur + timedelta(days=1)
            return round(h, 1)

        def days_count(a: Absence) -> int:
            cnt = 0
            cur = max(a.start_date, ctx.period_start)
            while cur <= a.end_date and cur < ctx.period_end:
                norm = cal.get(cur, 8.0 if cur.weekday() < 5 else 0.0)
                if norm > 0:
                    cnt += 1
                cur = cur + timedelta(days=1)
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
