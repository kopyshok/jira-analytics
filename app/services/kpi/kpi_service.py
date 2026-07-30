"""Расчёт KPI: по сотруднику, команде и периоду."""
import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.kpi import KpiMetric
from app.models.worklog import Worklog
from app.services.kpi.calculators import MetricResult, norm_to_fact, ratio, score_to_max
from app.services.kpi.conditions import ConditionSet, build_issue_query
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_late


def combine(
    parts: list[tuple[str, MetricResult, float]], empty_policy: str
) -> Optional[float]:
    """Взвешенная сумма метрик с учётом политики пустых данных."""
    if empty_policy == "redistribute":
        usable = [(r.value, w) for _, r, w in parts if r.has_data and r.value is not None]
        total_weight = sum(w for _, w in usable)
        if not usable or total_weight <= 0:
            return None
        return sum(v * w for v, w in usable) / total_weight
    fill = 100.0 if empty_policy == "full" else 0.0
    total_weight = sum(w for _, _, w in parts)
    if total_weight <= 0:
        return None
    acc = 0.0
    for _, r, w in parts:
        acc += (r.value if r.has_data and r.value is not None else fill) * w
    return acc / total_weight


def compute_metric(
    db: Session,
    metric: KpiMetric,
    account_id: str,
    period_start: date,
    period_end: date,
    teams: Optional[list[str]],
    settings: Optional[KpiSettings] = None,
    norm_value: Optional[float] = None,
) -> MetricResult:
    """Посчитать одну метрику для одного человека за период."""
    st = settings or read_kpi_settings(db)
    num_cs = ConditionSet.from_json(metric.numerator_json)

    if metric.calc_kind == "ratio":
        if num_cs.unit == "worklogs":
            return _ratio_over_worklogs(db, num_cs, account_id, period_start, period_end, st)
        den_cs = ConditionSet.from_json(metric.denominator_json)
        num_q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                                  st.excluded_statuses, teams)
        den_q = build_issue_query(db, den_cs, account_id, period_start, period_end,
                                  st.excluded_statuses, teams)
        return ratio(num_q.count(), den_q.count(), metric.invert, metric.cap_at_100)

    if metric.calc_kind == "norm_to_fact":
        q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                              st.excluded_statuses, teams)
        facts = [i.cycle_time_fact for i in q.all() if i.cycle_time_fact]
        return norm_to_fact(norm_value, facts)

    if metric.calc_kind == "score_to_max":
        q = build_issue_query(db, num_cs, account_id, period_start, period_end,
                              st.excluded_statuses, teams)
        names = json.loads(metric.score_fields or '["rating_speed","rating_quality","rating_result"]')
        rows = []
        for issue in q.all():
            row = [getattr(issue, n, None) for n in names]
            if any(v is not None for v in row):
                rows.append(row)
        return score_to_max(rows, metric.score_max or 5.0)

    return MetricResult(value=None, has_data=False)


def _ratio_over_worklogs(
    db: Session, cs: ConditionSet, account_id: str,
    period_start: date, period_end: date, st: KpiSettings,
) -> MetricResult:
    """Своевременность внесения часов. Единица счёта — запись, а не задача.

    Числитель и знаменатель одной формулы (просроченные / все) считаются
    напрямую по записям — набор условий метрики (числитель) описывает и то,
    и другое: своё поле ``denominator_json`` этому виду метрики не нужно.
    """
    emp = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if emp is None:
        return MetricResult(value=None, has_data=False)
    period_start_dt = datetime.combine(period_start, datetime.min.time())
    period_end_dt = datetime.combine(period_end, datetime.max.time())
    q = (
        db.query(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(Worklog.employee_id == emp.id)
        .filter(Worklog.started_at >= period_start_dt)
        .filter(Worklog.started_at <= period_end_dt)
    )
    project_keys = [c.value for c in cs.conditions if c.attr == "project_key"]
    if project_keys:
        from app.models.project import Project

        keys = project_keys[0] if isinstance(project_keys[0], list) else project_keys
        q = q.filter(Issue.project_id.in_(
            db.query(Project.id).filter(Project.key.in_(keys)).scalar_subquery()
        ))
    rows = q.all()
    if not rows:
        return MetricResult(value=None, has_data=False)
    late = sum(
        1 for w in rows
        if is_late(db, w.started_at.date(), w.jira_created_at,
                   st.worklog_deadline_days, st.worklog_deadline_time)
    )
    return ratio(late, len(rows), invert=True, cap_at_100=True)
