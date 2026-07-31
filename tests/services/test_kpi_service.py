"""Метрика без данных не обнуляет итог, а перераспределяет вес; расчёт метрики целиком."""
import json as _json
from datetime import date, datetime

from app.services.kpi.calculators import MetricResult
from app.services.kpi.kpi_service import combine, compute_metric
from app.services.kpi.settings import KpiSettings


def test_weights_redistributed_when_metric_has_no_data():
    parts = [
        ("quality", MetricResult(90.0, True), 0.5),
        ("timeliness", MetricResult(70.0, True), 0.3),
        ("customer", MetricResult(None, False), 0.2),
    ]
    total = combine(parts, empty_policy="redistribute")
    # 0.5 и 0.3 нормируются до 0.625 и 0.375
    assert round(total, 2) == round(90 * 0.625 + 70 * 0.375, 2)


def test_policy_full_counts_missing_as_hundred():
    parts = [("a", MetricResult(80.0, True), 0.5), ("b", MetricResult(None, False), 0.5)]
    assert combine(parts, empty_policy="full") == 90.0


def test_policy_zero_counts_missing_as_zero():
    parts = [("a", MetricResult(80.0, True), 0.5), ("b", MetricResult(None, False), 0.5)]
    assert combine(parts, empty_policy="zero") == 40.0


def test_all_metrics_missing_gives_none():
    parts = [("a", MetricResult(None, False), 1.0)]
    assert combine(parts, empty_policy="redistribute") is None


