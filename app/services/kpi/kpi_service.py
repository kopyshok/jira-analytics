"""Расчёт KPI: по сотруднику, команде и периоду."""
import json
from calendar import monthrange
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile
from app.models.worklog import Worklog
from app.services.kpi.calculators import MetricResult, norm_to_fact, ratio, score_to_max
from app.services.kpi.conditions import Condition, ConditionSet, build_issue_query
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_late
from app.services.team_membership import member_intervals, members_overlapping

QUARTER_OF_MONTH = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3,
                    10: 4, 11: 4, 12: 4}


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


def with_direction(cs: ConditionSet, direction: Optional[str]) -> ConditionSet:
    """Добавить фильтр по продуктовому направлению — параметр отчёта, не метрики.

    Направление сознательно не зашито в наборы условий метрик (см.
    ``app/services/kpi/seed.py``): руководитель выбирает его на экране отчёта,
    поэтому условие добавляется здесь, при построении запроса.
    """
    if not direction:
        return cs
    return ConditionSet(
        unit=cs.unit,
        person_field=cs.person_field,
        period_window=cs.period_window,
        conditions=[*cs.conditions, Condition(attr="direction", op="eq", value=direction)],
    )


def compute_metric(
    db: Session,
    metric: KpiMetric,
    account_id: str,
    period_start: date,
    period_end: date,
    teams: Optional[list[str]],
    settings: Optional[KpiSettings] = None,
    norm_value: Optional[float] = None,
    direction: Optional[str] = None,
) -> MetricResult:
    """Посчитать одну метрику для одного человека за период."""
    st = settings or read_kpi_settings(db)
    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)

    if metric.calc_kind == "ratio":
        if num_cs.unit == "worklogs":
            return _ratio_over_worklogs(db, num_cs, account_id, period_start, period_end, st)
        den_cs = with_direction(ConditionSet.from_json(metric.denominator_json), direction)
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
        rows: list[list[Optional[float]]] = []
        for issue in q.all():
            row = [getattr(issue, n, None) for n in names]
            if any(v is not None for v in row):
                rows.append(row)
        return score_to_max(rows, metric.score_max or 5.0)

    return MetricResult(value=None, has_data=False)


def worklog_items(
    db: Session, cs: ConditionSet, account_id: str,
    period_start: date, period_end: date, settings: Optional[KpiSettings] = None,
) -> tuple[list[Worklog], list[Worklog]]:
    """Записи трудозатрат человека за период, разделённые на внесённые вовремя и просроченные.

    Общий источник для расчёта метрики своевременности (``_ratio_over_worklogs``)
    и её расшифровки (``GET /kpi/breakdown``) — числа не должны разъезжаться.
    """
    st = settings or read_kpi_settings(db)
    emp = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if emp is None:
        return [], []
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
    direction_conds = [c.value for c in cs.conditions if c.attr == "direction"]
    if direction_conds:
        q = q.filter(Issue.direction == direction_conds[0])

    on_time: list[Worklog] = []
    late: list[Worklog] = []
    for w in q.all():
        bucket = late if is_late(
            db, w.started_at.date(), w.jira_created_at,
            st.worklog_deadline_days, st.worklog_deadline_time,
        ) else on_time
        bucket.append(w)
    return on_time, late


def _ratio_over_worklogs(
    db: Session, cs: ConditionSet, account_id: str,
    period_start: date, period_end: date, st: KpiSettings,
) -> MetricResult:
    """Своевременность внесения часов. Единица счёта — запись, а не задача.

    Числитель и знаменатель одной формулы (просроченные / все) считаются
    напрямую по записям — набор условий метрики (числитель) описывает и то,
    и другое: своё поле ``denominator_json`` этому виду метрики не нужно.
    """
    on_time, late = worklog_items(db, cs, account_id, period_start, period_end, st)
    total = len(on_time) + len(late)
    if total == 0:
        return MetricResult(value=None, has_data=False)
    return ratio(len(late), total, invert=True, cap_at_100=True)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Первый и последний день месяца."""
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def previous_month(year: int, month: int) -> tuple[int, int]:
    """Год и месяц, предшествующие данным."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _profile_for(db: Session, employee: Employee) -> Optional[KpiProfile]:
    """Профиль по роли сотрудника; если для роли профиля нет — первый включённый."""
    if employee.role:
        p = (
            db.query(KpiProfile)
            .filter(KpiProfile.role_code == employee.role, KpiProfile.is_enabled.is_(True))
            .first()
        )
        if p:
            return p
    return db.query(KpiProfile).filter(KpiProfile.is_enabled.is_(True)).first()


