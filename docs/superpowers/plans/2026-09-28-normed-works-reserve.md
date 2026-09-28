# Запас нормированных работ + заблокированные периоды — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заблокированные периоды получают вид работ, адресность до сотрудника с приоритетом и действуют в планах других команд; нормированные работы становятся запасом квартала, который честно показывается в «Загрузке по дням», сводке и предупреждениях.

**Architecture:** Два новых модуля чистого чтения: `app/services/scheduled_blocks.py` (кого и в какие дни закрывает период) и `app/services/normed_reserve.py` (запас команды, его расход и раскладка по дням для показа). Планировщик меняется только в одном: заблокированные дни берутся из резолвера (периоды основной команды закрывают день и в чужих планах). Диаграмма получает новые поля и живые предупреждения; фронт — новый слой, сводку и редактор периодов.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2.0, Alembic (batch), pytest; React 19, TypeScript, AntD 6, TanStack Query, Vitest.

**Спека:** [docs/superpowers/specs/2026-09-28-normed-works-reserve-design.md](../specs/2026-09-28-normed-works-reserve-design.md) — читать целиком перед любой задачей.

---

## Общие правила для исполнителей

- Тесты: `py -3.10 -m pytest <пути> -q -p no:cacheprovider`. Полный прогон — `py -3.10 -m pytest tests -q -p no:cacheprovider --ignore=tests/api/test_llm.py` (без сети test_llm зависает).
- Линт: `ruff check app/ tests/`. Фронт: `cd frontend && npx tsc -b && npx eslint <файлы> && npx vitest run <файлы>`.
- **Не коммитить.** Коммиты делает координатор после ревью фазы (параллельные исполнители в одной рабочей копии иначе захватывают чужие файлы).
- Трогать только файлы своей задачи. Докстринги и комментарии — по-русски, в стиле соседнего кода.
- Роль сотрудника — `Employee.role`, это код из реестра `roles` (`dev`, `analyst`, `RP`, `consultant`, `qa`, `other`). В тестах — `role="dev"` и т. п. (фабрика `make_employee` по умолчанию ставит `developer` — передавать роль явно).
- Фабрики тестов: `tests/services/xteam_factory.py` (`make_employee`, `join_team`, `make_plan`, `add_item`, `book`).

## Карта файлов

| Файл | Задача | Что |
|---|---|---|
| `alembic/versions/nw01_normed_reserve.py` | 1 | вид работ у периода, таблица выбора вида у задач других команд, заполнение «Закрытие месяца» |
| `app/models/scheduled_block.py`, `app/models/team_work_type_override.py`, `app/models/__init__.py` | 1 | модели |
| `app/services/cross_team_occupancy.py` | 1 (поле брони), 3 (отпечаток) | `ExternalBooking.backlog_item_id`; блоки в отпечатке |
| `app/services/scheduled_blocks.py` | 2 | резолвер периодов |
| `app/services/resource_planning_service.py` | 3 | `build_availability` на резолвере, отпечатки |
| `app/api/endpoints/resource_planning.py` | 3 (периоды, вызовы), 6 (диаграмма, выбор вида) | |
| `app/services/normed_reserve.py` | 5 | запас и раскладка |
| `frontend/src/components/resource-planning/ScheduledBlocksModal.tsx`, `frontend/src/api/resourcePlanning.ts` (тип периода), `frontend/src/pages/ResourcePlanningPage.tsx` (проп состава) | 4 | редактор периодов |
| `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`, `NormedReserveSummary.tsx` (новый), `ConflictPanel.tsx`, `frontend/src/utils/heatmapFill.ts`, `frontend/src/api/resourcePlanning.ts` (диаграмма), `frontend/src/hooks/useResourcePlanning.ts` | 7 | показ |
| `docs/help/resource-planning.md`, `app/services/CLAUDE.md`, `release_notes/drafts.json` | 8 | справка, заметки |

## Фазы и параллельность

- **Фаза 0** (последовательно, один исполнитель): задачи 1, 2.
- **Фаза 1** (параллельно): задачи 3, 4, 5. Ревью фазы. Коммит «выпуск 1» (задачи 1–4) и коммит сервиса запаса (задача 5).
- **Фаза 2** (параллельно): задачи 6, 7, 8. Ревью. Полный прогон. Коммит, push, черновик «Что нового».

---

### Task 1: Миграция и модели

**Files:**
- Create: `alembic/versions/nw01_normed_reserve.py`
- Create: `app/models/team_work_type_override.py`
- Modify: `app/models/scheduled_block.py`, `app/models/__init__.py`, `app/services/cross_team_occupancy.py` (только поле брони)
- Test: `tests/test_migration_nw01_normed_reserve.py`

- [ ] **Step 1: Тест миграции (падает — ревизии нет)**

```python
"""nw01: вид работ у заблокированного периода и выбор вида у задач других команд."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_month_close_blocks_get_support_work_type(tmp_path):
    url = f"sqlite:///{(tmp_path / 'nw01.db').as_posix()}"
    _alembic(url, "upgrade", "pq07_assignment_opo_part")
    engine = sa.create_engine(url)
    with engine.begin() as c:
        wt = c.execute(sa.text("SELECT id FROM mandatory_work_types WHERE code='support_consult'")).scalar()
        if wt is None:
            wt = "wt-support"
            c.execute(sa.text(
                "INSERT INTO mandatory_work_types (id, code, label, is_active, sort_order, "
                "subtracts_from_pool, is_system, theme_dict_version, created_at, updated_at) "
                "VALUES ('wt-support','support_consult','Сопровождение и консультация',1,3,1,1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        for bid, reason in (("b1", " Закрытие месяца "), ("b2", "Обучение")):
            c.execute(sa.text(
                "INSERT INTO scheduled_blocks (id, team, start_date, end_date, reason, created_at, updated_at) "
                "VALUES (:id, 'ERP', '2026-10-05', '2026-10-07', :r, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                {"id": bid, "r": reason})
    engine.dispose()

    _alembic(url, "upgrade", "head")

    engine = sa.create_engine(url)
    with engine.connect() as c:
        got = dict(c.execute(sa.text("SELECT id, work_type_id FROM scheduled_blocks")).all())
        cols = {x["name"] for x in sa.inspect(c).get_columns("team_work_type_overrides")}
    engine.dispose()
    assert got == {"b1": wt, "b2": None}
    assert {"team", "backlog_item_id", "work_type_id"} <= cols

    _alembic(url, "downgrade", "pq07_assignment_opo_part")
    _alembic(url, "upgrade", "head")
```

- [ ] **Step 2: Запустить — FAIL** (`Can't locate revision` / нет колонки).

Run: `py -3.10 -m pytest tests/test_migration_nw01_normed_reserve.py -q -p no:cacheprovider`

- [ ] **Step 3: Миграция**

```python
"""scheduled_blocks.work_type_id + team_work_type_overrides

Revision ID: nw01_normed_reserve
Revises: pq07_assignment_opo_part
Create Date: 2026-09-28

Заблокированный период — нормированная работа своего вида: он расходует
запас этого вида. Существующие «Закрытие месяца» получают «Сопровождение и
консультация»; остальные остаются без вида (закрывают день, запас не тратят).

Выбор вида работ для задачи другой команды: основная команда исполнителя
указывает, чем для неё считается эта работа (по умолчанию — «Технические
задачи»).

Самодостаточна: не импортирует код приложения. Сравнение причины — в Python:
SQLite lower() не знает кириллицу.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "nw01_normed_reserve"
down_revision: Union[str, None] = "pq07_assignment_opo_part"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONTH_CLOSE = "закрытие месяца"

blocks = sa.table(
    "scheduled_blocks",
    sa.column("id", sa.String),
    sa.column("reason", sa.String),
    sa.column("work_type_id", sa.String),
)
work_types = sa.table("mandatory_work_types", sa.column("id", sa.String), sa.column("code", sa.String))


def upgrade() -> None:
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.add_column(sa.Column("work_type_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_scheduled_blocks_work_type", "mandatory_work_types", ["work_type_id"], ["id"]
        )
    op.create_table(
        "team_work_type_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team", sa.String(200), nullable=False),
        sa.Column(
            "backlog_item_id", sa.String(36),
            sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "work_type_id", sa.String(36),
            sa.ForeignKey("mandatory_work_types.id"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team", "backlog_item_id", name="uq_team_work_type_override"),
    )
    op.create_index("ix_team_work_type_overrides_team", "team_work_type_overrides", ["team"])

    bind = op.get_bind()
    support = bind.execute(
        sa.select(work_types.c.id).where(work_types.c.code == "support_consult")
    ).scalar()
    if support is None:
        return
    for row in bind.execute(sa.select(blocks.c.id, blocks.c.reason)).all():
        if (row.reason or "").strip().lower() == MONTH_CLOSE:
            bind.execute(blocks.update().where(blocks.c.id == row.id).values(work_type_id=support))


def downgrade() -> None:
    op.drop_index("ix_team_work_type_overrides_team", table_name="team_work_type_overrides")
    op.drop_table("team_work_type_overrides")
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.drop_constraint("fk_scheduled_blocks_work_type", type_="foreignkey")
        batch.drop_column("work_type_id")
```

- [ ] **Step 4: Модели**

`app/models/scheduled_block.py` — добавить импорт `ForeignKey` и колонку после `reason`:

```python
    # Вид нормированных работ: период расходует запас этого вида.
    # None — старый период без вида: закрывает день, запас не тратит.
    work_type_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=True
    )
```

`app/models/team_work_type_override.py`:

```python
"""TeamWorkTypeOverride — чем считается задача другой команды для команды исполнителя."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamWorkTypeOverride(Base, TimestampMixin):
    """Вид нормированных работ, которым команда ``team`` считает работу своих
    людей над задачей ``backlog_item_id`` другой команды. Нет строки —
    «Технические задачи»."""

    __tablename__ = "team_work_type_overrides"
    __table_args__ = (
        UniqueConstraint("team", "backlog_item_id", name="uq_team_work_type_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    backlog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False
    )
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False
    )
```

`app/models/__init__.py` — импорт `TeamWorkTypeOverride` рядом с другими и добавить в `__all__`.

- [ ] **Step 5: Поле брони.** В `app/services/cross_team_occupancy.py` в конец dataclass `ExternalBooking` (после полей со значениями по умолчанию) добавить:

```python
    # Задача брони: по ней основная команда человека выбирает вид работ.
    backlog_item_id: Optional[str] = None
```

и в `external_bookings` при создании `ExternalBooking(...)` передать `backlog_item_id=a.backlog_item_id`.

- [ ] **Step 6: Прогон**

Run: `py -3.10 -m pytest tests/test_migration_nw01_normed_reserve.py tests/services/test_cross_team_occupancy.py tests/test_scheduled_block_multi.py -q -p no:cacheprovider` → PASS.
Проверить офлайн-SQL для Postgres: `DATABASE_URL=postgresql://offline:offline@localhost:1/offline py -3.10 -m alembic upgrade pq07_assignment_opo_part:nw01_normed_reserve --sql` — без ошибок (в PowerShell переменную задать через `$env:DATABASE_URL`). Если офлайн-режим падает на `bind.execute(...).scalar()` — обернуть заполнение в `if not context.is_offline_mode():` (`from alembic import context`).

---

### Task 2: Резолвер заблокированных дней

**Files:**
- Create: `app/services/scheduled_blocks.py`
- Test: `tests/services/test_scheduled_blocks.py`

- [ ] **Step 1: Тесты**

```python
"""Кого и в какие дни закрывает заблокированный период."""

from datetime import date

from app.models import MandatoryWorkType, Role, ScheduledBlock, ScheduledBlockEmployee, ScheduledBlockRole
from app.services.scheduled_blocks import resolve_blocked_days
from tests.services.xteam_factory import join_team, make_employee

D = date.fromisoformat


def _wt(db, code="support_consult"):
    w = MandatoryWorkType(code=code, label=code, subtracts_from_pool=True)
    db.add(w)
    db.flush()
    return w


def _role(db, code):
    r = Role(code=code, label=code)
    db.add(r)
    db.flush()
    return r


def _block(db, team, start, end, wt=None, roles=(), employees=(), reason="Закрытие месяца"):
    b = ScheduledBlock(team=team, start_date=D(start), end_date=D(end), reason=reason,
                       work_type_id=wt.id if wt else None)
    b.roles = [ScheduledBlockRole(role_id=r.id) for r in roles]
    b.employees = [ScheduledBlockEmployee(employee_id=e.id) for e in employees]
    db.add(b)
    db.flush()
    return b


def test_employee_block_overrides_role_block_within_month(db_session):
    wt = _wt(db_session)
    analyst = _role(db_session, "analyst")
    ivanov = make_employee(db_session, "Иванов", "ERP", role="analyst")
    petrov = make_employee(db_session, "Петров", "ERP", role="analyst")
    _block(db_session, "ERP", "2026-10-05", "2026-10-07", wt, roles=[analyst])
    _block(db_session, "ERP", "2026-11-05", "2026-11-06", wt, roles=[analyst])
    _block(db_session, "ERP", "2026-10-08", "2026-10-09", wt, employees=[ivanov])

    hits = resolve_blocked_days(db_session, [ivanov, petrov], D("2026-10-01"), D("2026-11-30"), "ERP")

    assert sorted(hits[ivanov.id]) == [D("2026-10-08"), D("2026-10-09"), D("2026-11-05"), D("2026-11-06")]
    assert sorted(hits[petrov.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07"),
                                       D("2026-11-05"), D("2026-11-06")]
    assert hits[petrov.id][D("2026-10-05")].work_type_id == wt.id


def test_role_block_beats_team_block_but_other_types_stay(db_session):
    wt, other = _wt(db_session), _wt(db_session, "organizational")
    dev = _role(db_session, "dev")
    e = make_employee(db_session, "Шутов", "ERP", role="dev")
    _block(db_session, "ERP", "2026-12-07", "2026-12-08", wt)                # вся команда
    _block(db_session, "ERP", "2026-12-10", "2026-12-10", wt, roles=[dev])   # роль
    _block(db_session, "ERP", "2026-12-14", "2026-12-14", other)             # другой вид

    hits = resolve_blocked_days(db_session, [e], D("2026-12-01"), D("2026-12-31"), "ERP")

    assert sorted(hits[e.id]) == [D("2026-12-10"), D("2026-12-14")]


def test_primary_team_block_closes_day_in_other_team_plan(db_session):
    wt = _wt(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    _block(db_session, "ERP", "2026-10-05", "2026-10-07", wt)
    _block(db_session, "Блок", "2026-10-12", "2026-10-12", wt)

    in_block_plan = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок")
    in_erp_plan = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "ERP")

    # В плане «Блока»: периоды основной ERP и периоды самого «Блока» (он там состоит).
    assert sorted(in_block_plan[e.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07"), D("2026-10-12")]
    # В плане ERP период неосновного «Блока» его не закрывает.
    assert sorted(in_erp_plan[e.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07")]
    assert in_block_plan[e.id][D("2026-10-05")].team == "ERP"


def test_borrowed_not_closed_by_plan_team_blocks(db_session):
    e = make_employee(db_session, "Гость", "ERP", role="dev")
    _block(db_session, "Блок", "2026-10-05", "2026-10-05")

    assert resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок") == {}


def test_blocks_without_team_apply_to_everyone_and_untyped_group(db_session):
    e = make_employee(db_session, "Любой", "ERP", role="qa")
    _block(db_session, None, "2026-10-05", "2026-10-05", reason="Субботник")

    hits = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "ERP")

    assert hits[e.id][D("2026-10-05")].work_type_id is None
    assert hits[e.id][D("2026-10-05")].reason == "Субботник"


def test_cells_by_team_skips_own_and_global(db_session):
    from app.services.scheduled_blocks import cells_by_team

    wt = _wt(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    _block(db_session, "ERP", "2026-10-05", "2026-10-05", wt)
    _block(db_session, "Блок", "2026-10-06", "2026-10-06", wt)
    _block(db_session, None, "2026-10-07", "2026-10-07")

    hits = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок")

    assert cells_by_team(hits, exclude_team="Блок") == {"ERP": [(e.id, "2026-10-05")]}
```

- [ ] **Step 2: Запустить — FAIL** (`ModuleNotFoundError`).

Run: `py -3.10 -m pytest tests/services/test_scheduled_blocks.py -q -p no:cacheprovider`

- [ ] **Step 3: Реализация**

```python
"""Заблокированные периоды: кого и в какие дни закрывает период.

Период команды X закрывает день человека, если в этот день он состоит в X
(в планах X) или X — его основная команда (в планах любой команды).
Привлечённого в план X (в X не состоит) периоды X не закрывают. Периоды без
команды — для всех.

Приоритет: вся команда < роль < сотрудник. Для человека, команды периода,
месяца и вида работ действуют только периоды самого точного уровня, который
у него есть в этом месяце. Периоды без вида — своя группа. Периоды разных
команд друг друга не перекрывают.

Чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Employee, Role, ScheduledBlock
from app.services import team_membership as tm

TEAM_LEVEL, ROLE_LEVEL, EMPLOYEE_LEVEL = 0, 1, 2


@dataclass(frozen=True)
class BlockHit:
    """Заблокированный день человека: какой период его закрывает."""

    block_id: str
    team: Optional[str]
    work_type_id: Optional[str]
    reason: str


def _active(periods, team: str, day: date, primary_only: bool) -> bool:
    """Состоит ли человек в ``team`` в этот день (``primary_only`` — и она основная)."""
    return any(
        t == team
        and (is_primary or not primary_only)
        and (joined is None or joined <= day)
        and (left is None or left > day)
        for t, joined, left, is_primary in periods
    )


def resolve_blocked_days(
    db: Session,
    employees: Iterable[Employee],
    start: date,
    end: date,
    plan_team: Optional[str],
) -> Dict[str, Dict[date, BlockHit]]:
    """{сотрудник: {день: период}} — заблокированные дни людей в плане ``plan_team``.

    ``plan_team=None`` — вне плана: только периоды основных команд и общие.
    Четыре запроса на любой объём: периоды участия, периоды, их роли и
    сотрудники (selectinload), коды ролей.
    """
    emps = [e for e in employees if e is not None]
    if not emps or start > end:
        return {}
    membership = tm.membership_rows(db, [e.id for e in emps])
    teams = {t for rows in membership.values() for t, _j, _l, primary in rows if primary}
    if plan_team:
        teams.add(plan_team)
    conds = [ScheduledBlock.team.is_(None)]
    if teams:
        conds.append(ScheduledBlock.team.in_(sorted(teams)))
    blocks = (
        db.execute(
            select(ScheduledBlock)
            .options(selectinload(ScheduledBlock.roles), selectinload(ScheduledBlock.employees))
            .where(or_(*conds), ScheduledBlock.start_date <= end, ScheduledBlock.end_date >= start)
            .order_by(ScheduledBlock.start_date, ScheduledBlock.id)
        )
        .scalars()
        .all()
    )
    if not blocks:
        return {}
    role_ids = {r.role_id for b in blocks for r in b.roles}
    code_of = (
        {
            r.id: (r.code or "").lower()
            for r in db.execute(select(Role).where(Role.id.in_(role_ids))).scalars()
        }
        if role_ids
        else {}
    )
    out: Dict[str, Dict[date, BlockHit]] = {}
    for e in emps:
        periods = membership.get(e.id, [])
        role = (e.role or "").lower()
        # (команда периода, год, месяц, вид) → [(уровень, день, период)]
        groups: Dict[tuple, List[tuple]] = defaultdict(list)
        for b in blocks:
            emp_ids = {x.employee_id for x in b.employees}
            b_roles = {code_of.get(x.role_id, "") for x in b.roles}
            if e.id in emp_ids:
                level = EMPLOYEE_LEVEL
            elif role and role in b_roles:
                level = ROLE_LEVEL
            elif not emp_ids and not b.roles:
                level = TEAM_LEVEL
            else:
                continue
            d = max(b.start_date, start)
            last = min(b.end_date, end)
            while d <= last:
                if b.team is None or _active(
                    periods, b.team, d, primary_only=b.team != plan_team
                ):
                    groups[(b.team, d.year, d.month, b.work_type_id)].append((level, d, b))
                d += timedelta(days=1)
        hits: Dict[date, BlockHit] = {}
        for items in groups.values():
            top = max(level for level, _d, _b in items)
            for level, d, b in items:
                if level == top and d not in hits:
                    hits[d] = BlockHit(b.id, b.team, b.work_type_id, b.reason)
        if hits:
            out[e.id] = hits
    return out


def cells_by_team(
    hits: Dict[str, Dict[date, BlockHit]], exclude_team: Optional[str]
) -> Dict[str, List[tuple[str, str]]]:
    """{команда: [(сотрудник, день ISO)]} — заблокированные дни чужих основных
    команд людей плана, для отпечатка плана (`cross_team_occupancy.fingerprint`).
    Периоды самой команды плана и общие периоды не входят."""
    out: Dict[str, List[tuple[str, str]]] = defaultdict(list)
    for eid, by_day in hits.items():
        for d, hit in by_day.items():
            if hit.team is not None and hit.team != exclude_team:
                out[hit.team].append((eid, d.isoformat()))
    return {t: sorted(cells) for t, cells in out.items()}
```

