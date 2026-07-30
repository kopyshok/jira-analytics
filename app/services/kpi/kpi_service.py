"""Расчёт KPI: по сотруднику, команде и периоду."""
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile
from app.models.worklog import Worklog
from app.services.kpi.calculators import MetricResult, norm_to_fact, ratio, score_to_max
from app.services.kpi.conditions import (
    Condition,
    ConditionSet,
    build_issue_query,
    issue_attribute_clauses,
)
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_late, load_calendar
from app.services.team_membership import (
    active_on_clause,
    member_intervals,
    members_overlapping,
    primary_team_on,
)

QUARTER_OF_MONTH = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3,
                    10: 4, 11: 4, 12: 4}

# Запас для чтения календаря вокруг периода отчёта — дедлайну внесения часов
# нужно место для поиска ближайшего рабочего дня за границей периода.
CALENDAR_BUFFER_DAYS = 7


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
    periods: list[tuple[date, date]],
    teams: Optional[list[str]],
    settings: Optional[KpiSettings] = None,
    norm_value: Optional[float] = None,
    direction: Optional[str] = None,
    calendar: Optional[dict[date, bool]] = None,
) -> MetricResult:
    """Посчитать одну метрику для одного человека за период (возможно — несколько отрезков)."""
    st = settings or read_kpi_settings(db)
    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)

    if metric.calc_kind == "ratio":
        if num_cs.unit == "worklogs":
            return _ratio_over_worklogs(
                db, num_cs, account_id, periods, teams, st,
                metric.invert, metric.cap_at_100, calendar,
            )
        den_cs = with_direction(ConditionSet.from_json(metric.denominator_json), direction)
        num_q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
        den_q = build_issue_query(db, den_cs, account_id, periods, st.excluded_statuses, teams)
        return ratio(num_q.count(), den_q.count(), metric.invert, metric.cap_at_100)

    if metric.calc_kind == "norm_to_fact":
        q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
        facts = [i.cycle_time_fact for i in q.all() if i.cycle_time_fact]
        return norm_to_fact(norm_value, facts)

    if metric.calc_kind == "score_to_max":
        q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
        names = json.loads(metric.score_fields or '["rating_speed","rating_quality","rating_result"]')
        rows: list[list[Optional[float]]] = []
        for issue in q.all():
            row = [getattr(issue, n, None) for n in names]
            if any(v is not None for v in row):
                rows.append(row)
        return score_to_max(rows, metric.score_max or 5.0)

    return MetricResult(value=None, has_data=False)


