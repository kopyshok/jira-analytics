# Периоды участия в команде + видимость общих ресурсов — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Участие сотрудника в команде становится периодом (дата входа + дата выбытия, несколько периодов); все расчёты — ресурс квартала, факт, аналитика, график работ — считают состав команды на дату; общий сотрудник (в нескольких командах) виден явно.

**Architecture:** `employee_teams` получает `left_at` и теряет unique `(employee_id, team)` — вместо него сервисная проверка непересечения. Новый модуль `app/services/team_membership.py` — единственная точка ответа «кто в команде», все ~30 прямых запросов по `EmployeeTeam.team == X` переводятся на него. Расхождение утверждённого сценария переиспользует существующий механизм `/capacity-diff` + `CapacityDriftIndicator`, новый баннер не создаётся.

**Tech Stack:** Python 3.10 (`py -3.10`), FastAPI, SQLAlchemy 2.0, Alembic (batch mode), pytest; React 19 + TS + Vite + AntD 6, react-query.

**Спека:** [docs/superpowers/specs/2026-07-28-team-membership-periods-design.md](../specs/2026-07-28-team-membership-periods-design.md)

---

## File Structure

**Создаются:**
- `app/services/team_membership.py` — единая точка расчёта состава на дату/период (чистые функции, без commit).
- `alembic/versions/<hash>_add_left_at_to_employee_teams.py` — `left_at` + снятие unique constraint.
- `tests/services/test_team_membership.py` — юниты helper'а.
- `tests/test_membership_periods_resource.py` — ресурс квартала при выбытии/входе.
- `tests/test_api_employees_membership_periods.py` — API периодов и перевода.
- `frontend/src/components/capacity/MembershipPeriods.tsx` — редактор периодов внутри карточки сотрудника.
- `frontend/src/components/capacity/TransferTeamModal.tsx` — диалог «Перевести в другую команду».

**Модифицируются (backend):** `app/models/employee_team.py`, `app/services/employee_team_service.py`, `app/api/endpoints/employees.py`, `app/services/resource_base_service.py`, `app/services/snapshot_writer.py`, `app/api/endpoints/planning.py`, `app/services/analytics_service.py`, `app/services/executive_dashboard_service.py`, `app/services/work_type_report_service.py`, `app/services/hours_balance_service.py`, `app/services/work_desk_widgets.py`, `app/services/plan_common.py`, `app/services/project_plan_service.py`, `app/services/scenario_xlsx_export.py`, `app/services/resource_planning_service.py`, `app/services/capacity_service.py`, `app/services/sync_service.py`, `app/api/endpoints/{analytics,capacity,work_desks,resource_planning}.py`.

**Модифицируются (frontend):** `frontend/src/types/api.ts`, `frontend/src/api/employees.ts`, `frontend/src/hooks/useCapacity.ts`, `frontend/src/components/capacity/EmployeeDrawer.tsx`, `frontend/src/pages/CapacityPage.tsx`, `frontend/src/components/planning/PlanningCapacityPanel.tsx`, `frontend/src/components/planning/ScenarioResourceSummary.tsx`, `frontend/src/pages/PlanningPage.tsx`.

---

## Ключевые соглашения

**Полуинтервал.** Участие активно в день `d`, если `(joined_at IS NULL OR joined_at <= d) AND (left_at IS NULL OR d < left_at)`. То есть `left_at` — **первый день вне команды**. Ушёл 15 февраля → `left_at = 2026-02-15`, последний рабочий день 14 февраля.

**Пересечение с периодом** `[start, end]` (обе границы включительно, как в остальном коде): `(joined_at IS NULL OR joined_at <= end) AND (left_at IS NULL OR left_at > start)`.

**Основная команда на дату** — среди активных на эту дату записей та, у которой `is_primary=True`. Инвариант: на любую дату не более одной.

---

### Task 1: `left_at` в модели + миграция

**Files:**
- Modify: `app/models/employee_team.py:29-46`
- Create: `alembic/versions/<hash>_add_left_at_to_employee_teams.py`
- Test: `tests/services/test_team_membership.py`

- [ ] **Step 1: Написать падающий тест на модель**

Создать `tests/services/test_team_membership.py`:

```python
"""Периоды участия в команде — модель и helper."""

from datetime import date

from app.models import Employee, EmployeeTeam


def _emp(db, name="Иванов И.", account="acc-1", role="dev"):
    e = Employee(
        jira_account_id=account,
        display_name=name,
        is_active=True,
        role=role,
    )
    db.add(e)
    db.flush()
    return e


def test_membership_stores_left_at(db_session):
    """У участия можно задать дату выбытия."""
    emp = _emp(db_session)
    db_session.add(EmployeeTeam(
        employee_id=emp.id,
        team="Альфа",
        is_primary=True,
        joined_at=date(2026, 1, 1),
        left_at=date(2026, 2, 15),
    ))
    db_session.commit()

    row = db_session.query(EmployeeTeam).one()
    assert row.left_at == date(2026, 2, 15)


def test_two_periods_in_same_team_allowed(db_session):
    """Ушёл и вернулся — две записи по одной паре сотрудник/команда."""
    emp = _emp(db_session)
    db_session.add_all([
        EmployeeTeam(
            employee_id=emp.id, team="Альфа", is_primary=False,
            joined_at=date(2026, 1, 1), left_at=date(2026, 3, 1),
        ),
        EmployeeTeam(
            employee_id=emp.id, team="Альфа", is_primary=True,
            joined_at=date(2026, 9, 1), left_at=None,
        ),
    ])
    db_session.commit()

    rows = db_session.query(EmployeeTeam).filter_by(team="Альфа").all()
    assert len(rows) == 2
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v`
Expected: FAIL — `TypeError: 'left_at' is an invalid keyword argument for EmployeeTeam` в первом тесте; второй падает на `UniqueConstraint`.

- [ ] **Step 3: Добавить поле и снять unique**

В `app/models/employee_team.py` заменить `__table_args__` и добавить поле после `joined_at`:

```python
    __tablename__ = "employee_teams"
    # Уникальность (employee_id, team) снята: одна пара может иметь несколько
    # непересекающихся периодов участия (ушёл — вернулся). Непересечение
    # проверяется в EmployeeTeamService, а не в БД.
```

(удалить блок `__table_args__` целиком)

```python
    joined_at: Mapped[_date | None] = mapped_column(Date, nullable=True)
    left_at: Mapped[_date | None] = mapped_column(Date, nullable=True)
```

И обновить docstring класса — добавить абзац:

```
    Участие периодизовано: активно в день ``d``, если
    ``(joined_at is None or joined_at <= d) and (left_at is None or d < left_at)``.
    ``left_at`` — первый день ВНЕ команды. Периодов на одну пару
    сотрудник/команда может быть несколько, пересекаться они не должны.
```

Инвариант `is_primary` в docstring поправить на: «не более одной активной ``is_primary=True`` записи на любую дату».

- [ ] **Step 4: Запустить тест — проходит**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Сгенерировать миграцию**

Run: `py -3.10 -m alembic revision --autogenerate -m "add left_at to employee_teams"`

Затем открыть созданный файл и привести `upgrade()`/`downgrade()` к batch-виду (SQLite не умеет DROP CONSTRAINT напрямую):

```python
def upgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch_op:
        batch_op.add_column(sa.Column("left_at", sa.Date(), nullable=True))
        batch_op.drop_constraint("uq_employee_teams_employee_team", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("employee_teams") as batch_op:
        batch_op.create_unique_constraint(
            "uq_employee_teams_employee_team", ["employee_id", "team"]
        )
        batch_op.drop_column("left_at")
```

`down_revision` должен быть `"f3a1b2c4d5e6"` (текущий head).

- [ ] **Step 6: Применить и проверить**

Run: `py -3.10 -m alembic upgrade head && py -3.10 -m alembic heads`
Expected: миграция применилась, head — новая ревизия.

- [ ] **Step 7: Commit**

```bash
git add app/models/employee_team.py alembic/versions/ tests/services/test_team_membership.py
git commit -m "feat(models): период участия в команде — дата выбытия"
```

---

### Task 2: Модуль `team_membership` — единая точка расчёта состава

**Files:**
- Create: `app/services/team_membership.py`
- Test: `tests/services/test_team_membership.py` (дополняем)

- [ ] **Step 1: Написать падающие тесты helper'а**

Дописать в `tests/services/test_team_membership.py`:

```python
from app.services import team_membership as tm


def _membership(db, emp, team, joined=None, left=None, primary=False):
    row = EmployeeTeam(
        employee_id=emp.id, team=team, is_primary=primary,
        joined_at=joined, left_at=left,
    )
    db.add(row)
    db.flush()
    return row


def test_members_on_respects_bounds(db_session):
    """left_at — первый день вне команды."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15))
    db_session.commit()

    assert tm.members_on(db_session, ["Альфа"], date(2026, 2, 14)) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2026, 2, 15)) == set()
    assert tm.members_on(db_session, ["Альфа"], date(2025, 12, 31)) == set()


def test_members_on_open_bounds(db_session):
    """Пустые даты — открытые границы."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа")
    db_session.commit()

    assert tm.members_on(db_session, ["Альфа"], date(2020, 1, 1)) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2030, 1, 1)) == {emp.id}


def test_members_overlapping(db_session):
    """Пересечение с периодом — хотя бы один день."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15))
    db_session.commit()

    assert tm.members_overlapping(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    ) == {emp.id}
    assert tm.members_overlapping(
        db_session, ["Альфа"], date(2026, 3, 1), date(2026, 3, 31)
    ) == set()


def test_member_intervals_clips_to_period(db_session):
    """Отрезки обрезаются границами запрошенного периода."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 10), date(2026, 2, 15))
    db_session.commit()

    intervals = tm.member_intervals(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert intervals[emp.id] == [(date(2026, 1, 10), date(2026, 2, 14))]


def test_member_intervals_two_periods(db_session):
    """Два периода с разрывом — два отрезка."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 1))
    _membership(db_session, emp, "Альфа", date(2026, 3, 1), None)
    db_session.commit()

    intervals = tm.member_intervals(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert intervals[emp.id] == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 3, 1), date(2026, 3, 31)),
    ]


def test_is_active_on_helper(db_session):
    """Проверка одного дня по заранее вычисленным отрезкам."""
    intervals = [(date(2026, 1, 1), date(2026, 1, 31))]
    assert tm.day_in_intervals(date(2026, 1, 15), intervals) is True
    assert tm.day_in_intervals(date(2026, 2, 1), intervals) is False


def test_members_ever_includes_departed(db_session):
    """Выбывшие входят в «когда-либо состоял»."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2020, 1, 1), date(2021, 1, 1))
    db_session.commit()

    assert tm.members_ever(db_session, ["Альфа"]) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2026, 1, 1)) == set()


def test_primary_team_on(db_session):
    """Основная команда определяется на дату."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15), primary=True)
    _membership(db_session, emp, "Бета", date(2026, 2, 15), None, primary=True)
    db_session.commit()

    assert tm.primary_team_on(db_session, emp.id, date(2026, 1, 20)) == "Альфа"
    assert tm.primary_team_on(db_session, emp.id, date(2026, 3, 1)) == "Бета"


def test_shared_members(db_session):
    """Сотрудник в двух командах за период — общий."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", primary=True)
    _membership(db_session, emp, "Бета")
    solo = _emp(db_session, name="Петров П.", account="acc-2")
    _membership(db_session, solo, "Альфа")
    db_session.commit()

    shared = tm.shared_members(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert shared == {emp.id: ["Бета"]}
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.team_membership'`