- [ ] **Step 4: Прогон** — `py -3.10 -m pytest tests/services/test_scheduled_blocks.py -q -p no:cacheprovider` → PASS; `ruff check app/services/scheduled_blocks.py tests/services/test_scheduled_blocks.py`.

---

### Task 3: Периоды в планировщике, отпечатке и API (бэкенд выпуска 1)

**Files:**
- Modify: `app/services/resource_planning_service.py` (`build_availability`, удалить `_block_targets`, `compute_schedule`, `_team_fingerprint`, запись отпечатка после расчёта ≈ стр. 1606)
- Modify: `app/services/cross_team_occupancy.py` (`_team_hashes`, `fingerprint`, `stale_teams`)
- Modify: `app/api/endpoints/resource_planning.py`: раздел `ScheduledBlocks` (схемы ≈ стр. 62–105, эндпоинты ≈ 749–825); загрузка периодов в расшифровке конфликта (≈ 2850–2910) и в расшифровке фазы (≈ 3536–3620); в `get_gantt` — только вызов `stale_teams` (≈ 1571)
- Modify tests: `tests/test_resource_planning_service.py` (тесты `_block_targets` → удалить, их покрывает Task 2)
- Test: `tests/services/test_rp_home_blocks.py`, `tests/api/test_scheduled_blocks_api.py`

- [ ] **Step 1: Тест — план другой команды не ставит часы в заблокированный день основной**

```python
"""Период основной команды закрывает день человека и в плане другой команды."""

import json
from datetime import date, datetime

from app.models import MandatoryWorkType, ResourcePlanAssignment, ScheduledBlock
from app.services import cross_team_occupancy as cto
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, join_team, make_employee, make_plan

D = date.fromisoformat


def test_guest_plan_skips_home_block_days(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопровождение", subtracts_from_pool=True)
    db_session.add(wt)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-12"), end_date=D("2026-01-14"),
                                  reason="Закрытие месяца", work_type_id=wt.id))
    sc, plan = make_plan(db_session, "Блок")
    add_item(db_session, sc, "Задача Блока", dev=80, assignee=e)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    rows = db_session.query(ResourcePlanAssignment).filter_by(plan_id=plan.id, employee_id=e.id).all()
    days = {D(k) for a in rows for k, v in json.loads(a.daily_hours_json or "{}").items() if v > 0}
    assert days, "фаза должна быть размещена"
    assert not days & {D("2026-01-12"), D("2026-01-13"), D("2026-01-14")}


def test_fingerprint_changes_with_home_block():
    b = []
    assert cto.fingerprint(b) == cto.fingerprint(b, {})
    with_block = cto.fingerprint(b, {"ERP": [("e1", "2026-01-12")]})
    assert with_block != cto.fingerprint(b)
    assert cto.stale_teams(cto.fingerprint(b), b, datetime(2026, 1, 1),
                           {"ERP": [("e1", "2026-01-12")]}) == ["ERP"]
```

Если `compute_schedule` в тесте не назначает исполнителя из `assignee` (зависит от правил подбора) — закрепить исполнителя так же, как в `tests/services/test_rp_borrowed_staff.py` / `tests/api/test_rp_cross_team_gantt.py` (посмотреть, как там добиваются назначения гостя), и оставить проверку дней неизменной.

- [ ] **Step 2: Запустить — FAIL** (день 12–14.01 занят; `fingerprint` не принимает второй аргумент).

- [ ] **Step 3: `cross_team_occupancy`** — заблокированные дни в отпечатке:

```python
def _team_hashes(
    bookings: Iterable[ExternalBooking],
    blocked_cells: Optional[Dict[str, List[tuple]]] = None,
) -> Dict[str, str]:
    """{команда: sha256 её броней и заблокированных дней её периодов}.
    ...(старый текст докстринга)...
    Команда без заблокированных дней хэшируется как раньше — старые
    отпечатки планов без периодов чужих команд не устаревают.
    """
    hours: Dict[str, Dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            hours[b.team][(b.employee_id, d.isoformat())] += h
    cells_of = blocked_cells or {}
    out: Dict[str, str] = {}
    for team in set(hours) | set(cells_of):
        rows = sorted(
            (eid, day, round(h, 2))
            for (eid, day), h in hours.get(team, {}).items()
            if round(h, 2) > 0
        )
        cells = sorted(list(c) for c in cells_of.get(team, ()))
        if not rows and not cells:
            continue
        payload = rows if not cells else {"blocked": cells, "hours": rows}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        out[team] = hashlib.sha256(raw).hexdigest()
    return out
```

Проверить, что для `payload = rows` результат байт-в-байт как раньше (`json.dumps(rows, separators=(",", ":"))` — `sort_keys` на список не влияет). `fingerprint(bookings, blocked_cells=None)` и `stale_teams(stored, bookings, computed_at, blocked_cells=None)` передают `blocked_cells` в `_team_hashes`; докстринги дополнить одной фразой.

- [ ] **Step 4: `build_availability` на резолвере**

Сигнатура: `build_availability(self, employees, start, end, blocked=None, team=None, borrowed=None)`. `blocked` — `{employee_id: {date: BlockHit}}` из `scheduled_blocks.resolve_blocked_days`; `None` или пустой — без периодов (старые вызовы с `[]` продолжают работать). Удалить загрузку ролей и цикл по периодам; условие дня: `... or d in blocked_map.get(emp.id, ())`, где `blocked_map = blocked or {}`. Удалить `_block_targets` и импорт `ScheduledBlock`/`Role`, если больше не нужны. Докстринг: «``blocked`` — заблокированные дни (см. `scheduled_blocks`)».

- [ ] **Step 5: Вызовы**

В `compute_schedule` вместо загрузки `ScheduledBlock.team == plan.team`:

```python
        # Заблокированные дни: периоды команды плана у её людей и периоды
        # основной команды каждого человека (закрывают день и в чужих планах).
        blocked = sb.resolve_blocked_days(
            self.db, employees, q_start, q_end_extended, plan.team
        )
        raw_avail = self.build_availability(
            employees, q_start, q_end_extended, blocked,
            team=plan.team, borrowed=borrowed,
        )
```

(`from app.services import scheduled_blocks as sb`.) Везде, где план запоминает `external_fingerprint` после расчёта (≈ стр. 1606) и в `_team_fingerprint`, передавать `sb.cells_by_team(blocked, exclude_team=plan.team)` вторым аргументом `cto.fingerprint`. В `_team_fingerprint` резолвер вызвать для `self._load_employees(plan)` на то же окно. Ранний выход без исполнителей (`cto.fingerprint([])`, ≈ стр. 688) не трогать.

В `get_gantt` (≈ стр. 1571):

```python
            blocked_cells = sb.cells_by_team(
                sb.resolve_blocked_days(db, list(plan_employees), q_start, q_end_ext, plan.team),
                exclude_team=plan.team,
            )
            changed_teams = cto.stale_teams(
                plan.external_fingerprint,
                cto.subtractable(bookings, borrowed),
                plan.computed_at,
                blocked_cells,
            )
```

Расшифровка конфликта (≈ 2850–2910) и расшифровка фазы (≈ 3536–3620): убрать загрузку `ScheduledBlock`, для каждого вызова `build_availability` передавать `sb.resolve_blocked_days(db, <те же сотрудники>, <то же окно>, team)` (у фазы — `plan.team`). `_occupancy_inputs` и `quarter_load_pct` передают `[]` — оставить (ёмкость без периодов).

- [ ] **Step 6: API периодов**

Схемы:

```python
class ScheduledBlockCreate(BaseModel):
    team: Optional[str] = None
    role_ids: List[str] = []
    employee_ids: List[str] = []
    start_date: date
    end_date: date
    reason: str
    work_type_id: str


class ScheduledBlockUpdate(BaseModel):
    team: Optional[str] = None
    role_ids: Optional[List[str]] = None
    employee_ids: Optional[List[str]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None
    work_type_id: Optional[str] = None


class ScheduledBlockOut(BaseModel):
    id: str
    team: Optional[str]
    role_ids: List[str]
    employee_ids: List[str]
    start_date: date
    end_date: date
    reason: str
    work_type_id: Optional[str] = None
    # Подписи для списка: вид работ, роли и сотрудники периода.
    work_type_label: Optional[str] = None
    role_labels: List[str] = []
    employee_names: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}
```

`_block_to_out(block)` → `_blocks_out(db, blocks) -> List[ScheduledBlockOut]`: три запроса на список (роли по id, сотрудники по id, виды работ по id), подписи в порядке названий. Проверка вида работ `_check_work_type(db, work_type_id)`: существует и `subtracts_from_pool=True`, иначе 422 «Выберите вид нормированных работ». В PATCH: если поле передано явно и равно `None` (`"work_type_id" in patch and patch["work_type_id"] is None`) — 422 тем же текстом. Сотрудники периода — любые `Employee.id` (проверять не нужно; UI даёт выбрать только состав команды).

- [ ] **Step 7: Тест API**

```python
"""API заблокированных периодов: вид работ обязателен, подписи в списке."""

from app.models import Employee, MandatoryWorkType, Role


def test_block_crud_with_work_type_and_labels(client, db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопровождение и консультация",
                           subtracts_from_pool=True)
    foreign = MandatoryWorkType(code="other_foreign", label="Прочие / Чужие", subtracts_from_pool=False)
    role = Role(code="analyst", label="Аналитик")
    emp = Employee(display_name="Иванов", jira_account_id="acc-iv", role="analyst")
    db_session.add_all([wt, foreign, role, emp])
    db_session.commit()
    base = {"team": "ERP", "start_date": "2026-10-05", "end_date": "2026-10-07", "reason": "Закрытие месяца"}

    assert client.post("/api/v1/resource-planning/scheduled-blocks", json=base).status_code == 422
    bad = client.post("/api/v1/resource-planning/scheduled-blocks",
                      json={**base, "work_type_id": foreign.id})
    assert bad.status_code == 422
    r = client.post("/api/v1/resource-planning/scheduled-blocks",
                    json={**base, "work_type_id": wt.id, "role_ids": [role.id], "employee_ids": [emp.id]})
    assert r.status_code == 201
    out = r.json()
    assert out["work_type_label"] == "Сопровождение и консультация"
    assert out["role_labels"] == ["Аналитик"]
    assert out["employee_names"] == ["Иванов"]

    listed = client.get("/api/v1/resource-planning/scheduled-blocks", params={"team": "ERP"}).json()
    assert listed[0]["role_labels"] == ["Аналитик"]
    assert client.patch(f"/api/v1/resource-planning/scheduled-blocks/{out['id']}",
                        json={"work_type_id": None}).status_code == 422
    assert client.patch(f"/api/v1/resource-planning/scheduled-blocks/{out['id']}",
                        json={"employee_ids": []}).json()["employee_names"] == []
```

Путь и фикстуры `client`/`db_session` сверить с `tests/api/test_rp_cross_team_gantt.py` (префикс API, авторизация).

- [ ] **Step 8: Прогон** — новые тесты + `tests/services tests/api -k "rp or resource or block or cross_team or gantt"` + `tests/test_resource_planning_service.py` → PASS; `ruff check app/ tests/`.

---

### Task 4: Редактор заблокированных периодов (фронт выпуска 1)

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts` (интерфейс `ScheduledBlock`, функции создания/изменения)
- Modify: `frontend/src/components/resource-planning/ScheduledBlocksModal.tsx`
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx` (проп `members`)
- Test: `frontend/src/utils/scheduledBlocks.test.ts` + `frontend/src/utils/scheduledBlocks.ts` (подпись «Кому»)

Контракт бэкенда — Task 3, шаг 6.

- [ ] **Step 1: Тип**

```ts
export interface ScheduledBlock {
  id: string;
  team: string | null;
  role_ids: string[];
  employee_ids: string[];
  start_date: string;
  end_date: string;
  reason: string;
  work_type_id: string | null;
  work_type_label?: string | null;
  role_labels?: string[];
  employee_names?: string[];
  created_at: string;
}
export type ScheduledBlockInput = Omit<ScheduledBlock, 'id' | 'created_at' | 'work_type_label' | 'role_labels' | 'employee_names'> & { work_type_id: string };
```

`createScheduledBlock(data: ScheduledBlockInput)`, `updateScheduledBlock(id, data: Partial<ScheduledBlockInput>)`. Хуки в `useResourcePlanning.ts` — если у изменения нет хука, добавить `useUpdateScheduledBlock` по образцу `useCreateScheduledBlock` (та же инвалидация).

- [ ] **Step 2: Тест подписи «Кому» (vitest)**

```ts
import { describe, expect, it } from 'vitest';
import { blockAudience } from './scheduledBlocks';

describe('blockAudience', () => {
  it('вся команда, если нет ни ролей, ни сотрудников', () => {
    expect(blockAudience({ role_labels: [], employee_names: [] })).toBe('вся команда');
  });
  it('роли, затем сотрудники', () => {
    expect(blockAudience({ role_labels: ['Аналитик', 'РП'], employee_names: ['Иванов'] }))
      .toBe('Аналитик, РП · Иванов');
  });
});
```

```ts
/** Подпись «Кому» заблокированного периода. */
export function blockAudience(b: { role_labels?: string[]; employee_names?: string[] }): string {
  const roles = (b.role_labels ?? []).join(', ');
  const people = (b.employee_names ?? []).join(', ');
  if (!roles && !people) return 'вся команда';
  return [roles, people].filter(Boolean).join(' · ');
}
```

- [ ] **Step 3: Модалка**

- Проп `members?: { id: string; name: string }[]` — состав команды для выбора сотрудников. На странице передать людей из `gantt.employee_load` без привлечённых (`!is_borrowed`), `{ id: employee_id, name: employee_name ?? '' }`, отсортированных по имени; нет диаграммы — пустой список.
- Форма (layout `vertical` или `inline` с переносом, ширина модалки 820): даты (обязательно), **Вид работ** (`Select`, обязательно; опции — `useMandatoryWorkTypes({ isActive: true })` с `subtracts_from_pool`), **Роли** (`Select mode="multiple"`, необяз.), **Сотрудники** (`Select mode="multiple"` из `members`, `optionFilterProp="label"`, необяз.), **Причина** (обязательно). Подсказка под полями: «Не выбраны роли и сотрудники — период для всей команды. Период сотрудника главнее периода роли в том же месяце и виде работ».
- Таблица: «Даты» (`ДД.ММ–ДД.ММ`), «Кому» (`blockAudience`), «Вид работ» (`work_type_label`, пусто — красный текст «укажите вид работ»), «Причина», действия: «изменить» (`EditOutlined`) и «удалить».
- «Изменить» заполняет форму значениями строки, кнопка становится «Сохранить» + «Отмена»; сохранение — `updateScheduledBlock` со всеми полями формы.
- Ошибки сервера (422) — `message.error(detail ?? 'Ошибка сохранения')`.

- [ ] **Step 4: Прогон** — `cd frontend && npx tsc -b && npx eslint src/components/resource-planning/ScheduledBlocksModal.tsx src/utils/scheduledBlocks.ts src/pages/ResourcePlanningPage.tsx && npx vitest run src/utils/scheduledBlocks.test.ts` → без ошибок.

---

### Task 5: Сервис запаса нормированных работ

**Files:**
- Create: `app/services/normed_reserve.py`
- Test: `tests/services/test_normed_reserve.py`

Зависит от задач 1–2 (модель выбора вида, `BlockHit`, `ExternalBooking.backlog_item_id`).

- [ ] **Step 1: Тесты**

