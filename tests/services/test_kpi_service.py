"""Метрика без данных не обнуляет итог, а перераспределяет вес; расчёт метрики целиком."""
import json as _json
from datetime import date, datetime

from app.services.kpi.calculators import MetricResult
from app.services.kpi.kpi_service import combine, compute_metric


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
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        teams=["Платежи"], settings=None,
    )
    assert result.has_data is True
    assert round(result.value, 1) == 80.0
