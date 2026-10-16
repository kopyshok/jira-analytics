"""Консоль Jira и Confluence: запросы на чтение от имени сервера.

Машина разработки Jira не видит, сервер видит. Администратор вставляет строки-
запросы, сервер отправляет их своим токеном и отдаёт ответы одним текстом.
Только GET, только на адрес системы из настроек и только пути `rest/…` —
иначе токен ушёл бы на чужой сервер.
"""
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

MAX_REQUESTS = 50
TARGET_TITLES = {"jira": "Jira", "confluence": "Confluence"}


class ConsoleError(Exception):
    """Запуск целиком невозможен: нет настроек, нет запросов, их слишком много."""


@dataclass
class Line:
    """Строка ввода: пояснение, проверенный запрос (`url`) или отказ (`reject`)."""

    text: str
    comment: bool = False
    url: Optional[str] = None
    reject: Optional[str] = None


def _setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else None


def credentials(db: Session, target: str) -> tuple[str, str]:
    """Адрес и токен системы. У Jira — запасной вариант из .env, как у синка."""
    if target == "jira":
        env = get_settings()
        base = _setting(db, "jira_base_url") or env.jira_base_url
        token = _setting(db, "jira_api_token") or env.jira_api_token
        section = "«Подключение к Jira»"
    else:
        base = _setting(db, "confluence_base_url")
        token = _setting(db, "confluence_api_token")
        section = "«Подключение к Confluence»"
    if not (base and token):
        raise ConsoleError(f"Не указаны адрес или токен — заполните раздел настроек {section}")
    return base.rstrip("/"), token


def _check(s: str, base: str, title: str) -> Line:
    """Привести строку к адресу внутри системы или отклонить с причиной."""
    b = urlsplit(base)
    base_path = b.path.rstrip("/")
    if s.startswith("//") or "\\" in s:
        return Line(s, reject=f"ссылка ведёт не на {title}")
    if "://" in s.split("?", 1)[0]:
        u = urlsplit(s)
        same = (u.scheme.lower(), u.netloc.lower()) == (b.scheme.lower(), b.netloc.lower())
        if not same or not u.path.startswith(base_path + "/"):
            return Line(s, reject=f"ссылка ведёт не на {title}")
        rel, query = u.path[len(base_path) + 1:], u.query
    else:
        rel, _, query = s.lstrip("/").partition("?")
    if not rel.startswith("rest/"):
        return Line(s, reject="путь после адреса должен начинаться с rest/")
    if ".." in rel or "%2e" in rel.lower():
        return Line(s, reject="в пути нельзя «..»")
    url = f"{base}/{rel}" + (f"?{query}" if query else "")
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return Line(s, reject="неверная ссылка")
    # ponytail: страховка поверх разбора выше — хост итогового адреса = хост системы.
    if (parsed.scheme, parsed.host) != (b.scheme.lower(), b.hostname or ""):
        return Line(s, reject=f"ссылка ведёт не на {title}")
    return Line(s, url=url)


def parse_lines(text: str, base: str, target: str) -> list[Line]:
    """Разобрать ввод: `#` — пояснение, пустые строки пропускаются."""
    title = TARGET_TITLES[target]
    lines: list[Line] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        lines.append(Line(s, comment=True) if s.startswith("#") else _check(s, base, title))
    count = sum(1 for line in lines if not line.comment)
    if count == 0:
        raise ConsoleError("Нет ни одного запроса")
    if count > MAX_REQUESTS:
        raise ConsoleError(f"Не больше {MAX_REQUESTS} запросов за один запуск, сейчас {count}")
    return lines