def _norm_for(db: Session, team: str, year: int, month: int) -> Optional[float]:
    """Норматив Cycle Time команды на квартал, которому принадлежит месяц."""
    row = (
        db.query(KpiCycleTimeNorm)
        .filter(
            KpiCycleTimeNorm.team == team,
            KpiCycleTimeNorm.year == year,
            KpiCycleTimeNorm.quarter == QUARTER_OF_MONTH[month],
        )
        .first()
    )
    return row.norm_value if row else None


def compute_employee_month(
    db: Session,
    employee: Employee,
    teams: list[str],
    year: int,
    month: int,
    settings: Optional[KpiSettings] = None,
    direction: Optional[str] = None,
) -> dict:
    """Результат одного сотрудника за месяц: метрики его профиля и итог.

    Общий строитель одной строки для ``build_report`` (все люди команды за
    месяц) и ``GET /kpi/trend`` (один человек за несколько месяцев) — чтобы
    числа в отчёте и на графике карточки не могли разойтись.
    """
    st = settings or read_kpi_settings(db)
    period_start, period_end = month_bounds(year, month)
    profile = _profile_for(db, employee)
    if profile is None:
        return {
            "employee_id": employee.id,
            "employee_name": employee.display_name,
            "account_id": employee.jira_account_id,
            "team": employee.team,
            "profile_code": None,
            "target_pct": None,
            "warn_band_pct": None,
            "metrics": [],
            "total": None,
        }

    if teams:
        intervals = member_intervals(db, teams, period_start, period_end)
        emp_intervals = intervals.get(employee.id, [])
    else:
        emp_intervals = []
    if emp_intervals:
        eff_start = max(period_start, min(lo for lo, _ in emp_intervals))
        eff_end = min(period_end, max(hi for _, hi in emp_intervals))
    else:
        eff_start, eff_end = period_start, period_end

    parts = []
    metric_payload = []
    for link in sorted(profile.metrics, key=lambda m: m.sort_order):
        norm = _norm_for(db, employee.team or (teams[0] if teams else ""), year, month) \
            if link.metric.calc_kind == "norm_to_fact" else None
        res = compute_metric(
            db, link.metric, employee.jira_account_id, eff_start, eff_end,
            teams, settings=st, norm_value=norm, direction=direction,
        )
        parts.append((link.metric.code, res, link.weight))
        metric_payload.append({
            "code": link.metric.code,
            "name": link.metric.name,
            "weight": link.weight,
            "value": res.value,
            "has_data": res.has_data,
            "numerator": res.numerator,
            "denominator": res.denominator,
        })

    return {
        "employee_id": employee.id,
        "employee_name": employee.display_name,
        "account_id": employee.jira_account_id,
        "team": employee.team,
        "profile_code": profile.code,
        "target_pct": profile.target_pct,
        "warn_band_pct": profile.warn_band_pct,
        "metrics": metric_payload,
        "total": combine(parts, st.empty_policy),
    }


def build_report(
    db: Session, teams: list[str], year: int, month: int, direction: Optional[str] = None,
) -> dict:
    """Отчёт по людям выбранных команд за месяц.

    Период человека внутри месяца обрезается по фактическим дням участия в
    команде (``app/services/team_membership.py``) — так неполный месяц не
    даёт задачам, закрытым до вступления или после выбытия, попасть в счёт.
    Сотрудник без профиля оценки попадает в отчёт с пустым списком метрик —
    руководителю нужно видеть его в списке команды, а не терять молча.
    """
    st = read_kpi_settings(db)
    period_start, period_end = month_bounds(year, month)
    emp_ids = members_overlapping(db, teams, period_start, period_end)
    if not emp_ids:
        return {"year": year, "month": month, "teams": teams, "rows": []}

    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(emp_ids))
        .order_by(Employee.display_name)
        .all()
    )

    rows = [
        compute_employee_month(db, emp, teams, year, month, settings=st, direction=direction)
        for emp in employees
    ]
    rows.sort(key=lambda r: (r["total"] is None, r["total"] or 0))
    return {"year": year, "month": month, "teams": teams, "rows": rows}


def summarize_report(rows: list[dict]) -> dict:
    """Сводка отчёта: средний итог, сколько людей ниже цели, сколько метрик без данных."""
    totals = [r["total"] for r in rows if r["total"] is not None]
    avg_total = sum(totals) / len(totals) if totals else None
    below_target = sum(
        1 for r in rows
        if r["total"] is not None and r["target_pct"] is not None and r["total"] < r["target_pct"]
    )
    no_data_metrics = sum(1 for r in rows for m in r["metrics"] if not m["has_data"])
    return {
        "avg_total": avg_total,
        "below_target_count": below_target,
        "no_data_metrics_count": no_data_metrics,
    }
