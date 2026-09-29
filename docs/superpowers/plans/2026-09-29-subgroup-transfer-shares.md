# Перевод и деление сотрудника между группами — план

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Группа сотрудника внутри команды становится историей «с даты — группа %»: перевод между группами с даты и деление человека между группами учитываются в ресурсе сценария, утверждении, планировании, группе задачи, перетоке и витринах.

**Architecture:** Новая таблица долей + единый модуль чтения `app/services/subgroup_shares.py` (как `team_membership.py` для состава) + сервис записи. Колонка группы у участия живёт до задачи 7 и синхронизируется сервисом записи, поэтому каждая задача оставляет тесты зелёными; все чтения переводятся на модуль по одному потребителю; в задаче 7 колонка удаляется.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic (batch для SQLite), React 19 + AntD 6.

**Спека:** [../specs/2026-09-29-subgroup-transfer-shares-design.md](../specs/2026-09-29-subgroup-transfer-shares-design.md).

## Общие правила

- Рабочая копия: `D:\ClaudeDev\JiraAnalysis-subgroups` (ветка `feature/subgroup-shares`). Не трогать `D:\ClaudeDev\JiraAnalysis` — там работают другие сессии.
- Python: `py -3.10`. Тесты: `py -3.10 -m pytest <пути> -q -p no:cacheprovider`; полный прогон — `py -3.10 -m pytest tests -q -p no:cacheprovider --ignore=tests/api/test_llm.py` (LLM-тесты виснут без сети).
- Фронт: `cd frontend && npx tsc -b && npx eslint <файлы> && npx vitest run src`.
- Не коммитить: коммитит координатор после ревью задачи.
- Перед исследованием кода — `graphify query "<вопрос>"` (граф в основной копии `D:\ClaudeDev\JiraAnalysis\graphify-out`, может быть устаревшим).
- Команда в данных — строка (`EmployeeTeam.team`, `Issue.team`), реестр `Team` адресуется по имени. Деление включено, если `Team.has_subgroups`.
- Комментарии и docstrings бизнес-логики — по-русски, как в соседнем коде.
- Прямое чтение `EmployeeTeam.subgroup_id` в новых местах запрещено; после задачи 7 колонки нет.

## Порядок

- **Задача 1** → **Задача 2** → задачи **3, 4, 5, 6** (независимы, можно параллельно) → **Задача 7** → задачи **8, 9** (фронт, параллельно) → **Задача 10**.

---

### Task 1: Таблица долей, миграция, модуль чтения, тестовые фикстуры

**Files:**
- Create: `app/models/employee_subgroup_share.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/sg01_subgroup_shares.py`
- Create: `app/services/subgroup_shares.py`
- Create: `tests/subgroup_fixtures.py`
- Test: `tests/services/test_subgroup_shares.py`, `tests/test_migration_sg01_subgroup_shares.py`
- Modify (фикстуры): 15 тестовых файлов из шага 9

- [ ] **Step 1: Модель**

`app/models/employee_subgroup_share.py`:

```python
"""Распределение сотрудника по группам внутри команды."""

from datetime import date as _date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class EmployeeSubgroupShare(Base, TimestampMixin):
    """Доля сотрудника в группе команды с даты.

    Запись распределения — все строки одного сотрудника в одной команде с
    одинаковой ``valid_from``; сумма ``percent`` = 100. Запись действует до
    ``valid_from`` следующей записи. ``valid_from = None`` — «с начала участия».

    Инварианты (сумма 100, группа этой команды, одна запись на дату)
    проверяет ``SubgroupShareService``: NULL в уникальном ключе не сравнивается.
    """

    __tablename__ = "employee_subgroup_shares"
    __table_args__ = (
        Index("ix_employee_subgroup_shares_emp_team", "employee_id", "team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    team: Mapped[str] = mapped_column(String(100), nullable=False)
    valid_from: Mapped[Optional[_date]] = mapped_column(Date, nullable=True)
    subgroup_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_subgroups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    percent: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<EmployeeSubgroupShare {self.employee_id}:{self.team}@{self.valid_from} {self.subgroup_id}={self.percent}>"
```

В `app/models/__init__.py` рядом с `EmployeeTeam`:

```python
from app.models.employee_subgroup_share import EmployeeSubgroupShare
```

и `"EmployeeSubgroupShare",` в `__all__` рядом с `"EmployeeTeam",`.

- [ ] **Step 2: Тест миграции (падает)**

`tests/test_migration_sg01_subgroup_shares.py`:

```python
"""sg01: таблица долей групп и перенос нынешней группы участия."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
PREV = "pi01_personal_settings"
REV = "sg01_subgroup_shares"


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_copies_current_group_as_base_record(tmp_path):
    url = f"sqlite:///{(tmp_path / 'sg01.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    now = "2026-09-29 00:00:00"
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO employees (id, jira_account_id, display_name, is_active, created_at, updated_at) "
            "VALUES ('e1', 'a1', 'Иванов', 1, :n, :n), ('e2', 'a2', 'Петров', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO teams (id, name, has_subgroups, created_at, updated_at) "
            "VALUES ('t1', 'T', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO team_subgroups (id, team_id, name, sort_order, created_at, updated_at) "
            "VALUES ('g1', 't1', 'A', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, subgroup_id, created_at) "
            "VALUES ('m1', 'e1', 'T', 1, 'g1', :n), ('m2', 'e2', 'T', 1, NULL, :n)"
        ), {"n": now})
    engine.dispose()

    _alembic(url, "upgrade", REV)

    engine = sa.create_engine(url)
    with engine.connect() as c:
        rows = c.execute(sa.text(
            "SELECT employee_id, team, valid_from, subgroup_id, percent FROM employee_subgroup_shares"
        )).all()
    engine.dispose()
    assert [tuple(r) for r in rows] == [("e1", "T", None, "g1", 100)]

    _alembic(url, "downgrade", PREV)
    _alembic(url, "upgrade", REV)


def test_upgrade_skips_table_created_by_create_all(tmp_path):
    from app.models import EmployeeSubgroupShare

    url = f"sqlite:///{(tmp_path / 'sg01b.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    EmployeeSubgroupShare.__table__.create(engine)
    engine.dispose()

    _alembic(url, "upgrade", REV)
```

Run: `py -3.10 -m pytest tests/test_migration_sg01_subgroup_shares.py -q -p no:cacheprovider` → FAIL (нет ревизии `sg01_subgroup_shares`).

- [ ] **Step 3: Миграция**

`alembic/versions/sg01_subgroup_shares.py`:

```python
"""employee_subgroup_shares: распределение сотрудника по группам с даты

Revision ID: sg01_subgroup_shares
Revises: pi01_personal_settings
Create Date: 2026-09-29

Переносит нынешнюю группу участия в запись «100% с начала участия».
Колонку группы у участия не трогает — её убирает sg02, когда все расчёты
читают доли. Самодостаточна: не импортирует код приложения. Локальная
dev-база может уже иметь таблицу от create_all в tests/conftest.py.
"""
from datetime import date, datetime
import uuid
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sg01_subgroup_shares"
down_revision: Union[str, None] = "pi01_personal_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "employee_subgroup_shares"


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "employee_id", sa.String(36),
                sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("team", sa.String(100), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column(
                "subgroup_id", sa.String(36),
                sa.ForeignKey("team_subgroups.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("percent", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_employee_subgroup_shares_emp_team", TABLE, ["employee_id", "team"]
        )
        op.create_index("ix_employee_subgroup_shares_subgroup_id", TABLE, ["subgroup_id"])

    if context.is_offline_mode():
        return
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("employee_teams")}
    if "subgroup_id" not in columns:
        return

    et = sa.table(
        "employee_teams",
        sa.column("employee_id"), sa.column("team"),
        sa.column("subgroup_id"), sa.column("joined_at"),
    )
    sh = sa.table(
        TABLE,
        sa.column("id"), sa.column("employee_id"), sa.column("team"),
        sa.column("valid_from"), sa.column("subgroup_id"), sa.column("percent"),
        sa.column("created_at"), sa.column("updated_at"),
    )
    sg = sa.table("team_subgroups", sa.column("id"))

    known = {r[0] for r in bind.execute(sa.select(sg.c.id))}
    done = {(r[0], r[1]) for r in bind.execute(sa.select(sh.c.employee_id, sh.c.team))}
    # Группа одна на пару сотрудник/команда; при расхождении периодов берём
    # группу самого позднего периода участия.
    latest: dict[tuple[str, str], tuple[str, date]] = {}
    for emp_id, team, subgroup_id, joined_at in bind.execute(
        sa.select(et.c.employee_id, et.c.team, et.c.subgroup_id, et.c.joined_at).where(
            et.c.subgroup_id.isnot(None)
        )
    ):
        key = (emp_id, team)
        if subgroup_id not in known or key in done:
            continue
        # SQLite отдаёт дату строкой.
        if isinstance(joined_at, str):
            joined_at = date.fromisoformat(joined_at[:10])
        joined = joined_at or date.min
        if key not in latest or joined >= latest[key][1]:
            latest[key] = (subgroup_id, joined)

    now = datetime.utcnow()
    if latest:
        op.bulk_insert(sh, [
            {
                "id": str(uuid.uuid4()), "employee_id": emp_id, "team": team,
                "valid_from": None, "subgroup_id": subgroup_id, "percent": 100,
                "created_at": now, "updated_at": now,
            }
            for (emp_id, team), (subgroup_id, _) in latest.items()
        ])


def downgrade() -> None:
    op.drop_index("ix_employee_subgroup_shares_subgroup_id", table_name=TABLE)
    op.drop_index("ix_employee_subgroup_shares_emp_team", table_name=TABLE)
    op.drop_table(TABLE)
```

Run: тест из шага 2 → PASS.

- [ ] **Step 4: Тест модуля чтения (падает)**

`tests/services/test_subgroup_shares.py`:

```python
"""Модуль чтения распределения сотрудника по группам."""

from datetime import date

from app.models import Employee, EmployeeSubgroupShare, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_shares as ss
from app.services.subgroup_shares import ShareRecord

A, B = "g-a", "g-b"
Q_START, Q_END = date(2026, 10, 1), date(2026, 12, 31)


def rec(valid_from, *shares):
    return ShareRecord(valid_from, tuple(shares))


def test_record_on_picks_latest_started():
    records = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.single_group_on(records, date(2026, 11, 14)) == A
    assert ss.single_group_on(records, date(2026, 11, 15)) == B


def test_record_on_before_first_dated_record_is_none():
    records = [rec(date(2026, 11, 1), (A, 100))]
    assert ss.record_on(records, date(2026, 10, 31)) is None
    assert ss.shares_on(records, date(2026, 10, 31)) == {}


def test_shared_person_has_no_single_group():
    records = [rec(None, (A, 60), (B, 40))]
    assert ss.single_group_on(records, date(2026, 10, 1)) is None
    assert ss.shares_on(records, date(2026, 10, 1)) == {A: 0.6, B: 0.4}


def test_split_hours_without_group_goes_to_empty_key():
    assert ss.split_hours([], date(2026, 10, 1), 8.0) == {"": 8.0}
    assert ss.split_hours([rec(None, (A, 60), (B, 40))], date(2026, 10, 1), 10.0) == {
        A: 6.0, B: 4.0,
    }


def test_segments_and_groups_between():
    records = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.segments(records, Q_START, Q_END) == [
        (Q_START, date(2026, 11, 14), records[0]),
        (date(2026, 11, 15), Q_END, records[1]),
    ]
    assert ss.groups_between(records, Q_START, Q_END) == {A, B}
    assert ss.groups_between(records, date(2026, 12, 1), Q_END) == {B}


def test_group_labels():
    transfer = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.group_label(transfer, A, Q_START, Q_END) == "до 15.11"
    assert ss.group_label(transfer, B, Q_START, Q_END) == "с 15.11"
    split = [rec(None, (A, 60), (B, 40))]
    assert ss.group_label(split, A, Q_START, Q_END) == "60%"
    whole = [rec(None, (A, 100))]
    assert ss.group_label(whole, A, Q_START, Q_END) == ""


def test_distribution_label_keeps_plain_name_for_whole_quarter():
    names = {A: "Ломбард", B: "РФМ"}
    assert ss.distribution_label([rec(None, (A, 100))], Q_START, Q_END, names) == "Ломбард"
    assert ss.distribution_label(
        [rec(None, (A, 60), (B, 40))], Q_START, Q_END, names
    ) == "Ломбард 60% · РФМ 40%"
    assert ss.distribution_label(
        [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))], Q_START, Q_END, names
    ) == "Ломбард до 15.11 · РФМ с 15.11"
    assert ss.distribution_label([], Q_START, Q_END, names) is None


def _team(db):
    team = Team(id="t1", name="T", has_subgroups=True)
    db.add(team)
    db.flush()
    db.add_all([
        TeamSubgroup(id=A, team_id="t1", name="Ломбард", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="РФМ", sort_order=2),
    ])
    for eid in ("e1", "e2", "e3"):
        db.add(Employee(id=eid, jira_account_id=f"acc-{eid}", display_name=eid, is_active=True))
        db.add(EmployeeTeam(employee_id=eid, team="T", is_primary=True))
    db.flush()


def test_load_team_groups_rows_into_records(db_session):
    _team(db_session)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=date(2026, 11, 15), subgroup_id=A, percent=40),
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=date(2026, 11, 15), subgroup_id=B, percent=60),
    ])
    db_session.commit()

    records = ss.load_team(db_session, "T")["e1"]
    assert records == [
        rec(None, (A, 100)),
        rec(date(2026, 11, 15), (B, 60), (A, 40)),
    ]
    assert ss.team_subgroups(db_session, "T") == [(A, "Ломбард"), (B, "РФМ")]


def test_ungrouped_members(db_session):
    _team(db_session)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        # e2 получает группу только с ноября — октябрь без группы
        EmployeeSubgroupShare(employee_id="e2", team="T", valid_from=date(2026, 11, 1), subgroup_id=B, percent=100),
    ])
    db_session.commit()

    assert ss.ungrouped_members(db_session, "T", Q_START, Q_END) == ["e2", "e3"]
    assert ss.ungrouped_members(db_session, "T", date(2026, 11, 1), Q_END) == ["e3"]


def test_ungrouped_members_empty_without_division(db_session):
    db_session.add(Team(id="t2", name="Plain", has_subgroups=False))
    db_session.add(Employee(id="e9", jira_account_id="acc-9", display_name="e9", is_active=True))
    db_session.add(EmployeeTeam(employee_id="e9", team="Plain", is_primary=True))
    db_session.commit()
    assert ss.ungrouped_members(db_session, "Plain", Q_START, Q_END) == []
```

Run: `py -3.10 -m pytest tests/services/test_subgroup_shares.py -q -p no:cacheprovider` → FAIL (нет модуля).

- [ ] **Step 5: Модуль чтения**

`app/services/subgroup_shares.py`:

```python
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
    """Отрезки периода [start, end] (границы включительно) с действующей записью."""
    out: list[tuple[date, date, ShareRecord]] = []
    for i, rec in enumerate(records):
        lo = max(rec.valid_from or start, start)
        nxt = records[i + 1].valid_from if i + 1 < len(records) else None
        hi = min(nxt - timedelta(days=1), end) if nxt else end
        if lo <= hi:
            out.append((lo, hi, rec))
    return out


def groups_between(records: Records, start: date, end: date) -> set[str]:
    """Группы, где у человека была доля хотя бы один день периода."""
    return {g for _, _, rec in segments(records, start, end) for g in rec.groups}


def _fmt(d: date) -> str:
    return d.strftime("%d.%m")


def group_label(records: Records, group_id: str, start: date, end: date) -> str:
    """Подпись участия в группе за период: «60%», «с 15.11», «до 15.11».

    Пусто — весь период человек целиком в этой группе.
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
    """
    present = groups_between(records, start, end)
    ordered = [g for g in names if g in present]
    if not ordered:
        return None
    return " · ".join(
        f"{names[g]} {group_label(records, g, start, end)}".strip() for g in ordered
    )


def quarter_labels(db: Session, team: str, start: date, end: date) -> dict[str, str]:
    """Сотрудник → подпись распределения за период. Пусто — деления нет."""
    groups = team_subgroups(db, team)
    if not groups:
        return {}
    names = dict(groups)
    out: dict[str, str] = {}
    for emp_id, records in load_team(db, team).items():
        label = distribution_label(records, start, end, names)
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
```

Run: `py -3.10 -m pytest tests/services/test_subgroup_shares.py -q -p no:cacheprovider` → PASS.

- [ ] **Step 6: Помощник фикстур**

`tests/subgroup_fixtures.py`:

```python
"""Приписка сотрудника к группе в тестах — строкой распределения."""

from datetime import date
from typing import Optional

from app.models import EmployeeSubgroupShare


def share(
    employee_id: str,
    team: str,
    subgroup_id: str,
    percent: int = 100,
    valid_from: Optional[date] = None,
) -> EmployeeSubgroupShare:
    """Строка распределения; по умолчанию — «100 % с начала участия»."""
    return EmployeeSubgroupShare(
        employee_id=employee_id,
        team=team,
        subgroup_id=subgroup_id,
        percent=percent,
        valid_from=valid_from,
    )
```

- [ ] **Step 7: Фикстуры — добавить строку распределения к каждой приписке**

Найти все места: `grep -rnE "subgroup_id\s*=" tests | grep -v "assigned_subgroup_id\|effective_subgroup_id"` в файлах, где создаётся `EmployeeTeam(...)`:

`tests/api/test_issue_subgroup.py`, `tests/services/test_subgroup_effective.py`, `tests/services/test_subgroup_filter.py`, `tests/services/test_subgroup_resolver.py`, `tests/services/test_team_registry_service.py`, `tests/test_api_planning_subgroups.py`, `tests/test_capacity_subgroup.py`, `tests/test_dashboard_subgroups.py`, `tests/test_export_subgroups.py`, `tests/test_people_views_subgroups.py`, `tests/test_projects_backlog_subgroups.py`, `tests/test_resource_summary_subgroups.py`, `tests/test_rp_subgroup_assignment.py`, `tests/test_scenario_subgroup_snapshot.py`, `tests/test_subgroup_flow.py`.

Правило: у каждого `EmployeeTeam(employee_id=E, team=T, ..., subgroup_id=G)` **оставить** `subgroup_id=G` (колонка пока читается) и сразу после добавления участия добавить `db.add(share(E, T, G))` — только если `G` не `None`. Пример из `tests/test_resource_summary_subgroups.py`:

```python
from tests.subgroup_fixtures import share
...
def _dev(db, eid, subgroup_id=None, role="dev"):
    db.add(Employee(...))
    db.add(
        EmployeeTeam(
            employee_id=eid, team=TEAM, is_primary=True, subgroup_id=subgroup_id
        )
    )
    if subgroup_id:
        db.add(share(eid, TEAM, subgroup_id))
```

Строке распределения нужна существующая группа (внешний ключ): если в тесте участие создаётся раньше группы, добавлять `share(...)` после `flush()` групп. Не трогать `Issue(... assigned_subgroup_id=...)` и прочие поля задач.

- [ ] **Step 8: Прогон**

Run: `py -3.10 -m pytest tests -q -p no:cacheprovider --ignore=tests/api/test_llm.py` → все зелёные (поведение не менялось).

---

### Task 2: Сервис записи, API долей, перевод между командами с группой, группа в составе команд сотрудника

**Files:**
- Create: `app/services/subgroup_share_service.py`
- Modify: `app/services/team_registry_service.py` (`assign_employee`, `delete_subgroup`)
- Modify: `app/schemas/team.py`, `app/api/endpoints/teams.py`
- Modify: `app/api/endpoints/employees.py` (`EmployeeTeamItem`, перевод)
- Test: `tests/services/test_subgroup_share_service.py`, `tests/api/test_subgroup_shares_api.py`

- [ ] **Step 1: Тесты сервиса (падают)**

`tests/services/test_subgroup_share_service.py`:

```python
"""Запись распределения сотрудника по группам."""

from datetime import date

import pytest

from app.models import Employee, EmployeeSubgroupShare, EmployeeTeam, Issue, Team, TeamSubgroup
from app.services import subgroup_shares as ss
from app.services.subgroup_share_service import SubgroupShareService
from app.services.team_registry_service import TeamRegistryService

A, B, OTHER = "g-a", "g-b", "g-x"


@pytest.fixture
def team(db_session):
    db_session.add_all([
        Team(id="t1", name="T", has_subgroups=True),
        Team(id="t2", name="Other", has_subgroups=True),
    ])
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id=A, team_id="t1", name="A", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="B", sort_order=2),
        TeamSubgroup(id=OTHER, team_id="t2", name="X", sort_order=1),
        Employee(id="e1", jira_account_id="acc-1", display_name="Иванов", is_active=True),
    ])
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id="e1", team="T", is_primary=True))
    db_session.commit()


def test_set_record_and_history(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    history = svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    assert [(r.valid_from, r.shares) for r in history] == [
        (None, ((A, 100),)),
        (date(2026, 11, 15), ((A, 60), (B, 40))),
    ]


def test_same_date_replaces_record(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    history = svc.set_record("e1", "T", date(2026, 11, 15), {B: 100})
    assert [(r.valid_from, r.shares) for r in history] == [(date(2026, 11, 15), ((B, 100),))]


@pytest.mark.parametrize("shares,message", [
    ({}, "хотя бы одну"),
    ({A: 60, B: 30}, "100"),
    ({A: 0, B: 100}, "от 1 до 100"),
    ({OTHER: 100}, "не из этой команды"),
])
def test_set_record_validation(db_session, team, shares, message):
    with pytest.raises(ValueError, match=message):
        SubgroupShareService(db_session).set_record("e1", "T", None, shares)


def test_set_record_requires_membership(db_session, team):
    db_session.add(Employee(id="e2", jira_account_id="acc-2", display_name="Петров", is_active=True))
    db_session.commit()
    with pytest.raises(ValueError, match="не состоит"):
        SubgroupShareService(db_session).set_record("e2", "T", None, {A: 100})


def test_delete_record(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    svc.set_record("e1", "T", date(2026, 11, 15), {B: 100})
    history = svc.delete_record("e1", "T", date(2026, 11, 15))
    assert [r.valid_from for r in history] == [None]
    with pytest.raises(LookupError):
        svc.delete_record("e1", "T", date(2026, 12, 1))


def test_legacy_column_follows_today(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 60, B: 40})
    assert db_session.query(EmployeeTeam.subgroup_id).filter_by(employee_id="e1").scalar() is None
    svc.set_record("e1", "T", None, {B: 100})
    assert db_session.query(EmployeeTeam.subgroup_id).filter_by(employee_id="e1").scalar() == B


def test_assign_employee_sets_base_record(db_session, team):
    TeamRegistryService(db_session).assign_employee("e1", "T", A)
    assert ss.load_team(db_session, "T")["e1"] == [ss.ShareRecord(None, ((A, 100),))]
    TeamRegistryService(db_session).assign_employee("e1", "T", None)
    assert ss.load_team(db_session, "T") == {}


def test_delete_subgroup_drops_whole_records(db_session, team):
    svc = SubgroupShareService(db_session)
    svc.set_record("e1", "T", None, {A: 100})
    svc.set_record("e1", "T", date(2026, 11, 15), {A: 60, B: 40})
    TeamRegistryService(db_session).delete_subgroup(B)
    assert [r.valid_from for r in ss.load_team(db_session, "T")["e1"]] == [None]
```

