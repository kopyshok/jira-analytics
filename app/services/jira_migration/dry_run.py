"""Пробный прогон переезда: только чтение новой Jira, в базу пишется лишь отчёт.

Единственная запись помимо отчёта — снимок облачных настроек полей при
первом прогоне (``fields.ensure_field_snapshot``).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors.jira_client import (
    JiraAuthError,
    JiraClientError,
    JiraNetworkError,
    JiraRateLimitError,
    JiraServerError,
)
from app.models import Issue, Project, Worklog
from app.services.jira_migration import store
from app.services.jira_migration.fields import (
    build_field_rows,
    ensure_field_snapshot,
    field_ids_of,
    resolve_fields,
)
from app.services.jira_migration.fingerprints import detect_offset, scan_dc_worklogs
from app.services.jira_migration.hours import (
    compare_hours,
    db_seconds,
    dc_seconds,
    hours_from_month,
    load_db_worklogs,
    month_of_minute,
    to_hours,
)
from app.services.jira_migration.issues import scan_issue_ids
from app.services.jira_migration.people import build_people_rows, vote_people
from app.services.jira_migration.probe import essential_failures, run_probe

logger = logging.getLogger(__name__)

ProgressFn = Callable[..., None]
REPORT_VERSION = 1

STEP_CHECK = "Проверка новой Jira"
STEP_ISSUES = "Задачи"
STEP_DB_WORKLOGS = "Списания базы"
STEP_DC_WORKLOGS = "Списания новой Jira"
STEP_PEOPLE = "Сотрудники"

# Сбои чтения новой Jira. Ошибки базы и кода идут наружу как есть.
_JIRA_READ_ERRORS = (JiraClientError, httpx.HTTPError, ValidationError)


class DryRunAborted(Exception):
    """Отчёт строить не из чего: новая Jira не отвечает на обязательные запросы
    или чтение прервалось посреди прогона (неполная выдача не должна стать отчётом).

    ``report`` — то, что успели проверить (проверка возможностей), для страницы.
    """

    def __init__(self, message: str, report: dict) -> None:
        super().__init__(message)
        self.report = report


@dataclass
class DryRunResult:
    report: dict   # сводка для страницы
    maps: dict     # для применения: {"projects": {ключ: id}, "issues": {ключ: id}}


def _silent(step: str, counters: Optional[dict] = None) -> None:
    return None


def _dc_fields(raw: list[dict]) -> list[dict[str, Any]]:
    return [
        {"id": str(f["id"]), "name": str(f.get("name") or f["id"]), "custom": bool(f.get("custom"))}
        for f in raw if f.get("id")
    ]


async def _try_read(call: Callable[[], Awaitable[Any]]) -> Optional[Any]:
    """Ответ Jira или ``None``: сбой попадёт в проверку возможностей."""
    try:
        return await call()
    except Exception:  # noqa: BLE001 — проверка возможностей покажет причину
        return None


def _probe_sample(db: Session, dc_project_keys: set[str]) -> tuple[Optional[str], Optional[str]]:
    """(проект, задача) для проверки — из проекта, который есть в новой Jira.

    Поиск по проекту, которого в новой Jira нет, она отвергает — и
    обязательная проверка поиска упала бы зря. Таких проектов нет — задача
    не выбирается, проверки по задаче пропускаются.
    """
    keys = sorted({key for (key,) in db.query(Project.key).all()} & dc_project_keys)
    if not keys:
        return None, None
    row = (
        db.query(Issue.key, Project.key)
        .join(Project, Project.id == Issue.project_id)
        .filter(Project.key.in_(keys))
        .order_by(Project.key, Issue.key)
        .first()
    )
    return (row[1], row[0]) if row else (keys[0], None)


def _reason(exc: Exception) -> str:
    """Причина остановки на языке администратора: технический текст клиента — только в журнал."""
    if isinstance(exc, JiraAuthError):
        return "нет доступа к новой Jira — проверьте токен и его права"
    if isinstance(exc, JiraRateLimitError):
        return "новая Jira ограничила частоту запросов — запустите прогон позже"
    if isinstance(exc, JiraNetworkError):
        return "нет связи с новой Jira"
    if isinstance(exc, JiraServerError):
        return "сбой на стороне новой Jira — запустите прогон позже"
    text = str(exc).strip()[:300]
    return f"чтение новой Jira прервалось ({text})" if text else "чтение новой Jira прервалось"


@contextmanager
def _abort_on_failure(step: str, partial: dict) -> Iterator[None]:
    """Сбой чтения новой Jira посреди шага — ``DryRunAborted`` с причиной по-русски."""
    try:
        yield
    except _JIRA_READ_ERRORS as exc:
        logger.warning("Пробный прогон переезда остановлен на шаге «%s»", step, exc_info=True)
        raise DryRunAborted(f"Пробный прогон остановлен на шаге «{step}»: {_reason(exc)}", partial) from exc


async def build_report(
    db: Session,
    jira: Any,
    *,
    now: datetime,
    progress: ProgressFn = _silent,
) -> DryRunResult:
    """Собрать отчёт пробного прогона.

    Обязательный запрос не работает или чтение новой Jira прервалось на
    любом шаге (нет доступа, лимит запросов, нет связи, сбой сервера,
    оборванная выдача) — ``DryRunAborted``. Перед долгими чтениями Jira
    транзакция базы фиксируется (в ней только чтение): открытая на десятки
    минут транзакция держит соединение и мешает Postgres.
    """
    progress(STEP_CHECK, None)
    snapshot = ensure_field_snapshot(db)
    db.commit()
    raw_fields = await _try_read(jira.get_fields)
    raw_projects = await _try_read(jira.get_projects)
    dc_fields = _dc_fields(raw_fields or [])
    field_rows = build_field_rows(snapshot, dc_fields)
    field_map = resolve_fields(field_rows, store.get_decisions(db, store.KIND_FIELD), dc_fields).mapping
    team_ids = field_ids_of(snapshot.get("jira_team_field_id"))
    team_field_id = field_map.get(team_ids[0]) if team_ids else None
    sample_project, sample_issue_key = _probe_sample(db, {p.key for p in raw_projects or []})
    db.commit()
    probe = await run_probe(
        db, jira,
        sample_project=sample_project,
        sample_issue_key=sample_issue_key,
        team_field_id=team_field_id,
        now=now,
    )
    probe_rows = [item.to_dict() for item in probe]
    partial = {"version": REPORT_VERSION, "generated_at": now.isoformat(), "probe": probe_rows}
    failed = essential_failures(probe)
    if failed:
        raise DryRunAborted(
            "Новая Jira не отвечает на обязательные запросы: " + ", ".join(item.title for item in failed),
            partial,
        )
    if raw_fields is None:
        # Первый запрос полей сорвался, проверка прошла: без полей не было бы предложений.
        with _abort_on_failure(STEP_CHECK, partial):
            raw_fields = await jira.get_fields()
        dc_fields = _dc_fields(raw_fields)
        field_rows = build_field_rows(snapshot, dc_fields)
    if raw_projects is None:
        with _abort_on_failure(STEP_CHECK, partial):
            raw_projects = await jira.get_projects()
    dc_projects = {p.key: str(p.id) for p in raw_projects}

    progress(STEP_ISSUES, {"issues_read": 0})
    with _abort_on_failure(STEP_ISSUES, partial):
        scan = await scan_issue_ids(
            db, jira, dc_projects, on_progress=lambda n: progress(STEP_ISSUES, {"issues_read": n}),
        )

    progress(STEP_DB_WORKLOGS, None)
    db_rows = load_db_worklogs(db)
    team_by_key: dict[str, Optional[str]] = {key: team for key, team in db.query(Issue.key, Issue.team).all()}
    worklog_counts: dict[str, int] = {}
    # Секунды на задачах, которые получат id новой Jira: применение удалит эти списания,
    # синк вернёт их к карточке сотрудника, только если он привязан к учётке новой Jira.
    rebound_seconds: dict[str, int] = {}
    for row in db_rows:
        worklog_counts[row.employee_id] = worklog_counts.get(row.employee_id, 0) + 1
        if row.key in scan.key_to_id:
            rebound_seconds[row.employee_id] = rebound_seconds.get(row.employee_id, 0) + row.seconds
    db.commit()

    progress(STEP_DC_WORKLOGS, {"worklogs_read": 0})
    id_to_key = {issue_id: key for key, issue_id in scan.key_to_id.items()}
    with _abort_on_failure(STEP_DC_WORKLOGS, partial):
        dc = await scan_dc_worklogs(
            jira, id_to_key, on_progress=lambda n: progress(STEP_DC_WORKLOGS, {"worklogs_read": n}),
        )
    offset = detect_offset(db_rows, dc.rows)
    votes = vote_people(db_rows, dc.rows, offset.hours)

    progress(STEP_PEOPLE, {"people_checked": 0})
    with _abort_on_failure(STEP_PEOPLE, partial):
        people = await build_people_rows(
            db, jira, votes, dc.authors, worklog_counts,
            on_progress=lambda n: progress(STEP_PEOPLE, {"people_checked": n}),
        )
    for person in people:
        # Без привязки эти часы уйдут к новой карточке, которую синк заведёт по учётке новой Jira.
        person["hours_at_risk"] = round(rebound_seconds.get(person["employee_id"], 0) / 3600, 2)

    min_started = db.query(func.min(Worklog.started_at)).scalar()
    min_date = min_started.date().isoformat() if min_started else None
    from_month = hours_from_month({"db_worklogs_min_date": min_date})
    shift = offset.hours * 60
    report = {
        "version": REPORT_VERSION,
        "generated_at": now.isoformat(),
        "probe": probe_rows,
        "fields": field_rows,
        "dc_fields": dc_fields,
        "projects": scan.projects,
        "issues": {
            "db_total": scan.db_total,
            "matched": scan.matched,
            "new_in_dc": scan.new_in_dc,
            "missing": scan.missing,
            # Проекты базы, которых нет в новой Jira: их задачи не сверялись и остаются как есть.
            "project_not_found": scan.project_not_found,
        },
        "offset_hours": offset.hours,
        "offset_matches": offset.counts[offset.hours],
        "offset_sample": offset.sample,
        # Сдвиг не московский (+3 ч): сверка после переезда может расходиться по месяцам.
        "offset_unexpected": offset.unexpected,
        "people": people,
        "hours": {
            "rows": compare_hours(
                to_hours(db_seconds(db_rows)), to_hours(dc_seconds(dc.rows, team_by_key, offset.hours)),
                from_month=from_month,
            ),
            # Сверяется история с этого месяца — её сервис загрузит после переезда.
            "from_month": from_month,
            "db_worklogs": sum(1 for r in db_rows if month_of_minute(r.minute) >= from_month),
            "dc_worklogs": sum(1 for r in dc.rows if month_of_minute(r.minute + shift) >= from_month),
            "dc_worklogs_total": dc.total,
        },
        "db_worklogs_min_date": min_date,
    }
    return DryRunResult(report=report, maps={"projects": dc_projects, "issues": scan.key_to_id})
