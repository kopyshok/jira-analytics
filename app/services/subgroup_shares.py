"""Распределение сотрудника по группам внутри команды — единая точка чтения.

Запись распределения: дата начала + доли по группам (сумма 100 %). Действует
до даты начала следующей записи того же сотрудника в той же команде. Дата
``None`` — «с начала участия». Перевод — запись «100 % в новую группу»,
деление — запись с несколькими группами.

Любой расчёт, которому нужна группа сотрудника, идёт сюда. Прямое чтение
таблицы долей в расчётах — регресс: без дат перевод снова начнёт переписывать
прошлое. Все функции — чистое чтение, без commit.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Employee, EmployeeSubgroupShare, Team
from app.services import team_membership as tm


@dataclass(frozen=True)
class ShareRecord:
    """Одна запись распределения."""

    valid_from: Optional[date]
    shares: tuple[tuple[str, int], ...]  # (группа, процент) по убыванию процента

    @property
    def groups(self) -> set[str]:
        return {g for g, _ in self.shares}


Records = list[ShareRecord]

_COLUMNS = (
    EmployeeSubgroupShare.employee_id,
    EmployeeSubgroupShare.team,
    EmployeeSubgroupShare.valid_from,
    EmployeeSubgroupShare.subgroup_id,
    EmployeeSubgroupShare.percent,
)


def _build(rows) -> dict[tuple[str, str], Records]:
    """Строки таблицы → записи по паре (сотрудник, команда), по возрастанию даты."""
    grouped: dict[tuple[str, str, Optional[date]], list[tuple[str, int]]] = {}
    for emp_id, team, valid_from, subgroup_id, percent in rows:
        grouped.setdefault((emp_id, team, valid_from), []).append(
            (subgroup_id, int(percent))
        )
    out: dict[tuple[str, str], Records] = {}
    for (emp_id, team, valid_from), shares in grouped.items():
        shares.sort(key=lambda s: (-s[1], s[0]))
        out.setdefault((emp_id, team), []).append(ShareRecord(valid_from, tuple(shares)))
    for records in out.values():
        records.sort(key=lambda r: r.valid_from or date.min)
    return out


def load_team(
    db: Session, team: str, employee_ids: Optional[Iterable[str]] = None
) -> dict[str, Records]:
    """Записи сотрудников одной команды: сотрудник → записи по дате."""
    q = db.query(*_COLUMNS).filter(EmployeeSubgroupShare.team == team)
    if employee_ids is not None:
        ids = list(employee_ids)
        if not ids:
            return {}
        q = q.filter(EmployeeSubgroupShare.employee_id.in_(ids))
    return {emp_id: recs for (emp_id, _), recs in _build(q.all()).items()}


def load_all(
    db: Session, employee_ids: Optional[Iterable[str]] = None
) -> dict[tuple[str, str], Records]:
    """Записи всех команд: (сотрудник, команда) → записи. Для витрин и резолвера."""
    q = db.query(*_COLUMNS)
    if employee_ids is not None:
        ids = list(employee_ids)
        if not ids:
            return {}
        q = q.filter(EmployeeSubgroupShare.employee_id.in_(ids))
    return _build(q.all())


def team_subgroups(db: Session, team: Optional[str]) -> list[tuple[str, str]]:
    """[(id, имя)] групп команды в порядке реестра. Пусто — деления нет."""
    if not team:
        return []
    registry = db.query(Team).filter(Team.name == team).first()
    if registry is None or not registry.has_subgroups:
        return []
    return [(g.id, g.name) for g in registry.subgroups]


def record_on(records: Records, day: date) -> Optional[ShareRecord]:
    """Запись, действующая в этот день. None — группы в этот день нет."""
    current: Optional[ShareRecord] = None
    for rec in records:
        if rec.valid_from is None or rec.valid_from <= day:
            current = rec
        else:
            break
    return current


def shares_on(records: Records, day: date) -> dict[str, float]:
    """Доли групп в этот день: группа → доля 0..1. Пусто — группы нет."""
    rec = record_on(records, day)
    return {g: p / 100.0 for g, p in rec.shares} if rec else {}


def single_group_on(records: Records, day: date) -> Optional[str]:
    """Группа, если в этот день человек целиком в одной группе, иначе None."""
    rec = record_on(records, day)
    if rec is not None and len(rec.shares) == 1:
        return rec.shares[0][0]
    return None


def split_hours(records: Records, day: date, hours: float) -> dict[str, float]:
    """Часы дня по группам. Ключ ``""`` — у человека в этот день нет группы."""
    shares = shares_on(records, day)
    if not shares:
        return {"": hours}
    return {g: hours * s for g, s in shares.items()}


def segments(
    records: Records, start: date, end: date
) -> list[tuple[date, date, ShareRecord]]:
    """Отрезки периода [start, end] (границы включительно) с действующей записью.

    ``start``/``end`` должны быть обрезаны по датам участия сотрудника в
    команде — иначе отрезки захватят дни, когда его в команде ещё/уже не было.
    """
    out: list[tuple[date, date, ShareRecord]] = []
    for i, rec in enumerate(records):
        lo = max(rec.valid_from or start, start)
        nxt = records[i + 1].valid_from if i + 1 < len(records) else None
        hi = min(nxt - timedelta(days=1), end) if nxt else end
        if lo <= hi:
            out.append((lo, hi, rec))
    return out


def groups_between(records: Records, start: date, end: date) -> set[str]:
    """Группы, где у человека была доля хотя бы один день периода.

    ``start``/``end`` — границы, обрезанные по датам участия сотрудника.
    """
    return {g for _, _, rec in segments(records, start, end) for g in rec.groups}


def membership_bounds(spans: list[tuple[date, date]]) -> tuple[date, date]:
    """Границы участия внутри периода: первый и последний день (включительно)."""
    return spans[0][0], spans[-1][1]


def _fmt(d: date) -> str:
    return d.strftime("%d.%m")


def group_label(records: Records, group_id: str, start: date, end: date) -> str:
    """Подпись участия в группе за период: «60%», «с 15.11», «до 15.11».

    Пусто — весь период человек целиком в этой группе или у группы нет доли
    в периоде. ``start``/``end`` — границы, обрезанные по датам участия
    сотрудника в команде.
    """
    spans: list[list] = []  # [lo, hi, pct], соседние с той же долей склеены
    for lo, hi, rec in segments(records, start, end):
        pct = dict(rec.shares).get(group_id)
        if not pct:
            continue
        if spans and spans[-1][1] + timedelta(days=1) == lo and spans[-1][2] == pct:
            spans[-1][1] = hi
        else:
            spans.append([lo, hi, pct])
    parts = []
    for lo, hi, pct in spans:
        bits = []
        if pct < 100:
            bits.append(f"{pct}%")
        if lo > start:
            bits.append(f"с {_fmt(lo)}")
        if hi < end:
            bits.append(f"до {_fmt(hi + timedelta(days=1))}")
        if bits:
            parts.append(" ".join(bits))
    return ", ".join(parts)


def distribution_label(
    records: Records, start: date, end: date, names: dict[str, str]
) -> Optional[str]:
    """Подпись распределения за период — для снимка утверждения и сравнения с ним.

    «Ломбард» — весь период целиком в одной группе (так же выглядят старые
    снимки); «Ломбард 60% · РФМ 40%», «Ломбард до 15.11 · РФМ с 15.11» — иначе.
    ``names`` — группы команды в порядке реестра. None — группы нет.
    ``start``/``end`` — границы, обрезанные по датам участия сотрудника в
    команде, иначе подпись помянет дни вне команды.
    """
    present = groups_between(records, start, end)
    ordered = [g for g in names if g in present]
    if not ordered:
        return None
    return " · ".join(
        f"{names[g]} {group_label(records, g, start, end)}".strip() for g in ordered
    )


def quarter_labels(db: Session, team: str, start: date, end: date) -> dict[str, str]:
    """Сотрудник → подпись распределения за период. Пусто — деления нет.

    Подпись считается по дням участия сотрудника внутри периода: у кого
    членство в команде уже/ещё не покрывает весь период, границы сужаются до
    его фактических дней участия.
    """
    groups = team_subgroups(db, team)
    if not groups:
        return {}
    names = dict(groups)
    intervals = tm.member_intervals(db, [team], start, end)
    records = load_team(db, team, list(intervals))
    out: dict[str, str] = {}
    for emp_id, spans in intervals.items():
        label = distribution_label(records.get(emp_id, []), *membership_bounds(spans), names)
        if label:
            out[emp_id] = label
    return out


def ungrouped_members(db: Session, team: str, start: date, end: date) -> list[str]:
    """Активные участники команды с делением, у кого нет группы хоть в один день участия в периоде.

    Записи только начинаются и не заканчиваются, поэтому достаточно проверить
    первый день участия внутри периода. Пусто — у команды нет деления.
    """
    if not team_subgroups(db, team):
        return []
    intervals = tm.member_intervals(db, [team], start, end)
    if not intervals:
        return []
    active = [
        emp_id
        for (emp_id,) in db.query(Employee.id).filter(
            Employee.id.in_(list(intervals)), Employee.is_active.is_(True)
        )
    ]
    records = load_team(db, team, active)
    return sorted(
        emp_id
        for emp_id in active
        if record_on(records.get(emp_id, []), intervals[emp_id][0][0]) is None
    )