Run: `py -3.10 -m pytest tests/services/test_subgroup_share_service.py -q -p no:cacheprovider` → FAIL.

- [ ] **Step 2: Сервис записи**

`app/services/subgroup_share_service.py`:

```python
"""Запись распределения сотрудника по группам внутри команды.

Перевод — запись «100 % в новую группу» с даты, деление — запись с
несколькими группами. Запись с той же датой заменяется целиком.
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmployeeSubgroupShare, EmployeeTeam
from app.services import subgroup_shares as ss
from app.services.subgroup_resolver import SubgroupResolver


class SubgroupShareService:
    """Правка истории распределения. Каждая правка пересчитывает группы задач."""

    def __init__(self, db: Session):
        self.db = db

    def history(self, employee_id: str, team: str) -> ss.Records:
        return ss.load_team(self.db, team, [employee_id]).get(employee_id, [])

    def set_record(
        self,
        employee_id: str,
        team: str,
        valid_from: Optional[date],
        shares: dict[str, int],
    ) -> ss.Records:
        """Задать запись с даты (``None`` — с начала участия). Вернуть историю."""
        groups = dict(ss.team_subgroups(self.db, team))
        if not groups:
            raise ValueError("У команды нет деления на группы")
        if not shares:
            raise ValueError("Укажите хотя бы одну группу")
        for subgroup_id, percent in shares.items():
            if subgroup_id not in groups:
                raise ValueError("Группа не из этой команды")
            if not isinstance(percent, int) or not 1 <= percent <= 100:
                raise ValueError("Доля — целое число от 1 до 100")
        if sum(shares.values()) != 100:
            raise ValueError("Сумма долей должна быть 100%")
        member = (
            self.db.query(EmployeeTeam.id)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .first()
        )
        if member is None:
            raise ValueError("Сотрудник не состоит в команде")

        self._delete_rows(employee_id, team, valid_from)
        for subgroup_id, percent in shares.items():
            self.db.add(
                EmployeeSubgroupShare(
                    employee_id=employee_id,
                    team=team,
                    valid_from=valid_from,
                    subgroup_id=subgroup_id,
                    percent=percent,
                )
            )
        return self._finish(employee_id, team)

    def delete_record(
        self, employee_id: str, team: str, valid_from: Optional[date]
    ) -> ss.Records:
        """Удалить запись с этой датой. Вернуть историю."""
        if not self._delete_rows(employee_id, team, valid_from):
            raise LookupError("Запись не найдена")
        return self._finish(employee_id, team)

    def _delete_rows(
        self, employee_id: str, team: str, valid_from: Optional[date]
    ) -> int:
        q = self.db.query(EmployeeSubgroupShare).filter(
            EmployeeSubgroupShare.employee_id == employee_id,
            EmployeeSubgroupShare.team == team,
        )
        q = (
            q.filter(EmployeeSubgroupShare.valid_from.is_(None))
            if valid_from is None
            else q.filter(EmployeeSubgroupShare.valid_from == valid_from)
        )
        return q.delete(synchronize_session=False)

    def _finish(self, employee_id: str, team: str) -> ss.Records:
        self.db.flush()
        self._sync_legacy_column(employee_id, team)
        self.db.commit()
        # Группа человека — третья ступень лесенки группы задачи.
        SubgroupResolver(self.db).recompute_effective(team=team)
        return self.history(employee_id, team)

    def _sync_legacy_column(self, employee_id: str, team: str) -> None:
        """Переходный период: колонка группы у участия повторяет группу «на сегодня».

        Удаляется вместе с колонкой (задача 7 плана).
        """
        group = ss.single_group_on(self.history(employee_id, team), date.today())
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team
        ).update({EmployeeTeam.subgroup_id: group}, synchronize_session=False)
```

- [ ] **Step 3: Реестр групп**

В `app/services/team_registry_service.py`:

`assign_employee` — задаёт или снимает базовую запись «100 % с начала участия»:

```python
    def assign_employee(
        self, employee_id: str, team: str, subgroup_id: Optional[str]
    ) -> None:
        """Первая группа сотрудника: запись «100 % с начала участия».

        Переводы и деление задаются датированными записями через
        ``SubgroupShareService``; здесь меняется только базовая запись.
        """
        from app.services.subgroup_share_service import SubgroupShareService

        svc = SubgroupShareService(self.db)
        if subgroup_id:
            svc.set_record(employee_id, team, None, {subgroup_id: 100})
            return
        try:
            svc.delete_record(employee_id, team, None)
        except LookupError:
            pass
```

`delete_subgroup` — перед удалением группы удалить целиком записи, где она встречается (запись без неё не даёт 100 %; человек возвращается к предыдущей записи или попадает в «без группы»):

```python
        affected = (
            self.db.query(
                EmployeeSubgroupShare.employee_id,
                EmployeeSubgroupShare.team,
                EmployeeSubgroupShare.valid_from,
            )
            .filter(EmployeeSubgroupShare.subgroup_id == subgroup_id)
            .distinct()
            .all()
        )
        for emp_id, team, valid_from in affected:
            q = self.db.query(EmployeeSubgroupShare).filter(
                EmployeeSubgroupShare.employee_id == emp_id,
                EmployeeSubgroupShare.team == team,
            )
            q = (
                q.filter(EmployeeSubgroupShare.valid_from.is_(None))
                if valid_from is None
                else q.filter(EmployeeSubgroupShare.valid_from == valid_from)
            )
            q.delete(synchronize_session=False)
```

(добавить `EmployeeSubgroupShare` в импорт моделей; остальное тело `delete_subgroup` не менять).

Run: тесты шага 1 → PASS.

- [ ] **Step 4: Тесты API (падают)**

`tests/api/test_subgroup_shares_api.py` — посмотреть, как соседние API-тесты получают клиент (`grep -rn "def client" tests/conftest.py tests/api/conftest.py`), и использовать тот же фикстурный клиент. Сценарии:

```python
"""API истории распределения по группам и перевода между командами с группой."""

from datetime import date

from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_shares as ss

A, B = "g-a", "g-b"


def _seed(db):
    db.add_all([
        Team(id="t1", name="T", has_subgroups=True),
        Team(id="t0", name="Old", has_subgroups=False),
    ])
    db.flush()
    db.add_all([
        TeamSubgroup(id=A, team_id="t1", name="Ломбард", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="РФМ", sort_order=2),
        Employee(id="e1", jira_account_id="acc-1", display_name="Иванов", is_active=True),
    ])
    db.flush()
    db.add(EmployeeTeam(employee_id="e1", team="T", is_primary=True))
    db.commit()


def test_put_get_delete_record(client, db):
    _seed(db)
    r = client.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None, "shares": [{"subgroup_id": A, "percent": 100}],
    })
    assert r.status_code == 200
    r = client.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": "2026-11-15",
        "shares": [{"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40}],
    })
    assert r.json() == [
        {"valid_from": None, "shares": [{"subgroup_id": A, "percent": 100}]},
        {"valid_from": "2026-11-15", "shares": [
            {"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40},
        ]},
    ]
    assert client.get("/api/v1/teams/employees/e1/subgroup-shares", params={"team": "T"}).json() == r.json()
    r = client.delete(
        "/api/v1/teams/employees/e1/subgroup-shares",
        params={"team": "T", "valid_from": "2026-11-15"},
    )
    assert [x["valid_from"] for x in r.json()] == [None]


def test_put_rejects_bad_sum(client, db):
    _seed(db)
    r = client.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 50}, {"subgroup_id": B, "percent": 40}],
    })
    assert r.status_code == 422


def test_delete_missing_record_is_404(client, db):
    _seed(db)
    r = client.delete("/api/v1/teams/employees/e1/subgroup-shares", params={"team": "T"})
    assert r.status_code == 404


def test_transfer_into_divided_team_requires_group(client, db):
    _seed(db)
    db.add(EmployeeTeam(employee_id="e1", team="Old", is_primary=False))
    db.query(EmployeeTeam).filter_by(employee_id="e1", team="T").delete()
    db.commit()
    r = client.post("/api/v1/employees/e1/teams/transfer", json={
        "from_team": "Old", "to_team": "T", "on": "2026-11-01",
    })
    assert r.status_code == 422
    r = client.post("/api/v1/employees/e1/teams/transfer", json={
        "from_team": "Old", "to_team": "T", "on": "2026-11-01", "subgroup_id": B,
    })
    assert r.status_code == 200
    assert ss.load_team(db, "T")["e1"] == [ss.ShareRecord(date(2026, 11, 1), ((B, 100),))]


def test_team_items_carry_current_distribution(client, db):
    _seed(db)
    client.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40}],
    })
    items = client.get("/api/v1/employees/e1/teams").json()
    t = next(i for i in items if i["team"] == "T")
    assert t["subgroup_id"] is None
    assert t["subgroup_label"] == "Ломбард 60% · РФМ 40%"
```

Имена фикстур `client`/`db` заменить на принятые в соседних API-тестах (например `testclient_db_session` + клиент, как в `tests/api/test_issue_subgroup.py`).

Run → FAIL.

- [ ] **Step 5: Схемы и эндпойнты**

`app/schemas/team.py` — добавить:

```python
from datetime import date


class SubgroupShareItem(BaseModel):
    subgroup_id: str
    percent: int


class SubgroupShareRecordIn(BaseModel):
    team: str
    valid_from: Optional[date] = None
    shares: List[SubgroupShareItem]


class SubgroupShareRecordOut(BaseModel):
    valid_from: Optional[date] = None
    shares: List[SubgroupShareItem]
```

`app/api/endpoints/teams.py` — добавить (импорты `date`, `Optional`, `Query`, схемы, `SubgroupShareService`):

```python
def _records_out(records) -> List[SubgroupShareRecordOut]:
    return [
        SubgroupShareRecordOut(
            valid_from=r.valid_from,
            shares=[SubgroupShareItem(subgroup_id=g, percent=p) for g, p in r.shares],
        )
        for r in records
    ]


@router.get(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def get_subgroup_shares(
    employee_id: str, team: str = Query(...), db: Session = Depends(get_db)
) -> List[SubgroupShareRecordOut]:
    """История распределения сотрудника по группам команды."""
    return _records_out(SubgroupShareService(db).history(employee_id, team))


@router.put(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def put_subgroup_shares(
    employee_id: str, data: SubgroupShareRecordIn, db: Session = Depends(get_db)
) -> List[SubgroupShareRecordOut]:
    """Перевод или деление с даты. Запись с той же датой заменяется."""
    try:
        records = SubgroupShareService(db).set_record(
            employee_id,
            data.team,
            data.valid_from,
            {s.subgroup_id: s.percent for s in data.shares},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _records_out(records)


@router.delete(
    "/employees/{employee_id}/subgroup-shares",
    response_model=List[SubgroupShareRecordOut],
)
def delete_subgroup_share(
    employee_id: str,
    team: str = Query(...),
    valid_from: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> List[SubgroupShareRecordOut]:
    """Удалить ошибочную запись. Без даты — базовую «с начала участия»."""
    try:
        records = SubgroupShareService(db).delete_record(employee_id, team, valid_from)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _records_out(records)
```