```python
"""Запас нормированных работ команды и раскладка по дням."""

from datetime import date, timedelta

from app.models import (
    MandatoryWorkType, ScenarioRule, ScheduledBlock, TeamWorkTypeOverride,
)
from app.services import normed_reserve as nr
from app.services.scheduled_blocks import BlockHit
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

D = date.fromisoformat
Q = (2026, 1)  # 2026-01-01 … 2026-03-31; календарь без аномалий — 8 ч в будни


def _types(db):
    out = {}
    for i, code in enumerate(["organizational", "support_consult", "minor_change", "technical_tasks"]):
        w = MandatoryWorkType(code=code, label=code, sort_order=i, subtracts_from_pool=True)
        db.add(w)
        out[code] = w
    db.add(MandatoryWorkType(code="other_foreign", label="Прочие", subtracts_from_pool=False))
    db.flush()
    return out


def _rules(db, scenario, types, role="dev"):
    for code, pct in {"organizational": 10, "support_consult": 15, "minor_change": 20,
                      "technical_tasks": 10}.items():
        db.add(ScenarioRule(scenario_id=scenario.id, role=role, work_type_id=types[code].id,
                            percent_of_norm=pct))
    db.flush()


def _weekdays(start, n):
    out, d = [], D(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _erp(db):
    """ERP: два разработчика; P занят в опорном плане «Блока» 180 ч."""
    types = _types(db)
    p = make_employee(db, "Пряничников", "ERP", role="dev")
    s = make_employee(db, "Шутов", "ERP", role="dev")
    join_team(db, p, "Блок")
    sc, _plan = make_plan(db, "ERP")
    _rules(db, sc, types)
    bsc, bplan = make_plan(db, "Блок")
    item = add_item(db, bsc, "OS-92122", dev=180)
    book(db, bplan, item, p, {d: 7.2 for d in _weekdays("2026-01-12", 25)})
    db.commit()
    return types, p, s, item


def test_team_reserve_shared_tech_pool_is_eaten_by_one_person(db_session):
    types, p, s, _item = _erp(db_session)

    r = nr.team_reserve(db_session, "ERP", *Q)

    norm = r.people[p.id].norm
    assert norm == r.people[s.id].norm > 0
    tech = next(x for x in r.roles["dev"] if x.work_type_id == types["technical_tasks"].id)
    assert round(tech.planned, 1) == round(0.10 * 2 * norm, 1)
    assert round(tech.other_teams, 1) == 180.0
    assert tech.remaining == 0.0
    assert round(tech.overuse, 1) == round(180.0 - tech.planned, 1)
    assert types["technical_tasks"].id not in r.people[s.id].share
    assert round(r.people[s.id].undated, 1) == round(0.45 * norm, 1)
    assert [w.hours for w in r.other_team_work] == [180.0]
    assert r.other_team_work[0].work_type_id == types["technical_tasks"].id
    assert r.other_team_work[0].is_manual is False


def test_override_moves_other_team_work_to_chosen_type(db_session):
    types, p, s, item = _erp(db_session)
    db_session.add(TeamWorkTypeOverride(team="ERP", backlog_item_id=item.id,
                                        work_type_id=types["support_consult"].id))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    rows = {x.work_type_id: x for x in r.roles["dev"]}
    assert rows[types["technical_tasks"].id].other_teams == 0.0
    assert round(rows[types["support_consult"].id].other_teams, 1) == 180.0
    assert r.other_team_work[0].is_manual is True


def test_home_block_consumes_its_type_for_the_person(db_session):
    types, p, s, _item = _erp(db_session)
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=types["support_consult"].id))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    support = next(x for x in r.roles["dev"] if x.work_type_id == types["support_consult"].id)
    assert support.blocked == 2 * 3 * 8.0  # оба разработчика, три дня
    assert r.people[p.id].blocked[types["support_consult"].id] == 24.0


def test_team_without_rules_has_no_reserve(db_session):
    make_employee(db_session, "Один", "Пусто", role="dev")
    make_plan(db_session, "Пусто")
    db_session.commit()

    assert nr.team_reserve(db_session, "Пусто", *Q) is None


def test_place_person_residue_then_free_days_then_unplaced():
    days = [D("2026-01-05") + timedelta(days=i) for i in range(5)]  # Пн–Пт
    capacity = {d: 8.0 for d in days}
    own = {days[0]: 7.2, days[1]: 7.2}
    residue = {days[0]: 0.1, days[1]: 0.1}
    reserve = nr.PersonReserve("e", "dev", 40.0, share={"wt": 20.0})
    blocked = {days[4]: BlockHit("b", "ERP", "wt2", "Закрытие месяца")}

    load = nr.place_person(capacity, own, {}, residue, blocked, reserve, {"wt": "Минорные", "wt2": "Сопровождение"})

    assert load.normed_by_day[days[0]] == 0.8 and load.normed_by_day[days[1]] == 0.8
    assert load.normed_by_day[days[4]] == 8.0
    # Доля 20 ч: 1,6 ч — остатки Пн/Вт; 18,4 ч — на свободные Ср/Чт (16 ч), 2,4 ч не поместились.
    assert round(load.normed_by_day[days[2]], 2) == 8.0 and round(load.normed_by_day[days[3]], 2) == 8.0
    assert round(load.unplaced, 2) == 2.4
    assert round(load.normed, 2) == 28.0          # 8 заблокировано + 20 доля
    assert round(load.pct, 1) == round((14.4 + 28.0) / 40 * 100, 1)
    assert load.normed_by_type == {"Сопровождение": 8.0, "Минорные": 20.0}
```

- [ ] **Step 2: Запустить — FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Реализация**