def worklog_items(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: Optional[list[str]] = None,
    settings: Optional[KpiSettings] = None,
    calendar: Optional[dict[date, bool]] = None,
) -> tuple[list[Worklog], list[Worklog]]:
    """Записи трудозатрат человека за период, разделённые на внесённые вовремя и просроченные.

    Отбор задач, к которым привязаны записи, переиспользует общий транслятор
    условий (``issue_attribute_clauses``) — раньше учитывались только проект и
    направление, а исключённые статусы, «кто считается» и любое условие,
    добавленное через настройки, молча игнорировались (см. ревью Фазы 3,
    ВАЖНО 5). Период здесь — дата самой записи (``Worklog.started_at``), а не
    дата закрытия задачи, поэтому условие периода из ``cs`` не применяется.

    Общий источник для расчёта метрики своевременности (``_ratio_over_worklogs``)
    и её расшифровки (``GET /kpi/breakdown``) — числа не должны разъезжаться.
    """
    st = settings or read_kpi_settings(db)
    emp = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if emp is None:
        return [], []

    period_clauses = [
        and_(
            Worklog.started_at >= datetime.combine(start, datetime.min.time()),
            Worklog.started_at <= datetime.combine(end, datetime.max.time()),
        )
        for start, end in periods
    ]
    attr_clauses = issue_attribute_clauses(cs, st.excluded_statuses, teams)

    q = (
        db.query(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(Worklog.employee_id == emp.id)
        .filter(or_(*period_clauses))
    )
    if attr_clauses:
        q = q.filter(and_(*attr_clauses))
    rows = q.all()

    if calendar is None:
        lo = min(start for start, _ in periods) - timedelta(days=CALENDAR_BUFFER_DAYS)
        hi = max(end for _, end in periods) + timedelta(days=CALENDAR_BUFFER_DAYS)
        calendar = load_calendar(db, lo, hi)

    on_time: list[Worklog] = []
    late: list[Worklog] = []
    for w in rows:
        bucket = late if is_late(
            calendar, w.started_at.date(), w.jira_created_at,
            st.worklog_deadline_days, st.worklog_deadline_time,
        ) else on_time
        bucket.append(w)
    return on_time, late


def _ratio_over_worklogs(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: Optional[list[str]],
    st: KpiSettings,
    invert: bool,
    cap_at_100: bool,
    calendar: Optional[dict[date, bool]],
) -> MetricResult:
    """Своевременность внесения часов. Единица счёта — запись, а не задача.

    Числитель и знаменатель одной формулы (просроченные / все) считаются
    напрямую по записям — набор условий метрики (числитель) описывает и то,
    и другое: своё поле ``denominator_json`` этому виду метрики не нужно.
    Инверсия и потолок берутся из самой метрики, а не зашиты здесь.
    """
    on_time, late = worklog_items(db, cs, account_id, periods, teams, st, calendar)
    total = len(on_time) + len(late)
    if total == 0:
        return MetricResult(value=None, has_data=False)
    return ratio(len(late), total, invert=invert, cap_at_100=cap_at_100)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Первый и последний день месяца."""
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def previous_month(year: int, month: int) -> tuple[int, int]:
    """Год и месяц, предшествующие данным."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass
class ReportCache:
    """Кэш отчёта на команду: без похода в БД на каждого сотрудника отдельно.

    Профиль, норматив и производственный календарь одинаковы для всех строк
    отчёта (или почти всех) — читать их по одному на сотрудника раньше давало
    порядка 1000+ запросов на месячный отчёт команды из 20 человек (см. ревью
    Фазы 3, ВАЖНО 6).
    """

    profiles_by_role: dict[str, KpiProfile]
    default_profile: Optional[KpiProfile]
    norms: dict[tuple[str, int, int], float]
    calendar: dict[date, bool]
    primary_team_by_employee: dict[str, str]


def _build_report_cache(
    db: Session, employee_ids: list[str], period_start: date, period_end: date,
) -> ReportCache:
    """Собрать кэш одним проходом на весь отчёт."""
    profiles = (
        db.query(KpiProfile)
        .filter(KpiProfile.is_enabled.is_(True))
        .order_by(KpiProfile.code)
        .all()
    )
    profiles_by_role: dict[str, KpiProfile] = {}
    default_profile: Optional[KpiProfile] = None
    for p in profiles:
        if p.role_code and p.role_code not in profiles_by_role:
            profiles_by_role[p.role_code] = p
        if p.is_default and default_profile is None:
            default_profile = p

    norms = {
        (n.team, n.year, n.quarter): n.norm_value
        for n in db.query(KpiCycleTimeNorm).all()
    }

    calendar = load_calendar(
        db,
        period_start - timedelta(days=CALENDAR_BUFFER_DAYS),
        period_end + timedelta(days=CALENDAR_BUFFER_DAYS),
    )

    primary_team_by_employee: dict[str, str] = {}
    if employee_ids:
        rows = (
            db.query(EmployeeTeam.employee_id, EmployeeTeam.team)
            .filter(
                EmployeeTeam.employee_id.in_(employee_ids),
                EmployeeTeam.is_primary.is_(True),
                *active_on_clause(period_start),
            )
            .all()
        )
        primary_team_by_employee = {emp_id: team for emp_id, team in rows}

    return ReportCache(
        profiles_by_role=profiles_by_role, default_profile=default_profile,
        norms=norms, calendar=calendar, primary_team_by_employee=primary_team_by_employee,
    )


def _resolve_profile(
    db: Session, employee: Employee, cache: Optional[ReportCache],
) -> Optional[KpiProfile]:
    """Профиль по роли сотрудника; иначе — явный профиль по умолчанию.

    Раньше запасным был «первый включённый профиль без сортировки» —
    недетерминированная подстановка (см. ревью Фазы 3, ВАЖНО 7). Теперь это
    осознанная настройка (``KpiProfile.is_default``): без неё сотрудник без
    своей роли попадает в отчёт строкой без метрик, а не оценивается чужим
    профилем случайно.
    """
    if cache is not None:
        if employee.role and employee.role in cache.profiles_by_role:
            return cache.profiles_by_role[employee.role]
        return cache.default_profile

    if employee.role:
        p = (
            db.query(KpiProfile)
            .filter(KpiProfile.role_code == employee.role, KpiProfile.is_enabled.is_(True))
            .first()
        )
        if p:
            return p
    return (
        db.query(KpiProfile)
        .filter(KpiProfile.is_enabled.is_(True), KpiProfile.is_default.is_(True))
        .order_by(KpiProfile.code)
        .first()
    )


def _team_for_norm(
    db: Session,
    employee: Employee,
    teams: list[str],
    period_start: date,
    cache: Optional[ReportCache] = None,
) -> str:
    """Команда для норматива Cycle Time — основная НА НАЧАЛО ПЕРИОДА, а не ``Employee.team``
    (это дериватив «на сегодня»).

    После перевода сотрудника отчёты за прошлые месяцы иначе брали бы
    норматив новой (текущей) команды — метрика ложно становилась «нет
    данных» (см. ревью Фазы 3, ВАЖНО 3).
    """
    team = (
        cache.primary_team_by_employee.get(employee.id)
        if cache is not None
        else primary_team_on(db, employee.id, period_start)
    )
    if team and (not teams or team in teams):
        return team
    if teams:
        return teams[0]
    return team or employee.team or ""


def _norm_for(
    db: Session, team: str, year: int, month: int, cache: Optional[ReportCache] = None,
) -> Optional[float]:
    """Норматив Cycle Time команды на квартал, которому принадлежит месяц."""
    quarter = QUARTER_OF_MONTH[month]
    if cache is not None:
        return cache.norms.get((team, year, quarter))
    row = (
        db.query(KpiCycleTimeNorm)
        .filter(
            KpiCycleTimeNorm.team == team,
            KpiCycleTimeNorm.year == year,
            KpiCycleTimeNorm.quarter == quarter,
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
    cache: Optional[ReportCache] = None,
) -> dict:
    """Результат одного сотрудника за месяц: метрики его профиля и итог.

    Общий строитель одной строки для ``build_report`` (все люди команды за
    месяц, с общим ``cache``) и ``GET /kpi/trend`` (один человек за несколько
    месяцев, без кэша) — чтобы числа в отчёте и на графике карточки не могли
    разойтись.
    """
    st = settings or read_kpi_settings(db)
    period_start, period_end = month_bounds(year, month)
    profile = _resolve_profile(db, employee, cache)
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
    # Несколько отрезков участия (ушёл-вернулся) считаются по фактическим
    # отрезкам, а не по общему диапазону от первого до последнего дня —
    # иначе разрыв между отрезками молча превращался в «состоял весь месяц».
    periods = emp_intervals if emp_intervals else [(period_start, period_end)]

    norm_team = _team_for_norm(db, employee, teams, period_start, cache) if teams \
        else (employee.team or "")
    calendar = cache.calendar if cache is not None else None

    parts = []
    metric_payload = []
    for link in sorted(profile.metrics, key=lambda m: m.sort_order):
        norm = _norm_for(db, norm_team, year, month, cache) \
            if link.metric.calc_kind == "norm_to_fact" else None
        res = compute_metric(
            db, link.metric, employee.jira_account_id, periods,
            teams, settings=st, norm_value=norm, direction=direction, calendar=calendar,
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
    cache = _build_report_cache(db, [e.id for e in employees], period_start, period_end)

    rows = [
        compute_employee_month(
            db, emp, teams, year, month, settings=st, direction=direction, cache=cache,
        )
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
