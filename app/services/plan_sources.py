"""Несколько полей оценки на роль и спорные оценки.

Настройка роли (AppSetting ``jira_planned_<role>_hours_field_id``) — JSON-список
``[{"field_id", "kind": "alt"|"sum", "name"}]`` либо старое значение-строка
(один «альтернативный» кандидат).

Кандидаты роли: каждое заполненное «альтернативное» поле — отдельный кандидат;
все заполненные «слагаемые» — один кандидат (их сумма) на позиции первого
слагаемого в списке. Ноль считается незаполненным полем, если у роли есть
ненулевое значение. Разные значения кандидатов — спор; по умолчанию действует
первый кандидат. Выбор пользователя хранится с отпечатком кандидатов и
действует, пока отпечаток совпадает.

Модуль чистый: без БД и без Jira-клиента — только данные на входе и выходе.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Optional, Sequence

KIND_ALT = "alt"
KIND_SUM = "sum"
SUM_SOURCE = "sum"
MANUAL_SOURCE = "manual"

# Порядок ролей = порядок в ответах API.
ROLE_SETTING_KEYS: dict[str, str] = {
    "analyst": "jira_planned_analyst_hours_field_id",
    "dev": "jira_planned_dev_hours_field_id",
    "qa": "jira_planned_qa_hours_field_id",
    "opo": "jira_planned_opo_hours_field_id",
}
PLAN_HOURS_SETTING_KEYS = frozenset(ROLE_SETTING_KEYS.values())

_PRECISION = 6


@dataclass(frozen=True)
class FieldSpec:
    """Одно поле Jira в настройке роли."""

    field_id: str
    kind: str = KIND_ALT
    name: Optional[str] = None


@dataclass(frozen=True)
class Candidate:
    """Кандидат на значение роли: поле Jira или сумма слагаемых."""

    source: str
    label: str
    value: float

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "label": self.label, "value": self.value}


@dataclass(frozen=True)
class RoleResolution:
    """Итог по роли: действующее Jira-значение и признак нерешённого спора."""

    value: Optional[float]
    candidates: tuple[Candidate, ...]
    disputed: bool


@lru_cache(maxsize=128)
def parse_field_setting(raw: Optional[str]) -> tuple[FieldSpec, ...]:
    """Разобрать значение настройки роли. Кэшируется: синк зовёт на каждой задаче."""
    if raw is None:
        return ()
    text = raw.strip()
    if not text:
        return ()
    if not text.startswith("["):
        return (FieldSpec(field_id=text),)
    try:
        data = json.loads(text)
    except ValueError:
        return ()
    if not isinstance(data, list):
        return ()
    specs: list[FieldSpec] = []
    seen: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        fid = str(entry.get("field_id") or "").strip()
        if not fid or fid in seen:
            continue
        kind = entry.get("kind")
        name = entry.get("name")
        specs.append(FieldSpec(
            field_id=fid,
            kind=kind if kind in (KIND_ALT, KIND_SUM) else KIND_ALT,
            name=name if isinstance(name, str) and name.strip() else None,
        ))
        seen.add(fid)
    return tuple(specs)


def field_layout(raw: Optional[str]) -> tuple[tuple[str, str], ...]:
    """Что из настройки роли читает синк: поля и их вид по порядку.

    Название поля — только подпись варианта в споре. Смена одних названий
    (например, старая строка → тот же список с названием) не повод
    перечитывать все задачи из Jira.
    """
    return tuple((s.field_id, s.kind) for s in parse_field_setting(raw))


def build_candidates(
    specs: Sequence[FieldSpec], values: Mapping[str, Optional[float]]
) -> tuple[Candidate, ...]:
    """Кандидаты роли в порядке настройки. ``values`` — {field_id: число|None}.

    Ноль — «поле не заполнено», если у роли есть ненулевое значение:
    «Анализ» = 0 при «Оценке 1С» = 56 — не спор, действует 56; нулевое
    слагаемое не попадает в подпись суммы. Все заполненные поля нулевые —
    роль получает 0 без спора.
    """
    filled = {
        s.field_id: float(v) for s in specs if (v := values.get(s.field_id)) is not None
    }
    if any(filled.values()):
        filled = {fid: v for fid, v in filled.items() if v}
    slots: list[Optional[Candidate]] = []
    sum_slot: Optional[int] = None
    sum_total = 0.0
    sum_labels: list[str] = []
    for spec in specs:
        if spec.kind == KIND_SUM and sum_slot is None:
            sum_slot = len(slots)
            slots.append(None)
        value = filled.get(spec.field_id)
        if value is None:
            continue
        label = spec.name or spec.field_id
        if spec.kind == KIND_SUM:
            sum_total += value
            sum_labels.append(label)
        else:
            slots.append(Candidate(spec.field_id, label, value))
    if sum_slot is not None and sum_labels:
        slots[sum_slot] = Candidate(
            SUM_SOURCE, " + ".join(sum_labels), round(sum_total, _PRECISION)
        )
    return tuple(c for c in slots if c is not None)


def fingerprint(candidates: Sequence[Candidate]) -> str:
    """Отпечаток набора кандидатов: меняется при любом изменении значений в Jira."""
    payload = json.dumps(
        [[c.source, round(c.value, _PRECISION)] for c in candidates],
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _has_conflict(candidates: Sequence[Candidate]) -> bool:
    return len({round(c.value, _PRECISION) for c in candidates}) > 1


def resolve_role(
    candidates: Sequence[Candidate],
    choice: Optional[Mapping[str, Any]],
    has_manual: bool = False,
) -> RoleResolution:
    """Действующее Jira-значение роли и признак нерешённого спора.

    Выбор «своё значение» (``manual``) решает спор, только пока у роли есть
    ручное значение; Jira-значение при этом остаётся первым кандидатом.
    """
    cands = tuple(candidates)
    if not cands:
        return RoleResolution(None, (), False)
    if not _has_conflict(cands):
        return RoleResolution(cands[0].value, cands, False)
    value = cands[0].value
    resolved = False
    if choice and choice.get("fingerprint") == fingerprint(cands):
        source = choice.get("source")
        if source == MANUAL_SOURCE:
            resolved = has_manual
        else:
            picked = next((c for c in cands if c.source == source), None)
            if picked is not None:
                value = picked.value
                resolved = True
    return RoleResolution(value, cands, not resolved)


def candidates_to_json(candidates: Sequence[Candidate]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in candidates]


def candidates_from_json(raw: Any) -> tuple[Candidate, ...]:
    """Прочитать кандидатов из JSON-колонки; мусор пропускается."""
    if not isinstance(raw, list):
        return ()
    out: list[Candidate] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        source, value = entry.get("source"), entry.get("value")
        if not isinstance(source, str) or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out.append(Candidate(source, str(entry.get("label") or source), float(value)))
    return tuple(out)


def disputes_for(
    sources: Optional[Mapping[str, Any]],
    choice: Optional[Mapping[str, Any]],
    manual_roles: set[str],
) -> dict[str, tuple[Candidate, ...]]:
    """Нерешённые споры задачи: {role: кандидаты} в порядке ролей."""
    result: dict[str, tuple[Candidate, ...]] = {}
    if not sources:
        return result
    choice = choice or {}
    for role in ROLE_SETTING_KEYS:
        cands = candidates_from_json(sources.get(role))
        res = resolve_role(cands, choice.get(role), has_manual=role in manual_roles)
        if res.disputed:
            result[role] = cands
    return result