Повторяющиеся группы в `shares` схлопнутся в словарь — это ок: сумма перестанет быть 100 и вернётся 422.

- [ ] **Step 6: Состав команд сотрудника и перевод**

`app/api/endpoints/employees.py`:

1. `EmployeeTeamItem` — поле `subgroup_id` остаётся (теперь вычисляемое: группа, если сегодня человек целиком в одной группе), добавить:

```python
    # Текущее распределение по группам: «Ломбард 60% · РФМ 40%». Пусто — нет группы.
    subgroup_label: Optional[str] = None
```

2. Помощник (импорты `from app.models import TeamSubgroup`, `from app.services import subgroup_shares as ss`):

```python
def _team_items(db: Session, rows) -> List[EmployeeTeamItem]:
    """Строки участия + группа на сегодня из истории распределения."""
    rows = list(rows)
    if not rows:
        return []
    today = date.today()
    records = ss.load_all(db, {r.employee_id for r in rows})
    names = dict(db.query(TeamSubgroup.id, TeamSubgroup.name).all())
    items: List[EmployeeTeamItem] = []
    for row in rows:
        item = EmployeeTeamItem.model_validate(row)
        rec = ss.record_on(records.get((row.employee_id, row.team), []), today)
        item.subgroup_id = rec.shares[0][0] if rec and len(rec.shares) == 1 else None
        item.subgroup_label = (
            " · ".join(
                f"{names.get(g, '?')}{f' {p}%' if p < 100 else ''}" for g, p in rec.shares
            )
            if rec
            else None
        )
        items.append(item)
    return items
```

3. Заменить все `EmployeeTeamItem.model_validate(...)`/списки из них на `_team_items(db, ...)`: в `list_employees` (`payload.teams = _team_items(db, teams)`), `get_teams`, `post_team` (`_team_items(db, [row])[0]`), `put_primary`, `put_teams`, `patch_joined_at`, `patch_left_at`, `post_transfer`.

4. Перевод:

```python
class TransferRequest(BaseModel):
    from_team: str
    to_team: str
    on: date
    # Обязательна, если у новой команды есть деление на группы.
    subgroup_id: Optional[str] = None
```

В `post_transfer` до `svc.transfer(...)`:

```python
    groups = dict(ss.team_subgroups(db, req.to_team))
    if groups and req.subgroup_id not in groups:
        raise HTTPException(status_code=422, detail="Выберите группу в новой команде")
```

после успешного `svc.transfer(...)`:

```python
    if groups:
        SubgroupShareService(db).set_record(
            employee_id, req.to_team, req.on, {req.subgroup_id: 100}
        )
```

Run: `py -3.10 -m pytest tests/api/test_subgroup_shares_api.py tests/services/test_subgroup_share_service.py tests/services/test_team_registry_service.py tests/test_api_employees_membership_periods.py -q -p no:cacheprovider` → PASS.

- [ ] **Step 7: Полный прогон** — как в задаче 1, шаг 8.

---

### Task 3: Ресурс сценария по долям, «без группы», блокировка утверждения

**Files:**
- Modify: `app/services/resource_base_service.py`
- Modify: `app/api/endpoints/planning.py` (`ResourceBaseEmployeeOut`, `ResourceSummaryOut`, `_subgroup_by_employee`, `approve_scenario`)
- Modify: `app/services/capacity_service.py` (удалить мёртвый `team_role_capacity_by_subgroup`)
- Modify: `tests/test_capacity_subgroup.py`, `tests/test_subgroups_disabled_regression.py`
- Test: `tests/test_resource_summary_subgroups.py` (дополнить), `tests/test_api_planning_subgroups.py` (дополнить)

- [ ] **Step 1: Тесты (падают)**

В `tests/test_resource_summary_subgroups.py` добавить (фикстура `two_groups`, `_dev`, `_scenario` уже есть; `share` из `tests/subgroup_fixtures.py`):

```python
def test_split_person_counts_by_share(db_session, two_groups):
    _dev(db_session, "e1")
    db_session.add(share("e1", TEAM, "sg-1", 60))
    db_session.add(share("e1", TEAM, "sg-2", 40))
    scenario = _scenario(db_session)
    db_session.commit()

    summary = ResourceBaseService(db_session).compute_summary(scenario)
    g1 = summary.gross_by_subgroup_role["sg-1"]["dev"]
    g2 = summary.gross_by_subgroup_role["sg-2"]["dev"]
    assert g1 == pytest.approx(summary.gross_by_role["dev"] * 0.6, abs=0.05)
    assert g1 + g2 == pytest.approx(summary.gross_by_role["dev"], abs=0.05)

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    assert emp.subgroup_id is None
    assert set(emp.subgroup_hours) == {"sg-1", "sg-2"}
    assert emp.subgroup_labels == {"sg-1": "60%", "sg-2": "40%"}


def test_transfer_mid_quarter_splits_by_days(db_session, two_groups):
    _dev(db_session, "e1")
    db_session.add(share("e1", TEAM, "sg-1"))
    db_session.add(share("e1", TEAM, "sg-2", valid_from=date(2026, 2, 1)))
    scenario = _scenario(db_session)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    jan = sum(d.hours for d in emp.days if d.date < date(2026, 2, 1))
    assert emp.subgroup_hours["sg-1"] == pytest.approx(jan, abs=0.05)
    assert emp.subgroup_hours["sg-1"] + emp.subgroup_hours["sg-2"] == pytest.approx(emp.total_hours, abs=0.05)
    assert emp.subgroup_labels == {"sg-1": "до 01.02", "sg-2": "с 01.02"}


def test_ungrouped_employees_listed(db_session, two_groups):
    _dev(db_session, "e1", "sg-1")
    _dev(db_session, "e2")
    scenario = _scenario(db_session)
    db_session.commit()

    summary = ResourceBaseService(db_session).compute_summary(scenario)
    assert [e["employee_id"] for e in summary.ungrouped_employees] == ["e2"]
```

В `tests/test_api_planning_subgroups.py` добавить тест утверждения (по образцу существующих вызовов API в этом файле): сценарий команды с делением, один сотрудник без группы → `POST /api/v1/planning/scenarios/{id}/approve` → 409, в `detail` его имя; после `db.add(share(...))` → 200.

Run → FAIL.

- [ ] **Step 2: `ResourceBaseService.compute`**

- Импорт: `from app.services import subgroup_shares as ss`.
- `EmployeeBase` — добавить поля (после `subgroup_id`):

```python
    # Часы по группам (ключ "" — дни без группы) и подписи участия в группе
    # за квартал («60%», «с 15.11»). Пусто — у команды нет деления.
    subgroup_hours: dict[str, float] = field(default_factory=dict)
    subgroup_labels: dict[str, str] = field(default_factory=dict)
```

- Вместо `_, emp_subgroup = self._team_subgroups(team)`:

```python
        # Распределение по группам. Пусто, если деления нет.
        has_groups = bool(ss.team_subgroups(self.db, team))
        share_records = (
            ss.load_team(self.db, team, [e.id for e in employees]) if has_groups else {}
        )
```

- В цикле по сотруднику: `records = share_records.get(e.id, [])`, `by_group: dict[str, float] = {}`; при добавлении дня:

```python
                hours = round(max(0.0, norm * pct - taken), 2)
                days_out.append(EmployeeDayHours(date=cur, hours=hours))
                if has_groups:
                    for key, part in ss.split_hours(records, cur, hours).items():
                        by_group[key] = by_group.get(key, 0.0) + part
```

- При сборке `EmployeeBase`:

```python
            groups = ss.groups_between(records, period_start, last_day) if has_groups else set()
            for g in groups:
                by_group.setdefault(g, 0.0)
            ...
                    subgroup_id=next(iter(groups)) if len(groups) == 1 and "" not in by_group else None,
                    subgroup_hours={k: round(v, 2) for k, v in by_group.items()},
                    subgroup_labels={
                        g: ss.group_label(records, g, period_start, last_day) for g in groups
                    },
```

- [ ] **Step 3: `ResourceBaseService.compute_summary`**

- `ResourceSummary` — добавить поле `ungrouped_employees: list[dict] = field(default_factory=list)  # [{employee_id, display_name}]`.
- Перед циклом валовых часов:

```python
        groups = ss.team_subgroups(self.db, team)
        share_records = (
            ss.load_team(self.db, team, [e.id for e in employees]) if groups else {}
        )
        # Часы и брони по группам: день делится по доле человека в этот день.
        gross_by_emp_group: dict[str, dict[str, float]] = {}
        booked_by_emp_group: dict[str, dict[str, float]] = {}
```

- Внутри цикла по дням, в ветке `if not on_absence:` после накоплений:

```python
                        if groups:
                            day_taken = min(emp_booked.get(cur, 0.0), norm * share)
                            for key, part in ss.split_hours(
                                share_records.get(e.id, []), cur, 1.0
                            ).items():
                                eg = gross_by_emp_group.setdefault(e.id, {})
                                eg[key] = eg.get(key, 0.0) + norm * part
                                eb = booked_by_emp_group.setdefault(e.id, {})
                                eb[key] = eb.get(key, 0.0) + day_taken * part
```

- Блок «разрез по группам» заменить:

```python
        subgroups = [{"id": g, "name": n} for g, n in groups]
        gross_by_subgroup_role: dict[str, dict[str, float]] = {}
        available_by_subgroup_role: dict[str, dict[str, float]] = {}
        if subgroups:
            sub_wts = [wt for wt in work_types if wt.subtracts_from_pool]

            def emp_net(emp_id: str) -> float:
                ...  # без изменений

            booked_by_subgroup_role: dict[str, dict[str, float]] = {}
            net_by_subgroup_role: dict[str, dict[str, float]] = {}
            net_people_by_role: dict[str, float] = {}
            for emp_id, per_group in gross_by_emp_group.items():
                role = emp_role[emp_id]
                if not role:
                    continue
                # Внешний QA задан вручную на всю команду и группе не принадлежит.
                if role == "qa" and scenario.external_qa_hours is not None:
                    continue
                emp_gross = gross_by_emp[emp_id]
                net_total = emp_net(emp_id)
                for sg_key, hours in per_group.items():
                    bucket = gross_by_subgroup_role.setdefault(sg_key, {})
                    bucket[role] = round(bucket.get(role, 0.0) + hours, 2)
                    taken_bucket = booked_by_subgroup_role.setdefault(sg_key, {})
                    taken_bucket[role] = taken_bucket.get(role, 0.0) + booked_by_emp_group[emp_id].get(sg_key, 0.0)
                    net = net_total * (hours / emp_gross) if emp_gross else 0.0
                    net_bucket = net_by_subgroup_role.setdefault(sg_key, {})
                    net_bucket[role] = net_bucket.get(role, 0.0) + net
                    net_people_by_role[role] = net_people_by_role.get(role, 0.0) + net

            for sg_key, roles in gross_by_subgroup_role.items():
                ...  # без изменений
```

- Перед `return ResourceSummary(...)`:

```python
        ungrouped = ss.ungrouped_members(self.db, team, period_start, last_day)
        ungrouped_employees = [
            {"employee_id": emp_id, "display_name": emp_name.get(emp_id, emp_id)}
            for emp_id in ungrouped
        ]
```

и `ungrouped_employees=ungrouped_employees` в конструктор.

- Удалить `_team_subgroups` (больше не используется).

- [ ] **Step 4: Выдача и опорный день в `planning.py`**