def test_quality_metric_end_to_end(db_session, sample_project):
    """Три бага на пятнадцать выпущенных задач дают 80%."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.issue_link import IssueLink
    from app.models.kpi import KpiMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.commit()

    released = []
    for i in range(15):
        issue = Issue(
            jira_issue_id=f"r{i}", key=f"OS-{100 + i}", summary="Задача",
            issue_type="Задача", status="ГОТОВО", status_category="done",
            resolution="Готово", resolved_at=datetime(2026, 7, 10),
            project_id=sample_project.id, reporter_account_id="acc-1", team="Платежи",
        )
        db_session.add(issue)
        released.append(issue)
    db_session.commit()

    for i in range(3):
        bug = Issue(
            jira_issue_id=f"b{i}", key=f"OS-{200 + i}", summary="Баг",
            issue_type="Баг", status="ГОТОВО", status_category="done",
            resolution="Готово", environment="PROD", resolved_at=datetime(2026, 7, 12),
            project_id=sample_project.id, team="Платежи",
        )
        db_session.add(bug)
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    metric = KpiMetric(
        code="quality", name="Качество выпуска", calc_kind="ratio", invert=True, cap_at_100=True,
        numerator_json=_json.dumps({
            "unit": "issues", "person_field": "linked_issue_author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
                {"attr": "environment", "op": "eq", "value": "PROD"},
            ],
        }),
        denominator_json=_json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Задача", "Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=None,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 80.0


def test_norm_to_fact_via_compute_metric(db_session, sample_project):
    """ВАЖНО 9: норматив-к-факту проходит через общий вход расчёта (не только через unit-тест калькулятора)."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.add(Issue(
        jira_issue_id="ct-1", key="OS-300", summary="ИТ-задача", issue_type="ИТ-задача",
        status="ГОТОВО", status_category="done", resolution="Готово",
        subtype="RFC_STANDARD", cost_type="Change", cycle_time_fact=100.0,
        resolved_at=datetime(2026, 7, 10), project_id=sample_project.id,
        assignee_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    metric = KpiMetric(
        code="cycle_time", name="Cycle Time", calc_kind="norm_to_fact",
        invert=False, cap_at_100=True, fact_field="cycle_time_fact",
        numerator_json=_json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["ИТ-задача"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=None, norm_value=70.0,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 70.0


def test_score_to_max_via_compute_metric(db_session, sample_project):
    """ВАЖНО 9: балл-к-максимуму проходит через общий вход расчёта."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.add(Issue(
        jira_issue_id="sc-1", key="OS-301", summary="ИТ-задача", issue_type="ИТ-задача",
        status="ГОТОВО", status_category="done", resolution="Готово",
        rating_speed=4, rating_quality=4, rating_result=4,
        resolved_at=datetime(2026, 7, 10), project_id=sample_project.id,
        assignee_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    metric = KpiMetric(
        code="customer_score", name="Оценка заказчика", calc_kind="score_to_max",
        invert=False, cap_at_100=True, score_max=5.0,
        score_fields=_json.dumps(["rating_speed", "rating_quality", "rating_result"]),
        numerator_json=_json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [{"attr": "resolution", "op": "in", "value": ["Готово"]}],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=None,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 80.0


def test_norm_to_fact_reads_configured_fact_field_not_hardcoded_column(db_session, sample_project):
    """BLOCKER 4: движок читает поле факта, заданное в метрике, а не всегда
    жёстко колонку cycle_time_fact."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.add(Issue(
        jira_issue_id="ct-2", key="OS-302", summary="ИТ-задача", issue_type="ИТ-задача",
        status="ГОТОВО", status_category="done", resolution="Готово",
        cycle_time_fact=999.0,  # намеренно «неправильное» значение — не должно использоваться
        estimated_hours=50.0,
        resolved_at=datetime(2026, 7, 10), project_id=sample_project.id,
        assignee_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    metric = KpiMetric(
        code="custom_fact", name="Своя метрика факта", calc_kind="norm_to_fact",
        invert=False, cap_at_100=True, fact_field="estimated_hours",
        numerator_json=_json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [{"attr": "resolution", "op": "in", "value": ["Готово"]}],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=None, norm_value=50.0,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 100.0


def test_build_teams_summary_returns_metric_averages_member_count_and_target(db_session, sample_project):
    """ВАЖНО 5: строка команды приходит с сервера целиком — сервер, не клиент,
    усредняет метрики по людям с данными, считает состав, отдаёт цель/жёлтую зону."""
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric
    from app.services.kpi.kpi_service import build_teams_summary

    e1 = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи", role="analyst")
    e2 = Employee(jira_account_id="acc-2", display_name="Петров П.", team="Платежи", role="analyst")
    db_session.add_all([e1, e2])
    db_session.commit()
    db_session.add_all([
        EmployeeTeam(employee_id=e1.id, team="Платежи", is_primary=True, joined_at=date(2026, 1, 1)),
        EmployeeTeam(employee_id=e2.id, team="Платежи", is_primary=True, joined_at=date(2026, 1, 1)),
    ])
    db_session.commit()

    # У e1 закрыта задача (данные есть), у e2 — ни одной (метрика без данных).
    db_session.add(Issue(
        jira_issue_id="ts-1", key="OS-700", summary="s", issue_type="Задача",
        status="ГОТОВО", status_category="done", resolution="Готово",
        resolved_at=datetime(2026, 7, 10), project_id=sample_project.id,
        reporter_account_id="acc-1", team="Платежи",
    ))
    db_session.commit()

    cond = _json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Задача"]}],
    })
    metric = KpiMetric(
        code="m1", name="Метрика", calc_kind="ratio", invert=False, cap_at_100=True,
        numerator_json=cond, denominator_json=cond,
    )
    profile = KpiProfile(code="analyst", name="Аналитик", role_code="analyst",
                         is_default=True, is_enabled=True, target_pct=80.0, warn_band_pct=10.0)
    db_session.add_all([metric, profile])
    db_session.commit()
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=1.0))
    db_session.commit()

    rows = build_teams_summary(db_session, ["Платежи"], 2026, 7)
    row = next(r for r in rows if r["team"] == "Платежи")
    assert row["member_count"] == 2
    assert row["target_pct"] == 80.0
    assert row["warn_band_pct"] == 10.0
    m = next(mm for mm in row["metrics"] if mm["code"] == "m1")
    # Среднее — только по людям с данными (e1), а не по всем — иначе «нет
    # данных» у e2 тянуло бы среднее вниз без причины.
    assert m["has_data"] is True
    assert round(m["value"], 1) == 100.0


