# Usage Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Админ-аналитика использования сервиса — кто заходит, какие страницы востребованы, кто чем живёт. Heartbeat-based реальное время работы (Page Visibility API), raw 90 дней + дневные агрегаты навсегда, UI как новая admin-вкладка `/settings` → «Использование».

**Architecture:** Две таблицы (`usage_events` raw 90 дней, `usage_daily` агрегат). Клиент копит события в буфере, шлёт bulk `POST /usage/events` каждые 30 секунд + `sendBeacon` на `beforeunload`. Daily cron сворачивает raw → daily и подчищает старые. Admin читает 6 query-эндпоинтов под `/admin/usage`.

**Tech Stack:** SQLAlchemy 2.0 + Alembic (batch для SQLite), FastAPI, pydantic v2, APScheduler (уже подключён), React 19 + TS 6 + AntD 6, TanStack Query, Recharts (если уже стоит) или AntD-родные графики.

**Spec:** [docs/superpowers/specs/2026-05-28-usage-analytics-design.md](../specs/2026-05-28-usage-analytics-design.md)

---

## File Map

**Backend create:**
- `app/models/usage_event.py` — `UsageEvent` model + `UsageEventType` enum
- `app/models/usage_daily.py` — `UsageDaily` model
- `app/schemas/usage.py` — pydantic schemas (in / out)
- `app/services/usage_service.py` — record + aggregate + queries
- `app/api/endpoints/usage.py` — client-facing `POST /usage/events`
- `app/api/endpoints/admin_usage.py` — admin queries
- `app/jobs/aggregate_usage.py` — cron entrypoint
- `alembic/versions/053_usage_analytics.py` — миграция
- `tests/test_usage_service.py`
- `tests/test_usage_endpoints.py`
- `tests/test_admin_usage_endpoints.py`
- `tests/test_aggregate_usage_job.py`

**Backend modify:**
- `app/models/__init__.py` — re-export `UsageEvent`, `UsageEventType`, `UsageDaily`
- `app/api/router.py` — register `/usage` (auth) и `/admin/usage` (admin)
- `app/main.py` — добавить daily job aggregate_usage в lifespan

**Frontend create:**
- `frontend/src/lib/usage/routeTable.ts` — список known routes для нормализации
- `frontend/src/lib/usage/normalizePath.ts` — `:id` / `:key` replacement
- `frontend/src/lib/usage/sender.ts` — буфер + flush + sendBeacon
- `frontend/src/lib/usage/track.ts` — `trackAction(type, entityId?)` helper
- `frontend/src/lib/usage/usePageView.ts` — hook
- `frontend/src/lib/usage/useHeartbeat.ts` — hook (Page Visibility)
- `frontend/src/lib/usage/__tests__/normalizePath.test.ts`
- `frontend/src/lib/usage/__tests__/sender.test.ts`
- `frontend/src/api/usage.ts` — admin queries client
- `frontend/src/components/admin/usage/UsageKpiBar.tsx`
- `frontend/src/components/admin/usage/UsageUsersTable.tsx`
- `frontend/src/components/admin/usage/UsagePagesTable.tsx`
- `frontend/src/components/admin/usage/UsageMatrix.tsx`
- `frontend/src/components/admin/usage/UsageTimeline.tsx`
- `frontend/src/components/admin/usage/UsageActionsTable.tsx`
- `frontend/src/components/admin/usage/UsageTab.tsx`
- `frontend/src/components/admin/usage/pathLabels.ts` — `/resource-planning` → «Планирование ресурсов»

**Frontend modify:**
- `frontend/src/App.tsx` — добавить `<UsageTracker />` (or hooks) после auth
- `frontend/src/pages/LoginPage.tsx` — `trackAction('login')` после успешного логина
- `frontend/src/pages/SettingsPage.tsx` — admin-only tab «Использование»
- `frontend/src/pages/SyncPage.tsx` — `trackAction('sync_started')` и `'sync_cancelled'`
- `frontend/src/pages/PlanningPage.tsx` (или scenarios) — `'scenario_created'`, `'scenario_approved'`, `'scenario_xlsx_exported'`
- `frontend/src/pages/ProjectsPage.tsx` — `'ai_summary_requested'`, `'ai_summary_refreshed'`
- `frontend/src/components/feedback/FeedbackDrawer.tsx` — `'feedback_submitted'`
- `frontend/src/pages/ResourcePlanningPage.tsx` — `'resource_plan_edited'` (на drag/PATCH)
- `frontend/src/pages/ThemeReportPage.tsx` (или где merge тем) — `'theme_merged'`
- `frontend/src/components/CategoryPicker.tsx` (или где меняют) — `'category_changed'`
- `frontend/src/components/AuthLayout.tsx` (или wherever logout) — `'logout'`

---

## Phase A — Backend Foundation

### Task A1: Models + migration

**Files:**
- Create: `app/models/usage_event.py`
- Create: `app/models/usage_daily.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/053_usage_analytics.py`

- [ ] **Step 1: Create `app/models/usage_event.py`**

```python
"""UsageEvent — raw события трекинга использования (хранятся 90 дней)."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class UsageEventType(str, PyEnum):
    page_view = "page_view"
    heartbeat = "heartbeat"
    action = "action"


class UsageEvent(Base, TimestampMixin):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[UsageEventType] = mapped_column(
        Enum(UsageEventType, native_enum=False), nullable=False
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("ix_usage_events_user_at", "user_id", "at"),
        Index("ix_usage_events_at_type", "at", "event_type"),
        Index("ix_usage_events_path_at", "path", "at"),
    )
```

- [ ] **Step 2: Create `app/models/usage_daily.py`**

```python
"""UsageDaily — дневной агрегат usage_events (хранится навсегда)."""
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class UsageDaily(Base, TimestampMixin):
    __tablename__ = "usage_daily"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("date", "user_id", "path", name="uq_usage_daily_date_user_path"),
        Index("ix_usage_daily_date_user", "date", "user_id"),
        Index("ix_usage_daily_date_path", "date", "path"),
    )
```

- [ ] **Step 3: Register both models in `app/models/__init__.py`**

After the `feedback` import (line 60), add:
```python
from app.models.usage_event import UsageEvent, UsageEventType
from app.models.usage_daily import UsageDaily
```

And add to `__all__`:
```python
    "UsageEvent",
    "UsageEventType",
    "UsageDaily",
```

- [ ] **Step 4: Create Alembic migration**

Run:
```bash
py -3.10 -m alembic revision -m "usage_analytics" --rev-id 053
```

Then replace the generated body with batch-mode create_table for both tables (mirror Step 1 + Step 2 schema). Use `op.batch_alter_table` is unnecessary for create; use `op.create_table` directly with the same indexes and unique constraint declared in `__table_args__`.

- [ ] **Step 5: Apply migration**

Run: `py -3.10 -m alembic upgrade head`
Expected: migration 053 applied without error.

- [ ] **Step 6: Commit**

```bash
git add app/models/usage_event.py app/models/usage_daily.py app/models/__init__.py alembic/versions/053_*.py
git commit -m "feat(usage): add usage_events + usage_daily tables"
```

---

### Task A2: Pydantic schemas

**Files:**
- Create: `app/schemas/usage.py`

- [ ] **Step 1: Create schemas**