```python
"""Запас нормированных работ команды на квартал и его раскладка по дням.

Нормированные работы — запас времени на квартал по видам работ: процент нормы
по ролям из опорного сценария команды (утверждённый, иначе свежий черновик;
правила роли заменяют правила «для всех ролей»; только виды, которые
уменьшают запас на проекты). Люди запаса — те, у кого команда основная, и
только в эти дни. Норма дня — производственный календарь минус отсутствия;
заблокированные периоды норму не уменьшают: они сами нормированная работа.

Расход с датой: заблокированный период команды с видом работ (весь день) и
работа в опорных планах других команд (вид — выбранный командой для задачи,
иначе «Технические задачи»). Остаток вида делится между людьми роли
пропорционально их норме.

Чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    Employee,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
    TeamWorkTypeOverride,
)
from app.services import cross_team_occupancy as cto
from app.services import scheduled_blocks as sb
from app.services import team_membership as tm
from app.services.plan_common import _quarter_variants, quarter_bounds

DEFAULT_HOURS_PER_DAY = 8.0
# Вид, которым основная команда по умолчанию считает работу своих людей в
# планах других команд.
CROSS_TEAM_WORK_TYPE_CODE = "technical_tasks"
BLOCK_WITHOUT_TYPE = "Заблокировано (вид не указан)"


def reference_scenario(
    db: Session, team: str, year: int, quarter: int
) -> Optional[PlanningScenario]:
    """Опорный сценарий команды на квартал: утверждённый, иначе свежий черновик."""
    rows = (
        db.execute(
            select(PlanningScenario).where(
                PlanningScenario.team == team,
                PlanningScenario.year == year,
                PlanningScenario.quarter.in_(_quarter_variants(quarter)),
                PlanningScenario.status.in_(("approved", "draft")),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    return max(
        rows,
        key=lambda s: (s.status == "approved", s.updated_at or s.created_at or datetime.min, s.id),
    )


def calendar_hours(db: Session, start: date, end: date) -> Dict[date, float]:
    """{рабочий день: часы}: производственный календарь, иначе 8 ч в будни."""
    anomalies = {
        r.date: float(r.hours)
        for r in db.execute(
            select(ProductionCalendarDay).where(
                ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end
            )
        ).scalars()
    }
    out: Dict[date, float] = {}
    d = start
    while d <= end:
        h = anomalies.get(d, DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0)
        if h > 0:
            out[d] = h
        d += timedelta(days=1)
    return out


def absent_days(
    db: Session, employee_ids: Iterable[str], start: date, end: date
) -> Dict[str, set]:
    """{сотрудник: дни отсутствий} внутри окна (конец отсутствия включительно)."""
    ids = list(employee_ids)
    out: Dict[str, set] = defaultdict(set)
    if not ids:
        return out
    for a in db.execute(
        select(Absence).where(
            Absence.employee_id.in_(ids), Absence.start_date <= end, Absence.end_date >= start
        )
    ).scalars():
        d = max(a.start_date, start)
        while d <= min(a.end_date, end):
            out[a.employee_id].add(d)
            d += timedelta(days=1)
    return out


def primary_on(periods, team: Optional[str], day: date) -> bool:
    """Основная ли ``team`` у человека в этот день (``periods`` — из membership_rows)."""
    return any(
        t == team and is_primary and (j is None or j <= day) and (lv is None or lv > day)
        for t, j, lv, is_primary in periods
    )


@dataclass
class WorkTypeReserve:
    """Запас вида работ роли и его расход с датой, часы."""

    work_type_id: str
    label: str
    planned: float = 0.0
    blocked: float = 0.0
    other_teams: float = 0.0

    @property
    def used(self) -> float:
        return self.blocked + self.other_teams

    @property
    def remaining(self) -> float:
        return max(0.0, self.planned - self.used)

    @property
    def overuse(self) -> float:
        return max(0.0, self.used - self.planned)


@dataclass
class PersonReserve:
    """Нормированные работы человека в запасе своей основной команды, часы."""

    employee_id: str
    role: Optional[str]
    norm: float
    blocked: Dict[str, float] = field(default_factory=dict)
    share: Dict[str, float] = field(default_factory=dict)

    @property
    def undated(self) -> float:
        """Доля остатков — нормированные работы без даты."""
        return sum(self.share.values())


@dataclass
class OtherTeamWork:
    """Работа людей команды над задачей другой команды за квартал."""

    backlog_item_id: str
    issue_key: Optional[str]
    title: str
    team: str
    hours: float
    work_type_id: str
    is_manual: bool


@dataclass
class TeamReserve:
    team: str
    scenario_id: str
    scenario_name: str
    roles: Dict[str, List[WorkTypeReserve]]
    people: Dict[str, PersonReserve]
    other_team_work: List[OtherTeamWork]
    # Все виды, уменьшающие запас на проекты: {id: подпись} — для выбора.
    labels: Dict[str, str]


def team_reserve(db: Session, team: str, year: int, quarter: int) -> Optional[TeamReserve]:
    """Запас нормированных работ команды на квартал; None — у команды нет правил.

    Запросов — константа на команду: сценарий, виды, правила, календарь,
    состав, периоды участия, отсутствия, сотрудники, периоды (резолвер),
    выбор видов, брони других команд.
    """
    scenario = reference_scenario(db, team, year, quarter)
    if scenario is None:
        return None
    types = {
        w.id: w
        for w in db.execute(
            select(MandatoryWorkType).where(MandatoryWorkType.subtracts_from_pool == True)  # noqa: E712
        ).scalars()
    }
    percents: Dict[Optional[str], Dict[str, float]] = defaultdict(dict)
    for r in db.execute(select(ScenarioRule).where(ScenarioRule.scenario_id == scenario.id)).scalars():
        if r.work_type_id in types and r.percent_of_norm:
            percents[r.role][r.work_type_id] = (
                percents[r.role].get(r.work_type_id, 0.0) + float(r.percent_of_norm)
            )
    if not percents:
        return None

    def pct_of(role: Optional[str]) -> Dict[str, float]:
        return percents[role] if role and role in percents else percents.get(None, {})

    q_start, q_end = quarter_bounds(year, quarter)
    cal = calendar_hours(db, q_start, q_end)
    ids = sorted(tm.members_overlapping(db, [team], q_start, q_end))
    membership = tm.membership_rows(db, ids)
    absent = absent_days(db, ids, q_start, q_end)
    norm_day: Dict[str, Dict[date, float]] = {}
    for eid in ids:
        days = {
            d: h
            for d, h in cal.items()
            if d not in absent.get(eid, ()) and primary_on(membership.get(eid, ()), team, d)
        }
        if days:
            norm_day[eid] = days
    employees = (
        {e.id: e for e in db.execute(select(Employee).where(Employee.id.in_(list(norm_day)))).scalars()}
        if norm_day
        else {}
    )

    rows: Dict[tuple, WorkTypeReserve] = {}

    def row(role: str, wt: str) -> WorkTypeReserve:
        if (role, wt) not in rows:
            rows[(role, wt)] = WorkTypeReserve(wt, types[wt].label if wt in types else wt)
        return rows[(role, wt)]

    people: Dict[str, PersonReserve] = {}
    for eid, days in norm_day.items():
        e = employees.get(eid)
        if e is None:
            continue
        norm = sum(days.values())
        people[eid] = PersonReserve(eid, e.role, norm)
        for wt, pct in pct_of(e.role).items():
            row(e.role or "", wt).planned += norm * pct / 100.0

    # Заблокированные периоды команды — весь день, в дни, когда она основная.
    hits = sb.resolve_blocked_days(db, [employees[i] for i in people], q_start, q_end, team)
    for eid, by_day in hits.items():
        p = people[eid]
        for d, hit in by_day.items():
            if hit.team != team or not hit.work_type_id or d not in norm_day[eid]:
                continue
            h = norm_day[eid][d]
            p.blocked[hit.work_type_id] = p.blocked.get(hit.work_type_id, 0.0) + h
            row(p.role or "", hit.work_type_id).blocked += h

    # Работа в опорных планах других команд.
    default_wt = next((w.id for w in types.values() if w.code == CROSS_TEAM_WORK_TYPE_CODE), None)
    overrides = {
        o.backlog_item_id: o.work_type_id
        for o in db.execute(
            select(TeamWorkTypeOverride).where(TeamWorkTypeOverride.team == team)
        ).scalars()
        if o.work_type_id in types
    }
    work: Dict[tuple, OtherTeamWork] = {}
    for b in cto.external_bookings(
        db, team=team, year=year, quarter=quarter,
        employee_ids=list(people), start=q_start, end=q_end,
    ):
        days = norm_day.get(b.employee_id, {})
        hours = sum(h for d, h in b.daily_hours.items() if d in days)
        manual = b.backlog_item_id in overrides
        wt = overrides.get(b.backlog_item_id) or default_wt
        if hours <= 0 or wt is None:
            continue
        row(people[b.employee_id].role or "", wt).other_teams += hours
        key = (b.backlog_item_id, b.team)
        if key not in work:
            work[key] = OtherTeamWork(
                b.backlog_item_id or "", b.issue_key, b.title, b.team, 0.0, wt, manual
            )
        work[key].hours += hours

    # Остаток вида — людям роли пропорционально норме.
    norm_by_role: Dict[str, float] = defaultdict(float)
    for p in people.values():
        norm_by_role[p.role or ""] += p.norm
    for (role, wt), r in rows.items():
        if r.remaining <= 0 or norm_by_role[role] <= 0:
            continue
        for p in people.values():
            if (p.role or "") == role:
                p.share[wt] = r.remaining * p.norm / norm_by_role[role]

    def order(r: WorkTypeReserve) -> tuple:
        w = types.get(r.work_type_id)
        return (w.sort_order if w else 999, r.label)

    roles_out: Dict[str, List[WorkTypeReserve]] = defaultdict(list)
    for (role, _wt), r in rows.items():
        roles_out[role].append(r)
    return TeamReserve(
        team=team,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        roles={role: sorted(rs, key=order) for role, rs in roles_out.items()},
        people=people,
        other_team_work=sorted(work.values(), key=lambda w: (-w.hours, w.issue_key or "")),
        labels={wt: w.label for wt, w in sorted(types.items(), key=lambda kv: (kv[1].sort_order, kv[1].label))},
    )


def merge_person(reserves: Iterable[Optional[TeamReserve]], employee_id: str) -> Optional[PersonReserve]:
    """Нормированные работы человека по всем его основным командам квартала
    (основная менялась внутри квартала — доли складываются)."""
    parts = [r.people[employee_id] for r in reserves if r is not None and employee_id in r.people]
    if not parts:
        return None
    out = PersonReserve(employee_id, parts[0].role, sum(p.norm for p in parts))
    for p in parts:
        for wt, h in p.blocked.items():
            out.blocked[wt] = out.blocked.get(wt, 0.0) + h
        for wt, h in p.share.items():
            out.share[wt] = out.share.get(wt, 0.0) + h
    return out


@dataclass
class PersonLoad:
    """Загрузка человека за квартал с нормированными работами, часы."""

    normed_by_day: Dict[date, float]
    blocked: Dict[date, sb.BlockHit]
    capacity: float
    own: float
    other_teams: float
    normed: float
    unplaced: float
    normed_by_type: Dict[str, float]

    @property
    def pct(self) -> float:
        total = self.own + self.other_teams + self.normed
        return total / self.capacity * 100.0 if self.capacity > 0 else 0.0


def place_person(
    capacity: Dict[date, float],
    own: Dict[date, float],
    other_teams: Dict[date, float],
    residue_share: Dict[date, float],
    blocked: Dict[date, sb.BlockHit],
    reserve: Optional[PersonReserve],
    labels: Dict[str, str],
) -> PersonLoad:
    """Раскладка нормированных работ человека по дням (для показа).

    ``capacity`` — норма рабочих дней квартала (календарь минус отсутствия),
    ``own``/``other_teams`` — часы задач плана и броней других команд,
    ``residue_share`` — доля дня вне задачи по вовлечённости (см.
    `cross_team_occupancy.other_work_share`), ``blocked`` — заблокированные
    дни. Заблокированный день — вся норма дня. В день с задачей — остаток
    дня после вовлечённости, пока хватает доли человека. Остаток доли —
    на свободное время дней пропорционально свободным часам. Не поместилось —
    ``unplaced``.
    """
    normed = {d: 0.0 for d in capacity}
    by_type: Dict[str, float] = defaultdict(float)
    for d, hit in blocked.items():
        if d in capacity:
            normed[d] = capacity[d]
            by_type[labels.get(hit.work_type_id or "", BLOCK_WITHOUT_TYPE)] += capacity[d]
    undated = reserve.undated if reserve else 0.0
    if reserve:
        for wt, h in reserve.share.items():
            by_type[labels.get(wt, wt)] += h
    remaining = undated
    for d in sorted(capacity):
        if remaining <= 0:
            break
        if d in blocked:
            continue
        busy = own.get(d, 0.0) + other_teams.get(d, 0.0)
        if busy <= 0:
            continue
        r = min(max(0.0, capacity[d] - busy), capacity[d] * residue_share.get(d, 0.0), remaining)
        normed[d] += r
        remaining -= r
    free = {
        d: max(0.0, capacity[d] - own.get(d, 0.0) - other_teams.get(d, 0.0) - normed[d])
        for d in capacity
        if d not in blocked
    }
    total_free = sum(free.values())
    if remaining > 0 and total_free > 0:
        k = min(1.0, remaining / total_free)
        for d, f in free.items():
            normed[d] += f * k
        remaining = max(0.0, remaining - total_free)
    return PersonLoad(
        normed_by_day=normed,
        blocked={d: h for d, h in blocked.items() if d in capacity},
        capacity=sum(capacity.values()),
        own=sum(own.get(d, 0.0) for d in capacity),
        other_teams=sum(other_teams.get(d, 0.0) for d in capacity),
        normed=sum(capacity[d] for d in blocked if d in capacity) + undated,
        unplaced=remaining,
        normed_by_type=dict(by_type),
    )
```

Проверить тест раскладки руками: Пн/Вт по 7,2 ч задачи + 0,8 ч остатка; Пт заблокирована (8 ч); доля 20 ч − 1,6 = 18,4 ч на свободные Ср/Чт (16 ч) → по 8 ч, не размещено 2,4 ч. Итог нормированных = 8 + 20 = 28 ч.

- [ ] **Step 4: Прогон** — `py -3.10 -m pytest tests/services/test_normed_reserve.py -q -p no:cacheprovider` → PASS; `ruff check app/services/normed_reserve.py tests/services/test_normed_reserve.py`.

---

### Task 6: Диаграмма — нормированные работы, сводка, предупреждения, выбор вида (бэкенд выпуска 2)

**Files:**
- Modify: `app/api/endpoints/resource_planning.py` (схемы ≈ 530–612, `get_gantt` ≈ 1344–1625, новый эндпоинт выбора вида)
- Test: `tests/api/test_rp_normed_reserve_gantt.py`

Зависит от задач 3 и 5.

- [ ] **Step 1: Схемы**

