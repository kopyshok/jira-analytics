"""Таблица разбора показателя: строка — задача, колонка — одно требование метрики.

Расшифровка раньше отдавала два списка («что считаем» и «с чем сравниваем»);
чтобы найти незачтённую задачу, руководитель сверял их глазами. Здесь тот же
отбор превращается в одну таблицу: у каждой строки видно, какое именно
требование не выполнено.

Проверки не зашиты в код: они выводятся из разницы между условиями числителя и
знаменателя той же метрики и считаются теми же предикатами, что и расчёт
(``conditions.condition_clauses``). Новое условие, добавленное в справочнике,
само становится колонкой.

Виды таблиц по способу расчёта метрики:

* ``checks``   — доля задач: колонка на каждое расхождение с базовым списком;
* ``norm``     — норматив к факту: факт, норматив, отклонение;
* ``score``    — балл к максимуму: оценки по задаче и их доля от максимума;
* ``worklogs`` — своевременность часов: строка — запись о часах, а не задача.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Query, Session

from app.models.issue import Issue
from app.models.kpi import KpiMetric
from app.services.kpi.conditions import (
    Condition,
    ConditionSet,
    build_issue_query,
    condition_clauses,
    describe_condition,
    describe_period,
    describe_person,
    field_label,
    period_clause,
    person_clause,
)
from app.services.kpi.kpi_service import (
    _norm_for,
    employee_periods,
    fact_value,
    has_fact_value,
    score_field_names,
    with_direction,
    worklog_items,
    worklog_rows,
)
from app.services.kpi.settings import KpiSettings, read_kpi_settings

# Таблица — инструмент разбора, а не выгрузка: строки режутся, полное число
# всегда рядом (``total_count``), выгрузка целиком — в Excel.
ROWS_LIMIT = 500


@dataclass
class Check:
    """Одно требование метрики: подпись колонки и предикаты для его проверки."""

    code: str
    label: str
    clauses: list


def _cond_key(cond: Condition) -> str:
    """Отпечаток условия — чтобы отличить требования числителя от общих со знаменателем."""
    return json.dumps([cond.attr, cond.op, cond.value], sort_keys=True, ensure_ascii=False)


def _checks_from_conditions(num_cs: ConditionSet, den_cs: ConditionSet) -> list[Check]:
    """Требования, которыми числитель строже знаменателя — они и есть колонки.

    Проверка заполненности нескольких полей разворачивается в колонку на поле:
    руководителю нужно знать, какое из трёх полей пустое, а не что «поля не
    заполнены».
    """
    shared = {_cond_key(c) for c in den_cs.conditions}
    checks: list[Check] = []
    for cond in num_cs.conditions:
        if _cond_key(cond) in shared:
            continue
        if cond.attr == "field_filled":
            names = cond.value if isinstance(cond.value, list) else [cond.value]
            for name in names:
                one = Condition(attr="field_filled", op="all", value=[name])
                clauses = condition_clauses(one)
                if clauses:
                    checks.append(Check(f"c{len(checks)}", field_label(name), clauses))
            continue
        clauses = condition_clauses(cond)
        if clauses:
            checks.append(Check(f"c{len(checks)}", describe_condition(cond), clauses))
    return checks


def _issue_row(issue: Issue, base_url: str) -> dict:
    return {
        "id": issue.id,
        "key": issue.key,
        "summary": issue.summary,
        "url": f"{base_url}/browse/{issue.key}" if base_url and issue.key else None,
        "status": issue.status,
        "resolution": issue.resolution,
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
    }


def _dropped_by_status(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: list[str],
    st: KpiSettings,
    kept_ids: set[str],
    base_url: str,
) -> list[dict]:
    """Задачи, отсеянные исключёнными статусами, — до сравнения они не дошли.

    Единственный шаг воронки, который руководитель на ведомости обычно и ищет
    («а где задача N?»): остальные шаги отсекают задачи чужого проекта или
    типа, и объяснять их поимённо незачем.
    """
    if not st.excluded_statuses:
        return []
    q = build_issue_query(db, cs, account_id, periods, [], teams)
    rows = [i for i in q.all() if i.id not in kept_ids]
    return [
        {**_issue_row(i, base_url), "reason": f"статус «{i.status}»"}
        for i in rows[:ROWS_LIMIT]
    ]


def _checks_table(
    db: Session,
    metric: KpiMetric,
    num_cs: ConditionSet,
    den_cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: list[str],
    st: KpiSettings,
    base_url: str,
) -> dict:
    """Доля задач: базовый список — знаменатель, колонки — чем строже числитель."""
    checks = _checks_from_conditions(num_cs, den_cs)
    if num_cs.person_field != den_cs.person_field:
        checks.append(Check(
            f"c{len(checks)}", describe_person(num_cs.person_field).capitalize(),
            [person_clause(num_cs, [account_id])],
        ))
    if num_cs.period_window != den_cs.period_window:
        checks.append(Check(
            f"c{len(checks)}", describe_period(num_cs.period_window).capitalize(),
            [period_clause(num_cs, periods)],
        ))

    base_q: Query = build_issue_query(db, den_cs, account_id, periods, st.excluded_statuses, teams)
    base_issues = base_q.all()
    base_ids = {i.id for i in base_issues}

    passed: dict[str, set[str]] = {
        check.code: {
            row[0] for row in base_q.with_entities(Issue.id).filter(and_(*check.clauses)).all()
        }
        for check in checks
    }

    num_q = build_issue_query(db, num_cs, account_id, periods, st.excluded_statuses, teams)
    numerator = num_q.all()
    counted_ids = {i.id for i in numerator}

    # У метрики с инверсией числитель — это нарушения (баг на проде), а не
    # успехи: там проблемная строка — попавшая в числитель, а не выпавшая из
    # него. Иначе таблица красит красным все нормальные задачи.
    invert = bool(metric.invert)

    rows: list[dict] = []
    for issue in base_issues:
        results = {c.code: issue.id in passed[c.code] for c in checks}
        counted = issue.id in counted_ids
        problem = counted if invert else not counted
        reasons = (
            [c.label for c in checks if results[c.code]] if invert
            else [c.label for c in checks if not results[c.code]]
        )
        rows.append({
            **_issue_row(issue, base_url),
            "checks": results,
            "counted": counted,
            "problem": problem,
            "reasons": reasons if problem else [],
        })
    # Числитель метрики может отбирать задачи, которых нет в списке сравнения
    # (например, «качество разработки» считает баги, связанные с задачами
    # сотрудника). Молча их прятать нельзя — иначе строк меньше, чем в дроби.
    for issue in numerator:
        if issue.id in base_ids:
            continue
        rows.append({
            **_issue_row(issue, base_url),
            "checks": {c.code: True for c in checks},
            "counted": True,
            "problem": invert,
            "reasons": [c.label for c in checks] if invert else [],
            "outside_base": True,
        })

    rows.sort(key=lambda r: (not r["problem"], r["key"] or ""))
    return {
        "kind": "checks",
        "invert": invert,
        "checks": [{"code": c.code, "label": c.label} for c in checks],
        "rows": rows[:ROWS_LIMIT],
        "total_count": len(rows),
        "counted_count": sum(1 for r in rows if r["counted"]),
        "problem_count": sum(1 for r in rows if r["problem"]),
        "truncated": len(rows) > ROWS_LIMIT,
        "dropped": _dropped_by_status(
            db, den_cs, account_id, periods, teams, st, base_ids, base_url,
        ),
    }


def _norm_table(
    db: Session,
    metric: KpiMetric,
    num_cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: list[str],
    st: KpiSettings,
    base_url: str,
    norm_value: Optional[float],
) -> dict:
    """Норматив к факту: факт задачи против норматива команды.

    В таблицу попадают и задачи без факта — в расчёт они не входят, но
    руководителю важнее всего именно они: это дыра в данных, а не результат.
    """
    issues = build_issue_query(
        db, num_cs, account_id, periods, st.excluded_statuses, teams,
    ).all()
    rows = []
    for issue in issues:
        counted = has_fact_value(issue, metric)
        fact = fact_value(issue, metric)
        paused = issue.paused_days or 0.0
        over = bool(counted and norm_value and fact and fact > norm_value)
        deviation = (
            round(100.0 * (fact - norm_value) / norm_value, 1)
            if counted and fact and norm_value else None
        )
        reasons = []
        if not counted:
            reasons.append("нет фактического значения")
        elif over:
            reasons.append(f"превышение норматива на {deviation}%")
        if paused:
            reasons.append(f"вычтено {paused:g} дн паузы")
        rows.append({
            **_issue_row(issue, base_url),
            "fact": fact,
            "paused_days": paused or None,
            "deviation_pct": deviation,
            "counted": counted,
            "problem": (not counted) or over,
            "reasons": reasons,
        })
    rows.sort(key=lambda r: (not r["problem"], -(r["fact"] or 0)))
    return {
        "kind": "norm",
        "checks": [],
        "norm_value": norm_value,
        "rows": rows[:ROWS_LIMIT],
        "total_count": len(rows),
        "counted_count": sum(1 for r in rows if r["counted"]),
        "problem_count": sum(1 for r in rows if r["problem"]),
        "truncated": len(rows) > ROWS_LIMIT,
        "dropped": [],
    }


def _score_table(
    db: Session,
    metric: KpiMetric,
    num_cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: list[str],
    st: KpiSettings,
    base_url: str,
) -> dict:
    """Балл к максимуму: оценки по задаче и их доля от максимума.

    Задача без единой оценки в расчёт не входит — в таблице она видна как
    пробел в данных, иначе показатель молча считается по половине задач.
    """
    names = score_field_names(metric)
    score_max = metric.score_max or 5.0
    issues = build_issue_query(
        db, num_cs, account_id, periods, st.excluded_statuses, teams,
    ).all()
    rows = []
    for issue in issues:
        values = [getattr(issue, n, None) for n in names]
        usable = [v for v in values if v is not None]
        avg = round(sum(usable) / len(usable), 2) if usable else None
        pct = round(100.0 * avg / score_max, 1) if avg is not None and score_max else None
        low = pct is not None and pct < 100
        rows.append({
            **_issue_row(issue, base_url),
            "score": avg,
            "score_pct": pct,
            "counted": avg is not None,
            "problem": avg is None or low,
            "reasons": (
                ["нет оценки заказчика"] if avg is None
                else ([f"оценка {avg} из {score_max:g}"] if low else [])
            ),
        })
    rows.sort(key=lambda r: (not r["problem"], r["score"] if r["score"] is not None else 0))
    return {
        "kind": "score",
        "checks": [],
        "score_max": score_max,
        "rows": rows[:ROWS_LIMIT],
        "total_count": len(rows),
        "counted_count": sum(1 for r in rows if r["counted"]),
        "problem_count": sum(1 for r in rows if r["problem"]),
        "truncated": len(rows) > ROWS_LIMIT,
        "dropped": [],
    }


def _delay_hours(started_at: Optional[datetime], created_at: Optional[datetime]) -> Optional[float]:
    """На сколько часов запись о часах отстала от работы, которую описывает."""
    if started_at is None or created_at is None:
        return None
    return round((created_at - started_at).total_seconds() / 3600.0, 1)


def _worklog_table(
    db: Session,
    num_cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    teams: list[str],
    st: KpiSettings,
    base_url: str,
) -> dict:
    """Своевременность часов: строка — запись о часах, проблема — опоздание с внесением."""
    def brief(w) -> dict:
        return {
            # У одной задачи бывает несколько записей о часах — строку таблицы
            # различает идентификатор записи, а не ключ задачи.
            "id": w.id,
            "key": w.issue.key if w.issue else None,
            "summary": w.issue.summary if w.issue else None,
            "url": f"{base_url}/browse/{w.issue.key}" if base_url and w.issue else None,
            "started_at": w.started_at.isoformat() if w.started_at else None,
            "created_at": w.jira_created_at.isoformat() if w.jira_created_at else None,
            "hours": w.hours,
        }

    on_time, late = worklog_items(db, num_cs, account_id, periods, teams, st)
    late_ids = {w.id for w in late}
    rows = []
    for w in on_time + late:
        is_late = w.id in late_ids
        rows.append({
            **brief(w),
            "delay_hours": _delay_hours(w.started_at, w.jira_created_at),
            "counted": not is_late,
            "problem": is_late,
            "reasons": ["часы внесены с опозданием"] if is_late else [],
        })
    rows.sort(key=lambda r: (not r["problem"], r["started_at"] or ""))

    # Записи без даты внесения расчёт не судит вообще. Показатель от этого
    # бывает пустым при полном месяце работы — без этого списка причина
    # выглядит как ошибка сервиса.
    undated = [
        {**brief(w), "reason": "нет даты внесения записи"}
        for w in worklog_rows(db, num_cs, account_id, periods, teams, st)
        if w.jira_created_at is None
    ]
    return {
        "kind": "worklogs",
        "checks": [],
        "rows": rows[:ROWS_LIMIT],
        "total_count": len(rows),
        "counted_count": len(on_time),
        "problem_count": len(late),
        "truncated": len(rows) > ROWS_LIMIT,
        "dropped": undated[:ROWS_LIMIT],
    }


def build_table(
    db: Session,
    metric: KpiMetric,
    account_id: str,
    year: int,
    month: int,
    teams: list[str],
    base_url: str,
    direction: Optional[str] = None,
    settings: Optional[KpiSettings] = None,
) -> dict:
    """Таблица разбора показателя одного сотрудника за месяц.

    Отбор — тот же, что и в расчёте отчёта (отрезки участия в команде,
    исключённые статусы, фильтр направления), поэтому «засчитано» в таблице
    совпадает с числителем в дроби над ней.
    """
    st = settings or read_kpi_settings(db)
    periods, employee = employee_periods(db, account_id, year, month, teams)
    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)

    if num_cs.unit == "worklogs":
        return _worklog_table(db, num_cs, account_id, periods, teams, st, base_url)

    if metric.calc_kind == "norm_to_fact":
        team = (employee.team if employee else None) or (teams[0] if teams else "")
        if teams and team not in teams:
            team = teams[0]
        return _norm_table(
            db, metric, num_cs, account_id, periods, teams, st, base_url,
            _norm_for(db, team, year, month),
        )

    if metric.calc_kind == "score_to_max":
        return _score_table(db, metric, num_cs, account_id, periods, teams, st, base_url)

    den_cs = with_direction(ConditionSet.from_json(metric.denominator_json), direction)
    return _checks_table(
        db, metric, num_cs, den_cs, account_id, periods, teams, st, base_url,
    )