- `ResourceBaseEmployeeOut`: `subgroup_hours: Dict[str, float] = {}`, `subgroup_labels: Dict[str, str] = {}`; в сборке — `subgroup_hours=getattr(e, "subgroup_hours", {}) or {}`, `subgroup_labels=getattr(e, "subgroup_labels", {}) or {}`.
- `ResourceSummaryOut`: `ungrouped_employees: List[Dict] = []`; в сборке `ungrouped_employees=summary.ungrouped_employees`.
- `_subgroup_by_employee(db, team)` → принимает сценарий:

```python
def _scenario_bounds(scenario: PlanningScenario) -> Optional[tuple[date, date]]:
    if not (scenario.year and scenario.quarter):
        return None
    months = QUARTER_MONTHS[int(str(scenario.quarter).replace("Q", ""))]
    return (
        date(scenario.year, months[0], 1),
        date(scenario.year, months[-1], calendar.monthrange(scenario.year, months[-1])[1]),
    )


def _subgroup_by_employee(db: Session, scenario: PlanningScenario) -> dict:
    """Группа сотрудника на опорный день квартала — для идей без задачи.

    Опорный день — сегодня, прижатый к границам квартала сценария. Поделённый
    между группами группы не получает: его идея остаётся «Без группы».
    """
    if not ss.team_subgroups(db, scenario.team):
        return {}
    bounds = _scenario_bounds(scenario)
    day = date.today() if bounds is None else min(max(date.today(), bounds[0]), bounds[1])
    out = {}
    for emp_id, records in ss.load_team(db, scenario.team).items():
        group = ss.single_group_on(records, day)
        if group:
            out[emp_id] = group
    return out
```

Все четыре вызова `_subgroup_by_employee(db, scenario.team)` → `_subgroup_by_employee(db, scenario)`. Импорты `calendar`, `date`, `ss` — проверить, что есть; `EmployeeTeam` удалить из импортов, если стал не нужен.

- `approve_scenario` — сразу после `_require_draft(scenario)`:

```python
    bounds = _scenario_bounds(scenario)
    if scenario.team and bounds:
        missing = ss.ungrouped_members(db, scenario.team, *bounds)
        if missing:
            names = [
                n for (n,) in db.query(Employee.display_name)
                .filter(Employee.id.in_(missing))
                .order_by(Employee.display_name)
            ]
            raise HTTPException(
                status_code=409,
                detail="Нельзя утвердить: у сотрудников нет группы — " + ", ".join(names),
            )
```

- [ ] **Step 5: Мёртвый код ёмкости по группам**

`CapacityService.team_role_capacity_by_subgroup` в приложении не вызывается (только тесты) и читает колонку группы. Удалить метод, удалить `tests/test_capacity_subgroup.py` целиком, если в нём нет других тестов (иначе — только тесты метода), и строку `assert svc.team_role_capacity_by_subgroup(...) == {}` в `tests/test_subgroups_disabled_regression.py`. Упомянуть в отчёте.

- [ ] **Step 6: Прогон** — тесты шага 1 → PASS; затем полный прогон.

---

### Task 4: Снимок утверждения и плашка расхождения по группам

**Files:**
- Modify: `app/services/snapshot_writer.py`
- Modify: `app/schemas/capacity_diff.py`, `app/api/endpoints/planning.py` (`get_capacity_diff`)
- Test: `tests/test_scenario_subgroup_snapshot.py` (дополнить)

- [ ] **Step 1: Тесты (падают)**

В `tests/test_scenario_subgroup_snapshot.py` (по образцу существующих тестов файла):
1. сотрудник 60/40 весь квартал → в снимке `subgroup_name == "<A> 60% · <B> 40%"`;
2. сотрудник целиком в группе → `subgroup_name == "<A>"` (как раньше);
3. после утверждения добавить запись «с даты внутри квартала — 100 % в B» → `GET /planning/scenarios/{id}/capacity-diff` отдаёт `has_changes: true`, у сотрудника `subgroup_before == "<A>"`, `subgroup_after == "<A> до dd.mm · <B> с dd.mm"`;
4. ревизия, где у всех `subgroup_name` пусто (деление включили после утверждения), расхождения по группам не даёт.

Run → FAIL.

- [ ] **Step 2: Снимок**

В `SnapshotWriter` заменить `_subgroup_names(team)` на:

```python
    def _subgroup_labels(self, scenario: PlanningScenario) -> dict[str, str]:
        """Сотрудник → распределение по группам за квартал сценария.

        «Ломбард» — весь квартал в одной группе (так выглядят и старые снимки),
        «Ломбард 60% · РФМ 40%» или «Ломбард до 15.11 · РФМ с 15.11» — иначе.
        Пусто, если у команды нет деления.
        """
        if not (scenario.team and scenario.year and scenario.quarter):
            return {}
        start, end = _quarter_bounds(scenario.year, scenario.quarter)
        return ss.quarter_labels(self.db, scenario.team, start, end)
```

и в записи снимка `subgroups = self._subgroup_labels(scenario)`. Импорт `from app.services import subgroup_shares as ss`.

- [ ] **Step 3: Расхождение**

`app/schemas/capacity_diff.py`, `EmployeeDiff`:

```python
    # Распределение по группам на момент утверждения и сейчас, если изменилось.
    subgroup_before: str | None = None
    subgroup_after: str | None = None
```

В `get_capacity_diff`:

```python
    # Распределение по группам: снимок утверждения vs сейчас. Сравниваем, только
    # если деление было на момент утверждения — иначе все люди команды
    # оказались бы «изменёнными».
    team_snaps = {
        s.employee_id: s.subgroup_name
        for s in db.query(ScenarioTeamSnapshot)
        .filter(ScenarioTeamSnapshot.revision_id == revision.id)
        .all()
        if s.employee_id
    }
    group_changes: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if scenario.team and any(team_snaps.values()):
        current_labels = ss.quarter_labels(db, scenario.team, quarter_start, quarter_end)
        for emp_id, before in team_snaps.items():
            after = current_labels.get(emp_id)
            if before != after:
                group_changes[emp_id] = (before, after)
```

Этот блок поставить после вычисления `quarter_start/quarter_end`; `emp_ids` дополнить `| set(group_changes)` **до** раннего выхода `if not emp_ids` (перенести расчёт `team_snaps`/`group_changes` выше этого выхода, а границы квартала — ещё выше). Условие добавления сотрудника: `if month_diffs or left_at or emp_id in group_changes:`; в `EmployeeDiff(...)` — `subgroup_before=group_changes.get(emp_id, (None, None))[0]`, `subgroup_after=group_changes.get(emp_id, (None, None))[1]`. Импорты `ScenarioTeamSnapshot`, `ss`.

- [ ] **Step 4: Прогон** — тесты файла → PASS; полный прогон.

---

### Task 5: Группа задачи по дате, переток по дате списания, фильтр витрин за период

**Files:**
- Modify: `app/services/subgroup_resolver.py`
- Modify: `app/services/subgroup_flow_service.py`
- Modify: `app/services/subgroup_filter.py`
- Modify: `app/api/endpoints/analytics.py`, `app/services/analytics_service.py`, `app/services/kpi/kpi_service.py` (передать период)
- Test: `tests/services/test_subgroup_resolver.py`, `tests/services/test_subgroup_effective.py`, `tests/test_subgroup_flow.py`, `tests/services/test_subgroup_filter.py` (дополнить)

- [ ] **Step 1: Тесты (падают)**

Резолвер (`tests/services/test_subgroup_resolver.py`, по образцу файла; `SubgroupResolver(db, today=date(2026, 12, 1))`):
1. записи: `None → A 100`, `2026-11-15 → B 100`. Закрытая задача без явной группы с `resolved_at=datetime(2026, 11, 1)` → угадана `A`; открытая (`resolved_at=None`) → `B`.
2. запись `None → A 60 / B 40`: у задачи этого исполнителя без явной группы и без группы у родителей группы нет (`source == "none"`).
3. `recompute_effective` даёт то же (материализация идёт через `_walk`).

Переток (`tests/test_subgroup_flow.py`):
1. переведённый 15.11 из A в B: ворклог 10.11 на задачу группы B → `out` у A = часы, `in` у B = часы; ворклог 20.11 на задачу B → перетока нет.
2. общий A 60 / B 40: ворклог на задачу B → перетока нет; ворклог на задачу группы C → `out` A = 0.6·h, `out` B = 0.4·h, `in` C = h.

Фильтр (`tests/services/test_subgroup_filter.py`):
1. `employee_ids(db, [B], ["T"], start, end)` включает переведённого в B 15.11, если период задевает дни после 15.11, и не включает, если период целиком до 15.11.
2. общий A/B попадает и в выборку `[A]`, и в `[B]`.
3. `"__none__"` включает участника без записи и участника, у которого первая запись начинается позже начала периода.

Run → FAIL.

- [ ] **Step 2: Резолвер**

В `app/services/subgroup_resolver.py`:

```python
from datetime import date, datetime
...
from app.models import Employee, Issue, Team
from app.services import subgroup_shares as ss
```

```python
    def __init__(self, db: Session, today: Optional[date] = None):
        self.db = db
        self._today = today or date.today()
        self._enabled_teams: Optional[set[str]] = None
        self._subgroup_team: dict[str, str] = {}
        # (account_id, команда) -> записи распределения исполнителя
        self._records: dict[tuple[str, str], ss.Records] = {}
```

В `_load` заменить сбор `_by_account`:

```python
        account_of = dict(self.db.query(Employee.id, Employee.jira_account_id).all())
        for (emp_id, team_name), records in ss.load_all(self.db).items():
            account_id = account_of.get(emp_id)
            if account_id:
                self._records[(account_id, team_name)] = records
```

Новый метод:

```python
    def _guess(
        self, account_id: Optional[str], team: str, resolved_at: Optional[datetime]
    ) -> Optional[str]:
        """Группа исполнителя на дату: закрытая задача — на дату закрытия, открытая — на сегодня.

        Поделённый между группами в этот день исполнитель группу не даёт.
        """
        records = self._records.get((account_id or "", team))
        if not records:
            return None
        day = resolved_at.date() if resolved_at else self._today
        group = ss.single_group_on(records, day)
        return group if self._valid(group, team) else None
```

`resolve_for_issue`, шаг 3: `guess = self._guess(issue.assignee_account_id, team, issue.resolved_at)`; `if guess: return SubgroupResolution(subgroup_id=guess, source=SubgroupSource.GUESS)`.

`_walk(...)` — добавить параметр `resolved_at: Optional[datetime]` и в конце `return self._guess(account_id, team, resolved_at)`. В `recompute_effective` запрос: `Issue.id, Issue.team, Issue.assignee_account_id, Issue.resolved_at, Issue.effective_subgroup_id`, цикл `for iid, team_name, account_id, resolved_at, current in q.all():` и вызов `_walk(iid, team_name, account_id, resolved_at, parents, assigned)`. Обновить docstring модуля: «3. Предположение по исполнителю — его группа на дату закрытия задачи (открытой — на сегодня); поделённый между группами — без предположения».

- [ ] **Step 3: Переток**

`flow_for_team` — заменить карту `emp_group` и агрегат:

```python
    records = ss.load_team(db, team)

    rows = (
        db.query(
            Worklog.employee_id,
            Issue.effective_subgroup_id,
            Worklog.started_at,
            Worklog.hours,
        )
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(
            Issue.team == team,
            Issue.effective_subgroup_id.isnot(None),
            Worklog.started_at >= datetime.combine(from_, datetime.min.time()),
            Worklog.started_at <= datetime.combine(to_, datetime.max.time()),
        )
        .all()
    )

    acc: dict[str, dict[str, float]] = {gid: {"out": 0.0, "in": 0.0} for gid in names}
    for employee_id, issue_group, started_at, hours in rows:
        if issue_group not in acc:
            continue
        # Группа человека — на дату списания. Без группы и чужак из другой
        # команды перетоком не считаются: у первого нет группы-источника,
        # второй — помощь извне. Работа в любой своей группе — не переток.
        shares = ss.shares_on(records.get(employee_id, []), started_at.date())
        if not shares or issue_group in shares:
            continue
        h = float(hours or 0)
        for group, part in shares.items():
            if group in acc:
                acc[group]["out"] += h * part
        acc[issue_group]["in"] += h
```

