"""Часы по командам и месяцам: база сервиса против новой Jira.

Команда — ``issues.team`` задачи ворклога (пусто — «Без команды»), месяц —
по началу ворклога во времени базы (ворклог новой Jira сдвигается на
найденное смещение). Расхождение больше 1 % подсвечивается.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Issue, Worklog
from app.services.jira_migration.fingerprints import DbWorklog, DcWorklog, minute_of

NO_TEAM = "Без команды"
DIFF_THRESHOLD_PCT = 1.0
# Решение 16.10.2026: после переезда сервис держит списания только с 2026 года —
# более старую историю из новой Jira не загружает и в сверке часов не сравнивает.
HISTORY_START = date(2026, 1, 1)
_EPOCH = datetime(1970, 1, 1)

TeamMonth = tuple[str, str]


def month_of_minute(minute: int) -> str:
    return (_EPOCH + timedelta(minutes=minute)).strftime("%Y-%m")


def history_start(earliest: date) -> date:
    """С какой даты сервис держит списания после переезда: не раньше ``HISTORY_START``."""
    return max(earliest, HISTORY_START)


def hours_from_month(report: Mapping[str, Any]) -> str:
    """Первый месяц сверки часов (``ГГГГ-ММ``) по самой ранней дате списаний в базе из отчёта."""
    raw = report.get("db_worklogs_min_date")
    earliest = date.fromisoformat(raw) if raw else HISTORY_START
    return history_start(earliest).strftime("%Y-%m")


def _team(team: Optional[str]) -> str:
    return team or NO_TEAM


def load_db_worklogs(db: Session) -> list[DbWorklog]:
    """Все ворклоги базы с ключом и командой задачи."""
    query = (
        db.query(Issue.key, Worklog.started_at, Worklog.time_spent_seconds, Worklog.employee_id, Issue.team)
        .select_from(Worklog)
        .join(Issue, Issue.id == Worklog.issue_id)
        .yield_per(5000)
    )
    return [
        DbWorklog(key, minute_of(started), int(seconds or 0), employee_id, team)
        for key, started, seconds, employee_id, team in query
    ]


def db_seconds(rows: Iterable[DbWorklog]) -> dict[TeamMonth, int]:
    out: dict[TeamMonth, int] = defaultdict(int)
    for row in rows:
        out[(_team(row.team), month_of_minute(row.minute))] += row.seconds
    return dict(out)


def dc_seconds(
    rows: Iterable[DcWorklog],
    team_by_key: Mapping[str, Optional[str]],
    offset_hours: int,
) -> dict[TeamMonth, int]:
    shift = offset_hours * 60
    out: dict[TeamMonth, int] = defaultdict(int)
    for row in rows:
        out[(_team(team_by_key.get(row.key)), month_of_minute(row.minute + shift))] += row.seconds
    return dict(out)


def to_hours(seconds: Mapping[TeamMonth, int]) -> dict[TeamMonth, float]:
    return {key: round(value / 3600, 2) for key, value in seconds.items()}


def _diff_pct(base: float, other: float) -> float:
    if base == 0:
        return 0.0 if other == 0 else 100.0
    return round((other - base) / base * 100, 2)


def compare_hours(
    db_hours: Mapping[TeamMonth, float],
    dc_hours: Mapping[TeamMonth, float],
    threshold_pct: float = DIFF_THRESHOLD_PCT,
    from_month: str = "",
) -> list[dict[str, Any]]:
    """Строки (месяц по убыванию, команда): база, новая Jira, разница в % от базы.

    Месяцы раньше ``from_month`` не сравниваются: эту историю сервис после переезда не держит.
    """
    keys = sorted((k for k in set(db_hours) | set(dc_hours) if k[1] >= from_month), key=lambda k: k[0])
    keys.sort(key=lambda k: k[1], reverse=True)
    rows: list[dict[str, Any]] = []
    for team, month in keys:
        base = round(db_hours.get((team, month), 0.0), 2)
        other = round(dc_hours.get((team, month), 0.0), 2)
        diff = _diff_pct(base, other)
        rows.append({
            "team": team, "month": month, "db_hours": base, "dc_hours": other,
            "diff_pct": diff, "flagged": abs(diff) > threshold_pct,
        })
    return rows


def post_check(db: Session, report: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Сверка после: часы базы сейчас против часов новой Jira из отчёта пробного прогона."""
    rows_now = load_db_worklogs(db)
    hours = report.get("hours") or {}
    dc_before = {(r["team"], r["month"]): float(r["dc_hours"]) for r in hours.get("rows", [])}
    return {
        "checked_at": now.replace(microsecond=0).isoformat() + "Z",
        "db_worklogs": len(rows_now),
        "dc_worklogs": int(hours.get("dc_worklogs", 0)),
        "rows": compare_hours(to_hours(db_seconds(rows_now)), dc_before, from_month=hours_from_month(report)),
    }