- [ ] **Step 3: Реализовать модуль**

Создать `app/services/team_membership.py`:

```python
"""Состав команды на дату — единая точка расчёта.

Участие сотрудника в команде периодизовано: ``joined_at`` — первый день
в команде (``None`` = «был всегда»), ``left_at`` — первый день ВНЕ команды
(``None`` = «состоит сейчас»). Полуинтервал ``[joined_at, left_at)``.

Одна пара сотрудник/команда может иметь несколько непересекающихся
периодов (ушёл — вернулся).

Все функции — чистое чтение, без commit. Любой код, которому нужен состав
команды, обязан идти сюда, а не запрашивать ``EmployeeTeam`` напрямую:
иначе выбывшие снова начнут попадать в расчёты задним числом.
"""

from datetime import date, timedelta
from typing import Iterable, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import EmployeeTeam


def active_on_clause(day: date):
    """SQLAlchemy-условие «участие активно в этот день»."""
    return (
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= day),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > day),
    )


def overlaps_clause(start: date, end: date):
    """SQLAlchemy-условие «участие пересекается с периодом [start, end]»."""
    return (
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= end),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > start),
    )


def members_on(db: Session, teams: Sequence[str], day: date) -> set[str]:
    """ID сотрудников, состоящих в любой из команд в указанный день."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)), *active_on_clause(day))
        .all()
    )
    return {r[0] for r in rows}


def members_overlapping(
    db: Session, teams: Sequence[str], start: date, end: date
) -> set[str]:
    """ID сотрудников, состоявших в командах хотя бы один день периода."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)), *overlaps_clause(start, end))
        .all()
    )
    return {r[0] for r in rows}


def members_ever(db: Session, teams: Sequence[str]) -> set[str]:
    """ID всех, кто когда-либо состоял в командах (включая выбывших)."""
    if not teams:
        return set()
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.team.in_(list(teams)))
        .all()
    )
    return {r[0] for r in rows}


def member_intervals(
    db: Session, teams: Sequence[str], start: date, end: date
) -> dict[str, list[tuple[date, date]]]:
    """Отрезки участия внутри периода, обрезанные его границами.

    Обе границы возвращаемых отрезков ВКЛЮЧИТЕЛЬНЫЕ — так удобнее для
    посуточных циклов. Отрезки одного сотрудника отсортированы по началу.
    """
    if not teams:
        return {}
    rows = (
        db.query(EmployeeTeam.employee_id, EmployeeTeam.joined_at, EmployeeTeam.left_at)
        .filter(EmployeeTeam.team.in_(list(teams)), *overlaps_clause(start, end))
        .all()
    )
    out: dict[str, list[tuple[date, date]]] = {}
    for emp_id, joined, left in rows:
        lo = max(joined, start) if joined else start
        hi = min(left - timedelta(days=1), end) if left else end
        if lo > hi:
            continue
        out.setdefault(emp_id, []).append((lo, hi))
    for intervals in out.values():
        intervals.sort()
    return out


def day_in_intervals(day: date, intervals: Iterable[tuple[date, date]]) -> bool:
    """Попадает ли день в один из отрезков (границы включительно)."""
    return any(lo <= day <= hi for lo, hi in intervals)


def primary_team_on(db: Session, employee_id: str, day: date) -> Optional[str]:
    """Основная команда сотрудника на указанный день."""
    row = (
        db.query(EmployeeTeam.team)
        .filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.is_primary == True,  # noqa: E712
            *active_on_clause(day),
        )
        .first()
    )
    return row[0] if row else None


def shared_members(
    db: Session, teams: Sequence[str], start: date, end: date
) -> dict[str, list[str]]:
    """Кто из состава команд пересекается с ДРУГИМИ командами за период.

    Возвращает ``employee_id -> отсортированный список чужих команд``.
    Сотрудники без пересечений в результат не попадают.
    """
    emp_ids = members_overlapping(db, teams, start, end)
    if not emp_ids:
        return {}
    rows = (
        db.query(EmployeeTeam.employee_id, EmployeeTeam.team)
        .filter(
            EmployeeTeam.employee_id.in_(list(emp_ids)),
            EmployeeTeam.team.notin_(list(teams)),
            *overlaps_clause(start, end),
        )
        .all()
    )
    out: dict[str, set[str]] = {}
    for emp_id, team in rows:
        out.setdefault(emp_id, set()).add(team)
    return {k: sorted(v) for k, v in out.items()}
```

- [ ] **Step 4: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v`
Expected: PASS (все тесты зелёные)

- [ ] **Step 5: Commit**

```bash
git add app/services/team_membership.py tests/services/test_team_membership.py
git commit -m "feat(services): состав команды на дату — единая точка расчёта"
```

---

### Task 3: Периоды в `EmployeeTeamService` — валидация и перевод

**Files:**
- Modify: `app/services/employee_team_service.py:103-243`
- Test: `tests/services/test_team_membership.py` (дополняем)

- [ ] **Step 1: Написать падающие тесты сервиса**

Дописать в `tests/services/test_team_membership.py`:

```python
import pytest

from app.services.employee_team_service import EmployeeTeamService


def test_set_left_at_closes_period(db_session):
    """Дата выбытия проставляется на открытый период."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа")

    svc.set_left_at(emp.id, "Альфа", date(2026, 2, 15))

    row = db_session.query(EmployeeTeam).filter_by(team="Альфа").one()
    assert row.left_at == date(2026, 2, 15)


def test_left_at_before_joined_at_rejected(db_session):
    """Выбытие не может быть раньше входа."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа")
    svc.set_joined_at(emp.id, "Альфа", date(2026, 3, 1))

    with pytest.raises(ValueError, match="раньше"):
        svc.set_left_at(emp.id, "Альфа", date(2026, 2, 1))


def test_overlapping_periods_rejected(db_session):
    """Второй период не может пересекаться с первым."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа", joined_at=date(2026, 1, 1))
    svc.set_left_at(emp.id, "Альфа", date(2026, 3, 1))

    with pytest.raises(ValueError, match="пересек"):
        svc.add_team(emp.id, "Альфа", joined_at=date(2026, 2, 1))


def test_rejoin_after_leaving_allowed(db_session):
    """Вернулся после выбытия — новый период создаётся."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа", joined_at=date(2026, 1, 1))
    svc.set_left_at(emp.id, "Альфа", date(2026, 3, 1))

    svc.add_team(emp.id, "Альфа", joined_at=date(2026, 9, 1))

    rows = db_session.query(EmployeeTeam).filter_by(team="Альфа").all()
    assert len(rows) == 2


def test_transfer_closes_old_and_opens_new(db_session):
    """Перевод одним шагом: старое закрыто, новое открыто с той же даты."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа", is_primary=True)

    svc.transfer(emp.id, from_team="Альфа", to_team="Бета", on=date(2026, 2, 15))

    old = db_session.query(EmployeeTeam).filter_by(team="Альфа").one()
    new = db_session.query(EmployeeTeam).filter_by(team="Бета").one()
    assert old.left_at == date(2026, 2, 15)
    assert old.is_primary is False
    assert new.joined_at == date(2026, 2, 15)
    assert new.left_at is None
    assert new.is_primary is True


def test_two_primary_on_same_date_rejected(db_session):
    """Две активные основные на одну дату — запрещено."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа", is_primary=True)

    with pytest.raises(ValueError, match="основн"):
        svc.add_team(emp.id, "Бета", is_primary=True, allow_primary_overlap=False)


def test_legacy_team_follows_today(db_session):
    """Legacy-колонка = основная команда на сегодня."""
    emp = _emp(db_session)
    svc = EmployeeTeamService(db_session)
    svc.add_team(emp.id, "Альфа", is_primary=True)
    assert emp.team == "Альфа"

    svc.set_left_at(emp.id, "Альфа", date(2020, 1, 1))
    db_session.refresh(emp)
    assert emp.team is None
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v -k "set_left_at or overlapping or rejoin or transfer or primary_on_same or legacy_team"`
Expected: FAIL — `AttributeError: 'EmployeeTeamService' object has no attribute 'set_left_at'`

- [ ] **Step 3: Реализовать периоды в сервисе**

В `app/services/employee_team_service.py`:

Добавить импорт вверху (после существующих):

```python
from app.services import team_membership as tm
```

Заменить `_recompute_legacy_team` (строки 103–115) на:

```python
    def _recompute_legacy_team(self, employee_id: str) -> None:
        """Обновить ``Employee.team`` = основная команда НА СЕГОДНЯ (или None).

        Derived-колонка для backward-compat с кодом, который ещё читает
        ``Employee.team`` напрямую. Вызывается из всех мутаций.
        """
        team = tm.primary_team_on(self.db, employee_id, date.today())
        emp = self.db.query(Employee).filter(Employee.id == employee_id).one()
        emp.team = team