Убрать импорт `EmployeeTeam`, `func`, если стали не нужны; добавить `from app.services import subgroup_shares as ss`. Обновить docstring модуля: группа человека берётся на дату списания; общий сотрудник в своих группах — не переток, вне их «ушло» делится по долям.

- [ ] **Step 4: Фильтр витрин**

`app/services/subgroup_filter.py`, `employee_ids`:

```python
def employee_ids(
    db: Session,
    subgroups: Optional[list[str]],
    teams: Optional[list[str]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Optional[set[str]]:
    """Сотрудники, у которых была доля в выбранных группах за период. ``None`` — фильтр не задан.

    Период по умолчанию — сегодня. Общий сотрудник попадает в каждую свою
    группу целиком — его показатели не делятся. ``teams`` нужен только для
    «Без группы»: неприписанного ищем среди участников выбранных команд.
    """
    if not subgroups:
        return None
    ids, has_none = _split(subgroups)
    start = start or date.today()
    end = end or start

    out: set[str] = set()
    if ids:
        wanted = set(ids)
        for (emp_id, _), records in ss.load_all(db).items():
            if ss.groups_between(records, start, end) & wanted:
                out.add(emp_id)
    if has_none:
        team_names = teams or [t for (t,) in db.query(EmployeeTeam.team).distinct()]
        for team in team_names:
            intervals = tm.member_intervals(db, [team], start, end)
            records = ss.load_team(db, team, intervals.keys())
            for emp_id, spans in intervals.items():
                if ss.record_on(records.get(emp_id, []), spans[0][0]) is None:
                    out.add(emp_id)
    return out
```

Импорты `date`, `ss`, `tm`; обновить docstring модуля («всё „на человека“ — по распределению сотрудника за период»).

Передать период вызывающим:
- `app/api/endpoints/analytics.py` (баланс часов): `subgroup_employee_ids(db, parse_subgroups_csv(subgroups), team_ids, resolved_from, resolved_to)`;
- `app/services/analytics_service.py` (нормированные работы): `sgf.employee_ids(self.db, subgroups, teams, period_start, period_end)`;
- `app/services/kpi/kpi_service.py`: границы отчёта —

```python
    last_month = month + months - 1
    period_start = date(year, month, 1)
    period_end = date(year, last_month, calendar.monthrange(year, last_month)[1])
    in_subgroups = sgf.employee_ids(db, subgroups, teams, period_start, period_end)
```

- стол тимлида (`app/api/endpoints/team_desk.py`) — без изменений: период по умолчанию «сегодня» совпадает с составом на сегодня.

- [ ] **Step 5: Прогон** — тесты шага 1 и файлы витрин (`tests/test_dashboard_subgroups.py tests/test_people_views_subgroups.py tests/test_export_subgroups.py tests/test_projects_backlog_subgroups.py`) → PASS; полный прогон.

---

### Task 6: Ресурсное планирование — свои группы за квартал, метка «соседняя группа»

**Files:**
- Modify: `app/services/resource_planning_service.py` (`_subgroup_context`, `_assign_employees`, `_pick_in_group`)
- Modify: `app/api/endpoints/resource_planning.py` (`AssignmentOut`, `_assignment_to_out`, сборка списка назначений)
- Test: `tests/test_rp_subgroup_assignment.py` (дополнить)

- [ ] **Step 1: Тесты (падают)**

В `tests/test_rp_subgroup_assignment.py` (по образцу `test_dev_from_own_subgroup` и `_pick_in_group` через сервис):
1. общий A 60 / B 40 — «свой» и для задачи группы A, и для задачи группы B (подбирается раньше соседа из третьей группы при равной загрузке);
2. `_pick_in_group` с картой множеств: `emp_group={"e1": {"A", "B"}, "e2": {"C"}}` → для группы `B` выбирается `e1`.

Метка в выдаче плана (API-тест в том же файле или `tests/test_api_rp_*` по образцу): назначение, у которого группа задачи не входит в группы исполнителя за даты назначения → `other_subgroup == true`; назначение своей группы → `false`; команда без деления → всегда `false`.

Run → FAIL.

- [ ] **Step 2: Контекст групп**

`_subgroup_context(self, plan, employees, items, q_start, q_end)` → `Tuple[Dict[str, Set[str]], Dict[str, str]]`:

```python
        """({сотрудник: его группы в квартале}, {item_id: группа}) для команды с делением.

        «Свои» для группы — все, у кого в квартале плана есть в ней доля: общий
        сотрудник свой для всех своих групп, переведённый внутри квартала — для
        обеих. Доля — ориентир, не лимит, поэтому ёмкость не режется по группам.
        Группа инициативы без своей — группа главного исполнителя на опорный
        день (сегодня, прижатый к кварталу); у поделённого — нет.
        """
        if not ss.team_subgroups(self.db, plan.team):
            return {}, {}
        records = ss.load_team(self.db, plan.team, [e.id for e in employees])
        emp_groups = {
            eid: groups
            for eid, recs in records.items()
            if (groups := ss.groups_between(recs, q_start, q_end))
        }
        ref_day = min(max(date.today(), q_start), q_end)
        item_group: Dict[str, str] = {}
        for it in items:
            gid = getattr(it.issue, "effective_subgroup_id", None) if it.issue else None
            if not gid and it.assignee_employee_id:
                gid = ss.single_group_on(records.get(it.assignee_employee_id, []), ref_day)
            if gid:
                item_group[it.id] = gid
        return emp_groups, item_group
```

Вызов (около строки 771): `self._subgroup_context(plan, employees, items, q_start, q_end)` — `q_start/q_end` уже есть в `compute_schedule` (используются в `quarter_capacity`); если объявлены ниже вызова — перенести объявление выше.

`_assign_employees(..., emp_group: Optional[Dict[str, Set[str]]] = None, ...)` и `_pick_in_group(..., emp_group: Dict[str, Set[str]], ...)`; в `_pick_in_group`:

```python
        own = [eid for eid in pool if group in emp_group.get(eid, ())]
```

Удалить `EmployeeTeam` из импортов модуля, если стал не нужен; добавить `from app.services import subgroup_shares as ss`, `Set` в typing.

- [ ] **Step 3: Метка в выдаче**

`AssignmentOut`:

```python
    # Исполнитель работает на группу, где у него нет доли в дни назначения
    # (задача старой группы после перевода или сосед, взятый на подмогу).
    other_subgroup: bool = False
```

`_assignment_to_out(..., other_subgroup: bool = False)` → `other_subgroup=other_subgroup`.

Помощник в `resource_planning.py`:

```python
def _other_subgroup_ids(db: Session, plan, assignments) -> set:
    """Назначения, где группа задачи не входит в группы исполнителя за даты назначения."""
    if not ss.team_subgroups(db, plan.team):
        return set()
    records = ss.load_team(db, plan.team, {a.employee_id for a in assignments if a.employee_id})
    out = set()
    for a in assignments:
        issue = a.backlog_item.issue if a.backlog_item else None
        group = getattr(issue, "effective_subgroup_id", None) if issue else None
        recs = records.get(a.employee_id) if a.employee_id else None
        if not group or not recs or not a.start_date or not a.end_date:
            continue
        if group not in ss.groups_between(recs, a.start_date, a.end_date):
            out.add(a.id)
    return out
```

В сборке списка (около строки 1686): `other = _other_subgroup_ids(db, plan, assignments_raw)` и `other_subgroup=a.id in other` в вызове `_assignment_to_out`.

- [ ] **Step 4: Прогон** — `py -3.10 -m pytest tests/test_rp_subgroup_assignment.py tests -k "rp or resource_plan" -q -p no:cacheprovider`, затем полный прогон.

---

### Task 7: Удалить колонку группы у участия

**Files:**
- Create: `alembic/versions/sg02_drop_employee_team_subgroup.py`
- Modify: `app/models/employee_team.py`, `app/services/subgroup_share_service.py` (убрать `_sync_legacy_column`), `app/services/team_registry_service.py` (убрать обнуление колонки в `delete_subgroup`)
- Modify: все тестовые фикстуры с `EmployeeTeam(..., subgroup_id=...)`; `tests/services/test_team_registry_service.py::test_membership_carries_subgroup`; `tests/services/test_subgroup_share_service.py::test_legacy_column_follows_today`
- Test: `tests/test_migration_sg02_drop_employee_team_subgroup.py`

- [ ] **Step 1: Проверка, что колонку больше никто не читает**

Run: `grep -rn "EmployeeTeam.subgroup_id\|\.subgroup_id" app --include=*.py | grep -v "effective_subgroup_id\|assigned_subgroup_id"` — оставшиеся попадания должны быть только про группу задачи/строки (`resolution.subgroup_id`, `target.subgroup_id`, `f.subgroup_id`, модель доли). Всё, что про участие, — доделать до удаления.

- [ ] **Step 2: Тест миграции (падает)**

```python
"""sg02: колонка группы у участия удалена, данные — в распределении."""
# импорты и _alembic — как в test_migration_sg01_subgroup_shares.py
PREV = "sg01_subgroup_shares"
REV = "sg02_drop_employee_team_subgroup"


def _columns(url):
    engine = sa.create_engine(url)
    with engine.connect() as c:
        cols = {x["name"] for x in sa.inspect(c).get_columns("employee_teams")}
    engine.dispose()
    return cols


def test_drop_and_restore(tmp_path):
    url = f"sqlite:///{(tmp_path / 'sg02.db').as_posix()}"
    _alembic(url, "upgrade", REV)
    assert "subgroup_id" not in _columns(url)
    _alembic(url, "downgrade", PREV)
    assert "subgroup_id" in _columns(url)
    _alembic(url, "upgrade", REV)
    assert "subgroup_id" not in _columns(url)


def test_upgrade_tolerates_missing_column(tmp_path):
    """Dev-база от create_all может не иметь колонки."""
    url = f"sqlite:///{(tmp_path / 'sg02b.db').as_posix()}"
    _alembic(url, "upgrade", REV)
    _alembic(url, "stamp", PREV)
    _alembic(url, "upgrade", REV)
```

- [ ] **Step 3: Миграция**

