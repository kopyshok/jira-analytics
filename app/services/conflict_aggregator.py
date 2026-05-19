"""Аггрегация конфликтов: дедупликация по диапазону + шаблонные сообщения.

OVERLOAD-конфликты приходят по одному на день; aggregate_conflicts склеивает
последовательные дни (gap ≤ 1) в единый диапазон. Сообщения генерятся по
шаблону с подстановкой имени сотрудника и метки инициативы (Jira-ключ + title).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session


RU_MONTHS = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _format_date_range(start: Optional[date], end: Optional[date]) -> str:
    if start is None and end is None:
        return ""
    if end is None or start == end:
        return f"{start.day} {RU_MONTHS[start.month]}" if start else ""
    if start is None:
        return f"{end.day} {RU_MONTHS[end.month]}"
    if start.month == end.month:
        return f"{start.day}–{end.day} {RU_MONTHS[start.month]}"
    return (
        f"{start.day} {RU_MONTHS[start.month]} – "
        f"{end.day} {RU_MONTHS[end.month]}"
    )


def aggregate_conflicts(
    raw: List[Dict[str, Any]],
    db_session: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """Склеить последовательные daily-конфликты в диапазоны и проштамповать сообщения.

    Группировка по (type, employee_id, assignment_id). В каждой группе строки
    сортируются по window_start и сливаются если разрыв ≤ 1 день.
    """
    groups: Dict[Tuple[Any, Any, Any], List[dict]] = defaultdict(list)
    for r in raw:
        key = (r.get("type"), r.get("employee_id"), r.get("assignment_id"))
        groups[key].append(r)

    # Bulk-load имён сотрудников и меток инициатив одним запросом каждый —
    # вместо N+1 db.get() в _build_message.
    emp_names = _bulk_employee_names(
        {r.get("employee_id") for r in raw if r.get("employee_id")},
        db_session,
    )
    item_labels = _bulk_item_labels(
        {r.get("backlog_item_id") for r in raw if r.get("backlog_item_id")},
        db_session,
    )

    out: List[dict] = []
    for items in groups.values():
        items.sort(key=lambda x: _to_date(x.get("window_start")) or date.min)
        merged: List[dict] = []
        for it in items:
            it_start = _to_date(it.get("window_start"))
            it_end = _to_date(it.get("window_end")) or it_start
            if merged:
                prev = merged[-1]
                prev_end = _to_date(prev.get("window_end")) or _to_date(
                    prev.get("window_start")
                )
                if prev_end and it_start and (it_start - prev_end).days <= 1:
                    new_end = max(prev_end, it_end) if it_end else prev_end
                    prev["window_end"] = new_end
                    prev["metric_value"] = max(
                        float(prev.get("metric_value") or 0.0),
                        float(it.get("metric_value") or 0.0),
                    )
                    # Уникальный detection_key для смежного диапазона.
                    type_ = prev.get("type", "")
                    aid = prev.get("assignment_id", "")
                    prev["detection_key"] = (
                        f"{type_}:{aid}:{prev.get('window_start')}-{new_end}"
                    )
                    continue
            copy = {**it, "window_start": it_start, "window_end": it_end}
            merged.append(copy)
        for m in merged:
            m["message"] = _build_message(m, emp_names, item_labels)
            out.append(m)
    return out


def _build_message(
    c: Dict[str, Any],
    emp_names: Dict[str, str],
    item_labels: Dict[str, str],
) -> str:
    t = c.get("type", "")
    rng = _format_date_range(_to_date(c.get("window_start")), _to_date(c.get("window_end")))
    emp_id = c.get("employee_id")
    emp_name = emp_names.get(emp_id, emp_id or "") if emp_id else ""
    item_id = c.get("backlog_item_id")
    item_label = item_labels.get(item_id, "") if item_id else ""
    if t.startswith("OVERLOAD_"):
        pct = int(round(float(c.get("metric_value") or 0)))
        rng_part = f" в период {rng}" if rng else ""
        who = emp_name or "сотрудник"
        return f"{who} перегружен {pct}%{rng_part}".strip()
    if t == "QUARTER_OVERFLOW":
        return f"{item_label} не вмещается в квартал".strip() if item_label else (
            c.get("message") or t
        )
    if t == "NO_ANALYST":
        return "В команде нет аналитиков — расписание фазы анализа невозможно"
    if t == "NO_DEV":
        return "В команде нет разработчиков — расписание фазы разработки невозможно"
    if t == "LATE_START":
        return f"{item_label} стартует с отставанием".strip() if item_label else (
            c.get("message") or t
        )
    if t == "LEVELING_DELAY":
        # Бэкенд формирует сообщение с именами сотрудников и названием задачи.
        return c.get("message") or t
    if t == "LEVELING_REASSIGN":
        return c.get("message") or t
    if t == "SPLIT_REQUIRED":
        return (
            f"{item_label} разбита на части — заблокированный период".strip()
            if item_label
            else (c.get("message") or t)
        )
    return c.get("message", t) or t


def _bulk_employee_names(
    emp_ids: set[str], db: Optional[Session]
) -> Dict[str, str]:
    """Загрузить display_name для всех нужных сотрудников одним запросом."""
    if not emp_ids or db is None:
        return {}
    from sqlalchemy import select

    from app.models import Employee

    rows = db.execute(
        select(Employee.id, Employee.display_name).where(Employee.id.in_(emp_ids))
    ).all()
    return {r[0]: (r[1] or r[0]) for r in rows}


def _bulk_item_labels(
    item_ids: set[str], db: Optional[Session]
) -> Dict[str, str]:
    """Загрузить «key title» для backlog items одним запросом."""
    if not item_ids or db is None:
        return {}
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.models import BacklogItem

    rows = (
        db.execute(
            select(BacklogItem)
            .options(joinedload(BacklogItem.issue))
            .where(BacklogItem.id.in_(item_ids))
        )
        .scalars()
        .all()
    )
    out: Dict[str, str] = {}
    for it in rows:
        key = getattr(it.issue, "key", "") if it.issue is not None else ""
        title = it.title or ""
        out[it.id] = f"{key} {title}".strip()
    return out