```

Добавить приватные проверки (после `_recompute_legacy_team`):

```python
    def _assert_no_overlap(
        self,
        employee_id: str,
        team: str,
        joined_at: Optional[date],
        left_at: Optional[date],
        *,
        exclude_id: Optional[str] = None,
    ) -> None:
        """Периоды одной пары сотрудник/команда не должны пересекаться."""
        if joined_at and left_at and left_at < joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        rows = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
            )
            .all()
        )
        lo = joined_at or date.min
        hi = left_at or date.max
        for r in rows:
            if exclude_id and r.id == exclude_id:
                continue
            r_lo = r.joined_at or date.min
            r_hi = r.left_at or date.max
            if lo < r_hi and r_lo < hi:
                raise ValueError(
                    f"Период пересекается с существующим участием в команде {team!r}"
                )

    def _assert_single_primary(
        self,
        employee_id: str,
        team: str,
        joined_at: Optional[date],
        left_at: Optional[date],
        *,
        exclude_id: Optional[str] = None,
    ) -> None:
        """На любую дату у сотрудника не более одной основной команды."""
        rows = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.is_primary == True,  # noqa: E712
            )
            .all()
        )
        lo = joined_at or date.min
        hi = left_at or date.max
        for r in rows:
            if exclude_id and r.id == exclude_id:
                continue
            if r.team == team:
                continue
            r_lo = r.joined_at or date.min
            r_hi = r.left_at or date.max
            if lo < r_hi and r_lo < hi:
                raise ValueError(
                    f"На эти даты основной уже назначена команда {r.team!r}"
                )
```

Заменить `add_team` (строки 125–163) на:

```python
    def add_team(
        self,
        employee_id: str,
        team: str,
        *,
        is_primary: bool = False,
        joined_at: Optional[date] = None,
        allow_primary_overlap: bool = True,
    ) -> EmployeeTeam:
        """Добавить период участия в команде.

        Если у сотрудника ещё нет ни одного участия — период становится
        основным автоматически. Если открытый период в этой команде уже есть,
        возвращается он (идемпотентность для авто-определения команды).

        ``allow_primary_overlap=False`` включает строгую проверку «одна
        основная на дату»; по умолчанию основная просто перевешивается
        на новый период — так ведёт себя UI выбора основной команды.
        """
        open_existing = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if open_existing is not None:
            if is_primary and not open_existing.is_primary:
                self.set_primary(employee_id, team)
                self.db.refresh(open_existing)
            return open_existing

        self._assert_no_overlap(employee_id, team, joined_at, None)

        has_any = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .count()
        ) > 0
        make_primary = is_primary or not has_any
        if make_primary:
            if allow_primary_overlap:
                # Перевешиваем основную: закрываем признак у пересекающихся.
                self.db.query(EmployeeTeam).filter(
                    EmployeeTeam.employee_id == employee_id,
                    EmployeeTeam.is_primary == True,  # noqa: E712
                ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")
            else:
                self._assert_single_primary(employee_id, team, joined_at, None)

        row = EmployeeTeam(
            employee_id=employee_id,
            team=team,
            is_primary=make_primary,
            joined_at=joined_at,
        )
        self.db.add(row)
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row
```

Добавить `set_left_at` и `transfer` (после `set_joined_at`):

```python
    def set_left_at(
        self, employee_id: str, team: str, left_at: date | None
    ) -> EmployeeTeam:
        """Установить дату выбытия из команды (первый день вне команды).

        Правит последний по времени период указанной команды.
        """
        row = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
            )
            .order_by(EmployeeTeam.joined_at.desc().nullslast())
            .first()
        )
        if row is None:
            raise ValueError(f"Membership {employee_id}/{team} not found")
        if left_at and row.joined_at and left_at < row.joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        self._assert_no_overlap(
            employee_id, team, row.joined_at, left_at, exclude_id=row.id
        )
        row.left_at = left_at
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def transfer(
        self, employee_id: str, *, from_team: str, to_team: str, on: date
    ) -> EmployeeTeam:
        """Перевести сотрудника в другую команду одним шагом.

        Закрывает открытый период в ``from_team`` датой ``on``, открывает
        период в ``to_team`` с той же даты. Признак основной переносится,
        если старое участие было основным. Без дыр и нахлёстов.
        """
        old = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == from_team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if old is None:
            raise ValueError(f"Открытое участие в команде {from_team!r} не найдено")
        if old.joined_at and on < old.joined_at:
            raise ValueError("Дата перевода раньше даты вступления")

        was_primary = old.is_primary
        old.left_at = on
        old.is_primary = False
        self.db.flush()

        self._assert_no_overlap(employee_id, to_team, on, None)
        new = EmployeeTeam(
            employee_id=employee_id,
            team=to_team,
            is_primary=was_primary,
            joined_at=on,
        )
        self.db.add(new)
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(new)
        return new
```

Заменить `set_joined_at` (строки 206–217) — добавить валидацию:

```python
    def set_joined_at(self, employee_id: str, team: str, joined_at: date | None) -> EmployeeTeam:
        """Установить дату вступления сотрудника в команду."""
        row = (
            self.db.query(EmployeeTeam)
            .filter_by(employee_id=employee_id, team=team)
            .order_by(EmployeeTeam.joined_at.desc().nullslast())
            .first()
        )
        if row is None:
            raise ValueError(f"Membership {employee_id}/{team} not found")
        if joined_at and row.left_at and row.left_at < joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        self._assert_no_overlap(
            employee_id, team, joined_at, row.left_at, exclude_id=row.id
        )
        row.joined_at = joined_at
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row
```

В `set_primary` (строки 190–204) — выбирать открытый период и не трогать закрытые:

```python
    def set_primary(self, employee_id: str, team: str) -> None:
        target = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if target is None:
            raise ValueError(f"Employee {employee_id} not in team {team!r}")
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.left_at.is_(None),
        ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")
        target.is_primary = True
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
```

В `remove_team` (строки 165–188) — удалять только открытый период, историю не трогать:

```python
    def remove_team(self, employee_id: str, team: str) -> None:
        """Удалить открытый период участия. Закрытые периоды — история, не трогаем.

        Для «человек ушёл» правильный путь — ``set_left_at``/``transfer``;
        удаление означает «участия не было вовсе» (ошибка ввода).
        """
        row = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if row is None:
            return
        was_primary = row.is_primary
        self.db.delete(row)
        self.db.flush()
        if was_primary:
            leftover = (
                self.db.query(EmployeeTeam)
                .filter(
                    EmployeeTeam.employee_id == employee_id,
                    EmployeeTeam.left_at.is_(None),
                )
                .order_by(EmployeeTeam.team)
                .first()
            )
            if leftover is not None:
                leftover.is_primary = True
                self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
```

В `replace_teams` (строки 219–242) — удалять только открытые периоды, историю сохранять:

```python
    def replace_teams(
        self,
        employee_id: str,
        teams: list[str],
        primary: Optional[str] = None,
    ) -> list[EmployeeTeam]:
        """Заменить набор ТЕКУЩИХ команд. Закрытые периоды — история, не трогаются.

        Если primary указан и входит в teams — делает его основным, иначе
        первую команду списка. Пустой список закрывает всё текущее участие.
        """
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.left_at.is_(None),
        ).delete(synchronize_session=False)
        self.db.flush()
        chosen_primary = primary if primary in teams else (teams[0] if teams else None)
        for t in teams:
            self.db.add(EmployeeTeam(
                employee_id=employee_id,
                team=t,
                is_primary=(t == chosen_primary),
            ))
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        return self.list_teams(employee_id)
```

В `list_teams` (строки 117–123) — сортировка с учётом периодов:

```python
    def list_teams(self, employee_id: str) -> list[EmployeeTeam]:
        """Все периоды участия: открытые первыми, затем по дате входа убыв."""
        return (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .order_by(
                EmployeeTeam.left_at.is_(None).desc(),
                EmployeeTeam.is_primary.desc(),
                EmployeeTeam.team,
            )
            .all()
        )
```

В `auto_detect_all_missing` (строки 84–88) — «нет команды» теперь значит «нет ОТКРЫТОГО участия»:

```python
            has_any = (
                self.db.query(EmployeeTeam)
                .filter(
                    EmployeeTeam.employee_id == emp.id,
                    EmployeeTeam.left_at.is_(None),
                )
                .count()
            ) > 0
```

- [ ] **Step 4: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v`
Expected: PASS (все зелёные)

- [ ] **Step 5: Прогнать существующие тесты участия в командах**

Run: `py -3.10 -m pytest tests/test_api_employees_team.py tests/services/test_hours_balance_service.py -v`
Expected: PASS. Если падает из-за `is_primary` при добавлении второй команды — проверить, что вызов идёт без `allow_primary_overlap=False`.

- [ ] **Step 6: Commit**

```bash
git add app/services/employee_team_service.py tests/services/test_team_membership.py
git commit -m "feat(services): периоды участия, перевод между командами, валидация"
```

---

### Task 4: API периодов и перевода

**Files:**
- Modify: `app/api/endpoints/employees.py:22-27, 320-337`
- Test: `tests/test_api_employees_membership_periods.py`

- [ ] **Step 1: Написать падающий тест API**

Создать `tests/test_api_employees_membership_periods.py`:

```python
"""API периодов участия в команде и перевода между командами."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def employee(db_session):
    e = Employee(
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_patch_left_at(client, employee):
    """Проставить дату выбытия."""
    r = client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})
    assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-15"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["left_at"] == "2026-02-15"


def test_patch_left_at_before_joined_at_422(client, employee):
    """Выбытие раньше входа — отказ."""
    client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})
    client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/joined-at",
        json={"joined_at": "2026-03-01"},
    )

    r = client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-01"},
    )
    assert r.status_code == 422, r.text


def test_transfer_endpoint(client, employee):
    """Перевод закрывает старое участие и открывает новое."""
    client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})

    r = client.post(
        f"/api/v1/employees/{employee.id}/teams/transfer",
        json={"from_team": "Альфа", "to_team": "Бета", "on": "2026-02-15"},
    )
    assert r.status_code == 200, r.text
    rows = {x["team"]: x for x in r.json()}
    assert rows["Альфа"]["left_at"] == "2026-02-15"
    assert rows["Бета"]["joined_at"] == "2026-02-15"
    assert rows["Бета"]["is_primary"] is True


def test_transfer_unknown_team_404(client, employee):
    """Перевод из команды, где человек не состоит."""
    r = client.post(
        f"/api/v1/employees/{employee.id}/teams/transfer",
        json={"from_team": "Гамма", "to_team": "Бета", "on": "2026-02-15"},
    )
    assert r.status_code == 404, r.text
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/test_api_employees_membership_periods.py -v`
Expected: FAIL — 404/405 на `/left-at` и `/transfer`