def test_worklog_timeliness_via_compute_metric_respects_status_team_and_metric_flags(
    db_session, sample_project,
):
    """ВАЖНО 5: своевременность трудозатрат — через общий транслятор, не ручной разбор двух условий.

    Проверяет разом: исключённый статус не попадает в знаменатель (раздел 6
    спеки), задача из чужой команды не попадает в знаменатель, а инверсия и
    потолок берутся из самой метрики (invert=False здесь — намеренно другое
    значение, чем зашитое ранее True, чтобы отличить «взято из метрики» от
    «совпало случайно»).
    """
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.issue import Issue
    from app.models.kpi import KpiMetric
    from app.models.worklog import Worklog

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True))

    on_time_issue = Issue(
        jira_issue_id="w1", key="OS-400", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    late_issue = Issue(
        jira_issue_id="w2", key="OS-401", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    cancelled_issue = Issue(
        jira_issue_id="w3", key="OS-402", summary="s", issue_type="Задача",
        status="Отменено", project_id=sample_project.id, team="Платежи",
    )
    other_team_issue = Issue(
        jira_issue_id="w4", key="OS-403", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Другая команда",
    )
    db_session.add_all([on_time_issue, late_issue, cancelled_issue, other_team_issue])
    db_session.commit()

    def _wl(jid, issue, started, created):
        return Worklog(
            jira_worklog_id=jid, issue_id=issue.id, employee_id=emp.id,
            started_at=started, jira_created_at=created, hours=4.0, time_spent_seconds=14400,
        )

    db_session.add_all([
        _wl("wl-1", on_time_issue, datetime(2026, 7, 13, 10, 0), datetime(2026, 7, 13, 18, 0)),
        _wl("wl-2", late_issue, datetime(2026, 7, 13, 10, 0), datetime(2026, 7, 15, 9, 0)),
        _wl("wl-3", cancelled_issue, datetime(2026, 7, 13, 10, 0), datetime(2026, 7, 13, 11, 0)),
        _wl("wl-4", other_team_issue, datetime(2026, 7, 13, 10, 0), datetime(2026, 7, 13, 11, 0)),
    ])
    db_session.commit()

    metric = KpiMetric(
        code="worklog_timeliness", name="Своевременность трудозатрат", calc_kind="ratio",
        invert=False, cap_at_100=True,
        numerator_json=_json.dumps({
            "unit": "worklogs", "person_field": "worklog_author", "period_window": "closed_in",
            "conditions": [{"attr": "project_key", "op": "in", "value": ["OS"]}],
        }),
    )
    db_session.add(metric)
    db_session.commit()

    st = KpiSettings(excluded_statuses=["Отменено"], worklog_deadline_days=1,
                     worklog_deadline_time="12:00", empty_policy="redistribute")
    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=st,
    )
    assert result.has_data is True
    # Знаменатель — 2 (отменённая и чужая команда отсеяны), просрочена 1 →
    # invert=False даёт долю просроченных, а не «долю вовремя».
    assert result.denominator == 2
    assert round(result.value, 1) == 50.0


def _worklog_timeliness_metric():
    from app.models.kpi import KpiMetric

    return KpiMetric(
        code="worklog_timeliness", name="Своевременность трудозатрат", calc_kind="ratio",
        invert=True, cap_at_100=True,
        numerator_json=_json.dumps({
            "unit": "worklogs", "person_field": "worklog_author", "period_window": "closed_in",
            "conditions": [{"attr": "project_key", "op": "in", "value": ["OS"]}],
        }),
    )


def test_worklog_timeliness_all_missing_created_at_gives_no_data(db_session, sample_project):
    """Дефект 2: без единой даты внесения метрика обязана честно сказать «нет данных»,
    а не молча посчитать все записи «внесёнными вовремя» (было 100% из ничего)."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.worklog import Worklog

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    issue = Issue(
        jira_issue_id="w10", key="OS-410", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    db_session.add(issue)
    db_session.commit()

    db_session.add_all([
        Worklog(jira_worklog_id="wl-10", issue_id=issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 13, 10, 0), jira_created_at=None,
                hours=4.0, time_spent_seconds=14400),
        Worklog(jira_worklog_id="wl-11", issue_id=issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 14, 10, 0), jira_created_at=None,
                hours=2.0, time_spent_seconds=7200),
    ])
    db_session.commit()

    metric = _worklog_timeliness_metric()
    db_session.add(metric)
    db_session.commit()

    st = KpiSettings(excluded_statuses=[], worklog_deadline_days=1,
                     worklog_deadline_time="12:00", empty_policy="redistribute")
    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=st,
    )
    assert result.has_data is False
    assert result.value is None


def test_worklog_timeliness_ignores_records_without_created_at(db_session, sample_project):
    """Часть записей без даты внесения не портит расчёт по остальным — учитываются только они."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.worklog import Worklog

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    issue = Issue(
        jira_issue_id="w11", key="OS-411", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    db_session.add(issue)
    db_session.commit()

    db_session.add_all([
        # Без даты — не считается ни в числителе, ни в знаменателе.
        Worklog(jira_worklog_id="wl-20", issue_id=issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 13, 10, 0), jira_created_at=None,
                hours=4.0, time_spent_seconds=14400),
        # С датой, вовремя (до 12:00 следующего рабочего дня).
        Worklog(jira_worklog_id="wl-21", issue_id=issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 13, 10, 0),
                jira_created_at=datetime(2026, 7, 14, 11, 0),
                hours=4.0, time_spent_seconds=14400),
    ])
    db_session.commit()

    metric = _worklog_timeliness_metric()
    db_session.add(metric)
    db_session.commit()

    st = KpiSettings(excluded_statuses=[], worklog_deadline_days=1,
                     worklog_deadline_time="12:00", empty_policy="redistribute")
    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=st,
    )
    assert result.has_data is True
    assert result.denominator == 1
    assert round(result.value, 1) == 100.0


