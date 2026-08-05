"""Очередь работы: сколько часов висит на человеке и на сколько дней это тянет."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Absence, ProductionCalendarDay
from app.services.team_desk.config import load_config

DAILY_NORM_HOURS = 8.0


def _calendar_hours(db: Session, start: date, end: date) -> dict[date, float]:
    """Нормо-часы по дням окна. Нет записи в календаре — будни по 8, выходные 0."""
    rows = (
        db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end)
        .all()
    )
    known = {row.date: float(row.hours or 0) for row in rows}
    out: dict[date, float] = {}
    cursor = start
    while cursor <= end:
        out[cursor] = known.get(
            cursor, DAILY_NORM_HOURS if cursor.weekday() < 5 else 0.0
        )
        cursor += timedelta(days=1)
    return out


def _absent_days(
    db: Session, employee_ids: list[str], start: date, end: date
) -> dict[str, set]:
    """Дни отсутствий каждого сотрудника внутри окна."""
    if not employee_ids:
        return {}
    rows = (
        db.query(Absence)
        .filter(
            Absence.employee_id.in_(employee_ids),
            Absence.start_date <= end,
            Absence.end_date >= start,
        )
        .all()
    )
    out: dict[str, set] = {}
    for row in rows:
        cursor = max(row.start_date, start)
        last = min(row.end_date, end)
        while cursor <= last:
            out.setdefault(row.employee_id, set()).add(cursor)
            cursor += timedelta(days=1)
    return out


def queue_for_developers(
    db: Session,
    issue_rows: list[dict],
    employee_by_account: dict[str, str],
    start: date,
    days: int = 7,
) -> dict[str, dict]:
    """Очередь работы на окно `days` дней вперёд.

    queue_hours — сумма оценок незакрытых задач в статусах очереди.
    available_hours — нормо-часы окна минус дни отсутствий.
    queue_days — во сколько рабочих дней укладывается очередь; None, если
    свободных часов в окне нет (человек в отпуске).
    Задачи без оценки в часы не попадают, но считаются отдельно — иначе
    очередь врала бы в меньшую сторону.
    """
    cfg = load_config(db)
    end = start + timedelta(days=days - 1)
    calendar = _calendar_hours(db, start, end)
    employee_ids = [e for e in employee_by_account.values() if e]
    absences = _absent_days(db, employee_ids, start, end)

    per_dev: dict[str, dict] = {}
    for row in issue_rows:
        dev_id = row.get("developer_id")
        if not dev_id or row.get("status") not in cfg.queue_statuses:
            continue
        bucket = per_dev.setdefault(
            dev_id, {"queue_hours": 0.0, "without_estimate": 0}
        )
        est = row.get("est_hours")
        if est is None:
            bucket["without_estimate"] += 1
        else:
            bucket["queue_hours"] += float(est)

    for dev_id, bucket in per_dev.items():
        employee_id = employee_by_account.get(dev_id)
        away = absences.get(employee_id, set()) if employee_id else set()
        available = sum(hours for day, hours in calendar.items() if day not in away)
        bucket["available_hours"] = available
        bucket["queue_days"] = (
            round(bucket["queue_hours"] / DAILY_NORM_HOURS, 1) if available > 0 else None
        )
        bucket["overloaded"] = available > 0 and bucket["queue_hours"] > available
    return per_dev