- [ ] **Step 3: Расширить API**

В `app/api/endpoints/employees.py`:

Добавить `left_at` в `EmployeeTeamItem` (строки 22–27):

```python
class EmployeeTeamItem(BaseModel):
    team: str
    is_primary: bool
    joined_at: Optional[date] = None
    left_at: Optional[date] = None

    model_config = {"from_attributes": True}
```

Заменить обработчик `patch_joined_at` (строки 324–336), добавив 422 на нарушение периода:

```python
@router.patch("/{employee_id}/teams/{team}/joined-at", response_model=EmployeeTeamItem)
def patch_joined_at(
    employee_id: str,
    team: str,
    payload: JoinedAtPayload,
    db: Session = Depends(get_db),
):
    """Установить дату вступления сотрудника в команду."""
    try:
        row = EmployeeTeamService(db).set_joined_at(employee_id, team, payload.joined_at)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    return EmployeeTeamItem.model_validate(row)
```

Добавить в конец файла:

```python
class LeftAtPayload(BaseModel):
    left_at: Optional[date] = None


@router.patch("/{employee_id}/teams/{team}/left-at", response_model=EmployeeTeamItem)
def patch_left_at(
    employee_id: str,
    team: str,
    payload: LeftAtPayload,
    db: Session = Depends(get_db),
):
    """Установить дату выбытия сотрудника из команды."""
    try:
        row = EmployeeTeamService(db).set_left_at(employee_id, team, payload.left_at)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    return EmployeeTeamItem.model_validate(row)


class TransferRequest(BaseModel):
    from_team: str
    to_team: str
    on: date


@router.post("/{employee_id}/teams/transfer", response_model=List[EmployeeTeamItem])
def post_transfer(
    employee_id: str,
    req: TransferRequest,
    db: Session = Depends(get_db),
):
    """Перевести сотрудника в другую команду с указанной даты."""
    emp = db.query(Employee).filter(Employee.id == employee_id).one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    svc = EmployeeTeamService(db)
    try:
        svc.transfer(employee_id, from_team=req.from_team, to_team=req.to_team, on=req.on)
    except ValueError as e:
        msg = str(e)
        if "не найдено" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    rows = svc.list_teams(employee_id)
    return [EmployeeTeamItem.model_validate(r) for r in rows]
```

Также добавить `joined_at` в `AddTeamRequest` — найти класс `AddTeamRequest` в файле и дописать поле:

```python
    joined_at: Optional[date] = None
```

и передать его в `post_team` (строка 265):

```python
    row = EmployeeTeamService(db).add_team(
        employee_id, req.team, is_primary=req.is_primary, joined_at=req.joined_at,
    )
```

- [ ] **Step 4: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/test_api_employees_membership_periods.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/employees.py tests/test_api_employees_membership_periods.py
git commit -m "feat(api): даты выбытия и перевод между командами"
```

---

### Task 5: Ресурс квартала считает только дни участия

**Files:**
- Modify: `app/services/resource_base_service.py:124-135, 194-247, 274-285, 336-416`
- Test: `tests/test_membership_periods_resource.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_membership_periods_resource.py`:

```python
"""Ресурс квартала при выбытии/входе в середине квартала."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Employee, EmployeeTeam, PlanningScenario
from app.services.resource_base_service import ResourceBaseService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _setup(db, joined=None, left=None):
    emp = Employee(
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(
        employee_id=emp.id, team="Альфа", is_primary=True,
        joined_at=joined, left_at=left,
    ))
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db.add(scenario)
    db.commit()
    return emp, scenario


def test_full_quarter_baseline(db_session):
    """Без дат — полный квартал (рабочие дни × 8ч)."""
    emp, scenario = _setup(db_session)
    base = ResourceBaseService(db_session).compute(scenario)
    assert base.role_totals["dev"] > 0
    return base.role_totals["dev"]


def test_departure_mid_quarter_reduces_hours(db_session):
    """Выбытие 15 февраля срезает часы с 15 февраля включительно."""
    emp, scenario = _setup(db_session, left=date(2026, 2, 15))
    base = ResourceBaseService(db_session).compute(scenario)

    days = {d.date for d in base.employees[0].days}
    assert date(2026, 2, 13) in days       # пятница до выбытия
    assert date(2026, 2, 16) not in days   # понедельник после
    assert all(d < date(2026, 2, 15) for d in days)


def test_join_mid_quarter(db_session):
    """Вход 15 февраля — до этой даты часов нет."""
    emp, scenario = _setup(db_session, joined=date(2026, 2, 15))
    base = ResourceBaseService(db_session).compute(scenario)

    days = {d.date for d in base.employees[0].days}
    assert all(d >= date(2026, 2, 15) for d in days)
    assert date(2026, 1, 20) not in days


def test_two_periods_with_gap(db_session):
    """Два периода: считаются оба, разрыв — нет."""
    emp = Employee(
        jira_account_id="acc-2", display_name="Петров П.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True,
                     joined_at=date(2026, 1, 1), left_at=date(2026, 2, 1)),
        EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=False,
                     joined_at=date(2026, 3, 1), left_at=None),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    days = {d.date for d in base.employees[0].days}
    assert date(2026, 1, 15) in days
    assert date(2026, 2, 10) not in days   # разрыв
    assert date(2026, 3, 10) in days


def test_summary_gross_respects_membership(db_session):
    """Сводка: брутто и календарные часы тоже режутся датами."""
    emp, scenario = _setup(db_session, left=date(2026, 2, 15))
    svc = ResourceBaseService(db_session)
    summary = svc.compute_summary(scenario)

    emp2, scenario2 = _setup(db_session)   # второй сотрудник без дат — контроль
    full = svc.compute_summary(scenario2)

    assert summary.gross_by_role["dev"] < full.gross_by_role["dev"]
    assert summary.calendar_gross_by_role["dev"] < full.calendar_gross_by_role["dev"]
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/test_membership_periods_resource.py -v`
Expected: FAIL — `test_departure_mid_quarter_reduces_hours` падает, т.к. дни после выбытия всё ещё в матрице.

- [ ] **Step 3: Учесть периоды в `ResourceBaseService`**

В `app/services/resource_base_service.py` добавить импорт:

```python
from app.services import team_membership as tm
```

В `compute` заменить блок «сотрудники команды» (строки 124–135) на:

```python
        # --- сотрудники команды (все, кто пересёкся с кварталом) ---
        # period_end — исключающая граница, для member_intervals нужна включающая
        last_day = period_end - timedelta(days=1)
        intervals = tm.member_intervals(self.db, [team], period_start, last_day)
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(list(intervals.keys())), Employee.is_active == True)  # noqa: E712
            .all()
        )
```

В цикле по сотрудникам (после `abs_ranges`, перед `while cur < period_end`) добавить:

```python
            emp_intervals = intervals.get(e.id, [])
```

И внутри цикла по дням — сразу после проверки `if norm <= 0.0`, до проверки отсутствия:

```python
                if not tm.day_in_intervals(cur, emp_intervals):
                    cur += timedelta(days=1)
                    continue
```

В `compute_summary` заменить блок «сотрудники команды» (строки 274–285) точно так же:

```python
        last_day = period_end - timedelta(days=1)
        intervals = tm.member_intervals(self.db, [team], period_start, last_day)
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(list(intervals.keys())), Employee.is_active == True)  # noqa: E712
            .all()
        )
```

В блоке «брутто: производственный календарь» (строки 336–346) — считать только дни участия:

```python
        calendar_gross_by_role: dict[str, float] = {}
        for e in employees:
            emp_intervals = intervals.get(e.id, [])
            total_cal = 0.0
            cur = period_start
            while cur < period_end:
                if tm.day_in_intervals(cur, emp_intervals):
                    total_cal += day_hours(cur)
                cur += timedelta(days=1)
            if e.role:
                calendar_gross_by_role[e.role] = (
                    calendar_gross_by_role.get(e.role, 0.0) + round(total_cal, 2)
                )
```

В блоке «валовые часы по сотрудникам» (строки 353–375) — добавить проверку дня:

```python
            total = 0.0
            emp_intervals = intervals.get(e.id, [])
            cur = period_start
            while cur < period_end:
                norm = day_hours(cur)
                if norm > 0 and tm.day_in_intervals(cur, emp_intervals):
                    on_absence = any(a.start_date <= cur <= a.end_date for a in abs_ranges)
                    if not on_absence:
                        total += norm
                cur += timedelta(days=1)
```

В блоке «дни отсутствия по сотрудникам» (строки 381–416) — считать отсутствия только за дни участия:

```python
        for e in employees:
            emp_intervals = intervals.get(e.id, [])
            abs_ranges = (
                self.db.query(Absence)
                .filter(
                    Absence.employee_id == e.id,
                    Absence.start_date < period_end,
                    Absence.end_date >= period_start,
                )
                .all()
            )
            planned_days = 0.0
            unplanned_days = 0.0
            cur = period_start
            while cur < period_end:
                if day_hours(cur) > 0 and tm.day_in_intervals(cur, emp_intervals):
```

(остальное тело цикла без изменений)

- [ ] **Step 4: Запустить тест — проходит**

Run: `py -3.10 -m pytest tests/test_membership_periods_resource.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Прогнать смежные тесты ресурса**

Run: `py -3.10 -m pytest tests/test_resource_base_service.py tests/test_api_planning_resource.py tests/test_api_planning_summary.py -v`
Expected: PASS — все существующие участия без дат, поведение не меняется.

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_base_service.py tests/test_membership_periods_resource.py
git commit -m "feat(planning): ресурс квартала считает только дни участия в команде"
```

---

### Task 6: Снимок утверждения и расхождение по составу

**Files:**
- Modify: `app/services/snapshot_writer.py:79-108, 228-343, 345-450, 528-570`
- Modify: `app/api/endpoints/planning.py:704-754, 849-1000`
- Modify: `app/schemas/capacity_diff.py`
- Test: `tests/test_membership_periods_snapshot.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_membership_periods_snapshot.py`:

```python
"""Снимок утверждения и расхождение состава после выбытия."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee, EmployeeTeam, ProductionCalendarDay


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_departure_after_approval_shows_drift(client, db_session):
    """Выбытие после утверждения → расхождение видно, слепок не изменился."""
    emp = Employee(
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    membership = EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True)
    db_session.add(membership)
    db_session.commit()

    r = client.post("/api/v1/planning/scenarios", json={
        "name": "Q1", "year": 2026, "quarter": 1, "team": "Альфа",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    # До выбытия расхождения нет
    r = client.get(f"/api/v1/planning/scenarios/{sid}/capacity-diff")
    assert r.status_code == 200, r.text
    assert r.json()["has_changes"] is False

    # Выбытие в середине квартала
    r = client.patch(
        f"/api/v1/employees/{emp.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-15"},
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/planning/scenarios/{sid}/capacity-diff")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_changes"] is True
    changed = body["changed_employees"][0]
    assert changed["employee_id"] == emp.id
    assert changed["left_team_at"] == "2026-02-15"
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/test_membership_periods_snapshot.py -v`
Expected: FAIL — `has_changes` остаётся `False`, ключа `left_team_at` нет.

- [ ] **Step 3: Периоды в снимке**

В `app/services/snapshot_writer.py` добавить импорт:

```python
from app.services import team_membership as tm
```

Заменить membership-запрос в `write_team_snapshot` (строки 89–97) на выборку по пересечению с кварталом:

```python
        emp_ids = tm.members_overlapping(self.db, [scenario.team], start, end)
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(list(emp_ids)), Employee.is_active == True)  # noqa: E712
            .all()
        )