```python
"""employee_teams.subgroup_id удалена: группа сотрудника — в employee_subgroup_shares

Revision ID: sg02_drop_employee_team_subgroup
Revises: sg01_subgroup_shares
Create Date: 2026-09-29

Самодостаточна. Колонки может не быть (dev-база от create_all).
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sg02_drop_employee_team_subgroup"
down_revision: Union[str, None] = "sg01_subgroup_shares"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists() -> bool:
    if context.is_offline_mode():
        return True
    cols = sa.inspect(op.get_bind()).get_columns("employee_teams")
    return any(c["name"] == "subgroup_id" for c in cols)


def upgrade() -> None:
    if not _column_exists():
        return
    insp = sa.inspect(op.get_bind())
    fk_names = [
        fk["name"] for fk in insp.get_foreign_keys("employee_teams")
        if fk.get("constrained_columns") == ["subgroup_id"] and fk.get("name")
    ]
    index_names = [
        ix["name"] for ix in insp.get_indexes("employee_teams")
        if ix.get("column_names") == ["subgroup_id"]
    ]
    with op.batch_alter_table("employee_teams", schema=None) as batch_op:
        for name in fk_names:
            batch_op.drop_constraint(name, type_="foreignkey")
        for name in index_names:
            batch_op.drop_index(name)
        batch_op.drop_column("subgroup_id")


def downgrade() -> None:
    with op.batch_alter_table("employee_teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subgroup_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_employee_teams_subgroup_id", ["subgroup_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_employee_teams_subgroup", "team_subgroups",
            ["subgroup_id"], ["id"], ondelete="SET NULL",
        )
    # Вернуть базовую группу «100 % с начала участия».
    bind = op.get_bind()
    sh = sa.table(
        "employee_subgroup_shares",
        sa.column("employee_id"), sa.column("team"), sa.column("valid_from"),
        sa.column("subgroup_id"), sa.column("percent"),
    )
    et = sa.table("employee_teams", sa.column("employee_id"), sa.column("team"), sa.column("subgroup_id"))
    for emp_id, team, subgroup_id in bind.execute(
        sa.select(sh.c.employee_id, sh.c.team, sh.c.subgroup_id).where(
            sh.c.valid_from.is_(None), sh.c.percent == 100
        )
    ):
        bind.execute(
            et.update()
            .where(et.c.employee_id == emp_id, et.c.team == team)
            .values(subgroup_id=subgroup_id)
        )
```

- [ ] **Step 4: Модель и сервисы**

- `app/models/employee_team.py`: удалить поле `subgroup_id` и его комментарий; в docstring класса добавить строку «Группа внутри команды — в ``EmployeeSubgroupShare`` (история с датами)».
- `SubgroupShareService`: удалить `_sync_legacy_column` и его вызов в `_finish`.
- `TeamRegistryService.delete_subgroup`: удалить обновление `EmployeeTeam.subgroup_id`; убрать `EmployeeTeam` из импорта, если не нужен (нужен в `sync_names` — оставить).

- [ ] **Step 5: Фикстуры**

Во всех тестах из задачи 1, шаг 7: удалить аргумент `subgroup_id=...` у `EmployeeTeam(...)` (строка `share(...)` уже добавлена). `test_membership_carries_subgroup` переписать на проверку строки распределения:

```python
def test_membership_group_lives_in_shares(db_session):
    ...  # та же подготовка, без subgroup_id у EmployeeTeam
    db_session.add(share(emp.id, team.name, group.id))
    db_session.commit()
    assert ss.load_team(db_session, team.name)[emp.id] == [ss.ShareRecord(None, ((group.id, 100),))]
```

`test_legacy_column_follows_today` — удалить. Run: `grep -rn "EmployeeTeam(" tests | grep "subgroup_id"` → пусто.

- [ ] **Step 6: Прогон**

1. `py -3.10 -m pytest tests -q -p no:cacheprovider --ignore=tests/api/test_llm.py` → зелёный.
2. Миграции на копии локальной базы: `copy data\jira_analytics.db data\sg-check.db`, затем `DATABASE_URL=sqlite:///data/sg-check.db py -3.10 -m alembic upgrade head`; проверить, что у «Команда 1С (Бухгалтерия)» 12 сотрудников получили записи «100 %», у троих без группы записей нет. Удалить `data\sg-check.db`.
3. Postgres: `.\scripts\run_tests_postgres.ps1 -k "subgroup or migration"` (нужен Docker; если недоступен — написать об этом в отчёте, не пропускать молча).

---

### Task 8: Интерфейс — карточка сотрудника, перевод, «Ресурсы»

**Files:**
- Modify: `frontend/src/types/api.ts`, `frontend/src/api/teams.ts`, `frontend/src/api/employees.ts`
- Modify: `frontend/src/hooks/useTeamRegistry.ts`, `frontend/src/hooks/useCapacity.ts`
- Create: `frontend/src/components/capacity/SubgroupShareModal.tsx`
- Modify: `frontend/src/components/capacity/EmployeeDrawer.tsx`, `frontend/src/components/capacity/TransferTeamModal.tsx`
- Modify: `frontend/src/pages/CapacityPage.tsx`

- [ ] **Step 1: Типы и API**

`types/api.ts`, `EmployeeTeamItem`:

```ts
  /** Группа, если сегодня сотрудник целиком в одной группе; иначе null. */
  subgroup_id?: string | null;
  /** Текущее распределение: «Ломбард 60% · РФМ 40%». null — группы нет. */
  subgroup_label?: string | null;
```

Там же:

```ts
export interface SubgroupShareItem {
  subgroup_id: string;
  percent: number;
}

export interface SubgroupShareRecord {
  /** null — «с начала участия». */
  valid_from: string | null;
  shares: SubgroupShareItem[];
}
```

`api/teams.ts`:

```ts
export const getSubgroupShares = (employeeId: string, team: string) =>
  api.get<SubgroupShareRecord[]>(
    `/teams/employees/${employeeId}/subgroup-shares?team=${encodeURIComponent(team)}`,
  );

export const putSubgroupShare = (
  employeeId: string,
  body: { team: string; valid_from: string | null; shares: SubgroupShareItem[] },
) => api.put<SubgroupShareRecord[]>(`/teams/employees/${employeeId}/subgroup-shares`, body);

export const deleteSubgroupShare = (employeeId: string, team: string, validFrom: string | null) =>
  api.del<SubgroupShareRecord[]>(
    `/teams/employees/${employeeId}/subgroup-shares?team=${encodeURIComponent(team)}`
      + (validFrom ? `&valid_from=${validFrom}` : ''),
  );
```

Проверить сигнатуры `api.get/put/del` в `frontend/src/api/client.ts` (возвращают ли `del` тело) и подстроиться.

`api/employees.ts`, `transferEmployeeTeam` — тело `{ from_team; to_team; on; subgroup_id?: string | null }`; `useTransferEmployeeTeam` в `hooks/useCapacity.ts` — пробросить `subgroup_id`.

- [ ] **Step 2: Хуки**

`hooks/useTeamRegistry.ts`:

```ts
export const useSubgroupShares = (employeeId: string | null, team: string | null) =>
  useQuery({
    queryKey: ['subgroup-shares', employeeId, team],
    queryFn: () => getSubgroupShares(employeeId!, team!),
    enabled: !!employeeId && !!team,
  });

// Распределение меняет группы задач, ресурс сценария и витрины.
const invalidateShares = (qc: QueryClient) => {
  qc.invalidateQueries({ queryKey: ['subgroup-shares'] });
  qc.invalidateQueries({ queryKey: ['employees'] });
  qc.invalidateQueries({ queryKey: ['employee'] });
  qc.invalidateQueries({ queryKey: ['capacity'] });
  qc.invalidateQueries({ queryKey: ['planning'] });
  qc.invalidateQueries({ queryKey: ['resource-planning'] });
};

export const usePutSubgroupShare = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { employeeId: string; team: string; valid_from: string | null; shares: SubgroupShareItem[] }) =>
      putSubgroupShare(v.employeeId, { team: v.team, valid_from: v.valid_from, shares: v.shares }),
    onSuccess: () => invalidateShares(qc),
  });
};

export const useDeleteSubgroupShare = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { employeeId: string; team: string; valid_from: string | null }) =>
      deleteSubgroupShare(v.employeeId, v.team, v.valid_from),
    onSuccess: () => invalidateShares(qc),
  });
};
```

Ключ `['resource-planning']` сверить с реальными ключами запросов плана (`grep -rn "queryKey: \[" frontend/src/hooks/useResourcePlanning*`) и использовать настоящий префикс.

- [ ] **Step 3: Окно «Перевести в группу / Разделить»**

`components/capacity/SubgroupShareModal.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { App, DatePicker, InputNumber, Modal, Select, Space, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

import { usePutSubgroupShare } from '../../hooks/useTeamRegistry';

const { Text } = Typography;

interface Props {
  employeeId: string;
  team: string;
  subgroups: { id: string; name: string }[];
  /** transfer — одна группа 100 %, split — проценты по группам. */
  mode: 'transfer' | 'split';
  onClose: () => void;
}

export default function SubgroupShareModal({ employeeId, team, subgroups, mode, onClose }: Props) {
  const { message } = App.useApp();
  const put = usePutSubgroupShare();
  const [on, setOn] = useState<Dayjs | null>(dayjs());
  const [group, setGroup] = useState<string | null>(null);
  const [pct, setPct] = useState<Record<string, number | null>>({});

  useEffect(() => setPct({}), [mode]);

  const shares = mode === 'transfer'
    ? (group ? [{ subgroup_id: group, percent: 100 }] : [])
    : Object.entries(pct)
        .filter(([, v]) => (v ?? 0) > 0)
        .map(([subgroup_id, v]) => ({ subgroup_id, percent: v as number }));
  const total = shares.reduce((s, x) => s + x.percent, 0);
  const valid = !!on && shares.length > 0 && total === 100
    && (mode === 'transfer' || shares.length >= 2);

  const handleOk = async () => {
    try {
      await put.mutateAsync({
        employeeId, team, valid_from: on!.format('YYYY-MM-DD'), shares,
      });
      message.success(mode === 'transfer' ? 'Сотрудник переведён' : 'Распределение сохранено');
      onClose();
    } catch (e) {
      message.error((e as Error).message || 'Не удалось сохранить');
    }
  };

  return (
    <Modal
      open
      title={mode === 'transfer' ? 'Перевести в группу' : 'Разделить между группами'}
      onOk={handleOk}
      onCancel={onClose}
      okText="Сохранить"
      cancelText="Отмена"
      okButtonProps={{ disabled: !valid }}
      confirmLoading={put.isPending}
      destroyOnHidden
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Text type="secondary">С даты</Text>
        <DatePicker value={on} onChange={setOn} format="DD.MM.YYYY" style={{ width: '100%' }} />
        {mode === 'transfer' ? (
          <>
            <Text type="secondary">Новая группа</Text>
            <Select
              placeholder="Группа"
              value={group}
              onChange={setGroup}
              options={subgroups.map((g) => ({ value: g.id, label: g.name }))}
            />
          </>
        ) : (
          <>
            {subgroups.map((g) => (
              <Space key={g.id} style={{ justifyContent: 'space-between', width: '100%' }}>
                <span>{g.name}</span>
                <InputNumber
                  min={0} max={100} precision={0} addonAfter="%"
                  value={pct[g.id] ?? null}
                  onChange={(v) => setPct((p) => ({ ...p, [g.id]: v }))}
                />
              </Space>
            ))}
            <Text type={total === 100 ? 'secondary' : 'danger'}>Итого {total}% — нужно 100%</Text>
          </>
        )}
        <Text type="secondary">
          До этой даты часы остаются в прежней группе, с неё — идут по новому распределению.
          Утверждённые сценарии не меняются: в них появится отметка о расхождении.
        </Text>
      </Space>
    </Modal>
  );
}
```

`InputNumber` с `addonAfter` в AntD 6 может быть помечен устаревшим — если `tsc`/консоль ругаются, заменить на `suffix="%"`.

- [ ] **Step 4: Блок «Группы» в карточке сотрудника**

`EmployeeDrawer.tsx`: в карточке каждого действующего участия (`!departed`), если у команды есть деление (`useTeamRegistry()` → строка по `m.team`, `has_subgroups`), под датами показать компонент `MembershipGroups` (в том же файле):

