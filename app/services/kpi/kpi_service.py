"""Расчёт KPI: по сотруднику, команде и периоду."""
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.kpi import KpiApproval, KpiCycleTimeNorm, KpiMetric, KpiProfile, KpiProfileRole
from app.models.role import Role
from app.models.worklog import Worklog
from app.services.kpi.calculators import MetricResult, norm_to_fact, ratio, score_to_max
from app.services.kpi.conditions import (
    Condition,
    ConditionSet,
    build_issue_query,
    issue_attribute_clauses,
)
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_worklog_late, load_calendar
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
        facts = [fact_value(i, metric) for i in q.all() if has_fact_value(i, metric)]
        return norm_to_fact(norm_value, facts)

    if metric.calc_kind == "score_to_max":
        q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
        names = score_field_names(metric)
        rows: list[list[Optional[float]]] = []
        for issue in q.all():
            if has_any_score(issue, names):
                rows.append([getattr(issue, n, None) for n in names])
        return score_to_max(rows, metric.score_max or 5.0)

    return MetricResult(value=None, has_data=False)


def score_field_names(metric: KpiMetric) -> list[str]:
    """Список полей оценки метрики «средний балл к максимуму», с дефолтом."""
    return json.loads(metric.score_fields or '["rating_speed","rating_quality","rating_result"]')


def fact_field_name(metric: KpiMetric) -> str:
    """Имя поля факта метрики «норматив к факту», с дефолтом на встроенный Cycle Time.

    Раньше расчёт всегда читал ``issue.cycle_time_fact`` напрямую, игнорируя
    ``metric.fact_field`` — новая метрика этого способа расчёта, заведённая
    через справочник с другим полем факта, тихо считала бы по чужим данным
    (см. ревью, BLOCKER 4).
    """
    return metric.fact_field or "cycle_time_fact"


def fact_value(issue: Issue, metric: KpiMetric) -> Optional[float]:
    """Значение факта задачи — поле, заданное в метрике."""
    return getattr(issue, fact_field_name(metric), None)


def has_fact_value(issue: Issue, metric: KpiMetric) -> bool:
    """Задача участвует в среднем факте метрики «норматив к факту»."""
    return bool(fact_value(issue, metric))


def has_any_score(issue: Issue, names: list[str]) -> bool:
    """Задача участвует в среднем балле метрики «балл к максимуму» — есть хоть одна оценка.

    Общий предикат для ``compute_metric`` и ``metric_breakdown``: расшифровка
    обязана показывать ровно те задачи, что вошли в расчёт, а не превышающий
    список без учёта фильтра «есть хоть одна оценка» (см. ревью Фазы 4,
    мелочи).
    """
    return any(getattr(issue, n, None) is not None for n in names)


def employee_periods(
    db: Session, account_id: str, year: int, month: int, teams: list[str],
) -> tuple[list[tuple[date, date]], Optional[Employee]]:
    """Отрезки месяца, за которые человек считается в команде, и он сам.

    Общий источник для расшифровки (``resolve_breakdown``) и таблицы разбора
    (``breakdown_table``) — обе обязаны резать период ровно так же, как расчёт
    отчёта, иначе дробь и строки под ней разъедутся.
    """
    period_start, period_end = month_bounds(year, month)
    employee = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    emp_intervals: list[tuple[date, date]] = []
    if employee is not None and teams:
        emp_intervals = member_intervals(db, teams, period_start, period_end).get(employee.id, [])
    return (emp_intervals or [(period_start, period_end)]), employee