```

(переменные `start`/`end` — границы квартала; если в методе их нет, получить через тот же `_quarter_bounds`, что используется в `write_capacity_snapshot`)

Ту же замену сделать в `write_capacity_snapshot` (строки 244–252), `write_norm_snapshot` (строки 376–384) и `write_allocation_breakdown` (строки 559–567) — все четыре места должны брать один и тот же состав.

В `write_capacity_snapshot` часы за месяц дополнительно прорезаются днями участия. После получения `mc = capacity_svc.monthly_capacity(...)` (строка ~313) домножить на долю дней участия в месяце:

```python
                # Доля рабочих дней месяца, когда сотрудник был в команде.
                month_start = date(year, month, 1)
                month_end = date(
                    year + (1 if month == 12 else 0),
                    1 if month == 12 else month + 1,
                    1,
                ) - timedelta(days=1)
                emp_intervals = tm.member_intervals(
                    self.db, [scenario.team], month_start, month_end
                ).get(emp.id, [])
                total_days = (month_end - month_start).days + 1
                member_days = sum(
                    (hi - lo).days + 1 for lo, hi in emp_intervals
                )
                share = 0.0 if total_days == 0 else min(1.0, member_days / total_days)
```

и применить `share` к `norm_hours`, `available_hours`, `gross_hours`, `absence_hours`, `mandatory_hours`, `project_hours` при записи строки снимка (умножить каждое значение на `share`, округлить до 2).

Добавить импорты `date`, `timedelta` в файл, если их там нет.

- [ ] **Step 4: Расхождение по составу в `/capacity-diff`**

В `app/schemas/capacity_diff.py` добавить поле в `EmployeeDiff`:

```python
    left_team_at: Optional[date] = None
```

(добавить `from datetime import date` и `Optional`, если их нет)

В `app/api/endpoints/planning.py`, в `get_capacity_diff` (строка 850):

Добавить импорт вверху файла:

```python
from app.services import team_membership as tm
```

После вычисления `quarter_start` / `quarter_end` (строки ~896–898) добавить:

```python
    # Состав на момент утверждения vs сейчас: кто выбыл из команды.
    left_dates: dict[str, date_t] = {}
    if scenario.team:
        current_intervals = tm.member_intervals(
            db, [scenario.team], quarter_start, quarter_end
        )
        for emp_id in emp_ids:
            spans = current_intervals.get(emp_id)
            if not spans:
                # Выбыл до начала квартала — считаем датой выбытия начало квартала.
                left_dates[emp_id] = quarter_start
                continue
            last_end = spans[-1][1]
            if last_end < quarter_end:
                left_dates[emp_id] = last_end + timedelta(days=1)
```

(добавить `from datetime import timedelta` рядом с существующим импортом `date as date_t`)

В цикле по сотрудникам, там где формируется `EmployeeDiff`, прокинуть поле и не отбрасывать сотрудника без изменений по отсутствиям:

```python
        left_at = left_dates.get(emp_id)
        if month_diffs or left_at:
            changed_employees.append(EmployeeDiff(
                employee_id=emp_id,
                display_name=employees[emp_id].display_name if emp_id in employees else "—",
                month_diffs=month_diffs,
                left_team_at=left_at,
            ))
```

(остальные поля `EmployeeDiff` оставить как в текущем коде — здесь показаны только добавляемые; при сборке смотреть фактический конструктор в файле)

Так как `write_capacity_snapshot` теперь режет часы по участию, помесячные дельты и так покажут падение — поле `left_team_at` даёт человеку причину, а не только цифру.

- [ ] **Step 5: Запустить тест — проходит**

Run: `py -3.10 -m pytest tests/test_membership_periods_snapshot.py -v`
Expected: PASS

- [ ] **Step 6: Прогнать тесты снимков**

Run: `py -3.10 -m pytest tests/test_snapshot_writer.py tests/test_snapshot_writer_external_qa.py tests/test_snapshot_writer_breakdown.py tests/test_capacity_snapshot.py tests/test_scenario_revision_history.py -v`
Expected: PASS — участия без дат дают `share = 1.0`, цифры не меняются.

- [ ] **Step 7: Commit**

```bash
git add app/services/snapshot_writer.py app/api/endpoints/planning.py app/schemas/capacity_diff.py tests/test_membership_periods_snapshot.py
git commit -m "feat(planning): снимок и расхождение утверждённого учитывают выбытие"
```

---

### Task 7: Факт и аналитика — списание попадает в команду по дате

**Files:**
- Modify: `app/services/team_membership.py` (добавить корреляцию по дате списания)
- Modify: `app/services/analytics_service.py:104-140, 361-362, 875-895, 1266-1272, 1322-1329, 1460-1461`
- Modify: `app/services/executive_dashboard_service.py:107-135, 534-535`
- Modify: `app/services/work_type_report_service.py:505-506`
- Test: `tests/test_membership_periods_facts.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_membership_periods_facts.py`:

```python
"""Списание попадает в команду только за дни участия."""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Employee, EmployeeTeam, Issue, Project, Worklog
from app.services.analytics_service import AnalyticsService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def data(db_session):
    emp = Employee(
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(
        employee_id=emp.id, team="Альфа", is_primary=True,
        joined_at=date(2026, 1, 1), left_at=date(2026, 2, 15),
    ))
    project = Project(jira_id="10000", key="PRJ", name="Проект")
    db_session.add(project)
    db_session.flush()
    issue = Issue(
        jira_id="20000", jira_key="PRJ-1", project_id=project.id,
        summary="Задача", issue_type="Task", status="Done",
        include_in_analysis=True,
    )
    db_session.add(issue)
    db_session.flush()
    db_session.add_all([
        Worklog(
            jira_id="w1", issue_id=issue.id, employee_id=emp.id,
            time_spent_seconds=8 * 3600,
            started_at=datetime(2026, 1, 20, 10, 0),
        ),
        Worklog(
            jira_id="w2", issue_id=issue.id, employee_id=emp.id,
            time_spent_seconds=8 * 3600,
            started_at=datetime(2026, 3, 10, 10, 0),
        ),
    ])
    db_session.commit()
    return emp


def test_worklog_before_departure_counts(db_session, data):
    """Списание до выбытия — в команде."""
    svc = AnalyticsService(db_session)
    rows = svc.get_hours_by_employee(
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        teams=["Альфа"],
    )
    assert any(r.employee_id == data.id and r.hours > 0 for r in rows)


def test_worklog_after_departure_excluded(db_session, data):
    """Списание после выбытия — не в команде."""
    svc = AnalyticsService(db_session)
    rows = svc.get_hours_by_employee(
        start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
        teams=["Альфа"],
    )
    assert all(r.hours == 0 for r in rows if r.employee_id == data.id) or not rows
```

> При сборке уточнить фактическую сигнатуру `AnalyticsService.get_hours_by_employee` (аргументы и форму строк ответа) и привести вызовы теста к ней — метод есть в `app/services/analytics_service.py`, менять его контракт не требуется.

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/test_membership_periods_facts.py -v`
Expected: FAIL — `test_worklog_after_departure_excluded`, мартовское списание всё ещё в команде.

- [ ] **Step 3: Добавить корреляцию по дате списания в helper**

Дописать в `app/services/team_membership.py`:

```python
from sqlalchemy import exists


def membership_on_column_exists(teams: Sequence[str], employee_col, date_col):
    """EXISTS-условие «сотрудник был в одной из команд на дату строки».

    ``employee_col`` — колонка с id сотрудника (например ``Worklog.employee_id``),
    ``date_col`` — колонка с датой события (``Worklog.started_at``).

    Сравнение Date с DateTime корректно и в SQLite (лексикографически по ISO),
    и в PostgreSQL (неявный каст даты к полуночи): день ``left_at`` уже НЕ
    засчитывается, потому что ``left_at > started_at`` ложно для любого времени
    внутри этого дня.
    """
    return exists().where(
        EmployeeTeam.employee_id == employee_col,
        EmployeeTeam.team.in_(list(teams)),
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= date_col),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > date_col),
    )


def has_any_membership_on(employee_col, date_col):
    """EXISTS-условие «на эту дату сотрудник состоял хоть в какой-то команде».

    Нужно для ветки «Без команды»: без даты выбывший задним числом становился бы
    «без команды» за всю историю.
    """
    return exists().where(
        EmployeeTeam.employee_id == employee_col,
        or_(EmployeeTeam.joined_at.is_(None), EmployeeTeam.joined_at <= date_col),
        or_(EmployeeTeam.left_at.is_(None), EmployeeTeam.left_at > date_col),
    )
```

