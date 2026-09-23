# Планирование Q4, часть 3: несколько полей оценки и спорные оценки. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Для каждой роли (анализ, разработка, тестирование, ОПЭ) можно указать несколько полей Jira с оценкой: «альтернативы» конкурируют, «слагаемые» суммируются. Если значения расходятся, оценка помечается спорной, пользователь выбирает действующее значение прямо в списке целевых задач.

**Architecture:** Разбор настройки, сбор кандидатов, отпечаток и проверку выбора держит маленький чистый модуль `app/services/plan_sources.py` без обращений к БД. Синк сохраняет кандидатов роли в `Issue.planned_hours_sources` и пишет действующее значение в прежний `planned_<role>_hours_jira`, так что остальной код ничего не замечает. Выбор пользователя хранится в `Issue.planned_hours_choice` вместе с отпечатком кандидатов. Когда значения в Jira меняются, отпечаток перестаёт совпадать и спор открывается снова. Список бэклога отдаёт спорные роли и кандидатов, `POST /issues/{id}/plan/choice` сохраняет выбор через `PlanEditService`.

**Tech Stack:** FastAPI, SQLAlchemy 2 (колонки `sa.JSON`), Alembic (batch mode), pytest; React 19 + TS + AntD 6, TanStack Query, vitest.

**Спецификация:** `docs/superpowers/specs/2026-09-23-planning-q4-design.md`, «Часть 3».

**Что уже должно быть сделано до начала:** части 1 и 2. Особенно пункт 1.5: в `PlanEditService` есть помощник `_sync_backlog(issue)`, который вызывает `BacklogService.sync_from_issue` только для задач со строкой бэклога. `edit/revert/resolve_conflict` вызывают его до commit, а инлайн-правка часов в строке бэклога идёт через `PlanEditService`. Проверка перед стартом:

```bash
grep -n "_sync_backlog" app/services/plan_edit_service.py
```
Ожидаемо: определение и минимум 3 вызова. Если их нет, остановиться: часть 1.5 не влита.

---

## Где спецификация расходится с кодом и как поступаем

1. **Кэша имён полей Jira нет.** Имена полей настройки получают вживую из Jira (`GET /sync/jira-fields`, `browse_jira_fields` в `app/api/endpoints/sync.py:926`), в базе они не хранятся. Поэтому имя поля записывается в саму настройку при сохранении: `{"field_id", "kind", "name"}`. Если имени нет (старая настройка-строка), подписью служит id поля.
2. **Формат хранения кандидатов.** В спеке указан словарь `{role: {source_key: value}}`. Такой формат теряет порядок и подписи, а без Jira нельзя восстановить, какой кандидат «первый», и нечего показать в поповере. Храним упорядоченный список `{role: [{"source", "label", "value"}, ...]}` в порядке настройки, сумма стоит на позиции первого слагаемого.
3. **JSON в настройке ломает текущий синк.** `_configured_planned_field_ids` (sync_service.py:666) и `_fld_float` (sync_service.py:912) используют значение настройки как id поля. JSON-строка ушла бы в `fields=` запроса к Jira. Разбираем JSON в обоих местах, а не только в `_configured_planned_field_ids`, как написано в спеке.
4. **«Ввести своё» и сброс к Jira.** Если выбор `"manual"` действует только по отпечатку, то после «Сбросить к Jira» (`revert`) ручное значение пропадёт, а спор останется «решённым» с первым кандидатом, то есть молча. Поэтому выбор `"manual"` засчитывается, только пока у роли есть ручное значение.
5. **Выбор поля Jira при действующем ручном значении.** Спека об этом молчит. Ручное значение перекрывает `_jira`, и выбор не дал бы видимого эффекта. Выбор поля снимает ручное значение и пишет запись журнала с источником `dispute_choice`.
6. **Смена порядка или состава полей в настройке** меняет отпечаток, и выбор становится недействительным. Так и задумано: меняется значение по умолчанию.
7. **Подпись суммы.** Собирается из полных имён заполненных слагаемых: «Оценка Back + Оценка Front», а не «Back + Front», как в спеке.
8. **ОПЭ после отсечки.** Ячейка ОПЭ в строке скрыта (`opoOffNow`), поэтому спор по ОПЭ доступен только через метку «спорно» у строки. Метка открывает поповер со всеми спорными ролями строки.
9. **Сюда же попадают дочерние эпики RFA.** Они приходят узкой схемой `BacklogChildSchema`. Спорные роли и кандидаты добавляются и в неё, иначе спор эпика в режиме «по эпикам» не виден.
10. **Миграция данных настройки не нужна.** Старое значение-строка читается как один «альтернативный» кандидат. Новый редактор при сохранении запишет список.
11. **Заметки «Что нового»** лежат не в `docs/`, а в `release_notes/drafts.json`. Добавляются командой `scripts/release_note.py add`.

---

## Карта файлов

| Файл | Что меняется |
|---|---|
| `app/services/plan_sources.py` (новый) | Разбор настройки, кандидаты, отпечаток, проверка выбора, спорные роли; чистые функции |
| `tests/test_plan_sources.py` (новый) | Модульные тесты чистого модуля |
| `app/models/issue.py` | Колонки `planned_hours_sources`, `planned_hours_choice` (JSON) |
| `alembic/versions/pq03_issue_plan_sources.py` (новый) | Добавление двух колонок |
| `app/services/sync_service.py` | Разбор списков в `_configured_planned_field_ids`, `_apply_plan_sources` вместо `_new_plan_values` |
| `tests/test_sync_plan_sources.py` (новый) | Синк: кандидаты, спор, выбор, запрос полей |
| `app/services/plan_edit_service.py` | `choose_source`, `choose_manual` |
| `tests/test_plan_choice_service.py` (новый) | Сервис выбора |
| `app/api/endpoints/issue_config.py` | `POST /issues/{id}/plan/choice` |
| `tests/test_plan_choice_api.py` (новый) | Эндпоинт выбора |
| `app/api/endpoints/backlog.py` | `disputed_roles`, `estimate_candidates` в строке и дочерней строке |
| `tests/test_backlog_disputes.py` (новый) | Список бэклога со спорами |
| `frontend/src/utils/planFieldSources.ts` (+ `.test.ts`) (новые) | Разбор и запись настройки, перестановка строк |
| `frontend/src/components/settings/PlanFieldListEditor.tsx` (новый) | Редактор списка полей роли |
| `frontend/src/components/JiraFieldsCard.tsx` | Блок «Плановые трудозатраты» на новом редакторе |
| `frontend/src/types/api.ts`, `frontend/src/api/issues.ts`, `frontend/src/hooks/useBacklog.ts` | Типы, запрос выбора, хук |
| `frontend/src/components/planning/BacklogRoleCell.tsx` | Признак `disputed`: пунктирная оранжевая обводка и «?» |
| `frontend/src/components/backlog/EstimateDisputePopover.tsx` (новый) | Поповер выбора |
| `frontend/src/pages/BacklogPage.tsx` | Спорные ячейки, метка «спорно», фильтр «Только спорные · N» |
| `docs/help/settings.md`, `docs/help/backlog.md` | Справка |
| `release_notes/drafts.json` | Заметки «Что нового» |

---

### Task 1: Чистый модуль `plan_sources`

**Files:**
- Create: `app/services/plan_sources.py`
- Test: `tests/test_plan_sources.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_plan_sources.py`:

```python
"""Несколько полей оценки на роль и спорные оценки — чистая логика."""
import json

from app.services.plan_sources import (
    MANUAL_SOURCE,
    SUM_SOURCE,
    Candidate,
    FieldSpec,
    build_candidates,
    candidates_from_json,
    candidates_to_json,
    disputes_for,
    fingerprint,
    parse_field_setting,
    resolve_role,
)

DEV = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
    {"field_id": "customfield_12889", "kind": "sum", "name": "Оценка Front"},
], ensure_ascii=False)


def _cands(setting: str, values: dict) -> tuple:
    return build_candidates(parse_field_setting(setting), values)


class TestParseFieldSetting:
    def test_empty(self):
        assert parse_field_setting(None) == ()
        assert parse_field_setting("") == ()
        assert parse_field_setting("   ") == ()

    def test_legacy_plain_string_is_one_alt(self):
        assert parse_field_setting("customfield_12431") == (
            FieldSpec(field_id="customfield_12431", kind="alt", name=None),
        )

    def test_json_list_keeps_order_kind_name(self):
        specs = parse_field_setting(DEV)
        assert [s.field_id for s in specs] == [
            "customfield_12432", "customfield_14648", "customfield_12888", "customfield_12889",
        ]
        assert [s.kind for s in specs] == ["alt", "alt", "sum", "sum"]
        assert specs[1].name == "Оценка 1С (ч)"

    def test_broken_json_gives_nothing(self):
        assert parse_field_setting("[{") == ()

    def test_unknown_kind_is_alt_and_duplicates_dropped(self):
        raw = json.dumps([
            {"field_id": "cf_1", "kind": "weird"},
            {"field_id": "cf_1", "kind": "sum"},
            {"field_id": ""},
        ])
        assert parse_field_setting(raw) == (FieldSpec("cf_1", "alt", None),)


class TestResolveRole:
    def test_no_candidates(self):
        res = resolve_role((), None)
        assert res.value is None and res.disputed is False

    def test_one_field(self):
        cands = _cands("customfield_12431", {"customfield_12431": 40.0})
        res = resolve_role(cands, None)
        assert res.value == 40.0
        assert res.disputed is False

    def test_empty_field_is_not_a_candidate(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": None})
        assert [c.source for c in cands] == ["customfield_12432"]
        assert resolve_role(cands, None).disputed is False

    def test_equal_alts_no_dispute(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 100.0})
        res = resolve_role(cands, None)
        assert res.value == 100.0
        assert res.disputed is False

    def test_different_alts_dispute_default_first(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        res = resolve_role(cands, None)
        assert res.disputed is True
        assert res.value == 100.0

    def test_sum_fields_summed_as_one_candidate_at_first_sum_position(self):
        raw = json.dumps([
            {"field_id": "cf_back", "kind": "sum", "name": "Оценка Back"},
            {"field_id": "cf_main", "kind": "alt", "name": "Разработка (ч)"},
            {"field_id": "cf_front", "kind": "sum", "name": "Оценка Front"},
        ], ensure_ascii=False)
        cands = _cands(raw, {"cf_back": 30.0, "cf_main": 80.0, "cf_front": 50.0})
        assert cands == (
            Candidate(SUM_SOURCE, "Оценка Back + Оценка Front", 80.0),
            Candidate("cf_main", "Разработка (ч)", 80.0),
        )
        res = resolve_role(cands, None)
        assert res.disputed is False  # 30 + 50 == 80
        assert res.value == 80.0

    def test_partial_sum_uses_filled_parts_only(self):
        cands = _cands(DEV, {"customfield_12888": 30.0})
        assert cands == (Candidate(SUM_SOURCE, "Оценка Back", 30.0),)

    def test_sum_vs_alt_dispute(self):
        cands = _cands(DEV, {
            "customfield_12432": 100.0, "customfield_12888": 30.0, "customfield_12889": 50.0,
        })
        res = resolve_role(cands, None)
        assert res.disputed is True
        assert res.value == 100.0
        assert [c.source for c in cands] == ["customfield_12432", SUM_SOURCE]

    def test_choice_valid_until_fingerprint_changes(self):
        before = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        choice = {"source": "customfield_14648", "fingerprint": fingerprint(before)}
        res = resolve_role(before, choice)
        assert res.value == 120.0
        assert res.disputed is False

        after = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 130.0})
        res2 = resolve_role(after, choice)
        assert res2.value == 100.0
        assert res2.disputed is True

    def test_manual_choice_resolves_only_with_manual_value(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        choice = {"source": MANUAL_SOURCE, "fingerprint": fingerprint(cands)}
        assert resolve_role(cands, choice, has_manual=True).disputed is False
        assert resolve_role(cands, choice, has_manual=True).value == 100.0
        assert resolve_role(cands, choice, has_manual=False).disputed is True

    def test_float_noise_is_not_a_dispute(self):
        cands = (Candidate("a", "A", 0.1 + 0.2), Candidate("b", "B", 0.3))
        assert resolve_role(cands, None).disputed is False


class TestStorage:
    def test_json_roundtrip(self):
        cands = _cands(DEV, {"customfield_12432": 100.0, "customfield_12888": 30.0})
        assert candidates_from_json(candidates_to_json(cands)) == cands

    def test_from_json_tolerates_garbage(self):
        assert candidates_from_json(None) == ()
        assert candidates_from_json([{"source": "x"}, "junk", {"source": "y", "label": "Y", "value": 5}]) == (
            Candidate("y", "Y", 5.0),
        )

    def test_disputes_for(self):
        disputed = _cands(DEV, {"customfield_12432": 100.0, "customfield_14648": 120.0})
        calm = _cands("cf_qa", {"cf_qa": 10.0})
        sources = {"dev": candidates_to_json(disputed), "qa": candidates_to_json(calm)}
        assert disputes_for(sources, None, set()) == {"dev": disputed}
        choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(disputed)}}
        assert disputes_for(sources, choice, set()) == {}
        assert disputes_for(None, None, set()) == {}
```

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_plan_sources.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.plan_sources'`

- [ ] **Step 3: Написать модуль**

`app/services/plan_sources.py`:

```python
"""Несколько полей оценки на роль и спорные оценки.

Настройка роли (AppSetting ``jira_planned_<role>_hours_field_id``) — JSON-список
``[{"field_id", "kind": "alt"|"sum", "name"}]`` либо старое значение-строка
(один «альтернативный» кандидат).

Кандидаты роли: каждое заполненное «альтернативное» поле — отдельный кандидат;
все заполненные «слагаемые» — один кандидат (их сумма) на позиции первого
слагаемого в списке. Разные значения кандидатов — спор; по умолчанию действует
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


def build_candidates(
    specs: Sequence[FieldSpec], values: Mapping[str, Optional[float]]
) -> tuple[Candidate, ...]:
    """Кандидаты роли в порядке настройки. ``values`` — {field_id: число|None}."""
    slots: list[Optional[Candidate]] = []
    sum_slot: Optional[int] = None
    sum_total = 0.0
    sum_labels: list[str] = []
    for spec in specs:
        value = values.get(spec.field_id)
        label = spec.name or spec.field_id
        if spec.kind == KIND_SUM:
            if sum_slot is None:
                sum_slot = len(slots)
                slots.append(None)
            if value is not None:
                sum_total += value
                sum_labels.append(label)
            continue
        if value is not None:
            slots.append(Candidate(spec.field_id, label, float(value)))
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
```

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_plan_sources.py -v`
Expected: PASS, все тесты.

- [ ] **Step 5: Линтер и типы**

Run: `ruff check app/services/plan_sources.py tests/test_plan_sources.py && mypy app/services/plan_sources.py`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add app/services/plan_sources.py tests/test_plan_sources.py
git commit -m "feat(planning): расчёт спорных оценок по нескольким полям Jira" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Колонки задачи и миграция

**Files:**
- Modify: `app/models/issue.py` (импорт в строке 7, блок плановых часов в строках 96–123)
- Create: `alembic/versions/pq03_issue_plan_sources.py`

- [ ] **Step 1: Добавить колонки в модель**

В `app/models/issue.py` импорт в строке 7:

```python
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, false, true
```

Сразу после `planned_opo_hours_manual` (перед `@property def planned_analyst_hours`):

```python
    # Несколько полей оценки на роль (см. app/services/plan_sources.py).
    # planned_hours_sources — кандидаты из Jira на момент синка:
    #   {role: [{"source": field_id|"sum", "label": str, "value": float}]}.
    # planned_hours_choice — выбор пользователя при споре:
    #   {role: {"source": field_id|"sum"|"manual", "fingerprint": str}};
    #   действует, пока отпечаток текущих кандидатов совпадает.
    # Действующее значение по-прежнему лежит в planned_<role>_hours_jira.
    planned_hours_sources: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    planned_hours_choice: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 2: Узнать текущую голову миграций**

Run: `py -3.10 -m alembic heads`
Expected: одна голова. На момент написания плана это `td06a_issue_sprint_release`. Части 1–2 могут добавить свою миграцию, тогда брать фактическую голову из вывода.

- [ ] **Step 3: Написать миграцию**

`alembic/versions/pq03_issue_plan_sources.py` (в `down_revision` подставить голову из Step 2):

```python
"""issues: кандидаты оценки из нескольких полей Jira и выбор при споре

Revision ID: pq03_issue_plan_sources
Revises: td06a_issue_sprint_release
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq03_issue_plan_sources"
down_revision: Union[str, None] = "td06a_issue_sprint_release"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("planned_hours_sources", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("planned_hours_choice", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("planned_hours_choice")
        batch.drop_column("planned_hours_sources")
```

Миграция самодостаточна: живой код приложения не импортирует.

- [ ] **Step 4: Прогнать миграцию туда и обратно на копии базы**