def resolve_breakdown(
    db: Session,
    metric: KpiMetric,
    account_id: str,
    year: int,
    month: int,
    teams: list[str],
    direction: Optional[str] = None,
    settings: Optional[KpiSettings] = None,
) -> dict:
    """Тот же отбор задач/записей, что использует расчёт отчёта — для расшифровки метрики.

    Раньше расшифровка резала период на весь месяц целиком и не подставляла
    все команды при пустом фильтре, а расчёт отчёта — по фактическим отрезкам
    участия сотрудника в команде (``member_intervals``) с тем же списком
    команд, что и остальной отчёт. Из-за расхождения дробь в отчёте и список
    задач под ней могли говорить о разных периодах (см. BLOCKER 2 ревью:
    сотрудник вступил в команду 20 числа — отчёт «0 из 1», расшифровка — две
    задачи). ``teams`` обязаны быть уже разрешённым списком (см.
    ``_resolve_teams`` в роутере — то же самое, что подставляет отчёту все
    команды при пустом фильтре).

    Возвращает объекты ORM (не сериализованные словари) — форматирование в
    JSON остаётся на роутере, здесь только который отбор данных.
    """
    st = settings or read_kpi_settings(db)
    periods, _employee = employee_periods(db, account_id, year, month, teams)

    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)

    if num_cs.unit == "worklogs":
        on_time, late = worklog_items(db, num_cs, account_id, periods, teams, st)
        return {
            "unit": "worklogs",
            "numerator": late,
            "denominator": on_time + late,
            "late_ids": {w.id for w in late},
        }

    num_q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
    numerator = num_q.all()
    if metric.calc_kind == "norm_to_fact":
        numerator = [i for i in numerator if has_fact_value(i, metric)]
    elif metric.calc_kind == "score_to_max":
        numerator = [i for i in numerator if has_any_score(i, score_field_names(metric))]

    denominator: list = []
    if metric.calc_kind == "ratio":
        den_cs = with_direction(ConditionSet.from_json(metric.denominator_json), direction)
        den_q = build_issue_query(db, den_cs, account_id, periods, st.excluded_statuses, teams)
        denominator = den_q.all()

    return {"unit": "issues", "numerator": numerator, "denominator": denominator}


def worklog_rows(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: Optional[list[str]],
    st: KpiSettings,
) -> list[Worklog]:
    """Все записи о часах человека за период, попадающие под условия метрики.

    До деления на «вовремя» и «просрочено»: таблице разбора нужны и записи без
    даты внесения — в расчёт они не входят, но именно из-за них показатель
    бывает пустым, и руководитель должен видеть их поимённо.
    """
    emp = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if emp is None:
        return []

    period_clauses = [
        and_(
            Worklog.started_at >= datetime.combine(start, datetime.min.time()),
            Worklog.started_at <= datetime.combine(end, datetime.max.time()),
        )
        for start, end in periods
    ]
    q = (
        db.query(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(Worklog.employee_id == emp.id)
        .filter(or_(*period_clauses))
    )
    attr_clauses = issue_attribute_clauses(cs, st.excluded_statuses, teams)
    if attr_clauses:
        q = q.filter(and_(*attr_clauses))
    return q.all()


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
    rows = worklog_rows(db, cs, account_id, periods, teams, st)
    if not rows:
        return [], []

    if calendar is None:
        lo = min(start for start, _ in periods) - timedelta(days=CALENDAR_BUFFER_DAYS)
        hi = max(end for _, end in periods) + timedelta(days=CALENDAR_BUFFER_DAYS)
        calendar = load_calendar(db, lo, hi)

    on_time: list[Worklog] = []
    late: list[Worklog] = []
    for w in rows:
        # Без даты внесения нельзя знать, вовремя запись или нет — запись не
        # участвует ни в числителе, ни в знаменателе (иначе метрика лжёт
        # «100%», не зная о записи ничего, см. дефект 2).
        if w.jira_created_at is None:
            continue
        bucket = late if is_worklog_late(calendar, w.started_at, w.jira_created_at, st) else on_time
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
    norms: dict[tuple[str, int, int], float]
    calendar: dict[date, bool]
    primary_team_by_employee: dict[str, str]


def _build_report_cache(
    db: Session, employee_ids: list[str], period_start: date, period_end: date,
) -> ReportCache:
    """Собрать кэш одним проходом на весь отчёт."""
    profiles_by_role = _profiles_by_role(db)

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
        profiles_by_role=profiles_by_role,
        norms=norms, calendar=calendar, primary_team_by_employee=primary_team_by_employee,
    )