- [ ] **Step 4: Перевести фильтры факта на корреляцию**

В `app/services/analytics_service.py`:

- строки 128–137 (`_apply_team_filter`, worklog-ветка): заменить подзапрос `select(EmployeeTeam.employee_id).where(EmployeeTeam.team.in_(named_teams))` на `tm.membership_on_column_exists(named_teams, Worklog.employee_id, Worklog.started_at)`; ветку `NO_TEAM` (`~exists().where(EmployeeTeam.employee_id == Worklog.employee_id)`) — на `~tm.has_any_membership_on(Worklog.employee_id, Worklog.started_at)`.
- строки 1266–1272 (`get_dashboard_categories`): та же замена.
- строки 1322–1329 (`_employees_last_worklog`): ростер «кто в команде сейчас» — заменить подзапрос на `tm.members_on(self.db, named_teams, date.today())`; ветку `NO_TEAM` — на `~tm.has_any_membership_on(Employee.id, func.now())`.
- строки 361–362 (`get_dashboard_projects`) и 875–876 (`get_dashboard_norm_work`): роcтер по пересечению — `tm.members_overlapping(self.db, teams, period_start, period_end)`.
- строки 894–895 и 1460–1461 (`emp_teams_all` / `emp_primary`): `emp_teams_all` строить из записей, пересекающихся с периодом (добавить в запрос `*tm.overlaps_clause(period_start, period_end)`); `emp_primary` — через `tm.primary_team_on(self.db, emp_id, period_end)`.

В `app/services/executive_dashboard_service.py`:
- строки 128–129 (`_apply_team_filter`): `tm.membership_on_column_exists(teams, Worklog.employee_id, Worklog.started_at)`.
- строки 534–535 (`_capacity_by_role`): `tm.members_overlapping(self.db, teams, sdt.date(), edt.date())`.

В `app/services/work_type_report_service.py`:
- строки 505–506: `tm.membership_on_column_exists(teams, Worklog.employee_id, Worklog.started_at)`.

Во все три файла добавить `from app.services import team_membership as tm`.

- [ ] **Step 5: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/test_membership_periods_facts.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Прогнать аналитику целиком**

Run: `py -3.10 -m pytest tests/test_analytics_report.py tests/test_analytics_pct_in_group.py tests/test_dashboard_endpoints.py tests/test_norm_work_cross_team.py tests/test_norm_work_orphan.py tests/test_executive_dashboard_service.py tests/test_work_type_report_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/team_membership.py app/services/analytics_service.py app/services/executive_dashboard_service.py app/services/work_type_report_service.py tests/test_membership_periods_facts.py
git commit -m "feat(analytics): списание попадает в команду по дате участия"
```

---

### Task 8: Остальные потребители состава — столы, планы, экспорт, ёмкость

**Files:**
- Modify: `app/services/plan_common.py:170-185`
- Modify: `app/services/project_plan_service.py:281, 330-331`
- Modify: `app/services/work_desk_widgets.py:555-580`
- Modify: `app/services/scenario_xlsx_export.py:425-427`
- Modify: `app/services/capacity_service.py:355-365, 565-575`
- Modify: `app/services/hours_balance_service.py:210-230`
- Modify: `app/api/endpoints/analytics.py:189-193`, `app/api/endpoints/capacity.py:319-325`, `app/api/endpoints/planning.py:708-717`, `app/api/endpoints/work_desks.py:44-48, 81-82`
- Test: `tests/services/test_team_membership.py` (дополняем)

- [ ] **Step 1: Написать падающий тест на ключевую точку**

Дописать в `tests/services/test_team_membership.py`:

```python
from app.services.plan_common import team_member_ids


def test_team_member_ids_respects_period(db_session):
    """Состав для планов/столов режется периодом."""
    emp = _emp(db_session, name="Сидоров С.", account="acc-9", role="dev")
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15))
    db_session.commit()

    inside = team_member_ids(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    after = team_member_ids(
        db_session, ["Альфа"], date(2026, 3, 1), date(2026, 3, 31)
    )
    assert emp.id in inside
    assert emp.id not in after
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py -v -k team_member_ids`
Expected: FAIL — `TypeError: team_member_ids() takes 2 positional arguments but 4 were given`

- [ ] **Step 3: Прокинуть период в `plan_common.team_member_ids`**

В `app/services/plan_common.py` заменить сигнатуру и тело (строка 178 и вокруг):

```python
def team_member_ids(
    db: Session,
    teams: Iterable[str],
    period_start: date,
    period_end: date,
) -> set[str]:
    """ID сотрудников команд за период + все QA (пул тестирования общий).

    Период обязателен: без него выбывшие сотрудники задним числом попадали бы
    в планы и рабочие столы прошлых кварталов.
    """
    ids = tm.members_overlapping(db, list(teams), period_start, period_end)
```

(остальное тело — существующее объединение с QA — оставить)

Обновить вызовы:
- `app/services/project_plan_service.py:281` (`_team_ids_for_project`) и `:330-331` (`_team_ids_by_root`) — прокинуть границы квартала, которые уже есть у `get_plan(year, quarter)` / `get_portfolio(year, quarter)`; если границы в методе не вычислены, взять их через существующий `quarter_bounds` из `plan_common`.
- `app/services/work_desk_widgets.py:560-561, 572-574` — заменить прямой join на `tm.members_overlapping(db, teams, q_start, q_end)`; `q_start`/`q_end` уже есть в `_adapter_team_absences`.

- [ ] **Step 4: Остальные точки**

- `app/services/scenario_xlsx_export.py:425-427` → `tm.members_overlapping(self.db, [scenario.team], ctx_start, ctx_end)` (границы квартала из контекста экспорта).
- `app/services/capacity_service.py:358-362` (`team_quarter_capacity`) и `:566-572` (`team_role_capacity`) → роcтер через `tm.members_overlapping(self.db, teams_filter, q_start, q_end)` вместо join по `EmployeeTeam.team`.
- `app/services/hours_balance_service.py:220-226` (`team_start`) → выбирать самый ранний период, пересекающийся с окном: добавить в запрос `*tm.overlaps_clause(period_from, period_to)` и брать `min(joined_at)` среди них.
- `app/api/endpoints/analytics.py:189-193` → `tm.members_overlapping(db, team_ids, resolved_from, resolved_to)`.
- `app/api/endpoints/capacity.py:321-323` → `tm.members_on(db, [team], date.today())` (счётчик «сейчас в команде»).
- `app/api/endpoints/planning.py:710-712` (снимок отсутствий при утверждении) → `tm.members_overlapping(db, [scenario.team], quarter_start, quarter_end)`.
- `app/api/endpoints/work_desks.py:44-48` (`_employee_in_user_teams`) и `:81-82` (`list_desks`) → `tm.members_on(db, teams, date.today())`.

Во все затронутые файлы добавить `from app.services import team_membership as tm` и `from datetime import date`, если отсутствует.

- [ ] **Step 5: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/services/test_team_membership.py tests/test_desk_widgets.py tests/services/test_project_plan_service.py tests/test_projects_plan_endpoints.py tests/test_scenario_xlsx_export.py tests/test_capacity_role.py tests/services/test_hours_balance_service.py tests/test_work_desks_admin_endpoint.py tests/test_desk_public_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/ app/api/endpoints/ tests/services/test_team_membership.py
git commit -m "feat(services): состав команды за период в планах, столах, экспорте и ёмкости"
```

---

### Task 9: График работ — пул исполнителей и конфликт «вне команды»

**Files:**
- Modify: `app/services/resource_planning_service.py:1378-1400, 2566-2600`
- Modify: `app/services/conflict_aggregator.py:129-163`
- Modify: `app/api/endpoints/resource_planning.py:994-998`
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx:15-27`
- Modify: `app/services/sync_service.py:1826-1828`
- Test: `tests/services/test_rp_out_of_team_conflict.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/services/test_rp_out_of_team_conflict.py`:

```python
"""Назначение на сотрудника после выбытия — конфликт."""

from datetime import date

from app.models import PlanConflict
from app.services.resource_planning_service import ResourcePlanningService


def test_assignment_after_departure_creates_conflict(db_session, rp_plan_fixture):
    """Задача стоит на сотруднике, который выбыл раньше её конца."""
    plan, employee, assignment = rp_plan_fixture
    # Сотрудник выбывает в середине окна назначения
    from app.services.employee_team_service import EmployeeTeamService
    EmployeeTeamService(db_session).set_left_at(
        employee.id, plan.team, date(2026, 2, 15)
    )

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    conflicts = (
        db_session.query(PlanConflict)
        .filter(PlanConflict.plan_id == plan.id, PlanConflict.type == "OUT_OF_TEAM")
        .all()
    )
    assert conflicts, "ожидался конфликт OUT_OF_TEAM"
    assert conflicts[0].employee_id == employee.id
```

> При сборке: фикстуру `rp_plan_fixture` собрать по образцу `tests/services/test_rp_pinned_edits.py` — там уже есть готовая сборка плана с сотрудником, командой и назначением на квартал 2026 Q1. Скопировать её в новый файл как локальную фикстуру, окно назначения выставить пересекающим 15 февраля.

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/services/test_rp_out_of_team_conflict.py -v`
Expected: FAIL — конфликтов типа `OUT_OF_TEAM` нет.

- [ ] **Step 3: Пул исполнителей по периоду**

В `app/services/resource_planning_service.py`, `_load_employees` (строки 1378–1400): заменить join по `EmployeeTeam.team == plan.team` на выборку по пересечению с окном плана:

```python
        q_start, q_end = self._quarter_bounds(plan)
        emp_ids = tm.members_overlapping(self.db, [plan.team], q_start, q_end)
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(list(emp_ids)), Employee.is_active == True)  # noqa: E712
            .all()
        )
