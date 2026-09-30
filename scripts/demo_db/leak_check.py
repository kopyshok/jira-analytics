"""Проверка демо-базы на утечки: ищет исходные чувствительные строки во всех колонках всех таблиц.

Сравнение без учёта регистра, «ё» = «е», пробелы схлопнуты; перед поиском раскрываются
\\uXXXX-экранирование (JSON) и %-кодирование (ссылки). ФИО, e-mail, команды и т. п. ищутся
подстрокой, фамилии — отдельным словом во всех падежных формах. Плюс шаблоны: ключи задач
настоящих проектов, e-mail не на example.com, ссылки на любые хосты кроме демо-адресов,
IP-адреса. Отдельно — точное совпадение значения с исходным свободным текстом (названия
задач, описания, комментарии): сверка по хэшам, не зависит от словаря замен.
Двоичные значения декодируются (utf-8, ошибки пропускаются) и проверяются так же.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import TYPE_CHECKING, Iterable, Optional
from urllib.parse import unquote

if TYPE_CHECKING:
    from .anonymize import Sensitive

ALLOWED_EMAIL_DOMAIN = "example.com"
ALLOWED_URL_HOSTS = frozenset({"example.com", "jira.example.com", "localhost", "127.0.0.1"})
ALLOWED_IPS = frozenset({"127.0.0.1", "0.0.0.0"})
MAX_FINDINGS = 10_000
# Исходный свободный текст короче этого не сверяется точным совпадением: короткие строки
# («Готово», «Тестирование») встречаются и в справочниках, это не утечка.
MIN_EXACT_LEN = 15

_WS_RE = re.compile(r"\s+")
_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@((?:[a-z0-9\-]+\.)+[a-z]{2,})")
# Хост ссылки (после «схема://» и необязательного «логин@»).
_URL_RE = re.compile(r"(?<![a-z0-9+.\-])[a-z][a-z0-9+.\-]*://(?:[^/\s\"'<>\\@]*@)?(\[[^\]/]*\]|[^/\s\"'<>\\?#:)\]]+)")
_IP_RE = re.compile(r"(?<!\d)(?<!\d\.)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\d)(?!\.\d)")
_SEP = "\x00"  # не пробельный символ: склеенные значения строки не образуют ложных совпадений


def norm(text: str) -> str:
    """Нормализованная форма для сравнения: нижний регистр, «ё» → «е», одиночные пробелы."""
    return _WS_RE.sub(" ", text).strip().lower().replace("ё", "е")


def exact_key(text: str) -> Optional[bytes]:
    """Хэш нормализованного текста для точной сверки (casefold, «ё» → «е», одиночные пробелы).

    None — текст короче MIN_EXACT_LEN. Хэш вместо строки: исходных описаний сотни тысяч.
    """
    normalized = _WS_RE.sub(" ", text).strip().casefold().replace("ё", "е")
    if len(normalized) < MIN_EXACT_LEN:
        return None
    return hashlib.blake2b(normalized.encode("utf-8"), digest_size=16).digest()


def _text(value: object) -> Optional[str]:
    """Строка для проверки: текст как есть, двоичное — декодированным (ошибки пропускаются)."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return value if isinstance(value, str) and value else None


def trie_pattern(words: Iterable[str], *, loose: bool = False) -> Optional[str]:
    """Регэксп-дерево из слов: самое длинное совпадение в позиции, быстрый поиск по тысячам слов.

    loose=True — для поиска в сыром тексте (с re.IGNORECASE): пробел совпадает с любыми
    пробелами, «е» — и с «ё». Слова должны быть уже нормализованы через norm().
    """
    trie: dict = {}
    for word in words:
        if not word:
            continue
        node = trie
        for ch in word:
            node = node.setdefault(ch, {})
        node[""] = {}
    if not trie:
        return None

    def char(ch: str) -> str:
        if loose and ch == " ":
            return r"\s+"
        if loose and ch == "е":
            return "[её]"
        return re.escape(ch)

    def build(node: dict) -> str:
        alts = [char(ch) + build(sub) for ch, sub in sorted(node.items()) if ch]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
        return f"(?:{body})?" if "" in node else body

    return build(trie)


def word_pattern(words: Iterable[str], *, loose: bool = False) -> Optional[str]:
    """Регэксп «любое из слов целиком»: слева и справа не буква (цифры и _ — граница)."""
    body = trie_pattern(words, loose=loose)
    return rf"(?<![^\W\d_])(?:{body})(?![^\W\d_])" if body else None


def _prepare(text: str) -> str:
    if "\\u" in text:
        text = _ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    if "%" in text:
        text = unquote(text)
    text = text.replace("\\/", "/")  # JSON с экранированным «/»
    return _WS_RE.sub(" ", text).lower().replace("ё", "е")


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "AND name <> 'alembic_version' ORDER BY name"
    )
    return [r[0] for r in rows]


def check(conn: sqlite3.Connection, sensitive: "Sensitive") -> list[str]:
    """Находки вида «таблица.колонка (строка N): вид находки»; пустой список — утечек нет.

    Сам найденный текст в находку не попадает: сборщик печатает находки, и исходные
    данные остались бы в выводе и журналах. Строку по номеру смотрят в базе сами.
    """
    pattern = trie_pattern(sensitive.strings)
    tokens = re.compile(pattern) if pattern else None
    pattern = word_pattern(sensitive.words)
    words = re.compile(pattern) if pattern else None
    keys = sorted({k.lower() for k in sensitive.project_keys}, key=len, reverse=True)
    key_re = re.compile(r"\b(?:%s)-\d+" % "|".join(map(re.escape, keys))) if keys else None
    originals = sensitive.originals

    def hit(text: str) -> Optional[str]:
        for rx, kind in ((tokens, "исходная строка"), (words, "фамилия"), (key_re, "ключ задачи")):
            if rx and rx.search(text):
                return kind
        for m in _EMAIL_RE.finditer(text):
            domain = m.group(1)
            if domain != ALLOWED_EMAIL_DOMAIN and not domain.endswith("." + ALLOWED_EMAIL_DOMAIN):
                return "e-mail"
        for m in _URL_RE.finditer(text):
            if m.group(1) not in ALLOWED_URL_HOSTS:
                return "ссылка"
        for m in _IP_RE.finditer(text):
            if all(int(g) <= 255 for g in m.groups()) and m.group(0) not in ALLOWED_IPS:
                return "IP-адрес"
        return None

    def copied(value: str) -> bool:
        return bool(originals) and len(value) >= MIN_EXACT_LEN and exact_key(value) in originals

    findings: list[str] = []
    for table in _tables(conn):
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for rowid, *row in conn.execute(f'SELECT rowid, * FROM "{table}"'):
            strs = [(c, t) for c, t in ((c, _text(v)) for c, v in zip(cols, row)) if t]
            if not strs:
                continue
            for col, value in strs:
                if copied(value):
                    findings.append(f"{table}.{col} (строка {rowid}): совпадает с исходным текстом")
            if hit(_prepare(_SEP.join(v for _, v in strs))):
                for col, value in strs:
                    kind = hit(_prepare(value))
                    if kind is not None:
                        findings.append(f"{table}.{col} (строка {rowid}): {kind}")
            if len(findings) >= MAX_FINDINGS:
                return findings
    return findings