def _profiles_by_role(db: Session) -> dict[str, KpiProfile]:
    """Роль сотрудника → включённый профиль оценки.

    Роль уникальна в таблице связи, поэтому словарь однозначен. Профиля «по
    умолчанию» больше нет: сотрудник, чья роль не привязана ни к одному
    профилю, в отчёт не попадает (см. спеку доработок 2026-08-03, раздел 2).
    """
    rows = (
        db.query(KpiProfileRole.role_code, KpiProfile)
        .join(KpiProfile, KpiProfile.id == KpiProfileRole.profile_id)
        .filter(KpiProfile.is_enabled.is_(True))
        .all()
    )
    return {role_code: profile for role_code, profile in rows}


def _resolve_profile(
    db: Session, employee: Employee, cache: Optional[ReportCache],
) -> Optional[KpiProfile]:
    """Профиль по роли сотрудника; роль не привязана — профиля нет.

    Возврат ``None`` означает «сотрудник разделом не оценивается»: строка в
    ведомость не попадает вовсе. Раньше запасным был профиль «по умолчанию»,
    из-за которого в ведомость попадали программисты и тестировщики.
    """
    if not employee.role:
        return None
    if cache is not None:
        return cache.profiles_by_role.get(employee.role)
    return _profiles_by_role(db).get(employee.role)


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

    # Команда строки отчёта — та, что действовала на начало отчётного периода
    # (и совпадает с фильтром, если он задан), а не «сегодняшняя»
    # ``employee.team``. Иначе сотрудник, сменивший или покинувший команду
    # позже отчётного месяца, попадал в строки другой команды или вовсе без
    # команды — состав под строкой команды расходился со сводкой (см. ревью,
    # ВАЖНО 5).
    row_team = _team_for_norm(db, employee, teams, period_start, cache) or None

    profile = _resolve_profile(db, employee, cache)
    if profile is None:
        return {
            "employee_id": employee.id,
            "employee_name": employee.display_name,
            "account_id": employee.jira_account_id,
            "team": row_team,
            "profile_code": None,
            "profile_name": None,
            "target_pct": None,
            "warn_band_pct": None,
            "metrics": [],
            "total": None,
            "empty_policy": st.empty_policy,
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

    calendar = cache.calendar if cache is not None else None

    parts = []
    metric_payload = []
    for link in sorted(profile.metrics, key=lambda m: m.sort_order):
        norm = _norm_for(db, row_team or "", year, month, cache) \
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
        "team": row_team,
        "profile_code": profile.code,
        # Человекочитаемое название профиля — фронт показывал технический
        # код (латиницей) там, где нужна была роль сотрудника (см. ревью,
        # мелочи).
        "profile_name": profile.name,
        "target_pct": profile.target_pct,
        "warn_band_pct": profile.warn_band_pct,
        "metrics": metric_payload,
        "total": combine(parts, st.empty_policy),
        # Политика на отсутствие данных — так карточка сотрудника пишет
        # правду про применённую политику, а не всегда «вес перераспределён»
        # (это лишь одна из трёх настраиваемых политик, см. ревью, ВАЖНО 9).
        "empty_policy": st.empty_policy,
    }


