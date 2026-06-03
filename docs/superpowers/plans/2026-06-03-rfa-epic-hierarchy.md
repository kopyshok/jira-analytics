# RFA + Эпики: режим планирования, остаток часов, ручная правка плана — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Длинная RFA получает таблицу 6 колонок (План / Факт прошлых Q / Факт текущий / Утверждено / Запланировать / Черновик) per роль; PM выбирает режим планирования группы (целиком / по Эпикам / смешанно); плановые часы любого Issue можно править в сервисе с историей и конфликт-резолюшеном с Jira-sync.

**Architecture:**
- Backend: на `issues` переименование `planned_<role>_hours` → `planned_<role>_hours_jira` + добавление `_manual` (NULL=нет правки); новая таблица `plan_audit` (журнал). На `backlog_items` — `planning_mode` (`whole|by_epics`) + `included_in_planning` (bool). Новый сервис `HoursBreakdownService` считает 6 колонок по поддереву RFA с учётом глобального квартала. `BacklogService.sync_from_issue` теперь читает `_effective` (manual ?? jira) для `estimate_*_hours`. Sync-конфликт: если новый Jira-план ≠ предыдущему `_jira` И `_manual` задан → пишем audit-запись с `source='jira_sync_conflict'`, ручная правка остаётся.
- Frontend: переиспользуемый компонент `HoursBreakdownTable` (читает один эндпоинт `/issues/{id}/hours-breakdown?quarter=...`). В `BacklogPage` — раскрытие строки RFA через ▶, внутри — таблица + чекбоксы/радио. В `PlanningPage` — иконка ℹ на строке RFA открывает `HoursBreakdownDrawer`. `PlanEditDrawer` (общий) с input на 4 роли + обязательный комментарий + ссылка «История правок».

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (batch для SQLite), Pydantic, React 19 + AntD 6 + TanStack Query, pytest + Playwright.

**Спека:** `docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md`

---

## Phase 1 — Backend: миграции и модели

### Task 1: Миграция — переименование `planned_<role>_hours` + добавление `_manual`

**Files:**
- Create: `alembic/versions/057_plan_hours_versioning.py`
- Modify: `app/models/issue.py` — добавить новые колонки, оставить `planned_<role>_hours` как `@property` для backward compat

- [ ] **Step 1: Создать миграцию**

```python
"""plan hours versioning: rename + manual fields

Revision ID: 057_plan_hours_versioning
Revises: eff9e06ce1f5
Create Date: 2026-06-03
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "057_plan_hours_versioning"
down_revision: Union[str, None] = "eff9e06ce1f5"
branch_labels = None
depends_on = None

ROLES = ("analyst", "dev", "qa", "opo")


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        for role in ROLES:
            batch.alter_column(
                f"planned_{role}_hours",
                new_column_name=f"planned_{role}_hours_jira",
            )
            batch.add_column(
                sa.Column(f"planned_{role}_hours_manual", sa.Float(), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        for role in ROLES:
            batch.drop_column(f"planned_{role}_hours_manual")
            batch.alter_column(
                f"planned_{role}_hours_jira",
                new_column_name=f"planned_{role}_hours",
            )
```

- [ ] **Step 2: Запустить миграцию + проверить**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m alembic current
```

Expected: `057_plan_hours_versioning (head)`.

- [ ] **Step 3: Обновить `app/models/issue.py`**

Найти блок `planned_analyst_hours`, `planned_dev_hours`, `planned_qa_hours`, `planned_opo_hours` и заменить:

```python
# planned hours from Jira + manual overrides (см. spec 2026-06-03-rfa-epic-hierarchy-design)
planned_analyst_hours_jira: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_analyst_hours_manual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_dev_hours_jira: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_dev_hours_manual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_qa_hours_jira: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_qa_hours_manual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_opo_hours_jira: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
planned_opo_hours_manual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

@property
def planned_analyst_hours(self) -> Optional[float]:
    return self.planned_analyst_hours_manual if self.planned_analyst_hours_manual is not None else self.planned_analyst_hours_jira

@property
def planned_dev_hours(self) -> Optional[float]:
    return self.planned_dev_hours_manual if self.planned_dev_hours_manual is not None else self.planned_dev_hours_jira

@property
def planned_qa_hours(self) -> Optional[float]:
    return self.planned_qa_hours_manual if self.planned_qa_hours_manual is not None else self.planned_qa_hours_jira

@property
def planned_opo_hours(self) -> Optional[float]:
    return self.planned_opo_hours_manual if self.planned_opo_hours_manual is not None else self.planned_opo_hours_jira
```

- [ ] **Step 4: Адаптировать sync_service.py — писать в `_jira`**

В `app/services/sync_service.py` найти `_upsert_issue` (поиск `planned_analyst_hours`). Заменить присваивания:

```python
# было:
issue.planned_analyst_hours = parsed.planned_analyst_hours
# стало:
issue.planned_analyst_hours_jira = parsed.planned_analyst_hours
```

То же для `dev`, `qa`, `opo`.

- [ ] **Step 5: Прогнать тесты**

```bash
py -3.10 -m pytest tests/ -k "issue or sync or backlog" -v
```

Expected: PASS (property возвращает _manual ?? _jira; sync пишет в _jira).

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/057_plan_hours_versioning.py app/models/issue.py app/services/sync_service.py
git commit -m "feat(plan-hours): split planned_<role>_hours into _jira + _manual

Renames Issue.planned_<role>_hours → _jira; adds _manual override; property
returns manual ?? jira for backward-compat. Sync writes _jira only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Миграция — таблица `plan_audit`

**Files:**
- Create: `alembic/versions/058_plan_audit.py`
- Create: `app/models/plan_audit.py`
- Modify: `app/models/__init__.py` — импорт `PlanAudit`

- [ ] **Step 1: Создать миграцию**

```python
"""plan_audit journal

Revision ID: 058_plan_audit
Revises: 057_plan_hours_versioning
Create Date: 2026-06-03
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "058_plan_audit"
down_revision: Union[str, None] = "057_plan_hours_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),  # analyst|dev|qa|opo
        sa.Column("value_before", sa.Float(), nullable=True),
        sa.Column("value_after", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),  # jira_sync | manual_edit | manual_revert | jira_sync_conflict
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plan_audit_issue_created", "plan_audit", ["issue_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_plan_audit_issue_created", table_name="plan_audit")
    op.drop_table("plan_audit")
```

- [ ] **Step 2: Создать модель `app/models/plan_audit.py`**

```python
"""PlanAudit — журнал правок плановых часов."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class PlanAudit(Base):
    __tablename__ = "plan_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    value_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
```

- [ ] **Step 3: Добавить импорт в `app/models/__init__.py`**

```python
from app.models.plan_audit import PlanAudit  # noqa: F401
```

(Поставить после импорта `User` или в алфавитном порядке среди других моделей.)

- [ ] **Step 4: Запустить миграцию**

```bash
py -3.10 -m alembic upgrade head
```

Expected: `058_plan_audit (head)`.

- [ ] **Step 5: Написать smoke-test**

`tests/test_plan_audit_model.py`:

```python
"""Smoke test for PlanAudit model."""
from app.models.plan_audit import PlanAudit


def test_plan_audit_create(db_session, issue_factory):
    issue = issue_factory()
    audit = PlanAudit(
        issue_id=issue.id, role="analyst",
        value_before=100.0, value_after=150.0,
        source="manual_edit", comment="test",
    )
    db_session.add(audit)
    db_session.commit()
    assert audit.id is not None
    fetched = db_session.query(PlanAudit).filter_by(id=audit.id).one()
    assert fetched.role == "analyst"
    assert fetched.value_after == 150.0
```

- [ ] **Step 6: Прогнать**

```bash
py -3.10 -m pytest tests/test_plan_audit_model.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/058_plan_audit.py app/models/plan_audit.py app/models/__init__.py tests/test_plan_audit_model.py
git commit -m "feat(plan-audit): plan_audit journal table

Tracks every change to Issue planned_<role>_hours (jira sync, manual edit,
revert, sync conflict). Foreign keys to issues + users.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Миграция — `backlog_items.planning_mode` + `included_in_planning`

**Files:**
- Create: `alembic/versions/059_backlog_planning_mode.py`
- Modify: `app/models/backlog_item.py` — добавить поля

- [ ] **Step 1: Создать миграцию**

```python
"""backlog_items.planning_mode + included_in_planning

Revision ID: 059_backlog_planning_mode
Revises: 058_plan_audit
Create Date: 2026-06-03
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "059_backlog_planning_mode"
down_revision: Union[str, None] = "058_plan_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column("planning_mode", sa.String(16), nullable=False, server_default="whole"))
        batch.add_column(sa.Column("included_in_planning", sa.Boolean(), nullable=False, server_default=sa.text("1")))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("included_in_planning")
        batch.drop_column("planning_mode")
```

- [ ] **Step 2: Обновить модель `app/models/backlog_item.py`**

Добавить после `archived_at`:

```python
# Режим планирования группы RFA: 'whole' (RFA целиком в сценарии) | 'by_epics'
# (дочерние Эпики идут в сценарий, RFA-родитель — отдельной галочкой). Только для
# RFA-родителей с дочками; на одиночных задачах поле остаётся 'whole' и не используется.
planning_mode: Mapped[str] = mapped_column(
    String(16), nullable=False, default="whole", server_default="whole",
)
# В режиме 'by_epics' — индивидуальный флаг участия в утверждаемом сценарии.
# В режиме 'whole' не используется (поведение по дефолту: всегда включён).
included_in_planning: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=True, server_default=sa.text("1"),
)
```

Импорт `Boolean` и `sa` сверху если ещё нет.

- [ ] **Step 3: Запустить миграцию + тест**