```python
"""Pydantic schemas для usage analytics."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class UsageEventIn(BaseModel):
    event_type: Literal["page_view", "heartbeat", "action"]
    path: str = Field(..., max_length=255)
    action_type: str | None = Field(None, max_length=64)
    entity_id: str | None = Field(None, max_length=36)
    at: datetime


class UsageEventBatchIn(BaseModel):
    events: list[UsageEventIn] = Field(..., max_length=100)


class UsageBatchResult(BaseModel):
    accepted: int
    rejected: int


class UsageOverviewOut(BaseModel):
    dau: int
    wau: int
    mau: int
    hours_30d: float


class UsageUserRowOut(BaseModel):
    user_id: str
    display_name: str
    role: str
    last_seen: datetime | None
    active_days: int
    hours: float
    top_path: str | None


class UsagePageRowOut(BaseModel):
    path: str
    unique_users: int
    views: int
    hours: float


class UsageMatrixCellOut(BaseModel):
    user_id: str
    display_name: str
    path: str
    hours: float


class UsageMatrixOut(BaseModel):
    users: list[dict]  # [{user_id, display_name}]
    paths: list[dict]  # [{path}]
    cells: list[UsageMatrixCellOut]


class UsageTimelinePointOut(BaseModel):
    date: date
    views: int
    active_users: int
    seconds: int


class UsageActionRowOut(BaseModel):
    action_type: str
    total: int
    top_users: list[dict]  # [{user_id, display_name, count}]
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/usage.py
git commit -m "feat(usage): add pydantic schemas"
```

---

### Task A3: UsageService — record + validation

**Files:**
- Create: `app/services/usage_service.py`
- Create: `tests/test_usage_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_usage_service.py
"""Тесты UsageService — запись событий и валидация."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import User, UsageEvent, UsageEventType, UserRole
from app.services.usage_service import UsageService, ALLOWED_PATHS


@pytest.fixture
def user(db_session):
    u = User(
        email="u@test", password_hash="x", display_name="U",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_record_events_accepts_known_path(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": now},
    ])
    assert res == {"accepted": 1, "rejected": 0}
    rows = db_session.query(UsageEvent).all()
    assert len(rows) == 1
    assert rows[0].event_type == UsageEventType.page_view


def test_record_events_rejects_unknown_path(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/nonsense", "at": now},
    ])
    assert res == {"accepted": 0, "rejected": 1}
    assert db_session.query(UsageEvent).count() == 0


def test_record_events_rejects_old_timestamp(db_session, user):
    svc = UsageService(db_session)
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": old},
    ])
    assert res == {"accepted": 0, "rejected": 1}


def test_record_events_action_requires_action_type(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "action", "path": "/dashboard", "at": now},
    ])
    assert res == {"accepted": 0, "rejected": 1}
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: ImportError / NameError on `UsageService`, `ALLOWED_PATHS`.

- [ ] **Step 3: Implement service**

```python
# app/services/usage_service.py
"""UsageService — запись raw событий + валидация."""
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import UsageEvent, UsageEventType


# Whitelist маршрутов SPA — нормализованные пути.
ALLOWED_PATHS: set[str] = {
    "/dashboard",
    "/analytics",
    "/projects",
    "/projects/:key",
    "/sync",
    "/categories",
    "/category-config",
    "/capacity",
    "/backlog",
    "/planning",
    "/scenarios/:id",
    "/scenarios/:id/edit",
    "/resource-planning",
    "/executive",
    "/themes",
    "/work-type-report",
    "/feedback",
    "/settings",
    "/login",
}

_MAX_TIME_SKEW = timedelta(hours=1)


class UsageService:
    def __init__(self, db: Session):
        self.db = db

    def record_events(self, *, user_id: str, events: Iterable[dict]) -> dict:
        """Batch insert. Тихо игнорирует мусор; возвращает счётчики."""
        now = datetime.utcnow()
        accepted = 0
        rejected = 0
        rows: list[UsageEvent] = []

        for ev in events:
            if not self._is_valid(ev, now):
                rejected += 1
                continue
            rows.append(UsageEvent(
                user_id=user_id,
                event_type=UsageEventType(ev["event_type"]),
                path=ev["path"],
                action_type=ev.get("action_type"),
                entity_id=ev.get("entity_id"),
                at=ev["at"] if isinstance(ev["at"], datetime) else datetime.fromisoformat(ev["at"]),
            ))
            accepted += 1

        if rows:
            self.db.add_all(rows)
            self.db.commit()

        return {"accepted": accepted, "rejected": rejected}

    @staticmethod
    def _is_valid(ev: dict, now: datetime) -> bool:
        if ev.get("path") not in ALLOWED_PATHS:
            return False
        if ev.get("event_type") not in ("page_view", "heartbeat", "action"):
            return False
        if ev["event_type"] == "action" and not ev.get("action_type"):
            return False
        at = ev.get("at")
        if isinstance(at, str):
            try:
                at = datetime.fromisoformat(at)
            except ValueError:
                return False
        if not isinstance(at, datetime):
            return False
        if at.tzinfo is not None:
            at = at.astimezone(timezone.utc).replace(tzinfo=None)
        if abs((now - at).total_seconds()) > _MAX_TIME_SKEW.total_seconds():
            return False
        return True
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/usage_service.py tests/test_usage_service.py
git commit -m "feat(usage): add UsageService.record_events with validation"
```

---

### Task A4: Client endpoint `POST /usage/events`

**Files:**
- Create: `app/api/endpoints/usage.py`
- Create: `tests/test_usage_endpoints.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_usage_endpoints.py
"""Тесты client-facing /usage/events."""
from datetime import datetime


def test_post_events_inserts(authed_client):
    now = datetime.utcnow().isoformat()
    r = authed_client.post("/api/v1/usage/events", json={"events": [
        {"event_type": "page_view", "path": "/dashboard", "at": now},
        {"event_type": "heartbeat", "path": "/dashboard", "at": now},
    ]})
    assert r.status_code == 200
    assert r.json() == {"accepted": 2, "rejected": 0}


def test_post_events_ignores_garbage(authed_client):
    now = datetime.utcnow().isoformat()
    r = authed_client.post("/api/v1/usage/events", json={"events": [
        {"event_type": "page_view", "path": "/dashboard", "at": now},
        {"event_type": "page_view", "path": "/garbage", "at": now},
    ]})
    assert r.status_code == 200
    assert r.json() == {"accepted": 1, "rejected": 1}


def test_post_events_requires_auth(client):
    now = datetime.utcnow().isoformat()
    r = client.post("/api/v1/usage/events", json={"events": [
        {"event_type": "page_view", "path": "/dashboard", "at": now},
    ]})
    assert r.status_code in (401, 403)