Run:
```bash
py -3.10 -m alembic upgrade head && py -3.10 -m alembic downgrade -1 && py -3.10 -m alembic upgrade head
```
Expected: без ошибок. Если локальная база — бэкап продакшна, предварительно сделать копию `data/*.db`.

- [ ] **Step 5: Тесты моделей и цепочки миграций**

Run: `py -3.10 -m pytest tests/ -k "migration or model" -q --ignore=tests/api/test_llm.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/issue.py alembic/versions/pq03_issue_plan_sources.py
git commit -m "feat(db): кандидаты оценки и выбор при споре у задачи" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Синк читает несколько полей и считает спор

**Files:**
- Modify: `app/services/sync_service.py` (импорты; `_configured_planned_field_ids` ~666; `_upsert_issue`: `_new_plan_values` ~939 и вызов `_record_plan_changes` ~1010; новая функция рядом с `_record_plan_changes` ~466)
- Test: `tests/test_sync_plan_sources.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_sync_plan_sources.py`:

```python
"""Синк: несколько полей оценки на роль, спор и выбор."""
import json
from unittest.mock import MagicMock

from app.models import AppSetting, Issue, Project
from app.services.plan_sources import SUM_SOURCE, candidates_from_json, fingerprint
from app.services.sync_service import SyncService
from tests.test_sync_service import _make_issue_schema_with_extra

DEV_SETTING = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
    {"field_id": "customfield_12889", "kind": "sum", "name": "Оценка Front"},
], ensure_ascii=False)


def _setup(db):
    db.add(AppSetting(key="jira_planned_dev_hours_field_id", value=DEV_SETTING))
    db.add(AppSetting(key="jira_planned_analyst_hours_field_id", value="customfield_12431"))
    proj = Project(jira_project_id="pps", key="RFA", name="RFA")
    db.add(proj)
    db.commit()
    return SyncService(db, jira_client=MagicMock()), proj


def _upsert(svc, proj, extra):
    schema = _make_issue_schema_with_extra(
        jira_id="90001", key="RFA-900", project_key="RFA", project_id="pps",
        extra_fields=extra,
    )
    svc._upsert_issue(schema, project_id=proj.id)
    svc.db.commit()
    return svc.db.query(Issue).filter_by(jira_issue_id="90001").one()


def test_configured_ids_expand_lists_not_json(db_session):
    svc, _ = _setup(db_session)
    ids = svc._configured_planned_field_ids()
    for fid in ("customfield_12432", "customfield_14648", "customfield_12888",
                "customfield_12889", "customfield_12431"):
        assert fid in ids
    assert not any(i.startswith("[") for i in ids)


def test_legacy_string_setting_still_works(db_session):
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12431": 40})
    assert issue.planned_analyst_hours_jira == 40.0
    assert candidates_from_json(issue.planned_hours_sources["analyst"])[0].value == 40.0


def test_equal_alts_no_dispute_value_set(db_session):
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12432": 100, "customfield_14648": "100"})
    assert issue.planned_dev_hours_jira == 100.0
    assert len(issue.planned_hours_sources["dev"]) == 2


def test_dispute_default_first_then_choice_then_change(db_session):
    svc, proj = _setup(db_session)
    extra = {"customfield_12432": 100, "customfield_12888": 30, "customfield_12889": 50}
    issue = _upsert(svc, proj, extra)
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    assert [c.source for c in cands] == ["customfield_12432", SUM_SOURCE]
    assert issue.planned_dev_hours_jira == 100.0

    issue.planned_hours_choice = {"dev": {"source": SUM_SOURCE, "fingerprint": fingerprint(cands)}}
    db_session.commit()
    issue = _upsert(svc, proj, extra)
    assert issue.planned_dev_hours_jira == 80.0

    extra["customfield_12889"] = 60
    issue = _upsert(svc, proj, extra)
    assert issue.planned_dev_hours_jira == 100.0


def test_no_fields_filled_clears_sources(db_session):
    svc, proj = _setup(db_session)
    _upsert(svc, proj, {"customfield_12432": 100})
    issue = _upsert(svc, proj, {})
    assert issue.planned_hours_sources is None
    assert issue.planned_dev_hours_jira is None
```

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_sync_plan_sources.py -v`
Expected: FAIL (в `ids` лежит JSON-строка, `planned_hours_sources` пуст).

- [ ] **Step 3: Импорт**

В `app/services/sync_service.py` рядом с остальными `from app.services...` импортами:

```python
from app.services.plan_sources import (
    PLAN_HOURS_SETTING_KEYS,
    ROLE_SETTING_KEYS,
    build_candidates,
    candidates_to_json,
    parse_field_setting,
    resolve_role,
)
```

- [ ] **Step 4: `_configured_planned_field_ids` разворачивает списки**

Заменить цикл в `_configured_planned_field_ids`:

```python
        for key in _ALL_PLANNED_KEYS:
            raw = self._get_setting(key)
            if key in PLAN_HOURS_SETTING_KEYS:
                # Плановые часы: в настройке список полей (или старая строка).
                fids = [s.field_id for s in parse_field_setting(raw)]
            else:
                fids = [raw] if raw else []
            for fid in fids:
                if fid not in seen:
                    ids.append(fid)
                    seen.add(fid)
        return ids
```

- [ ] **Step 5: Функция расчёта по ролям**

В `app/services/sync_service.py` сразу перед `def _record_plan_changes`:

```python
def _apply_plan_sources(
    issue: "Issue", extra: dict, planned_ids: dict[str, Optional[str]]
) -> dict[str, Optional[float]]:
    """Собрать кандидатов по ролям, сохранить их в задаче и вернуть
    действующие Jira-значения {role: часы} для ``_record_plan_changes``.

    Спор без действующего выбора даёт первого кандидата по настройке.
    """
    choice = issue.planned_hours_choice or {}
    sources: dict[str, list] = {}
    values: dict[str, Optional[float]] = {}
    for role, key in ROLE_SETTING_KEYS.items():
        specs = parse_field_setting(planned_ids.get(key))
        raw = {s.field_id: _to_float(extra.get(s.field_id)) for s in specs}
        cands = build_candidates(specs, raw)
        values[role] = resolve_role(cands, choice.get(role)).value
        if cands:
            sources[role] = candidates_to_json(cands)
    new_sources = sources or None
    if issue.planned_hours_sources != new_sources:
        issue.planned_hours_sources = new_sources
    return values
```

- [ ] **Step 6: Подключить в `_upsert_issue`**

Удалить блок:

```python
        _new_plan_values = {
            "analyst": _fld_float("jira_planned_analyst_hours_field_id"),
            "dev": _fld_float("jira_planned_dev_hours_field_id"),
            "qa": _fld_float("jira_planned_qa_hours_field_id"),
            "opo": _fld_float("jira_planned_opo_hours_field_id"),
        }
```

Строку `_record_plan_changes(self.db, issue, _new_plan_values)` после `upsert_by_field` заменить на:

```python
        _record_plan_changes(
            self.db, issue, _apply_plan_sources(issue, extra, planned_ids)
        )
```

(`extra` и `planned_ids` уже определены выше в этом методе.)

- [ ] **Step 7: Запустить новые и старые тесты синка**

Run: `py -3.10 -m pytest tests/test_sync_plan_sources.py tests/test_sync_service.py -v`
Expected: PASS. Старый `test_upsert_issue_extracts_planned_hours_from_customfields` проходит, потому что строковые настройки читаются как одно поле.

- [ ] **Step 8: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_plan_sources.py
git commit -m "feat(sync): оценка роли из нескольких полей Jira, спор по умолчанию — первое поле" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Выбор значения в `PlanEditService`

**Files:**
- Modify: `app/services/plan_edit_service.py`
- Test: `tests/test_plan_choice_service.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_plan_choice_service.py`:

```python
"""PlanEditService: выбор значения спорной оценки."""
import pytest

from app.models import BacklogItem, Issue, PlanAudit, Project
from app.services.plan_edit_service import PlanEditService
from app.services.plan_sources import (
    MANUAL_SOURCE, candidates_from_json, disputes_for, fingerprint,
)

SOURCES = {"dev": [
    {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
    {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
]}


def _seed(db, manual=None):
    p = Project(id="p-ch", key="CH", jira_project_id="jp-ch", name="CH")
    i = Issue(
        id="i-ch", key="CH-1", jira_issue_id="j-ch", summary="Инициатива",
        issue_type="RFA", status="Open", project_id=p.id,
        category="initiatives_rfa",
        planned_dev_hours_jira=100.0, planned_dev_hours_manual=manual,
        planned_hours_sources=SOURCES,
    )
    b = BacklogItem(id="b-ch", title="Инициатива", issue_id=i.id,
                    estimate_dev_hours=manual if manual is not None else 100.0)
    db.add_all([p, i, b])
    db.commit()
    return i


def test_choose_source_sets_value_choice_audit_and_backlog(db_session):
    _seed(db_session, manual=90.0)
    PlanEditService(db_session).choose_source("i-ch", "dev", "sum", user_id=None)

    issue = db_session.get(Issue, "i-ch")
    assert issue.planned_dev_hours_jira == 80.0
    assert issue.planned_dev_hours_manual is None
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    assert issue.planned_hours_choice["dev"] == {"source": "sum", "fingerprint": fingerprint(cands)}
    assert disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, set()) == {}

    audit = db_session.query(PlanAudit).filter_by(issue_id="i-ch", source="dispute_choice").one()
    assert audit.value_before == 90.0 and audit.value_after == 80.0
    assert db_session.get(BacklogItem, "b-ch").estimate_dev_hours == 80.0


def test_choose_source_unknown_source_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_source("i-ch", "dev", "customfield_404")


def test_choose_source_unknown_role_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_source("i-ch", "boss", "sum")


def test_choose_manual_sets_manual_and_resolves(db_session):
    _seed(db_session)
    PlanEditService(db_session).choose_manual("i-ch", "dev", 95.0, user_id=None)

    issue = db_session.get(Issue, "i-ch")
    assert issue.planned_dev_hours_manual == 95.0
    assert issue.planned_dev_hours_jira == 100.0
    assert issue.planned_hours_choice["dev"]["source"] == MANUAL_SOURCE
    assert disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, {"dev"}) == {}
    assert db_session.get(BacklogItem, "b-ch").estimate_dev_hours == 95.0


def test_choose_manual_without_candidates_raises(db_session):
    _seed(db_session)
    with pytest.raises(ValueError):
        PlanEditService(db_session).choose_manual("i-ch", "qa", 10.0)
```

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_plan_choice_service.py -v`
Expected: FAIL, `AttributeError: 'PlanEditService' object has no attribute 'choose_source'`

- [ ] **Step 3: Реализовать**

В `app/services/plan_edit_service.py` добавить импорт (`BacklogService` и `BacklogItem` уже импортированы частью 1.5):

```python
from app.services.plan_sources import MANUAL_SOURCE, candidates_from_json, fingerprint
```

Методы в класс `PlanEditService` (после `resolve_conflict`):

```python
    def choose_source(
        self,
        issue_id: str,
        role: str,
        source: str,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Спорная оценка: сделать действующим одно из полей Jira.

        Выбор запоминается с отпечатком кандидатов: любое изменение значений
        в Jira делает его недействительным, и спор открывается снова.
        Ручное значение роли снимается — пользователь явно выбрал поле Jira.
        """
        if role not in ROLES:
            raise ValueError("Unknown role")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        candidates = candidates_from_json((issue.planned_hours_sources or {}).get(role))
        picked = next((c for c in candidates if c.source == source), None)
        if picked is None:
            raise ValueError("Такого значения нет среди полей Jira этой задачи")
        before = getattr(issue, f"planned_{role}_hours")
        choice = dict(issue.planned_hours_choice or {})
        choice[role] = {"source": source, "fingerprint": fingerprint(candidates)}
        issue.planned_hours_choice = choice  # новый dict — иначе JSON-колонка не заметит правку
        setattr(issue, f"planned_{role}_hours_jira", picked.value)
        setattr(issue, f"planned_{role}_hours_manual", None)
        if before != picked.value:
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=picked.value,
                source="dispute_choice", user_id=user_id,
                comment=f"Спорная оценка: выбрано «{picked.label}»",
                created_at=datetime.utcnow(),
            ))
        self._sync_backlog(issue)
        self.db.commit()
        return issue

    def choose_manual(
        self,
        issue_id: str,
        role: str,
        value: float,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Спорная оценка: «Ввести своё» — ручное значение роли.

        Спор считается решённым, пока совпадает отпечаток кандидатов и
        у роли есть ручное значение.
        """
        if role not in ROLES:
            raise ValueError("Unknown role")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        candidates = candidates_from_json((issue.planned_hours_sources or {}).get(role))
        if not candidates:
            raise ValueError("У роли нет значений из Jira")
        choice = dict(issue.planned_hours_choice or {})
        choice[role] = {"source": MANUAL_SOURCE, "fingerprint": fingerprint(candidates)}
        issue.planned_hours_choice = choice
        # edit (часть 1.5) пишет журнал, синкает копию в бэклоге и коммитит.
        return self.edit(
            issue_id, {role: value}, "Спорная оценка: введено своё значение",
            user_id=user_id,
        )
```

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_plan_choice_service.py tests/test_plan_edit_api.py tests/test_plan_conflict_api.py -v`
Expected: PASS.

Если `test_choose_manual_sets_manual_and_resolves` падает на `estimate_dev_hours`, значит `edit` не вызывает `_sync_backlog` и часть 1.5 не влита. Вернуться к предусловию.

- [ ] **Step 5: Commit**

```bash
git add app/services/plan_edit_service.py tests/test_plan_choice_service.py
git commit -m "feat(planning): выбор значения спорной оценки — поле Jira или своё" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `POST /issues/{id}/plan/choice`

**Files:**
- Modify: `app/api/endpoints/issue_config.py` (после `resolve_plan_conflict`, ~1273)
- Test: `tests/test_plan_choice_api.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_plan_choice_api.py`:

```python
"""POST /issues/{id}/plan/choice."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project
from app.services.event_bus import get_event_bus

SOURCES = {"dev": [
    {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
    {"source": "customfield_14648", "label": "Оценка 1С (ч)", "value": 120.0},
]}


@pytest.fixture
def client(testclient_db_session):
    bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app), bus
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_event_bus, None)


def _seed(db):
    p = Project(id="p-pc", key="PC", jira_project_id="jp-pc", name="PC")
    i = Issue(
        id="i-pc", key="PC-1", jira_issue_id="j-pc", summary="S",
        issue_type="RFA", status="Open", project_id=p.id,
        planned_dev_hours_jira=100.0, planned_hours_sources=SOURCES,
    )
    db.add_all([p, i])
    db.commit()


def test_choice_source(client, testclient_db_session):
    c, bus = client
    _seed(testclient_db_session)
    r = c.post("/api/v1/issues/i-pc/plan/choice",
               json={"role": "dev", "source": "customfield_14648"})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["dev"] == 120.0
    bus.publish.assert_awaited()


def test_choice_manual(client, testclient_db_session):
    c, _ = client
    _seed(testclient_db_session)
    r = c.post("/api/v1/issues/i-pc/plan/choice", json={"role": "dev", "manual_value": 110})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["dev"] == 110.0


@pytest.mark.parametrize("body", [
    {"role": "dev"},
    {"role": "dev", "source": "customfield_12432", "manual_value": 5},
    {"role": "dev", "source": "customfield_404"},
    {"role": "boss", "source": "customfield_12432"},
    {"role": "dev", "manual_value": -1},
])
def test_choice_invalid(client, testclient_db_session, body):
    c, _ = client
    _seed(testclient_db_session)
    assert c.post("/api/v1/issues/i-pc/plan/choice", json=body).status_code == 422


def test_choice_404(client):
    c, _ = client
    r = c.post("/api/v1/issues/missing/plan/choice", json={"role": "dev", "source": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run: `py -3.10 -m pytest tests/test_plan_choice_api.py -v`
Expected: FAIL с 404/405 (маршрута нет).

- [ ] **Step 3: Реализовать**

В `app/api/endpoints/issue_config.py` после `resolve_plan_conflict`:

```python
class PlanChoiceRequest(BaseModel):
    """Выбор значения спорной оценки: поле Jira (``source``) или своё (``manual_value``)."""

    role: str
    source: Optional[str] = None
    manual_value: Optional[float] = Field(default=None, ge=0)


@router.post("/{issue_id}/plan/choice")
async def choose_plan_source(
    issue_id: str,
    payload: PlanChoiceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    if (payload.source is None) == (payload.manual_value is None):
        raise HTTPException(422, "Укажите либо поле Jira, либо своё значение")
    svc = PlanEditService(db)
    try:
        if payload.source is not None:
            svc.choose_source(issue_id, payload.role, payload.source, user_id=current_user.id)
        else:
            svc.choose_manual(
                issue_id, payload.role, payload.manual_value, user_id=current_user.id,
            )
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.refresh(issue)
    # Снимок до await: после commit атрибуты в TestClient-потоке перечитываются.
    plan = {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    await event_bus.publish(
        {"type": "entity_changed", "entities": ["issues", "backlog", "planning"]}
    )
    return {"plan": plan}
```

`manual_value` после проверки выше не `None`. Если mypy попросит сузить тип, передать `float(payload.manual_value)`.

- [ ] **Step 4: Запустить тесты**

Run: `py -3.10 -m pytest tests/test_plan_choice_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issue_config.py tests/test_plan_choice_api.py
git commit -m "feat(api): сохранение выбора по спорной оценке" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Список бэклога отдаёт спорные роли и кандидатов

**Files:**
- Modify: `app/api/endpoints/backlog.py` (схемы ~96–200, `_to_response` ~305, сборка `BacklogChildSchema` ~628–645)
- Test: `tests/test_backlog_disputes.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_backlog_disputes.py`:

```python
"""Список бэклога: спорные оценки."""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project
from app.services.event_bus import get_event_bus
from app.services.plan_sources import candidates_from_json, fingerprint

SOURCES = {
    "dev": [
        {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
        {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
    ],
    "qa": [{"source": "customfield_12433", "label": "Тестирование (ч)", "value": 20.0}],
}


def _get(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: AsyncMock()
    try:
        r = TestClient(app).get("/api/v1/backlog?view=active")
        assert r.status_code == 200, r.text
        return next(x for x in r.json() if x["id"] == "b-bd")
    finally:
        app.dependency_overrides.clear()


def _seed(db, choice=None):
    p = Project(id="p-bd", key="BD", jira_project_id="jp-bd", name="BD", is_active=True)
    i = Issue(
        id="i-bd", key="BD-1", jira_issue_id="j-bd", summary="S", issue_type="RFA",
        status="Open", status_category="new", project_id=p.id,
        planned_hours_sources=SOURCES, planned_hours_choice=choice,
    )
    b = BacklogItem(id="b-bd", title="S", issue_id=i.id)
    db.add_all([p, i, b])
    db.commit()


def test_disputed_role_and_candidates(testclient_db_session):
    _seed(testclient_db_session)
    row = _get(testclient_db_session)
    assert row["disputed_roles"] == ["dev"]
    assert row["estimate_candidates"]["dev"] == [
        {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
        {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
    ]
    assert "qa" not in row["estimate_candidates"]


def test_valid_choice_hides_dispute(testclient_db_session):
    fp = fingerprint(candidates_from_json(SOURCES["dev"]))
    _seed(testclient_db_session, choice={"dev": {"source": "sum", "fingerprint": fp}})
    row = _get(testclient_db_session)
    assert row["disputed_roles"] == []
    assert row["estimate_candidates"] == {}
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `py -3.10 -m pytest tests/test_backlog_disputes.py -v`
Expected: FAIL, `KeyError: 'disputed_roles'`

- [ ] **Step 3: Схемы и помощник**

В `app/api/endpoints/backlog.py` импорт:

```python
from app.services.plan_sources import ROLE_SETTING_KEYS, disputes_for
```

Перед `class BacklogChildSchema`:

```python
class EstimateCandidateSchema(BaseModel):
    """Значение роли из одного поля Jira (или сумма слагаемых) — для выбора при споре."""

    source: str
    label: str
    value: float
```

В `BacklogChildSchema` и в `BacklogItemResponse` (в конце полей, перед `class Config` у второй) добавить:

```python
    # Спорные оценки: роли, где поля Jira дают разные значения и выбор не сделан,
    # и кандидаты для выбора по каждой такой роли.
    disputed_roles: List[str] = []
    estimate_candidates: dict[str, List[EstimateCandidateSchema]] = {}
```

Помощник перед `_to_response`:

```python
def _estimate_disputes(
    issue: Optional[Issue],
) -> tuple[list[str], dict[str, list[EstimateCandidateSchema]]]:
    """Нерешённые споры оценки задачи: (роли, {роль: кандидаты})."""
    if issue is None or not issue.planned_hours_sources:
        return [], {}
    manual_roles = {
        r for r in ROLE_SETTING_KEYS
        if getattr(issue, f"planned_{r}_hours_manual") is not None
    }
    found = disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, manual_roles)
    return list(found), {
        role: [EstimateCandidateSchema(**c.to_dict()) for c in cands]
        for role, cands in found.items()
    }
```

- [ ] **Step 4: Заполнить в `_to_response` и у детей**

В `_to_response` перед `return BacklogItemResponse(`:

```python
    disputed_roles, estimate_candidates = _estimate_disputes(issue)
```

и в аргументы `BacklogItemResponse(...)` (после `children=children or [],`):

```python
        disputed_roles=disputed_roles,
        estimate_candidates=estimate_candidates,
```

В `list_backlog_items`, где собирается `schema = BacklogChildSchema(...)`, перед этой строкой:

```python
        child_disputed, child_candidates = _estimate_disputes(child_issue)
```

и в аргументы `BacklogChildSchema(...)`:

```python
            disputed_roles=child_disputed,
            estimate_candidates=child_candidates,
```

- [ ] **Step 5: Запустить тесты бэклога**

Run: `py -3.10 -m pytest tests/test_backlog_disputes.py tests/test_backlog_endpoints.py tests/test_backlog_active_view.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_backlog_disputes.py
git commit -m "feat(backlog): спорные оценки и кандидаты в строках списка" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Фронт: разбор и запись настройки полей

**Files:**
- Create: `frontend/src/utils/planFieldSources.ts`
- Test: `frontend/src/utils/planFieldSources.test.ts`

- [ ] **Step 1: Написать падающие тесты**

`frontend/src/utils/planFieldSources.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { moveEntry, parsePlanFieldSetting, serializePlanFieldSetting } from './planFieldSources';

describe('parsePlanFieldSetting', () => {
  it('пусто', () => {
    expect(parsePlanFieldSetting(null)).toEqual([]);
    expect(parsePlanFieldSetting('  ')).toEqual([]);
  });
  it('старая строка = одно поле-альтернатива', () => {
    expect(parsePlanFieldSetting('customfield_12431')).toEqual([
      { field_id: 'customfield_12431', kind: 'alt', name: null },
    ]);
  });
  it('JSON-список', () => {
    const raw = JSON.stringify([
      { field_id: 'customfield_12888', kind: 'sum', name: 'Оценка Back' },
      { field_id: 'customfield_12432', kind: 'x' },
    ]);
    expect(parsePlanFieldSetting(raw)).toEqual([
      { field_id: 'customfield_12888', kind: 'sum', name: 'Оценка Back' },
      { field_id: 'customfield_12432', kind: 'alt', name: null },
    ]);
  });
  it('битый JSON', () => {
    expect(parsePlanFieldSetting('[{')).toEqual([]);
  });
});

describe('serializePlanFieldSetting', () => {
  it('пустые строки и дубли выкидываются', () => {
    const out = serializePlanFieldSetting([
      { field_id: '', kind: 'alt' },
      { field_id: 'cf_1', kind: 'sum', name: 'A' },
      { field_id: 'cf_1', kind: 'alt' },
    ]);
    expect(JSON.parse(out)).toEqual([{ field_id: 'cf_1', kind: 'sum', name: 'A' }]);
  });
  it('ничего не выбрано → пустая строка', () => {
    expect(serializePlanFieldSetting([{ field_id: '', kind: 'alt' }])).toBe('');
  });
});

describe('moveEntry', () => {
  it('двигает и не выходит за края', () => {
    expect(moveEntry(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c']);
    expect(moveEntry(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
    expect(moveEntry(['a', 'b'], 1, 1)).toEqual(['a', 'b']);
  });
});
```

- [ ] **Step 2: Запустить и убедиться, что тесты падают**

Run (из `frontend/`): `npx vitest run src/utils/planFieldSources.test.ts`
Expected: FAIL, модуль не найден.

- [ ] **Step 3: Реализовать**

`frontend/src/utils/planFieldSources.ts`:

```ts
/** Настройка «Плановые трудозатраты»: несколько полей Jira на роль.
 *  Формат совпадает с бэкендом (app/services/plan_sources.py). */
export type PlanFieldKind = 'alt' | 'sum';

export interface PlanFieldEntry {
  field_id: string;
  kind: PlanFieldKind;
  name?: string | null;
}

export function parsePlanFieldSetting(raw: string | null | undefined): PlanFieldEntry[] {
  const text = (raw ?? '').trim();
  if (!text) return [];
  if (!text.startsWith('[')) return [{ field_id: text, kind: 'alt', name: null }];
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  return data.flatMap((e): PlanFieldEntry[] => {
    if (!e || typeof e !== 'object') return [];
    const o = e as Record<string, unknown>;
    const id = typeof o.field_id === 'string' ? o.field_id.trim() : '';
    if (!id) return [];
    return [{
      field_id: id,
      kind: o.kind === 'sum' ? 'sum' : 'alt',
      name: typeof o.name === 'string' && o.name.trim() ? o.name : null,
    }];
  });
}

export function serializePlanFieldSetting(entries: PlanFieldEntry[]): string {
  const seen = new Set<string>();
  const clean = entries.flatMap((e) => {
    const id = e.field_id.trim();
    if (!id || seen.has(id)) return [];
    seen.add(id);
    return [{ field_id: id, kind: e.kind, ...(e.name ? { name: e.name } : {}) }];
  });
  return clean.length ? JSON.stringify(clean) : '';
}

export function moveEntry<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = list.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
```

- [ ] **Step 4: Запустить тесты**

Run (из `frontend/`): `npx vitest run src/utils/planFieldSources.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/planFieldSources.ts frontend/src/utils/planFieldSources.test.ts
git commit -m "feat(settings): разбор списка полей оценки на фронте" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Настройки: список полей на роль

**Files:**
- Create: `frontend/src/components/settings/PlanFieldListEditor.tsx`
- Modify: `frontend/src/components/JiraFieldsCard.tsx`

- [ ] **Step 1: Редактор списка**

`frontend/src/components/settings/PlanFieldListEditor.tsx`:

```tsx
import { useState } from 'react';
import { Button, Segmented, Select, Space, Tooltip } from 'antd';
import {
  ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined,
} from '@ant-design/icons';
import {
  moveEntry, parsePlanFieldSetting, serializePlanFieldSetting,
  type PlanFieldEntry, type PlanFieldKind,
} from '../../utils/planFieldSources';

export interface JiraFieldOption {
  value: string;
  label: string;
  name: string;
}

interface Props {
  value: string;
  onChange: (next: string) => void;
  options: JiraFieldOption[];
  loading: boolean;
  onOpen: () => void;
}

const KIND_OPTIONS = [
  { label: 'Альтернатива', value: 'alt' },
  { label: 'Слагаемое', value: 'sum' },
];

/** Список полей Jira для одной роли: порядок важен — при споре по умолчанию
 *  действует верхнее поле. Пустые строки держим локально, в настройку не пишем. */
export default function PlanFieldListEditor({ value, onChange, options, loading, onOpen }: Props) {
  const [rows, setRows] = useState<PlanFieldEntry[]>(() => {
    const parsed = parsePlanFieldSetting(value);
    return parsed.length ? parsed : [{ field_id: '', kind: 'alt' }];
  });
  const nameById = new Map(options.map((o) => [o.value, o.name]));

  const update = (next: PlanFieldEntry[]) => {
    setRows(next);
    onChange(serializePlanFieldSetting(next));
  };
  const patchRow = (i: number, patch: Partial<PlanFieldEntry>) =>
    update(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      {rows.map((row, i) => (
        <Space key={i} size={4} wrap>
          <Select
            style={{ width: 300 }}
            value={row.field_id || undefined}
            showSearch
            allowClear
            optionFilterProp="label"
            placeholder="customfield_XXXXX"
            options={options}
            loading={loading}
            onOpenChange={(open) => { if (open) onOpen(); }}
            onChange={(v?: string) => patchRow(i, {
              field_id: v ?? '',
              name: v ? (nameById.get(v) ?? row.name ?? null) : null,
            })}
          />
          <Segmented
            size="small"
            value={row.kind}
            options={KIND_OPTIONS}
            onChange={(v) => patchRow(i, { kind: v as PlanFieldKind })}
          />
          <Tooltip title="Выше">
            <Button size="small" icon={<ArrowUpOutlined />} disabled={i === 0}
              onClick={() => update(moveEntry(rows, i, -1))} />
          </Tooltip>
          <Tooltip title="Ниже">
            <Button size="small" icon={<ArrowDownOutlined />} disabled={i === rows.length - 1}
              onClick={() => update(moveEntry(rows, i, 1))} />
          </Tooltip>
          <Tooltip title="Убрать поле">
            <Button size="small" icon={<DeleteOutlined />}
              onClick={() => update(rows.filter((_, j) => j !== i))} />
          </Tooltip>
        </Space>
      ))}
      <Button size="small" type="dashed" icon={<PlusOutlined />}
        onClick={() => setRows([...rows, { field_id: '', kind: 'alt' }])}>
        Добавить поле
      </Button>
    </Space>
  );
}
```

- [ ] **Step 2: Подключить в `JiraFieldsCard.tsx`**

1. Импорт: `import PlanFieldListEditor from './settings/PlanFieldListEditor';`
2. `interface FieldDef` дополнить полем `multi?: boolean;`.
3. Группу `planned_hours` заменить на:

```tsx
  {
    panelKey: 'planned_hours',
    title: 'Плановые трудозатраты (часы)',
    subtitle: 'На роль можно указать несколько полей. «Альтернатива» — отдельная оценка: если значения расходятся, оценка помечается спорной, а до выбора действует верхнее поле. «Слагаемые» складываются в одно значение.',
    fields: [
      { key: 'jira_planned_analyst_hours_field_id', label: 'Анализ (часы)', multi: true },
      { key: 'jira_planned_dev_hours_field_id',     label: 'Разработка (часы)', multi: true },
      { key: 'jira_planned_qa_hours_field_id',      label: 'Тестирование (часы)', multi: true },
      { key: 'jira_planned_opo_hours_field_id',     label: 'ОПЭ (часы)', multi: true },
    ],
  },
```

4. `fieldOptions` дополнить именем:

```tsx
  const fieldOptions = (jiraFields.data ?? []).map(f => ({
    value: f.id,
    label: `${f.name} (${f.id})`,
    name: f.name,
  }));
```

5. В начале `renderField` добавить ветку:

```tsx
  const renderField = (f: FieldDef) => f.multi ? (
    <Form.Item key={f.key} label={f.label} style={{ marginBottom: 8 }} wrapperCol={{ flex: '1 1 auto' }}>
      <PlanFieldListEditor
        // Перемонтируем после загрузки настроек: редактор держит строки у себя.
        key={`${f.key}-${loaded}`}
        value={values[f.key] ?? ''}
        onChange={v => setValues(prev => ({ ...prev, [f.key]: v }))}
        options={fieldOptions}
        loading={jiraFields.isFetching}
        onOpen={() => { if (!jiraFields.data) jiraFields.refetch(); }}
      />
    </Form.Item>
  ) : (
```

Дальше идёт существующая разметка `<Form.Item key={f.key} ...><Select .../></Form.Item>`. В конце выражения закрыть скобку тернарного оператора `)`.

`handleSaveAll` не меняется: значение роли уже строка (JSON или пусто).

- [ ] **Step 3: Проверить сборку и линтер**

Run (из `frontend/`): `npm run build && npm run lint`
Expected: без ошибок. Уже существующие ошибки линтера фронта сверить с `git stash`-прогоном и не чинить.

- [ ] **Step 4: Ручная проверка**

Запустить бэкенд и фронт (`make dev` или `uvicorn app.main:app --port 8000` плюс `npm run dev`). На `/settings` → «Поля Jira» → «Плановые трудозатраты»:
- у роли, где раньше было одно поле, это поле отображается строкой «Альтернатива»;
- поля добавляются, переставляются, удаляются, переключаются между «Альтернативой» и «Слагаемым»;
- после «Сохранить» и перезагрузки страницы порядок и вид полей на месте.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/PlanFieldListEditor.tsx frontend/src/components/JiraFieldsCard.tsx
git commit -m "feat(settings): несколько полей оценки на роль — альтернативы и слагаемые" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Фронт: типы, запрос и хук выбора

**Files:**
- Modify: `frontend/src/types/api.ts` (`BacklogChild` ~458, `BacklogItemResponse` ~476)
- Modify: `frontend/src/api/issues.ts` (после `resolvePlanConflict` ~196)
- Modify: `frontend/src/hooks/useBacklog.ts`

- [ ] **Step 1: Типы**

В `frontend/src/types/api.ts` перед `export interface BacklogChild`:

```ts
export type PlanRole = 'analyst' | 'dev' | 'qa' | 'opo';

/** Значение роли из поля Jira (или сумма слагаемых) — вариант выбора при споре. */
export interface EstimateCandidate {
  source: string;
  label: string;
  value: number;
}
```

В `BacklogChild` и в `BacklogItemResponse` добавить:

```ts
  disputed_roles?: PlanRole[];
  estimate_candidates?: Partial<Record<PlanRole, EstimateCandidate[]>>;
```

- [ ] **Step 2: Запрос**

В `frontend/src/api/issues.ts` после `resolvePlanConflict`:

```ts
export type PlanChoiceBody =
  | { role: string; source: string }
  | { role: string; manual_value: number };

export const choosePlanSource = (
  issueId: string,
  body: PlanChoiceBody,
): Promise<{ plan: Record<string, number | null> }> =>
  api.post(`/issues/${issueId}/plan/choice`, body);
```

- [ ] **Step 3: Хук**

В `frontend/src/hooks/useBacklog.ts` импорт `import { choosePlanSource, type PlanChoiceBody } from '../api/issues';` и в конец файла:

```ts
export const useChoosePlanSource = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, body }: { issueId: string; body: PlanChoiceBody }) =>
      choosePlanSource(issueId, body),
    onSuccess: (_d, vars) => {
      invalidateAllBacklog(qc);
      qc.invalidateQueries({ queryKey: ['plan-history', vars.issueId] });
      qc.invalidateQueries({ queryKey: ['planning'] });
    },
  });
};
```

- [ ] **Step 4: Сборка**

Run (из `frontend/`): `npm run build`
Expected: без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/issues.ts frontend/src/hooks/useBacklog.ts
git commit -m "feat(backlog): запрос выбора спорной оценки на фронте" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Ячейка со спором, поповер, метка и фильтр

**Files:**
- Modify: `frontend/src/components/planning/BacklogRoleCell.tsx`
- Create: `frontend/src/components/backlog/EstimateDisputePopover.tsx`
- Modify: `frontend/src/pages/BacklogPage.tsx`

- [ ] **Step 1: Признак спора у ячейки**

В `BacklogRoleCell.tsx`:
- в `BacklogRoleCellProps` добавить `disputed?: boolean;  // оценки в полях Jira расходятся`;
- в сигнатуру: `({ label, hours, total, color, involvement, durationDays, disputed })`;
- в `style` внешнего `div` после `userSelect: 'none',`:

```tsx
        outline: disputed ? '2px dashed var(--warn, #fa8c16)' : undefined,
        outlineOffset: disputed ? 1 : undefined,
```

- подпись роли: `{label}` заменить на

```tsx
        {label}
        {disputed && <span style={{ marginLeft: 3, color: 'var(--warn, #fa8c16)' }}>?</span>}
```

- подсказка: перед `if (!hasJiraData) return cell;` вставить

```tsx
  if (disputed) {
    return <Tooltip title="Оценки в полях Jira расходятся — нажмите, чтобы выбрать">{cell}</Tooltip>;
  }
```

`BacklogAllocRow.tsx` признак не передаёт, поэтому поведение там не меняется.

- [ ] **Step 2: Поповер выбора**

`frontend/src/components/backlog/EstimateDisputePopover.tsx`:

```tsx
import { useState, type ReactNode } from 'react';
import { App, Button, InputNumber, Popover, Radio, Space, Typography } from 'antd';
import { useChoosePlanSource } from '../../hooks/useBacklog';
import type { EstimateCandidate, PlanRole } from '../../types/api';

const ROLE_TITLE: Record<PlanRole, string> = {
  analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ',
};
const MANUAL = '__manual__';

function RoleChoice({ issueId, role, candidates, onDone }: {
  issueId: string;
  role: PlanRole;
  candidates: EstimateCandidate[];
  onDone: () => void;
}) {
  const { notification } = App.useApp();
  const choose = useChoosePlanSource();
  // Пока выбора нет, действует первое поле — его и отмечаем.
  const [picked, setPicked] = useState<string>(candidates[0]?.source ?? MANUAL);
  const [manual, setManual] = useState<number | null>(null);

  const accept = () => {
    const body = picked === MANUAL
      ? { role, manual_value: manual as number }
      : { role, source: picked };
    choose.mutate({ issueId, body }, {
      onSuccess: onDone,
      onError: (e) => notification.error({ title: 'Не удалось сохранить выбор', description: (e as Error).message }),
    });
  };

  return (
    <Space orientation="vertical" size={4}>
      <Typography.Text strong>{ROLE_TITLE[role]}</Typography.Text>
      <Radio.Group value={picked} onChange={(e) => setPicked(e.target.value)}>
        <Space orientation="vertical" size={2}>
          {candidates.map((c) => (
            <Radio key={c.source} value={c.source}>
              {c.label} — <b>{c.value} ч</b>
            </Radio>
          ))}
          <Radio value={MANUAL}>
            Ввести своё
            {picked === MANUAL && (
              <InputNumber
                autoFocus
                size="small"
                min={0}
                value={manual}
                onChange={(v) => setManual(v)}
                style={{ width: 90, marginLeft: 8 }}
              />
            )}
          </Radio>
        </Space>
      </Radio.Group>
      <Button
        size="small"
        type="primary"
        loading={choose.isPending}
        disabled={picked === MANUAL && manual == null}
        onClick={accept}
      >
        Принять
      </Button>
    </Space>
  );
}

/** Поповер выбора по спорным оценкам: одна роль (клик по ячейке) или все
 *  спорные роли строки (клик по метке «спорно»). */
export default function EstimateDisputePopover({ issueId, roles, candidates, children }: {
  issueId: string;
  roles: PlanRole[];
  candidates: Partial<Record<PlanRole, EstimateCandidate[]>>;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      title="Оценки в Jira расходятся — выберите значение"
      content={(
        <Space orientation="vertical" size={12} style={{ maxWidth: 380 }}>
          {roles.map((role) => (
            <RoleChoice
              key={role}
              issueId={issueId}
              role={role}
              candidates={candidates[role] ?? []}
              onDone={() => setOpen(false)}
            />
          ))}
        </Space>
      )}
    >
      {children}
    </Popover>
  );
}
```

- [ ] **Step 3: Спорная ячейка в колонке «АН / ПР / ТС / ОПЭ»**

В `BacklogPage.tsx`:
- импорты: `import EstimateDisputePopover from '../components/backlog/EstimateDisputePopover';`, а в `import type { ... } from '../types/api'` добавить `PlanRole`;
- на уровне модуля (рядом с `groupByQuarterLabel`):

```tsx
type EstimateField = 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours';
const FIELD_ROLE: Record<EstimateField, PlanRole> = {
  estimate_analyst_hours: 'analyst',
  estimate_dev_hours: 'dev',
  estimate_qa_hours: 'qa',
  estimate_opo_hours: 'opo',
};

function rowHasDispute(r: BacklogItemResponse): boolean {
  return (r.disputed_roles?.length ?? 0) > 0
    || (r.children ?? []).some((c) => (c.disputed_roles?.length ?? 0) > 0);
}
```

- в `makeCell` строку `const cell = <BacklogRoleCell ... />;` и следующую `if (!isEditable) return cell;` заменить на:

```tsx
          const disputed = (r.disputed_roles ?? []).includes(FIELD_ROLE[field]);
          const cell = <BacklogRoleCell label={label} hours={hours} total={total} color={color} involvement={involvement} durationDays={durationDays} disputed={disputed} />;
          if (disputed && r.issue_id) {
            return (
              <EstimateDisputePopover
                key={field}
                issueId={r.issue_id}
                roles={[FIELD_ROLE[field]]}
                candidates={r.estimate_candidates ?? {}}
              >
                <span style={{ cursor: 'pointer' }}>{cell}</span>
              </EstimateDisputePopover>
            );
          }
          if (!isEditable) return cell;
```

Если часть 1.5 изменила условие `isEditable` или тип поля ячейки, оставить её правки и вставить только ветку `if (disputed && r.issue_id)` перед проверкой редактируемости.

- [ ] **Step 4: Метка «спорно» у строки**

В колонке «Идея», внутри `<Space size={6}>` после блока `r.is_multi_team && (...)`:

```tsx
            {r.issue_id && (r.disputed_roles?.length ?? 0) > 0 && (
              <EstimateDisputePopover
                issueId={r.issue_id}
                roles={r.disputed_roles ?? []}
                candidates={r.estimate_candidates ?? {}}
              >
                <Tag
                  color="orange"
                  title="Оценки в полях Jira расходятся — нажмите, чтобы выбрать"
                  style={{ marginInlineEnd: 0, cursor: 'pointer' }}
                >
                  спорно
                </Tag>
              </EstimateDisputePopover>
            )}
```

- [ ] **Step 5: Прокинуть споры в дочерние строки**

В `adaptChildren`, в объекте ребёнка после `subgroup_source: ...`:

```tsx
        disputed_roles: c.disputed_roles ?? [],
        estimate_candidates: c.estimate_candidates ?? {},
```

- [ ] **Step 6: Фильтр «Только спорные · N»**

После `const quarterlyRows = useMemo(...)`:

```tsx
  const [onlyDisputed, setOnlyDisputed] = useState(false);
  const activeShown = useMemo(
    () => (onlyDisputed ? activeRows?.filter(rowHasDispute) : activeRows),
    [activeRows, onlyDisputed],
  );
  const quarterlyShown = useMemo(
    () => (onlyDisputed ? quarterlyRows?.filter(rowHasDispute) : quarterlyRows),
    [quarterlyRows, onlyDisputed],
  );
  const activeDisputed = activeRows?.filter(rowHasDispute).length ?? 0;
  const quarterlyDisputed = quarterlyRows?.filter(rowHasDispute).length ?? 0;
  const disputeFilter = (count: number) => (count > 0 || onlyDisputed) && (
    <Tag.CheckableTag
      checked={onlyDisputed}
      onChange={setOnlyDisputed}
      style={{ marginBottom: 8, marginRight: 8 }}
    >
      Только спорные · {count}
    </Tag.CheckableTag>
  );
```

Подключение:
- `quarterlyTable`: перед кнопкой «Группировать по кварталам» вставить `{disputeFilter(quarterlyDisputed)}`. `groupByQuarterLabel(quarterlyRows ?? [])` заменить на `groupByQuarterLabel(quarterlyShown ?? [])`, `dataSource={quarterlyRows}` на `dataSource={quarterlyShown}`;
- `activeTable`: обернуть в `<div>{disputeFilter(activeDisputed)}<Table ... dataSource={activeShown} .../></div>`.

Счётчики во вкладках («Активные (N)», «Бэклог (N)») и `totalHoursAll` продолжают считаться по нефильтрованным строкам. Если часть 2 уже добавила рядом метку «Не в плане · N», поставить новую метку в тот же ряд.

- [ ] **Step 7: Сборка и линтер**

Run (из `frontend/`): `npm run build && npm run lint && npx vitest run`
Expected: без новых ошибок.

- [ ] **Step 8: Ручная проверка в браузере**

В настройках у «Разработки» указать два поля-альтернативы, затем «Обновить только видимые» на «Целевых задачах» (или синк). У задачи, где значения расходятся:
- ячейка ПР с пунктирной оранжевой обводкой и «?», в ней значение первого поля;
- у строки метка «спорно»; метка «Только спорные · N» оставляет только такие строки;
- клик по ячейке открывает поповер с двумя полями и значениями; после «Принять» с другим полем обводка исчезает, число в ячейке и в «Всего часов» меняется;
- «Ввести своё» с числом: ячейка показывает введённое значение, спора нет;
- после изменения значения поля в Jira и повторного обновления спор появляется снова.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/planning/BacklogRoleCell.tsx frontend/src/components/backlog/EstimateDisputePopover.tsx frontend/src/pages/BacklogPage.tsx
git commit -m "feat(backlog): спорные оценки — подсветка, выбор значения, фильтр" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Справка

**Files:**
- Modify: `docs/help/settings.md:77`
- Modify: `docs/help/backlog.md` (таблица 3.1, раздел 7 «Частые проблемы»)

- [ ] **Step 1: Настройки**

`docs/help/settings.md`, строку 77 заменить на:

```markdown
- **Плановые трудозатраты (часы)** — поля оценки часов по ролям: анализ, разработка, тестирование, ОПЭ. На роль можно указать несколько полей. **Альтернатива** — отдельная оценка той же работы (например, «Разработка (ч)» и «Оценка 1С (ч)»). Если альтернативы расходятся, оценка в «Целевых задачах» помечается спорной, и до выбора действует верхнее поле списка. **Слагаемые** складываются в одно значение (например, «Оценка Back» + «Оценка Front») и конкурируют с альтернативами как одна оценка. Порядок меняется стрелками.
```

- [ ] **Step 2: Бэклог**

`docs/help/backlog.md`: в таблице 3.1 к строке **АН / ПР / ТС / ОПЭ** дописать:

```markdown
 Ячейка с пунктирной оранжевой обводкой и знаком «?» — спорная оценка: поля Jira дают разные значения. Клик открывает выбор: одно из полей или своё значение.
```

В раздел 7 «Частые проблемы» добавить пункт:

```markdown
- **У задачи метка «спорно».** В Jira у роли заполнено несколько полей оценки с разными значениями. Пока выбора нет, действует верхнее поле из настроек. Выберите значение кликом по ячейке или по метке; чтобы увидеть все такие задачи, включите «Только спорные». Если значение в Jira поменяется, выбор сбросится и задача снова станет спорной.
```

- [ ] **Step 3: Commit**

```bash
git add docs/help/settings.md docs/help/backlog.md
git commit -m "docs(help): несколько полей оценки и спорные оценки" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Полная проверка

- [ ] **Step 1: Бэкенд целиком (SQLite)**

Run: `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py`
Expected: всё зелёное.

- [ ] **Step 2: Postgres**

Run: `.\scripts\run_tests_postgres.ps1 -k "plan_sources or plan_choice or backlog_disputes or sync_plan_sources or migration"`
Expected: PASS (JSON-колонки и миграция на PostgreSQL).

- [ ] **Step 3: Линтеры**

Run: `ruff check app/ tests/ && mypy app/`
Expected: без новых ошибок.

- [ ] **Step 4: Фронт**

Run (из `frontend/`): `npm run build && npm run lint && npx vitest run`
Expected: без новых ошибок.

- [ ] **Step 5: Граф кода**

Run: `graphify update .`

---

### Task 13: Черновики «Что нового»

**Files:**
- Modify/Create: `release_notes/drafts.json` (через CLI)

Порядок записей: Новое → Улучшение → Исправление. В этой части только «Новое».

- [ ] **Step 1: Добавить записи**

```bash
py -3.10 scripts/release_note.py add --type new --section settings --title "Несколько полей оценки на роль" --description "В настройках полей Jira для каждой роли — анализа, разработки, тестирования, ОПЭ — можно указать несколько полей оценки. «Альтернатива» — отдельная оценка той же работы, «слагаемые» складываются в одно значение (например, оценка бэкенда и фронтенда). Порядок полей важен: если оценки расходятся, до выбора действует верхнее."
py -3.10 scripts/release_note.py add --type new --section backlog --title "Спорные оценки в целевых задачах" --description "Если поля оценки в Jira дают разные значения, ячейка роли обводится оранжевым пунктиром со знаком «?», а у задачи появляется метка «спорно». Клик открывает выбор: одно из полей Jira или своё значение. Метка «Только спорные» показывает все такие задачи. Если значение в Jira изменится, задача снова станет спорной."
```

- [ ] **Step 2: Проверить файл**

Run: `py -3.10 -c "import json;print(json.load(open('release_notes/drafts.json',encoding='utf-8'))['notes'][-2:])"`
Expected: две новые записи в конце списка. Если в файле уже есть заметки частей 1–2 типа «Улучшение»/«Исправление», руками переставить наши записи в блок «Новое», перед ними.

- [ ] **Step 3: Commit**

```bash
git add release_notes/drafts.json
git commit -m "docs(release-notes): несколько полей оценки и спорные оценки" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Самопроверка плана по спецификации

| Требование спеки | Задача |
|---|---|
| Настройка — JSON-список `{field_id, kind}`, старая строка читается | 1 (`parse_field_setting`), 7 |
| UI: список полей на роль, переключатель, добавить/удалить, вверх/вниз | 8 |
| Синк запрашивает все перечисленные поля | 3 (Step 4) |
| Кандидаты: альтернативы отдельно, слагаемые — сумма на позиции первого | 1 |
| 0 → пусто; 1 или все равны → без спора; разные → спор, первый по умолчанию | 1, 3 |
| Хранение кандидатов и выбора с отпечатком | 2, 3, 4 |
| «Ввести своё» = ручное значение через `PlanEditService`, источник `manual` | 4 |
| `_jira` = действующее значение, после записи — `sync_from_issue` | 3 (через пересчёт категорий после синка), 4 |
| Список бэклога: `disputed_roles` + кандидаты с подписями | 6 |
| `POST /issues/{id}/plan/choice` `{role, source}` / `{role, manual_value}`, событие | 5 |
| Ячейка: пунктир + «?», метка «спорно», фильтр «Только спорные · N», поповер | 10 |
| Тесты из спеки (одно поле, равные, разные, сумма, сумма против альтернативы, выбор до изменения, старая строка) | 1, 3 |