```

Добавить импорт `from app.services import team_membership as tm`.

- [ ] **Step 4: Новый тип конфликта**

В `_build_conflict_dicts` (строки 2566+) добавить блок после существующих проверок (рядом с `LATE_START`):

```python
        # --- назначение выходит за период участия сотрудника в команде ---
        q_start, q_end = self._quarter_bounds_extended(plan)
        member_spans = tm.member_intervals(self.db, [plan.team], q_start, q_end)
        for a in assignments:
            if not a.employee_id or not a.start_date or not a.end_date:
                continue
            spans = member_spans.get(a.employee_id, [])
            outside = [
                d for d in _iter_days(a.start_date, a.end_date)
                if not tm.day_in_intervals(d, spans)
            ]
            if not outside:
                continue
            detected.append({
                "type": "OUT_OF_TEAM",
                "severity": "critical",
                "employee_id": a.employee_id,
                "assignment_id": a.id,
                "backlog_item_id": a.backlog_item_id,
                "window_start": min(outside),
                "window_end": max(outside),
                "metric_value": float(len(outside)),
                "detection_key": f"OUT_OF_TEAM:{a.id}",
            })
```

Вспомогательная функция (добавить рядом с прочими модульными хелперами файла):

```python
def _iter_days(start: date, end: date):
    """Дни отрезка включительно."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)
```

В `app/services/conflict_aggregator.py`, `_build_message` (строки 129–163) добавить ветку:

```python
    if ctype == "OUT_OF_TEAM":
        return (
            f"Сотрудник вне команды {int(metric_value)} дн. в окне задачи "
            f"({window_start:%d.%m}–{window_end:%d.%m})"
        )
```

(имена переменных привести к тем, что уже используются в этой функции)

В `frontend/src/components/resource-planning/ConflictPanel.tsx` в `TYPE_LABELS` (строки 15–27) добавить:

```ts
  OUT_OF_TEAM: 'Вне команды',
```

- [ ] **Step 5: Загрузка ворклогов берёт всех, кто когда-либо состоял**

В `app/services/sync_service.py:1826-1828` заменить join по команде на:

```python
        emp_ids = tm.members_ever(self.db, list(teams))
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(list(emp_ids)))
            .distinct()
            .all()
        )
```

Добавить импорт `from app.services import team_membership as tm`.

- [ ] **Step 6: Пул строк в Гантте**

В `app/api/endpoints/resource_planning.py:994-998` заменить join на `tm.members_overlapping(db, [plan.team], q_start, q_end)` — `q_start`/`q_end` в функции уже есть.

- [ ] **Step 7: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/services/test_rp_out_of_team_conflict.py tests/test_resource_planning_service.py tests/test_resource_planning_endpoints.py tests/services/test_conflict_aggregator.py tests/test_sync_service_update.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/services/resource_planning_service.py app/services/conflict_aggregator.py app/services/sync_service.py app/api/endpoints/resource_planning.py frontend/src/components/resource-planning/ConflictPanel.tsx tests/services/test_rp_out_of_team_conflict.py
git commit -m "feat(rp): конфликт «вне команды» и пул исполнителей по периоду"
```

---

### Task 10: Общий сотрудник — видимость в ресурсе сценария

**Files:**
- Modify: `app/services/resource_base_service.py:65-95, 194-260`
- Modify: `app/api/endpoints/planning.py` (схема ответа `/resource`)
- Test: `tests/test_membership_periods_shared.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_membership_periods_shared.py`:

```python
"""Общий сотрудник виден в базе ресурса."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Employee, EmployeeTeam, PlanningScenario
from app.services.resource_base_service import ResourceBaseService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_shared_employee_marked(db_session):
    """Сотрудник в двух командах помечен и несёт список чужих команд."""
    shared = Employee(
        jira_account_id="acc-1", display_name="Общий О.",
        is_active=True, role="dev",
    )
    solo = Employee(
        jira_account_id="acc-2", display_name="Только А.",
        is_active=True, role="dev",
    )
    db_session.add_all([shared, solo])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=shared.id, team="Альфа", is_primary=True),
        EmployeeTeam(employee_id=shared.id, team="Бета", is_primary=False),
        EmployeeTeam(employee_id=solo.id, team="Альфа", is_primary=True),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    by_name = {e.display_name: e for e in base.employees}

    assert by_name["Общий О."].shared_with == ["Бета"]
    assert by_name["Только А."].shared_with == []
    # Ресурс НЕ режется — часы у обоих одинаковые
    assert by_name["Общий О."].total_hours == by_name["Только А."].total_hours


