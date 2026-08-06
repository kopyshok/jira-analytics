"""Период отчёта KPI: месяц, квартал, произвольный отрезок.

Ключевое требование заказчика (2026-08-06): итог квартала — ОДНА дробь по
задачам всех трёх месяцев, а не среднее трёх месячных процентов. На данных
ниже эти два способа дают разные числа (80% против 83,3%), поэтому тест
отличает реализацию от подмены.
"""
import json
from datetime import date, datetime

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric, KpiProfileRole
from app.services.kpi.kpi_service import (
    build_report,
    months_in_period,
    period_bounds,
    period_quarter,
    previous_period,
)

TEAM = "Платежи"
ACCOUNT = "acc-per"


def test_period_bounds_month_and_quarter():
    assert period_bounds(2026, 7) == (date(2026, 7, 1), date(2026, 7, 31))
    assert period_bounds(2026, 9, 3) == (date(2026, 7, 1), date(2026, 9, 30))
    # Отрезок через границу года
    assert period_bounds(2026, 2, 4) == (date(2025, 11, 1), date(2026, 2, 28))


def test_months_in_period_is_ascending():
    assert months_in_period(2026, 2, 3) == [(2025, 12), (2026, 1), (2026, 2)]


def test_previous_period_matches_length():
    assert previous_period(2026, 7) == (2026, 6)
    assert previous_period(2026, 9, 3) == (2026, 6)
    assert previous_period(2026, 3, 3) == (2025, 12)


def test_period_quarter_only_for_whole_quarter():
    assert period_quarter(2026, 9, 3) == (2026, 3)
    assert period_quarter(2026, 12, 3) == (2026, 4)
    # «Последние 3 месяца», кончающиеся октябрём — не квартал
    assert period_quarter(2026, 10, 3) is None
    assert period_quarter(2026, 9, 1) is None
    assert period_quarter(2026, 9, 6) is None


def _seed(db, sample_project):
    """Аналитик с единственной метрикой «доля задач среди всего закрытого».

    Метрика заводится прямо здесь, а не берётся из справочника по умолчанию:
    тесту нужна простая дробь с предсказуемым числителем и знаменателем.
    """
    employee = Employee(
        jira_account_id=ACCOUNT, display_name="Аналитик Периодов",
        email="per@example.com", role="analyst", team=TEAM,
    )
    db.add(employee)
    db.commit()
    db.add(EmployeeTeam(employee_id=employee.id, team=TEAM, is_primary=True,
                        joined_at=date(2025, 1, 1)))

    def cs(types: list[str]) -> str:
        return json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [{"attr": "issue_type", "op": "in", "value": types}],
        })

    metric = KpiMetric(
        code="share_check", name="Доля задач", calc_kind="ratio",
        invert=False, cap_at_100=True,
        numerator_json=cs(["Задача"]), denominator_json=cs(["Задача", "Ошибка"]),
    )
    profile = KpiProfile(code="analyst", name="Аналитик", target_pct=80.0, warn_band_pct=10.0)
    db.add_all([metric, profile])
    db.commit()
    db.add(KpiProfileRole(profile_id=profile.id, role_code="analyst"))
    db.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    db.commit()
    return employee


def _closed(db, sample_project, key: str, issue_type: str, when: datetime) -> None:
    db.add(Issue(
        jira_issue_id=f"per-{key}", key=key, summary="s", issue_type=issue_type,
        status="ГОТОВО", status_category="done", resolution="Готово", resolved_at=when,
        project_id=sample_project.id, reporter_account_id=ACCOUNT, team=TEAM,
    ))
    db.commit()


def _row(report: dict) -> dict:
    return next(r for r in report["rows"] if r["account_id"] == ACCOUNT)


def test_quarter_total_is_single_fraction_not_average_of_months(db_session, sample_project):
    """Июль 1 из 2, август 1 из 1, сентябрь 2 из 2 → квартал 4 из 5 = 80%, а не 83,3%."""
    _seed(db_session, sample_project)
    _closed(db_session, sample_project, "OS-7001", "Задача", datetime(2026, 7, 10))
    _closed(db_session, sample_project, "OS-7002", "Ошибка", datetime(2026, 7, 12))
    _closed(db_session, sample_project, "OS-8001", "Задача", datetime(2026, 8, 10))
    _closed(db_session, sample_project, "OS-9001", "Задача", datetime(2026, 9, 10))
    _closed(db_session, sample_project, "OS-9002", "Задача", datetime(2026, 9, 20))

    quarter = _row(build_report(db_session, [TEAM], 2026, 9, months=3))
    assert round(quarter["total"], 1) == 80.0
    assert quarter["metrics"][0]["numerator"] == 4
    assert quarter["metrics"][0]["denominator"] == 5

    # Среднее месячных дало бы 83,3 — именно от этого способа заказчик отказался.
    monthly = [_row(build_report(db_session, [TEAM], 2026, m))["total"] for m in (7, 8, 9)]
    assert round(sum(monthly) / 3, 1) == 83.3


def test_quarter_row_carries_months_breakdown(db_session, sample_project):
    """Разбивка по месяцам внутри периода — те же числа, что дал бы месячный отчёт."""
    _seed(db_session, sample_project)
    _closed(db_session, sample_project, "OS-7001", "Задача", datetime(2026, 7, 10))
    _closed(db_session, sample_project, "OS-7002", "Ошибка", datetime(2026, 7, 12))
    _closed(db_session, sample_project, "OS-8001", "Задача", datetime(2026, 8, 10))

    row = _row(build_report(db_session, [TEAM], 2026, 9, months=3))
    breakdown = {(p["year"], p["month"]): p["total"] for p in row["months_breakdown"]}

    assert list(breakdown) == [(2026, 7), (2026, 8), (2026, 9)]
    assert round(breakdown[(2026, 7)], 1) == 50.0
    assert round(breakdown[(2026, 8)], 1) == 100.0
    # В сентябре задач нет — метрика без данных, итога месяца тоже нет.
    assert breakdown[(2026, 9)] is None


def test_month_report_has_no_months_breakdown(db_session, sample_project):
    """Месяц дробить не на что — лишнего поля в строке быть не должно."""
    _seed(db_session, sample_project)
    _closed(db_session, sample_project, "OS-7001", "Задача", datetime(2026, 7, 10))

    row = _row(build_report(db_session, [TEAM], 2026, 7))
    assert "months_breakdown" not in row