def build_report(
    db: Session, teams: list[str], year: int, month: int, direction: Optional[str] = None,
) -> dict:
    """Отчёт по людям выбранных команд за месяц.

    Период человека внутри месяца обрезается по фактическим дням участия в
    команде (``app/services/team_membership.py``) — так неполный месяц не
    даёт задачам, закрытым до вступления или после выбытия, попасть в счёт.

    Сотрудник, чья роль не привязана ни к одному профилю оценки, в отчёт не
    попадает вообще (решение заказчика, спека доработок 2026-08-03) — раньше
    его подхватывал профиль «по умолчанию», из-за чего в ведомость попадали
    программисты и тестировщики. Сколько человек так отсеялось, отдаётся
    отдельным числом (``skipped_no_profile``): молча терять людей нельзя,
    руководитель должен видеть, что состав команды шире оценённого.
    """
    st = read_kpi_settings(db)
    period_start, period_end = month_bounds(year, month)
    emp_ids = members_overlapping(db, teams, period_start, period_end)
    if not emp_ids:
        return {
            "year": year, "month": month, "teams": teams, "rows": [],
            "skipped_no_profile": 0, "skipped": [],
        }

    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(emp_ids))
        .order_by(Employee.display_name)
        .all()
    )
    cache = _build_report_cache(db, [e.id for e in employees], period_start, period_end)

    evaluated = [e for e in employees if _resolve_profile(db, e, cache) is not None]
    rows = [
        compute_employee_month(
            db, emp, teams, year, month, settings=st, direction=direction, cache=cache,
        )
        for emp in evaluated
    ]
    rows.sort(key=lambda r: (r["total"] is None, r["total"] or 0))

    # Поимённый список выпавших из оценки: числа мало, руководителю нужно
    # знать, кого именно он не видит и по какой роли (спека доработок, п. 2).
    evaluated_ids = {e.id for e in evaluated}
    role_labels = {r.code: r.label for r in db.query(Role).all()}
    skipped = [
        {
            "employee_id": e.id,
            "employee_name": e.display_name,
            "role_code": e.role,
            "role_label": role_labels.get(e.role or "", "Роль не заполнена" if not e.role else e.role),
        }
        for e in employees if e.id not in evaluated_ids
    ]
    return {
        "year": year, "month": month, "teams": teams, "rows": rows,
        "skipped_no_profile": len(skipped), "skipped": skipped,
    }


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


# === Утверждение месяца: снимок и его чтение (BLOCKER 1) ===

def build_approval_payload(db: Session, team: str, year: int, month: int) -> dict:
    """Снимок утверждаемого месяца: отчёт команды, сводка и применённые правила расчёта.

    Кладётся в ``KpiApproval.payload_json`` при утверждении и отдаётся назад
    без пересчёта — иначе правка весов профиля или норматива Cycle Time после
    утверждения молча меняла бы уже подписанный результат. В снимок
    сознательно попадают не только строки отчёта (веса и значения там уже
    есть на метрику), но и общие правила месяца — не по строкам восстановить,
    какой норматив или срок внесения часов действовал на момент утверждения.
    """
    report = build_report(db, [team], year, month)
    report["summary"] = summarize_report(report["rows"])
    st = read_kpi_settings(db)
    quarter = QUARTER_OF_MONTH[month]
    report["rules_snapshot"] = {
        "excluded_statuses": st.excluded_statuses,
        "worklog_deadline_mode": st.worklog_deadline_mode,
        "worklog_deadline_hours": st.worklog_deadline_hours,
        "worklog_deadline_days": st.worklog_deadline_days,
        "worklog_deadline_time": st.worklog_deadline_time,
        "empty_policy": st.empty_policy,
        "cycle_time_norm": {
            "team": team, "year": year, "quarter": quarter,
            "value": _norm_for(db, team, year, month),
        },
    }
    return report


def save_approval(
    db: Session, team: str, year: int, month: int, approved_by: str, approved_at: datetime, payload: str,
) -> KpiApproval:
    """Записать снимок утверждения, устойчиво к одновременному утверждению.

    Двое руководителей могут закрыть один и тот же месяц одновременно: оба
    видят, что снимка ещё нет, оба пытаются вставить строку. Уникальное
    ограничение (``team``, ``year``, ``month``) не даёт вставиться второй —
    без обработки это 500 на ровном месте. Проигравший гонку откатывается,
    перечитывает уже вставленную соперником строку и обновляет её той же
    информацией, что вставлял бы сам (см. ревью, ВАЖНО 3).
    """
    row = db.query(KpiApproval).filter_by(team=team, year=year, month=month).first()
    if row is None:
        row = KpiApproval(
            team=team, year=year, month=month,
            approved_by=approved_by, approved_at=approved_at, payload_json=payload,
        )
        db.add(row)
        try:
            db.commit()
            return row
        except IntegrityError:
            db.rollback()
            row = db.query(KpiApproval).filter_by(team=team, year=year, month=month).first()
            if row is None:
                raise

    row.approved_by = approved_by
    row.approved_at = approved_at
    row.payload_json = payload
    db.commit()
    return row