def test_worklog_timeliness_boundary_on_time_vs_one_minute_late(db_session, sample_project):
    """Граница дедлайна не сломана исправлением: ровно в срок — вовремя, минутой позже — просрочено."""
    from app.models.employee import Employee
    from app.models.issue import Issue
    from app.models.worklog import Worklog

    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи")
    db_session.add(emp)
    on_time_issue = Issue(
        jira_issue_id="w12", key="OS-412", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    late_issue = Issue(
        jira_issue_id="w13", key="OS-413", summary="s", issue_type="Задача",
        status="ГОТОВО", project_id=sample_project.id, team="Платежи",
    )
    db_session.add_all([on_time_issue, late_issue])
    db_session.commit()

    db_session.add_all([
        # Дедлайн для работы 13.07 (пн) при days=1 — 12:00 14.07 (вт).
        Worklog(jira_worklog_id="wl-30", issue_id=on_time_issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 13, 10, 0),
                jira_created_at=datetime(2026, 7, 14, 12, 0),
                hours=4.0, time_spent_seconds=14400),
        Worklog(jira_worklog_id="wl-31", issue_id=late_issue.id, employee_id=emp.id,
                started_at=datetime(2026, 7, 13, 10, 0),
                jira_created_at=datetime(2026, 7, 14, 12, 1),
                hours=4.0, time_spent_seconds=14400),
    ])
    db_session.commit()

    metric = _worklog_timeliness_metric()
    db_session.add(metric)
    db_session.commit()

    st = KpiSettings(excluded_statuses=[], worklog_deadline_days=1,
                     worklog_deadline_time="12:00", empty_policy="redistribute")
    result = compute_metric(
        db_session, metric, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        teams=["Платежи"], settings=st,
    )
    assert result.has_data is True
    assert result.denominator == 2
    # invert=True: доля вовремя — 1 из 2 просрочена → 50%.
    assert round(result.value, 1) == 50.0
