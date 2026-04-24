"""Тесты ResourceBaseService — посуточная матрица ресурса команды."""

from datetime import date

import pytest

from app.models import (
    Absence,
    AbsenceReason,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
)
from app.services.resource_base_service import ResourceBaseService

# ---------------------------------------------------------------------------
# Вспомогательные фикстуры (inline, чтобы тесты были изолированы)
# ---------------------------------------------------------------------------

TEAM = "TestTeam"

# Три понедельника Q1 2026: 5 янв, 12 янв, 19 янв — обычные рабочие дни
MON1 = date(2026, 1, 5)
MON2 = date(2026, 1, 12)
MON3 = date(2026, 1, 19)


def _make_employee(db, *, eid="emp-1", role="analyst") -> Employee:
    e = Employee(
        id=eid,
        jira_account_id=f"jira-{eid}",
        display_name=f"Employee {eid}",
        role=role,
        is_active=True,
    )
    db.add(e)
    db.add(EmployeeTeam(employee_id=eid, team=TEAM, is_primary=True))
    return e


def _make_scenario(db, *, sid="sc-1", external_qa=None) -> PlanningScenario:
    s = PlanningScenario(
        id=sid,
        name="Test Scenario",
        quarter="Q1",
        year=2026,
        team=TEAM,
        status="draft",
        external_qa_hours=external_qa,
    )
    db.add(s)
    return s


def _make_work_type(db, *, wid="wt-1", subtracts=True) -> MandatoryWorkType:
    wt = MandatoryWorkType(
        id=wid,
        code=f"wt_{wid}",
        label=f"WorkType {wid}",
        is_active=True,
        subtracts_from_pool=subtracts,
    )
    db.add(wt)
    return wt


def _make_absence_reason(db, *, rid="ar-1") -> AbsenceReason:
    ar = AbsenceReason(
        id=rid,
        code=f"reason_{rid}",
        label="Отпуск",
        is_planned=True,
        is_active=True,
        sort_order=0,
    )
    db.add(ar)
    return ar


def _seed_calendar_mondays(db) -> None:
    """Явно добавить три понедельника как обычные рабочие дни (8 ч).

    По умолчанию сервис делает fallback Пн-Пт=8, но в тестах чистим таблицу,
    поэтому явная запись гарантирует нужное поведение независимо от fallback.
    """
    for d in (MON1, MON2, MON3):
        db.add(
            ProductionCalendarDay(
                date=d,
                is_workday=True,
                kind="workday",
                hours=8.0,
                source="manual",
            )
        )


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------


def test_resource_base_single_employee_no_absence_no_rules(db_session):
    """Один сотрудник, нет отсутствий, нет правил → 3 дня × 8 ч = 24 ч."""
    _make_employee(db_session, role="analyst")
    scenario = _make_scenario(db_session)
    _seed_calendar_mondays(db_session)
    db_session.flush()

    svc = ResourceBaseService(db_session)
    result = svc.compute(scenario)

    assert len(result.employees) == 1
    emp = result.employees[0]

    # Три понедельника должны присутствовать в посуточном списке
    day_dates = {d.date for d in emp.days}
    assert MON1 in day_dates
    assert MON2 in day_dates
    assert MON3 in day_dates

    # Каждый из трёх дней = 8.0 ч (без вычетов)
    for d in emp.days:
        if d.date in (MON1, MON2, MON3):
            assert d.hours == 8.0

    # Итого по роли
    assert result.role_totals.get("analyst", 0) == emp.total_hours
    # Три дня = 24 ч минимум (в Q1 2026 есть и другие рабочие дни — total > 24)
    assert emp.total_hours > 0.0
    # Явная проверка суммы по нашим трём засеянным дням
    seeded_sum = sum(d.hours for d in emp.days if d.date in (MON1, MON2, MON3))
    assert seeded_sum == 24.0