```tsx
function MembershipGroups({ employeeId, team, subgroups }: {
  employeeId: string;
  team: string;
  subgroups: { id: string; name: string }[];
}) {
  const { message } = App.useApp();
  const { data: history = [] } = useSubgroupShares(employeeId, team);
  const del = useDeleteSubgroupShare();
  const [mode, setMode] = useState<'transfer' | 'split' | null>(null);
  const name = (id: string) => subgroups.find((g) => g.id === id)?.name ?? '—';

  return (
    <div style={{ marginTop: 10 }}>
      <Text style={{ color: DARK_THEME.textSecondary, fontSize: 12 }}>Группы</Text>
      {history.length === 0 && (
        <div><Tag color="red">без группы — поправьте карточку</Tag></div>
      )}
      {history.map((r) => (
        <div key={r.valid_from ?? 'base'} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
          <span style={{ color: DARK_THEME.textMuted, minWidth: 110 }}>
            {r.valid_from ? `с ${dayjs(r.valid_from).format('DD.MM.YYYY')}` : 'с начала участия'}
          </span>
          <span style={{ color: DARK_THEME.textPrimary }}>
            {r.shares.map((s) => `${name(s.subgroup_id)}${s.percent < 100 ? ` ${s.percent}%` : ''}`).join(' · ')}
          </span>
          <Popconfirm
            title="Удалить запись?"
            description="Удаляйте только ошибочные записи — история перевода нужна для прошлых кварталов."
            onConfirm={() =>
              del.mutateAsync({ employeeId, team, valid_from: r.valid_from })
                .then(() => message.success('Запись удалена'))
                .catch(() => message.error('Не удалось удалить'))
            }
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </div>
      ))}
      <Space size="small" style={{ marginTop: 6 }}>
        <Button size="small" onClick={() => setMode('transfer')}>Перевести в группу</Button>
        <Button size="small" onClick={() => setMode('split')}>Разделить между группами</Button>
      </Space>
      {mode && (
        <SubgroupShareModal
          employeeId={employeeId} team={team} subgroups={subgroups}
          mode={mode} onClose={() => setMode(null)}
        />
      )}
    </div>
  );
}
```

Импорты: `Popconfirm`, `DeleteOutlined`, хуки, `useTeamRegistry`, `SubgroupShareModal`.

- [ ] **Step 5: Перевод между командами с группой**

`TransferTeamModal.tsx`: `Form.useWatch('to_team', form)`; если у выбранной команды деление (`useTeamRegistry()`), показать обязательное поле:

```tsx
        {targetGroups.length > 0 && (
          <Form.Item
            name="subgroup_id"
            label="Группа в новой команде"
            rules={[{ required: true, message: 'Выберите группу' }]}
          >
            <Select
              placeholder="Группа"
              options={targetGroups.map((g) => ({ value: g.id, label: g.name }))}
            />
          </Form.Item>
        )}
```

где `targetGroups = registry?.find((t) => t.name === toTeam && t.has_subgroups)?.subgroups ?? []`; в `mutateAsync` передать `subgroup_id: values.subgroup_id ?? null`.

- [ ] **Step 6: «Ресурсы» — колонка группы и плашка**

`CapacityPage.tsx`, блок группы в строке (около строки 346):
- если у сотрудника нет группы (`!membership?.subgroup_label`) — прежний `Select` (задаёт первую запись, эндпойнт тот же);
- иначе — текст `membership.subgroup_label` ссылкой, клик открывает карточку: `onClick={() => setDrawerEmployeeId(r.employee_id)}`, `title="Перевод и деление — в карточке сотрудника"`.

Плашка над таблицей: для команд из глобального фильтра с делением собрать активных сотрудников, у которых в строке этой команды нет `subgroup_label`, и показать:

```tsx
<Alert
  type="error"
  showIcon
  title={`Без группы: ${ungrouped.length} чел.`}
  description={
    <>
      В команде с делением на группы у каждого сотрудника должна быть группа. Иначе сценарий
      нельзя утвердить. Поправьте карточку или сделайте сотрудника неактивным:{' '}
      {ungrouped.map((u, i) => (
        <span key={u.id}>
          {i > 0 && ', '}
          <a onClick={() => setDrawerEmployeeId(u.id)}>{u.name}</a>
        </span>
      ))}
    </>
  }
/>
```

Источник данных — тот же список сотрудников с командами, что уже грузится на странице (найти, откуда берётся `teams` в строке). У AntD 6 `Alert` — `title`, не `message` (см. память проекта про `notification`; для `Alert` проверить по типам и выбрать не устаревшее свойство).

- [ ] **Step 7: Проверка**

`cd frontend && npx tsc -b && npx eslint src/components/capacity src/pages/CapacityPage.tsx src/hooks/useTeamRegistry.ts src/api/teams.ts && npx vitest run src` → без ошибок.

---

### Task 9: Интерфейс — «Сценарии» и ресурсное планирование

**Files:**
- Modify: `frontend/src/types/api.ts` (`ResourceEmployee`, сводка, `EmployeeDiff`, назначение плана)
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`
- Modify: `frontend/src/pages/PlanningPage.tsx` (плашка, кнопка «Утвердить», `CapacityDriftIndicator`)
- Modify: `frontend/src/api/resourcePlanning.ts`, `frontend/src/components/resource-planning/GanttRows.tsx`

- [ ] **Step 1: Типы**

```ts
// ResourceEmployee
  /** Часы по группам за квартал; ключ '' — дни без группы. */
  subgroup_hours?: Record<string, number>;
  /** Подписи участия в группе: «60%», «с 15.11», «до 15.11». */
  subgroup_labels?: Record<string, string>;

// сводка ресурса сценария (тип с available_by_subgroup_role)
  ungrouped_employees?: { employee_id: string; display_name: string }[];

// EmployeeDiff
  subgroup_before?: string | null;
  subgroup_after?: string | null;

// назначение плана (api/resourcePlanning.ts, рядом с subgroup_id)
  other_subgroup?: boolean;
```

- [ ] **Step 2: Секции «По сотрудникам» и «Ресурс по ролям»**

`PlanningCapacityPanel.tsx`:
- `groupSections`: сотрудники секции — `resourceBase.employees.filter((e) => (e.subgroup_hours ?? {})[g.id] !== undefined)`; «Без группы» — те, у кого есть ключ `''` (и секция только если такие есть), заголовок «Без группы» красным (`DARK_THEME.red` или ближайший красный токен темы).
- `renderEmployee(e, sectionId?)`: при `sectionId` ёмкость = `e.subgroup_hours?.[sectionId] ?? e.total_hours`, потребность = часы его идей этой группы; метка `e.subgroup_labels?.[sectionId]` — `<Tag>` рядом с именем с подсказкой «Часть времени сотрудника в этой группе». Для потребности по группе завести

```ts
  const demandByEmployeeGroup = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    if (!hasSubgroups || !resourceBase?.employees) return out;
    const byGroup: Record<string, AllocationResponse[]> = {};
    for (const a of allocations) (byGroup[a.subgroup_id ?? ''] ??= []).push(a);
    for (const [key, list] of Object.entries(byGroup)) {
      out[key] = demandByEmployeeOf(list, resourceBase.employees);
    }
    return out;
  }, [hasSubgroups, allocations, resourceBase]);
```

и в секции брать `demandByEmployeeGroup[sectionId]?.[e.employee_id] ?? 0`.
- `roleBars(..., sec.employees)` — число людей по роли считать по новым `sec.employees` (общий засчитывается в каждой своей группе — это счёт людей, а не часов).

- [ ] **Step 3: Плашка «без группы» и кнопка «Утвердить»**

`PlanningPage.tsx`: `const ungrouped = resourceSummary?.ungrouped_employees ?? [];`
- над таблицей идей, если `ungrouped.length > 0`: `Alert type="error"` «Без группы: N чел. — сценарий нельзя утвердить» со списком имён и ссылкой «Открыть „Ресурсы“» (роут страницы ресурсов — найти в `App.tsx`/роутинге);
- кнопка «Утвердить»: `disabled={ungrouped.length > 0}` + `Tooltip title="Сначала проставьте группы: ..."` вокруг кнопки при блокировке. Сервер всё равно отвечает 409 — `onError` уже показывает `detail`.

- [ ] **Step 4: Расхождение по группам**

`CapacityDriftIndicator`: в строке сотрудника, если `emp.subgroup_before !== undefined && (emp.subgroup_before || emp.subgroup_after)`:

```tsx
{(emp.subgroup_before || emp.subgroup_after) && (
  <div style={{ display: 'flex', gap: 8, padding: '4px 6px', background: 'rgba(245,158,11,0.07)', borderRadius: 5, fontSize: 12, marginBottom: 3 }}>
    <span style={{ color: '#e2e8f0', fontWeight: 500, minWidth: 120 }}>{emp.employee_name}</span>
    <span style={{ color: 'var(--text-muted, #94a3b8)' }}>
      группа: {emp.subgroup_before ?? 'без группы'} → {emp.subgroup_after ?? 'без группы'}
    </span>
  </div>
)}
```

- [ ] **Step 5: Метка на полоске плана**

`GanttRows.tsx`, у полоски назначения:
- `title`: добавить `${assignment.other_subgroup ? ' · работа на соседнюю группу' : ''}`;
- стиль: если `assignment.other_subgroup && !assignment.is_on_critical_path` — `border: '1px dashed #a78bfa'` (критический путь сохраняет свою рамку).

Проверить второй рендер полоски около строки 1435 (другой режим) — добавить ту же подсказку.

- [ ] **Step 6: Проверка** — `npx tsc -b && npx eslint <изменённые файлы> && npx vitest run src`.

---

### Task 10: Справка, спека, проверка вживую

**Files:**
- Modify: `docs/help/` — разделы «Ресурсы» и «Сценарии» (найти файлы: `ls docs/help`), при наличии — раздел ресурсного планирования
- Modify: `docs/superpowers/specs/2026-09-29-subgroup-transfer-shares-design.md` (уточнения ниже)

- [ ] **Step 1: Справка**

«Ресурсы»: блок «Группы» в карточке сотрудника — «Перевести в группу» (с даты, прошлое не меняется), «Разделить между группами» (проценты, сумма 100), удаление ошибочной записи; красная плашка «без группы». «Сценарии»: ресурс группы по долям и по дням перевода, пометки «60%», «с 15.11»; утверждение заблокировано, пока есть сотрудники без группы; отметка расхождения при переводе после утверждения. Планирование: пунктирная рамка «работа на соседнюю группу». Язык — аналитика, без технических терминов.

- [ ] **Step 2: Спека — уточнения, принятые при планировании**

- §5, автоподбор: «свой» — все группы, где у человека есть доля в квартале плана; ёмкость по группам не режется (доля — ориентир). Переведённый внутри квартала свой для обеих групп в этом квартале; метка «соседняя группа» показывает, где он работает не на свою группу.
- §8: общий сотрудник в витринах «на человека» учитывается целиком в каждой своей группе (решение пользователя 29.09); деление по доле — только в «Сценариях». Пометка «общий» — в «Сценариях» и «Ресурсах».
- Техприложение: колонка группы у участия удалена отдельной миграцией после перевода всех чтений; мёртвый расчёт ёмкости по группам в сервисе ёмкости удалён.

- [ ] **Step 3: Проверка вживую**

Запустить бэкенд на копии локальной базы (порт свободный, например 8010) и фронт; открыть «Ресурсы» с командой «Команда 1С (Бухгалтерия)»: плашка с тремя сотрудниками без группы; у одного из сотрудников сделать «Разделить между группами» 60/40 с 01.10; открыть сценарий Q4 команды — сотрудник в двух секциях с «60%»/«40%», сумма секций равна итогу команды; кнопка «Утвердить» заблокирована, пока трое без группы. Скриншоты — в отчёт.