```

> `authed_client` and `client` fixtures already exist in conftest (see `tests/test_feedback_endpoints.py` for example wiring — copy that pattern if needed).

- [ ] **Step 2: Run tests — expect FAIL**

```bash
py -3.10 -m pytest tests/test_usage_endpoints.py -v
```
Expected: 404 on the route.

- [ ] **Step 3: Implement endpoint**

```python
# app/api/endpoints/usage.py
"""Client-facing endpoint для записи usage-событий."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.usage import UsageBatchResult, UsageEventBatchIn
from app.services.usage_service import UsageService

router = APIRouter()


@router.post("/events", response_model=UsageBatchResult)
def post_events(
    payload: UsageEventBatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageBatchResult:
    svc = UsageService(db)
    res = svc.record_events(
        user_id=user.id,
        events=[e.model_dump() for e in payload.events],
    )
    return UsageBatchResult(**res)
```

- [ ] **Step 4: Register router in `app/api/router.py`**

Add import alongside other endpoint imports:
```python
from app.api.endpoints import usage as usage_endpoints
```

Add include after the feedback router include (around line 182):
```python
api_router.include_router(
    usage_endpoints.router, prefix="/usage", tags=["usage"], dependencies=_auth_dep,
)
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
py -3.10 -m pytest tests/test_usage_endpoints.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/usage.py app/api/router.py tests/test_usage_endpoints.py
git commit -m "feat(usage): add POST /usage/events client endpoint"
```

---

### Task A5: Aggregator — `aggregate_day` + `cleanup_old_events`

**Files:**
- Modify: `app/services/usage_service.py`
- Modify: `tests/test_usage_service.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_usage_service.py`:

```python
import json
from datetime import date

from app.models import UsageDaily


def test_aggregate_day_groups_views_seconds_actions(db_session, user):
    svc = UsageService(db_session)
    target = datetime(2026, 5, 27, 10, 0, 0)
    svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": target},
        {"event_type": "heartbeat", "path": "/dashboard", "at": target},
        {"event_type": "heartbeat", "path": "/dashboard", "at": target},
        {"event_type": "action", "action_type": "sync_started",
         "path": "/sync", "at": target},
    ])
    # bypass time-skew validation by writing directly
    for ev in db_session.query(UsageEvent).all():
        ev.at = target
    db_session.commit()

    svc.aggregate_day(date(2026, 5, 27))
    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 2  # /dashboard и /sync
    dash = next(r for r in rows if r.path == "/dashboard")
    assert dash.views == 1
    assert dash.seconds == 60  # 2 heartbeats × 30s
    sync = next(r for r in rows if r.path == "/sync")
    assert json.loads(sync.actions_json) == {"sync_started": 1}


def test_aggregate_day_idempotent(db_session, user):
    svc = UsageService(db_session)
    target = datetime(2026, 5, 27, 10, 0, 0)
    svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": target},
    ])
    for ev in db_session.query(UsageEvent).all():
        ev.at = target
    db_session.commit()

    svc.aggregate_day(date(2026, 5, 27))
    svc.aggregate_day(date(2026, 5, 27))
    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 1
    assert rows[0].views == 1


def test_cleanup_old_events_deletes_past_retention(db_session, user):
    svc = UsageService(db_session)
    old = datetime.utcnow() - timedelta(days=100)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=old,
    ))
    recent = datetime.utcnow() - timedelta(days=30)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=recent,
    ))
    db_session.commit()

    deleted = svc.cleanup_old_events(retention_days=90)
    assert deleted == 1
    assert db_session.query(UsageEvent).count() == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: AttributeError on `aggregate_day`, `cleanup_old_events`.

- [ ] **Step 3: Implement methods**

Add at the top of `app/services/usage_service.py` (next to existing imports):

```python
import json
from collections import defaultdict
from datetime import date as date_type

from app.models import UsageDaily


HEARTBEAT_SECONDS = 30
```

Then append the methods below INSIDE the existing `UsageService` class (do not create a second class):

```python
    def aggregate_day(self, target: date_type) -> int:
        """Свернуть raw события за `target` в usage_daily. Идемпотентно."""
        from datetime import datetime as _dt
        day_start = _dt.combine(target, _dt.min.time())
        day_end = day_start + timedelta(days=1)

        events = (
            self.db.query(UsageEvent)
            .filter(UsageEvent.at >= day_start, UsageEvent.at < day_end)
            .all()
        )
        # group by (user_id, path)
        buckets: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"views": 0, "seconds": 0, "actions": defaultdict(int)}
        )
        for ev in events:
            b = buckets[(ev.user_id, ev.path)]
            if ev.event_type == UsageEventType.page_view:
                b["views"] += 1
            elif ev.event_type == UsageEventType.heartbeat:
                b["seconds"] += HEARTBEAT_SECONDS
            elif ev.event_type == UsageEventType.action and ev.action_type:
                b["actions"][ev.action_type] += 1

        upserted = 0
        for (user_id, path), agg in buckets.items():
            existing = (
                self.db.query(UsageDaily)
                .filter_by(date=target, user_id=user_id, path=path)
                .one_or_none()
            )
            actions_json = json.dumps(dict(agg["actions"]))
            if existing is None:
                self.db.add(UsageDaily(
                    date=target, user_id=user_id, path=path,
                    views=agg["views"], seconds=agg["seconds"],
                    actions_json=actions_json,
                ))
            else:
                existing.views = agg["views"]
                existing.seconds = agg["seconds"]
                existing.actions_json = actions_json
            upserted += 1
        self.db.commit()
        return upserted

    def cleanup_old_events(self, retention_days: int = 90) -> int:
        from datetime import datetime as _dt
        cutoff = _dt.utcnow() - timedelta(days=retention_days)
        deleted = (
            self.db.query(UsageEvent)
            .filter(UsageEvent.at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
```

> NOTE: remove the placeholder `class UsageService(UsageService): pass` block — the methods above should be appended INSIDE the original class body.

- [ ] **Step 4: Run tests — expect PASS**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/usage_service.py tests/test_usage_service.py
git commit -m "feat(usage): aggregate_day + cleanup_old_events"
```

---

### Task A6: Cron job wiring

**Files:**
- Create: `app/jobs/aggregate_usage.py`
- Modify: `app/main.py`
- Create: `tests/test_aggregate_usage_job.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aggregate_usage_job.py
"""Cron-job entry: свернуть вчерашний день и подчистить старые события."""
from datetime import date, datetime, timedelta

from app.jobs.aggregate_usage import aggregate_usage_job
from app.models import UsageDaily, UsageEvent, UsageEventType


def test_aggregate_usage_job_processes_yesterday(db_session, user):
    yesterday = datetime.utcnow() - timedelta(days=1)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=yesterday,
    ))
    db_session.commit()

    aggregate_usage_job(_session_factory=lambda: db_session)

    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 1
    assert rows[0].date == yesterday.date()
```

(`user` fixture reused — declare it via `from tests.test_usage_service import user` or duplicate the fixture.)

- [ ] **Step 2: Run — expect FAIL**

```bash
py -3.10 -m pytest tests/test_aggregate_usage_job.py -v
```
Expected: ImportError on `aggregate_usage_job`.

- [ ] **Step 3: Implement job**

```python
# app/jobs/aggregate_usage.py
"""Cron-job: ежедневно агрегировать usage_events и удалять старые."""
import logging
from datetime import datetime, timedelta
from typing import Callable

from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)


def aggregate_usage_job(
    *, _session_factory: Callable | None = None, retention_days: int = 90,
) -> None:
    """Свернуть вчерашний день в usage_daily, удалить события старше retention."""
    if _session_factory is None:
        from app.database import SessionLocal
        _session_factory = SessionLocal

    db = _session_factory()
    try:
        svc = UsageService(db)
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()
        upserted = svc.aggregate_day(yesterday)
        deleted = svc.cleanup_old_events(retention_days=retention_days)
        logger.info(
            "aggregate_usage_job: upserted=%d daily rows, deleted=%d old events",
            upserted, deleted,
        )
    finally:
        db.close()
```

- [ ] **Step 4: Wire into `app/main.py` lifespan**

After the `regenerate_summaries` job (around line 54), add:

```python
    from app.jobs.aggregate_usage import aggregate_usage_job
    sched_svc.scheduler.add_job(
        aggregate_usage_job,
        trigger=CronTrigger(hour=3, minute=10),
        id="aggregate_usage",
        replace_existing=True,
        max_instances=1,
    )
```

- [ ] **Step 5: Run job test — expect PASS**

```bash
py -3.10 -m pytest tests/test_aggregate_usage_job.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add app/jobs/aggregate_usage.py app/main.py tests/test_aggregate_usage_job.py
git commit -m "feat(usage): daily aggregate+cleanup cron job"
```

---

### Task A7: Admin query methods

**Files:**
- Modify: `app/services/usage_service.py`
- Modify: `tests/test_usage_service.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_usage_service.py`:

```python
from datetime import date as date_type


def _seed_daily(db_session, user, day, path, views=0, seconds=0, actions=None):
    db_session.add(UsageDaily(
        date=day, user_id=user.id, path=path,
        views=views, seconds=seconds,
        actions_json=json.dumps(actions or {}),
    ))
    db_session.commit()


def test_query_overview_counts_dau_wau_mau(db_session, user):
    today = date_type.today()
    _seed_daily(db_session, user, today, "/dashboard", views=1, seconds=3600)
    svc = UsageService(db_session)
    out = svc.query_overview()
    assert out["dau"] >= 1
    assert out["wau"] >= 1
    assert out["mau"] >= 1
    assert out["hours_30d"] >= 1.0


def test_query_pages_aggregates_by_path(db_session, user):
    today = date_type.today()
    _seed_daily(db_session, user, today, "/dashboard", views=3, seconds=1800)
    svc = UsageService(db_session)
    rows = svc.query_pages(days=30)
    by_path = {r["path"]: r for r in rows}
    assert by_path["/dashboard"]["views"] == 3
    assert by_path["/dashboard"]["unique_users"] == 1
    assert by_path["/dashboard"]["hours"] == 0.5
```

- [ ] **Step 2: Run — expect FAIL**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: AttributeError на `query_overview`, `query_pages`.

- [ ] **Step 3: Implement query methods**

Append inside `UsageService`:

```python
    def _period(self, days: int) -> tuple[date_type, date_type]:
        end = date_type.today()
        start = end - timedelta(days=days - 1)
        return start, end

    def query_overview(self) -> dict:
        today = date_type.today()
        wk = today - timedelta(days=6)
        mo = today - timedelta(days=29)

        def _unique(since):
            return (
                self.db.query(UsageDaily.user_id)
                .filter(UsageDaily.date >= since)
                .distinct().count()
            )

        from sqlalchemy import func as sqlfn
        secs_30d = (
            self.db.query(sqlfn.coalesce(sqlfn.sum(UsageDaily.seconds), 0))
            .filter(UsageDaily.date >= mo)
            .scalar() or 0
        )
        return {
            "dau": _unique(today),
            "wau": _unique(wk),
            "mau": _unique(mo),
            "hours_30d": round(secs_30d / 3600, 1),
        }

    def query_users(self, days: int = 30) -> list[dict]:
        from sqlalchemy import func as sqlfn
        from app.models import User
        start, _ = self._period(days)
        rows = (
            self.db.query(
                User.id, User.display_name, User.role,
                sqlfn.count(sqlfn.distinct(UsageDaily.date)).label("active_days"),
                sqlfn.coalesce(sqlfn.sum(UsageDaily.seconds), 0).label("secs"),
                sqlfn.max(UsageDaily.date).label("last_date"),
            )
            .outerjoin(UsageDaily,
                       (UsageDaily.user_id == User.id) & (UsageDaily.date >= start))
            .group_by(User.id)
            .all()
        )
        out = []
        for r in rows:
            # top path for this user in window
            top = (
                self.db.query(UsageDaily.path)
                .filter(UsageDaily.user_id == r.id, UsageDaily.date >= start)
                .group_by(UsageDaily.path)
                .order_by(sqlfn.sum(UsageDaily.seconds).desc())
                .first()
            )
            out.append({
                "user_id": r.id,
                "display_name": r.display_name,
                "role": r.role.value if hasattr(r.role, "value") else r.role,
                "last_seen": r.last_date,
                "active_days": int(r.active_days or 0),
                "hours": round((r.secs or 0) / 3600, 1),
                "top_path": top[0] if top else None,
            })
        return out

    def query_pages(self, days: int = 30) -> list[dict]:
        from sqlalchemy import func as sqlfn
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageDaily.path,
                sqlfn.count(sqlfn.distinct(UsageDaily.user_id)).label("uu"),
                sqlfn.sum(UsageDaily.views).label("views"),
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.path)
            .all()
        )
        return [{
            "path": r.path,
            "unique_users": int(r.uu or 0),
            "views": int(r.views or 0),
            "hours": round((r.secs or 0) / 3600, 1),
        } for r in rows]

    def query_matrix(self, days: int = 30, top_n: int = 10) -> dict:
        from sqlalchemy import func as sqlfn
        from app.models import User
        start, _ = self._period(days)

        # топ-N юзеров по часам
        top_users = (
            self.db.query(UsageDaily.user_id, sqlfn.sum(UsageDaily.seconds).label("s"))
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.user_id)
            .order_by(sqlfn.sum(UsageDaily.seconds).desc())
            .limit(top_n).all()
        )
        user_ids = [u[0] for u in top_users]

        top_paths = (
            self.db.query(UsageDaily.path, sqlfn.sum(UsageDaily.seconds).label("s"))
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.path)
            .order_by(sqlfn.sum(UsageDaily.seconds).desc())
            .limit(top_n).all()
        )
        paths = [p[0] for p in top_paths]

        users_meta = {
            u.id: u.display_name for u in
            self.db.query(User).filter(User.id.in_(user_ids)).all()
        }

        cells_rows = (
            self.db.query(
                UsageDaily.user_id, UsageDaily.path,
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(
                UsageDaily.date >= start,
                UsageDaily.user_id.in_(user_ids),
                UsageDaily.path.in_(paths),
            )
            .group_by(UsageDaily.user_id, UsageDaily.path)
            .all()
        )
        return {
            "users": [{"user_id": uid, "display_name": users_meta.get(uid, uid)}
                      for uid in user_ids],
            "paths": [{"path": p} for p in paths],
            "cells": [{
                "user_id": r.user_id, "path": r.path,
                "display_name": users_meta.get(r.user_id, r.user_id),
                "hours": round((r.secs or 0) / 3600, 1),
            } for r in cells_rows],
        }

    def query_timeline(self, days: int = 30) -> list[dict]:
        from sqlalchemy import func as sqlfn
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageDaily.date,
                sqlfn.sum(UsageDaily.views).label("views"),
                sqlfn.sum(UsageDaily.seconds).label("secs"),
                sqlfn.count(sqlfn.distinct(UsageDaily.user_id)).label("uu"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.date)
            .order_by(UsageDaily.date)
            .all()
        )
        return [{
            "date": r.date,
            "views": int(r.views or 0),
            "seconds": int(r.secs or 0),
            "active_users": int(r.uu or 0),
        } for r in rows]

    def query_actions(self, days: int = 30) -> list[dict]:
        from sqlalchemy import func as sqlfn
        from app.models import User
        start, _ = self._period(days)
        # actions live inside actions_json — easier to scan via usage_events for raw window
        # but usage_events keeps only 90 days, so for >90d window we'd need to scan daily JSON.
        # For MVP: scan usage_events table (covers up to 90 days).
        from app.models import UsageEvent
        rows = (
            self.db.query(
                UsageEvent.action_type, UsageEvent.user_id,
                sqlfn.count().label("c"),
            )
            .filter(
                UsageEvent.event_type == UsageEventType.action,
                UsageEvent.at >= datetime.combine(start, datetime.min.time()),
            )
            .group_by(UsageEvent.action_type, UsageEvent.user_id)
            .all()
        )
        # roll up
        agg: dict[str, dict] = defaultdict(lambda: {"total": 0, "by_user": defaultdict(int)})
        for r in rows:
            agg[r.action_type]["total"] += r.c
            agg[r.action_type]["by_user"][r.user_id] += r.c

        user_names = {u.id: u.display_name for u in self.db.query(User).all()}
        out = []
        for action_type, data in agg.items():
            top = sorted(data["by_user"].items(), key=lambda kv: -kv[1])[:3]
            out.append({
                "action_type": action_type,
                "total": data["total"],
                "top_users": [
                    {"user_id": uid, "display_name": user_names.get(uid, uid),
                     "count": cnt}
                    for uid, cnt in top
                ],
            })
        out.sort(key=lambda r: -r["total"])
        return out
```

- [ ] **Step 4: Run — expect PASS**

```bash
py -3.10 -m pytest tests/test_usage_service.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/usage_service.py tests/test_usage_service.py
git commit -m "feat(usage): admin query methods (overview/users/pages/matrix/timeline/actions)"
```

---

### Task A8: Admin query endpoints

**Files:**
- Create: `app/api/endpoints/admin_usage.py`
- Create: `tests/test_admin_usage_endpoints.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_admin_usage_endpoints.py
"""Admin /admin/usage/* эндпоинты — только админам."""
import json
from datetime import date as date_type

from app.models import UsageDaily


def test_overview_admin_only(authed_client):
    # обычный manager — 403
    r = authed_client.get("/api/v1/admin/usage/overview")
    assert r.status_code == 403


def test_overview_admin_ok(admin_client, db_session, admin_user):
    db_session.add(UsageDaily(
        date=date_type.today(), user_id=admin_user.id,
        path="/dashboard", views=1, seconds=3600, actions_json="{}",
    ))
    db_session.commit()
    r = admin_client.get("/api/v1/admin/usage/overview")
    assert r.status_code == 200
    body = r.json()
    assert {"dau", "wau", "mau", "hours_30d"} <= set(body.keys())


def test_users_endpoint(admin_client):
    r = admin_client.get("/api/v1/admin/usage/users?days=30")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_pages_endpoint(admin_client):
    r = admin_client.get("/api/v1/admin/usage/pages?days=30")
    assert r.status_code == 200


def test_matrix_endpoint(admin_client):
    r = admin_client.get("/api/v1/admin/usage/matrix?days=30")
    assert r.status_code == 200
    body = r.json()
    assert {"users", "paths", "cells"} <= set(body.keys())


def test_timeline_endpoint(admin_client):
    r = admin_client.get("/api/v1/admin/usage/timeline?days=30")
    assert r.status_code == 200


def test_actions_endpoint(admin_client):
    r = admin_client.get("/api/v1/admin/usage/actions?days=30")
    assert r.status_code == 200
```

> If `admin_client` / `admin_user` fixtures don't exist yet, add them to `tests/conftest.py` mirroring `authed_client` but with `role=UserRole.admin`. Check existing conftest first — likely already there for hierarchy_rules admin tests.

- [ ] **Step 2: Run — expect FAIL**

```bash
py -3.10 -m pytest tests/test_admin_usage_endpoints.py -v
```
Expected: 404.

- [ ] **Step 3: Implement endpoints**

```python
# app/api/endpoints/admin_usage.py
"""Admin-only endpoints для usage аналитики."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.usage_service import UsageService

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return UsageService(db).query_overview()


@router.get("/users")
def users(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_users(days=days)


@router.get("/pages")
def pages(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_pages(days=days)


@router.get("/matrix")
def matrix(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> dict:
    return UsageService(db).query_matrix(days=days)


@router.get("/timeline")
def timeline(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_timeline(days=days)


@router.get("/actions")
def actions(days: int = Query(30, ge=1, le=90), db: Session = Depends(get_db)) -> list[dict]:
    return UsageService(db).query_actions(days=days)
```

- [ ] **Step 4: Register in `app/api/router.py`**

Add to imports:
```python
from app.api.endpoints import admin_usage as admin_usage_endpoints
```

Add after `hierarchy_rules` admin include:
```python
api_router.include_router(
    admin_usage_endpoints.router,
    prefix="/admin/usage",
    tags=["admin-usage"],
    dependencies=_admin_dep,
)
```

- [ ] **Step 5: Run — expect PASS**

```bash
py -3.10 -m pytest tests/test_admin_usage_endpoints.py -v
```
Expected: all passed.

- [ ] **Step 6: Run full backend suite**

```bash
py -3.10 -m pytest tests/ -v -x
```
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add app/api/endpoints/admin_usage.py app/api/router.py tests/test_admin_usage_endpoints.py
git commit -m "feat(usage): admin /admin/usage/* query endpoints"
```

---

## Phase B — Frontend Tracker

### Task B1: Path normalization

**Files:**
- Create: `frontend/src/lib/usage/routeTable.ts`
- Create: `frontend/src/lib/usage/normalizePath.ts`
- Create: `frontend/src/lib/usage/__tests__/normalizePath.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/usage/__tests__/normalizePath.test.ts
import { describe, expect, it } from "vitest";
import { normalizePath } from "../normalizePath";

describe("normalizePath", () => {
  it("returns known path unchanged", () => {
    expect(normalizePath("/dashboard")).toBe("/dashboard");
  });

  it("replaces project key segment", () => {
    expect(normalizePath("/projects/PROJ-123")).toBe("/projects/:key");
  });

  it("replaces uuid id segment in scenarios", () => {
    expect(normalizePath("/scenarios/abc-def-uuid/edit")).toBe("/scenarios/:id/edit");
  });

  it("strips query string", () => {
    expect(normalizePath("/dashboard?team=foo")).toBe("/dashboard");
  });

  it("returns null for unknown path", () => {
    expect(normalizePath("/nonsense/route")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd frontend && npm test -- normalizePath
```

- [ ] **Step 3: Implement**

```typescript
// frontend/src/lib/usage/routeTable.ts
export const KNOWN_ROUTES: string[] = [
  "/dashboard",
  "/analytics",
  "/projects",
  "/projects/:key",
  "/sync",
  "/categories",
  "/category-config",
  "/capacity",
  "/backlog",
  "/planning",
  "/scenarios/:id",
  "/scenarios/:id/edit",
  "/resource-planning",
  "/executive",
  "/themes",
  "/work-type-report",
  "/feedback",
  "/settings",
  "/login",
];
```

```typescript
// frontend/src/lib/usage/normalizePath.ts
import { KNOWN_ROUTES } from "./routeTable";

const ROUTE_PATTERNS: { regex: RegExp; route: string }[] = KNOWN_ROUTES.map((route) => {
  const pattern = route
    .replace(/:[a-z]+/gi, "([^/]+)")
    .replace(/\//g, "\\/");
  return { regex: new RegExp(`^${pattern}$`), route };
});

export function normalizePath(rawPath: string): string | null {
  const path = rawPath.split("?")[0].replace(/\/+$/, "") || "/";
  for (const { regex, route } of ROUTE_PATTERNS) {
    if (regex.test(path)) return route;
  }
  return null;
}
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd frontend && npm test -- normalizePath
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/usage/routeTable.ts frontend/src/lib/usage/normalizePath.ts frontend/src/lib/usage/__tests__/normalizePath.test.ts
git commit -m "feat(usage): path normalization + route table"
```

---

### Task B2: UsageSender

**Files:**
- Create: `frontend/src/lib/usage/sender.ts`
- Create: `frontend/src/lib/usage/__tests__/sender.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/usage/__tests__/sender.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UsageSender } from "../sender";

describe("UsageSender", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ accepted: 1, rejected: 0 }) });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("buffers events and flushes on demand", async () => {
    const s = new UsageSender({ endpoint: "/api/v1/usage/events", flushIntervalMs: 0 });
    s.enqueue({ event_type: "page_view", path: "/dashboard", at: new Date().toISOString() });
    await s.flushNow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.events).toHaveLength(1);
  });

  it("drops events when buffer exceeds capacity", () => {
    const s = new UsageSender({ endpoint: "/x", flushIntervalMs: 0, capacity: 2 });
    s.enqueue({ event_type: "page_view", path: "/dashboard", at: "now" });
    s.enqueue({ event_type: "page_view", path: "/dashboard", at: "now" });
    s.enqueue({ event_type: "page_view", path: "/dashboard", at: "now" });
    expect(s.bufferSize()).toBe(2);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd frontend && npm test -- sender
```

- [ ] **Step 3: Implement**

```typescript
// frontend/src/lib/usage/sender.ts
export interface UsageEvent {
  event_type: "page_view" | "heartbeat" | "action";
  path: string;
  action_type?: string;
  entity_id?: string;
  at: string;
}

interface UsageSenderOpts {
  endpoint: string;
  flushIntervalMs: number;
  capacity?: number;
}

const DEFAULT_CAPACITY = 100;

export class UsageSender {
  private buffer: UsageEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private opts: Required<UsageSenderOpts>;

  constructor(opts: UsageSenderOpts) {
    this.opts = { capacity: DEFAULT_CAPACITY, ...opts };
    if (opts.flushIntervalMs > 0) {
      this.timer = setInterval(() => void this.flushNow(), opts.flushIntervalMs);
    }
  }

  enqueue(ev: UsageEvent): void {
    if (this.buffer.length >= this.opts.capacity) return;
    this.buffer.push(ev);
    if (this.buffer.length >= this.opts.capacity) void this.flushNow();
  }

  bufferSize(): number {
    return this.buffer.length;
  }

  async flushNow(): Promise<void> {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0, this.buffer.length);
    try {
      await fetch(this.opts.endpoint, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: batch }),
        keepalive: true,
      });
    } catch {
      // fire-and-forget; drop on failure
    }
  }

  flushBeacon(): void {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0, this.buffer.length);
    const body = new Blob(
      [JSON.stringify({ events: batch })],
      { type: "application/json" },
    );
    navigator.sendBeacon?.(this.opts.endpoint, body);
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

// Singleton — стартует один раз, использует cookie auth.
export const usageSender = new UsageSender({
  endpoint: `${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/usage/events`,
  flushIntervalMs: 30_000,
});

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => usageSender.flushBeacon());
}
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd frontend && npm test -- sender
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/usage/sender.ts frontend/src/lib/usage/__tests__/sender.test.ts
git commit -m "feat(usage): UsageSender with buffer + sendBeacon"
```

---

### Task B3: trackAction helper + hooks

**Files:**
- Create: `frontend/src/lib/usage/track.ts`
- Create: `frontend/src/lib/usage/usePageView.ts`
- Create: `frontend/src/lib/usage/useHeartbeat.ts`

- [ ] **Step 1: Implement `track.ts`**

```typescript
// frontend/src/lib/usage/track.ts
import { normalizePath } from "./normalizePath";
import { usageSender } from "./sender";

export function trackAction(actionType: string, entityId?: string): void {
  const path = normalizePath(window.location.pathname) ?? "/";
  usageSender.enqueue({
    event_type: "action",
    action_type: actionType,
    entity_id: entityId,
    path,
    at: new Date().toISOString(),
  });
}
```

- [ ] **Step 2: Implement `usePageView.ts`**

```typescript
// frontend/src/lib/usage/usePageView.ts
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { normalizePath } from "./normalizePath";
import { usageSender } from "./sender";

export function usePageView(): void {
  const location = useLocation();
  useEffect(() => {
    const path = normalizePath(location.pathname);
    if (!path) return;
    usageSender.enqueue({
      event_type: "page_view",
      path,
      at: new Date().toISOString(),
    });
  }, [location.pathname]);
}
```

- [ ] **Step 3: Implement `useHeartbeat.ts`**

```typescript
// frontend/src/lib/usage/useHeartbeat.ts
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { normalizePath } from "./normalizePath";
import { usageSender } from "./sender";

const HEARTBEAT_INTERVAL_MS = 30_000;

export function useHeartbeat(): void {
  const location = useLocation();
  useEffect(() => {
    const path = normalizePath(location.pathname);
    if (!path) return;

    const tick = () => {
      if (document.visibilityState !== "visible") return;
      usageSender.enqueue({
        event_type: "heartbeat",
        path,
        at: new Date().toISOString(),
      });
    };

    const id = setInterval(tick, HEARTBEAT_INTERVAL_MS);
    return () => clearInterval(id);
  }, [location.pathname]);
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/usage/track.ts frontend/src/lib/usage/usePageView.ts frontend/src/lib/usage/useHeartbeat.ts
git commit -m "feat(usage): trackAction + usePageView + useHeartbeat hooks"
```

---

### Task B4: Wire tracker into App

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Identify mount point**

Open `frontend/src/App.tsx`. Find the authenticated layout (where routes render after auth). Tracker must run only after auth so events carry the session cookie.

- [ ] **Step 2: Add component**

In `frontend/src/App.tsx`, define and mount a small component inside the authenticated subtree:

```tsx
import { usePageView } from "./lib/usage/usePageView";
import { useHeartbeat } from "./lib/usage/useHeartbeat";

function UsageTracker() {
  usePageView();
  useHeartbeat();
  return null;
}
```

Render `<UsageTracker />` inside the authenticated layout (next to `<Outlet />` or equivalent — wherever the protected routes render).

- [ ] **Step 3: Manual smoke**

```bash
cd frontend && npm run dev
```

Open the app, log in, navigate two pages. In DevTools Network tab confirm `POST /api/v1/usage/events` fires ~every 30s while the tab is visible, stops when switched away.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(usage): mount UsageTracker after auth"
```

---

### Task B5: Wire trackAction at action sites

**Files:** see "Frontend modify" — every page/component that triggers a tracked action.

- [ ] **Step 1: Add `trackAction` calls**

For each site below, import `trackAction` and call it on success of the relevant handler:

| Page/Component | Event handler | Call |
|---|---|---|
| `LoginPage.tsx` | onLogin success | `trackAction('login')` |
| `AuthLayout.tsx` (or logout) | onLogout | `trackAction('logout')` |
| `SyncPage.tsx` | start sync button | `trackAction('sync_started')` |
| `SyncPage.tsx` | cancel sync | `trackAction('sync_cancelled')` |
| `PlanningPage.tsx` (or scenarios) | create scenario success | `trackAction('scenario_created', scenarioId)` |
| same | approve scenario | `trackAction('scenario_approved', scenarioId)` |
| same | xlsx export | `trackAction('scenario_xlsx_exported', scenarioId)` |
| `ProjectsPage.tsx` | AI-summary request | `trackAction('ai_summary_requested', projectKey)` |
| same | AI refresh button | `trackAction('ai_summary_refreshed', projectKey)` |
| `FeedbackDrawer.tsx` | submit success | `trackAction('feedback_submitted')` |
| `ResourcePlanningPage.tsx` | PATCH/drag commit | `trackAction('resource_plan_edited')` |
| `ThemeReportPage.tsx` | merge themes | `trackAction('theme_merged')` |
| `CategoryPicker.tsx` (or equiv) | change category | `trackAction('category_changed')` |

If you can't find the exact file, grep for the user-visible action label first; don't insert blindly.

- [ ] **Step 2: Manual smoke**

Perform each action once and confirm in Network that a `POST /usage/events` carries an `event_type: "action"` with the right `action_type`.

- [ ] **Step 3: Commit (one cohesive commit)**

```bash
git add -A frontend/src/
git commit -m "feat(usage): trackAction at action sites (login/sync/scenarios/ai/...)"
```

---

## Phase C — Admin UI

### Task C1: Admin API client

**Files:**
- Create: `frontend/src/api/usage.ts`

- [ ] **Step 1: Implement**

```typescript
// frontend/src/api/usage.ts
import { apiClient } from "./client";

export interface UsageOverview {
  dau: number; wau: number; mau: number; hours_30d: number;
}
export interface UsageUserRow {
  user_id: string; display_name: string; role: string;
  last_seen: string | null; active_days: number; hours: number;
  top_path: string | null;
}
export interface UsagePageRow {
  path: string; unique_users: number; views: number; hours: number;
}
export interface UsageMatrix {
  users: { user_id: string; display_name: string }[];
  paths: { path: string }[];
  cells: { user_id: string; path: string; display_name: string; hours: number }[];
}
export interface UsageTimelinePoint {
  date: string; views: number; seconds: number; active_users: number;
}
export interface UsageActionRow {
  action_type: string; total: number;
  top_users: { user_id: string; display_name: string; count: number }[];
}

export const usageApi = {
  overview: () => apiClient.get<UsageOverview>("/admin/usage/overview"),
  users: (days: number) => apiClient.get<UsageUserRow[]>(`/admin/usage/users?days=${days}`),
  pages: (days: number) => apiClient.get<UsagePageRow[]>(`/admin/usage/pages?days=${days}`),
  matrix: (days: number) => apiClient.get<UsageMatrix>(`/admin/usage/matrix?days=${days}`),
  timeline: (days: number) => apiClient.get<UsageTimelinePoint[]>(`/admin/usage/timeline?days=${days}`),
  actions: (days: number) => apiClient.get<UsageActionRow[]>(`/admin/usage/actions?days=${days}`),
};
```

> If `apiClient.get` uses different shape (e.g. axios), match the existing pattern from `frontend/src/api/feedback.ts`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/usage.ts
git commit -m "feat(usage): admin API client"
```

---

### Task C2: pathLabels + KPI bar + UsersTable + PagesTable

**Files:**
- Create: `frontend/src/components/admin/usage/pathLabels.ts`
- Create: `frontend/src/components/admin/usage/UsageKpiBar.tsx`
- Create: `frontend/src/components/admin/usage/UsageUsersTable.tsx`
- Create: `frontend/src/components/admin/usage/UsagePagesTable.tsx`

- [ ] **Step 1: pathLabels**

```typescript
// frontend/src/components/admin/usage/pathLabels.ts
export const PATH_LABELS: Record<string, string> = {
  "/dashboard": "Дашборд",
  "/analytics": "Аналитика",
  "/projects": "Проекты",
  "/projects/:key": "Карточка проекта",
  "/sync": "Синхронизация",
  "/categories": "Категории",
  "/category-config": "Настройка категорий",
  "/capacity": "Загрузка",
  "/backlog": "Бэклог",
  "/planning": "Планирование",
  "/scenarios/:id": "Сценарий",
  "/scenarios/:id/edit": "Редактор сценария",
  "/resource-planning": "Планирование ресурсов",
  "/executive": "Сводка для руководства",
  "/themes": "Темы",
  "/work-type-report": "Отчёт по видам работ",
  "/feedback": "Обратная связь",
  "/settings": "Настройки",
  "/login": "Логин",
};

export const pathLabel = (path: string): string => PATH_LABELS[path] ?? path;
```

- [ ] **Step 2: UsageKpiBar**

```tsx
// frontend/src/components/admin/usage/UsageKpiBar.tsx
import { Card, Col, Row, Statistic } from "antd";
import { useQuery } from "@tanstack/react-query";
import { usageApi } from "../../../api/usage";

export function UsageKpiBar() {
  const { data, isLoading } = useQuery({
    queryKey: ["usage", "overview"],
    queryFn: usageApi.overview,
  });
  return (
    <Row gutter={16}>
      <Col span={6}><Card loading={isLoading}><Statistic title="Активных сегодня" value={data?.dau ?? 0} /></Card></Col>
      <Col span={6}><Card loading={isLoading}><Statistic title="За неделю" value={data?.wau ?? 0} /></Card></Col>
      <Col span={6}><Card loading={isLoading}><Statistic title="За 30 дней" value={data?.mau ?? 0} /></Card></Col>
      <Col span={6}><Card loading={isLoading}><Statistic title="Часов за 30 дней" value={data?.hours_30d ?? 0} precision={1} /></Card></Col>
    </Row>
  );
}
```

- [ ] **Step 3: UsageUsersTable**

```tsx
// frontend/src/components/admin/usage/UsageUsersTable.tsx
import { Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { usageApi, type UsageUserRow } from "../../../api/usage";
import { pathLabel } from "./pathLabels";

interface Props { days: number }

export function UsageUsersTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["usage", "users", days],
    queryFn: () => usageApi.users(days),
  });
  const columns = [
    { title: "Пользователь", dataIndex: "display_name" },
    { title: "Роль", dataIndex: "role", render: (r: string) => <Tag>{r}</Tag> },
    {
      title: "Последний вход", dataIndex: "last_seen",
      render: (d: string | null) => d ? new Date(d).toLocaleDateString("ru-RU") : "—",
    },
    { title: "Активных дней", dataIndex: "active_days" },
    { title: "Часов", dataIndex: "hours", render: (h: number) => h.toFixed(1) },
    {
      title: "Самый частый раздел", dataIndex: "top_path",
      render: (p: string | null) => p ? pathLabel(p) : "—",
    },
  ];
  return <Table<UsageUserRow> rowKey="user_id" loading={isLoading} dataSource={data} columns={columns} pagination={{ pageSize: 20 }} />;
}
```

- [ ] **Step 4: UsagePagesTable**

```tsx
// frontend/src/components/admin/usage/UsagePagesTable.tsx
import { Table } from "antd";
import { useQuery } from "@tanstack/react-query";
import { usageApi, type UsagePageRow } from "../../../api/usage";
import { pathLabel } from "./pathLabels";

interface Props { days: number }

export function UsagePagesTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["usage", "pages", days],
    queryFn: () => usageApi.pages(days),
  });
  const columns = [
    { title: "Раздел", dataIndex: "path", render: (p: string) => pathLabel(p) },
    { title: "Уник. пользователей", dataIndex: "unique_users", sorter: (a: UsagePageRow, b: UsagePageRow) => a.unique_users - b.unique_users },
    { title: "Заходов", dataIndex: "views", sorter: (a: UsagePageRow, b: UsagePageRow) => a.views - b.views },
    { title: "Часов", dataIndex: "hours", render: (h: number) => h.toFixed(1), sorter: (a: UsagePageRow, b: UsagePageRow) => a.hours - b.hours, defaultSortOrder: "descend" as const },
  ];
  return <Table<UsagePageRow> rowKey="path" loading={isLoading} dataSource={data} columns={columns} pagination={false} />;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin/usage/
git commit -m "feat(usage): KPI bar + users table + pages table"
```

---

### Task C3: Matrix + Timeline + ActionsTable + UsageTab

**Files:**
- Create: `frontend/src/components/admin/usage/UsageMatrix.tsx`
- Create: `frontend/src/components/admin/usage/UsageTimeline.tsx`
- Create: `frontend/src/components/admin/usage/UsageActionsTable.tsx`
- Create: `frontend/src/components/admin/usage/UsageTab.tsx`

- [ ] **Step 1: UsageMatrix (heatmap as table with cell tint)**

```tsx
// frontend/src/components/admin/usage/UsageMatrix.tsx
import { useMemo } from "react";
import { Empty, Table, Tooltip } from "antd";
import { useQuery } from "@tanstack/react-query";
import { usageApi } from "../../../api/usage";
import { pathLabel } from "./pathLabels";

interface Props { days: number }

export function UsageMatrix({ days }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["usage", "matrix", days],
    queryFn: () => usageApi.matrix(days),
  });
  const max = useMemo(() => {
    if (!data) return 0;
    return data.cells.reduce((m, c) => Math.max(m, c.hours), 0);
  }, [data]);

  if (!data || (data.users.length === 0)) {
    return <Empty description="Нет данных за период" />;
  }

  const tint = (h: number) => {
    if (h === 0 || max === 0) return undefined;
    const alpha = Math.min(1, h / max);
    return { background: `rgba(24, 144, 255, ${alpha.toFixed(2)})` };
  };

  const cellMap = new Map<string, number>();
  for (const c of data.cells) cellMap.set(`${c.user_id}|${c.path}`, c.hours);

  const columns = [
    { title: "Пользователь", dataIndex: "display_name", fixed: "left" as const, width: 180 },
    ...data.paths.map((p) => ({
      title: pathLabel(p.path),
      key: p.path,
      align: "right" as const,
      render: (_: unknown, row: { user_id: string }) => {
        const h = cellMap.get(`${row.user_id}|${p.path}`) ?? 0;
        return <div style={tint(h)}><Tooltip title={`${h.toFixed(1)} ч`}>{h > 0 ? h.toFixed(1) : ""}</Tooltip></div>;
      },
    })),
  ];

  return (
    <Table
      rowKey="user_id"
      loading={isLoading}
      dataSource={data.users}
      columns={columns}
      pagination={false}
      scroll={{ x: true }}
      size="small"
    />
  );
}
```

- [ ] **Step 2: UsageTimeline (simple AntD Line chart from @ant-design/plots or recharts — pick whichever is already in deps)**

First grep `frontend/package.json` for `recharts` or `@ant-design/plots`. Use whichever is present. If neither, render as a sortable AntD `Table` for MVP — graph polish is non-blocking.

```tsx
// frontend/src/components/admin/usage/UsageTimeline.tsx
import { Card, Empty } from "antd";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from "recharts";
import { usageApi } from "../../../api/usage";

interface Props { days: number }

export function UsageTimeline({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["usage", "timeline", days],
    queryFn: () => usageApi.timeline(days),
  });
  if (!isLoading && data.length === 0) return <Empty description="Нет данных" />;
  return (
    <Card loading={isLoading} title="Динамика">
      <div style={{ height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="views" name="Заходов" stroke="#1890ff" />
            <Line type="monotone" dataKey="active_users" name="Активных" stroke="#52c41a" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

> If recharts isn't installed, swap to a plain table (date / views / active_users) and note in PR description that graph polish is deferred.

- [ ] **Step 3: UsageActionsTable**

```tsx
// frontend/src/components/admin/usage/UsageActionsTable.tsx
import { Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { usageApi, type UsageActionRow } from "../../../api/usage";

interface Props { days: number }

export function UsageActionsTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["usage", "actions", days],
    queryFn: () => usageApi.actions(days),
  });
  const columns = [
    { title: "Действие", dataIndex: "action_type" },
    { title: "Всего", dataIndex: "total", sorter: (a: UsageActionRow, b: UsageActionRow) => a.total - b.total, defaultSortOrder: "descend" as const },
    {
      title: "Топ-3 пользователя", dataIndex: "top_users",
      render: (users: { display_name: string; count: number }[]) =>
        users.map(u => <Tag key={u.display_name}>{u.display_name} ({u.count})</Tag>),
    },
  ];
  return <Table<UsageActionRow> rowKey="action_type" loading={isLoading} dataSource={data} columns={columns} pagination={false} />;
}
```

- [ ] **Step 4: UsageTab (assemble all)**

```tsx
// frontend/src/components/admin/usage/UsageTab.tsx
import { useState } from "react";
import { Radio, Space, Tabs } from "antd";
import { UsageKpiBar } from "./UsageKpiBar";
import { UsageUsersTable } from "./UsageUsersTable";
import { UsagePagesTable } from "./UsagePagesTable";
import { UsageMatrix } from "./UsageMatrix";
import { UsageTimeline } from "./UsageTimeline";
import { UsageActionsTable } from "./UsageActionsTable";

export function UsageTab() {
  const [days, setDays] = useState<number>(30);
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <UsageKpiBar />
      <Radio.Group value={days} onChange={(e) => setDays(e.target.value)}>
        <Radio.Button value={7}>7 дней</Radio.Button>
        <Radio.Button value={30}>30 дней</Radio.Button>
        <Radio.Button value={90}>90 дней</Radio.Button>
      </Radio.Group>
      <Tabs
        items={[
          { key: "users", label: "Пользователи", children: <UsageUsersTable days={days} /> },
          { key: "pages", label: "Разделы", children: <UsagePagesTable days={days} /> },
          { key: "matrix", label: "Кто в каких разделах", children: <UsageMatrix days={days} /> },
          { key: "timeline", label: "Динамика", children: <UsageTimeline days={days} /> },
          { key: "actions", label: "Действия", children: <UsageActionsTable days={days} /> },
        ]}
      />
    </Space>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin/usage/
git commit -m "feat(usage): matrix + timeline + actions + UsageTab assembly"
```

---

### Task C4: Wire UsageTab into SettingsPage

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Read existing SettingsPage to find tab pattern**

Open `frontend/src/pages/SettingsPage.tsx` and locate the admin-tab section (likely similar to feedback tab from previous shipped feature).

- [ ] **Step 2: Add tab**

Add import:
```tsx
import { UsageTab } from "../components/admin/usage/UsageTab";
```

In the tabs array (admin-only branch), append:
```tsx
{ key: "usage", label: "Использование", children: <UsageTab /> },
```

If gating happens via `currentUser.role === 'admin'`, ensure the tab is conditional like other admin tabs.

- [ ] **Step 3: Manual smoke**

Login as admin → /settings → switch to «Использование». Confirm:
- KPI plates render with numbers (even if 0)
- Period selector switches data
- All 5 inner tabs load without errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat(usage): mount UsageTab in /settings (admin only)"
```

---

## Phase D — Verify + Ship

### Task D1: Full backend test sweep

- [ ] **Step 1: Run all tests**

```bash
py -3.10 -m pytest tests/ -v
```
Expected: no regressions, all new usage tests passing.

- [ ] **Step 2: Ruff + mypy**

```bash
ruff check app/ tests/
mypy app/
```

- [ ] **Step 3: Fix any issues, commit if needed**

---

### Task D2: Full frontend lint + build

- [ ] **Step 1: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Unit tests**

```bash
cd frontend && npm test
```

- [ ] **Step 4: Fix any issues**

---

### Task D3: End-to-end manual smoke

- [ ] **Step 1: Start backend + frontend**

```bash
.\scripts\smoke-local.ps1
```

- [ ] **Step 2: Exercise tracker**

- Log in (manager) → navigate /dashboard → wait 90 sec → switch to another browser tab for 1 min → switch back for 30 sec → log out.
- Log in as admin → /settings → «Использование».
- Verify: your manager session shows up in KPI (DAU = at least 1), Users table shows last_seen ≈ now, Pages table shows /dashboard with > 0 hours, Matrix tab shows the cell tinted.

- [ ] **Step 3: Trigger aggregator manually for sanity**

In a Python shell:
```python
from app.jobs.aggregate_usage import aggregate_usage_job
aggregate_usage_job()
```
Confirm new rows in `usage_daily` for yesterday, raw events older than 90 days are gone.

---

### Task D4: Push to origin/main

- [ ] **Step 1: Confirm clean local state**

```bash
git status
git log --oneline -20
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

- [ ] **Step 3: Update memory**

Save a memory: `project_usage_analytics_shipped.md` with date 2026-05-28, what shipped, follow-ups (if any).
