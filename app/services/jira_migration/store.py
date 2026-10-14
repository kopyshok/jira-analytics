"""Хранение отчёта пробного прогона и решений администратора.

Отчёт — одна строка: новый прогон вытесняет прежние. Решения — отдельная
таблица, переживают повторные прогоны.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

KIND_FIELD = "field"
KIND_ISSUE = "issue"
KIND_PERSON = "person"
KINDS = (KIND_FIELD, KIND_ISSUE, KIND_PERSON)

ISSUE_DELETE = "delete"
ISSUE_KEEP = "keep"
PERSON_BIND = "bind"
PERSON_UNBIND = "unbind"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(raw: Optional[str]) -> Optional[Any]:
    return json.loads(raw) if raw else None


def latest_report(db: Session) -> Optional[JiraMigrationReport]:
    """Последний отчёт. Соответствия (мегабайты) подгружаются только по запросу.

    Колонка ``maps_json`` отложена: её читает отдельный запрос при первом
    обращении (``report_maps``), пока строка привязана к открытой сессии.
    """
    return (
        db.query(JiraMigrationReport)
        .options(defer(JiraMigrationReport.maps_json))
        .order_by(JiraMigrationReport.started_at.desc())
        .first()
    )


def report_data(row: Optional[JiraMigrationReport]) -> dict:
    if row is None:
        return {}
    return _load(row.report_json) or {}


def report_maps(row: Optional[JiraMigrationReport]) -> dict:
    if row is None:
        return {}
    return _load(row.maps_json) or {}


def apply_summary(row: Optional[JiraMigrationReport]) -> Optional[dict]:
    return _load(row.apply_summary_json) if row is not None else None


def post_check_data(row: Optional[JiraMigrationReport]) -> Optional[dict]:
    return _load(row.post_check_json) if row is not None else None


def start_report(db: Session, now: datetime) -> str:
    """Начать прогон: прежние отчёты удаляются (решения не трогаются). Коммитит."""
    db.query(JiraMigrationReport).delete(synchronize_session=False)
    row = JiraMigrationReport(status=STATUS_RUNNING, started_at=now)
    db.add(row)
    db.flush()
    report_id = row.id
    db.commit()
    return report_id


def finish_report(db: Session, report_id: str, report: dict, maps: dict, now: datetime) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is None:
        return
    row.status = STATUS_DONE
    row.finished_at = now
    row.error = None
    row.report_json = _dump(report)
    row.maps_json = _dump(maps)
    db.commit()


def fail_report(
    db: Session,
    report_id: Optional[str],
    error: str,
    now: datetime,
    report: Optional[dict] = None,
) -> None:
    if report_id is None:
        return
    row = db.get(JiraMigrationReport, report_id)
    if row is None:
        return
    row.status = STATUS_FAILED
    row.finished_at = now
    row.error = error
    if report is not None:
        row.report_json = _dump(report)
    db.commit()


def set_sync_run(db: Session, report_id: str, run_id: str) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is not None:
        row.sync_run_id = run_id
        db.commit()


def save_post_check(db: Session, report_id: str, data: dict) -> None:
    row = db.get(JiraMigrationReport, report_id)
    if row is not None:
        row.post_check_json = _dump(data)
        db.commit()


def get_decisions(db: Session, kind: str) -> dict[str, dict]:
    rows = db.query(JiraMigrationDecision).filter(JiraMigrationDecision.kind == kind).all()
    return {r.item_key: json.loads(r.decision_json) for r in rows}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_decision(kind: str, decision: Optional[Mapping[str, Any]]) -> None:
    """Проверить форму решения; ``None`` — снять решение. Ошибка — ``ValueError``."""
    if kind not in KINDS:
        raise ValueError("Неизвестный вид решения")
    if decision is None:
        return
    keys = set(decision)
    if kind == KIND_FIELD:
        value = decision.get("dc_field_id")
        if keys != {"dc_field_id"} or (value is not None and not _is_text(value)):
            raise ValueError("Решение по полю: выберите поле новой Jira или «Не использовать»")
        return
    if kind == KIND_ISSUE:
        if keys != {"action"} or decision.get("action") not in (ISSUE_DELETE, ISSUE_KEEP):
            raise ValueError("Решение по задаче: «Удалить» или «Оставить»")
        return
    action = decision.get("action")
    if action == PERSON_UNBIND and keys == {"action"}:
        return
    if (
        action == PERSON_BIND
        and keys <= {"action", "key", "name", "display_name"}
        and _is_text(decision.get("key"))
        and _is_text(decision.get("display_name"))
        and (decision.get("name") is None or isinstance(decision.get("name"), str))
    ):
        return
    raise ValueError("Решение по сотруднику: выберите пользователя новой Jira или «Без привязки»")


def _find_decision(db: Session, kind: str, item_key: str) -> Optional[JiraMigrationDecision]:
    return (
        db.query(JiraMigrationDecision)
        .filter(JiraMigrationDecision.kind == kind, JiraMigrationDecision.item_key == item_key)
        .first()
    )


def set_decision(
    db: Session,
    kind: str,
    item_key: str,
    decision: Optional[Mapping[str, Any]],
    decided_by: Optional[str],
) -> None:
    """Записать или снять (``None``) решение. Коммитит.

    Если другой администратор успел записать решение по тому же пункту между
    проверкой и записью, повторяем один раз — уже как обновление его строки.
    """
    validate_decision(kind, decision)
    try:
        _write_decision(db, kind, item_key, decision, decided_by)
    except IntegrityError:
        db.rollback()
        _write_decision(db, kind, item_key, decision, decided_by)


def _write_decision(
    db: Session,
    kind: str,
    item_key: str,
    decision: Optional[Mapping[str, Any]],
    decided_by: Optional[str],
) -> None:
    row = _find_decision(db, kind, item_key)
    if decision is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(JiraMigrationDecision(
            kind=kind, item_key=item_key, decision_json=_dump(dict(decision)), decided_by=decided_by,
        ))
    else:
        row.decision_json = _dump(dict(decision))
        row.decided_by = decided_by
    db.commit()