def report_with_approvals(
    db: Session, teams: list[str], year: int, month: int, direction: Optional[str] = None,
) -> dict:
    """Отчёт по командам: утверждённые команды отдаются из снимка, остальные считаются вживую.

    Направление — фильтр отчёта в реальном времени; на утверждённые месяцы не
    действует, снимок замораживает месяц целиком таким, каким он был на дату
    утверждения. Живая часть по-прежнему считается одним общим проходом по
    всем неутверждённым командам (см. ``build_report``/``ReportCache``), а не
    по одной на команду.
    """
    approvals = {
        a.team: a
        for a in db.query(KpiApproval).filter(
            KpiApproval.team.in_(teams), KpiApproval.year == year, KpiApproval.month == month,
        ).all()
    } if teams else {}

    live_teams = [t for t in teams if t not in approvals]
    rows: list[dict] = []
    skipped: list[dict] = []
    if live_teams:
        live = build_report(db, live_teams, year, month, direction=direction)
        rows.extend(live["rows"])
        skipped = live.get("skipped", [])

    approval_info: dict[str, dict] = {
        t: {"approved": False, "approved_by": None, "approved_at": None} for t in live_teams
    }
    for team, appr in approvals.items():
        frozen = json.loads(appr.payload_json)
        rows.extend(frozen.get("rows", []))
        approval_info[team] = {
            "approved": True, "approved_by": appr.approved_by, "approved_at": appr.approved_at.isoformat(),
        }

    rows.sort(key=lambda r: (r["total"] is None, r["total"] or 0))
    return {
        "year": year, "month": month, "teams": teams, "rows": rows,
        "approvals": approval_info,
        "skipped_no_profile": len(skipped), "skipped": skipped,
    }


def group_rows_by_team(rows: list[dict]) -> dict[str, list[dict]]:
    """Строки отчёта, сгруппированные по команде — для сводки по нескольким командам сразу."""
    by_team: dict[str, list[dict]] = {}
    for row in rows:
        by_team.setdefault(row.get("team") or "", []).append(row)
    return by_team


def _uniform_or_none(values: list) -> Optional[float]:
    """Значение, если оно одно и то же у всех, иначе ``None``.

    Используется для цели и жёлтой зоны строки команды: раньше фронт брал их
    у первого сотрудника — при разных профилях внутри команды заливка ячеек
    красилась по цели случайного человека (см. ревью, ВАЖНО 5).
    """
    present = {v for v in values if v is not None}
    return present.pop() if len(present) == 1 else None


def _team_metric_averages(rows: list[dict]) -> list[dict]:
    """Средние по метрикам для строки команды — только по людям с данными.

    Раньше среднее по колонке метрики строки команды считал фронт простым
    средним показанных на экране процентов; здесь тот же принцип, но на
    сервере — единственный источник чисел, который клиент только рисует
    (см. ревью, ВАЖНО 5).
    """
    by_code: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        for m in row["metrics"]:
            if m["code"] not in by_code:
                by_code[m["code"]] = {"code": m["code"], "name": m["name"], "values": []}
                order.append(m["code"])
            if m["has_data"] and m["value"] is not None:
                by_code[m["code"]]["values"].append(m["value"])
    result = []
    for code in order:
        entry = by_code[code]
        values = entry["values"]
        result.append({
            "code": code, "name": entry["name"],
            "value": sum(values) / len(values) if values else None,
            "has_data": bool(values),
        })
    return result