def test_shared_hours_committed_elsewhere(db_session):
    """Показывается, сколько часов на общего заложено всеми командами."""
    shared = Employee(
        jira_account_id="acc-1", display_name="Общий О.",
        is_active=True, role="dev",
    )
    db_session.add(shared)
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=shared.id, team="Альфа", is_primary=True),
        EmployeeTeam(employee_id=shared.id, team="Бета", is_primary=False),
    ])
    scenario = PlanningScenario(
        name="Q1", year=2026, quarter=1, team="Альфа", status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    # В двух командах на полную — суммарно вдвое больше календарной нормы
    assert emp.committed_hours_all_teams == pytest.approx(emp.total_hours * 2, rel=0.01)
    assert emp.is_overcommitted is True
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `py -3.10 -m pytest tests/test_membership_periods_shared.py -v`
Expected: FAIL — `AttributeError: 'EmployeeBase' object has no attribute 'shared_with'`

- [ ] **Step 3: Реализовать пометку общего**

В `app/services/resource_base_service.py` расширить `EmployeeBase` (строки 73–81):

```python
@dataclass
class EmployeeBase:
    """Посуточная база ресурса одного сотрудника."""

    employee_id: str
    display_name: str
    role: Optional[str]
    days: list[EmployeeDayHours]
    total_hours: float
    shared_with: list[str]                 # чужие команды за этот квартал
    committed_hours_all_teams: float       # часы, заложенные всеми командами
    is_overcommitted: bool                 # заложено больше календарной нормы
```

В `compute`, перед циклом по сотрудникам:

```python
        shared_map = tm.shared_members(self.db, [team], period_start, last_day)
```

Внутри цикла, при сборке `EmployeeBase`, добавить расчёт (ресурс НЕ режется — только показываем):

```python
            others = shared_map.get(e.id, [])
            # Часы, заложенные всеми командами: своя база + столько же за каждую
            # чужую команду, где сотрудник числится в этом же квартале.
            # Норматива деления нет, поэтому считаем «полный человек в каждой».
            committed = round(total * (1 + len(others)), 2)
            calendar_norm = 0.0
            cur_n = period_start
            while cur_n < period_end:
                if tm.day_in_intervals(cur_n, emp_intervals):
                    calendar_norm += day_hours(cur_n)
                cur_n += timedelta(days=1)
            result_emps.append(
                EmployeeBase(
                    employee_id=e.id,
                    display_name=e.display_name,
                    role=e.role,
                    days=days_out,
                    total_hours=total,
                    shared_with=others,
                    committed_hours_all_teams=committed,
                    is_overcommitted=committed > round(calendar_norm, 2) + 0.01,
                )
            )
```

- [ ] **Step 4: Прокинуть поля в ответ API**

В `app/api/endpoints/planning.py` найти Pydantic-схему ответа `/scenarios/{id}/resource` (класс с полями `employee_id`, `display_name`, `role`, `days`, `total_hours`) и добавить:

```python
    shared_with: list[str] = []
    committed_hours_all_teams: float = 0.0
    is_overcommitted: bool = False
```

- [ ] **Step 5: Запустить тесты — проходят**

Run: `py -3.10 -m pytest tests/test_membership_periods_shared.py tests/test_api_planning_resource.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/resource_base_service.py app/api/endpoints/planning.py tests/test_membership_periods_shared.py
git commit -m "feat(planning): общий сотрудник виден в базе ресурса"
```

---

### Task 11: Правка старых тестов инвариантов

**Files:**
- Modify: `tests/test_employee_team_model.py:19, 41-42`
- Modify: `tests/test_capacity_role.py:205, 208`

- [ ] **Step 1: Прогнать и увидеть падения**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py tests/test_capacity_role.py -v`
Expected: FAIL — тесты, проверяющие уникальность `(сотрудник, команда)` и жёсткий single-primary.

- [ ] **Step 2: Переписать инвариантные тесты под периоды**

В `tests/test_employee_team_model.py` тест, проверяющий `IntegrityError` на повторную пару сотрудник/команда, заменить на проверку запрета пересечения через сервис:

```python
def test_overlapping_periods_rejected(db_session):
    """Повтор пары сотрудник/команда допустим, но периоды не должны пересекаться."""
    import pytest
    from datetime import date

    from app.services.employee_team_service import EmployeeTeamService

    svc = EmployeeTeamService(db_session)
    svc.add_team(employee.id, "Альфа", joined_at=date(2026, 1, 1))
    svc.set_left_at(employee.id, "Альфа", date(2026, 3, 1))
    svc.add_team(employee.id, "Альфа", joined_at=date(2026, 9, 1))   # ок

    with pytest.raises(ValueError, match="пересек"):
        svc.add_team(employee.id, "Альфа", joined_at=date(2026, 2, 1))
```

(`employee` — фикстура сотрудника, уже существующая в этом файле)

Тест single-primary переформулировать как «не более одной основной на дату» — использовать `EmployeeTeamService.add_team(..., is_primary=True, allow_primary_overlap=False)` и ожидать `ValueError` с «основн».

В `tests/test_capacity_role.py:205, 208` — там, где создаются две membership-строки на одну пару, развести их непересекающимися периодами (`joined_at`/`left_at`), либо развести по разным командам, в зависимости от смысла теста.

- [ ] **Step 3: Прогнать — проходят**

Run: `py -3.10 -m pytest tests/test_employee_team_model.py tests/test_capacity_role.py -v`
Expected: PASS

- [ ] **Step 4: Полный прогон backend**

Run: `py -3.10 -m pytest tests/ -q`
Expected: PASS (падения, существовавшие до начала работы, допустимы — сверить с `git stash` прогоном при сомнении)

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: инварианты участия переписаны под периоды"
```

---

### Task 12: Фронт — карточка сотрудника с периодами и переводом

**Files:**
- Modify: `frontend/src/types/api.ts:3-7`
- Modify: `frontend/src/api/employees.ts:34-42`
- Modify: `frontend/src/hooks/useCapacity.ts`
- Create: `frontend/src/components/capacity/TransferTeamModal.tsx`
- Modify: `frontend/src/components/capacity/EmployeeDrawer.tsx:27-178`

- [ ] **Step 1: Типы и API-клиент**

В `frontend/src/types/api.ts` расширить `EmployeeTeamItem` (строки 3–7):

```ts
export interface EmployeeTeamItem {
  team: string;
  is_primary: boolean;
  joined_at?: string | null;
  left_at?: string | null;
}
```

В `frontend/src/api/employees.ts` добавить после `updateMembershipJoinedAt`:

```ts
export const updateMembershipLeftAt = (
  employeeId: string,
  payload: { team: string; left_at: string | null },
) =>
  api.patch<EmployeeTeamItem>(
    `/employees/${employeeId}/teams/${encodeURIComponent(payload.team)}/left-at`,
    { left_at: payload.left_at },
  );

export const transferEmployeeTeam = (
  employeeId: string,
  payload: { from_team: string; to_team: string; on: string },
) =>
  api.post<EmployeeTeamItem[]>(`/employees/${employeeId}/teams/transfer`, payload);
```

- [ ] **Step 2: Хуки**

В `frontend/src/hooks/useCapacity.ts` добавить (рядом с прочими мутациями участия):

```ts
export const useUpdateMembershipLeftAt = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, team, left_at }: {
      employeeId: string; team: string; left_at: string | null;
    }) => updateMembershipLeftAt(employeeId, { team, left_at }),
    onSettled: (_d, _e, vars) => {
      qc.invalidateQueries({ queryKey: ['employee', 'teams', vars.employeeId] });
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
    },
  });
};

export const useTransferEmployeeTeam = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, from_team, to_team, on }: {
      employeeId: string; from_team: string; to_team: string; on: string;
    }) => transferEmployeeTeam(employeeId, { from_team, to_team, on }),
    onSettled: (_d, _e, vars) => {
      qc.invalidateQueries({ queryKey: ['employee', 'teams', vars.employeeId] });
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
    },
  });
};
```

Импорты подтянуть из `../api/employees`.

- [ ] **Step 3: Диалог перевода**

Создать `frontend/src/components/capacity/TransferTeamModal.tsx`:

```tsx
import { Modal, Form, Select, DatePicker, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

import { useTransferEmployeeTeam } from '../../hooks/useCapacity';

const { Text } = Typography;

interface Props {
  open: boolean;
  employeeId: string;
  fromTeam: string;
  availableTeams: string[];
  onClose: () => void;
}

export default function TransferTeamModal({
  open, employeeId, fromTeam, availableTeams, onClose,
}: Props) {
  const [form] = Form.useForm<{ to_team: string; on: Dayjs }>();
  const transfer = useTransferEmployeeTeam();

  const handleOk = async () => {
    const values = await form.validateFields();
    await transfer.mutateAsync({
      employeeId,
      from_team: fromTeam,
      to_team: values.to_team,
      on: values.on.format('YYYY-MM-DD'),
    });
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      open={open}
      title={`Перевести из команды «${fromTeam}»`}
      onOk={handleOk}
      onCancel={onClose}
      okText="Перевести"
      cancelText="Отмена"
      confirmLoading={transfer.isPending}
    >
      <Form form={form} layout="vertical" initialValues={{ on: dayjs() }}>
        <Form.Item
          name="to_team"
          label="Новая команда"
          rules={[{ required: true, message: 'Выберите команду' }]}
        >
          <Select
            showSearch
            options={availableTeams
              .filter((t) => t !== fromTeam)
              .map((t) => ({ value: t, label: t }))}
          />
        </Form.Item>
        <Form.Item
          name="on"
          label="Дата перевода"
          rules={[{ required: true, message: 'Укажите дату' }]}
        >
          <DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} />
        </Form.Item>
        <Text type="secondary">
          Участие в прежней команде закроется этой датой, новое откроется с неё же.
          Часы квартала пересчитаются автоматически.
        </Text>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 4: Периоды в карточке сотрудника**

В `frontend/src/components/capacity/EmployeeDrawer.tsx` в блоке «Членство в командах» (строки 112–160):

- рядом с существующим `DatePicker` «В команде с…» добавить второй — «по…», с `value` из `left_at` и `onChange` через `useUpdateMembershipLeftAt`;
- закрытые периоды (`left_at != null`) рендерить приглушённым цветом с подписью «выбыл DD.MM.YYYY»;
- под списком добавить кнопку «Перевести в другую команду», открывающую `TransferTeamModal` для открытого участия (если открытых участий несколько — кнопка на каждой строке).

Список доступных команд для диалога брать из существующего запроса команд (`/teams`) — он уже используется в `CapacityPage`; прокинуть его в drawer пропсом `availableTeams`.

Локальную инлайновую мутацию `joined_at` (строки 34–43) заменить на новый хук `useUpdateMembershipJoinedAt`, добавив его в `useCapacity.ts` по образцу `useUpdateMembershipLeftAt`.

- [ ] **Step 5: Проверить сборку**

Run: `cd frontend && npm run lint && npm run build`
Expected: без ошибок

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): периоды участия и перевод между командами в карточке"
```

---

### Task 13: Фронт — выбывшие в списках и общий сотрудник в ресурсе

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx:94-117, 139-181, 233-318, 354-359`
- Modify: `frontend/src/types/api.ts:544-559`
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx:251-337`
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx:328-390`

- [ ] **Step 1: Переключатель «показывать выбывших»**

В `frontend/src/pages/CapacityPage.tsx` рядом с существующими переключателями (строки 354–359, там где `ui_capacity_show_fact`) добавить третий, по тому же образцу с сохранением настройки:

```tsx
<Space size={4}>
  <Switch
    size="small"
    checked={showDeparted}
    onChange={(v) => { setShowDeparted(v); saveSetting.mutate({ key: 'ui_capacity_show_departed', value: String(v) }); }}
  />
  <Text type="secondary">Показывать выбывших</Text>
</Space>
```

Состояние `showDeparted` завести по образцу `showFact` (строки 94–117): чтение через `useGenericSetting('ui_capacity_show_departed')`, запись через `useSaveGenericSetting`.

В фильтрации сотрудников (строка 108 и `groupByTeam`, строки 139–181) исключать участия с `left_at`, попавшим в прошлое, когда `showDeparted === false`:

```tsx
const isDeparted = (m: EmployeeTeamItem) =>
  !!m.left_at && dayjs(m.left_at).isBefore(dayjs(), 'day');
```

Выбывшие строки (когда переключатель включён) рендерить приглушённо с тегом «выбыл DD.MM».

- [ ] **Step 2: Типы ресурса**

В `frontend/src/types/api.ts` расширить `ResourceEmployee` (строки 544–559):

```ts
  shared_with?: string[];
  committed_hours_all_teams?: number;
  is_overcommitted?: boolean;
```

- [ ] **Step 3: Метка общего сотрудника**

В `frontend/src/components/planning/PlanningCapacityPanel.tsx`, в строке сотрудника (строки 269–329, имя на 283–285) добавить рядом с именем тег для общего:

```tsx
{!!emp.shared_with?.length && (
  <Tooltip
    title={`Делит время с командами: ${emp.shared_with.join(', ')}. Заложено всеми командами: ${Math.round(emp.committed_hours_all_teams ?? 0)} ч${emp.is_overcommitted ? ' — больше его нормы' : ''}`}
  >
    <Tag color={emp.is_overcommitted ? 'red' : 'blue'} style={{ marginInlineStart: 4 }}>
      общий
    </Tag>
  </Tooltip>
)}
```

Ту же метку добавить в `ScenarioResourceSummary.tsx` в тултипе имён по ролям (строки 328–390) — к имени сотрудника дописывать « · общий», если он есть в списке общих.

- [ ] **Step 4: Проверить сборку**

Run: `cd frontend && npm run lint && npm run build`
Expected: без ошибок

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): выбывшие в списках и метка общего сотрудника"
```

---

### Task 14: Финальная проверка и заметка к релизу

- [ ] **Step 1: Полный backend-прогон**

Run: `py -3.10 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 2: Линтеры**

Run: `ruff check app/ tests/ && mypy app/`
Expected: без новых ошибок

- [ ] **Step 3: Фронт**

Run: `cd frontend && npm run lint && npm run build`
Expected: без ошибок

- [ ] **Step 4: Черновик заметки к релизу**

Добавить запись в ленту «Что нового» через существующий механизм заметок (`app/services/release_note_seed.py` — по образцу последних записей), категории в порядке Новое → Улучшение → Исправление:

- **Новое:** «Движение ресурсов между командами. У участия сотрудника в команде появились даты входа и выбытия. Ресурс квартала считается только за дни, когда человек был в команде. Есть перевод в другую команду одним действием.»
- **Новое:** «Общий сотрудник виден. Если человек числится в нескольких командах, он помечен в базе ресурса, видно чужие команды и сколько часов на него заложено суммарно.»
- **Улучшение:** «Отчёты за прошлые периоды больше не переписываются задним числом при изменении состава команды.»

- [ ] **Step 5: Commit + push**

```bash
git add .
git commit -m "docs(release): заметка про движение ресурсов между командами"
git push origin main
```

---

## Порядок исполнения

Задачи 1→14 строго последовательны: 2 зависит от 1, 3 от 2, далее все расчётные задачи (5–10) опираются на helper из задачи 2. Задачи 12–13 (фронт) требуют задач 4 и 10 (API-поля).

Задачи 5, 7, 8, 9 независимы между собой после задачи 3 — при желании исполняются параллельно разными агентами, но коммитятся по очереди, чтобы не ловить конфликты в `app/services/`.