```bash
py -3.10 -m alembic upgrade head
py -3.10 -m pytest tests/test_backlog_service.py -v
```

Expected: миграция применена, существующие тесты бэклога PASS.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/059_backlog_planning_mode.py app/models/backlog_item.py
git commit -m "feat(backlog): planning_mode + included_in_planning on backlog_items

planning_mode='whole'|'by_epics' — переключатель режима группы RFA.
included_in_planning — индивидуальный чекбокс участия в режиме 'by_epics'.
Default whole/true сохраняет текущее поведение.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Расчёт часов (6 колонок)

### Task 4: `HoursBreakdownService` + unit-тесты

**Files:**
- Create: `app/services/hours_breakdown_service.py`
- Create: `tests/test_hours_breakdown_service.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_hours_breakdown_service.py`:

```python
"""Тесты для HoursBreakdownService.

Все периоды относительны "выбранного квартала" (year, quarter).
Поддерево RFA = все потомки на любую глубину.
"""
from datetime import date

import pytest

from app.services.hours_breakdown_service import HoursBreakdownService


def test_simple_rfa_no_children(db_session, issue_factory):
    """Одиночная RFA без дочек: только План и Запланировать = План."""
    rfa = issue_factory(
        key="RFA-1", issue_type="RFA",
        planned_analyst_hours_jira=100,
        planned_dev_hours_jira=200,
        planned_qa_hours_jira=50,
        planned_opo_hours_jira=25,
    )
    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["plan"]["analyst"] == 100
    assert result["plan"]["dev"] == 200
    assert result["fact_past"]["analyst"] == 0
    assert result["fact_current"]["analyst"] == 0
    assert result["approved"]["analyst"] == 0
    assert result["planable"]["analyst"] == 100
    assert result["planable"]["dev"] == 200
    assert result["draft"]["analyst"] == 0


def test_long_rfa_with_approved_q1_epic_viewing_q2(db_session, issue_factory, worklog_factory, scenario_with_allocation):
    """RFA 1000ч, утв. Эпик Q1 (план 400, факт 300), смотрим Q2."""
    rfa = issue_factory(
        key="RFA-77", issue_type="RFA",
        planned_analyst_hours_jira=200, planned_dev_hours_jira=500,
        planned_qa_hours_jira=200, planned_opo_hours_jira=100,
    )
    epic_q1 = issue_factory(
        key="PRJ-1", issue_type="Epic", parent_id=rfa.id,
        planned_analyst_hours_jira=100, planned_dev_hours_jira=250,
        planned_qa_hours_jira=25, planned_opo_hours_jira=25,
    )
    # факт в Q1 (январь) на Эпике
    worklog_factory(issue_id=epic_q1.id, started=date(2026, 1, 15), hours=80, role="analyst")
    worklog_factory(issue_id=epic_q1.id, started=date(2026, 2, 10), hours=150, role="dev")
    worklog_factory(issue_id=epic_q1.id, started=date(2026, 3, 5), hours=50, role="qa")
    worklog_factory(issue_id=epic_q1.id, started=date(2026, 3, 20), hours=20, role="opo")
    # утверждаем Эпик Q1 в сценарии Q1
    scenario_with_allocation(year=2026, quarter=1, backlog_issue=epic_q1, included=True, status="approved")

    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    # Факт прошлых Q = вся работа в Q1
    assert result["fact_past"]["analyst"] == 80
    assert result["fact_past"]["dev"] == 150
    # Факт текущий в Q2 = 0 (ничего не делали)
    assert result["fact_current"]["analyst"] == 0
    # Утверждено в Q2 = 0 (нет утв. эпиков на Q2)
    assert result["approved"]["analyst"] == 0
    # Запланировать = 200 - 80 - 0 = 120
    assert result["planable"]["analyst"] == 120


def test_draft_epic_in_count(db_session, issue_factory):
    """Эпик без статуса утв. и без ворклогов попадает в «Черновик»."""
    rfa = issue_factory(key="RFA-2", issue_type="RFA", planned_dev_hours_jira=500)
    issue_factory(
        key="PRJ-2", issue_type="Epic", parent_id=rfa.id,
        planned_dev_hours_jira=100,
    )
    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["draft"]["dev"] == 100


def test_manual_override_used_in_plan(db_session, issue_factory):
    """Если задан _manual — он перетирает _jira для колонки «План»."""
    rfa = issue_factory(
        key="RFA-3", issue_type="RFA",
        planned_dev_hours_jira=500, planned_dev_hours_manual=600,
    )
    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["plan"]["dev"] == 600


def test_planable_negative_marked(db_session, issue_factory, worklog_factory):
    """Если факт прошлых > план — Запланировать отрицательное, флаг overrun=True."""
    rfa = issue_factory(key="RFA-4", issue_type="RFA", planned_dev_hours_jira=100)
    worklog_factory(issue_id=rfa.id, started=date(2026, 1, 15), hours=150, role="dev")
    svc = HoursBreakdownService(db_session)
    result = svc.calculate(rfa.id, year=2026, quarter=2)
    assert result["planable"]["dev"] == -50
    assert result["flags"]["overrun"] is True
```

- [ ] **Step 2: Запустить — должно упасть на импорте**

```bash
py -3.10 -m pytest tests/test_hours_breakdown_service.py -v
```

Expected: FAIL «No module named 'app.services.hours_breakdown_service'».

- [ ] **Step 3: Реализовать сервис**

`app/services/hours_breakdown_service.py`:

```python
"""HoursBreakdownService — расчёт 6 колонок часов длинной RFA.

См. spec: docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md
"""
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import (
    Issue, Worklog, BacklogItem, ScenarioAllocation, PlanningScenario,
)

ROLES = ("analyst", "dev", "qa", "opo")
QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


def quarter_range(year: int, quarter: int) -> tuple[date, date]:
    months = QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    end_month = months[-1]
    end_day = 31 if end_month in (3, 12) else 30 if end_month == 6 or end_month == 9 else 31
    # ровные диапазоны: Q1=янв-март, Q2=апр-июнь, Q3=июл-сент, Q4=окт-дек
    end_map = {3: 31, 6: 30, 9: 30, 12: 31}
    end = date(year, end_month, end_map[end_month])
    return start, end


class HoursBreakdownService:
    """Считает 6 колонок per роль для заданной RFA и квартала."""

    def __init__(self, db: Session):
        self.db = db

    def _subtree_ids(self, root_id: str) -> Set[str]:
        """Все потомки root_id на любую глубину + сам root."""
        result: Set[str] = {root_id}
        frontier: List[str] = [root_id]
        while frontier:
            children = (
                self.db.query(Issue.id)
                .filter(Issue.parent_id.in_(frontier))
                .all()
            )
            new_ids = [c[0] for c in children if c[0] not in result]
            if not new_ids:
                break
            result.update(new_ids)
            frontier = new_ids
        return result

    def _approved_subtree_ids(self, subtree: Set[str], year: int, quarter: int) -> Set[str]:
        """Задачи из поддерева, утверждённые в сценарии (year, quarter)."""
        rows = (
            self.db.query(Issue.id)
            .join(BacklogItem, BacklogItem.issue_id == Issue.id)
            .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .filter(
                Issue.id.in_(subtree),
                PlanningScenario.year == year,
                PlanningScenario.quarter == quarter,
                PlanningScenario.status == "approved",
                ScenarioAllocation.included_flag == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows}

    def _aggregate_worklog(self, issue_ids: Set[str], start: date, end: date) -> Dict[str, float]:
        """Σ worklog.hours per роль за период [start, end]."""
        if not issue_ids:
            return {r: 0.0 for r in ROLES}
        rows = (
            self.db.query(Worklog.role, Worklog.hours)
            .filter(
                Worklog.issue_id.in_(issue_ids),
                Worklog.started >= start,
                Worklog.started <= end,
            )
            .all()
        )
        out = defaultdict(float)
        for role, hours in rows:
            if role in ROLES:
                out[role] += hours or 0
        return {r: out[r] for r in ROLES}

    def _aggregate_plan(self, issue_ids: Set[str], use_manual: bool = True) -> Dict[str, float]:
        """Σ plan_effective per роль для заданных задач."""
        if not issue_ids:
            return {r: 0.0 for r in ROLES}
        issues = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
        out: Dict[str, float] = {r: 0.0 for r in ROLES}
        for issue in issues:
            for role in ROLES:
                jira = getattr(issue, f"planned_{role}_hours_jira") or 0
                manual = getattr(issue, f"planned_{role}_hours_manual")
                eff = manual if (use_manual and manual is not None) else jira
                out[role] += eff or 0
        return out

    def _issue_has_worklog(self, issue_id: str) -> bool:
        return self.db.query(Worklog.id).filter(Worklog.issue_id == issue_id).first() is not None

    def calculate(self, root_issue_id: str, year: int, quarter: int) -> Dict:
        rfa = self.db.query(Issue).filter(Issue.id == root_issue_id).one()
        subtree = self._subtree_ids(root_issue_id)
        descendants = subtree - {root_issue_id}

        q_start, q_end = quarter_range(year, quarter)
        # Прошлый период: с начала эпохи до q_start - 1 день
        past_end = date(q_start.year, q_start.month, q_start.day)
        # Для worklog.started < q_start
        past_start = date(2000, 1, 1)

        # План RFA — сама RFA (не поддерево)
        plan = self._aggregate_plan({root_issue_id})

        # Факт прошлых Q — весь поддерево, started < q_start
        fact_past = self._aggregate_worklog(subtree, past_start, date(q_start.year, q_start.month, q_start.day))
        # Поправка: нужен интервал [past_start, q_start) — но _aggregate_worklog inclusive. Используем end = q_start − 1 день.
        from datetime import timedelta
        fact_past = self._aggregate_worklog(subtree, past_start, q_start - timedelta(days=1))

        # Утв. поддерево на год+квартал
        approved_ids = self._approved_subtree_ids(subtree, year, quarter)

        # Факт текущий — worklog только утв. эпиков поддерева в [q_start, q_end]
        fact_current = self._aggregate_worklog(approved_ids, q_start, q_end)

        # Утверждено — план утв. эпиков (целиком, _effective)
        approved = self._aggregate_plan(approved_ids)

        # Черновик — эпики поддерева, без статуса утв. и без ворклогов
        draft_ids: Set[str] = set()
        for iid in descendants:
            if iid in approved_ids:
                continue
            if self._issue_has_worklog(iid):
                continue
            draft_ids.add(iid)
        draft = self._aggregate_plan(draft_ids)

        # Запланировать = План − Факт прошлых − Утверждено
        planable = {r: plan[r] - fact_past[r] - approved[r] for r in ROLES}

        # Флаги
        flags = {
            "overrun": any(planable[r] < 0 for r in ROLES),
            "plan_missing": all(plan[r] == 0 for r in ROLES),
            "draft_exceeds_planable": any(draft[r] > planable[r] for r in ROLES),
        }

        def _with_total(d: Dict[str, float]) -> Dict[str, float]:
            d_copy = dict(d)
            d_copy["total"] = sum(d_copy[r] for r in ROLES)
            return d_copy

        return {
            "issue_id": root_issue_id,
            "year": year,
            "quarter": quarter,
            "plan": _with_total(plan),
            "fact_past": _with_total(fact_past),
            "fact_current": _with_total(fact_current),
            "approved": _with_total(approved),
            "planable": _with_total(planable),
            "draft": _with_total(draft),
            "flags": flags,
        }
```