```python
class EmployeeLoadDay(BaseModel):
    date: date
    pct: float
    off: Optional[str] = None
    ext_pct: float = 0.0
    # Нормированные работы дня: заблокированный период, остаток дня после
    # вовлечённости и доля запаса на свободное время. В % ёмкости и в часах.
    normed_pct: float = 0.0
    normed_hours: float = 0.0
    # Заблокированный день: «причина · вид работ».
    blocked: Optional[str] = None


class NormedTypeHours(BaseModel):
    label: str
    hours: float


class EmployeeQuarterLoad(BaseModel):
    """Загрузка человека за квартал, часы; одинакова в плане любой команды."""
    capacity_hours: float
    own_hours: float
    other_teams_hours: float
    normed_hours: float
    unplaced_hours: float
    pct: float
    normed_by_type: List[NormedTypeHours] = []


class ReserveTypeRow(BaseModel):
    work_type_id: str
    label: str
    planned_hours: float
    blocked_hours: float
    other_teams_hours: float
    remaining_hours: float
    overuse_hours: float


class ReserveRoleOut(BaseModel):
    role: str
    role_label: str
    rows: List[ReserveTypeRow]


class OtherTeamWorkOut(BaseModel):
    backlog_item_id: str
    issue_key: Optional[str] = None
    title: str
    team: str
    hours: float
    work_type_id: str
    is_manual: bool


class WorkTypeOption(BaseModel):
    id: str
    label: str


class ReserveOut(BaseModel):
    """Запас нормированных работ команды плана на квартал."""
    team: str
    scenario_name: str
    roles: List[ReserveRoleOut]
    other_team_work: List[OtherTeamWorkOut]
    work_types: List[WorkTypeOption]
```

`EmployeeLoadOut` + `quarter: Optional[EmployeeQuarterLoad] = None`; `GanttProjection` + `reserve: Optional[ReserveOut] = None`. Поля `other_pct`/`other_hours` удалить.

- [ ] **Step 2: Тест диаграммы (падает)**

Сценарий из `tests/services/test_normed_reserve.py::_erp` (скопировать хелперы в тест или вынести в `tests/services/normed_factory.py` — один файл, импорт из обоих тестов). Проверки на `GET /api/v1/resource-planning/resource-plans/{erp_plan}/gantt`:

```python
    body = client.get(f"/api/v1/resource-planning/resource-plans/{plan.id}/gantt").json()
    rows = {r["employee_id"]: r for r in body["employee_load"]}
    q = rows[p.id]["quarter"]
    assert q["other_teams_hours"] == 180.0
    assert q["unplaced_hours"] >= 0
    assert q["pct"] > rows[s.id]["quarter"]["pct"]
    dev = next(r for r in body["reserve"]["roles"] if r["role"] == "dev")
    tech = next(x for x in dev["rows"] if x["label"] == "technical_tasks")
    assert tech["overuse_hours"] > 0
    types = {c["type"] for c in body["conflicts"]}
    assert "NORMED_OVERUSE" in types
    assert body["reserve"]["other_team_work"][0]["hours"] == 180.0
    # день с задачей «Блока» у Пряничникова: 7,2 ч других команд + нормированные ≤ остатка дня
    day = next(d for d in rows[p.id]["days"] if d["date"] == "2026-01-12")
    assert day["ext_pct"] == 90.0 and day["normed_hours"] <= 0.8 + 1e-6
```

Отдельный тест: `PUT /api/v1/resource-planning/work-type-overrides` `{team: "ERP", backlog_item_id, work_type_id: support}` → 204; диаграмма: строка «Технические задачи» без `other_teams_hours`, `other_team_work[0].is_manual is True`; `work_type_id: null` → 204 и выбор снят; несуществующий вид → 422; «Прочие / Чужие» → 422; несуществующая задача → 404.

Отдельный тест: команда без правил — `reserve is None`, у людей `quarter` есть, `normed_hours` дней 0 (кроме заблокированных).

- [ ] **Step 3: `get_gantt`**

В блоке `if plan_employees:` после расчёта `used`, `bookings`, `other_share`, `membership`:

```python
            # Нормированные работы — запас основных команд людей плана
            # (см. app/services/normed_reserve.py). Раскладка — по всему
            # кварталу человека, цифры не зависят от плана, в котором смотрят.
            ids = [e.id for e in plan_employees]
            cal = nr.calendar_hours(db, q_start, q_end)
            absent = nr.absent_days(db, ids, q_start, q_end)
            full_cap = {eid: {d: h for d, h in cal.items() if d not in absent.get(eid, ())} for eid in ids}
            own_full = _daily_used(assignments_raw, full_cap)
            quarter = cto.quarter_num(plan.quarter)
            home_teams = {
                t for rows_ in membership.values() for t, _j, _l, prim in rows_ if prim
            }
            reserves = {t: nr.team_reserve(db, t, plan.year, quarter) for t in sorted(home_teams)} if plan.year and quarter else {}
            labels = next((r.labels for r in reserves.values() if r), {}) or {
                w.id: w.label for w in db.execute(select(MandatoryWorkType)).scalars()
            }
            hits = sb.resolve_blocked_days(db, plan_employees, q_start, q_end, plan.team)
            loads = {}
            for e in plan_employees:
                rows_ = membership.get(e.id, [])
                shown = {
                    d: h for d, h in hits.get(e.id, {}).items()
                    if h.team is None or nr.primary_on(rows_, h.team, d)
                }
                loads[e.id] = nr.place_person(
                    full_cap[e.id],
                    own_full.get(e.id, {}),
                    {d: h for d, h in ext_daily.get(e.id, {}).items() if q_start <= d <= q_end},
                    other_share.get(e.id, {}),
                    shown,
                    nr.merge_person(reserves.values(), e.id),
                    labels,
                )
```

Если `membership` в `get_gantt` — только периоды людей плана из `tm.membership_rows` (так и есть, ≈ стр. 1394), используем его. `MandatoryWorkType` импортировать из `app.models`; `nr` — `from app.services import normed_reserve as nr`, `sb` — из Task 3.

В цикле дней: вместо `other_h`/`other_pct`:

```python
                    load = loads[e.id]
                    normed_h = load.normed_by_day.get(d, 0.0) if av > 0 else 0.0
                    hit = load.blocked.get(d)
                    blocked_label = (
                        f"{hit.reason} · {labels.get(hit.work_type_id, '')}".rstrip(" ·")
                        if hit and hit.work_type_id else (hit.reason if hit else None)
                    )
```

и в `EmployeeLoadDay(..., normed_pct=round(normed_h / av * 100, 1) if av > 0 else 0.0, normed_hours=round(normed_h, 2), blocked=blocked_label)`. В `EmployeeLoadOut(..., quarter=EmployeeQuarterLoad(capacity_hours=round(load.capacity, 1), own_hours=round(load.own, 1), other_teams_hours=round(load.other_teams, 1), normed_hours=round(load.normed, 1), unplaced_hours=round(load.unplaced, 1), pct=round(load.pct, 1), normed_by_type=[NormedTypeHours(label=k, hours=round(v, 1)) for k, v in sorted(load.normed_by_type.items(), key=lambda kv: -kv[1])]))`.

`base_share` остаётся — им пользуются отметки пересечений и `_cross_team_conflicts`; удалить только то, что станет неиспользуемым.

Сводка и предупреждения (после цикла людей):

```python
            plan_reserve = reserves.get(plan.team) if plan.team in reserves else (
                nr.team_reserve(db, plan.team, plan.year, quarter) if plan.year and quarter else None
            )
            if plan_reserve is not None:
                reserve_out = _reserve_out(db, plan_reserve)
                normed_warnings = _normed_warnings(plan, plan_reserve, loads, names, role_labels)
```

`_reserve_out` — сборка `ReserveOut` (роль → подпись из реестра `roles`: `{r.code: r.label}` одним запросом; строки с `round(…, 1)`; `work_types` — из `plan_reserve.labels`). `_normed_warnings` — `ConflictOut` с `is_live=True`, `status="open"`, `severity="warning"`, штамп как у `_cross_team_conflicts`:
- `NORMED_OVERUSE`, id `live:NORMED_OVERUSE:{role}:{work_type_id}`, `metric_value=overuse`, сообщение `f"{role_label} · {label}: заложено {planned:.0f} ч, " + ", ".join(части)` где части — `f"другие команды заняли {other:.0f} ч"` (если > 0) и `f"заблокировано {blocked:.0f} ч"` (если > 0); только строки с `overuse > 0.5`.
- `NORMED_UNPLACED`, id `live:NORMED_UNPLACED:{employee_id}`, `employee_id`, `employee_name`, сообщение `f"{name}: не вмещается {unplaced:.0f} ч нормированных работ"`; только люди запаса команды плана (`eid in plan_reserve.people`) из `loads` с `unplaced > 0.5`.

Добавить их к `live_conflicts`. Префикс — константа `LIVE_CONFLICT_PREFIX` (как у `CROSS_TEAM_OVERLAP`). Проверить, что PATCH статуса живого конфликта отвечает 409 и для новых типов (общий путь по префиксу).

- [ ] **Step 4: Эндпоинт выбора вида**

```python
class WorkTypeOverrideIn(BaseModel):
    team: str
    backlog_item_id: str
    # None — вернуть вид по умолчанию («Технические задачи»).
    work_type_id: Optional[str] = None


@router.put("/work-type-overrides", status_code=204)
async def put_work_type_override(
    data: WorkTypeOverrideIn,
    db: Session = Depends(get_db),
    bus: EventBroadcaster = Depends(get_event_broadcaster),
    _: User = Depends(get_current_user),
):
    """Чем команда ``team`` считает работу своих людей над задачей другой команды."""
    if db.get(BacklogItem, data.backlog_item_id) is None:
        raise HTTPException(404, "Задача не найдена")
    if data.work_type_id is not None:
        wt = db.get(MandatoryWorkType, data.work_type_id)
        if wt is None or not wt.subtracts_from_pool:
            raise HTTPException(422, "Выберите вид нормированных работ")
    row = db.execute(
        select(TeamWorkTypeOverride).where(
            TeamWorkTypeOverride.team == data.team,
            TeamWorkTypeOverride.backlog_item_id == data.backlog_item_id,
        )
    ).scalar_one_or_none()
    if data.work_type_id is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(TeamWorkTypeOverride(team=data.team, backlog_item_id=data.backlog_item_id,
                                    work_type_id=data.work_type_id))
    else:
        row.work_type_id = data.work_type_id
    db.commit()
    await _announce(bus, bookings=False)
```

