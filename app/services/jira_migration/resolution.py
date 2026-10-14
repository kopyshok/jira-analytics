"""Текущее состояние решений по отчёту и препятствия к применению.

Служебные данные задач, которых нет в новой Jira, пересчитываются при
каждом обращении: за сутки до применения у «удаляемой» задачи могли
появиться ручные данные — тогда по ней нужно решение.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Employee, Issue
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import store
from app.services.jira_migration.fields import FieldResolution, remap_plan_sources, resolve_fields
from app.services.jira_migration.issues import classify_missing
from app.services.jira_migration.people import PersonOutcome, finalize_people
from app.services.jira_migration.state import STATE_DONE, get_migration_state

REPORT_MAX_AGE = timedelta(hours=24)

BLOCK_DONE = "Переезд уже выполнен"
BLOCK_JOB = "Идёт другая операция переезда — дождитесь её окончания"
BLOCK_NO_REPORT = "Пробный прогон ещё не запускался"
BLOCK_FAILED = "Последний пробный прогон не завершился успешно — запустите его заново"
BLOCK_STALE = "Пробный прогон старше суток — запустите его заново"
BLOCK_BACKUP = "Отметьте, что свежая копия базы сделана"


@dataclass
class Resolution:
    row: JiraMigrationReport
    report: dict
    fields: FieldResolution
    field_decisions: dict[str, dict]
    people: dict[str, PersonOutcome]
    person_decisions: dict[str, dict]
    deletable: list[str]          # нет в новой Jira, нет служебных данных — удалятся
    with_data: list[dict]         # нет в новой Jira, есть служебные данные — нужны решения
    issue_decisions: dict[str, dict]
    new_employees: int            # сотрудники, которых нет в отчёте
    # Проекты базы, которых нет в новой Jira: их задачи остаются без изменений ([{key, issues}]).
    project_not_found: list[dict]
    # Сдвиг времени облачных списаний не +3 ч — сверка после переезда может расходиться.
    offset_unexpected: bool
    # Задачи, у которых применение сбросит выбранную в споре оценку (её поле «не использовать»).
    choices_dropped: int = 0

    def unresolved_issue_keys(self) -> list[str]:
        return [item["key"] for item in self.with_data if item["key"] not in self.issue_decisions]

    def unresolved_people_ids(self) -> list[str]:
        return [employee_id for employee_id, outcome in self.people.items() if outcome.unresolved]

    def counts(self) -> dict[str, int]:
        return {
            "fields": len(self.fields.unresolved),
            "issues": len(self.unresolved_issue_keys()),
            "people": len(self.unresolved_people_ids()),
        }

    def issues_to_delete(self) -> list[str]:
        with_data_keys = {item["key"] for item in self.with_data}
        decided = {
            key for key, decision in self.issue_decisions.items()
            if key in with_data_keys and decision.get("action") == store.ISSUE_DELETE
        }
        return sorted(set(self.deletable) | decided)


def _count_choices_dropped(
    db: Session, mapping: Mapping[str, Optional[str]], deleted_keys: Collection[str],
) -> int:
    """Сколько оставшихся задач потеряют действующий выбор оценки — как посчитает применение."""
    rows = (
        db.query(Issue.key, Issue.planned_hours_sources, Issue.planned_hours_choice)
        .filter(Issue.planned_hours_choice.isnot(None))
        .all()
    )
    deleted = set(deleted_keys)
    return sum(
        1 for key, sources, choice in rows
        if key not in deleted and remap_plan_sources(sources, choice, mapping)[2]
    )


def resolve(db: Session, row: Optional[JiraMigrationReport] = None) -> Optional[Resolution]:
    """Отчёт + решения + текущие данные. Нет успешного отчёта — ``None``."""
    row = row if row is not None else store.latest_report(db)
    if row is None or row.status != store.STATUS_DONE:
        return None
    report = store.report_data(row)
    issues_report = report.get("issues", {})
    field_decisions = store.get_decisions(db, store.KIND_FIELD)
    person_decisions = store.get_decisions(db, store.KIND_PERSON)
    issue_decisions = store.get_decisions(db, store.KIND_ISSUE)
    people_rows = report.get("people", [])
    deletable, with_data = classify_missing(db, issues_report.get("missing", []))
    in_report = {r["employee_id"] for r in people_rows}
    new_employees = sum(1 for (employee_id,) in db.query(Employee.id).all() if employee_id not in in_report)
    res = Resolution(
        row=row,
        report=report,
        fields=resolve_fields(report.get("fields", []), field_decisions, report.get("dc_fields", [])),
        field_decisions=field_decisions,
        people=finalize_people(people_rows, person_decisions),
        person_decisions=person_decisions,
        deletable=deletable,
        with_data=with_data,
        issue_decisions=issue_decisions,
        new_employees=new_employees,
        project_not_found=issues_report.get("project_not_found", []),
        offset_unexpected=bool(report.get("offset_unexpected", False)),
    )
    res.choices_dropped = _count_choices_dropped(db, res.fields.mapping, res.issues_to_delete())
    return res


def _essential_probe_failures(report: Mapping[str, Any]) -> list[str]:
    return [
        str(item.get("title") or item.get("code"))
        for item in report.get("probe", [])
        if item.get("essential") and not item.get("ok")
    ]


def collect_blockers(
    db: Session,
    *,
    now: datetime,
    backup_confirmed: bool,
    job_running: bool,
    resolution: Optional[Resolution] = None,
) -> list[str]:
    """Почему «Применить» сейчас нельзя. Пустой список — можно."""
    if get_migration_state(db) == STATE_DONE:
        return [BLOCK_DONE]
    blockers: list[str] = []
    if job_running:
        blockers.append(BLOCK_JOB)
    row = resolution.row if resolution is not None else store.latest_report(db)
    if row is None:
        blockers.append(BLOCK_NO_REPORT)
    elif row.status != store.STATUS_DONE:
        # Прогон ещё идёт — об этом уже сказано выше; «идёт» без операции — прерван.
        if not (row.status == store.STATUS_RUNNING and job_running):
            blockers.append(BLOCK_FAILED)
    else:
        if row.finished_at is None or now - row.finished_at > REPORT_MAX_AGE:
            blockers.append(BLOCK_STALE)
        res = resolution if resolution is not None else resolve(db, row)
        if res is not None:
            failed = _essential_probe_failures(res.report)
            if failed:
                blockers.append(
                    f"Новая Jira не отвечала на обязательные запросы ({', '.join(failed)}) — "
                    "запустите прогон заново"
                )
            counts = res.counts()
            if any(counts.values()):
                blockers.append(
                    f"Остались нерешённые пункты: поля — {counts['fields']}, "
                    f"задачи — {counts['issues']}, сотрудники — {counts['people']}"
                )
            if res.new_employees:
                blockers.append(
                    f"После пробного прогона появились новые сотрудники ({res.new_employees}) — "
                    "запустите прогон заново"
                )
    if not backup_confirmed:
        blockers.append(BLOCK_BACKUP)
    return blockers
