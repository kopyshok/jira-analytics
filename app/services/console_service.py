"""Консоль Jira и Confluence: запросы на чтение от имени сервера.

Машина разработки Jira не видит, сервер видит. Администратор вставляет строки-
запросы, сервер отправляет их своим токеном и отдаёт ответы одним текстом.
Только GET, только на адрес системы из настроек и только пути `rest/…` —
иначе токен ушёл бы на чужой сервер.
"""
import re
from dataclasses import dataclass
from typing import Any, Optional
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


_MAIL_KEYS = {"emailAddress", "email"}
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class Masker:
    """Заменяет имена и почту метками «Человек-N» / «почта-N» в рамках запуска.

    Логины, `key` и номера учёток не трогает — по ним сверяем людей.
    """

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self._count = {"Человек": 0, "почта": 0}

    def _label(self, value: str, kind: str) -> str:
        key = value.strip().lower() if kind == "почта" else value.strip()
        if key not in self._labels:
            self._count[kind] += 1
            self._labels[key] = f"{kind}-{self._count[kind]}"
        return self._labels[key]

    def walk(self, data: Any) -> Any:
        """Заменить значения полей имени и почты в разобранном ответе."""
        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for k, v in data.items():
                if k == "displayName" and isinstance(v, str) and v.strip():
                    out[k] = self._label(v, "Человек")
                elif k in _MAIL_KEYS and isinstance(v, str) and v.strip():
                    out[k] = self._label(v, "почта")
                else:
                    out[k] = self.walk(v)
            return out
        if isinstance(data, list):
            return [self.walk(v) for v in data]
        return data

    def scrub(self, text: str) -> str:
        """Заменить в тексте уже встреченные имена и любые адреса почты."""
        names = [k for k in self._labels if " " in k and len(k) >= 5]
        # ponytail: имя из одного слова («Jira», «Admin») в тексте не ищем — заденет обычные слова.
        for name in sorted(names, key=len, reverse=True):
            text = text.replace(name, self._labels[name])
        return _EMAIL_RE.sub(lambda m: self._label(m.group(0), "почта"), text)


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