def test_applies_absence(db_session):
    """Отсутствие на один из трёх понедельников → он пропадает из списка дней."""
    _make_employee(db_session, role="analyst")
    scenario = _make_scenario(db_session)
    _seed_calendar_mondays(db_session)
    reason = _make_absence_reason(db_session)

    # Отсутствие точно на MON1 (включительно — как трактует CapacityService)
    db_session.add(
        Absence(
            id="abs-1",
            employee_id="emp-1",
            start_date=MON1,
            end_date=MON1,
            reason_id=reason.id,
        )
    )
    db_session.flush()

    svc = ResourceBaseService(db_session)
    result = svc.compute(scenario)

    emp = result.employees[0]
    day_dates = {d.date for d in emp.days}

    # MON1 вычтен как день отсутствия
    assert MON1 not in day_dates
    # MON2 и MON3 остались
    assert MON2 in day_dates
    assert MON3 in day_dates

    # Сумма по оставшимся двум засеянным понедельникам
    seeded_sum = sum(d.hours for d in emp.days if d.date in (MON1, MON2, MON3))
    assert seeded_sum == 16.0


def test_applies_scenario_rule_subtract(db_session):
    """Правило 25% нормы → каждый день = 8 × 0.75 = 6 ч."""
    _make_employee(db_session, role="analyst")
    scenario = _make_scenario(db_session)
    _seed_calendar_mondays(db_session)
    wt = _make_work_type(db_session, subtracts=True)

    db_session.add(
        ScenarioRule(
            id="rule-1",
            scenario_id=scenario.id,
            role="analyst",
            work_type_id=wt.id,
            percent_of_norm=25.0,
        )
    )
    db_session.flush()

    svc = ResourceBaseService(db_session)
    result = svc.compute(scenario)

    emp = result.employees[0]

    # Каждый из трёх засеянных понедельников = 6 ч
    for d in emp.days:
        if d.date in (MON1, MON2, MON3):
            assert d.hours == 6.0

    seeded_sum = sum(d.hours for d in emp.days if d.date in (MON1, MON2, MON3))
    assert seeded_sum == 18.0


def test_ignores_rule_when_work_type_toggle_off(db_session):
    """Правило с subtracts_from_pool=False игнорируется → полные 8 ч."""
    _make_employee(db_session, role="analyst")
    scenario = _make_scenario(db_session)
    _seed_calendar_mondays(db_session)
    wt = _make_work_type(db_session, wid="wt-off", subtracts=False)

    db_session.add(
        ScenarioRule(
            id="rule-off",
            scenario_id=scenario.id,
            role="analyst",
            work_type_id=wt.id,
            percent_of_norm=50.0,
        )
    )
    db_session.flush()

    svc = ResourceBaseService(db_session)
    result = svc.compute(scenario)

    emp = result.employees[0]

    # Правило проигнорировано — полные 8 ч на каждый засеянный понедельник
    for d in emp.days:
        if d.date in (MON1, MON2, MON3):
            assert d.hours == 8.0

    seeded_sum = sum(d.hours for d in emp.days if d.date in (MON1, MON2, MON3))
    assert seeded_sum == 24.0


def test_external_qa_override_replaces_qa_sum(db_session):
    """external_qa_hours перезаписывает role_totals['qa']."""
    _make_employee(db_session, eid="qa-emp", role="qa")
    scenario = _make_scenario(db_session, sid="sc-qa", external_qa=500.0)
    _seed_calendar_mondays(db_session)
    db_session.flush()

    svc = ResourceBaseService(db_session)
    result = svc.compute(scenario)

    # QA-сотрудник добавляет какую-то сумму, но external_qa_hours = 500 побеждает
    assert result.external_qa_hours == 500.0
    assert result.role_totals["qa"] == 500.0


def test_external_qa_override_replaces_qa_sum_in_summary(db_session):
    """external_qa_hours перезаписывает gross_by_role['qa'] в compute_summary.

    Раньше compute_summary **прибавлял** external_qa к часам штатных QA —
    верхняя таблица показывала qa = внутренний + внешний, а правый блок
    capacityByRole.qa = только внешний, расхождение у пользователя 680 vs 340.
    После фикса оба блока согласованы: внешний QA замещает штатных.
    """
    _make_employee(db_session, eid="qa-emp", role="qa")
    scenario = _make_scenario(db_session, sid="sc-qa-sum", external_qa=500.0)
    _seed_calendar_mondays(db_session)
    db_session.flush()

    svc = ResourceBaseService(db_session)
    summary = svc.compute_summary(scenario)

    # gross должен быть РАВЕН external_qa_hours (замена), а не больше (прибавление).
    assert summary.gross_by_role["qa"] == 500.0
    # Без правил обязательных работ для qa — доступно всё 500.
    assert summary.available_by_role["qa"] == 500.0
    assert summary.external_qa_hours == 500.0
