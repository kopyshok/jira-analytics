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


class TestScaffold:
    def test_workbook_has_seven_sheets_in_order(self, db_session, minimal_scenario):
        data = ScenarioXlsxExporter(db_session, minimal_scenario.scenario_id).build()
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == EXPECTED_SHEETS

    def test_unknown_scenario_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ScenarioXlsxExporter(db_session, "no-such-id").build()


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
