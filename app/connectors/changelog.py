"""Разбор истории изменений задачи Jira DC (``expand=changelog``).

Формат: ``{"total": N, "histories": [{"created": "...", "items": [{"field":
"status", "from": "<id>", "fromString": "...", "to": "<id>", "toString": "..."}]}]}``.
Время ``created`` приходит со смещением (``+0300``, ``+0000``), поэтому записи
упорядочиваются по разобранному времени, а не по строке; наружу отдаётся
исходная строка.
"""

from datetime import datetime, timezone
from typing import Any, Optional

_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _parse(value: Any) -> Optional[datetime]:
    """Время записи с часовым поясом; ``None`` — не разобрать."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        pass
    try:
        if len(value) > 5 and value[-5] in "+-" and value[-3] != ":":
            value = f"{value[:-2]}:{value[-2:]}"
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sort_key(history: dict) -> datetime:
    return _parse(history.get("created")) or _MIN


def _items(history: dict) -> list[dict]:
    return [i for i in history.get("items") or [] if isinstance(i, dict)]


def _histories(changelog: Any) -> list[dict]:
    if not isinstance(changelog, dict):
        return []
    return [h for h in changelog.get("histories") or [] if isinstance(h, dict)]


def status_only(changelog: Any) -> Any:
    """Копия истории только со сменами статуса — история целиком тяжёлая.

    Каждая запись истории и счётчики (``total``, ``maxResults``) остаются:
    по ним :func:`is_complete` видит, что поиск отдал историю не целиком.
    """
    if not isinstance(changelog, dict):
        return changelog
    trimmed = {k: v for k, v in changelog.items() if k != "histories"}
    trimmed["histories"] = [
        {
            "created": history.get("created"),
            "items": [i for i in _items(history) if i.get("field") == "status"],
        }
        for history in _histories(changelog)
    ]
    return trimmed


def is_complete(changelog: Any) -> bool:
    """В ответе вся история: поиск может отдать только часть записей."""
    if not isinstance(changelog, dict):
        return True
    total = changelog.get("total")
    return not isinstance(total, int) or total <= len(_histories(changelog))


def status_changes(changelog: Any) -> list[tuple[str, str]]:
    """История смен статуса: ``(когда ISO-строкой, новый статус)`` по возрастанию времени."""
    out: list[tuple[datetime, str, str]] = []
    for history in _histories(changelog):
        created = history.get("created")
        if not created:
            continue
        for item in _items(history):
            if item.get("field") == "status" and item.get("toString"):
                out.append((_sort_key(history), created, item["toString"]))
    out.sort(key=lambda change: change[0])
    return [(created, name) for _, created, name in out]


def category_changed_at(
    changelog: Any, status_categories: Optional[dict[str, str]]
) -> Optional[str]:
    """Когда задача последний раз сменила категорию статуса (``new`` /
    ``indeterminate`` / ``done``) — то, что облако отдавало полем
    ``statuscategorychangedate``.

    ``status_categories`` — id статуса → ключ категории из ``GET /status``.
    Статус, которого нет в справочнике, считается сменой категории: лучше
    сдвинуть дату на этот переход, чем потерять его. ``None`` — категория ни
    разу не менялась (тогда берут дату создания задачи).
    """
    categories = status_categories or {}
    last: Optional[str] = None
    for history in sorted(_histories(changelog), key=_sort_key):
        created = history.get("created")
        if _parse(created) is None:
            continue
        for item in _items(history):
            if item.get("field") != "status":
                continue
            before = categories.get(str(item.get("from")))
            after = categories.get(str(item.get("to")))
            if before is None or after is None or before != after:
                last = created
    return last