Имя зависимости шины (`get_event_broadcaster` или иное) и `EventBroadcaster` — взять из существующих async-эндпоинтов этого файла.

- [ ] **Step 5: Прогон** — новый тест + `tests/api/test_rp_cross_team_gantt.py tests/services/test_rp_involvement_defaults.py` и всё, что грепается по `other_pct|other_hours` в `tests/` (поправить ожидания на `normed_*`, не меняя смысла проверок пересечений) → PASS; `ruff check app/ tests/`.

---

### Task 7: «Загрузка по дням», сводка запаса, подписи предупреждений (фронт выпуска 2)

**Files:**
- Modify: `frontend/src/api/resourcePlanning.ts` (типы диаграммы, `putWorkTypeOverride`)
- Modify: `frontend/src/hooks/useResourcePlanning.ts` (`useSetWorkTypeOverride`)
- Modify: `frontend/src/utils/heatmapFill.ts` (+ тест), `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`, утилита подсказки дня (где `dayTooltipLines` — найти grep'ом, вероятно `frontend/src/utils/rpBusy.ts`)
- Create: `frontend/src/components/resource-planning/NormedReserveSummary.tsx`, `frontend/src/utils/normedReserve.ts` (+ `normedReserve.test.ts`)
- Modify: `frontend/src/components/resource-planning/ConflictPanel.tsx`, место рендера «Загрузки по дням» в `ResourcePlanningPage.tsx`

Контракт — Task 6, шаги 1 и 4 (типы TS зеркалят схемы: `EmployeeLoadDay.normed_pct/normed_hours/blocked`, `EmployeeQuarterLoad`, `EmployeeLoadOut.quarter?`, `ReserveTypeRow`, `ReserveRoleOut`, `OtherTeamWorkOut`, `WorkTypeOption`, `ReserveOut`, `GanttProjection.reserve?: ReserveOut | null`). `other_pct/other_hours` удалить из типов и всех мест использования.

- [ ] **Step 1: `heatmapFill`**

`OTHER_WORK_COLOR` → `NORMED_WORK_COLOR` (тот же цвет), параметр `otherPct` → `normedPct`, комментарии — «нормированные работы». `quarterLoad` удалить, если после перехода на `row.quarter` он нигде не нужен (проверить grep'ом, включая тесты). Тест `heatmapFill.test.ts` (создать, если нет): заливка с `normedPct` даёт градиент с `NORMED_WORK_COLOR`; без внешних и нормированных — исходный цвет.

- [ ] **Step 2: Утилита сводки + тест**

```ts
import type { ReserveOut } from '../api/resourcePlanning';

/** Строки сводки с перерасходом — для красной подсветки и счётчика. */
export function overuseCount(reserve: ReserveOut | null | undefined): number {
  if (!reserve) return 0;
  return reserve.roles.reduce((n, r) => n + r.rows.filter((x) => x.overuse_hours > 0.5).length, 0);
}

/** Подпись часов: «102 ч». */
export const fmtHours = (h: number) => `${Math.round(h)} ч`;
```

Тест: `overuseCount(null) === 0`; две роли, одна строка с перерасходом 78 ч и одна с 0,2 ч → 1.

- [ ] **Step 3: `NormedReserveSummary`**

Пропсы: `reserve: ReserveOut`, `planTeam: string`. Над «Загрузкой по дням» (тот же тёмный стиль контейнера, что у тепловой карты). Заголовок «Нормированные работы — запас квартала» + подпись сценария. По ролям — компактная таблица (`Table size="small" pagination={false}`) колонок: «Вид работ», «Заложено», «Заблокировано», «Другие команды», «Осталось»; строка с `overuse_hours > 0.5` — «Осталось» красным как `−78 ч` и подсказка «перерасход». Ниже — `Collapse` «Работа наших людей в других командах (N)»: строки «KEY · название — команда — часы — вид работ»; вид — `Select` (опции `reserve.work_types`, `allowClear`, placeholder «Технические задачи»; значение — `is_manual ? work_type_id : undefined`), смена → `useSetWorkTypeOverride().mutate({ team: planTeam, backlog_item_id, work_type_id: value ?? null })`, после успеха — инвалидация диаграммы (как у других правок плана в хуке). Пустой список — блок не показывать. Тексты — без технических слов.

- [ ] **Step 4: `EmployeeLoadHeatmap`**

- Слой клетки: `splitLoadFill(bg, d.pct, d.ext_pct ?? 0, d.normed_pct ?? 0)`; заблокированный день (`d.blocked`) — тот же слой (он уже 100% нормированных).
- Легенда: «нормированные работы» вместо «прочие работы».
- Описание под заголовком: «Только рабочие дни. Нормированные работы — запас квартала из сценария основной команды: заблокированные периоды, остаток дня после вовлечённости и остальное — на свободные дни. Процент у имени — загрузка за квартал с задачами других команд и нормированными работами. Наведите на день — часы; на имя — разбивка; щелчок по имени — фильтр по человеку.»
- Подсказка дня: вместо строки «прочие работы» — «нормированные работы N ч»; если `blocked` — первой строкой «заблокировано: {blocked}».
- Процент у имени — `row.quarter?.pct` (округлить), красный при > 100; подсказка у имени (title или тот же плавающий tip): «Задачи плана N ч · Другие команды N ч · Нормированные работы N ч» + по строке на `normed_by_type` + «Не вмещается N ч» при `unplaced_hours > 0.5` + «Норма квартала N ч».

- [ ] **Step 5: `ConflictPanel`** — в `TYPE_LABELS`: `NORMED_OVERUSE: 'Перерасход нормированных работ'`, `NORMED_UNPLACED: 'Квартал не вмещается'`. Убедиться, что для живых конфликтов меню действий скрыто (как у `CROSS_TEAM_OVERLAP`).

- [ ] **Step 6: Страница** — `NormedReserveSummary` рендерить прямо перед `EmployeeLoadHeatmap`, если `gantt.reserve` и `gantt.plan.team`.

- [ ] **Step 7: Прогон** — `cd frontend && npx tsc -b && npx eslint <изменённые файлы> && npx vitest run src/utils` → без ошибок.

---

### Task 8: Справка, заметки о модулях, черновики «Что нового»

**Files:**
- Modify: `docs/help/resource-planning.md`, `app/services/CLAUDE.md`, `release_notes/drafts.json`

- [ ] **Step 1: Справка.** В `docs/help/resource-planning.md` найти разделы про заблокированные периоды и «Загрузку по дням» (раздел 3.10, «Подвал»). Переписать языком пользователя (без технических слов):
  - Заблокированные периоды: вид работ (обязателен; «Закрытие месяца» → «Сопровождение и консультация»), кому (вся команда / роли / сотрудники), приоритет «сотрудник главнее роли, роль главнее команды — в пределах месяца и вида работ» с примером про Иванова, период основной команды закрывает день и в планах других команд, их план помечается устаревшим.
  - Нормированные работы в «Загрузке по дням»: откуда проценты (сценарий основной команды), общий запас роли, работа в других командах — «Технические задачи» или выбранный вид, остаток делится между людьми роли, как ложится на дни, процент у имени, «не вмещается», сводка над диаграммой и выбор вида у задач других команд, предупреждения. Пример с двумя разработчиками и 102 ч.
  - Вовлечённость: плотность работы над задачей; количество нормированных работ за квартал задают проценты сценария.
- [ ] **Step 2: `app/services/CLAUDE.md`** — по короткому абзацу о `scheduled_blocks.py` и `normed_reserve.py` (в стиле соседних абзацев), в абзаце `cross_team_occupancy` — упоминание, что отпечаток включает заблокированные дни чужих основных команд.
- [ ] **Step 3: Черновики.** В `release_notes/drafts.json` найти заметки 28.09 о «прочих работах» (грепнуть «прочие работы»). Заменить их заметками (формат и поля — как у соседних):
  - `feature`, раздел ресурсного планирования: «Нормированные работы в загрузке сотрудников» — запас квартала из сценария, сводка, предупреждения, выбор вида у задач других команд;
  - `improvement`: «Заблокированные периоды: вид работ и сотрудники» — вид работ, несколько ролей, конкретные сотрудники с приоритетом, в списке видно кому, периоды основной команды действуют в планах других команд.
  Порядок в файле: новое → улучшение → исправление. Текст — для пользователей, без технических слов.

---

## Самопроверка плана (выполнено при написании)

- Покрытие спеки: 4.1–4.2 → задачи 3 (API), 4 (UI); 4.3–4.4 → 2; 4.5 → 3; 5.1–5.4 → 5; 5.5–5.6 → 5 (`place_person`), 6; 5.7 → 6, 7; 5.8 → 6, 7; 6.7 → 8.
- Имена согласованы: `resolve_blocked_days`, `cells_by_team`, `BlockHit`, `team_reserve`, `merge_person`, `place_person`, `primary_on`, `calendar_hours`, `absent_days`, `TeamWorkTypeOverride`, `NORMED_OVERUSE`/`NORMED_UNPLACED`, `normed_pct`/`normed_hours`/`blocked`/`quarter`/`reserve`.
