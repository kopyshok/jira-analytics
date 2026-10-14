"""Ответ страницы «Переезд на новую Jira»: состояние, отчёт с решениями, препятствия.

Решения пересчитываются по базе (``resolve``) только до применения и не во
время него: после применения сопоставления отчёта (по старым id) к базе уже
не относятся — страница показывает сохранённый итог применения и сверку; во
время применения база меняется — страница показывает только ход операции.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Issue, SyncRun, Worklog
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import runner, store
from app.services.jira_migration.issues import chunks, classify_missing
from app.services.jira_migration.resolution import (
    BLOCK_DONE,
    BLOCK_JOB,
    Resolution,
    collect_blockers,
    resolve,
)
from app.services.jira_migration.state import STATE_DONE, get_migration_state

BACKUP_COMMAND = "docker compose exec postgres-backup /backup.sh"
DELETABLE_SAMPLE = 50
# Запуск полной синхронизации «идёт», а в процессе её нет — оборвана перезапуском сервиса.
SYNC_RUN_INTERRUPTED = "interrupted"
NO_UNRESOLVED = {"fields": 0, "issues": 0, "people": 0}


def iso(dt: Optional[datetime]) -> Optional[str]:
    """Наивное UTC-время базы → ISO с «Z», чтобы браузер не принял его за местное."""
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def job_dict(job: runner.MigrationJob) -> dict[str, Any]:
    return {
        "kind": job.kind,
        "state": job.state,
        "step": job.step,
        "counters": dict(job.counters),
        "error": job.error,
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }


def _static_sections(report: Mapping[str, Any]) -> dict[str, Any]:
    """Части успешного отчёта, которые не зависят от решений и текущей базы."""
    return {
        "dc_fields": report.get("dc_fields", []),
        "projects": report.get("projects", []),
        "hours": report.get("hours", {}),
        "offset_hours": report.get("offset_hours"),
        "offset_matches": report.get("offset_matches"),
        "offset_sample": report.get("offset_sample"),
        "offset_unexpected": bool(report.get("offset_unexpected", False)),
    }


def _hours_on_issues(db: Session, keys: Sequence[str]) -> float:
    """Часы списаний базы на задачах с этими ключами."""
    seconds = 0
    for chunk in chunks(list(keys)):
        seconds += (
            db.query(func.sum(Worklog.time_spent_seconds))
            .join(Issue, Issue.id == Worklog.issue_id)
            .filter(Issue.key.in_(chunk))
            .scalar()
        ) or 0
    return round(seconds / 3600, 2)


def _decision_sections(db: Session, res: Resolution) -> dict[str, Any]:
    """Поля, задачи и сотрудники с решениями — по текущей базе."""
    report = res.report
    to_delete = res.issues_to_delete()
    fields = []
    for row in report.get("fields", []):
        cloud_id = row["cloud_id"]
        final_id = res.fields.mapping.get(cloud_id)
        fields.append({
            "cloud_id": cloud_id,
            "cloud_name": row.get("cloud_name") or cloud_id,
            "labels": row.get("labels", []),
            "suggested_id": row.get("suggested_id"),
            "suggested_name": row.get("suggested_name"),
            "decision": res.field_decisions.get(cloud_id),
            "final_id": final_id,
            "final_name": res.fields.names.get(final_id) if final_id else None,
            "auto_only": bool(row.get("auto_only")),
            "unresolved": cloud_id in res.fields.unresolved,
        })
    people = []
    for row in report.get("people", []):
        outcome = res.people.get(row["employee_id"])
        people.append({
            **row,
            "decision": res.person_decisions.get(row["employee_id"]),
            "final": outcome.to_dict() if outcome else None,
        })
    issues_report = report.get("issues", {})
    issues = {
        "db_total": issues_report.get("db_total", 0),
        "matched": issues_report.get("matched", 0),
        "new_in_dc": issues_report.get("new_in_dc", 0),
        "missing_total": len(issues_report.get("missing", [])),
        "deletable_total": len(res.deletable),
        "deletable_sample": res.deletable[:DELETABLE_SAMPLE],
        # Удалит применение: исчезнувшие без данных сервиса и с решением «удалить» — и часы на них.
        "to_delete_total": len(to_delete),
        "to_delete_hours": _hours_on_issues(db, to_delete),
        "missing_with_data": [
            {**item, "decision": res.issue_decisions.get(item["key"])} for item in res.with_data
        ],
        "project_not_found": res.project_not_found,
    }
    return {
        "fields": fields,
        "issues": issues,
        "people": people,
        "choices_dropped": res.choices_dropped,
    }


def _report_out(
    db: Session, row: JiraMigrationReport, res: Optional[Resolution], building: bool, now: datetime,
) -> dict[str, Any]:
    status, error = row.status, row.error
    if status == store.STATUS_RUNNING and not building:
        status, error = store.STATUS_FAILED, runner.RUN_INTERRUPTED
    data = res.report if res is not None else store.report_data(row)
    out: dict[str, Any] = {
        "status": status,
        "error": error,
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
        "age_hours": round((now - row.finished_at).total_seconds() / 3600, 1) if row.finished_at else None,
        "probe": data.get("probe", []),
    }
    if row.status == store.STATUS_DONE:
        out.update(_static_sections(data))
    if res is not None:
        out.update(_decision_sections(db, res))
    return out


def _sync_run_out(db: Session, run_id: str, job: runner.MigrationJob) -> Optional[dict[str, Any]]:
    """Запуск полной синхронизации после применения.

    Его ведёт только операция переезда, а сервис работает одним процессом:
    «идёт», а полной синхронизации в процессе нет — оборван перезапуском
    (даже если блокировка синка ещё на нём), его можно запустить заново.
    """
    run = db.get(SyncRun, run_id)
    if run is None:
        return None
    status, error = run.status, runner.run_error_text(run.error_text)
    if status == "running" and not (job.state == runner.JOB_RUNNING and job.kind == runner.KIND_FULL_SYNC):
        status, error = SYNC_RUN_INTERRUPTED, runner.SYNC_INTERRUPTED
    return {
        "id": run.id,
        "status": status,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "error": error,
    }


def build_overview(db: Session, *, now: datetime) -> dict[str, Any]:
    state = get_migration_state(db)
    row = store.latest_report(db)
    job = runner.current_job()
    job_running = job.state == runner.JOB_RUNNING
    applying = job_running and job.kind == runner.KIND_APPLY
    applied = state == STATE_DONE or (row is not None and row.applied_at is not None)
    building = runner.report_in_progress(row, job)
    res = resolve(db, row) if row is not None and not applied and not applying else None

    if state == STATE_DONE:
        blockers = [BLOCK_DONE]
    elif row is not None and row.status == store.STATUS_DONE and res is None:
        # Пересчёт пропущен: идёт применение (или отчёт уже применён).
        blockers = [BLOCK_JOB] if job_running else [BLOCK_DONE]
    else:
        blockers = collect_blockers(
            db, now=now, backup_confirmed=True, job_running=job_running or building, resolution=res,
        )

    return {
        "migration_state": state,
        "job": job_dict(job),
        "report": _report_out(db, row, res, building, now) if row is not None else None,
        "unresolved": res.counts() if res is not None else dict(NO_UNRESOLVED),
        "blockers": blockers,
        "backup_command": BACKUP_COMMAND,
        "applied_at": iso(row.applied_at) if row is not None else None,
        "apply_summary": store.apply_summary(row),
        "sync_run": _sync_run_out(db, row.sync_run_id, job) if row is not None and row.sync_run_id else None,
        "post_check": store.post_check_data(row),
    }


def check_decision_target(
    db: Session, kind: str, item_key: str, decision: Optional[Mapping[str, Any]],
) -> None:
    """Решение верной формы и относится к пункту последнего успешного отчёта. Нет — ``ValueError``."""
    store.validate_decision(kind, decision)
    row = store.latest_report(db)
    if row is None or row.status != store.STATUS_DONE:
        raise ValueError("Сначала нужен успешный пробный прогон")
    data = store.report_data(row)
    if kind == store.KIND_FIELD:
        if item_key not in {r["cloud_id"] for r in data.get("fields", [])}:
            raise ValueError("Такого поля нет в отчёте")
        chosen = decision.get("dc_field_id") if decision else None
        if chosen and chosen not in {f["id"] for f in data.get("dc_fields", [])}:
            raise ValueError("Такого поля нет в новой Jira")
    elif kind == store.KIND_ISSUE:
        if item_key not in data.get("issues", {}).get("missing", []):
            raise ValueError("По этой задаче решение не нужно")
        _, with_data = classify_missing(db, [item_key])
        if not with_data:
            raise ValueError("По этой задаче решение не нужно")
    elif kind == store.KIND_PERSON:
        if item_key not in {r["employee_id"] for r in data.get("people", [])}:
            raise ValueError("Такого сотрудника нет в отчёте")
    else:
        raise ValueError("Неизвестный вид решения")
