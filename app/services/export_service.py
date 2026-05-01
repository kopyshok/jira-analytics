"""Сервис экспортов отчётов в xlsx / pdf / pptx.

Генерит байты готовых файлов. Эндпоинты оборачивают результат в
StreamingResponse с нужным MIME-типом.

Формат экспортов:
- **Аналитика (xlsx)** — многолистовая книга с агрегатами из
  AnalyticsService (сотрудники/проекты/категории/периоды/переключения).
- **Аналитика (pdf)** — сводный отчёт с теми же таблицами, простой layout.
- **Сценарий (xlsx)** — один лист со сводкой сценария и таблицей
  раскладок.
- **Сценарий (pptx)** — несколько слайдов: титул, ключевые метрики,
  таблица включённых задач, пропущенные задачи.

Все модули импортируются лениво внутри методов, чтобы отсутствие одной
из библиотек не ломало импорт остального проекта.
"""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    BacklogItem,
    PlanningScenario,
    ScenarioAllocation,
)
from app.services.planning_service import PlanningService


@dataclass
class ScenarioExportRow:
    """Строка экспорта сценария (одна запись раскладки)."""

    title: str
    priority: Optional[int]
    estimate_hours: float
    planned_hours: float
    included: bool


class ExportService:
    """Сервис экспортов аналитики и сценариев планирования."""

    def __init__(self, db: Session):
        self.db = db

    # === Helpers ===

    @staticmethod
    def _fmt_period(start: Optional[datetime], end: Optional[datetime]) -> str:
        if not start and not end:
            return "за всё время"
        s = start.strftime("%Y-%m-%d") if start else "…"
        e = end.strftime("%Y-%m-%d") if end else "…"
        return f"{s} — {e}"

    def _collect_analytics(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
    ) -> dict:
        """Собрать все аналитические отчёты за период."""
        analytics = AnalyticsService(self.db)
        kw = dict(
            teams=teams,
            match_employees=match_employees,
            match_issues=match_issues,
        )
        return {
            "by_employee": analytics.hours_by_employee(start, end, **kw),
            "by_project": analytics.hours_by_project(start, end, **kw),
            "by_category": analytics.hours_by_category(start, end, **kw),
            "by_period": analytics.hours_by_period("month", start, end, **kw),
            "switching": analytics.context_switching(start, end, **kw),
        }

    def _load_scenario_rows(
        self, scenario_id: str
    ) -> tuple[PlanningScenario, list[ScenarioExportRow], dict]:
        """Загрузить сценарий и его раскладки, склеив с BacklogItem.

        Возвращает (сценарий, строки_для_экспорта, сводка).
        """
        scenario = self.db.get(PlanningScenario, scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found")

        allocations = (
            self.db.query(ScenarioAllocation, BacklogItem)
            .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .filter(ScenarioAllocation.scenario_id == scenario_id)
            .all()
        )

        rows = [
            ScenarioExportRow(
                title=item.title,
                priority=item.priority,
                estimate_hours=float(item.estimate_hours or 0.0),
                planned_hours=float(alloc.planned_hours or 0.0),
                included=bool(alloc.included_flag),
            )
            for alloc, item in allocations
        ]
        rows.sort(
            key=lambda r: (
                not r.included,
                r.priority is None,
                r.priority if r.priority is not None else 0,
                r.title,
            )
        )

        total_planned = sum(r.planned_hours for r in rows if r.included)
        included = [r for r in rows if r.included]
        skipped = [r for r in rows if not r.included]
        summary = {
            "total_planned_hours": total_planned,
            "included_count": len(included),
            "skipped_count": len(skipped),
        }
        return scenario, rows, summary

    # === Capacity: Excel ===

    def export_capacity_xlsx(self, year: int, quarter: int) -> bytes:
        """Excel-выгрузка квартальной ёмкости команды с группировкой по команде."""
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        from app.services.capacity_service import CapacityService

        MONTH_LABELS = {
            1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
            7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
        }
        Q = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}

        rows = CapacityService(self.db).team_quarter_capacity(year, quarter)

        wb = Workbook()
        ws = wb.active
        ws.title = f"Capacity Q{quarter} {year}"

        bold = Font(bold=True)
        team_fill = PatternFill("solid", fgColor="FFF2E8")
        right = Alignment(horizontal="right")

        months = Q[quarter]
        header: list = ["Сотрудник"]
        for m in months:
            header += [f"{MONTH_LABELS[m]} План", f"{MONTH_LABELS[m]} Факт", f"{MONTH_LABELS[m]} %"]
        header += ["Итого План", "Итого Факт", "Итого %"]
        ws.append(header)
        for c in ws[1]:
            c.font = bold

        groups: dict[str, list] = {}
        for r in rows:
            key = r.team or "__none__"
            groups.setdefault(key, []).append(r)
        ordered_keys = sorted([k for k in groups if k != "__none__"])
        if "__none__" in groups:
            ordered_keys.append("__none__")

        def _pct(plan: float, fact: float) -> str:
            return f"{round(fact / plan * 100)}%" if plan > 0 else "—"

        def _month_value(r, m, attr):
            mc = next((x for x in r.months if x.month == m), None)
            return getattr(mc, attr) if mc else 0.0

        for k in ordered_keys:
            members = groups[k]
            label = "Без команды" if k == "__none__" else k

            team_plan_per_m = [sum(_month_value(r, m, "available_hours") for r in members) for m in months]
            team_fact_per_m = [sum(_month_value(r, m, "fact_hours") for r in members) for m in months]

            team_row: list = [label]
            for plan, fact in zip(team_plan_per_m, team_fact_per_m):
                team_row += [round(plan, 1), round(fact, 1), _pct(plan, fact)]
            total_plan = sum(r.total_available_hours for r in members)
            total_fact = sum(r.total_fact_hours for r in members)
            team_row += [round(total_plan, 1), round(total_fact, 1), _pct(total_plan, total_fact)]
            ws.append(team_row)
            for c in ws[ws.max_row]:
                c.font = bold
                c.fill = team_fill

            for r in members:
                emp_row: list = [r.employee_name]
                for m in months:
                    mc = next((x for x in r.months if x.month == m), None)
                    if mc is None:
                        emp_row += ["", "", ""]
                    else:
                        emp_row += [round(mc.available_hours, 1), round(mc.fact_hours, 1), _pct(mc.available_hours, mc.fact_hours)]
                emp_row += [round(r.total_available_hours, 1), round(r.total_fact_hours, 1), _pct(r.total_available_hours, r.total_fact_hours)]
                ws.append(emp_row)
                for c in ws[ws.max_row][1:]:
                    c.alignment = right

        ws.column_dimensions["A"].width = 28
        for col_letter in "BCDEFGHIJKLM":
            ws.column_dimensions[col_letter].width = 12

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # === Analytics Report: Excel ===

    def export_analytics_report_xlsx(
        self,
        report: "AnalyticsReportResponse",
        visible_columns: list[str],
    ) -> bytes:
        """Плоская xlsx-выгрузка иерархического отчёта Аналитики (по задачам)."""
        from io import BytesIO
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Аналитика"

        base_headers = [
            "Команда", "Роль", "Сотрудник", "Вид работ", "Категория",
            "Ключ", "Заголовок", "Тип", "Статус", "Часы факт",
        ]
        col_label_map = {
            "plan_hours": "Часы план",
            "pct_plan": "% план",
            "pct_total": "% от итога",
            "worklog_count": "Ворклогов",
            "issue_count": "Задач",
            "employee_count": "Сотрудников",
            "avg_worklog_minutes": "Ср.мин",
            "last_worklog_at": "Последний ворклог",
            "assignee_name": "Исполнитель",
        }
        opt_headers = []
        opt_keys = []
        for col in visible_columns:
            label = col_label_map.get(col)
            if label:
                opt_headers.append(label)
                opt_keys.append(col)

        ws.append(base_headers + opt_headers)

        for team in report.teams:
            for role in team.roles:
                for emp in role.employees:
                    for wt in emp.work_types:
                        for cat in wt.categories:
                            for issue in cat.issues:
                                row: list = [
                                    team.team or "Без команды",
                                    role.role_label,
                                    emp.name,
                                    wt.label,
                                    cat.label,
                                    issue.key,
                                    issue.summary,
                                    issue.issue_type,
                                    issue.status,
                                    issue.totals.fact_hours,
                                ]
                                for k in opt_keys:
                                    if k == "plan_hours":
                                        row.append(issue.totals.plan_hours if issue.totals.plan_hours is not None else "")
                                    elif k == "pct_plan":
                                        row.append(issue.totals.pct_plan if issue.totals.pct_plan is not None else "")
                                    elif k == "pct_total":
                                        row.append(issue.totals.pct_total)
                                    elif k == "worklog_count":
                                        row.append(issue.totals.worklog_count)
                                    elif k == "issue_count":
                                        row.append(issue.totals.issue_count)
                                    elif k == "employee_count":
                                        row.append(issue.totals.employee_count)
                                    elif k == "avg_worklog_minutes":
                                        row.append(issue.totals.avg_worklog_minutes)
                                    elif k == "last_worklog_at":
                                        row.append(issue.last_worklog_at.isoformat() if issue.last_worklog_at else "")
                                    elif k == "assignee_name":
                                        row.append(issue.assignee_name or "")
                                    else:
                                        row.append("")
                                ws.append(row)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # === Scenario: Excel ===

    def build_scenario_xlsx(self, scenario_id: str) -> bytes:
        """Собрать xlsx со сводкой и раскладкой сценария — делегирует в ScenarioXlsxExporter."""
        from app.services.scenario_xlsx_export import ScenarioXlsxExporter

        return ScenarioXlsxExporter(self.db, scenario_id).build()

    # === Scenario: PPTX ===

    def build_scenario_pptx(self, scenario_id: str) -> bytes:
        """Собрать презентацию со сводкой сценария."""
        from pptx import Presentation
        from pptx.util import Inches, Pt

        scenario, rows, summary = self._load_scenario_rows(scenario_id)

        quarter_num = int(scenario.quarter.replace("Q", "")) if scenario.quarter else 0
        total_capacity = 0.0
        if scenario.year and quarter_num:
            total_capacity = PlanningService(self.db)._team_capacity_hours(
                scenario.year, quarter_num
            )
        leftover = max(0.0, total_capacity - summary["total_planned_hours"])

        prs = Presentation()
        blank = prs.slide_layouts[6]

        # --- Slide 1: title ---
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9), Inches(2))
        frame = tb.text_frame
        p = frame.paragraphs[0]
        p.text = f"Сценарий: {scenario.name}"
        p.font.size = Pt(36)
        p.font.bold = True
        p2 = frame.add_paragraph()
        p2.text = f"{scenario.quarter or ''} {scenario.year or ''}".strip()
        p2.font.size = Pt(20)

        # --- Slide 2: summary metrics ---
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(0.6))
        tb.text_frame.text = "Ключевые метрики"
        tb.text_frame.paragraphs[0].font.size = Pt(28)
        tb.text_frame.paragraphs[0].font.bold = True

        metrics = [
            ("Ёмкость команды, ч", f"{total_capacity:.1f}"),
            ("Запланировано, ч", f"{summary['total_planned_hours']:.1f}"),
            ("Остаток, ч", f"{leftover:.1f}"),
            ("Включено задач", str(summary["included_count"])),
            ("Пропущено задач", str(summary["skipped_count"])),
        ]
        self._pptx_table(
            slide,
            ["Показатель", "Значение"],
            [list(m) for m in metrics],
            top=Inches(1.3),
            width=Inches(6),
        )

        # --- Slide 3: included items ---
        included_rows = [r for r in rows if r.included]
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(0.6))
        tb.text_frame.text = f"Включено в квартал ({len(included_rows)})"
        tb.text_frame.paragraphs[0].font.size = Pt(24)
        tb.text_frame.paragraphs[0].font.bold = True
        self._pptx_table(
            slide,
            ["Задача", "Приоритет", "План, ч"],
            [
                [
                    r.title[:60],
                    str(r.priority) if r.priority is not None else "—",
                    f"{r.planned_hours:.1f}",
                ]
                for r in included_rows
            ]
            or [["(нет задач)", "", ""]],
            top=Inches(1.2),
            width=Inches(9),
        )

        # --- Slide 4: skipped items ---
        skipped_rows = [r for r in rows if not r.included]
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(0.6))
        tb.text_frame.text = f"Не вошло в квартал ({len(skipped_rows)})"
        tb.text_frame.paragraphs[0].font.size = Pt(24)
        tb.text_frame.paragraphs[0].font.bold = True
        self._pptx_table(
            slide,
            ["Задача", "Приоритет", "Оценка, ч"],
            [
                [
                    r.title[:60],
                    str(r.priority) if r.priority is not None else "—",
                    f"{r.estimate_hours:.1f}",
                ]
                for r in skipped_rows
            ]
            or [["(нет задач)", "", ""]],
            top=Inches(1.2),
            width=Inches(9),
        )

        buf = BytesIO()
        prs.save(buf)
        return buf.getvalue()

    @staticmethod
    def _pptx_table(
        slide, headers: list[str], rows: list[list[str]], *, top, width
    ) -> None:
        from pptx.util import Inches, Pt

        n_rows = len(rows) + 1
        n_cols = len(headers)
        max_rows_on_slide = 15
        n_rows = min(n_rows, max_rows_on_slide + 1)

        table_shape = slide.shapes.add_table(
            n_rows,
            n_cols,
            Inches(0.5),
            top,
            width,
            Inches(0.4 * n_rows),
        )
        table = table_shape.table

        for j, h in enumerate(headers):
            cell = table.cell(0, j)
            cell.text = h
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.size = Pt(12)

        for i, row in enumerate(rows[: max_rows_on_slide], start=1):
            for j, value in enumerate(row):
                cell = table.cell(i, j)
                cell.text = str(value)
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(11)
