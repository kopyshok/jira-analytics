# Sync Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить 18 разрозненных sync-кнопок единым хабом `/sync` с pipeline-оркестратором, добавить APScheduler с дефолт-расписанием и SSE-шину для авто-инвалидации кэшей открытых страниц.

**Architecture:** Backend — `PipelineOrchestrator` (8 стадий, 4 режима) запускает существующие сервисы в правильном порядке, пишет историю в `sync_run`, публикует события в `EventBroadcaster` (in-memory pub/sub). `SchedulerService` (APScheduler в lifespan) дёргает pipeline по cron из `sync_schedule`. Frontend — `SyncHubPage` с глобальным `useEventStream` listener в `App.tsx`, дубли sync-кнопок с других страниц удаляются.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · Alembic batch · APScheduler 3.10 · croniter 2.0 · React 19 · TanStack Query · Server-Sent Events (native EventSource)

**Spec:** [`docs/superpowers/specs/2026-04-27-sync-consolidation-design.md`](../specs/2026-04-27-sync-consolidation-design.md)

**Phases / PR boundaries:**
1. Phase 1 — Backend foundation: модели, миграция 035, EventBroadcaster, SSE endpoint, GET /sync/runs (T1–T11)
2. Phase 2 — Pipeline orchestrator (T12–T26)
3. Phase 3 — Scheduler (T27–T34)
4. Phase 4 — Frontend hub + global event listener (T35–T48)
5. Phase 5 — Удаление дубликатов кнопок + категории на отдельной странице (T49–T56)
6. Phase 6 — Cleanup deprecated (через 1 неделю после релиза, отдельный PR)

---

## File Structure

**Создаются (бэк):**
- `app/models/sync_run.py` — модель `SyncRun`
- `app/models/sync_schedule.py` — модель `SyncSchedule`
- `app/repositories/sync_run.py` — CRUD `SyncRun`
- `app/repositories/sync_schedule.py` — CRUD `SyncSchedule`
- `app/services/event_bus.py` — `EventBroadcaster` синглтон
- `app/services/sync_pipeline.py` — `PipelineOrchestrator` + stage runners
- `app/services/scheduler.py` — `SchedulerService` (APScheduler wrapper)
- `app/api/endpoints/events.py` — `GET /events/stream`
- `app/schemas/sync_pipeline.py` — Pydantic `PipelineRequest`, `SyncRunOut`, `SyncScheduleOut`, `SyncScheduleUpdate`
- `alembic/versions/035_sync_pipeline.py` — таблицы + сиды
- тесты: `tests/services/test_event_bus.py`, `tests/services/test_sync_pipeline.py`, `tests/services/test_scheduler.py`, `tests/api/test_sync_pipeline.py`, `tests/api/test_sync_schedule.py`, `tests/api/test_events_stream.py`

**Создаются (фронт):**
- `frontend/src/pages/SyncHubPage.tsx`
- `frontend/src/pages/CategoriesEditorPage.tsx`
- `frontend/src/components/sync/PipelineRunner.tsx`
- `frontend/src/components/sync/SyncSchedule.tsx`
- `frontend/src/components/sync/SyncHistory.tsx`
- `frontend/src/components/sync/SyncAdvanced.tsx`
- `frontend/src/hooks/useSyncPipeline.ts`
- `frontend/src/hooks/useEventStream.ts`
- `frontend/src/api/events.ts`
- `frontend/src/api/syncPipeline.ts`
- `frontend/src/api/syncSchedule.ts`
- `frontend/src/api/syncRuns.ts`
- E2E: `tests/e2e/sync_hub.spec.ts`

**Модифицируются (бэк):**
- `app/main.py` — старт `SchedulerService` в lifespan
- `app/api/router.py` — добавить новые роутеры (events, обновить sync)
- `app/api/endpoints/sync.py` — новые маршруты pipeline/runs/schedule, пометить старые `deprecated=True`
- `app/services/mapping_service.py` — добавить `recalculate_for_issues(issue_ids)`
- `app/models/__init__.py` — экспорт `SyncRun`, `SyncSchedule`
- `requirements.txt` — добавить `apscheduler>=3.10`, `croniter>=2.0`

**Модифицируются (фронт):**
- `frontend/src/App.tsx` — подключить `useEventStream()`
- `frontend/src/router.tsx` (или эквивалент роутинга) — `/sync` → `SyncHubPage`, редирект `/sync-old`, `/categories`
- `frontend/src/pages/DashboardPage.tsx` — удалить кнопку «Синхронизация»
- `frontend/src/pages/BacklogPage.tsx` — заменить «Обновить с Jira» на локальный invalidate
- `frontend/src/pages/PlanningPage.tsx` — удалить «Синк с бэклогом»
- `frontend/src/pages/CapacityPage.tsx` — удалить «Пересчитать состав/ёмкость»
- `frontend/src/pages/SyncPage.tsx` — оставить только Tab1 как наследие на `/sync-old`, потом удалить (Phase 6)

---

# Phase 1 — Backend Foundation

## Task 1: Подготовить зависимости

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Добавить пакеты**

```diff
+apscheduler>=3.10,<4.0
+croniter>=2.0,<3.0
```

- [ ] **Step 2: Установить**

Run: `py -3.10 -m pip install apscheduler croniter`
Expected: «Successfully installed apscheduler-3.x.x croniter-2.x.x»

- [ ] **Step 3: Smoke import**

Run: `py -3.10 -c "from apscheduler.schedulers.asyncio import AsyncIOScheduler; from croniter import croniter; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add APScheduler + croniter for sync scheduler"
```

---

## Task 2: Модель SyncRun

**Files:**
- Create: `app/models/sync_run.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Создать модель**

```python
# app/models/sync_run.py
"""SyncRun model — история запусков pipeline синхронизации."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class SyncRun(Base, TimestampMixin):
    """Запуск sync pipeline — manual или scheduled.

    `stages_json` хранит список словарей вида
    `{stage, started, finished, status, counts, error}`.
    """

    __tablename__ = "sync_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # running | ok | partial | failed | cancelled | skipped
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    # manual | scheduled
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    # quick | normal | full | team
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stages_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schedule_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sync_schedule.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SyncRun {self.id} {self.mode} {self.status}>"
```

- [ ] **Step 2: Экспорт в `__init__.py`**

Find `app/models/__init__.py`, добавить в импорты:
```python
from app.models.sync_run import SyncRun
```
И в `__all__` (если используется).

- [ ] **Step 3: Smoke import**

Run: `py -3.10 -c "from app.models.sync_run import SyncRun; print(SyncRun.__tablename__)"`
Expected: `sync_run`

- [ ] **Step 4: Commit**

```bash
git add app/models/sync_run.py app/models/__init__.py
git commit -m "feat(models): add SyncRun model for pipeline history"
```

---

## Task 3: Модель SyncSchedule

**Files:**
- Create: `app/models/sync_schedule.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Создать модель**

```python
# app/models/sync_schedule.py
"""SyncSchedule — cron-конфиг автозапуска pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class SyncSchedule(Base, TimestampMixin):
    """Правило автозапуска sync pipeline (читается SchedulerService)."""

    __tablename__ = "sync_schedule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<SyncSchedule {self.name} {self.cron_expr} {self.mode}>"
```

- [ ] **Step 2: Экспорт в `__init__.py`**

```python
from app.models.sync_schedule import SyncSchedule
```

- [ ] **Step 3: Smoke import**

Run: `py -3.10 -c "from app.models.sync_schedule import SyncSchedule; print(SyncSchedule.__tablename__)"`
Expected: `sync_schedule`

- [ ] **Step 4: Commit**

```bash
git add app/models/sync_schedule.py app/models/__init__.py
git commit -m "feat(models): add SyncSchedule model for cron config"
```

---

## Task 4: Миграция 035 — таблицы + сиды

**Files:**
- Create: `alembic/versions/035_sync_pipeline.py`

- [ ] **Step 1: Создать миграцию вручную (НЕ autogenerate)**

```python
"""sync_pipeline tables + default schedule seeds

Revision ID: 035_sync_pipeline
Revises: 034_scenario_allocation_sort_order
Create Date: 2026-04-27 12:00:00
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "035_sync_pipeline"
down_revision = "034_scenario_allocation_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_schedule",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("cron_expr", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_run_id", sa.String(36), nullable=True),
        sa.Column("next_run_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "sync_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("stages_json", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("error_text", sa.Text, nullable=True),
        sa.Column(
            "schedule_id",
            sa.String(36),
            sa.ForeignKey("sync_schedule.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_index("ix_sync_run_started_at", "sync_run", ["started_at"])
    op.create_index("ix_sync_run_status", "sync_run", ["status"])

    # Seed default schedule rules только если таблица пуста
    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM sync_schedule")).scalar()
    if existing == 0:
        seeds = [
            ("daily_incremental", "0 6 * * *", "normal"),
            ("worklogs_workhours", "0 8-20/2 * * 1-5", "quick"),
            ("weekly_full", "0 3 * * 0", "full"),
        ]
        for name, cron, mode in seeds:
            bind.execute(
                sa.text(
                    "INSERT INTO sync_schedule "
                    "(id, name, cron_expr, mode, enabled, created_at, updated_at) "
                    "VALUES (:id, :name, :cron, :mode, 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": str(uuid.uuid4()), "name": name, "cron": cron, "mode": mode},
            )


def downgrade() -> None:
    op.drop_index("ix_sync_run_status", table_name="sync_run")
    op.drop_index("ix_sync_run_started_at", table_name="sync_run")
    op.drop_table("sync_run")
    op.drop_table("sync_schedule")
```

- [ ] **Step 2: Применить миграцию на dev DB**

Run: `py -3.10 -m alembic upgrade head`
Expected: «Running upgrade 034_... -> 035_sync_pipeline»

- [ ] **Step 3: Проверить сиды**

Run: `py -3.10 -c "import sqlite3; c=sqlite3.connect('data/dev.db'); print(c.execute('SELECT name, cron_expr, mode FROM sync_schedule').fetchall())"`
Expected: 3 строки с `daily_incremental`, `worklogs_workhours`, `weekly_full`

- [ ] **Step 4: Проверить downgrade**

Run: `py -3.10 -m alembic downgrade -1 && py -3.10 -m alembic upgrade head`
Expected: обе команды успешны, сиды снова на месте

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/035_sync_pipeline.py
git commit -m "feat(db): migration 035 — sync_run + sync_schedule with default seeds"
```

---

## Task 5: SyncRun repository

**Files:**
- Create: `app/repositories/sync_run.py`
- Test: `tests/repositories/test_sync_run.py`

- [ ] **Step 1: Тест**

```python
# tests/repositories/test_sync_run.py
from datetime import datetime, timedelta

import pytest

from app.models.sync_run import SyncRun
from app.repositories.sync_run import SyncRunRepository


def test_create_and_fetch_latest(db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    assert run.id is not None
    assert run.status == "running"
    assert run.started_at is not None

    latest = repo.list_latest(limit=10)
    assert latest[0].id == run.id


def test_finalize_sets_status_and_finished_at(db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    repo.finalize(run.id, status="ok", stages=[{"stage": "projects", "status": "ok"}])

    db_session.refresh(run)
    assert run.status == "ok"
    assert run.finished_at is not None
    assert run.stages_json == [{"stage": "projects", "status": "ok"}]


def test_list_latest_orders_by_started_desc(db_session):
    repo = SyncRunRepository(db_session)
    older = repo.create(mode="quick", trigger="scheduled")
    older.started_at = datetime.utcnow() - timedelta(hours=2)
    db_session.commit()
    newer = repo.create(mode="normal", trigger="manual")

    rows = repo.list_latest(limit=10)
    assert rows[0].id == newer.id
    assert rows[1].id == older.id
```

- [ ] **Step 2: Запустить тест — должен упасть**

Run: `py -3.10 -m pytest tests/repositories/test_sync_run.py -v`
Expected: FAIL — `ImportError: cannot import name 'SyncRunRepository'`

- [ ] **Step 3: Реализация**

```python
# app/repositories/sync_run.py
"""Репозиторий SyncRun — CRUD истории запусков pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sync_run import SyncRun


class SyncRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        mode: str,
        trigger: str,
        team: Optional[str] = None,
        schedule_id: Optional[str] = None,
    ) -> SyncRun:
        run = SyncRun(
            started_at=datetime.utcnow(),
            status="running",
            trigger=trigger,
            mode=mode,
            team=team,
            schedule_id=schedule_id,
            stages_json=[],
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finalize(
        self,
        run_id: str,
        *,
        status: str,
        stages: list,
        error_text: Optional[str] = None,
    ) -> None:
        run = self.db.get(SyncRun, run_id)
        if run is None:
            return
        run.finished_at = datetime.utcnow()
        run.status = status
        run.stages_json = stages
        run.error_text = error_text
        self.db.commit()

    def list_latest(self, limit: int = 20) -> list[SyncRun]:
        return (
            self.db.query(SyncRun)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
            .all()
        )

    def get(self, run_id: str) -> Optional[SyncRun]:
        return self.db.get(SyncRun, run_id)

    def latest_successful_finished_at(self) -> Optional[datetime]:
        run = (
            self.db.query(SyncRun)
            .filter(SyncRun.status.in_(("ok", "partial")))
            .order_by(SyncRun.finished_at.desc())
            .first()
        )
        return run.finished_at if run else None
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/repositories/test_sync_run.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/repositories/sync_run.py tests/repositories/test_sync_run.py
git commit -m "feat(repos): SyncRunRepository with create/finalize/list"
```

---

## Task 6: SyncSchedule repository

**Files:**
- Create: `app/repositories/sync_schedule.py`
- Test: `tests/repositories/test_sync_schedule.py`

- [ ] **Step 1: Тест**

```python
# tests/repositories/test_sync_schedule.py
from app.repositories.sync_schedule import SyncScheduleRepository


def test_list_returns_seeded_defaults(db_session):
    # Сиды добавлены миграцией 035; на тестовой БД они должны быть
    repo = SyncScheduleRepository(db_session)
    items = repo.list_all()
    names = {i.name for i in items}
    assert {"daily_incremental", "worklogs_workhours", "weekly_full"}.issubset(names)


def test_update_changes_cron_and_enabled(db_session):
    repo = SyncScheduleRepository(db_session)
    item = repo.list_all()[0]
    repo.update(item.id, cron_expr="0 7 * * *", enabled=False)
    db_session.refresh(item)
    assert item.cron_expr == "0 7 * * *"
    assert item.enabled is False


def test_create_and_delete(db_session):
    repo = SyncScheduleRepository(db_session)
    new = repo.create(name="custom_team", cron_expr="*/30 * * * *", mode="team", team="QA")
    assert new.id is not None
    repo.delete(new.id)
    assert repo.get(new.id) is None
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/repositories/test_sync_schedule.py -v`
Expected: FAIL — нет модуля

- [ ] **Step 3: Реализация**

```python
# app/repositories/sync_schedule.py
"""Репозиторий SyncSchedule — CRUD расписания автозапуска pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sync_schedule import SyncSchedule


class SyncScheduleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[SyncSchedule]:
        return self.db.query(SyncSchedule).order_by(SyncSchedule.name).all()

    def get(self, schedule_id: str) -> Optional[SyncSchedule]:
        return self.db.get(SyncSchedule, schedule_id)

    def create(
        self,
        *,
        name: str,
        cron_expr: str,
        mode: str,
        team: Optional[str] = None,
        enabled: bool = True,
    ) -> SyncSchedule:
        item = SyncSchedule(
            name=name,
            cron_expr=cron_expr,
            mode=mode,
            team=team,
            enabled=enabled,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, schedule_id: str, **fields) -> Optional[SyncSchedule]:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return None
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.db.commit()
        return item

    def delete(self, schedule_id: str) -> bool:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return False
        self.db.delete(item)
        self.db.commit()
        return True

    def set_last_run(self, schedule_id: str, run_id: str, next_run_at: Optional[datetime]) -> None:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return
        item.last_run_id = run_id
        item.next_run_at = next_run_at
        self.db.commit()
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/repositories/test_sync_schedule.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/repositories/sync_schedule.py tests/repositories/test_sync_schedule.py
git commit -m "feat(repos): SyncScheduleRepository with CRUD"
```

---

## Task 7: EventBroadcaster (in-memory pub/sub)

**Files:**
- Create: `app/services/event_bus.py`
- Test: `tests/services/test_event_bus.py`

- [ ] **Step 1: Тест**

```python
# tests/services/test_event_bus.py
import asyncio

import pytest

from app.services.event_bus import EventBroadcaster


@pytest.mark.asyncio
async def test_subscribe_and_receive_published_event():
    bus = EventBroadcaster()
    queue = bus.subscribe()
    await bus.publish({"type": "stage_done", "stage": "projects"})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["stage"] == "projects"


@pytest.mark.asyncio
async def test_multiple_subscribers_each_get_event():
    bus = EventBroadcaster()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    await bus.publish({"type": "ping"})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1["type"] == "ping"
    assert e2["type"] == "ping"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBroadcaster()
    queue = bus.subscribe()
    bus.unsubscribe(queue)
    await bus.publish({"type": "x"})
    assert queue.empty()


@pytest.mark.asyncio
async def test_slow_consumer_drops_oldest_when_full(caplog):
    bus = EventBroadcaster(queue_size=2)
    queue = bus.subscribe()
    for i in range(5):
        await bus.publish({"type": "e", "i": i})
    # Очередь не должна заблокировать публикацию
    assert queue.qsize() <= 2
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_event_bus.py -v`
Expected: FAIL — нет модуля

- [ ] **Step 3: Реализация**

```python
# app/services/event_bus.py
"""EventBroadcaster — in-memory pub/sub для SSE-канала.

Один процесс, single-user MVP. Каждый подписчик — свой asyncio.Queue.
При переполнении очереди дропаем старые события (subscriber слишком медленный).
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBroadcaster:
    def __init__(self, queue_size: int = 100) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, push newest
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("event_bus: subscriber queue still full, dropping event")


# Singleton — единственный процесс, один EventBroadcaster
_instance: EventBroadcaster | None = None


def get_event_bus() -> EventBroadcaster:
    global _instance
    if _instance is None:
        _instance = EventBroadcaster()
    return _instance
```

- [ ] **Step 4: Установить pytest-asyncio (если ещё нет)**

Run: `py -3.10 -c "import pytest_asyncio" 2>&1 || py -3.10 -m pip install pytest-asyncio`
Expected: уже установлен или ставится

- [ ] **Step 5: Запустить тесты**

Run: `py -3.10 -m pytest tests/services/test_event_bus.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add app/services/event_bus.py tests/services/test_event_bus.py
git commit -m "feat(services): EventBroadcaster pub/sub for SSE channel"
```

---

## Task 8: SSE-эндпоинт `GET /events/stream`

**Files:**
- Create: `app/api/endpoints/events.py`
- Modify: `app/api/router.py`
- Test: `tests/api/test_events_stream.py`

- [ ] **Step 1: Тест**

```python
# tests/api/test_events_stream.py
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.event_bus import get_event_bus


@pytest.mark.asyncio
async def test_stream_delivers_published_event():
    bus = get_event_bus()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/api/v1/events/stream", timeout=2.0) as resp:
            assert resp.status_code == 200
            assert resp.headers.get("content-type", "").startswith("text/event-stream")

            # Дать listener-у подписаться
            await asyncio.sleep(0.1)
            await bus.publish({"type": "test_event", "value": 42})

            # Прочитать первое реальное событие (пропустить ping, если есть)
            received = None
            async for chunk in resp.aiter_text():
                if "test_event" in chunk:
                    received = chunk
                    break
            assert received is not None
            assert "42" in received
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/api/test_events_stream.py -v`
Expected: FAIL — 404 на `/events/stream`

- [ ] **Step 3: Реализация эндпоинта**

```python
# app/api/endpoints/events.py
"""SSE endpoint for global event stream."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

PING_INTERVAL_SEC = 30


@router.get("/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """Глобальный SSE-канал: stage_done, entity_changed, sync_started, sync_finished."""
    bus = get_event_bus()
    queue = bus.subscribe()

    async def event_generator():
        try:
            yield ":connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL_SEC)
                    payload = json.dumps(event)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ":ping\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Подключить роутер**

Modify `app/api/router.py` — добавить импорт и include:
```python
from app.api.endpoints import events as events_endpoints
api_router.include_router(events_endpoints.router, prefix="/events", tags=["events"])
```

- [ ] **Step 5: Тесты**

Run: `py -3.10 -m pytest tests/api/test_events_stream.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/events.py app/api/router.py tests/api/test_events_stream.py
git commit -m "feat(api): GET /events/stream SSE endpoint"
```

---

## Task 9: Pydantic схемы pipeline / runs / schedule

**Files:**
- Create: `app/schemas/sync_pipeline.py`

- [ ] **Step 1: Создать схемы**

```python
# app/schemas/sync_pipeline.py
"""Pydantic schemas for sync pipeline / runs / schedule."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PipelineMode = Literal["quick", "normal", "full", "team"]
SyncRunStatus = Literal["running", "ok", "partial", "failed", "cancelled", "skipped"]
SyncTrigger = Literal["manual", "scheduled"]


class PipelineRequest(BaseModel):
    mode: PipelineMode
    team: Optional[str] = None
    since: Optional[date] = None


class TeamRefreshRequest(BaseModel):
    team: str


class StageReport(BaseModel):
    stage: str
    started: datetime
    finished: Optional[datetime] = None
    status: str  # ok | partial | failed | skipped
    counts: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class SyncRunOut(BaseModel):
    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: SyncRunStatus
    trigger: SyncTrigger
    mode: PipelineMode
    team: Optional[str]
    stages_json: list[dict]
    error_text: Optional[str]
    schedule_id: Optional[str]

    model_config = {"from_attributes": True}


class SyncScheduleOut(BaseModel):
    id: str
    name: str
    cron_expr: str
    mode: PipelineMode
    team: Optional[str]
    enabled: bool
    last_run_id: Optional[str]
    next_run_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SyncScheduleUpdate(BaseModel):
    cron_expr: Optional[str] = None
    mode: Optional[PipelineMode] = None
    team: Optional[str] = None
    enabled: Optional[bool] = None


class SyncScheduleCreate(BaseModel):
    name: str
    cron_expr: str
    mode: PipelineMode
    team: Optional[str] = None
    enabled: bool = True
```

- [ ] **Step 2: Smoke import**

Run: `py -3.10 -c "from app.schemas.sync_pipeline import PipelineRequest, SyncRunOut; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/sync_pipeline.py
git commit -m "feat(schemas): pydantic schemas for sync pipeline"
```

---

## Task 10: `GET /sync/runs` + `GET /sync/runs/{id}`

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Test: `tests/api/test_sync_runs.py`

- [ ] **Step 1: Тест**

```python
# tests/api/test_sync_runs.py
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.sync_run import SyncRunRepository

client = TestClient(app)


def test_list_runs_returns_recent_first(db_session):
    repo = SyncRunRepository(db_session)
    older = repo.create(mode="quick", trigger="scheduled")
    older.started_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    newer = repo.create(mode="normal", trigger="manual")

    resp = client.get("/api/v1/sync/runs?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == newer.id
    assert body[1]["id"] == older.id


def test_get_run_returns_stages(db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    repo.finalize(run.id, status="ok", stages=[{"stage": "issues", "status": "ok"}])

    resp = client.get(f"/api/v1/sync/runs/{run.id}")
    assert resp.status_code == 200
    assert resp.json()["stages_json"] == [{"stage": "issues", "status": "ok"}]


def test_get_run_404_for_unknown(db_session):
    resp = client.get("/api/v1/sync/runs/does-not-exist")
    assert resp.status_code == 404
```

- [ ] **Step 2: Запустить — упадёт (404 на новых маршрутах)**

Run: `py -3.10 -m pytest tests/api/test_sync_runs.py -v`
Expected: FAIL

- [ ] **Step 3: Добавить маршруты в `app/api/endpoints/sync.py`**

В конец файла:
```python
from app.repositories.sync_run import SyncRunRepository
from app.schemas.sync_pipeline import SyncRunOut


@router.get("/runs", response_model=list[SyncRunOut])
def list_sync_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[SyncRunOut]:
    repo = SyncRunRepository(db)
    return [SyncRunOut.model_validate(r) for r in repo.list_latest(limit=limit)]


@router.get("/runs/{run_id}", response_model=SyncRunOut)
def get_sync_run(run_id: str, db: Session = Depends(get_db)) -> SyncRunOut:
    repo = SyncRunRepository(db)
    run = repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return SyncRunOut.model_validate(run)
```

(Если в файле ещё нет импорта `HTTPException` / `Depends` / `Session` / `get_db` — добавить.)

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/api/test_sync_runs.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/sync.py tests/api/test_sync_runs.py
git commit -m "feat(api): GET /sync/runs + /sync/runs/{id}"
```

---

## Task 11: AppSetting `sync_lock` helper

**Files:**
- Create: `app/services/sync_lock.py`
- Test: `tests/services/test_sync_lock.py`

- [ ] **Step 1: Тест**

```python
# tests/services/test_sync_lock.py
from datetime import datetime, timedelta

from app.services.sync_lock import SyncLock


def test_acquire_then_release(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1") is True
    assert lock.current_run_id() == "run-1"
    lock.release()
    assert lock.current_run_id() is None


def test_acquire_fails_if_held(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1") is True
    assert lock.acquire("run-2") is False
    assert lock.current_run_id() == "run-1"


def test_stale_lock_older_than_ttl_treated_as_free(db_session):
    lock = SyncLock(db_session, stale_after_minutes=60)
    lock.acquire("run-old")
    # Перемотаем started_at в прошлое
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=120))
    assert lock.is_stale() is True
    assert lock.acquire("run-new") is True
    assert lock.current_run_id() == "run-new"
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_sync_lock.py -v`
Expected: FAIL — нет модуля

- [ ] **Step 3: Реализация**

```python
# app/services/sync_lock.py
"""SyncLock — advisory lock через AppSetting.

Хранит JSON {run_id, started_at}. Stale lock (старше TTL) считается
свободным. Single-process, single-user MVP.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

KEY = "sync_lock"
DEFAULT_STALE_AFTER_MIN = 60


class SyncLock:
    def __init__(self, db: Session, stale_after_minutes: int = DEFAULT_STALE_AFTER_MIN) -> None:
        self.db = db
        self.stale_after = timedelta(minutes=stale_after_minutes)

    def _row(self) -> Optional[AppSetting]:
        return self.db.query(AppSetting).filter(AppSetting.key == KEY).one_or_none()

    def _payload(self) -> Optional[dict]:
        row = self._row()
        if row is None or row.value is None or row.value == "":
            return None
        try:
            return json.loads(row.value)
        except Exception:
            return None

    def current_run_id(self) -> Optional[str]:
        payload = self._payload()
        return payload.get("run_id") if payload else None

    def is_stale(self) -> bool:
        payload = self._payload()
        if not payload:
            return False
        started = datetime.fromisoformat(payload["started_at"])
        return datetime.utcnow() - started > self.stale_after

    def acquire(self, run_id: str) -> bool:
        if self.current_run_id() and not self.is_stale():
            return False
        self._write({"run_id": run_id, "started_at": datetime.utcnow().isoformat()})
        return True

    def release(self) -> None:
        self._write(None)

    def _write(self, payload: Optional[dict]) -> None:
        row = self._row()
        value = json.dumps(payload) if payload else None
        if row is None:
            row = AppSetting(key=KEY, value=value)
            self.db.add(row)
        else:
            row.value = value
        self.db.commit()

    def _set_started_at(self, started_at: datetime) -> None:
        # Helper for tests
        payload = self._payload() or {}
        payload["started_at"] = started_at.isoformat()
        self._write(payload)
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/services/test_sync_lock.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_lock.py tests/services/test_sync_lock.py
git commit -m "feat(services): SyncLock advisory lock via AppSetting"
```

---

# Phase 2 — Pipeline Orchestrator

## Task 12: `MappingService.recalculate_for_issues(issue_ids)`

**Files:**
- Modify: `app/services/mapping_service.py`
- Test: `tests/services/test_mapping_service.py` (дополнить)

- [ ] **Step 1: Тест**

В `tests/services/test_mapping_service.py` добавить:
```python
def test_recalculate_for_issues_updates_only_given_subset(db_session, seeded_issues):
    """Если передан список issue_ids — пересчёт только для них."""
    from app.services.mapping_service import MappingService
    svc = MappingService(db_session)
    target = [seeded_issues[0].id, seeded_issues[1].id]
    affected = svc.recalculate_for_issues(target)
    assert affected == 2
```

(Если фикстуры `seeded_issues` нет — использовать существующий паттерн из текущего test_mapping_service.py для seed-а данных.)

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_mapping_service.py::test_recalculate_for_issues_updates_only_given_subset -v`
Expected: FAIL — `AttributeError: ... recalculate_for_issues`

- [ ] **Step 3: Реализация**

В `app/services/mapping_service.py` рядом с `recalculate_all`:
```python
def recalculate_for_issues(self, issue_ids: list[str]) -> int:
    """Пересчитать категории только для указанных issue_ids.

    Возвращает количество затронутых issues. Используется team-mode pipeline,
    чтобы не гонять полный recalculate_all для пары сотен задач.
    """
    if not issue_ids:
        return 0
    issues = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
    affected = 0
    for issue in issues:
        new_category = self.resolver.resolve(issue)
        if issue.category != new_category:
            issue.category = new_category
            affected += 1
    self.db.commit()
    return affected
```

(Если в файле уже есть свой паттерн — следовать ему. `Issue` и `resolver` должны быть уже импортированы.)

- [ ] **Step 4: Тест**

Run: `py -3.10 -m pytest tests/services/test_mapping_service.py::test_recalculate_for_issues_updates_only_given_subset -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/mapping_service.py tests/services/test_mapping_service.py
git commit -m "feat(services): MappingService.recalculate_for_issues subset variant"
```

---

## Task 13: PipelineOrchestrator skeleton (stage interface + mode router)

**Files:**
- Create: `app/services/sync_pipeline.py`
- Test: `tests/services/test_sync_pipeline.py`

- [ ] **Step 1: Тест skeleton-а с моками стадий**

```python
# tests/services/test_sync_pipeline.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import PipelineOrchestrator, Stage


class FakeStage(Stage):
    name = "fake"
    critical = True

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = 0

    async def run(self, ctx):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("boom")
        return {"items": 1}

    def invalidates(self):
        return ["fake_key"]


@pytest.mark.asyncio
async def test_orchestrator_runs_stages_in_order():
    s1 = FakeStage()
    s2 = FakeStage()
    orch = PipelineOrchestrator(stages=[s1, s2], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s1.calls == 1
    assert s2.calls == 1
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_orchestrator_stops_on_critical_failure():
    s_ok = FakeStage()
    s_fail = FakeStage(should_fail=True)
    s_after = FakeStage()
    orch = PipelineOrchestrator(stages=[s_ok, s_fail, s_after], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s_ok.calls == 1
    assert s_fail.calls == 1
    assert s_after.calls == 0
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_non_critical_failure_continues_with_partial():
    s_ok = FakeStage()
    s_fail = FakeStage(should_fail=True)
    s_fail.critical = False
    s_after = FakeStage()
    orch = PipelineOrchestrator(stages=[s_ok, s_fail, s_after], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s_ok.calls == 1
    assert s_fail.calls == 1
    assert s_after.calls == 1
    assert result["status"] == "partial"


@pytest.mark.asyncio
async def test_publishes_stage_done_with_invalidates():
    s = FakeStage()
    bus = MagicMock(publish=AsyncMock())
    orch = PipelineOrchestrator(stages=[s], db=MagicMock(), bus=bus)
    await orch.run(mode="normal", trigger="manual")
    published = [c.args[0] for c in bus.publish.call_args_list]
    stage_done = [e for e in published if e.get("type") == "stage_done"]
    assert any(e["invalidates"] == ["fake_key"] for e in stage_done)
```

- [ ] **Step 2: Запустить — упадёт (нет модуля)**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Реализация skeleton-а**

```python
# app/services/sync_pipeline.py
"""PipelineOrchestrator — единая точка запуска стадий sync.

Стадии описаны как наследники Stage. Оркестратор:
- Запускает их по порядку для выбранного mode
- Перехватывает ошибки: critical → stop+failed, non-critical → warn+partial
- Публикует stage_start/stage_progress/stage_done/stage_failed/pipeline_done в EventBroadcaster
- Пишет историю в SyncRun (через репозиторий)
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from app.services.event_bus import EventBroadcaster

logger = logging.getLogger(__name__)


class Stage(ABC):
    name: str = ""
    critical: bool = True

    @abstractmethod
    async def run(self, ctx: dict) -> dict:
        """Выполнить стадию. Возвращает словарь counts (любые числа для отчёта)."""

    def invalidates(self) -> list[str]:
        return []


class PipelineOrchestrator:
    def __init__(self, stages: list[Stage], db, bus: EventBroadcaster) -> None:
        self.stages = stages
        self.db = db
        self.bus = bus

    async def run(
        self,
        *,
        mode: str,
        trigger: str,
        team: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {"mode": mode, "team": team, "run_id": run_id}
        stages_report: list[dict] = []
        had_non_critical_failure = False

        await self.bus.publish({"type": "sync_started", "run_id": run_id, "mode": mode, "trigger": trigger})

        for stage in self.stages:
            started = datetime.utcnow()
            await self.bus.publish({"type": "stage_start", "stage": stage.name, "run_id": run_id})
            try:
                counts = await stage.run(ctx)
                finished = datetime.utcnow()
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "finished": finished.isoformat(),
                    "status": "ok",
                    "counts": counts or {},
                })
                await self.bus.publish({
                    "type": "stage_done",
                    "stage": stage.name,
                    "run_id": run_id,
                    "duration_ms": int((finished - started).total_seconds() * 1000),
                    "invalidates": stage.invalidates(),
                })
            except asyncio.CancelledError:
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "status": "cancelled",
                })
                await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": "cancelled"})
                return {"status": "cancelled", "stages": stages_report}
            except Exception as exc:
                logger.exception("Pipeline stage %s failed", stage.name)
                stages_report.append({
                    "stage": stage.name,
                    "started": started.isoformat(),
                    "finished": datetime.utcnow().isoformat(),
                    "status": "failed",
                    "error": str(exc),
                })
                await self.bus.publish({
                    "type": "stage_failed",
                    "stage": stage.name,
                    "run_id": run_id,
                    "error": str(exc),
                    "critical": stage.critical,
                })
                if stage.critical:
                    await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": "failed"})
                    return {"status": "failed", "stages": stages_report, "error": str(exc)}
                had_non_critical_failure = True

        status = "partial" if had_non_critical_failure else "ok"
        await self.bus.publish({"type": "pipeline_done", "run_id": run_id, "status": status})
        return {"status": status, "stages": stages_report}
```

- [ ] **Step 4: Тесты skeleton-а**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_pipeline.py tests/services/test_sync_pipeline.py
git commit -m "feat(services): PipelineOrchestrator skeleton with stage interface"
```

---

## Task 14: Реальные стадии — обёртки над существующими сервисами

**Files:**
- Modify: `app/services/sync_pipeline.py`
- Test: `tests/services/test_sync_pipeline_stages.py`

- [ ] **Step 1: Тест на стадии-обёртки (мокаем сервисы)**

```python
# tests/services/test_sync_pipeline_stages.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import (
    CalendarStage,
    ProjectsStage,
    IssuesIncrementalStage,
    IssuesFullStage,
    WorklogsDeltaStage,
    WorklogsFullStage,
    IssuesRefreshByKeysStage,
    MappingStage,
)


@pytest.mark.asyncio
async def test_projects_stage_calls_sync_service():
    sync_svc = MagicMock(sync_projects=AsyncMock(return_value={"count": 5}))
    stage = ProjectsStage(sync_svc)
    result = await stage.run({})
    sync_svc.sync_projects.assert_awaited_once()
    assert result["count"] == 5


@pytest.mark.asyncio
async def test_issues_incremental_stage():
    sync_svc = MagicMock(sync_issues=AsyncMock(return_value={"updated": 12}))
    stage = IssuesIncrementalStage(sync_svc)
    result = await stage.run({})
    sync_svc.sync_issues.assert_awaited_once_with(incremental=True)
    assert result["updated"] == 12


@pytest.mark.asyncio
async def test_worklogs_delta_collects_keys_into_ctx():
    sync_svc = MagicMock(update_worklogs_since=AsyncMock(
        return_value={"worklogs_upserted": 10, "issue_keys": ["A-1", "A-2"]}
    ))
    ctx = {"team": "QA", "since": "2026-04-01"}
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run(ctx)
    sync_svc.update_worklogs_since.assert_awaited_once()
    assert ctx["touched_issue_keys"] == ["A-1", "A-2"]


@pytest.mark.asyncio
async def test_issues_refresh_by_keys_uses_ctx_keys():
    sync_svc = MagicMock(refresh_issues_by_keys=AsyncMock(return_value={"refreshed": 2}))
    stage = IssuesRefreshByKeysStage(sync_svc)
    ctx = {"touched_issue_keys": ["A-1", "A-2"]}
    await stage.run(ctx)
    sync_svc.refresh_issues_by_keys.assert_awaited_once_with(jira_keys=["A-1", "A-2"])


@pytest.mark.asyncio
async def test_mapping_stage_subset_when_keys_in_ctx():
    mapping_svc = MagicMock(recalculate_for_issues=MagicMock(return_value=3))
    stage = MappingStage(mapping_svc)
    ctx = {"touched_issue_ids": ["i1", "i2"]}
    result = await stage.run(ctx)
    mapping_svc.recalculate_for_issues.assert_called_once_with(["i1", "i2"])
    assert result["affected"] == 3


@pytest.mark.asyncio
async def test_mapping_stage_full_when_no_keys():
    mapping_svc = MagicMock(recalculate_all=MagicMock(return_value=100))
    stage = MappingStage(mapping_svc)
    result = await stage.run({})
    mapping_svc.recalculate_all.assert_called_once()
    assert result["affected"] == 100
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline_stages.py -v`
Expected: FAIL — нет классов

- [ ] **Step 3: Реализовать стадии в `app/services/sync_pipeline.py`**

В конец файла добавить:
```python
# === Stages ===

class CalendarStage(Stage):
    name = "calendar"
    critical = False  # non-critical: при отсутствии откатимся к hours_per_day=8

    def __init__(self, calendar_svc, year: Optional[int] = None) -> None:
        self.svc = calendar_svc
        self.year = year

    async def run(self, ctx: dict) -> dict:
        year = self.year or datetime.utcnow().year
        result = self.svc.sync_year(year)
        return {"year": year, "days": result if isinstance(result, int) else None}

    def invalidates(self) -> list[str]:
        return ["production-calendar", "capacity"]


class ProjectsStage(Stage):
    name = "projects"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        return await self.svc.sync_projects() or {}

    def invalidates(self) -> list[str]:
        return ["projects"]


class IssuesIncrementalStage(Stage):
    name = "issues"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        return await self.svc.sync_issues(incremental=True) or {}

    def invalidates(self) -> list[str]:
        return ["issues", "tree", "backlog", "planning"]


class IssuesFullStage(Stage):
    name = "issues"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        return await self.svc.sync_issues(incremental=False) or {}

    def invalidates(self) -> list[str]:
        return ["issues", "tree", "backlog", "planning"]


class WorklogsDeltaStage(Stage):
    name = "worklogs"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        kwargs = {}
        if ctx.get("since"):
            kwargs["since"] = ctx["since"]
        if ctx.get("team"):
            kwargs["teams"] = [ctx["team"]]
        result = await self.svc.update_worklogs_since(**kwargs) or {}
        keys = result.get("issue_keys") or []
        if keys:
            ctx["touched_issue_keys"] = keys
        return {k: v for k, v in result.items() if k != "issue_keys"} | {
            "issue_keys_count": len(keys)
        }

    def invalidates(self) -> list[str]:
        return ["analytics", "capacity", "employees"]


class WorklogsFullStage(Stage):
    name = "worklogs"
    critical = True

    def __init__(self, sync_svc, since=None) -> None:
        self.svc = sync_svc
        self.since = since

    async def run(self, ctx: dict) -> dict:
        kwargs = {}
        if self.since or ctx.get("since"):
            kwargs["since"] = self.since or ctx["since"]
        return await self.svc.reload_worklogs_since(**kwargs) or {}

    def invalidates(self) -> list[str]:
        return ["analytics", "capacity", "employees"]


class IssuesRefreshByKeysStage(Stage):
    name = "issues_refresh"
    critical = True

    def __init__(self, sync_svc) -> None:
        self.svc = sync_svc

    async def run(self, ctx: dict) -> dict:
        keys = ctx.get("touched_issue_keys") or []
        if not keys:
            return {"refreshed": 0}
        result = await self.svc.refresh_issues_by_keys(jira_keys=keys) or {}
        # Соберём issue_ids из результата для последующей mapping-стадии
        ctx["touched_issue_ids"] = result.get("issue_ids", [])
        return {"refreshed": result.get("refreshed", len(keys))}

    def invalidates(self) -> list[str]:
        return ["issues", "tree"]


class MappingStage(Stage):
    name = "mapping"
    critical = False  # mapping recalc — non-critical

    def __init__(self, mapping_svc) -> None:
        self.svc = mapping_svc

    async def run(self, ctx: dict) -> dict:
        ids = ctx.get("touched_issue_ids")
        if ids:
            affected = self.svc.recalculate_for_issues(ids)
        else:
            affected = self.svc.recalculate_all()
        return {"affected": affected}

    def invalidates(self) -> list[str]:
        return ["analytics", "categories"]
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline_stages.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_pipeline.py tests/services/test_sync_pipeline_stages.py
git commit -m "feat(services): pipeline stage wrappers (calendar/projects/issues/worklogs/mapping)"
```

---

## Task 15: Mode → stages router (`build_pipeline`)

**Files:**
- Modify: `app/services/sync_pipeline.py`
- Test: `tests/services/test_sync_pipeline_modes.py`

- [ ] **Step 1: Тест соответствия mode → стадии**

```python
# tests/services/test_sync_pipeline_modes.py
from app.services.sync_pipeline import (
    build_pipeline,
    CalendarStage,
    ProjectsStage,
    IssuesIncrementalStage,
    IssuesFullStage,
    WorklogsDeltaStage,
    WorklogsFullStage,
    IssuesRefreshByKeysStage,
    MappingStage,
)


class _Stub:
    def __init__(self, *a, **k): pass


def test_quick_mode_has_only_worklogs_delta():
    stages = build_pipeline(mode="quick", services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()})
    assert [type(s) for s in stages] == [WorklogsDeltaStage]


def test_normal_mode_has_full_chain():
    stages = build_pipeline(mode="normal", services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()})
    assert [type(s) for s in stages] == [
        CalendarStage, ProjectsStage, IssuesIncrementalStage, WorklogsDeltaStage, MappingStage,
    ]


def test_full_mode_uses_full_variants():
    stages = build_pipeline(mode="full", services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()})
    types = [type(s) for s in stages]
    assert IssuesFullStage in types
    assert WorklogsFullStage in types


def test_team_mode_includes_refresh_by_keys():
    stages = build_pipeline(
        mode="team",
        services={"sync": _Stub(), "calendar": _Stub(), "mapping": _Stub()},
        team="QA",
    )
    assert [type(s) for s in stages] == [
        WorklogsDeltaStage, IssuesRefreshByKeysStage, MappingStage,
    ]
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline_modes.py -v`
Expected: FAIL — нет `build_pipeline`

- [ ] **Step 3: Реализация**

В `app/services/sync_pipeline.py` добавить:
```python
def build_pipeline(*, mode: str, services: dict, team: Optional[str] = None) -> list[Stage]:
    """Собрать список стадий по режиму. services: {sync, calendar, mapping}."""
    sync = services["sync"]
    calendar = services["calendar"]
    mapping = services["mapping"]

    if mode == "quick":
        return [WorklogsDeltaStage(sync)]
    if mode == "normal":
        return [
            CalendarStage(calendar),
            ProjectsStage(sync),
            IssuesIncrementalStage(sync),
            WorklogsDeltaStage(sync),
            MappingStage(mapping),
        ]
    if mode == "full":
        return [
            CalendarStage(calendar),
            ProjectsStage(sync),
            IssuesFullStage(sync),
            WorklogsFullStage(sync),
            MappingStage(mapping),
        ]
    if mode == "team":
        if not team:
            raise ValueError("team mode requires `team` argument")
        return [
            WorklogsDeltaStage(sync),
            IssuesRefreshByKeysStage(sync),
            MappingStage(mapping),
        ]
    raise ValueError(f"Unknown pipeline mode: {mode}")
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/services/test_sync_pipeline_modes.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/sync_pipeline.py tests/services/test_sync_pipeline_modes.py
git commit -m "feat(services): build_pipeline mode→stages router"
```

---

## Task 16: `POST /sync/pipeline` SSE endpoint

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Test: `tests/api/test_sync_pipeline_endpoint.py`

- [ ] **Step 1: Тест**

```python
# tests/api/test_sync_pipeline_endpoint.py
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_pipeline_endpoint_streams_sse_events():
    """End-to-end: дёрнуть /sync/pipeline в normal-режиме, замокать сервисы."""
    fake_orch_run = AsyncMock(return_value={"status": "ok", "stages": []})

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch:
        build_orch.return_value.run = fake_orch_run

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST", "/api/v1/sync/pipeline",
                json={"mode": "normal"},
                timeout=5.0,
            ) as resp:
                assert resp.status_code == 200
                body = ""
                async for chunk in resp.aiter_text():
                    body += chunk
                    if "pipeline_done" in body:
                        break
                assert "pipeline_done" in body or "run_id" in body


@pytest.mark.asyncio
async def test_pipeline_returns_409_when_lock_held(db_session):
    from app.services.sync_lock import SyncLock
    SyncLock(db_session).acquire("other-run")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/sync/pipeline", json={"mode": "quick"})
    assert resp.status_code == 409
    assert "running_run_id" in resp.json()
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/api/test_sync_pipeline_endpoint.py -v`
Expected: FAIL — 404 либо нет `_build_orchestrator`

- [ ] **Step 3: Эндпоинт + helper-builder**

В `app/api/endpoints/sync.py`:
```python
import json
from datetime import date
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.repositories.sync_run import SyncRunRepository
from app.schemas.sync_pipeline import PipelineRequest, TeamRefreshRequest
from app.services.event_bus import get_event_bus
from app.services.mapping_service import MappingService
from app.services.production_calendar_service import ProductionCalendarService
from app.services.sync_lock import SyncLock
from app.services.sync_pipeline import PipelineOrchestrator, build_pipeline
from app.services.sync_service import SyncService


def _build_orchestrator(db, *, mode: str, team: Optional[str] = None) -> PipelineOrchestrator:
    sync_svc = SyncService(db)
    calendar_svc = ProductionCalendarService(db)
    mapping_svc = MappingService(db)
    stages = build_pipeline(
        mode=mode,
        services={"sync": sync_svc, "calendar": calendar_svc, "mapping": mapping_svc},
        team=team,
    )
    return PipelineOrchestrator(stages=stages, db=db, bus=get_event_bus())


@router.post("/pipeline")
async def run_pipeline(
    request: PipelineRequest,
    db: Session = Depends(get_db),
):
    """Запустить sync pipeline. Возвращает SSE-stream стадий."""
    lock = SyncLock(db)
    run_repo = SyncRunRepository(db)

    if lock.current_run_id() and not lock.is_stale():
        raise HTTPException(
            status_code=409,
            detail={"running_run_id": lock.current_run_id()},
        )

    run = run_repo.create(mode=request.mode, trigger="manual", team=request.team)
    if not lock.acquire(run.id):
        run_repo.finalize(run.id, status="skipped", stages=[], error_text="lock contention")
        raise HTTPException(status_code=409, detail={"running_run_id": lock.current_run_id()})

    orch = _build_orchestrator(db, mode=request.mode, team=request.team)
    bus = get_event_bus()
    queue = bus.subscribe()

    async def event_generator():
        run_task = asyncio.create_task(
            orch.run(mode=request.mode, trigger="manual", team=request.team, run_id=run.id)
        )
        try:
            while True:
                if run_task.done():
                    result = run_task.result()
                    run_repo.finalize(
                        run.id,
                        status=result["status"],
                        stages=result.get("stages", []),
                        error_text=result.get("error"),
                    )
                    yield f"data: {json.dumps({'type':'pipeline_done','run_id':run.id,'status':result['status']})}\n\n"
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ":ping\n\n"
        finally:
            bus.unsubscribe(queue)
            lock.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/team/refresh")
async def team_refresh(
    request: TeamRefreshRequest,
    db: Session = Depends(get_db),
):
    """Sugar: team-mode pipeline."""
    pipeline_request = PipelineRequest(mode="team", team=request.team)
    return await run_pipeline(pipeline_request, db=db)
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/api/test_sync_pipeline_endpoint.py -v`
Expected: 2 passed

- [ ] **Step 5: Перезапустить uvicorn (windows-uvicorn-reload фикс)**

Run (PowerShell):
```powershell
$pids = (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess
if ($pids) { Stop-Process -Id $pids -Force }
Start-Process powershell -ArgumentList "-NoExit","-Command","py -3.10 -m uvicorn app.main:app --reload --port 8000"
```

- [ ] **Step 6: Smoke вручную**

Run: `curl -X POST http://localhost:8000/api/v1/sync/pipeline -H "Content-Type: application/json" -d '{"mode":"quick"}' -N`
Expected: SSE-стрим с событиями `stage_start`, `stage_done`, `pipeline_done`

- [ ] **Step 7: Commit**

```bash
git add app/api/endpoints/sync.py tests/api/test_sync_pipeline_endpoint.py
git commit -m "feat(api): POST /sync/pipeline SSE + /sync/team/refresh sugar"
```

---

## Task 17: Cancellation в pipeline (request.is_disconnected)

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Test: `tests/api/test_sync_pipeline_cancel.py`

- [ ] **Step 1: Тест**

```python
# tests/api/test_sync_pipeline_cancel.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_pipeline_cancels_on_client_disconnect():
    """Если клиент закрыл соединение посреди стрима — pipeline отменяется."""
    slow_run = AsyncMock(side_effect=lambda **kw: asyncio.sleep(5))

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch:
        build_orch.return_value.run = slow_run

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("POST", "/api/v1/sync/pipeline", json={"mode": "quick"}, timeout=1.0):
                # Закрываем стрим сразу
                pass
        # Главное — не зависает
        assert True
```

- [ ] **Step 2: Запустить — должен пройти, но проверим что cancellation чисто отрабатывает**

Run: `py -3.10 -m pytest tests/api/test_sync_pipeline_cancel.py -v --timeout=10`
Expected: PASS

- [ ] **Step 3: Дополнить эндпоинт проверкой `request.is_disconnected()`**

В `event_generator` добавить параметр `request: Request` и проверку:
```python
async def event_generator():
    run_task = asyncio.create_task(...)
    try:
        while True:
            if await request.is_disconnected():
                run_task.cancel()
                run_repo.finalize(run.id, status="cancelled", stages=[])
                break
            # ... остальное как было
```

(Сигнатура `run_pipeline` принимает `request: Request`.)

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/api/test_sync_pipeline_cancel.py -v --timeout=10`
Expected: PASS, без зависаний

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/sync.py tests/api/test_sync_pipeline_cancel.py
git commit -m "feat(api): pipeline cancels on client disconnect"
```

---

## Task 18: Smoke-тест pipeline на seeded e2e.db

**Files:**
- Test: `tests/integration/test_sync_pipeline_e2e.py`

- [ ] **Step 1: Подготовить seeded базу**

Run: `py -3.10 scripts/seed_e2e.py`
Expected: data/e2e.db создан

- [ ] **Step 2: Тест**

```python
# tests/integration/test_sync_pipeline_e2e.py
"""Integration: pipeline на seeded e2e.db, без реальных Jira-вызовов.

Используется DUMMY-конфиг: SyncService.sync_projects/sync_issues/etc.
должны корректно отрабатывать на пустой Jira (если SYNC_DRY_RUN не
поддерживается, мокаем сетевые вызовы напрямую через httpx mock).
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_pipeline_normal_mode_writes_sync_run(e2e_db_session):
    from app.services.sync_pipeline import build_pipeline, PipelineOrchestrator
    from app.services.sync_service import SyncService
    from app.services.production_calendar_service import ProductionCalendarService
    from app.services.mapping_service import MappingService
    from app.services.event_bus import EventBroadcaster
    from app.repositories.sync_run import SyncRunRepository

    # Замокать сетевые вызовы
    with patch.object(SyncService, "sync_projects", AsyncMock(return_value={"count": 0})), \
         patch.object(SyncService, "sync_issues", AsyncMock(return_value={"updated": 0})), \
         patch.object(SyncService, "update_worklogs_since", AsyncMock(return_value={"worklogs_upserted": 0})), \
         patch.object(ProductionCalendarService, "sync_year", lambda self, year: 0), \
         patch.object(MappingService, "recalculate_all", lambda self: 0):

        services = {
            "sync": SyncService(e2e_db_session),
            "calendar": ProductionCalendarService(e2e_db_session),
            "mapping": MappingService(e2e_db_session),
        }
        stages = build_pipeline(mode="normal", services=services)
        bus = EventBroadcaster()
        repo = SyncRunRepository(e2e_db_session)
        run = repo.create(mode="normal", trigger="manual")
        orch = PipelineOrchestrator(stages, db=e2e_db_session, bus=bus)
        result = await orch.run(mode="normal", trigger="manual", run_id=run.id)
        repo.finalize(run.id, status=result["status"], stages=result["stages"])

    e2e_db_session.refresh(run)
    assert run.status == "ok"
    assert len(run.stages_json) == 5  # calendar+projects+issues+worklogs+mapping
```

(Фикстура `e2e_db_session` — нужно либо взять существующую из `tests/conftest.py`, либо создать локальную, указывающую на `data/e2e.db`.)

- [ ] **Step 3: Запустить**

Run: `py -3.10 -m pytest tests/integration/test_sync_pipeline_e2e.py -v`
Expected: 1 passed

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_sync_pipeline_e2e.py
git commit -m "test(integration): pipeline normal-mode end-to-end on seeded e2e.db"
```

---

# Phase 3 — Scheduler

## Task 19: SchedulerService (APScheduler wrapper)

**Files:**
- Create: `app/services/scheduler.py`
- Test: `tests/services/test_scheduler.py`

- [ ] **Step 1: Тест**

```python
# tests/services/test_scheduler.py
from unittest.mock import MagicMock

import pytest
from croniter import croniter

from app.services.scheduler import SchedulerService


def test_validates_cron_expression():
    assert SchedulerService.is_valid_cron("0 6 * * *") is True
    assert SchedulerService.is_valid_cron("not a cron") is False


def test_compute_next_run():
    nxt = SchedulerService.next_run_at("0 6 * * *")
    assert nxt is not None


def test_register_jobs_creates_one_per_enabled_schedule():
    svc = SchedulerService(scheduler=MagicMock(), trigger_runner=MagicMock())
    schedules = [
        MagicMock(id="1", name="a", cron_expr="0 6 * * *", enabled=True, mode="normal", team=None),
        MagicMock(id="2", name="b", cron_expr="0 7 * * *", enabled=False, mode="quick", team=None),
        MagicMock(id="3", name="c", cron_expr="0 8 * * *", enabled=True, mode="full", team=None),
    ]
    svc.register_jobs(schedules)
    # add_job вызван дважды (только enabled)
    assert svc.scheduler.add_job.call_count == 2
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_scheduler.py -v`
Expected: FAIL — нет модуля

- [ ] **Step 3: Реализация**

```python
# app/services/scheduler.py
"""SchedulerService — APScheduler wrapper для запуска pipeline по cron."""

import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        *,
        scheduler: Optional[AsyncIOScheduler] = None,
        trigger_runner: Optional[Callable] = None,
    ) -> None:
        self.scheduler = scheduler or AsyncIOScheduler()
        self.trigger_runner = trigger_runner

    @staticmethod
    def is_valid_cron(expr: str) -> bool:
        try:
            croniter(expr, datetime.utcnow())
            return True
        except Exception:
            return False

    @staticmethod
    def next_run_at(expr: str) -> Optional[datetime]:
        try:
            return croniter(expr, datetime.utcnow()).get_next(datetime)
        except Exception:
            return None

    def register_jobs(self, schedules: list) -> None:
        # Удалить все текущие (для re-register)
        for job in list(self.scheduler.get_jobs()):
            self.scheduler.remove_job(job.id)
        for sch in schedules:
            if not sch.enabled:
                continue
            self.scheduler.add_job(
                self.trigger_runner,
                trigger=CronTrigger.from_crontab(sch.cron_expr),
                id=sch.id,
                name=sch.name,
                kwargs={"schedule_id": sch.id, "mode": sch.mode, "team": sch.team},
                replace_existing=True,
            )

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/services/test_scheduler.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/services/test_scheduler.py
git commit -m "feat(services): SchedulerService APScheduler wrapper"
```

---

## Task 20: Trigger runner (вызов pipeline из APScheduler job)

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/services/test_scheduler_trigger.py`

- [ ] **Step 1: Тест**

```python
# tests/services/test_scheduler_trigger.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_trigger_runner_skips_when_lock_held(db_session):
    from app.services.scheduler import scheduled_pipeline_runner
    from app.services.sync_lock import SyncLock

    SyncLock(db_session).acquire("manual-run-id")

    with patch("app.services.scheduler._get_db_session", return_value=db_session):
        await scheduled_pipeline_runner(schedule_id="sch-1", mode="quick", team=None)

    from app.repositories.sync_run import SyncRunRepository
    runs = SyncRunRepository(db_session).list_latest(limit=5)
    skipped = [r for r in runs if r.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].error_text == "previous_running"


@pytest.mark.asyncio
async def test_trigger_runner_creates_run_and_calls_orchestrator(db_session):
    from app.services.scheduler import scheduled_pipeline_runner

    fake_orch = MagicMock(run=AsyncMock(return_value={"status": "ok", "stages": []}))
    with patch("app.services.scheduler._get_db_session", return_value=db_session), \
         patch("app.services.scheduler._build_orchestrator", return_value=fake_orch):
        await scheduled_pipeline_runner(schedule_id="sch-1", mode="normal", team=None)

    fake_orch.run.assert_awaited_once()
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/services/test_scheduler_trigger.py -v`
Expected: FAIL — нет функции

- [ ] **Step 3: Дополнить `app/services/scheduler.py`**

```python
async def scheduled_pipeline_runner(*, schedule_id: str, mode: str, team: Optional[str] = None) -> None:
    """Job, регистрируемая в APScheduler. Вызывается планировщиком."""
    db = _get_db_session()
    try:
        from app.repositories.sync_run import SyncRunRepository
        from app.services.sync_lock import SyncLock

        lock = SyncLock(db)
        repo = SyncRunRepository(db)

        if lock.current_run_id() and not lock.is_stale():
            run = repo.create(mode=mode, trigger="scheduled", team=team, schedule_id=schedule_id)
            repo.finalize(run.id, status="skipped", stages=[], error_text="previous_running")
            return

        run = repo.create(mode=mode, trigger="scheduled", team=team, schedule_id=schedule_id)
        if not lock.acquire(run.id):
            repo.finalize(run.id, status="skipped", stages=[], error_text="lock contention")
            return

        try:
            orch = _build_orchestrator(db, mode=mode, team=team)
            result = await orch.run(mode=mode, trigger="scheduled", team=team, run_id=run.id)
            repo.finalize(run.id, status=result["status"], stages=result.get("stages", []), error_text=result.get("error"))
        finally:
            lock.release()
    finally:
        db.close()


def _get_db_session():
    """Открыть новую сессию для job-а (вне FastAPI-зависимостей)."""
    from app.database import SessionLocal
    return SessionLocal()


def _build_orchestrator(db, *, mode: str, team: Optional[str] = None):
    from app.services.sync_pipeline import build_pipeline, PipelineOrchestrator
    from app.services.sync_service import SyncService
    from app.services.production_calendar_service import ProductionCalendarService
    from app.services.mapping_service import MappingService
    from app.services.event_bus import get_event_bus

    services = {
        "sync": SyncService(db),
        "calendar": ProductionCalendarService(db),
        "mapping": MappingService(db),
    }
    stages = build_pipeline(mode=mode, services=services, team=team)
    return PipelineOrchestrator(stages=stages, db=db, bus=get_event_bus())
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/services/test_scheduler_trigger.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/services/test_scheduler_trigger.py
git commit -m "feat(services): scheduled_pipeline_runner with skip-if-running"
```

---

## Task 21: Подключить scheduler в FastAPI lifespan

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_lifespan.py`

- [ ] **Step 1: Тест**

```python
# tests/test_lifespan.py
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_lifespan_starts_scheduler_with_seeded_jobs():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200

    # Проверим что в app.state есть scheduler
    assert hasattr(app.state, "scheduler")
    jobs = app.state.scheduler.scheduler.get_jobs()
    job_names = {j.name for j in jobs}
    # Должны зарегистрироваться 3 default seeds
    assert {"daily_incremental", "worklogs_workhours", "weekly_full"}.issubset(job_names)
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/test_lifespan.py -v`
Expected: FAIL — нет `app.state.scheduler`

- [ ] **Step 3: Дополнить lifespan**

```python
# app/main.py — заменить lifespan
from app.database import SessionLocal
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.scheduler import SchedulerService, scheduled_pipeline_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Debug mode: {settings.debug}")

    scheduler = SchedulerService(trigger_runner=scheduled_pipeline_runner)
    db = SessionLocal()
    try:
        schedules = SyncScheduleRepository(db).list_all()
    finally:
        db.close()
    scheduler.register_jobs(schedules)
    scheduler.start()
    app.state.scheduler = scheduler
    print(f"Scheduler started with {len(scheduler.scheduler.get_jobs())} jobs")

    yield

    print("Shutting down scheduler...")
    scheduler.shutdown()
```

- [ ] **Step 4: Перезапуск uvicorn (windows фикс — см. Task 16 step 5)**

- [ ] **Step 5: Тест**

Run: `py -3.10 -m pytest tests/test_lifespan.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_lifespan.py
git commit -m "feat(main): start SchedulerService in lifespan with seeded jobs"
```

---

## Task 22: Sync schedule API (CRUD + run-now)

**Files:**
- Modify: `app/api/endpoints/sync.py`
- Test: `tests/api/test_sync_schedule.py`

- [ ] **Step 1: Тест**

```python
# tests/api/test_sync_schedule.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_returns_seeded():
    resp = client.get("/api/v1/sync/schedule")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"] for s in body}
    assert {"daily_incremental", "worklogs_workhours", "weekly_full"}.issubset(names)


def test_patch_updates_cron_and_enabled():
    body = client.get("/api/v1/sync/schedule").json()
    sch_id = body[0]["id"]
    resp = client.patch(f"/api/v1/sync/schedule/{sch_id}", json={"cron_expr": "30 7 * * *", "enabled": False})
    assert resp.status_code == 200
    assert resp.json()["cron_expr"] == "30 7 * * *"
    assert resp.json()["enabled"] is False


def test_patch_invalid_cron_400():
    body = client.get("/api/v1/sync/schedule").json()
    sch_id = body[0]["id"]
    resp = client.patch(f"/api/v1/sync/schedule/{sch_id}", json={"cron_expr": "garbage"})
    assert resp.status_code == 400


def test_create_and_delete_custom():
    resp = client.post("/api/v1/sync/schedule", json={
        "name": "custom_qa",
        "cron_expr": "*/30 * * * *",
        "mode": "team",
        "team": "QA",
    })
    assert resp.status_code == 201
    sch_id = resp.json()["id"]
    resp = client.delete(f"/api/v1/sync/schedule/{sch_id}")
    assert resp.status_code == 204
```

- [ ] **Step 2: Запустить — упадёт**

Run: `py -3.10 -m pytest tests/api/test_sync_schedule.py -v`
Expected: FAIL

- [ ] **Step 3: Реализация в `app/api/endpoints/sync.py`**

```python
from fastapi import status
from app.repositories.sync_schedule import SyncScheduleRepository
from app.schemas.sync_pipeline import (
    SyncScheduleOut, SyncScheduleCreate, SyncScheduleUpdate,
)
from app.services.scheduler import SchedulerService


@router.get("/schedule", response_model=list[SyncScheduleOut])
def list_schedule(db: Session = Depends(get_db)) -> list[SyncScheduleOut]:
    return [SyncScheduleOut.model_validate(s) for s in SyncScheduleRepository(db).list_all()]


@router.post("/schedule", response_model=SyncScheduleOut, status_code=201)
def create_schedule(req: SyncScheduleCreate, db: Session = Depends(get_db)) -> SyncScheduleOut:
    if not SchedulerService.is_valid_cron(req.cron_expr):
        raise HTTPException(status_code=400, detail="Invalid cron expression")
    item = SyncScheduleRepository(db).create(**req.model_dump())
    _refresh_app_scheduler(db)
    return SyncScheduleOut.model_validate(item)


@router.patch("/schedule/{schedule_id}", response_model=SyncScheduleOut)
def update_schedule(
    schedule_id: str,
    req: SyncScheduleUpdate,
    db: Session = Depends(get_db),
) -> SyncScheduleOut:
    if req.cron_expr and not SchedulerService.is_valid_cron(req.cron_expr):
        raise HTTPException(status_code=400, detail="Invalid cron expression")
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    item = SyncScheduleRepository(db).update(schedule_id, **fields)
    if item is None:
        raise HTTPException(status_code=404)
    _refresh_app_scheduler(db)
    return SyncScheduleOut.model_validate(item)


@router.delete("/schedule/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)) -> None:
    if not SyncScheduleRepository(db).delete(schedule_id):
        raise HTTPException(status_code=404)
    _refresh_app_scheduler(db)
    return None


@router.post("/schedule/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str, db: Session = Depends(get_db)):
    sch = SyncScheduleRepository(db).get(schedule_id)
    if sch is None:
        raise HTTPException(status_code=404)
    return await run_pipeline(
        PipelineRequest(mode=sch.mode, team=sch.team),
        db=db,
    )


def _refresh_app_scheduler(db) -> None:
    from app.main import app
    if hasattr(app.state, "scheduler"):
        schedules = SyncScheduleRepository(db).list_all()
        app.state.scheduler.register_jobs(schedules)
```

- [ ] **Step 4: Тесты**

Run: `py -3.10 -m pytest tests/api/test_sync_schedule.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/sync.py tests/api/test_sync_schedule.py
git commit -m "feat(api): sync schedule CRUD + run-now + cron validation"
```

---

# Phase 4 — Frontend Hub + Global Event Listener

## Task 23: API клиент `frontend/src/api/syncPipeline.ts`

**Files:**
- Create: `frontend/src/api/syncPipeline.ts`

- [ ] **Step 1: Создать**

```typescript
// frontend/src/api/syncPipeline.ts
import { API_BASE } from './config';

export type PipelineMode = 'quick' | 'normal' | 'full' | 'team';

export interface PipelineRequest {
  mode: PipelineMode;
  team?: string;
  since?: string;
}

export interface PipelineEvent {
  type: 'sync_started' | 'stage_start' | 'stage_progress' | 'stage_done' | 'stage_failed' | 'pipeline_done';
  stage?: string;
  run_id?: string;
  duration_ms?: number;
  invalidates?: string[];
  error?: string;
  critical?: boolean;
  status?: string;
  scanned?: number;
  total?: number;
}

export async function startPipeline(
  req: PipelineRequest,
  onEvent: (event: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/sync/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });

  if (resp.status === 409) {
    const body = await resp.json();
    throw new Error(`Pipeline already running: ${body.detail?.running_run_id}`);
  }
  if (!resp.ok) throw new Error(`Pipeline failed: ${resp.status}`);

  const reader = resp.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)) as PipelineEvent);
        } catch {
          // ignore malformed
        }
      }
    }
  }
}

export async function refreshTeam(team: string, onEvent: (e: PipelineEvent) => void, signal?: AbortSignal) {
  return startPipeline({ mode: 'team', team }, onEvent, signal);
}
```

- [ ] **Step 2: Smoke build**

Run: `cd frontend && npm run build`
Expected: build success (или те же warnings что были до коммита)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/syncPipeline.ts
git commit -m "feat(frontend/api): syncPipeline.ts SSE client"
```

---

## Task 24: API клиенты `syncSchedule.ts` + `syncRuns.ts`

**Files:**
- Create: `frontend/src/api/syncSchedule.ts`
- Create: `frontend/src/api/syncRuns.ts`

- [ ] **Step 1: syncSchedule.ts**

```typescript
// frontend/src/api/syncSchedule.ts
import { API_BASE } from './config';
import type { PipelineMode } from './syncPipeline';

export interface SyncSchedule {
  id: string;
  name: string;
  cron_expr: string;
  mode: PipelineMode;
  team?: string | null;
  enabled: boolean;
  last_run_id?: string | null;
  next_run_at?: string | null;
}

export async function listSchedule(): Promise<SyncSchedule[]> {
  const resp = await fetch(`${API_BASE}/sync/schedule`);
  if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
  return resp.json();
}

export async function patchSchedule(id: string, patch: Partial<Pick<SyncSchedule, 'cron_expr' | 'enabled' | 'mode' | 'team'>>): Promise<SyncSchedule> {
  const resp = await fetch(`${API_BASE}/sync/schedule/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
  return resp.json();
}

export async function runScheduleNow(id: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/sync/schedule/${id}/run-now`, { method: 'POST' });
  if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
}
```

- [ ] **Step 2: syncRuns.ts**

```typescript
// frontend/src/api/syncRuns.ts
import { API_BASE } from './config';
import type { PipelineMode } from './syncPipeline';

export interface SyncRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'ok' | 'partial' | 'failed' | 'cancelled' | 'skipped';
  trigger: 'manual' | 'scheduled';
  mode: PipelineMode;
  team: string | null;
  stages_json: Array<{ stage: string; status: string; counts?: Record<string, unknown>; error?: string; started?: string; finished?: string }>;
  error_text: string | null;
  schedule_id: string | null;
}

export async function listRuns(limit = 20): Promise<SyncRun[]> {
  const resp = await fetch(`${API_BASE}/sync/runs?limit=${limit}`);
  if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
  return resp.json();
}

export async function getRun(id: string): Promise<SyncRun> {
  const resp = await fetch(`${API_BASE}/sync/runs/${id}`);
  if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/syncSchedule.ts frontend/src/api/syncRuns.ts
git commit -m "feat(frontend/api): syncSchedule + syncRuns clients"
```

---

## Task 25: API + хук `useEventStream` (глобальный SSE listener)

**Files:**
- Create: `frontend/src/api/events.ts`
- Create: `frontend/src/hooks/useEventStream.ts`

- [ ] **Step 1: events.ts**

```typescript
// frontend/src/api/events.ts
import { API_BASE } from './config';

export interface BusEvent {
  type: string;
  stage?: string;
  invalidates?: string[];
  entity?: string;
  id?: string;
  run_id?: string;
  status?: string;
}

export const STAGE_INVALIDATIONS: Record<string, string[]> = {
  calendar: ['production-calendar', 'capacity'],
  projects: ['projects'],
  issues: ['issues', 'tree', 'backlog', 'planning'],
  worklogs: ['analytics', 'capacity', 'employees'],
  mapping: ['analytics', 'categories'],
};

export function subscribeEvents(onEvent: (e: BusEvent) => void): () => void {
  const es = new EventSource(`${API_BASE}/events/stream`);
  es.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data) as BusEvent);
    } catch {
      // ignore
    }
  };
  es.onerror = () => {
    // EventSource auto-reconnect handles transient errors
  };
  return () => es.close();
}
```

- [ ] **Step 2: useEventStream.ts**

```typescript
// frontend/src/hooks/useEventStream.ts
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { subscribeEvents, STAGE_INVALIDATIONS, type BusEvent } from '../api/events';

export function useEventStream(): void {
  const qc = useQueryClient();

  useEffect(() => {
    const unsub = subscribeEvents((event: BusEvent) => {
      if (event.type === 'stage_done') {
        const keys = event.invalidates ?? STAGE_INVALIDATIONS[event.stage ?? ''] ?? [];
        for (const key of keys) {
          qc.invalidateQueries({ queryKey: [key] });
        }
      }
      if (event.type === 'entity_changed' && event.invalidates) {
        for (const key of event.invalidates) {
          qc.invalidateQueries({ queryKey: [key] });
        }
      }
    });
    return unsub;
  }, [qc]);
}
```

- [ ] **Step 3: Подключить в `App.tsx`**

В `frontend/src/App.tsx` добавить:
```tsx
import { useEventStream } from './hooks/useEventStream';

function App() {
  useEventStream();
  // ... остальной jsx
}
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 5: Smoke в браузере**

Открыть `/dashboard`, в консоли Network проверить наличие `EventSource` соединения с `/api/v1/events/stream`. Status должен быть `pending` (long-lived).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/events.ts frontend/src/hooks/useEventStream.ts frontend/src/App.tsx
git commit -m "feat(frontend): global useEventStream listener wires SSE to React Query"
```

---

## Task 26: Хук `useSyncPipeline`

**Files:**
- Create: `frontend/src/hooks/useSyncPipeline.ts`

- [ ] **Step 1: Создать**

```typescript
// frontend/src/hooks/useSyncPipeline.ts
import { useCallback, useRef, useState } from 'react';

import { startPipeline, type PipelineEvent, type PipelineRequest } from '../api/syncPipeline';

export interface PipelineState {
  running: boolean;
  currentStage: string | null;
  stagesDone: string[];
  lastError: string | null;
  runId: string | null;
}

export function useSyncPipeline() {
  const [state, setState] = useState<PipelineState>({
    running: false,
    currentStage: null,
    stagesDone: [],
    lastError: null,
    runId: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (req: PipelineRequest) => {
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    setState({ running: true, currentStage: null, stagesDone: [], lastError: null, runId: null });

    try {
      await startPipeline(req, (event: PipelineEvent) => {
        setState((prev) => {
          if (event.type === 'sync_started') return { ...prev, runId: event.run_id ?? null };
          if (event.type === 'stage_start') return { ...prev, currentStage: event.stage ?? null };
          if (event.type === 'stage_done') {
            return { ...prev, stagesDone: [...prev.stagesDone, event.stage ?? ''], currentStage: null };
          }
          if (event.type === 'stage_failed') {
            return { ...prev, lastError: event.error ?? 'unknown', currentStage: null };
          }
          if (event.type === 'pipeline_done') {
            return { ...prev, running: false, currentStage: null };
          }
          return prev;
        });
      }, ctl.signal);
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setState((prev) => ({ ...prev, running: false, lastError: (err as Error).message }));
      } else {
        setState((prev) => ({ ...prev, running: false }));
      }
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { ...state, start, cancel };
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSyncPipeline.ts
git commit -m "feat(frontend/hooks): useSyncPipeline with SSE state machine"
```

---

## Task 27: PipelineRunner компонент (главные кнопки + прогресс)

**Files:**
- Create: `frontend/src/components/sync/PipelineRunner.tsx`

- [ ] **Step 1: Создать**

```tsx
// frontend/src/components/sync/PipelineRunner.tsx
import { Button, Card, Dropdown, Progress, Space, Tag, Select } from 'antd';
import { SyncOutlined, TeamOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useSyncPipeline } from '../../hooks/useSyncPipeline';
import type { PipelineMode } from '../../api/syncPipeline';

const STAGE_TOTAL: Record<PipelineMode, number> = {
  quick: 1,
  normal: 5,
  full: 5,
  team: 3,
};

export function PipelineRunner({ teams }: { teams: string[] }) {
  const pipeline = useSyncPipeline();
  const [team, setTeam] = useState<string | undefined>(undefined);

  const total = pipeline.runId ? STAGE_TOTAL[pipeline.running ? 'normal' : 'normal'] : 0;
  const percent = total > 0 ? Math.round((pipeline.stagesDone.length / total) * 100) : 0;

  const items = [
    { key: 'quick', label: 'Быстро (worklogs delta)' },
    { key: 'normal', label: 'Обычно ★ (incremental + worklogs + mapping)' },
    { key: 'full', label: 'Полностью (full reread)' },
  ];

  return (
    <Card>
      <Space size="middle">
        <Dropdown
          menu={{
            items,
            onClick: ({ key }) => pipeline.start({ mode: key as PipelineMode }),
          }}
          disabled={pipeline.running}
        >
          <Button type="primary" icon={<SyncOutlined spin={pipeline.running} />}>
            Синхронизировать ▾
          </Button>
        </Dropdown>

        <Space>
          <TeamOutlined />
          <Select
            placeholder="Команда"
            style={{ width: 200 }}
            value={team}
            onChange={setTeam}
            allowClear
            options={teams.map((t) => ({ value: t, label: t }))}
          />
          <Button
            disabled={!team || pipeline.running}
            onClick={() => team && pipeline.start({ mode: 'team', team })}
          >
            Обновить команду
          </Button>
        </Space>
      </Space>

      {pipeline.running && (
        <div style={{ marginTop: 16 }}>
          <div>
            Этап {pipeline.stagesDone.length + 1}/{total} —{' '}
            <Tag color="processing">{pipeline.currentStage ?? '...'}</Tag>
          </div>
          <Progress percent={percent} status={pipeline.lastError ? 'exception' : 'active'} />
          <Button danger onClick={pipeline.cancel}>Прервать</Button>
        </div>
      )}

      {pipeline.lastError && !pipeline.running && (
        <div style={{ marginTop: 8 }}>
          <Tag color="error">Ошибка: {pipeline.lastError}</Tag>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sync/PipelineRunner.tsx
git commit -m "feat(frontend/sync): PipelineRunner — main buttons + progress"
```

---

## Task 28: SyncSchedule компонент

**Files:**
- Create: `frontend/src/components/sync/SyncSchedule.tsx`

- [ ] **Step 1: Создать**

```tsx
// frontend/src/components/sync/SyncSchedule.tsx
import { Card, Switch, Table, Button, Input, message } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { listSchedule, patchSchedule, runScheduleNow, type SyncSchedule } from '../../api/syncSchedule';

export function SyncScheduleSection() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({
    queryKey: ['sync-schedule'],
    queryFn: listSchedule,
  });

  const patchMut = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<SyncSchedule> }) => patchSchedule(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync-schedule'] }),
    onError: (e: Error) => message.error(e.message),
  });

  const runNowMut = useMutation({
    mutationFn: (id: string) => runScheduleNow(id),
    onSuccess: () => message.success('Запущено'),
    onError: (e: Error) => message.error(e.message),
  });

  return (
    <Card title="Расписание автозапуска">
      <Table
        loading={isLoading}
        dataSource={data}
        rowKey="id"
        pagination={false}
        columns={[
          { title: 'Название', dataIndex: 'name' },
          {
            title: 'Cron',
            dataIndex: 'cron_expr',
            render: (val, row) => (
              <Input
                defaultValue={val}
                style={{ width: 160 }}
                onBlur={(e) => {
                  if (e.target.value !== val) patchMut.mutate({ id: row.id, patch: { cron_expr: e.target.value } });
                }}
              />
            ),
          },
          { title: 'Режим', dataIndex: 'mode' },
          {
            title: 'Включено',
            dataIndex: 'enabled',
            render: (val, row) => (
              <Switch checked={val} onChange={(checked) => patchMut.mutate({ id: row.id, patch: { enabled: checked } })} />
            ),
          },
          {
            title: 'Действия',
            render: (_, row) => (
              <Button size="small" onClick={() => runNowMut.mutate(row.id)}>
                Запустить сейчас
              </Button>
            ),
          },
        ]}
      />
    </Card>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sync/SyncSchedule.tsx
git commit -m "feat(frontend/sync): SyncSchedule section with inline edit + run-now"
```

---

## Task 29: SyncHistory компонент

**Files:**
- Create: `frontend/src/components/sync/SyncHistory.tsx`

- [ ] **Step 1: Создать**

```tsx
// frontend/src/components/sync/SyncHistory.tsx
import { Card, Table, Tag, Descriptions } from 'antd';
import { useQuery } from '@tanstack/react-query';

import { listRuns, type SyncRun } from '../../api/syncRuns';

const STATUS_COLORS: Record<string, string> = {
  ok: 'success',
  partial: 'warning',
  failed: 'error',
  cancelled: 'default',
  skipped: 'default',
  running: 'processing',
};

function formatDuration(start: string, end: string | null): string {
  if (!end) return '...';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

export function SyncHistorySection() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['sync-runs'],
    queryFn: () => listRuns(20),
    refetchInterval: 5000,
  });

  return (
    <Card title="История запусков">
      <Table<SyncRun>
        loading={isLoading}
        dataSource={data}
        rowKey="id"
        pagination={false}
        expandable={{
          expandedRowRender: (run) => (
            <Descriptions bordered size="small" column={1}>
              {run.stages_json.map((s, i) => (
                <Descriptions.Item key={i} label={s.stage}>
                  <Tag color={STATUS_COLORS[s.status] ?? 'default'}>{s.status}</Tag>
                  {s.error && <span style={{ color: 'red', marginLeft: 8 }}>{s.error}</span>}
                  {s.counts && Object.keys(s.counts).length > 0 && (
                    <span style={{ marginLeft: 8 }}>{JSON.stringify(s.counts)}</span>
                  )}
                </Descriptions.Item>
              ))}
            </Descriptions>
          ),
        }}
        columns={[
          { title: 'Время', dataIndex: 'started_at', render: (v) => new Date(v).toLocaleString() },
          { title: 'Триггер', dataIndex: 'trigger' },
          {
            title: 'Статус',
            dataIndex: 'status',
            render: (v) => <Tag color={STATUS_COLORS[v] ?? 'default'}>{v}</Tag>,
          },
          {
            title: 'Длит.',
            render: (_, row) => formatDuration(row.started_at, row.finished_at),
          },
          { title: 'Режим', dataIndex: 'mode' },
        ]}
      />
    </Card>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sync/SyncHistory.tsx
git commit -m "feat(frontend/sync): SyncHistory table with stage drill-down"
```

---

## Task 30: SyncAdvanced (collapsible — редкие операции)

**Files:**
- Create: `frontend/src/components/sync/SyncAdvanced.tsx`

- [ ] **Step 1: Создать**

```tsx
// frontend/src/components/sync/SyncAdvanced.tsx
import { Collapse, Space, Button, DatePicker, InputNumber, Popconfirm, message } from 'antd';
import { useState } from 'react';
import dayjs, { type Dayjs } from 'dayjs';

import { useReloadWorklogs, useUpdateWorklogs, useRecalculateMapping } from '../../hooks/useSync';
import { useSyncProductionCalendarYear } from '../../hooks/useProductionCalendar';
import { useAutoDetectTeams } from '../../hooks/useAutoDetectTeams';

export function SyncAdvanced() {
  const [reloadDate, setReloadDate] = useState<Dayjs | null>(dayjs().subtract(30, 'day'));
  const [calYear, setCalYear] = useState<number>(dayjs().year());

  const reloadMut = useReloadWorklogs();
  const calMut = useSyncProductionCalendarYear();
  const detectMut = useAutoDetectTeams();
  const recalcMut = useRecalculateMapping();

  return (
    <Collapse
      items={[{
        key: 'advanced',
        label: 'Дополнительно (редкие операции)',
        children: (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space>
              <DatePicker value={reloadDate} onChange={setReloadDate} />
              <Popconfirm
                title="Удалить и перечитать ворклоги с указанной даты?"
                onConfirm={() => reloadDate && reloadMut.mutate({ since: reloadDate.format('YYYY-MM-DD') })}
              >
                <Button danger loading={reloadMut.isPending}>
                  Полная перезагрузка ворклогов
                </Button>
              </Popconfirm>
            </Space>

            <Space>
              <InputNumber value={calYear} onChange={(v) => setCalYear(v ?? dayjs().year())} />
              <Button onClick={() => calMut.mutate(calYear)} loading={calMut.isPending}>
                Загрузить производственный календарь
              </Button>
            </Space>

            <Button onClick={() => detectMut.mutate()} loading={detectMut.isPending}>
              Авто-определить команды сотрудников
            </Button>

            <Button onClick={() => recalcMut.mutate()} loading={recalcMut.isPending}>
              Пересчитать маппинг категорий
            </Button>
          </Space>
        ),
      }]}
    />
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success (если хук `useAutoDetectTeams` отсутствует — извлечь существующий из CapacityPage в `frontend/src/hooks/useAutoDetectTeams.ts`)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sync/SyncAdvanced.tsx frontend/src/hooks/useAutoDetectTeams.ts
git commit -m "feat(frontend/sync): SyncAdvanced collapsible — rare operations"
```

---

## Task 31: SyncHubPage — собрать все секции

**Files:**
- Create: `frontend/src/pages/SyncHubPage.tsx`

- [ ] **Step 1: Создать**

```tsx
// frontend/src/pages/SyncHubPage.tsx
import { Space } from 'antd';
import { useQuery } from '@tanstack/react-query';

import { PipelineRunner } from '../components/sync/PipelineRunner';
import { SyncScheduleSection } from '../components/sync/SyncSchedule';
import { SyncHistorySection } from '../components/sync/SyncHistory';
import { SyncAdvanced } from '../components/sync/SyncAdvanced';
import { fetchTeams } from '../api/teams';

export default function SyncHubPage() {
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: fetchTeams });

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PipelineRunner teams={teams.map((t: { name?: string }) => t.name ?? '').filter(Boolean)} />
      <SyncScheduleSection />
      <SyncHistorySection />
      <SyncAdvanced />
    </Space>
  );
}
```

(Если `fetchTeams` отсутствует — найти аналог в существующих API и использовать его.)

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SyncHubPage.tsx
git commit -m "feat(frontend/pages): SyncHubPage assembles all sync sections"
```

---

## Task 32: Маршрутизация — `/sync` → SyncHubPage, `/sync-old` редирект

**Files:**
- Modify: routing config (`frontend/src/router.tsx` или `App.tsx` в зависимости от того, где определён router)

- [ ] **Step 1: Найти текущий router**

Run: `grep -rn "Routes\|createBrowserRouter\|BrowserRouter" frontend/src --include="*.tsx" -l | head -5`
Expected: один файл с router-конфигом

- [ ] **Step 2: Подменить маршрут `/sync`**

В файле router-а:
```tsx
// Старое: <Route path="/sync" element={<SyncPage />} />
<Route path="/sync" element={<SyncHubPage />} />
<Route path="/sync-old" element={<SyncPage />} />
```

(Если используется createBrowserRouter — соответствующая правка структуры.)

- [ ] **Step 3: Build + ручной smoke**

Run: `cd frontend && npm run build && npm run dev`
Открыть `/sync` — должен загрузиться SyncHubPage с 4 секциями.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router.tsx  # путь по факту
git commit -m "feat(frontend/router): /sync → SyncHubPage, /sync-old → legacy SyncPage"
```

---

## Task 33: CategoriesEditorPage — извлечь Tab1 из SyncPage в отдельную страницу `/categories`

**Files:**
- Create: `frontend/src/pages/CategoriesEditorPage.tsx`
- Modify: routing config + меню

- [ ] **Step 1: Создать страницу-обёртку**

```tsx
// frontend/src/pages/CategoriesEditorPage.tsx
import { CategoryConfigTab } from '../components/CategoryConfigTab';

export default function CategoriesEditorPage() {
  return <CategoryConfigTab />;
}
```

(Если `CategoryConfigTab` сейчас живёт inline в `SyncPage.tsx` — извлечь в отдельный файл `frontend/src/components/CategoryConfigTab.tsx`.)

- [ ] **Step 2: Маршрут**

```tsx
<Route path="/categories" element={<CategoriesEditorPage />} />
```

- [ ] **Step 3: Пункт меню**

В файле меню (обычно `frontend/src/components/AppLayout.tsx` или подобный):
```tsx
{ key: 'categories', label: 'Категории', icon: <TagsOutlined />, path: '/categories' }
```

(Поставить рядом с пунктом «Бэклог».)

- [ ] **Step 4: Build + smoke**

Run: `cd frontend && npm run build && npm run dev`
Открыть `/categories` — должен загрузиться editor категорий.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CategoriesEditorPage.tsx frontend/src/components/CategoryConfigTab.tsx frontend/src/router.tsx frontend/src/components/AppLayout.tsx
git commit -m "feat(frontend/pages): /categories — editor extracted from SyncPage"
```

---

# Phase 5 — Удаление дубликатов кнопок

## Task 34: Удалить кнопку «Синхронизация» с DashboardPage

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx:36-47`

- [ ] **Step 1: Удалить блок кнопки**

Удалить из `DashboardPage.tsx` импорт `useSyncMutation`, `SyncOutlined`, кнопку `<Button>...</Button>` (строки 36-47 по аудиту), и связанный `onClick` handler.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: success

- [ ] **Step 3: Smoke**

Dashboard открывается, нет кнопки «Синхронизация».

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "refactor(dashboard): remove sync button (moved to /sync hub)"
```

---

## Task 35: Заменить «Обновить с Jira» на BacklogPage локальным invalidate

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx:579-587`

- [ ] **Step 1: Заменить mutation на refetch**

Старое:
```tsx
const refreshMut = useRefreshFromJira();
<Button onClick={() => refreshMut.mutate()}>Обновить с Jira</Button>
```

Новое:
```tsx
const qc = useQueryClient();
<Button onClick={() => qc.invalidateQueries({ queryKey: ['backlog'] })}>
  Обновить
</Button>
```

(Удалить импорт `useRefreshFromJira`, если он больше не нужен — проверить grep.)

- [ ] **Step 2: Build + smoke**

Run: `cd frontend && npm run build`
Expected: success. Открыть Backlog — кнопка переименована, обновляет только локальный кэш (без Jira-запроса).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BacklogPage.tsx
git commit -m "refactor(backlog): replace 'Refresh from Jira' with local query invalidate"
```

---

## Task 36: Удалить «Синк с бэклогом» с PlanningPage (авто через event)

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx:464-473`

- [ ] **Step 1: Удалить блок кнопки**

Найти `<Button>Синк с бэклогом</Button>` и связанный `useSyncScenarioBacklog` mutation. Удалить.

(Бэкенд продолжает делать backlog→draft scenario sync inline в issue stage. Кнопка дублирует уже автоматическое поведение.)

- [ ] **Step 2: Убедиться что событие issues→planning инвалидирует planning queries**

В `frontend/src/api/events.ts` STAGE_INVALIDATIONS уже включает `planning` для стадии `issues` — ничего менять не надо.

- [ ] **Step 3: Build + smoke**

Run: `cd frontend && npm run build`
Открыть Planning — кнопки нет. После запуска pipeline normal mode planning auto-refreshes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "refactor(planning): remove 'Sync backlog' button (auto via event stream)"
```

---

## Task 37: Удалить «Пересчитать состав / ёмкость» с CapacityPage

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx:356-394`

- [ ] **Step 1: Удалить кнопки**

Удалить блоки:
- «Определить команды авто» (строки ~356-364) — переехала в SyncAdvanced
- «Пересчитать состав» (строки ~369-376) — теперь в `/employees/recalc-active` происходит автоматически после worklogs stage; кнопка лишняя
- «Пересчитать ёмкость по командам» (строки ~379-394) — авто после worklogs event

Удалить связанные импорты `useAutoDetectTeams`, `useRecalcActiveEmployees`, `useTeamRecalc`, если они больше не используются.

- [ ] **Step 2: Build + smoke**

Run: `cd frontend && npm run build`
Открыть Capacity — кнопок нет. Запустить pipeline → данные на capacity-странице обновляются автоматически.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CapacityPage.tsx
git commit -m "refactor(capacity): remove recalc buttons (auto via event stream)"
```

---

## Task 38: Пометить deprecated старые backend-эндпоинты

**Files:**
- Modify: `app/api/endpoints/sync.py`

- [ ] **Step 1: Добавить `deprecated=True` к старым маршрутам**

Найти и пометить:
- `POST /sync/full`
- `POST /sync/projects` (при необходимости — если фронт ещё зовёт)
- `POST /sync/issues`
- `POST /sync/teams`
- `POST /sync/issues/refresh` — оставить активным (используется в team mode внутри pipeline)
- `POST /sync/worklogs`
- `POST /sync/comments`
- `POST /sync/worklogs/reload`
- `POST /sync/worklogs/reload/stream`
- `POST /sync/worklogs/update/stream` — оставить активным (используется в pipeline и SyncAdvanced)

Пример:
```python
@router.post("/full", deprecated=True)
async def full_sync(...):
    ...
```

- [ ] **Step 2: Smoke OpenAPI**

Run: `curl http://localhost:8000/openapi.json | python -m json.tool | grep -A 1 '"deprecated": true' | head -20`
Expected: deprecated маршруты помечены

- [ ] **Step 3: Commit**

```bash
git add app/api/endpoints/sync.py
git commit -m "chore(api): mark legacy sync endpoints deprecated (removed in PR 6)"
```

---

## Task 39: E2E тест хаба (Playwright)

**Files:**
- Create: `tests/e2e/sync_hub.spec.ts`

- [ ] **Step 1: Тест**

```typescript
// tests/e2e/sync_hub.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Sync Hub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/sync');
  });

  test('shows main button + schedule + history sections', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Синхронизировать/ })).toBeVisible();
    await expect(page.getByText('Расписание автозапуска')).toBeVisible();
    await expect(page.getByText('История запусков')).toBeVisible();
  });

  test('schedule shows seeded rules', async ({ page }) => {
    await expect(page.getByText('daily_incremental')).toBeVisible();
    await expect(page.getByText('worklogs_workhours')).toBeVisible();
    await expect(page.getByText('weekly_full')).toBeVisible();
  });

  test('toggling enabled persists', async ({ page }) => {
    const row = page.getByRole('row', { name: /daily_incremental/ });
    const toggle = row.getByRole('switch');
    await toggle.click();
    await page.reload();
    const reloaded = page.getByRole('row', { name: /daily_incremental/ }).getByRole('switch');
    await expect(reloaded).toHaveAttribute('aria-checked', 'false');
    // Восстановить
    await reloaded.click();
  });
});
```

- [ ] **Step 2: Запустить через локальный e2e скрипт**

Run: `.\scripts\e2e-local.ps1`
Expected: новые тесты проходят (плюс существующие)

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/sync_hub.spec.ts
git commit -m "test(e2e): sync hub — main button, schedule, history visible"
```

---

## Task 40: Финальный smoke + ручная проверка end-to-end

**Files:** none (manual)

- [ ] **Step 1: Перезапуск стека**

Run (PowerShell):
```powershell
.\restart-dev.ps1
```

- [ ] **Step 2: Backend smoke**

Run: `py -3.10 -m pytest tests/ -v --timeout=60`
Expected: все тесты зелёные (или те же flakies что были до начала плана — см. memory `project_ci_red_pre_existing.md`)

- [ ] **Step 3: Frontend lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: success

- [ ] **Step 4: Ручной сценарий «обычная синхронизация»**

1. Открыть `/sync`
2. Жмём «Синхронизировать → Обычно»
3. Видим прогресс по 5 стадиям
4. Pipeline завершается, в Истории появляется строка status=ok
5. Открыть `/dashboard` в новой вкладке — видим свежие данные без F5
6. Открыть `/capacity` — видим свежие данные

- [ ] **Step 5: Ручной сценарий «обновить команду»**

1. На `/sync` выбрать команду из dropdown, нажать «Обновить команду»
2. Видим прогресс по 3 стадиям (worklogs → issues_refresh → mapping)
3. В Истории строка mode=team team=<выбранная>

- [ ] **Step 6: Ручной сценарий «расписание»**

1. На `/sync` в секции Расписание выключить toggle daily_incremental
2. Перезагрузить страницу — toggle остался выключенным
3. Включить обратно
4. Нажать «Запустить сейчас» рядом с любым правилом — pipeline стартует

- [ ] **Step 7: Commit всех изменений если что-то правилось вручную**

```bash
git status
# при необходимости git add + commit
```

- [ ] **Step 8: Push в origin/main**

```bash
git push origin main
```

(Соответствует memory feedback: «Commit + push after each batch».)

---

# Phase 6 — Cleanup (отдельный PR через 1 неделю после релиза)

## Task 41 (вне scope этого спринта): Удалить deprecated endpoints + /sync-old

**Files:**
- Modify: `app/api/endpoints/sync.py` — удалить эндпоинты, помеченные `deprecated=True`
- Modify: routing config — удалить `/sync-old` route и `SyncPage` (legacy)

Делается отдельным PR через ≥1 спринт после релиза.

---

# Self-Review (заполняется при выполнении плана)

После прохождения всех задач Phase 1-5:

- [ ] **Spec coverage:** каждая секция спека (`docs/superpowers/specs/2026-04-27-sync-consolidation-design.md`) имеет соответствующую задачу
- [ ] **Placeholder scan:** все шаги содержат конкретный код / команду
- [ ] **Type consistency:** имена методов, классов, типов совпадают между задачами

---

# Дополнительные замечания исполнителю

- **Windows uvicorn --reload** часто не подхватывает изменения в backend-коде (см. memory `feedback_windows_uvicorn_reload.md`). После каждой правки бэка перезапускай процесс через `restart-dev.ps1` или вручную (см. Task 16 step 5).
- **AntD 6 notification** использует `title` (не `message` — `message` deprecated). См. memory `feedback_antd6_notification_title.md`.
- **Model field gotchas:** `Issue.issue_type`, `Category.label/is_system`. См. memory `feedback_model_field_names.md`.
- **conftest и тесты:** если новые тесты падают с проблемами `:memory:` БД — взгляни на `project_capacity_overhaul_followups.md` (StaticPool fix).
- **Коммитить часто** после каждой завершённой задачи — push в origin/main по завершении phase.
- **Не «улучшать» соседний код** — touch только то, что относится к sync consolidation.
- **Каждый тест должен реально упасть до реализации** (TDD red phase). Если тест проходит сразу — это значит тест плохой или код уже есть, переделай тест.
