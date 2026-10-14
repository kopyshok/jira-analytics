"""Сборка JQL из значений базы и пользователя."""

import re
from typing import Optional

_CUSTOM_FIELD_RE = re.compile(r"customfield_(\d+)")


def jql_quote(value: str) -> str:
    """Строковый литерал JQL в двойных кавычках.

    Сначала экранируется ``\\``, затем ``"`` — иначе логин или название команды
    с кавычкой ломают запрос (или меняют его смысл).
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def custom_field_number(field_id: str) -> Optional[str]:
    """Номер кастомного поля: ``customfield_11092`` → ``"11092"``, иначе ``None``."""
    match = _CUSTOM_FIELD_RE.fullmatch(field_id)
    return match.group(1) if match else None


def jql_field_ref(field_id: str) -> str:
    """Ссылка на поле в JQL: ``customfield_11092`` → ``cf[11092]``, прочее — в кавычках."""
    number = custom_field_number(field_id)
    return f"cf[{number}]" if number else jql_quote(field_id)
