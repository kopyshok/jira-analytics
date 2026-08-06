"""Предпросмотр метрики: воронка отбора, разбор по людям, проверка одной задачи.

Отладочный инструмент конструктора метрики. Считает **несохранённое**
определение метрики — иначе проверить заведомо неверную настройку можно было
бы только положив её в справочник, откуда её тут же подхватил бы отчёт.

Главное здесь не итоговый процент, а воронка: сколько задач осталось после
каждого условия. Когда метрика показывает «нет данных», ровно это отвечает
на вопрос «какое условие всё съело».
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.issue import Issue
from app.models.kpi import KpiMetric
from app.models.worklog import Worklog
from app.services.kpi.conditions import (
    ConditionSet,
    condition_clauses,
    describe_condition,
    describe_period,
    describe_person,
    period_clause,
    person_clause,
)
from app.services.kpi.kpi_service import (
    _norm_for,
    compute_metric,
    period_bounds,
    resolve_breakdown,
    with_direction,
    worklog_items,
)
from app.services.kpi.settings import KpiSettings, read_kpi_settings
from app.services.kpi.timeliness import is_worklog_late, load_calendar
from app.services.team_membership import member_intervals, members_overlapping

# Списки задач в ответе режутся: воронка и числа честные, а таблица —
# только образец. Полное число всегда рядом.
ITEMS_LIMIT = 200


@dataclass
class FunnelStep:
    """Один шаг воронки: подпись условия, остаток и сколько отсеяно."""

    label: str
    remaining: int
    dropped: Optional[int]

    def as_dict(self) -> dict:
        return {"label": self.label, "remaining": self.remaining, "dropped": self.dropped}


def _base_issue_clauses(
    cs: ConditionSet, periods: list[tuple[date, date]], teams: Optional[list[str]],
) -> list:
    """Стартовое множество воронки: команда и окно периода, без условий метрики."""
    clauses = [period_clause(cs, periods)]
    if teams:
        clauses.append(Issue.team.in_(teams))
    return clauses


def issue_funnel(
    db: Session,
    cs: ConditionSet,
    account_ids: list[str],
    periods: list[tuple[date, date]],
    teams: Optional[list[str]],
    settings: KpiSettings,
) -> list[dict]:
    """Пошаговый отбор задач: условия метрики, исключённые статусы, «кто считается».

    Порядок шагов повторяет то, как условие читается человеком: сначала
    широкий отбор по атрибутам, потом статусы, в конце — привязка к людям.
    Итоговый остаток совпадает с числителем/знаменателем расчёта.
    """
    clauses = _base_issue_clauses(cs, periods, teams)

    def count() -> int:
        return db.query(Issue.id).filter(and_(*clauses)).count()

    steps = [FunnelStep(
        label=f"Все задачи периода · {describe_period(cs.period_window)}",
        remaining=count(), dropped=None,
    )]

    for cond in cs.conditions:
        extra = condition_clauses(cond)
        if not extra:
            continue
        previous = steps[-1].remaining
        clauses.extend(extra)
        remaining = count()
        steps.append(FunnelStep(describe_condition(cond), remaining, previous - remaining))

    if settings.excluded_statuses:
        previous = steps[-1].remaining
        clauses.append(
            or_(Issue.status.is_(None), ~Issue.status.in_(settings.excluded_statuses)),
        )
        remaining = count()
        steps.append(FunnelStep(
            f"Статус не в исключённых: {', '.join(settings.excluded_statuses)}",
            remaining, previous - remaining,
        ))

    previous = steps[-1].remaining
    clauses.append(person_clause(cs, account_ids))
    remaining = count()
    steps.append(FunnelStep(
        f"Кто считается: {describe_person(cs.person_field)}", remaining, previous - remaining,
    ))

    return [s.as_dict() for s in steps]


def worklog_funnel(
    db: Session,
    cs: ConditionSet,
    employee_ids: list[str],
    periods: list[tuple[date, date]],
    teams: Optional[list[str]],
    settings: KpiSettings,
    calendar: dict[date, bool],
) -> list[dict]:
    """Воронка для метрик, считающих записи о часах, а не задачи.

    Период здесь — дата самой записи, а не дата закрытия задачи (так же, как
    в расчёте, см. ``kpi_service.worklog_items``). Два последних шага —
    единственное место, где метрика своевременности отличается от прочих:
    запись без даты внесения выбывает совсем, остальные делятся на вовремя и
    просроченные.
    """
    period_clauses = [
        and_(
            Worklog.started_at >= datetime.combine(start, datetime.min.time()),
            Worklog.started_at <= datetime.combine(end, datetime.max.time()),
        )
        for start, end in periods
    ]
    base = (
        db.query(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(Worklog.employee_id.in_(employee_ids))
        .filter(or_(*period_clauses))
    )
    steps = [FunnelStep("Все записи о часах за период", base.count(), None)]

    clauses: list = []
    for cond in cs.conditions:
        extra = condition_clauses(cond)
        if not extra:
            continue
        previous = steps[-1].remaining
        clauses.extend(extra)
        remaining = base.filter(and_(*clauses)).count()
        steps.append(FunnelStep(describe_condition(cond), remaining, previous - remaining))

    if settings.excluded_statuses:
        previous = steps[-1].remaining
        clauses.append(or_(Issue.status.is_(None), ~Issue.status.in_(settings.excluded_statuses)))
        remaining = base.filter(and_(*clauses)).count()
        steps.append(FunnelStep(
            f"Статус задачи не в исключённых: {', '.join(settings.excluded_statuses)}",
            remaining, previous - remaining,
        ))
    if teams:
        previous = steps[-1].remaining
        clauses.append(Issue.team.in_(teams))
        remaining = base.filter(and_(*clauses)).count()
        steps.append(FunnelStep("Команда задачи", remaining, previous - remaining))

    rows = base.filter(and_(*clauses)).all() if clauses else base.all()
    judged = [w for w in rows if w.jira_created_at is not None and w.started_at is not None]
    steps.append(FunnelStep(
        "Есть дата внесения записи", len(judged), steps[-1].remaining - len(judged),
    ))
    late = [w for w in judged if is_worklog_late(calendar, w.started_at, w.jira_created_at, settings)]
    steps.append(FunnelStep("Внесены с опозданием", len(late), len(judged) - len(late)))
    return [s.as_dict() for s in steps]


def _issue_brief(issue: Issue, base_url: Optional[str]) -> dict:
    return {
        "key": issue.key,
        "summary": issue.summary,
        "status": issue.status,
        "resolution": issue.resolution,
        "url": f"{base_url}/browse/{issue.key}" if base_url and issue.key else None,
    }


@dataclass
class PreviewContext:
    """Разрешённые параметры предпросмотра: люди, отрезки участия, календарь."""

    employees: list[Employee]
    intervals: dict[str, list[tuple[date, date]]]
    period: tuple[date, date]
    settings: KpiSettings
    calendar: dict[date, bool]

    def periods_for(self, employee: Employee) -> list[tuple[date, date]]:
        return self.intervals.get(employee.id) or [self.period]

    @property
    def account_ids(self) -> list[str]:
        return [e.jira_account_id for e in self.employees if e.jira_account_id]

    @property
    def all_periods(self) -> list[tuple[date, date]]:
        """Общие границы периода — воронка по команде считается по периоду целиком."""
        return [self.period]


def build_context(
    db: Session,
    team: str,
    year: int,
    month: int,
    account_id: Optional[str],
    calendar_buffer_days: int,
    months: int = 1,
) -> PreviewContext:
    """Собрать состав команды на период и всё, что нужно для расчёта, одним проходом.

    ``months`` — длина периода: предпросмотр метрики в конструкторе всегда
    смотрит на один месяц, а воронка под расшифровкой в отчёте обязана
    повторять период отчёта, иначе шаги воронки и дробь над ней разойдутся.
    """
    period_start, period_end = period_bounds(year, month, months)
    emp_ids = members_overlapping(db, [team], period_start, period_end) if team else []
    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(emp_ids))
        .order_by(Employee.display_name)
        .all()
        if emp_ids else []
    )
    if account_id:
        employees = [e for e in employees if e.jira_account_id == account_id]
    intervals = (
        member_intervals(db, [team], period_start, period_end) if team and employees else {}
    )
    calendar = load_calendar(
        db,
        period_start - timedelta(days=calendar_buffer_days),
        period_end + timedelta(days=calendar_buffer_days),
    )
    return PreviewContext(
        employees=employees, intervals=intervals, period=(period_start, period_end),
        settings=read_kpi_settings(db), calendar=calendar,
    )


def preview_metric(
    db: Session,
    metric: KpiMetric,
    team: str,
    year: int,
    month: int,
    account_id: Optional[str],
    direction: Optional[str],
    base_url: Optional[str],
    calendar_buffer_days: int,
) -> dict:
    """Посчитать метрику на команде и месяце, вернуть воронку и разбор по людям.

    ``metric`` — объект в памяти, собранный из формы конструктора; в базу он
    не попадает.
    """
    ctx = build_context(db, team, year, month, account_id, calendar_buffer_days)
    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)
    den_cs = (
        with_direction(ConditionSet.from_json(metric.denominator_json), direction)
        if metric.denominator_json else None
    )

    if num_cs.unit == "worklogs":
        numerator_funnel = worklog_funnel(
            db, num_cs, [e.id for e in ctx.employees], ctx.all_periods,
            [team] if team else None, ctx.settings, ctx.calendar,
        )
        denominator_funnel: list[dict] = []
    else:
        numerator_funnel = issue_funnel(
            db, num_cs, ctx.account_ids, ctx.all_periods,
            [team] if team else None, ctx.settings,
        )
        denominator_funnel = issue_funnel(
            db, den_cs, ctx.account_ids, ctx.all_periods,
            [team] if team else None, ctx.settings,
        ) if den_cs else []

    rows = []
    for emp in ctx.employees:
        if not emp.jira_account_id:
            continue
        result = compute_metric(
            db, metric, emp.jira_account_id, ctx.periods_for(emp), [team] if team else None,
            settings=ctx.settings, norm_value=_norm_hint(db, metric, team, year, month),
            direction=direction, calendar=ctx.calendar,
        )
        rows.append({
            "employee_id": emp.id,
            "employee_name": emp.display_name,
            "account_id": emp.jira_account_id,
            "numerator": result.numerator,
            "denominator": result.denominator,
            "value": result.value,
            "has_data": result.has_data,
        })

    items: dict = {"numerator": [], "denominator": [], "numerator_count": 0, "denominator_count": 0}
    if account_id and ctx.employees:
        breakdown = resolve_breakdown(
            db, metric, account_id, year, month, [team] if team else [],
            direction=direction, settings=ctx.settings,
        )
        items = _breakdown_items(breakdown, base_url)

    values = [r["value"] for r in rows if r["has_data"] and r["value"] is not None]
    return {
        "metric_name": metric.name,
        "calc_kind": metric.calc_kind,
        "team": team,
        "year": year,
        "month": month,
        "team_value": sum(values) / len(values) if values else None,
        "people_with_data": len(values),
        "people_total": len(rows),
        "numerator_funnel": numerator_funnel,
        "denominator_funnel": denominator_funnel,
        "rows": rows,
        "items": items,
    }


def _norm_hint(
    db: Session, metric: KpiMetric, team: str, year: int, month: int,
) -> Optional[float]:
    """Норматив Cycle Time — метрике «норматив к факту» без него считать нечего."""
    if metric.calc_kind != "norm_to_fact":
        return None
    return _norm_for(db, team, year, month)


def _breakdown_items(breakdown: dict, base_url: Optional[str]) -> dict:
    """Списки «что считаем» / «с чем сравниваем» — усечённые, с полным числом рядом."""
    if breakdown.get("unit") == "worklogs":
        def brief(w) -> dict:
            return {
                "key": w.issue.key if w.issue else None,
                "summary": w.issue.summary if w.issue else None,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "jira_created_at": w.jira_created_at.isoformat() if w.jira_created_at else None,
                "hours": w.hours,
            }
        numerator = breakdown["numerator"]
        denominator = breakdown["denominator"]
        return {
            "numerator": [brief(w) for w in numerator[:ITEMS_LIMIT]],
            "denominator": [brief(w) for w in denominator[:ITEMS_LIMIT]],
            "numerator_count": len(numerator),
            "denominator_count": len(denominator),
        }
    numerator = breakdown["numerator"]
    denominator = breakdown["denominator"]
    return {
        "numerator": [_issue_brief(i, base_url) for i in numerator[:ITEMS_LIMIT]],
        "denominator": [_issue_brief(i, base_url) for i in denominator[:ITEMS_LIMIT]],
        "numerator_count": len(numerator),
        "denominator_count": len(denominator),
    }


def explain_issue(
    db: Session,
    metric: KpiMetric,
    side: str,
    issue_key: str,
    team: str,
    year: int,
    month: int,
    account_id: Optional[str],
    direction: Optional[str],
    calendar_buffer_days: int,
) -> dict:
    """На каком шаге отбора отсеялась конкретная задача.

    Отвечает на самый частый вопрос при разборе с сотрудником — «а где моя
    задача». Проверка идёт теми же предикатами, что и расчёт, по одной
    задаче: первый непройденный шаг и есть ответ.
    """
    issue = db.query(Issue).filter(Issue.key == issue_key.strip().upper()).first()
    if issue is None:
        return {"found": False, "issue_key": issue_key, "passed": False, "failed_step": None,
                "steps": []}

    ctx = build_context(db, team, year, month, account_id, calendar_buffer_days)
    raw = metric.denominator_json if side == "denominator" else metric.numerator_json
    if not raw:
        raw = metric.numerator_json
    cs = with_direction(ConditionSet.from_json(raw), direction)

    account_ids = ctx.account_ids
    checks: list[tuple[str, list]] = [
        (f"Все задачи периода · {describe_period(cs.period_window)}",
         [period_clause(cs, ctx.all_periods)]),
    ]
    if team:
        checks.append(("Команда задачи", [Issue.team.in_([team])]))
    for cond in cs.conditions:
        extra = condition_clauses(cond)
        if extra:
            checks.append((describe_condition(cond), extra))
    if ctx.settings.excluded_statuses:
        checks.append((
            f"Статус не в исключённых: {', '.join(ctx.settings.excluded_statuses)}",
            [or_(Issue.status.is_(None), ~Issue.status.in_(ctx.settings.excluded_statuses))],
        ))
    if account_ids:
        checks.append((
            f"Кто считается: {describe_person(cs.person_field)}",
            [person_clause(cs, account_ids)],
        ))

    steps = []
    failed_step = None
    for label, clauses in checks:
        ok = db.query(Issue.id).filter(Issue.id == issue.id).filter(and_(*clauses)).count() > 0
        steps.append({"label": label, "passed": ok})
        if not ok and failed_step is None:
            failed_step = label
    return {
        "found": True,
        "issue_key": issue.key,
        "summary": issue.summary,
        "passed": failed_step is None,
        "failed_step": failed_step,
        "steps": steps,
    }


def compare_deadline_modes(
    db: Session, team: str, year: int, month: int, calendar_buffer_days: int,
) -> dict:
    """Своевременность трудозатрат обоими способами сразу — до переключения.

    Способ по ТЗ строже: он не прощает выходные. Смотреть на разницу нужно
    заранее, потому что переключение задним числом меняет уже показанные
    руководителю проценты за прошлые (неутверждённые) месяцы.
    """
    metric = (
        db.query(KpiMetric).filter(KpiMetric.code == "worklog_timeliness").first()
    )
    if metric is None:
        return {"team": team, "year": year, "month": month, "rows": []}

    ctx = build_context(db, team, year, month, None, calendar_buffer_days)
    cs = ConditionSet.from_json(metric.numerator_json)
    by_hours = replace(ctx.settings, worklog_deadline_mode="hours_from_start")
    by_calendar = replace(ctx.settings, worklog_deadline_mode="calendar")

    rows = []
    for emp in ctx.employees:
        if not emp.jira_account_id:
            continue
        periods = ctx.periods_for(emp)
        teams = [team] if team else None
        hours_on_time, hours_late = worklog_items(
            db, cs, emp.jira_account_id, periods, teams, by_hours, ctx.calendar,
        )
        cal_on_time, cal_late = worklog_items(
            db, cs, emp.jira_account_id, periods, teams, by_calendar, ctx.calendar,
        )
        total = len(hours_on_time) + len(hours_late)
        if total == 0:
            rows.append({
                "employee_name": emp.display_name, "worklog_count": 0,
                "hours_from_start": None, "calendar": None,
            })
            continue
        rows.append({
            "employee_name": emp.display_name,
            "worklog_count": total,
            "hours_from_start": 100.0 * (1 - len(hours_late) / total),
            "calendar": 100.0 * (1 - len(cal_late) / (len(cal_on_time) + len(cal_late))),
        })
    return {"team": team, "year": year, "month": month, "rows": rows}