def build_teams_summary(
    db: Session, teams: list[str], year: int, month: int, direction: Optional[str] = None,
) -> list[dict]:
    """Итог по каждой команде за месяц плюс дельта к прошлому месяцу — двумя расчётами на всё, не на команду.

    Раньше на каждую команду вызывался отдельный расчёт отчёта (текущий и
    прошлый месяц) — свой проход по кэшу профилей/нормативов/календаря на
    каждую команду, сотни лишних запросов на десяток команд (см. ревью,
    ВАЖНО 4). Здесь один комбинированный расчёт на все команды сразу (за
    текущий и за прошлый месяц), а деление по командам — уже в памяти.

    Строка отдаёт не только итог, но и всё, что раньше клиент довычислял
    сам — среднее по каждой метрике, цель, жёлтую зону, число людей (см.
    ревью, ВАЖНО 5). Ключи сводки — запрошенные команды плюс любая команда,
    реально встретившаяся в строках, но не входившая в фильтр (в частности
    пустая — сотрудник без команды), иначе для неё итог всегда был прочерк.
    """
    prev_year, prev_month = previous_month(year, month)
    current = report_with_approvals(db, teams, year, month, direction=direction)
    prior = report_with_approvals(db, teams, prev_year, prev_month, direction=direction)
    current_by_team = group_rows_by_team(current["rows"])
    prior_by_team = group_rows_by_team(prior["rows"])

    extra_keys = [k for k in (*current_by_team, *prior_by_team) if k not in teams]
    team_keys = [*teams, *dict.fromkeys(extra_keys)]

    rows = []
    for key in team_keys:
        cur_rows = current_by_team.get(key, [])
        prior_rows = prior_by_team.get(key, [])
        cur_summary = summarize_report(cur_rows)
        prior_summary = summarize_report(prior_rows)
        delta = (
            cur_summary["avg_total"] - prior_summary["avg_total"]
            if cur_summary["avg_total"] is not None and prior_summary["avg_total"] is not None
            else None
        )
        rows.append({
            "team": key or None,
            "member_count": len(cur_rows),
            "avg_total": cur_summary["avg_total"],
            "below_target_count": cur_summary["below_target_count"],
            "no_data_metrics_count": cur_summary["no_data_metrics_count"],
            "delta": delta,
            "target_pct": _uniform_or_none([r["target_pct"] for r in cur_rows]),
            "warn_band_pct": _uniform_or_none([r["warn_band_pct"] for r in cur_rows]),
            "metrics": _team_metric_averages(cur_rows),
            # Норматив Cycle Time на квартал: без него метрика пуста у всей
            # команды, и это самая частая причина «нет данных» — страница
            # называет её прямо, а не оставляет руководителя гадать.
            "cycle_time_norm": _norm_for(db, key, year, month) if key else None,
        })
    return rows


def build_trend(
    db: Session,
    employee: Employee,
    teams: list[str],
    year: int,
    month: int,
    months: int,
    direction: Optional[str] = None,
) -> list[dict]:
    """Тренд сотрудника за N месяцев назад — с одним общим кэшем на весь диапазон.

    Раньше каждый месяц заново читал профиль, нормативы и календарь — полгода
    истории одного человека давали больше сотни запросов (см. ревью, ВАЖНО
    4). Профиль/нормативы не зависят от периода, календарь читается одним
    запросом с запасом на весь диапазон; основная команда на начало месяца
    пересчитывается каждый месяц отдельно (дешёвый индексный запрос) — она
    могла смениться внутри диапазона при переводе сотрудника.

    Утверждённые месяцы отдаются из снимка команды, а не пересчитываются —
    как и в отчёте (BLOCKER 1). Признак заморозки применяется только когда
    запрошена ровно одна команда: утверждение — понятие на одну команду,
    а не на произвольный набор.
    """
    st = read_kpi_settings(db)
    year_months: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(months):
        year_months.append((y, m))
        y, m = previous_month(y, m)
    year_months.reverse()

    first_start, _ = month_bounds(*year_months[0])
    _, last_end = month_bounds(*year_months[-1])
    cache = _build_report_cache(db, [employee.id], first_start, last_end)

    single_team = teams[0] if len(teams) == 1 else None
    points = []
    for yy, mm in year_months:
        approval = (
            db.query(KpiApproval).filter_by(team=single_team, year=yy, month=mm).first()
            if single_team else None
        )
        if approval is not None:
            frozen = json.loads(approval.payload_json)
            frozen_row = next(
                (r for r in frozen.get("rows", []) if r.get("employee_id") == employee.id), None,
            )
            if frozen_row is not None:
                points.append({"year": yy, "month": mm, **frozen_row, "approved": True})
                continue

        period_start, _ = month_bounds(yy, mm)
        if teams:
            cache.primary_team_by_employee[employee.id] = primary_team_on(db, employee.id, period_start) or ""
        row = compute_employee_month(db, employee, teams, yy, mm, settings=st, direction=direction, cache=cache)
        points.append({"year": yy, "month": mm, **row, "approved": False})
    return points