- [ ] **Step 4: Прогнать тесты — некоторые могут падать на отсутствии фикстур `scenario_with_allocation` / `worklog_factory(role=...)`**

```bash
py -3.10 -m pytest tests/test_hours_breakdown_service.py -v
```

- [ ] **Step 5: Добавить фабрики если нет**

Проверить `tests/conftest.py`. Если нет `scenario_with_allocation` — добавить:

```python
@pytest.fixture
def scenario_with_allocation(db_session, backlog_item_factory):
    """Создаёт сценарий + BacklogItem (если нет) + ScenarioAllocation."""
    def _create(year, quarter, backlog_issue, included=True, status="approved"):
        from app.models import PlanningScenario, ScenarioAllocation, BacklogItem
        bi = db_session.query(BacklogItem).filter_by(issue_id=backlog_issue.id).first()
        if bi is None:
            bi = backlog_item_factory(issue_id=backlog_issue.id, title=backlog_issue.summary or backlog_issue.key)
        sc = PlanningScenario(year=year, quarter=quarter, status=status, name=f"S{year}Q{quarter}")
        db_session.add(sc)
        db_session.flush()
        a = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=included, planned_hours=0)
        db_session.add(a)
        db_session.commit()
        return sc
    return _create
```

И в `worklog_factory` — убедиться что параметр `role` поддерживается. Если нет — добавить.

- [ ] **Step 6: Прогнать снова до PASS**

```bash
py -3.10 -m pytest tests/test_hours_breakdown_service.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/hours_breakdown_service.py tests/test_hours_breakdown_service.py tests/conftest.py
git commit -m "feat(hours-breakdown): расчёт 6 колонок часов для длинной RFA

План / Факт прошлых Q / Факт текущий / Утверждено / Запланировать / Черновик
per роль с агрегатом 'total'. Период берётся из (year, quarter) запроса.
Поддерево — все потомки на любую глубину.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: API `GET /issues/{id}/hours-breakdown`

**Files:**
- Modify: `app/api/endpoints/issues.py` — добавить эндпоинт
- Modify: `tests/test_issues_endpoints.py` (или создать `tests/test_issues_hours_breakdown_api.py`)

- [ ] **Step 1: Написать тест**

`tests/test_issues_hours_breakdown_api.py`:

```python
def test_hours_breakdown_api(client, issue_factory):
    rfa = issue_factory(
        key="RFA-10", issue_type="RFA",
        planned_dev_hours_jira=500,
    )
    r = client.get(f"/api/v1/issues/{rfa.id}/hours-breakdown?year=2026&quarter=2")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["dev"] == 500
    assert body["plan"]["total"] == 500
    assert body["planable"]["dev"] == 500


def test_hours_breakdown_404(client):
    r = client.get("/api/v1/issues/nonexistent/hours-breakdown?year=2026&quarter=2")
    assert r.status_code == 404
```

- [ ] **Step 2: Прогнать — должен упасть на 404 / отсутствии маршрута**

```bash
py -3.10 -m pytest tests/test_issues_hours_breakdown_api.py -v
```

Expected: FAIL.

- [ ] **Step 3: Добавить эндпоинт в `app/api/endpoints/issues.py`**

Найти `router = APIRouter(...)` — после него добавить:

```python
from app.services.hours_breakdown_service import HoursBreakdownService


