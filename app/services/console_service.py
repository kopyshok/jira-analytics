"""Консоль Jira и Confluence: запросы на чтение от имени сервера.

Машина разработки Jira не видит, сервер видит. Администратор вставляет строки-
запросы, сервер отправляет их своим токеном и отдаёт ответы одним текстом.
Только GET, только на адрес системы из настроек и только пути `rest/…` —
иначе токен ушёл бы на чужой сервер.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

MAX_REQUESTS = 50
REQUEST_TIMEOUT_S = 60.0
# Прокси на сервере рвёт запрос через 120 с — оставляем запас.
RUN_BUDGET_S = 100.0
MAX_RESPONSE_CHARS = 5 * 1024 * 1024
MAX_OUTPUT_CHARS = 10 * 1024 * 1024
# Сырой ответ больше этого не читаем: разбор и скрытие имён съели бы память.
MAX_RAW_BYTES = 20 * 1024 * 1024
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
    base, token = (base or "").strip(), (token or "").strip()
    if not (base and token):
        raise ConsoleError(f"Не указаны адрес или токен — заполните раздел настроек {section}")
    # Пробел или не-ASCII в токене ломает заголовок, а текст ошибки выдал бы токен.
    if not token.isascii() or any(c.isspace() for c in token):
        raise ConsoleError(f"Токен содержит недопустимые символы — проверьте раздел настроек {section}")
    return base.rstrip("/"), token


def _safe(text: str, token: str) -> str:
    """Убрать токен из текста ошибки."""
    return text.replace(token, "***") if token else text


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


@dataclass
class RunResult:
    output: str
    request_count: int
    error_count: int
    rejected_count: int
    duration_ms: int


def _secs(seconds: float, digits: int = 2) -> str:
    return f"{seconds:.{digits}f}".replace(".", ",")


def _mb(chars: int) -> str:
    return f"{chars / 1024 / 1024:.1f}".replace(".", ",")


class _TooBig(Exception):
    """Ответ больше MAX_RAW_BYTES — не читаем дальше."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[int, Optional[str], str]:
    """Статус, адрес перенаправления и текст ответа; больше MAX_RAW_BYTES — _TooBig."""
    async with client.stream("GET", url) as resp:
        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > MAX_RAW_BYTES:
                raise _TooBig(resp.status_code)
            chunks.append(chunk)
        text = b"".join(chunks).decode(resp.charset_encoding or "utf-8", errors="replace")
        return resp.status_code, resp.headers.get("location"), text


def _body(status: int, location: Optional[str], text: str, masker: Optional[Masker]) -> str:
    """Тело ответа: JSON с отступами, иначе текст; длинное — обрезать."""
    if 300 <= status < 400:
        return f"Перенаправление: {location or '—'}"
    try:
        data = json.loads(text)
    except ValueError:
        pass
    else:
        if masker:
            data = masker.walk(data)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > MAX_RESPONSE_CHARS:
        text = (
            text[:MAX_RESPONSE_CHARS]
            + f"\n… обрезано, показано {_mb(MAX_RESPONSE_CHARS)} МБ из {_mb(len(text))} МБ"
        )
    return text


async def execute(
    lines: list[Line],
    target: str,
    mask: bool,
    base: str,
    token: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Выполнить запросы по очереди и собрать один текст.

    Ошибка одного запроса пакет не останавливает. Когда вышло общее время или
    результат стал слишком большим, оставшиеся строки помечаются невыполненными.
    """
    masker = Masker() if mask else None
    start = clock()
    # (заголовок, тело или None, пустая строка после блока)
    blocks: list[tuple[list[str], Optional[str], bool]] = []
    count = errors = rejected = skipped = total = 0
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=False, transport=transport,
    ) as client:
        for line in lines:
            if line.comment:
                blocks.append(([line.text], None, False))
                continue
            count += 1
            head = [f"### {count}. {line.text}"]
            if line.reject or not line.url:
                rejected += 1
                blocks.append((head + [f"→ отклонено: {line.reject}"], None, True))
                continue
            left = RUN_BUDGET_S - (clock() - start)
            if left <= 0:
                skipped += 1
                blocks.append((head + ["→ не выполнено — вышло общее время, запустите эти строки отдельно"], None, True))
                continue
            if total >= MAX_OUTPUT_CHARS:
                skipped += 1
                blocks.append((head + ["→ не выполнено — результат слишком большой"], None, True))
                continue
            t0 = clock()
            try:
                status, location, raw = await asyncio.wait_for(
                    _fetch(client, line.url), timeout=min(REQUEST_TIMEOUT_S, left),
                )
            except _TooBig as e:
                errors += 1
                blocks.append((head + [
                    f"→ {e.status} · ответ больше {_mb(MAX_RAW_BYTES)} МБ — "
                    "сузьте запрос (меньше maxResults, без expand)"
                ], None, True))
                continue
            except (httpx.TimeoutException, asyncio.TimeoutError):
                errors += 1
                blocks.append((head + [f"→ нет ответа за {_secs(clock() - t0)} с"], None, True))
                continue
            except (httpx.HTTPError, httpx.InvalidURL) as e:
                errors += 1
                blocks.append((head + [f"→ нет ответа: {type(e).__name__}: {_safe(str(e), token)}"], None, True))
                continue
            if status >= 400:
                errors += 1
            body = _body(status, location, raw, masker)
            if total + len(body) > MAX_OUTPUT_CHARS:
                body = (
                    body[: max(MAX_OUTPUT_CHARS - total, 0)]
                    + "\n… обрезано: достигнут общий предел результата"
                )
            total += len(body)
            blocks.append((head + [f"→ {status} · {_secs(clock() - t0)} с"], body, True))

    elapsed = clock() - start
    parts: list[str] = []
    for head, shown, gap in blocks:
        parts.extend(head)
        if shown is not None:
            parts.append(shown)
        if gap:
            parts.append("")
    # Имена из поздних ответов скрываем и в ранних, и в строках запросов — поэтому в самом конце.
    text = "\n".join(parts)
    if masker:
        text = masker.scrub(text)
    banner = [
        f"=== {TARGET_TITLES[target]}{' · имена и почта скрыты' if mask else ''} ===",
        f"Запросов: {count}, с ошибкой: {errors}, отклонено: {rejected}, "
        f"не выполнено: {skipped}, время: {_secs(elapsed, 1)} с",
        "",
    ]
    return RunResult(
        output="\n".join(banner + [text]).rstrip() + "\n",
        request_count=count,
        error_count=errors,
        rejected_count=rejected,
        duration_ms=int(elapsed * 1000),
    )
