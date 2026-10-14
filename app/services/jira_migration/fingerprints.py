"""Отпечатки ворклогов и смещение «настенного» времени облака.

Отпечаток ворклога — (ключ задачи, начало до минуты, длительность в
секундах): id ворклогов при переезде сменились и пересекаются с чужими.
В базе начало хранится «настенным» временем облака (наивным), в новой Jira
— UTC; разница находится сама по максимуму совпадений.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, NamedTuple, Optional

OFFSET_RANGE = range(-12, 15)
# Синк пишет начало ворклога фиксированным московским временем (UTC+3):
# сверка после применения рассчитывает именно на это смещение.
EXPECTED_OFFSET_HOURS = 3
OFFSET_SAMPLE = 20000
PROGRESS_EVERY = 5000
_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True, slots=True)
class DbWorklog:
    """Ворклог базы: ``minute`` — «настенное» время облака, как хранится."""

    key: str
    minute: int
    seconds: int
    employee_id: str
    team: Optional[str]


@dataclass(frozen=True, slots=True)
class DcWorklog:
    """Ворклог новой Jira: ``minute`` — UTC."""

    key: str
    minute: int
    seconds: int
    author_key: str


@dataclass(frozen=True, slots=True)
class DcUser:
    """Пользователь новой Jira: ``key`` — идентичность, ``name`` — логин."""

    key: str
    name: Optional[str]
    display_name: str

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "display_name": self.display_name}


@dataclass
class DcScan:
    rows: list[DcWorklog]          # только ворклоги задач, которые есть в базе
    authors: dict[str, DcUser]     # все авторы ворклогов новой Jira
    total: int                     # сколько ворклогов прочитано всего


class OffsetResult(NamedTuple):
    """Найденное смещение: раскладывается как (часы, совпадения, выборка)."""

    hours: int
    counts: dict[int, int]
    sample: int

    @property
    def unexpected(self) -> bool:
        """Смещение не московское — сверка после применения разойдётся по месяцам."""
        return self.hours != EXPECTED_OFFSET_HOURS


def minute_of(dt: datetime) -> int:
    """Номер минуты от 1970-01-01. Время с поясом переводится в UTC, наивное берётся как есть."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return int((dt - _EPOCH).total_seconds() // 60)


def detect_offset(
    db_rows: Sequence[DbWorklog],
    dc_rows: Sequence[DcWorklog],
    sample_limit: int = OFFSET_SAMPLE,
) -> OffsetResult:
    """Смещение (часы), с которым UTC новой Jira совпадает с временем базы.

    На равномерной выборке ворклогов новой Jira (шаг с округлением вверх —
    выборка покрывает весь список) пробуются −12…+14 ч; берётся смещение с
    наибольшим числом совпадений, при равенстве — московское (+3), затем
    меньшее по модулю. Возвращает (смещение, совпадения по смещениям,
    размер выборки); ``unexpected`` — смещение не московское.
    """
    db_set = {(r.key, r.minute, r.seconds) for r in db_rows}
    step = max(1, -(-len(dc_rows) // sample_limit)) if sample_limit > 0 else 1
    sample = list(dc_rows[::step])
    counts = {hours: 0 for hours in OFFSET_RANGE}
    for row in sample:
        for hours in OFFSET_RANGE:
            if (row.key, row.minute + hours * 60, row.seconds) in db_set:
                counts[hours] += 1
    best = max(
        OFFSET_RANGE,
        key=lambda hours: (counts[hours], hours == EXPECTED_OFFSET_HOURS, -abs(hours)),
    )
    return OffsetResult(best, counts, len(sample))


async def scan_dc_worklogs(
    jira: Any,
    id_to_key: Mapping[str, str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> DcScan:
    """Все ворклоги новой Jira (``since=0``) потоком; в память — только нужное.

    Ворклог задачи, которой нет в базе, не сравнивается, но его автор
    запоминается: по авторам ищутся неактивные пользователи для ФИО.
    """
    rows: list[DcWorklog] = []
    authors: dict[str, DcUser] = {}
    total = 0
    async for worklog in jira.iter_worklogs_updated_since(0):
        total += 1
        author = worklog.author
        author_key = author.jira_account_id
        if author_key not in authors:
            authors[author_key] = DcUser(author_key, author.name, author.display_name)
        key = id_to_key.get(str(worklog.issueId))
        if key is not None:
            rows.append(DcWorklog(
                key, minute_of(worklog.started_datetime), int(worklog.timeSpentSeconds), author_key,
            ))
        if on_progress is not None and total % PROGRESS_EVERY == 0:
            on_progress(total)
    if on_progress is not None:
        on_progress(total)
    return DcScan(rows=rows, authors=authors, total=total)