@router.get("/{issue_id}/hours-breakdown")
def get_hours_breakdown(
    issue_id: str,
    year: int,
    quarter: int,
    db: Session = Depends(get_db),
):
    """6 колонок часов для длинной RFA. См. spec 2026-06-03-rfa-epic-hierarchy."""
    issue = db.query(Issue).filter(Issue.id == issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    return HoursBreakdownService(db).calculate(issue_id, year, quarter)
```

- [ ] **Step 4: Прогнать**

```bash
py -3.10 -m pytest tests/test_issues_hours_breakdown_api.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/issues.py tests/test_issues_hours_breakdown_api.py
git commit -m "feat(api): GET /issues/{id}/hours-breakdown?year&quarter

Возвращает 6 колонок часов от HoursBreakdownService. 404 если задачи нет.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Ручная правка плана + конфликт

### Task 6: API `PATCH /issues/{id}/plan` + журнал

**Files:**
- Create: `app/services/plan_edit_service.py`
- Modify: `app/api/endpoints/issues.py` — добавить эндпоинты
- Create: `tests/test_plan_edit_api.py`

- [ ] **Step 1: Написать тесты**

`tests/test_plan_edit_api.py`:

```python
import pytest


def test_patch_plan_creates_audit(client, issue_factory, auth_user, db_session):
    issue = issue_factory(planned_dev_hours_jira=500)
    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "После ретро"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["dev"] == 600

    from app.models import PlanAudit
    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 1
    assert rows[0].role == "dev"
    assert rows[0].value_before == 500
    assert rows[0].value_after == 600
    assert rows[0].source == "manual_edit"
    assert rows[0].comment == "После ретро"


def test_patch_plan_requires_comment(client, issue_factory):
    issue = issue_factory(planned_dev_hours_jira=500)
    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": ""},
    )
    assert r.status_code == 422


def test_revert_plan(client, issue_factory, db_session):
    from app.models import Issue
    issue = issue_factory(planned_dev_hours_jira=500)
    # сначала правка
    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "test"},
    )
    # потом откат
    r = client.post(f"/api/v1/issues/{issue.id}/plan/revert", json={})
    assert r.status_code == 200
    db_session.expire_all()
    refreshed = db_session.query(Issue).filter_by(id=issue.id).one()
    assert refreshed.planned_dev_hours_manual is None
    assert refreshed.planned_dev_hours == 500


def test_plan_history(client, issue_factory, db_session):
    issue = issue_factory(planned_dev_hours_jira=500)
    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "first"},
    )
    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 700}, "comment": "second"},
    )
    r = client.get(f"/api/v1/issues/{issue.id}/plan-history")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    # latest first
    assert rows[0]["value_after"] == 700
    assert rows[0]["comment"] == "second"
```

- [ ] **Step 2: Прогнать — упадёт на 404**

```bash
py -3.10 -m pytest tests/test_plan_edit_api.py -v
```

- [ ] **Step 3: Создать сервис `app/services/plan_edit_service.py`**

```python
"""PlanEditService — ручная правка плановых часов + журнал."""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import Issue, PlanAudit

ROLES = ("analyst", "dev", "qa", "opo")


class PlanEditService:
    def __init__(self, db: Session):
        self.db = db

    def edit(
        self,
        issue_id: str,
        role_hours: Dict[str, Optional[float]],
        comment: str,
        user_id: Optional[str] = None,
    ) -> Issue:
        if not comment or len(comment.strip()) < 1:
            raise ValueError("Comment is required for manual edits")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        for role, new_value in role_hours.items():
            if role not in ROLES:
                continue
            field_manual = f"planned_{role}_hours_manual"
            before = getattr(issue, f"planned_{role}_hours")  # effective
            setattr(issue, field_manual, new_value)
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=new_value,
                source="manual_edit", user_id=user_id, comment=comment,
            ))
        self.db.commit()
        return issue

    def revert(
        self,
        issue_id: str,
        audit_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Issue:
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        if audit_id is None:
            # сброс к Jira: убрать все _manual для всех ролей
            for role in ROLES:
                field_manual = f"planned_{role}_hours_manual"
                before = getattr(issue, f"planned_{role}_hours")
                if getattr(issue, field_manual) is not None:
                    setattr(issue, field_manual, None)
                    after = getattr(issue, f"planned_{role}_hours_jira")
                    self.db.add(PlanAudit(
                        issue_id=issue.id, role=role,
                        value_before=before, value_after=after,
                        source="manual_revert", user_id=user_id, comment="Сброс к Jira",
                    ))
        else:
            audit = self.db.query(PlanAudit).filter_by(id=audit_id).one()
            field_manual = f"planned_{audit.role}_hours_manual"
            field_jira = f"planned_{audit.role}_hours_jira"
            target = audit.value_after
            jira_now = getattr(issue, field_jira)
            before = getattr(issue, f"planned_{audit.role}_hours")
            # если возвращаем к Jira-значению — обнулить _manual; иначе записать
            if target == jira_now:
                setattr(issue, field_manual, None)
            else:
                setattr(issue, field_manual, target)
            self.db.add(PlanAudit(
                issue_id=issue.id, role=audit.role,
                value_before=before, value_after=target,
                source="manual_revert", user_id=user_id,
                comment=f"Откат к записи {audit_id}",
            ))
        self.db.commit()
        return issue

    def history(self, issue_id: str) -> list[PlanAudit]:
        return (
            self.db.query(PlanAudit)
            .filter_by(issue_id=issue_id)
            .order_by(PlanAudit.created_at.desc())
            .all()
        )
```

- [ ] **Step 4: Добавить эндпоинты в `app/api/endpoints/issues.py`**

```python
from app.core.auth_deps import get_current_user
from app.services.plan_edit_service import PlanEditService, ROLES as PLAN_ROLES
from pydantic import BaseModel, Field, validator


class PlanEditRequest(BaseModel):
    role_hours: Dict[str, Optional[float]]
    comment: str = Field(..., min_length=1)


class PlanRevertRequest(BaseModel):
    audit_id: Optional[str] = None


@router.patch("/{issue_id}/plan")
def patch_plan(
    issue_id: str,
    payload: PlanEditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    svc = PlanEditService(db)
    try:
        svc.edit(
            issue_id, payload.role_hours, payload.comment,
            user_id=current_user.id if current_user else None,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.refresh(issue)
    return {
        "plan": {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    }


@router.post("/{issue_id}/plan/revert")
def revert_plan(
    issue_id: str,
    payload: PlanRevertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    PlanEditService(db).revert(
        issue_id, audit_id=payload.audit_id,
        user_id=current_user.id if current_user else None,
    )
    db.refresh(issue)
    return {
        "plan": {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    }


@router.get("/{issue_id}/plan-history")
def plan_history(issue_id: str, db: Session = Depends(get_db)):
    rows = PlanEditService(db).history(issue_id)
    return [
        {
            "id": r.id, "role": r.role,
            "value_before": r.value_before, "value_after": r.value_after,
            "source": r.source, "user_id": r.user_id, "comment": r.comment,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
```

Импорты: `Dict`, `Optional` из `typing`; `BaseModel`, `Field` из `pydantic`. `get_current_user_optional` — нужно посмотреть как это сделано в auth-эндпоинтах; если нет — использовать существующий `get_current_user` и сделать `Depends(get_current_user)` для тестов с авторизацией. Для простоты — поправить тесты, чтобы не требовали юзера.

- [ ] **Step 5: Если в тестах используется `auth_user` и `client` без логина — обойти**

Может потребоваться поправить тест и убрать `auth_user` параметр; user_id в audit будет NULL.

Прогнать:

```bash
py -3.10 -m pytest tests/test_plan_edit_api.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/plan_edit_service.py app/api/endpoints/issues.py tests/test_plan_edit_api.py
git commit -m "feat(plan-edit): ручная правка плановых часов через API + журнал

PATCH /issues/{id}/plan — правка с обязательным комментарием.
POST /issues/{id}/plan/revert — откат к Jira (без audit_id) или к точке (с audit_id).
GET /issues/{id}/plan-history — журнал в обратном хронологическом порядке.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Sync — детект конфликта + audit

**Files:**
- Modify: `app/services/sync_service.py` — в `_upsert_issue` добавить детект и запись в `plan_audit`
- Create: `tests/test_sync_plan_conflict.py`

- [ ] **Step 1: Тест**

`tests/test_sync_plan_conflict.py`:

```python
"""Sync должен записывать в plan_audit при изменении plan_<role>_hours_jira."""
from datetime import datetime


def test_sync_logs_jira_change(db_session, issue_factory):
    """Симуляция: меняем _jira напрямую и убеждаемся что в реальном sync есть audit-запись.

    Заметка: проверяем helper-функцию `_record_plan_changes` из sync_service.
    """
    from app.services.sync_service import _record_plan_changes  # helper
    from app.models import PlanAudit

    issue = issue_factory(planned_dev_hours_jira=500)
    # Симулируем новое значение из Jira
    _record_plan_changes(
        db_session, issue,
        new_values={"analyst": None, "dev": 550, "qa": None, "opo": None},
        manual_conflict_only=False,
    )
    db_session.commit()

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 1
    assert rows[0].role == "dev"
    assert rows[0].value_before == 500
    assert rows[0].value_after == 550
    assert rows[0].source == "jira_sync"


def test_sync_conflict_when_manual_set(db_session, issue_factory):
    """Если _manual задан и новое Jira != старому _jira → source='jira_sync_conflict',
    _jira обновляется, _manual остаётся."""
    from app.services.sync_service import _record_plan_changes
    from app.models import PlanAudit, Issue

    issue = issue_factory(planned_dev_hours_jira=500, planned_dev_hours_manual=600)
    _record_plan_changes(
        db_session, issue,
        new_values={"analyst": None, "dev": 550, "qa": None, "opo": None},
        manual_conflict_only=False,
    )
    db_session.commit()
    db_session.refresh(issue)
    # _manual не тронут
    assert issue.planned_dev_hours_manual == 600
    # _jira обновлено
    assert issue.planned_dev_hours_jira == 550

    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert any(r.source == "jira_sync_conflict" for r in rows)
```

- [ ] **Step 2: Прогнать — упадёт на отсутствии helper**

- [ ] **Step 3: Реализовать helper в `app/services/sync_service.py`**

В начале файла рядом с другими helper'ами:

```python
def _record_plan_changes(
    db,
    issue,
    new_values: dict,  # {analyst|dev|qa|opo: Optional[float]}
    manual_conflict_only: bool = False,
):
    """Сравнивает новое Jira-значение со старым `_jira`, пишет audit-записи.

    - Если значения одинаковы — ничего не делает.
    - Если изменено и `_manual` пустое — source='jira_sync', обновляет `_jira`.
    - Если изменено и `_manual` задан — source='jira_sync_conflict', обновляет
      только `_jira`, `_manual` остаётся (PM должен решить через баннер).
    """
    from app.models import PlanAudit
    for role in ("analyst", "dev", "qa", "opo"):
        new = new_values.get(role)
        field_jira = f"planned_{role}_hours_jira"
        field_manual = f"planned_{role}_hours_manual"
        old_jira = getattr(issue, field_jira)
        if new == old_jira:
            continue  # no change
        has_manual = getattr(issue, field_manual) is not None
        source = "jira_sync_conflict" if has_manual else "jira_sync"
        if manual_conflict_only and not has_manual:
            # пропускаем не-конфликты, если запросили только их
            setattr(issue, field_jira, new)
            continue
        db.add(PlanAudit(
            issue_id=issue.id, role=role,
            value_before=old_jira, value_after=new,
            source=source, user_id=None,
            comment=None,
        ))
        setattr(issue, field_jira, new)
```

Затем найти место в `_upsert_issue` где сейчас идёт:

```python
issue.planned_analyst_hours_jira = parsed.planned_analyst_hours
issue.planned_dev_hours_jira = parsed.planned_dev_hours
issue.planned_qa_hours_jira = parsed.planned_qa_hours
issue.planned_opo_hours_jira = parsed.planned_opo_hours
```

Заменить на:

```python
_record_plan_changes(self.db, issue, {
    "analyst": parsed.planned_analyst_hours,
    "dev": parsed.planned_dev_hours,
    "qa": parsed.planned_qa_hours,
    "opo": parsed.planned_opo_hours,
})
```

(Если в текущем коде атрибуты называются по-старому — посмотреть фактическое присвоение в Task 1, Step 4.)

- [ ] **Step 4: Прогнать**

```bash
py -3.10 -m pytest tests/test_sync_plan_conflict.py tests/test_sync_service.py -v
```

Expected: новые 2 PASS; pre-existing test_sync_service пусть остаётся как был (см. memory о known issue).

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_service.py tests/test_sync_plan_conflict.py
git commit -m "feat(sync): детект конфликта Jira-vs-ручная + audit log

Sync пишет в plan_audit когда planned_<role>_hours_jira реально меняется.
Если ручная правка задана — source='jira_sync_conflict' (для баннера на UI).
_manual никогда не затирается при sync.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: API resolve-conflict + список открытых конфликтов

**Files:**
- Modify: `app/api/endpoints/issues.py`
- Modify: `app/services/plan_edit_service.py` — методы `accept_jira` / `ignore_conflict`
- Create: `tests/test_plan_conflict_api.py`

- [ ] **Step 1: Тест**

`tests/test_plan_conflict_api.py`:

```python
def test_conflict_accept_jira(client, issue_factory, db_session):
    from app.models import Issue
    issue = issue_factory(planned_dev_hours_jira=550, planned_dev_hours_manual=600)
    # симулировать sync_conflict audit-запись
    from app.models import PlanAudit
    db_session.add(PlanAudit(
        issue_id=issue.id, role="dev",
        value_before=500, value_after=550,
        source="jira_sync_conflict",
    ))
    db_session.commit()

    r = client.post(
        f"/api/v1/issues/{issue.id}/plan/conflict-resolve",
        json={"action": "accept_jira", "role": "dev"},
    )
    assert r.status_code == 200
    db_session.refresh(issue)
    assert issue.planned_dev_hours_manual is None
    assert issue.planned_dev_hours == 550  # effective


def test_conflict_ignore(client, issue_factory, db_session):
    from app.models import Issue, PlanAudit
    issue = issue_factory(planned_dev_hours_jira=550, planned_dev_hours_manual=600)
    db_session.add(PlanAudit(
        issue_id=issue.id, role="dev",
        value_before=500, value_after=550,
        source="jira_sync_conflict",
    ))
    db_session.commit()

    r = client.post(
        f"/api/v1/issues/{issue.id}/plan/conflict-resolve",
        json={"action": "ignore", "role": "dev"},
    )
    assert r.status_code == 200
    db_session.refresh(issue)
    # _manual остался (PM игнорирует Jira)
    assert issue.planned_dev_hours_manual == 600
    # audit получил resolution
    rows = db_session.query(PlanAudit).filter_by(issue_id=issue.id, role="dev").order_by(PlanAudit.created_at).all()
    assert rows[-1].source == "conflict_ignored"
```

- [ ] **Step 2: Реализовать в сервисе**

Добавить в `PlanEditService`:

```python
def resolve_conflict(
    self, issue_id: str, role: str, action: str, user_id: Optional[str] = None,
) -> Issue:
    """action: 'accept_jira' | 'ignore'."""
    if role not in ROLES:
        raise ValueError("Unknown role")
    if action not in ("accept_jira", "ignore"):
        raise ValueError("Unknown action")
    issue = self.db.query(Issue).filter_by(id=issue_id).one()
    field_jira = f"planned_{role}_hours_jira"
    field_manual = f"planned_{role}_hours_manual"
    jira_now = getattr(issue, field_jira)
    before = getattr(issue, f"planned_{role}_hours")  # effective
    if action == "accept_jira":
        setattr(issue, field_manual, None)
        self.db.add(PlanAudit(
            issue_id=issue.id, role=role,
            value_before=before, value_after=jira_now,
            source="conflict_accepted", user_id=user_id,
            comment="Принято Jira-значение",
        ))
    else:  # ignore
        self.db.add(PlanAudit(
            issue_id=issue.id, role=role,
            value_before=before, value_after=before,
            source="conflict_ignored", user_id=user_id,
            comment="Конфликт проигнорирован, ручная правка сохранена",
        ))
    self.db.commit()
    return issue


def open_conflicts(self, issue_id: str) -> list[dict]:
    """Возвращает открытые (не разрешённые) конфликты для задачи."""
    rows = (
        self.db.query(PlanAudit)
        .filter_by(issue_id=issue_id)
        .order_by(PlanAudit.created_at.desc())
        .all()
    )
    # для каждой роли — есть ли свежий jira_sync_conflict без последующего resolved
    by_role: dict = {}
    for r in rows:
        if r.role in by_role:
            continue  # уже определили исход для этой роли (берём свежее)
        if r.source in ("conflict_accepted", "conflict_ignored", "manual_edit", "manual_revert"):
            by_role[r.role] = None  # закрыто
        elif r.source == "jira_sync_conflict":
            by_role[r.role] = r
    return [
        {"role": role, "audit_id": audit.id,
         "value_jira": audit.value_after, "value_before": audit.value_before}
        for role, audit in by_role.items() if audit is not None
    ]
```

- [ ] **Step 3: Эндпоинты**

В `app/api/endpoints/issues.py`:

```python
class ConflictResolveRequest(BaseModel):
    action: str  # accept_jira | ignore
    role: str


@router.post("/{issue_id}/plan/conflict-resolve")
def resolve_plan_conflict(
    issue_id: str,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    try:
        PlanEditService(db).resolve_conflict(
            issue_id, payload.role, payload.action,
            user_id=current_user.id if current_user else None,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.get("/{issue_id}/plan-conflicts")
def get_plan_conflicts(issue_id: str, db: Session = Depends(get_db)):
    return PlanEditService(db).open_conflicts(issue_id)
```

- [ ] **Step 4: Прогнать**

```bash
py -3.10 -m pytest tests/test_plan_conflict_api.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/plan_edit_service.py app/api/endpoints/issues.py tests/test_plan_conflict_api.py
git commit -m "feat(plan-conflict): API для разрешения конфликта Jira-vs-ручная

POST /issues/{id}/plan/conflict-resolve {action,role} — accept_jira / ignore.
GET /issues/{id}/plan-conflicts — список открытых конфликтов.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Режим планирования группы

### Task 9: API `PATCH /backlog/{id}/planning-mode` + `/included`

**Files:**
- Modify: `app/api/endpoints/backlog.py`
- Create: `tests/test_backlog_planning_mode_api.py`

- [ ] **Step 1: Тест**

```python
def test_set_planning_mode(client, backlog_item_factory, db_session):
    from app.models import BacklogItem
    bi = backlog_item_factory()
    r = client.patch(f"/api/v1/backlog/{bi.id}/planning-mode", json={"mode": "by_epics"})
    assert r.status_code == 200
    db_session.refresh(bi)
    assert bi.planning_mode == "by_epics"


def test_set_included(client, backlog_item_factory, db_session):
    bi = backlog_item_factory()
    r = client.patch(f"/api/v1/backlog/{bi.id}/included", json={"included": False})
    assert r.status_code == 200
    db_session.refresh(bi)
    assert bi.included_in_planning is False


def test_invalid_mode_rejected(client, backlog_item_factory):
    bi = backlog_item_factory()
    r = client.patch(f"/api/v1/backlog/{bi.id}/planning-mode", json={"mode": "bogus"})
    assert r.status_code == 422
```

- [ ] **Step 2: Эндпоинты в `app/api/endpoints/backlog.py`**

```python
class PlanningModeRequest(BaseModel):
    mode: str  # 'whole' | 'by_epics'


class IncludedRequest(BaseModel):
    included: bool


@router.patch("/{item_id}/planning-mode")
def set_planning_mode(item_id: str, payload: PlanningModeRequest, db: Session = Depends(get_db)):
    if payload.mode not in ("whole", "by_epics"):
        raise HTTPException(422, "mode must be 'whole' or 'by_epics'")
    bi = db.query(BacklogItem).filter_by(id=item_id).one_or_none()
    if bi is None:
        raise HTTPException(404, "BacklogItem not found")
    bi.planning_mode = payload.mode
    db.commit()
    return {"id": bi.id, "planning_mode": bi.planning_mode}


@router.patch("/{item_id}/included")
def set_included(item_id: str, payload: IncludedRequest, db: Session = Depends(get_db)):
    bi = db.query(BacklogItem).filter_by(id=item_id).one_or_none()
    if bi is None:
        raise HTTPException(404, "BacklogItem not found")
    bi.included_in_planning = payload.included
    db.commit()
    return {"id": bi.id, "included_in_planning": bi.included_in_planning}
```

- [ ] **Step 3: Прогнать**

```bash
py -3.10 -m pytest tests/test_backlog_planning_mode_api.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/endpoints/backlog.py tests/test_backlog_planning_mode_api.py
git commit -m "feat(backlog-api): PATCH planning-mode + included для группы RFA

PATCH /backlog/{id}/planning-mode {mode: whole|by_epics}
PATCH /backlog/{id}/included {included: bool}

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Включить planning_mode в `/backlog` ответ + warning на двойной счёт

**Files:**
- Modify: `app/api/endpoints/backlog.py` — расширить ответ списка
- Modify: `tests/test_backlog_*` — добавить проверку

- [ ] **Step 1: Найти текущий response schema списка `/backlog`**

```bash
grep -n "GET.*backlog\|/backlog" app/api/endpoints/backlog.py
```

- [ ] **Step 2: Добавить поля `planning_mode`, `included_in_planning`, `has_parent_in_backlog`, `has_children_in_backlog` в Pydantic response model**

Если используется dict-возврат — добавить ключи. Логику `has_*`:
- `has_children_in_backlog` — `EXISTS` query: есть ли в `backlog_items` запись, у которой `issue.parent_id == self.issue_id` (то есть текущая RFA — родитель).
- `has_parent_in_backlog` — обратное: есть ли в `backlog_items` родительская задача.

- [ ] **Step 3: Тест**

```python
def test_backlog_list_includes_hierarchy_flags(client, issue_factory, backlog_item_factory):
    rfa = issue_factory(key="RFA-100", issue_type="RFA")
    epic = issue_factory(key="PRJ-100", issue_type="Epic", parent_id=rfa.id)
    backlog_item_factory(issue_id=rfa.id)
    backlog_item_factory(issue_id=epic.id)
    r = client.get("/api/v1/backlog/")
    assert r.status_code == 200
    rows = r.json()
    by_key = {row["issue_key"]: row for row in rows if row.get("issue_key")}
    assert by_key["RFA-100"]["has_children_in_backlog"] is True
    assert by_key["RFA-100"]["planning_mode"] == "whole"
    assert by_key["PRJ-100"]["has_parent_in_backlog"] is True
```

- [ ] **Step 4: Реализовать; прогнать**

```bash
py -3.10 -m pytest tests/test_backlog_*.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/backlog.py tests/...
git commit -m "feat(backlog-api): hierarchy flags в ответе списка

has_parent_in_backlog / has_children_in_backlog + planning_mode +
included_in_planning. Фронт использует для раскрытия RFA-строки.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Frontend: компоненты часов

### Task 11: Компонент `HoursBreakdownTable`

**Files:**
- Create: `frontend/src/components/hours/HoursBreakdownTable.tsx`
- Create: `frontend/src/hooks/useHoursBreakdown.ts`
- Modify: `frontend/src/api/issues.ts` — добавить `getHoursBreakdown`

- [ ] **Step 1: API helper**

`frontend/src/api/issues.ts` (или соответствующий файл):

```typescript
export interface HoursBreakdown {
  issue_id: string;
  year: number;
  quarter: number;
  plan: Record<string, number>;       // analyst, dev, qa, opo, total
  fact_past: Record<string, number>;
  fact_current: Record<string, number>;
  approved: Record<string, number>;
  planable: Record<string, number>;
  draft: Record<string, number>;
  flags: { overrun: boolean; plan_missing: boolean; draft_exceeds_planable: boolean };
}

export const getHoursBreakdown = (issueId: string, year: number, quarter: number) =>
  api.get<HoursBreakdown>(`/issues/${issueId}/hours-breakdown`, { year, quarter });
```

- [ ] **Step 2: TanStack hook**

`frontend/src/hooks/useHoursBreakdown.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { getHoursBreakdown } from '../api/issues';

export function useHoursBreakdown(issueId: string | null, year: number, quarter: number) {
  return useQuery({
    queryKey: ['hours-breakdown', issueId, year, quarter],
    queryFn: () => getHoursBreakdown(issueId!, year, quarter),
    enabled: !!issueId,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 3: Компонент таблицы**

`frontend/src/components/hours/HoursBreakdownTable.tsx`:

```typescript
import { Table, Tag, Progress, Tooltip } from 'antd';
import type { HoursBreakdown } from '../../api/issues';
import { DARK_THEME } from '../../utils/constants';

const ROLES = [
  { key: 'analyst', label: 'Аналитик' },
  { key: 'dev', label: 'Разработка' },
  { key: 'qa', label: 'Тестирование' },
  { key: 'opo', label: 'ОПЭ' },
];

interface Props {
  data: HoursBreakdown;
  loading?: boolean;
}

export default function HoursBreakdownTable({ data, loading }: Props) {
  const rows = ROLES.map(({ key, label }) => ({
    role: label,
    plan: data.plan[key],
    fact_past: data.fact_past[key],
    fact_current: data.fact_current[key],
    approved: data.approved[key],
    planable: data.planable[key],
    draft: data.draft[key],
  }));
  rows.push({
    role: 'Итого',
    plan: data.plan.total,
    fact_past: data.fact_past.total,
    fact_current: data.fact_current.total,
    approved: data.approved.total,
    planable: data.planable.total,
    draft: data.draft.total,
  });

  const fmt = (v: number) => (v === 0 ? '—' : Math.round(v).toString());

  return (
    <div>
      <ProgressBar data={data} />
      <Table
        size="small"
        loading={loading}
        pagination={false}
        rowKey="role"
        dataSource={rows}
        columns={[
          { title: 'Роль', dataIndex: 'role' },
          { title: 'План', dataIndex: 'plan', align: 'right', render: fmt },
          { title: 'Факт прошлых Q', dataIndex: 'fact_past', align: 'right', render: fmt },
          { title: 'Факт текущий', dataIndex: 'fact_current', align: 'right', render: fmt },
          { title: 'Утверждено', dataIndex: 'approved', align: 'right', render: fmt },
          {
            title: 'Запланировать',
            dataIndex: 'planable',
            align: 'right',
            render: (v: number) => (
              <span style={{ color: v < 0 ? DARK_THEME.errorColor : DARK_THEME.successColor, fontWeight: 600 }}>
                {fmt(v)}
              </span>
            ),
          },
          { title: 'Черновик', dataIndex: 'draft', align: 'right', render: fmt },
        ]}
      />
      {data.flags.overrun && (
        <Tag color="error" style={{ marginTop: 8 }}>Перерасход</Tag>
      )}
      {data.flags.plan_missing && (
        <Tag color="warning" style={{ marginTop: 8 }}>План не задан</Tag>
      )}
    </div>
  );
}

function ProgressBar({ data }: { data: HoursBreakdown }) {
  const total = data.plan.total || 1;
  const pct = (v: number) => (v / total) * 100;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', height: 18, borderRadius: 3, overflow: 'hidden', background: '#1e293b' }}>
        <Tooltip title={`Факт прошлых Q: ${Math.round(data.fact_past.total)}ч`}>
          <div style={{ background: '#94a3b8', width: `${pct(data.fact_past.total)}%` }} />
        </Tooltip>
        <Tooltip title={`Факт текущий: ${Math.round(data.fact_current.total)}ч`}>
          <div style={{ background: '#fb923c', width: `${pct(data.fact_current.total)}%` }} />
        </Tooltip>
        <Tooltip title={`Утверждено (остаток): ${Math.round(Math.max(0, data.approved.total - data.fact_current.total))}ч`}>
          <div style={{ background: '#38bdf8', width: `${pct(Math.max(0, data.approved.total - data.fact_current.total))}%` }} />
        </Tooltip>
        <Tooltip title={`Запланировать: ${Math.round(data.planable.total)}ч`}>
          <div style={{ background: '#22c55e', width: `${pct(Math.max(0, data.planable.total))}%` }} />
        </Tooltip>
      </div>
      <div style={{ fontSize: 11, color: '#a78bfa', marginTop: 6 }}>
        Черновик: {Math.round(data.draft.total)}ч (информационно)
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Smoke-test (просто проверить build)**

```bash
cd frontend && npm run lint && cd ..
```

Expected: no errors. Если eslint ругается на отсутствие тестов в компоненте — игнор, fine.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/issues.ts frontend/src/hooks/useHoursBreakdown.ts frontend/src/components/hours/HoursBreakdownTable.tsx
git commit -m "feat(frontend): HoursBreakdownTable — 6 колонок + прогресс-бар

Reusable компонент для длинной RFA. Используется в бэклоге (раскрытие)
и в Сценарии (drawer ℹ). Хук useHoursBreakdown поверх TanStack Query.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: `PlanEditDrawer` + `PlanHistoryDrawer`

**Files:**
- Create: `frontend/src/components/hours/PlanEditDrawer.tsx`
- Create: `frontend/src/components/hours/PlanHistoryView.tsx`
- Modify: `frontend/src/api/issues.ts` — добавить `patchPlan`, `revertPlan`, `getPlanHistory`, `resolveConflict`, `getPlanConflicts`

- [ ] **Step 1: API**

```typescript
export interface PlanAuditRow {
  id: string; role: string;
  value_before: number | null; value_after: number | null;
  source: string; user_id: string | null;
  comment: string | null; created_at: string;
}

export const patchPlan = (id: string, role_hours: Record<string, number | null>, comment: string) =>
  api.patch(`/issues/${id}/plan`, { role_hours, comment });

export const revertPlan = (id: string, audit_id?: string) =>
  api.post(`/issues/${id}/plan/revert`, { audit_id: audit_id ?? null });

export const getPlanHistory = (id: string) =>
  api.get<PlanAuditRow[]>(`/issues/${id}/plan-history`);

export const resolvePlanConflict = (id: string, action: 'accept_jira' | 'ignore', role: string) =>
  api.post(`/issues/${id}/plan/conflict-resolve`, { action, role });

export const getPlanConflicts = (id: string) =>
  api.get<{role: string; audit_id: string; value_jira: number; value_before: number}[]>(`/issues/${id}/plan-conflicts`);
```

- [ ] **Step 2: PlanEditDrawer**

`frontend/src/components/hours/PlanEditDrawer.tsx`:

```typescript
import { Drawer, Form, InputNumber, Button, Input, Space, Table, message } from 'antd';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { patchPlan, getPlanHistory, revertPlan, type PlanAuditRow } from '../../api/issues';

interface JiraValues { analyst: number | null; dev: number | null; qa: number | null; opo: number | null; }

interface Props {
  open: boolean;
  onClose: () => void;
  issueId: string;
  issueKey: string;
  jiraValues: JiraValues;
  effectiveValues: JiraValues;
}

export default function PlanEditDrawer({ open, onClose, issueId, issueKey, jiraValues, effectiveValues }: Props) {
  const [form] = Form.useForm();
  const [showHistory, setShowHistory] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    if (open) form.setFieldsValue({ ...effectiveValues, comment: '' });
  }, [open, effectiveValues, form]);

  const editMut = useMutation({
    mutationFn: (vals: any) => patchPlan(issueId, {
      analyst: vals.analyst, dev: vals.dev, qa: vals.qa, opo: vals.opo,
    }, vals.comment),
    onSuccess: () => {
      message.success('План обновлён');
      qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      onClose();
    },
  });

  const revertMut = useMutation({
    mutationFn: () => revertPlan(issueId),
    onSuccess: () => {
      message.success('Сброс к Jira');
      qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      onClose();
    },
  });

  return (
    <Drawer
      open={open} onClose={onClose}
      title={`Редактирование плана · ${issueKey}`}
      width={520}
    >
      <Form form={form} layout="vertical" onFinish={editMut.mutate}>
        <Table
          size="small" pagination={false} rowKey="role"
          dataSource={[
            { role: 'Аналитик', key: 'analyst' },
            { role: 'Разработка', key: 'dev' },
            { role: 'Тестирование', key: 'qa' },
            { role: 'ОПЭ', key: 'opo' },
          ]}
          columns={[
            { title: 'Роль', dataIndex: 'role' },
            { title: 'Jira', dataIndex: 'key', align: 'right',
              render: (k: string) => <span style={{ color: '#94a3b8' }}>{(jiraValues as any)[k] ?? '—'}</span> },
            { title: 'Правка', dataIndex: 'key', align: 'right',
              render: (k: string) => (
                <Form.Item name={k} noStyle>
                  <InputNumber min={0} max={9999} style={{ width: 80 }} />
                </Form.Item>
              ),
            },
          ]}
        />
        <Form.Item
          label="Комментарий"
          name="comment"
          rules={[{ required: true, min: 1, message: 'Комментарий обязателен' }]}
          style={{ marginTop: 12 }}
        >
          <Input.TextArea rows={3} placeholder="Например: после ретро Q1" />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={editMut.isPending}>Сохранить</Button>
          <Button onClick={() => revertMut.mutate()} loading={revertMut.isPending}>Сбросить к Jira</Button>
          <Button onClick={() => setShowHistory(s => !s)}>{showHistory ? 'Скрыть' : 'Показать'} историю</Button>
        </Space>
      </Form>
      {showHistory && <PlanHistorySection issueId={issueId} />}
    </Drawer>
  );
}

function PlanHistorySection({ issueId }: { issueId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['plan-history', issueId],
    queryFn: () => getPlanHistory(issueId),
  });
  return (
    <Table<PlanAuditRow>
      style={{ marginTop: 16 }}
      size="small"
      loading={isLoading}
      pagination={false}
      rowKey="id"
      dataSource={data ?? []}
      columns={[
        { title: 'Дата', dataIndex: 'created_at', render: (v: string) => new Date(v).toLocaleString('ru') },
        { title: 'Роль', dataIndex: 'role' },
        { title: 'Было', dataIndex: 'value_before', align: 'right', render: (v) => v ?? '—' },
        { title: 'Стало', dataIndex: 'value_after', align: 'right', render: (v) => v ?? '—' },
        { title: 'Источник', dataIndex: 'source' },
        { title: 'Комментарий', dataIndex: 'comment', render: (v) => v ?? '—' },
      ]}
    />
  );
}
```

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint && cd ..
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/issues.ts frontend/src/components/hours/PlanEditDrawer.tsx
git commit -m "feat(frontend): PlanEditDrawer + история правок плана

Drawer 520px справа. Поля: Jira (read-only) | Правка (input) + обязательный
комментарий. Кнопки Сохранить / Сбросить к Jira / Показать историю.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Frontend: интеграция в страницы

### Task 13: BacklogPage — раскрытие RFA-строки + переключатель режима

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`
- Create: `frontend/src/components/backlog/RfaExpandedRow.tsx`

- [ ] **Step 1: Найти текущую таблицу бэклога**

```bash
grep -n "expandable\|Table" frontend/src/pages/BacklogPage.tsx | head -20
```

- [ ] **Step 2: Создать `RfaExpandedRow`**

`frontend/src/components/backlog/RfaExpandedRow.tsx`:

```typescript
import { Radio, Checkbox, Space, Card, Button, Alert } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import HoursBreakdownTable from '../hours/HoursBreakdownTable';
import { useHoursBreakdown } from '../../hooks/useHoursBreakdown';
import { useState } from 'react';
import PlanEditDrawer from '../hours/PlanEditDrawer';
import { useGlobalQuarter } from '../../hooks/useGlobalQuarter';  // existing or stub
import api from '../../api/client';

interface Props {
  backlogItemId: string;
  issueId: string;
  issueKey: string;
  planningMode: 'whole' | 'by_epics';
  includedInPlanning: boolean;
  hasChildren: boolean;
  jiraValues: any;
  effectiveValues: any;
  children?: Array<{ id: string; backlog_item_id: string; key: string; title: string; included_in_planning: boolean; status: string; }>;
}

export default function RfaExpandedRow(p: Props) {
  const { year, quarter } = useGlobalQuarter();
  const { data, isLoading } = useHoursBreakdown(p.issueId, year, quarter);
  const [editOpen, setEditOpen] = useState(false);
  const qc = useQueryClient();

  const modeMut = useMutation({
    mutationFn: (mode: 'whole' | 'by_epics') => api.patch(`/backlog/${p.backlogItemId}/planning-mode`, { mode }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
  const incMut = useMutation({
    mutationFn: ({ id, included }: { id: string; included: boolean }) =>
      api.patch(`/backlog/${id}/included`, { included }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });

  return (
    <Card size="small" style={{ background: '#0f2340' }}>
      {p.hasChildren && (
        <Space direction="vertical" style={{ width: '100%', marginBottom: 12 }}>
          <Radio.Group
            value={p.planningMode}
            onChange={(e) => modeMut.mutate(e.target.value)}
          >
            <Radio value="whole">RFA целиком</Radio>
            <Radio value="by_epics">По Эпикам</Radio>
          </Radio.Group>
          {p.planningMode === 'by_epics' && (
            <Checkbox
              checked={p.includedInPlanning}
              onChange={(e) => incMut.mutate({ id: p.backlogItemId, included: e.target.checked })}
            >
              Включить саму RFA (для непокрытых кварталов)
            </Checkbox>
          )}
        </Space>
      )}
      {data && <HoursBreakdownTable data={data} loading={isLoading} />}
      <div style={{ marginTop: 12 }}>
        <Button onClick={() => setEditOpen(true)}>✎ Редактировать план</Button>
      </div>
      <PlanEditDrawer
        open={editOpen} onClose={() => setEditOpen(false)}
        issueId={p.issueId} issueKey={p.issueKey}
        jiraValues={p.jiraValues} effectiveValues={p.effectiveValues}
      />
      {p.children && p.children.length > 0 && (
        <ChildrenList items={p.children}
          mode={p.planningMode}
          onToggle={(child, value) => incMut.mutate({ id: child.backlog_item_id, included: value })} />
      )}
    </Card>
  );
}

function ChildrenList({ items, mode, onToggle }: any) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}>Дочерние Эпики</div>
      {items.map((c: any) => (
        <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
          {mode === 'by_epics' && (
            <Checkbox checked={c.included_in_planning} onChange={(e) => onToggle(c, e.target.checked)} />
          )}
          <span style={{ fontFamily: 'monospace' }}>{c.key}</span>
          <span style={{ flex: 1 }}>{c.title}</span>
          <span style={{ color: '#38bdf8', fontSize: 12 }}>{c.status}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire expandable в `BacklogPage`**

В `Table` бэклога добавить `expandable`:

```typescript
expandable={{
  expandedRowRender: (row) => (
    <RfaExpandedRow
      backlogItemId={row.id}
      issueId={row.issue_id}
      issueKey={row.issue_key}
      planningMode={row.planning_mode}
      includedInPlanning={row.included_in_planning}
      hasChildren={row.has_children_in_backlog}
      jiraValues={row.plan_jira_values}     // см. backend response
      effectiveValues={row.plan_effective_values}
      children={row.children_in_backlog}    // если nested подгружен
    />
  ),
  rowExpandable: (row) => row.has_children_in_backlog || row.has_parent_in_backlog === false,
}}
```

- [ ] **Step 4: useGlobalQuarter — если хука нет, использовать существующий способ глобального квартала (URL search params).**

```bash
grep -rn "useGlobalQuarter\|globalQuarter\|year=2026" frontend/src/hooks/ | head -5
```

Если хука нет — стаб: `const { year, quarter } = { year: 2026, quarter: 2 }` (но взять из глобального фильтра выбранного периода — проверить как сделано в Dashboard / Analytics).

- [ ] **Step 5: Lint + ручная проверка**

```bash
cd frontend && npm run lint && cd ..
```

Запустить dev-сервер, открыть `/backlog`, развернуть RFA — проверить визуально.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx frontend/src/components/backlog/RfaExpandedRow.tsx
git commit -m "feat(backlog-page): раскрытие RFA-строки с таблицей часов + режим

▶ на строке RFA с дочками → панель с прогресс-баром, 6 колонок,
радио целиком/по Эпикам, чекбоксы участия дочек, кнопка правки плана.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: PlanningPage — иконка ℹ на RFA → drawer

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx` (или соответствующий child-компонент сценария)
- Create: `frontend/src/components/hours/HoursBreakdownDrawer.tsx`

- [ ] **Step 1: Drawer-обёртка**

`frontend/src/components/hours/HoursBreakdownDrawer.tsx`:

```typescript
import { Drawer } from 'antd';
import HoursBreakdownTable from './HoursBreakdownTable';
import { useHoursBreakdown } from '../../hooks/useHoursBreakdown';

interface Props {
  open: boolean;
  onClose: () => void;
  issueId: string | null;
  issueKey?: string;
  year: number;
  quarter: number;
}

export default function HoursBreakdownDrawer({ open, onClose, issueId, issueKey, year, quarter }: Props) {
  const { data, isLoading } = useHoursBreakdown(issueId, year, quarter);
  return (
    <Drawer open={open} onClose={onClose} width={720}
      title={`Разбивка часов · ${issueKey ?? ''} · Q${quarter} ${year}`}>
      {data && <HoursBreakdownTable data={data} loading={isLoading} />}
    </Drawer>
  );
}
```

- [ ] **Step 2: На строке RFA в Сценарии добавить иконку ℹ**

Найти где рендерится список инициатив в PlanningPage:

```bash
grep -n "RFA\|initiative\|issue_key" frontend/src/pages/PlanningPage.tsx | head -10
```

В колонке ключа задачи добавить:

```tsx
{isRfaWithChildren && (
  <InfoCircleOutlined
    onClick={(e) => { e.stopPropagation(); setBreakdown({ issueId, issueKey, open: true }); }}
    style={{ marginLeft: 6, cursor: 'pointer', color: '#38bdf8' }}
  />
)}
```

И смонтировать drawer на уровне страницы:

```tsx
<HoursBreakdownDrawer
  open={breakdown.open} onClose={() => setBreakdown(b => ({ ...b, open: false }))}
  issueId={breakdown.issueId} issueKey={breakdown.issueKey}
  year={selectedYear} quarter={selectedQuarter}
/>
```

- [ ] **Step 3: Lint + ручная проверка**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/hours/HoursBreakdownDrawer.tsx frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning-page): иконка ℹ на RFA → drawer с разбивкой часов

Иконка появляется только если задача — RFA с детьми. Drawer 720px справа,
переиспользует HoursBreakdownTable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Конфликт-баннер в раскрытой RFA

**Files:**
- Modify: `frontend/src/components/backlog/RfaExpandedRow.tsx`
- Create: `frontend/src/components/hours/PlanConflictBanner.tsx`

- [ ] **Step 1: Компонент баннера**

```typescript
import { Alert, Button, Space } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPlanConflicts, resolvePlanConflict } from '../../api/issues';

interface Props { issueId: string }

const ROLE_LABEL: Record<string, string> = {
  analyst: 'Аналитик', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ',
};

export default function PlanConflictBanner({ issueId }: Props) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['plan-conflicts', issueId],
    queryFn: () => getPlanConflicts(issueId),
  });
  const resolveMut = useMutation({
    mutationFn: ({ action, role }: { action: 'accept_jira' | 'ignore'; role: string }) =>
      resolvePlanConflict(issueId, action, role),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan-conflicts', issueId] });
      qc.invalidateQueries({ queryKey: ['hours-breakdown', issueId] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
    },
  });
  if (!data || data.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      {data.map((c) => (
        <Alert
          key={c.audit_id}
          type="warning"
          showIcon
          message={`В Jira план изменили на ${c.value_jira}ч (${ROLE_LABEL[c.role] ?? c.role}). Сейчас активна ручная правка.`}
          action={
            <Space>
              <Button size="small" onClick={() => resolveMut.mutate({ action: 'accept_jira', role: c.role })}>
                Принять Jira
              </Button>
              <Button size="small" onClick={() => resolveMut.mutate({ action: 'ignore', role: c.role })}>
                Игнорировать
              </Button>
            </Space>
          }
          style={{ marginBottom: 6 }}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Вставить в RfaExpandedRow перед HoursBreakdownTable**

```tsx
<PlanConflictBanner issueId={p.issueId} />
```

- [ ] **Step 3: Lint + Commit**

```bash
git add frontend/src/components/hours/PlanConflictBanner.tsx frontend/src/components/backlog/RfaExpandedRow.tsx
git commit -m "feat(plan-conflict): баннер конфликта Jira-vs-ручная

Над таблицей часов RFA — список открытых конфликтов с кнопками
Принять Jira / Игнорировать.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7 — Справка + лента «Что нового»

### Task 16: Обновить docs/help/backlog.md + docs/help/planning.md

**Files:**
- Modify: `docs/help/backlog.md`
- Modify: `docs/help/planning.md`

- [ ] **Step 1: Прочитать текущий `docs/help/backlog.md`**

- [ ] **Step 2: Добавить разделы**

В конце `docs/help/backlog.md`:

```markdown
## Раскрытие RFA: что внутри

Если у инициативы есть дочерние Эпики, слева от ключа появится стрелка ▶. Клик — раскроется панель:

- **Прогресс-бар часов** сверху: Факт прошлых кварталов · Факт текущий квартал · Утверждено (остаток) · Запланировать (свободно). Под полосой — отдельная заметка о черновиках.
- **Таблица по ролям** (Аналитик / Разработка / Тестирование / ОПЭ): шесть колонок — План / Факт прошлых Q / Факт текущий / Утверждено / Запланировать / Черновик. Период «текущего» квартала берётся из глобального фильтра наверху страницы.
- **Список дочерних Эпиков** со статусом (утверждён / черновик / без статуса) и индивидуальными чекбоксами участия (см. ниже).

## Режим планирования группы

Над таблицей часов — переключатель:
- **RFA целиком** (по умолчанию): в сценарий идёт сама RFA, дочерние Эпики скрыты от выбора.
- **По Эпикам**: в сценарий идут отмеченные дочерние Эпики. RFA-родитель остаётся доступным как отдельная галочка — её включают для «непокрытых» кварталов длинной RFA.

Если в режиме «По Эпикам» одновременно отметить RFA и одну из её дочек, а их квартал совпадает — появится оранжевый знак: часы будут посчитаны дважды. Это допустимо в редких случаях; решение остаётся за вами.

## Ручная правка плановых часов

Кнопка «✎ Редактировать план» в раскрытой панели открывает drawer справа:

- Слева — текущее значение из Jira (read-only).
- Справа — поле ввода вашей правки.
- Обязательное поле «Комментарий» (объясните, зачем правка).
- Сохранение — мгновенное, без перезагрузки страницы.
- «Сбросить к Jira» — возвращает все значения к синхронизированным с Jira.
- «Показать историю» — журнал всех правок с авторами и комментариями.

Колонка «План» в таблице часов будет показывать вашу правку. Если хотите сравнить — наведите курсор: всплывёт значение из Jira.

## Конфликт с Jira

Если в Jira план изменили *после* вашей правки, при следующей синхронизации над таблицей появится баннер:

> **В Jira план изменили на N часов (Роль). Сейчас активна ручная правка.**
> [Принять Jira]  [Игнорировать]

- **Принять Jira** — заменяет вашу правку значением из Jira.
- **Игнорировать** — оставляет вашу правку, баннер исчезает.

Ваша ручная правка никогда не теряется автоматически — её можно потерять только через явное «Принять Jira» или «Сбросить к Jira».
```

В `docs/help/planning.md` — раздел:

```markdown
## Разбивка часов длинной RFA

Если в сценарии есть RFA с дочерними Эпиками, рядом с её ключом появится иконка ℹ. Клик откроет drawer справа с той же таблицей 6 колонок, что и в бэклоге (см. справку по бэклогу). Период — из глобального фильтра-квартала.
```

- [ ] **Step 3: Commit**

```bash
git add docs/help/backlog.md docs/help/planning.md
git commit -m "docs(help): RFA-раскрытие, режим планирования, правка плана

backlog.md — 4 новых раздела; planning.md — раздел про ℹ-drawer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Заметки в ленту «Что нового»

**Files:**
- Запуск `scripts/release_note.py add` 4 раза

- [ ] **Step 1: Создать 4 заметки**

```bash
py -3.10 scripts/release_note.py add --type new --section backlog \
  --title "Длинная RFA: остаток часов по ролям и кварталам" \
  --description "У RFA с дочерними Эпиками появилось раскрытие строки в бэклоге. Внутри — таблица по ролям (Аналитик / Разработка / Тестирование / ОПЭ) с шестью колонками: План, Факт прошлых кварталов, Факт текущий, Утверждено, Запланировать, Черновик. Период текущего квартала берётся из глобального фильтра сверху страницы."

py -3.10 scripts/release_note.py add --type new --section backlog \
  --title "Режим планирования группы RFA" \
  --description "В раскрытой строке RFA — переключатель «RFA целиком / По Эпикам». В режиме «По Эпикам» вы отмечаете отдельные дочерние Эпики; RFA-родитель остаётся доступным как опциональная галочка для непокрытых кварталов. Пересечение «RFA + дочка в одном квартале» подсвечивается оранжевым."

py -3.10 scripts/release_note.py add --type new --section backlog \
  --title "Ручная правка плановых часов с историей" \
  --description "Кнопка «Редактировать план» в раскрытой RFA или у любой задачи открывает drawer: вводите часы по ролям, обязательный комментарий — и план обновляется без обхода через Jira. История всех правок (кто, когда, что) хранится и доступна по ссылке «Показать историю». Если в Jira план потом изменили — появится баннер «Принять Jira / Игнорировать», ваша правка не теряется автоматически."

py -3.10 scripts/release_note.py add --type new --section planning \
  --title "Разбивка часов RFA в сценарии" \
  --description "Рядом с ключом длинной RFA в сценарии появилась иконка ℹ. Клик — drawer с таблицей часов (План / Факт / Утверждено / Запланировать / Черновик per роль) для выбранного квартала."
```

- [ ] **Step 2: Проверить в админке `/settings → Что нового`**

Запустить backend + frontend, открыть `/settings`, вкладка релизных заметок — должны появиться 4 черновика.

- [ ] **Step 3: Commit (если что-то изменилось в файлах — fixture/seed). Если заметки лежат только в БД, отдельный commit не нужен.**

---

## Phase 8 — финальная сборка

### Task 18: Прогон полного теста + ручная проверка золотых путей

- [ ] **Step 1: Прогнать весь pytest**

```bash
py -3.10 -m pytest tests/ -v
```

Expected: все новые тесты PASS; известные pre-existing failures (см. memory `project_capacity_overhaul_followups`, `project_ci_red_pre_existing`) — можно игнорировать, не наша область.

- [ ] **Step 2: Запустить full-stack smoke**

```bash
.\scripts\smoke-local.ps1
```

- [ ] **Step 3: Проверить золотые пути в браузере**

1. `/backlog` → найти RFA с дочками → ▶ раскрыть → проверить таблицу, переключатель режима, кнопку правки.
2. Правка → drawer → сохранить → таблица обновилась.
3. История правок — открыть, проверить запись.
4. `/planning` → открыть сценарий → ℹ на RFA → drawer открылся.
5. `/settings → Что нового` → 4 черновика на месте.

- [ ] **Step 4: Прогнать e2e (если применимо)**

```bash
.\scripts\e2e-local.ps1
```

- [ ] **Step 5: Финальный commit (если что-то поправили)**

```bash
git add ...
git commit -m "chore: smoke + golden paths verified"
git push origin main
```

---

## Открытые вопросы (на будущее, не блокируют этот план)

- Перформанс расчёта 6 колонок при массовом запросе (например для всех RFA в бэклоге одним endpoint'ом). Сейчас — N+1, по одному запросу на RFA. Если медленно — добавить batch-эндпоинт `/issues/hours-breakdown-batch`.
- Что делать если факт текущий > утверждено (per роль) в общей формуле «Запланировать». Сейчас фиксированная формула из spec; edge case с оранжевой подсветкой. Если PM попросит — менять на `max(approved, fact_current)`.
- Карточка задачи (детальная страница) — пока не делаем, формат «Часы»-блока готов и переиспользуется.
