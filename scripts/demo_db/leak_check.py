"""Проверка демо-базы на утечки: ищет исходные чувствительные строки во всех колонках всех таблиц.

Сравнение без учёта регистра, «ё» = «е», пробелы схлопнуты; перед поиском раскрываются
\\uXXXX-экранирование (JSON) и %-кодирование (ссылки). ФИО, e-mail, команды и т. п. ищутся
подстрокой, фамилии — отдельным словом во всех падежных формах. Плюс шаблоны: ключи задач
настоящих проектов, e-mail не на example.com.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING, Iterable, Optional
from urllib.parse import unquote

if TYPE_CHECKING:
    from .anonymize import Sensitive

ALLOWED_EMAIL_DOMAIN = "example.com"
MAX_FINDINGS = 10_000

_WS_RE = re.compile(r"\s+")
_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@((?:[a-z0-9\-]+\.)+[a-z]{2,})")
_SEP = "\x00"  # не пробельный символ: склеенные значения строки не образуют ложных совпадений


def norm(text: str) -> str:
    """Нормализованная форма для сравнения: нижний регистр, «ё» → «е», одиночные пробелы."""
    return _WS_RE.sub(" ", text).strip().lower().replace("ё", "е")


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
    return _WS_RE.sub(" ", text).lower().replace("ё", "е")


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "AND name <> 'alembic_version' ORDER BY name"
    )
    return [r[0] for r in rows]


def check(conn: sqlite3.Connection, sensitive: "Sensitive") -> list[str]:
    """Находки вида «таблица.колонка: фрагмент»; пустой список — утечек нет."""
    pattern = trie_pattern(sensitive.strings)
    tokens = re.compile(pattern) if pattern else None
    pattern = word_pattern(sensitive.words)
    words = re.compile(pattern) if pattern else None
    keys = sorted({k.lower() for k in sensitive.project_keys}, key=len, reverse=True)
    key_re = re.compile(r"\b(?:%s)-\d+" % "|".join(map(re.escape, keys))) if keys else None

    def hit(text: str) -> Optional[str]:
        for rx in (tokens, words, key_re):
            m = rx.search(text) if rx else None
            if m:
                return text[max(0, m.start() - 20):m.end() + 20]
        for m in _EMAIL_RE.finditer(text):
            domain = m.group(1)
            if domain != ALLOWED_EMAIL_DOMAIN and not domain.endswith("." + ALLOWED_EMAIL_DOMAIN):
                return text[max(0, m.start() - 20):m.end() + 20]
        return None

    findings: list[str] = []
    for table in _tables(conn):
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            strs = [(c, v) for c, v in zip(cols, row) if isinstance(v, str) and v]
            if not strs or not hit(_prepare(_SEP.join(v for _, v in strs))):
                continue
            for col, value in strs:
                fragment = hit(_prepare(value))
                if fragment is not None:
                    findings.append(f"{table}.{col}: {fragment}")
            if len(findings) >= MAX_FINDINGS:
                return findings
    return findings
