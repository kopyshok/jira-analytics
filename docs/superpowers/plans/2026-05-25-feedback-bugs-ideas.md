# Feedback (Bugs + Ideas) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Server-backed feedback flow: two streams (bugs + ideas), admin-only triage with batch markdown export for Claude Code handoff, replacing the existing clipboard-only `BugReportButton`.

**Architecture:** One table `feedback_items` with `kind` discriminator. FastAPI router under `/feedback` (user-level endpoints) + `/feedback/admin/*` (admin-only). Frontend: existing `errorStore` extended with console + network ring-buffers, new submit drawer replaces clipboard modal, new `/feedback` page for users, new admin tab in `/settings`.

**Tech Stack:** SQLAlchemy 2.0 + Alembic (batch mode for SQLite), FastAPI, pydantic v2 schemas, React 19 + TS 6 + AntD 6, TanStack Query.

**Spec:** [docs/superpowers/specs/2026-05-25-feedback-bugs-ideas-design.md](../specs/2026-05-25-feedback-bugs-ideas-design.md)

---

## File Map

**Backend create:**
- `app/models/feedback.py` — `FeedbackItem` model + `FeedbackKind` enum
- `app/schemas/feedback.py` — pydantic schemas (Create/Read variants)
- `app/services/feedback_service.py` — business logic
- `app/api/endpoints/feedback.py` — router
- `alembic/versions/052_feedback_items.py` — migration
- `tests/test_feedback_service.py`
- `tests/test_feedback_endpoints.py`

**Backend modify:**
- `app/models/__init__.py` — re-export `FeedbackItem`
- `app/api/router.py` — register `/feedback` router

**Frontend create:**
- `frontend/src/api/feedback.ts` — API client
- `frontend/src/components/feedback/FeedbackDrawer.tsx` — submit form (bug+idea toggle)
- `frontend/src/components/feedback/FeedbackButton.tsx` — replaces `BugReportButton.tsx`
- `frontend/src/components/feedback/FeedbackList.tsx` — reusable table (my / public ideas / admin)
- `frontend/src/components/feedback/FeedbackDetailDrawer.tsx` — view a single item
- `frontend/src/components/feedback/FeedbackAdminTab.tsx` — admin /settings tab
- `frontend/src/pages/FeedbackPage.tsx` — `/feedback` user page
- `frontend/src/utils/consoleCapture.ts` — install global console/error listeners
- `e2e/feedback.spec.ts` — Playwright happy path

**Frontend modify:**
- `frontend/src/utils/errorStore.ts` — extend with context builder + helpers (keep `pushError`)
- `frontend/src/api/client.ts` — keep `pushError`, no behaviour change (already wires API errors)
- `frontend/src/components/BugReportButton.tsx` — **delete** (replaced by FeedbackButton)
- `frontend/src/App.tsx` (or wherever `BugReportButton` is mounted) — swap import
- `frontend/src/routes.tsx` — add `/feedback` route
- `frontend/src/pages/SettingsPage.tsx` — add `feedback` tab (admin)
- `frontend/src/pages/lazyPages.tsx` — register `FeedbackPage`
- `frontend/src/main.tsx` — call `installConsoleCapture()` once on bootstrap
- `frontend/src/components/layout/Sidebar.tsx` (or equivalent) — add «Обратная связь» menu link

---

## Phase A — Backend Foundation

### Task A1: Model

**Files:**
- Create: `app/models/feedback.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the model file**

```python
# app/models/feedback.py
"""FeedbackItem — пользовательские баг-репорты и предложения улучшений."""
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class FeedbackKind(str, PyEnum):
    bug = "bug"
    idea = "idea"


class FeedbackItem(Base, TimestampMixin):
    __tablename__ = "feedback_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    kind: Mapped[FeedbackKind] = mapped_column(
        Enum(FeedbackKind, native_enum=False), nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    read_at: Mapped["DateTime | None"] = mapped_column(DateTime, nullable=True)
    read_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # bug-only (nullable for ideas):
    steps_to_reproduce: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_feedback_kind_read_created", "kind", "read_at", "created_at"),
    )
```

- [ ] **Step 2: Re-export in `app/models/__init__.py`**

Find the existing import block and add:

```python
from app.models.feedback import FeedbackItem, FeedbackKind  # noqa: F401
```

(Match the existing import style — alphabetical or grouped, whichever the file already uses.)

- [ ] **Step 3: Commit**

```bash
git add app/models/feedback.py app/models/__init__.py
git commit -m "feat(feedback): add FeedbackItem model"
```

---

### Task A2: Migration

**Files:**
- Create: `alembic/versions/052_feedback_items.py`

- [ ] **Step 1: Generate the migration**

Run from `d:\ClaudeDev\JiraAnalysis`:

```bash
alembic revision --autogenerate -m "feedback items"
```

Move/rename the resulting file to `alembic/versions/052_feedback_items.py` if the autogen used a hash filename.

- [ ] **Step 2: Edit migration to use batch mode**

Open the new file. The `upgrade()` must use `op.create_table` directly (top-level CREATE TABLE is safe in SQLite even without batch). If autogen used `op.create_table` with `op.create_index` separately — leave as-is. Sample target:

```python
def upgrade() -> None:
    op.create_table(
        "feedback_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("page_url", sa.String(2048), nullable=True),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.Column("read_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("steps_to_reproduce", sa.Text, nullable=True),
        sa.Column("expected", sa.Text, nullable=True),
        sa.Column("actual", sa.Text, nullable=True),
        sa.Column("context_json", sa.Text, nullable=True),
        sa.Column("attachments_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_items_author_id", "feedback_items", ["author_id"])
    op.create_index(
        "ix_feedback_kind_read_created",
        "feedback_items",
        ["kind", "read_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_kind_read_created", table_name="feedback_items")
    op.drop_index("ix_feedback_items_author_id", table_name="feedback_items")
    op.drop_table("feedback_items")
```

Confirm `down_revision` points to the latest existing head (`alembic heads` if unsure).

- [ ] **Step 3: Run migration up + down**

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: all three succeed without errors.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/052_feedback_items.py
git commit -m "feat(feedback): add feedback_items migration"
```

---

### Task A3: Schemas

**Files:**
- Create: `app/schemas/feedback.py`

- [ ] **Step 1: Write schemas**

```python
# app/schemas/feedback.py
"""Pydantic schemas для feedback (баги + идеи)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AttachmentRef(BaseModel):
    filename: str
    mime: str
    size: int
    path: str  # storage path returned by upload endpoint


class FeedbackContext(BaseModel):
    """Авто-собранный контекст браузера (только для багов)."""
    user_agent: str | None = None
    language: str | None = None
    screen_w: int | None = None
    screen_h: int | None = None
    timezone: str | None = None
    active_team: str | None = None
    active_period: str | None = None
    theme: str | None = None
    console_errors: list[dict] = Field(default_factory=list)
    network_errors: list[dict] = Field(default_factory=list)


class BugCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    page_url: str | None = None
    steps_to_reproduce: str | None = None
    expected: str | None = None
    actual: str | None = None
    context: FeedbackContext | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)


class IdeaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    page_url: str | None = None


class FeedbackAuthor(BaseModel):
    id: str
    display_name: str
    email: str


class FeedbackRead(BaseModel):
    id: str
    kind: Literal["bug", "idea"]
    author: FeedbackAuthor
    title: str
    body: str
    page_url: str | None
    read_at: datetime | None
    read_by: str | None
    steps_to_reproduce: str | None = None
    expected: str | None = None
    actual: str | None = None
    context: FeedbackContext | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MarkReadRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1)


class ExportRequest(BaseModel):
    kind: Literal["bug", "idea"]
    ids: list[str] | None = None
    only_unread: bool = False
    mark_after: bool = False
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/feedback.py
git commit -m "feat(feedback): add pydantic schemas"
```

---

### Task A4: Service — create + list

**Files:**
- Create: `app/services/feedback_service.py`
- Create: `tests/test_feedback_service.py`

- [ ] **Step 1: Write failing test for `create_bug`**

```python
# tests/test_feedback_service.py
"""Тесты FeedbackService."""
import json

import pytest
from sqlalchemy.orm import Session

from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User, UserRole
from app.schemas.feedback import AttachmentRef, BugCreate, FeedbackContext, IdeaCreate
from app.services.feedback_service import FeedbackService


@pytest.fixture
def author(db_session: Session) -> User:
    u = User(
        email="bob@example.com",
        password_hash="x",
        display_name="Bob",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_create_bug_persists_all_fields(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    payload = BugCreate(
        title="UI crash on Gantt",
        body="Page freezes when scrolling",
        page_url="/resource-planning",
        steps_to_reproduce="1. open\n2. scroll right",
        expected="smooth scroll",
        actual="freeze",
        context=FeedbackContext(
            user_agent="Chrome 130",
            active_team="ITGRI",
            console_errors=[{"ts": "2026-05-25T10:00:00Z", "message": "TypeError"}],
        ),
        attachments=[AttachmentRef(filename="s.png", mime="image/png", size=12, path="x.png")],
    )
    item = svc.create_bug(db_session, author=author, payload=payload)
    assert item.kind == FeedbackKind.bug
    assert item.author_id == author.id
    assert item.read_at is None
    ctx = json.loads(item.context_json)
    assert ctx["active_team"] == "ITGRI"
    atts = json.loads(item.attachments_json)
    assert atts[0]["filename"] == "s.png"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
py -3.10 -m pytest tests/test_feedback_service.py::test_create_bug_persists_all_fields -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.feedback_service'`.

- [ ] **Step 3: Implement minimal service**

```python
# app/services/feedback_service.py
"""FeedbackService — баги и идеи от пользователей."""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import BugCreate, IdeaCreate


class FeedbackService:
    def create_bug(
        self, db: Session, *, author: User, payload: BugCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.bug,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
            steps_to_reproduce=payload.steps_to_reproduce,
            expected=payload.expected,
            actual=payload.actual,
            context_json=(
                json.dumps(payload.context.model_dump()) if payload.context else None
            ),
            attachments_json=(
                json.dumps([a.model_dump() for a in payload.attachments])
                if payload.attachments
                else None
            ),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def create_idea(
        self, db: Session, *, author: User, payload: IdeaCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.idea,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
```

- [ ] **Step 4: Run test to verify it passes**

```bash
py -3.10 -m pytest tests/test_feedback_service.py::test_create_bug_persists_all_fields -v
```

Expected: PASS.

- [ ] **Step 5: Add `create_idea` test**

Append to `tests/test_feedback_service.py`:

```python
def test_create_idea_minimal_fields(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    payload = IdeaCreate(
        title="Add CSV export",
        body="Would be useful on /analytics",
        page_url="/analytics",
    )
    item = svc.create_idea(db_session, author=author, payload=payload)
    assert item.kind == FeedbackKind.idea
    assert item.steps_to_reproduce is None
    assert item.context_json is None
```

- [ ] **Step 6: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v
git add app/services/feedback_service.py tests/test_feedback_service.py
git commit -m "feat(feedback): service create_bug + create_idea"
```

Expected: 2 passed.

---

### Task A5: Service — list + mark read/unread

**Files:**
- Modify: `app/services/feedback_service.py`
- Modify: `tests/test_feedback_service.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_feedback_service.py`:

```python
def test_list_admin_filter_unread(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    a = svc.create_bug(db_session, author=author, payload=BugCreate(title="A", body="x"))
    b = svc.create_bug(db_session, author=author, payload=BugCreate(title="B", body="y"))
    svc.mark_read(db_session, ids=[a.id], reader_id=author.id)

    unread = svc.list_for_admin(db_session, kind=FeedbackKind.bug, filter_mode="unread")
    assert {x.id for x in unread} == {b.id}

    all_items = svc.list_for_admin(db_session, kind=FeedbackKind.bug, filter_mode="all")
    assert {x.id for x in all_items} == {a.id, b.id}


def test_list_user_scope_mine_only_own_bugs(db_session: Session, author: User) -> None:
    other = User(
        email="alice@example.com", password_hash="x", display_name="Alice", role=UserRole.manager,
    )
    db_session.add(other)
    db_session.commit()
    svc = FeedbackService()
    own = svc.create_bug(db_session, author=author, payload=BugCreate(title="Own", body="b"))
    svc.create_bug(db_session, author=other, payload=BugCreate(title="Other", body="b"))

    mine = svc.list_for_user(
        db_session, author_id=author.id, kind=FeedbackKind.bug, scope="mine"
    )
    assert {x.id for x in mine} == {own.id}


def test_list_user_scope_all_ideas_visible(db_session: Session, author: User) -> None:
    other = User(
        email="alice@example.com", password_hash="x", display_name="Alice", role=UserRole.manager,
    )
    db_session.add(other)
    db_session.commit()
    svc = FeedbackService()
    own = svc.create_idea(db_session, author=author, payload=IdeaCreate(title="A", body="b"))
    foreign = svc.create_idea(db_session, author=other, payload=IdeaCreate(title="B", body="b"))

    feed = svc.list_for_user(
        db_session, author_id=author.id, kind=FeedbackKind.idea, scope="all"
    )
    assert {x.id for x in feed} == {own.id, foreign.id}


def test_mark_unread_clears_read_at(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_bug(db_session, author=author, payload=BugCreate(title="T", body="b"))
    svc.mark_read(db_session, ids=[item.id], reader_id=author.id)
    db_session.refresh(item)
    assert item.read_at is not None
    svc.mark_unread(db_session, ids=[item.id])
    db_session.refresh(item)
    assert item.read_at is None
    assert item.read_by is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v
```

Expected: 4 new tests FAIL with `AttributeError: 'FeedbackService' object has no attribute 'list_for_admin'` etc.

- [ ] **Step 3: Implement methods**

Append to `app/services/feedback_service.py`:

```python
    def list_for_admin(
        self,
        db: Session,
        *,
        kind: FeedbackKind,
        filter_mode: str = "unread",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if filter_mode == "unread":
            stmt = stmt.where(FeedbackItem.read_at.is_(None))
        elif filter_mode == "read":
            stmt = stmt.where(FeedbackItem.read_at.is_not(None))
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def list_for_user(
        self,
        db: Session,
        *,
        author_id: str,
        kind: FeedbackKind,
        scope: str = "mine",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if scope == "mine" or kind == FeedbackKind.bug:
            # Юзер видит только свои баги — чужие баги admin-only.
            stmt = stmt.where(FeedbackItem.author_id == author_id)
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def mark_read(self, db: Session, *, ids: list[str], reader_id: str) -> int:
        now = datetime.utcnow()
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            if item.read_at is None:
                item.read_at = now
                item.read_by = reader_id
        db.commit()
        return len(items)

    def mark_unread(self, db: Session, *, ids: list[str]) -> int:
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            item.read_at = None
            item.read_by = None
        db.commit()
        return len(items)
```

- [ ] **Step 4: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v
git add app/services/feedback_service.py tests/test_feedback_service.py
git commit -m "feat(feedback): service list/mark-read/mark-unread"
```

Expected: 6 passed.

---

### Task A6: Service — markdown export

**Files:**
- Modify: `app/services/feedback_service.py`
- Modify: `tests/test_feedback_service.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_feedback_service.py`:

```python
def test_export_markdown_bug_contains_all_sections(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_bug(
        db_session,
        author=author,
        payload=BugCreate(
            title="Crash",
            body="freezes",
            steps_to_reproduce="1. click",
            expected="ok",
            actual="crash",
            page_url="/x",
            context=FeedbackContext(active_team="ITGRI", user_agent="Chrome"),
        ),
    )
    md = svc.export_markdown(
        db_session, kind=FeedbackKind.bug, ids=[item.id], only_unread=False, mark_after=False
    )
    assert "## #1 — Crash" in md
    assert "Шаги воспроизведения" in md
    assert "ITGRI" in md
    assert "Chrome" in md


def test_export_markdown_mark_after_marks_unread(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    a = svc.create_bug(db_session, author=author, payload=BugCreate(title="A", body="b"))
    b = svc.create_bug(db_session, author=author, payload=BugCreate(title="B", body="b"))
    svc.export_markdown(
        db_session,
        kind=FeedbackKind.bug,
        ids=None,
        only_unread=True,
        mark_after=True,
        reader_id=author.id,
    )
    db_session.refresh(a)
    db_session.refresh(b)
    assert a.read_at is not None
    assert b.read_at is not None


def test_export_markdown_idea_format(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_idea(
        db_session, author=author, payload=IdeaCreate(title="CSV", body="useful")
    )
    md = svc.export_markdown(
        db_session, kind=FeedbackKind.idea, ids=[item.id], only_unread=False, mark_after=False
    )
    assert "# Идеи — выгрузка" in md
    assert "CSV" in md
    assert "Шаги воспроизведения" not in md  # idea md skips bug-only sections
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v -k export
```

Expected: 3 FAIL with `AttributeError: 'FeedbackService' object has no attribute 'export_markdown'`.

- [ ] **Step 3: Implement `export_markdown`**

Append to `app/services/feedback_service.py`:

```python
    def export_markdown(
        self,
        db: Session,
        *,
        kind: FeedbackKind,
        ids: list[str] | None,
        only_unread: bool,
        mark_after: bool,
        reader_id: str | None = None,
    ) -> str:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if only_unread:
            stmt = stmt.where(FeedbackItem.read_at.is_(None))
        if ids:
            stmt = stmt.where(FeedbackItem.id.in_(ids))
        stmt = stmt.order_by(FeedbackItem.created_at.desc())
        items = list(db.execute(stmt).scalars())

        # Pre-load authors to avoid lazy-load after commit.
        author_ids = {it.author_id for it in items}
        authors = {
            u.id: u
            for u in db.execute(
                select(User).where(User.id.in_(author_ids))
            ).scalars()
        }

        header = "# Баги" if kind == FeedbackKind.bug else "# Идеи"
        today = datetime.utcnow().strftime("%Y-%m-%d")
        lines: list[str] = [f"{header} — выгрузка {today} ({len(items)} штук)", ""]

        for idx, it in enumerate(items, start=1):
            author = authors.get(it.author_id)
            display = author.display_name if author else "—"
            email = author.email if author else "—"
            lines.append("---\n")
            lines.append(f"## #{idx} — {it.title}\n")
            lines.append(
                f"**Автор:** {display} ({email})  |  "
                f"**Создан:** {it.created_at.strftime('%Y-%m-%d %H:%M')}  |  "
                f"**URL:** {it.page_url or '—'}\n"
            )
            section_label = "Что случилось" if kind == FeedbackKind.bug else "Описание"
            lines.append(f"### {section_label}\n{it.body}\n")
            if kind == FeedbackKind.bug:
                if it.steps_to_reproduce:
                    lines.append(f"### Шаги воспроизведения\n{it.steps_to_reproduce}\n")
                if it.expected:
                    lines.append(f"### Ожидание\n{it.expected}\n")
                if it.actual:
                    lines.append(f"### Факт\n{it.actual}\n")
                if it.context_json:
                    ctx = json.loads(it.context_json)
                    lines.append("### Контекст")
                    if ctx.get("user_agent"):
                        lines.append(f"- Браузер: {ctx['user_agent']}")
                    if ctx.get("screen_w") and ctx.get("screen_h"):
                        lines.append(f"- Экран: {ctx['screen_w']}×{ctx['screen_h']}")
                    if ctx.get("active_team"):
                        lines.append(f"- Активная команда: {ctx['active_team']}")
                    if ctx.get("active_period"):
                        lines.append(f"- Период: {ctx['active_period']}")
                    if ctx.get("theme"):
                        lines.append(f"- Тема: {ctx['theme']}")
                    lines.append("")
                    ce = ctx.get("console_errors") or []
                    if ce:
                        lines.append(f"### Консольные ошибки ({len(ce)})")
                        for i, e in enumerate(ce, start=1):
                            msg = e.get("message", "")
                            stack = e.get("stack", "")
                            lines.append(f"{i}. `{msg}`" + (f" — {stack}" if stack else ""))
                        lines.append("")
                    ne = ctx.get("network_errors") or []
                    if ne:
                        lines.append(f"### Сетевые ошибки ({len(ne)})")
                        for i, e in enumerate(ne, start=1):
                            lines.append(
                                f"{i}. `{e.get('method', '')} {e.get('url', '')} "
                                f"{e.get('status', '')}` → {e.get('detail', '')}"
                            )
                        lines.append("")
                if it.attachments_json:
                    atts = json.loads(it.attachments_json)
                    if atts:
                        lines.append(f"### Приложения ({len(atts)})")
                        for a in atts:
                            lines.append(
                                f"- `{a['filename']}` → /api/v1/feedback/attachments/{a['path']}"
                            )
                        lines.append("")

        if mark_after and items:
            self.mark_read(
                db, ids=[it.id for it in items], reader_id=reader_id or items[0].author_id
            )

        return "\n".join(lines)
```

- [ ] **Step 4: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v
git add app/services/feedback_service.py tests/test_feedback_service.py
git commit -m "feat(feedback): markdown export with mark-after"
```

Expected: 9 passed total.

---

### Task A7: Attachments storage helper

**Files:**
- Modify: `app/services/feedback_service.py`
- Modify: `tests/test_feedback_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_feedback_service.py`:

```python
def test_save_attachment_returns_ref(tmp_path, db_session: Session) -> None:
    from app.services.feedback_service import FeedbackService

    storage = tmp_path / "atts"
    svc = FeedbackService(attachments_dir=str(storage))
    ref = svc.save_attachment(filename="screenshot.png", mime="image/png", data=b"\x89PNG...")
    assert ref.filename == "screenshot.png"
    assert ref.mime == "image/png"
    assert ref.size == len(b"\x89PNG...")
    assert (storage / ref.path).exists()


def test_save_attachment_rejects_bad_mime(tmp_path) -> None:
    from app.services.feedback_service import FeedbackService

    svc = FeedbackService(attachments_dir=str(tmp_path))
    with pytest.raises(ValueError):
        svc.save_attachment(filename="evil.exe", mime="application/x-msdownload", data=b"X")


def test_save_attachment_rejects_oversize(tmp_path) -> None:
    from app.services.feedback_service import FeedbackService

    svc = FeedbackService(attachments_dir=str(tmp_path))
    with pytest.raises(ValueError):
        svc.save_attachment(
            filename="big.png", mime="image/png", data=b"X" * (5 * 1024 * 1024 + 1)
        )
```

- [ ] **Step 2: Run to verify fail**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v -k attachment
```

Expected: 3 FAIL.

- [ ] **Step 3: Implement save_attachment**

Modify `__init__` and add method in `app/services/feedback_service.py`:

```python
import os
import uuid
from pathlib import Path

from app.schemas.feedback import AttachmentRef

_ALLOWED_MIME_PREFIXES = ("image/",)
_ALLOWED_MIME_EXACT = {"application/pdf", "text/plain", "application/json"}
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


class FeedbackService:
    def __init__(self, attachments_dir: str | None = None) -> None:
        self.attachments_dir = attachments_dir or "data/feedback_attachments"

    # ... existing methods ...

    def save_attachment(
        self, *, filename: str, mime: str, data: bytes
    ) -> AttachmentRef:
        if len(data) > _MAX_ATTACHMENT_BYTES:
            raise ValueError("Файл слишком большой (>5 МБ)")
        if not (
            any(mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES)
            or mime in _ALLOWED_MIME_EXACT
        ):
            raise ValueError(f"Тип файла не разрешён: {mime}")
        Path(self.attachments_dir).mkdir(parents=True, exist_ok=True)
        ext = os.path.splitext(filename)[1] or ""
        stored_name = f"{uuid.uuid4()}{ext}"
        full = Path(self.attachments_dir) / stored_name
        full.write_bytes(data)
        return AttachmentRef(filename=filename, mime=mime, size=len(data), path=stored_name)

    def attachment_full_path(self, stored_name: str) -> Path:
        # Защита от path traversal.
        safe = os.path.basename(stored_name)
        return Path(self.attachments_dir) / safe
```

(Make sure existing methods retain `self` — they already use `Session` parameter, no change needed.)

- [ ] **Step 4: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_service.py -v
git add app/services/feedback_service.py tests/test_feedback_service.py
git commit -m "feat(feedback): attachment storage with MIME+size validation"
```

Expected: 12 passed.

---

### Task A8: API router — user endpoints

**Files:**
- Create: `app/api/endpoints/feedback.py`
- Modify: `app/api/router.py`
- Create: `tests/test_feedback_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_feedback_endpoints.py
"""Endpoint-уровень для /feedback."""
import pytest
from fastapi.testclient import TestClient

from app.models.user import User, UserRole


@pytest.fixture
def manager(db_session) -> User:
    u = User(
        email="m@example.com", password_hash="x", display_name="Mgr", role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def admin_user(db_session) -> User:
    u = User(
        email="a@example.com", password_hash="x", display_name="Adm", role=UserRole.admin,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_create_bug_as_manager(
    client: TestClient, manager: User, override_current_user
) -> None:
    override_current_user(manager)
    r = client.post(
        "/api/v1/feedback/bugs",
        json={"title": "Crash", "body": "freezes", "page_url": "/x"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["kind"] == "bug"
    assert data["author"]["id"] == manager.id


def test_create_idea_as_manager(
    client: TestClient, manager: User, override_current_user
) -> None:
    override_current_user(manager)
    r = client.post(
        "/api/v1/feedback/ideas", json={"title": "Idea", "body": "Add CSV"}
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "idea"


def test_list_my_returns_only_my(
    client: TestClient, manager: User, admin_user: User, override_current_user
) -> None:
    override_current_user(manager)
    client.post(
        "/api/v1/feedback/bugs", json={"title": "Mine", "body": "x"}
    )
    override_current_user(admin_user)
    client.post(
        "/api/v1/feedback/bugs", json={"title": "AdminBug", "body": "y"}
    )
    override_current_user(manager)
    r = client.get("/api/v1/feedback/my")
    assert r.status_code == 200
    titles = [it["title"] for it in r.json()]
    assert titles == ["Mine"]


def test_list_ideas_public_visible_to_all(
    client: TestClient, manager: User, admin_user: User, override_current_user
) -> None:
    override_current_user(admin_user)
    client.post(
        "/api/v1/feedback/ideas", json={"title": "Admin idea", "body": "x"}
    )
    override_current_user(manager)
    r = client.get("/api/v1/feedback/ideas?scope=all")
    assert r.status_code == 200
    titles = [it["title"] for it in r.json()]
    assert "Admin idea" in titles
```

**NOTE on fixtures:** the project's `tests/conftest.py` provides `client`, `db_session`, and an auth-override mechanism. Look at existing tests (e.g. `tests/test_capacity_rules_endpoints.py` or `tests/test_admin_users.py`) to see the exact fixture name for current-user override and adapt the `override_current_user` references accordingly. If the codebase uses a different pattern (e.g. login flow via `client.post("/auth/login")`), use that instead.

- [ ] **Step 2: Run test (fails — endpoint missing)**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v -k create_bug
```

Expected: FAIL with 404.

- [ ] **Step 3: Write endpoint file (user-facing)**

```python
# app/api/endpoints/feedback.py
"""Feedback endpoints: bugs + ideas (user-facing) + admin moderation."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import (
    AttachmentRef,
    BugCreate,
    ExportRequest,
    FeedbackAuthor,
    FeedbackContext,
    FeedbackRead,
    IdeaCreate,
    MarkReadRequest,
)
from app.services.feedback_service import FeedbackService

router = APIRouter()
_service = FeedbackService()


def _to_read(item: FeedbackItem, db: Session) -> FeedbackRead:
    """Serialize a FeedbackItem into FeedbackRead with author + parsed JSON blobs."""
    author = db.get(User, item.author_id)
    return FeedbackRead(
        id=item.id,
        kind=item.kind.value,
        author=FeedbackAuthor(
            id=author.id if author else item.author_id,
            display_name=author.display_name if author else "—",
            email=author.email if author else "—",
        ),
        title=item.title,
        body=item.body,
        page_url=item.page_url,
        read_at=item.read_at,
        read_by=item.read_by,
        steps_to_reproduce=item.steps_to_reproduce,
        expected=item.expected,
        actual=item.actual,
        context=(
            FeedbackContext(**json.loads(item.context_json)) if item.context_json else None
        ),
        attachments=(
            [AttachmentRef(**a) for a in json.loads(item.attachments_json)]
            if item.attachments_json
            else []
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/bugs", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def create_bug(
    payload: BugCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedbackRead:
    item = _service.create_bug(db, author=user, payload=payload)
    return _to_read(item, db)


@router.post("/ideas", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def create_idea(
    payload: IdeaCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedbackRead:
    item = _service.create_idea(db, author=user, payload=payload)
    return _to_read(item, db)


@router.get("/my", response_model=list[FeedbackRead])
def list_my(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedbackRead]:
    bugs = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.bug, scope="mine"
    )
    ideas = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.idea, scope="mine"
    )
    combined = sorted(bugs + ideas, key=lambda x: x.created_at, reverse=True)
    return [_to_read(it, db) for it in combined]


@router.get("/ideas", response_model=list[FeedbackRead])
def list_ideas_feed(
    scope: str = "all",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedbackRead]:
    items = _service.list_for_user(
        db, author_id=user.id, kind=FeedbackKind.idea, scope=scope
    )
    return [_to_read(it, db) for it in items]
```

- [ ] **Step 4: Register router**

In `app/api/router.py`, add import:

```python
from app.api.endpoints import feedback as feedback_endpoints
```

And include after the existing authenticated routers block (before admin-only block):

```python
api_router.include_router(
    feedback_endpoints.router, prefix="/feedback", tags=["feedback"], dependencies=_auth_dep,
)
```

(The admin endpoints inside the same router will use `require_admin` per-route, not at include level — that lets user endpoints stay accessible.)

- [ ] **Step 5: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v
git add app/api/endpoints/feedback.py app/api/router.py tests/test_feedback_endpoints.py
git commit -m "feat(feedback): user endpoints create/list"
```

Expected: 4 passed.

---

### Task A9: API router — admin endpoints + export

**Files:**
- Modify: `app/api/endpoints/feedback.py`
- Modify: `tests/test_feedback_endpoints.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_feedback_endpoints.py`:

```python
def test_admin_list_bugs_excludes_read_when_filter_unread(
    client: TestClient, manager: User, admin_user: User, override_current_user
) -> None:
    override_current_user(manager)
    a = client.post("/api/v1/feedback/bugs", json={"title": "A", "body": "x"}).json()
    client.post("/api/v1/feedback/bugs", json={"title": "B", "body": "y"})
    override_current_user(admin_user)
    client.post("/api/v1/feedback/admin/mark-read", json={"ids": [a["id"]]})
    r = client.get("/api/v1/feedback/admin/bugs?filter=unread")
    titles = [it["title"] for it in r.json()]
    assert titles == ["B"]


def test_admin_endpoints_403_for_manager(
    client: TestClient, manager: User, override_current_user
) -> None:
    override_current_user(manager)
    r = client.get("/api/v1/feedback/admin/bugs")
    assert r.status_code == 403


def test_admin_export_marks_read_atomically(
    client: TestClient, manager: User, admin_user: User, override_current_user
) -> None:
    override_current_user(manager)
    client.post("/api/v1/feedback/bugs", json={"title": "A", "body": "x"})
    client.post("/api/v1/feedback/bugs", json={"title": "B", "body": "y"})
    override_current_user(admin_user)
    r = client.post(
        "/api/v1/feedback/admin/export",
        json={"kind": "bug", "only_unread": True, "mark_after": True},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert "## #1" in body
    # Now nothing should be unread.
    r2 = client.get("/api/v1/feedback/admin/bugs?filter=unread")
    assert r2.json() == []
```

- [ ] **Step 2: Run (fail)**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v
```

Expected: 3 new tests FAIL.

- [ ] **Step 3: Add admin endpoints**

Append to `app/api/endpoints/feedback.py`:

```python
@router.get("/admin/bugs", response_model=list[FeedbackRead])
def admin_list_bugs(
    filter: str = "unread",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[FeedbackRead]:
    items = _service.list_for_admin(db, kind=FeedbackKind.bug, filter_mode=filter)
    return [_to_read(it, db) for it in items]


@router.get("/admin/ideas", response_model=list[FeedbackRead])
def admin_list_ideas(
    filter: str = "unread",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[FeedbackRead]:
    items = _service.list_for_admin(db, kind=FeedbackKind.idea, filter_mode=filter)
    return [_to_read(it, db) for it in items]


@router.post("/admin/mark-read", status_code=204)
def admin_mark_read(
    payload: MarkReadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    _service.mark_read(db, ids=payload.ids, reader_id=user.id)
    return Response(status_code=204)


@router.post("/admin/mark-unread", status_code=204)
def admin_mark_unread(
    payload: MarkReadRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    _service.mark_unread(db, ids=payload.ids)
    return Response(status_code=204)


@router.post("/admin/export")
def admin_export(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    kind = FeedbackKind(payload.kind)
    md = _service.export_markdown(
        db,
        kind=kind,
        ids=payload.ids,
        only_unread=payload.only_unread,
        mark_after=payload.mark_after,
        reader_id=user.id,
    )
    today = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"feedback-{payload.kind}s-{today}.md"
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v
git add app/api/endpoints/feedback.py tests/test_feedback_endpoints.py
git commit -m "feat(feedback): admin endpoints + markdown export"
```

Expected: 7 passed.

---

### Task A10: Attachments upload/download endpoints

**Files:**
- Modify: `app/api/endpoints/feedback.py`
- Modify: `tests/test_feedback_endpoints.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_feedback_endpoints.py`:

```python
def test_upload_attachment_returns_ref(
    client: TestClient, manager: User, override_current_user, tmp_path
) -> None:
    override_current_user(manager)
    r = client.post(
        "/api/v1/feedback/attachments",
        files={"file": ("s.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filename"] == "s.png"
    assert data["mime"] == "image/png"
    assert data["size"] > 0
    assert data["path"].endswith(".png")


def test_upload_rejects_bad_mime(
    client: TestClient, manager: User, override_current_user
) -> None:
    override_current_user(manager)
    r = client.post(
        "/api/v1/feedback/attachments",
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run (fail)**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v -k upload
```

Expected: FAIL.

- [ ] **Step 3: Add upload + download endpoints**

Append to `app/api/endpoints/feedback.py`:

```python
@router.post("/attachments", response_model=AttachmentRef)
async def upload_attachment(
    file: UploadFile,
    _: User = Depends(get_current_user),
) -> AttachmentRef:
    data = await file.read()
    try:
        ref = _service.save_attachment(
            filename=file.filename or "file",
            mime=file.content_type or "application/octet-stream",
            data=data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ref


@router.get("/attachments/{stored_name}")
def download_attachment(
    stored_name: str,
    user: User = Depends(get_current_user),
) -> FileResponse:
    # Минимальная защита: проверяем что юзер либо автор baga либо admin.
    # Для простоты MVP — любой authenticated может скачать (UUID — не угадаешь).
    path = _service.attachment_full_path(stored_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path)
```

- [ ] **Step 4: Run + commit**

```bash
py -3.10 -m pytest tests/test_feedback_endpoints.py -v
git add app/api/endpoints/feedback.py tests/test_feedback_endpoints.py
git commit -m "feat(feedback): attachment upload + download endpoints"
```

Expected: 9 passed.

---

## Phase B — Frontend infrastructure

### Task B1: Extend errorStore with console + network buffers + context builder

**Files:**
- Modify: `frontend/src/utils/errorStore.ts`
- Create: `frontend/src/utils/consoleCapture.ts`

- [ ] **Step 1: Rewrite `errorStore.ts`**

Replace contents entirely:

```ts
// frontend/src/utils/errorStore.ts
/** Хранилище ошибок и контекста для feedback-формы. */

export interface NetworkErrorEntry {
  ts: string;
  method: string;
  url: string;
  status: number | null;
  detail: string;
  requestBody?: string;
}

export interface ConsoleErrorEntry {
  ts: string;
  message: string;
  stack?: string;
  source?: string;
}

export interface FeedbackContext {
  user_agent: string;
  language: string;
  screen_w: number;
  screen_h: number;
  timezone: string;
  active_team: string | null;
  active_period: string | null;
  theme: string | null;
  console_errors: ConsoleErrorEntry[];
  network_errors: NetworkErrorEntry[];
}

const MAX_NETWORK = 20;
const MAX_CONSOLE = 20;

const networkErrors: NetworkErrorEntry[] = [];
const consoleErrors: ConsoleErrorEntry[] = [];
const listeners = new Set<() => void>();

function notify() { listeners.forEach((fn) => fn()); }

export function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export function pushError(entry: NetworkErrorEntry): void {
  networkErrors.push(entry);
  if (networkErrors.length > MAX_NETWORK) networkErrors.shift();
  notify();
}

export function pushConsoleError(entry: ConsoleErrorEntry): void {
  consoleErrors.push(entry);
  if (consoleErrors.length > MAX_CONSOLE) consoleErrors.shift();
  notify();
}

export function getNetworkErrors(): readonly NetworkErrorEntry[] {
  return networkErrors;
}

export function getConsoleErrors(): readonly ConsoleErrorEntry[] {
  return consoleErrors;
}

export function getErrorCount(): number {
  return networkErrors.length + consoleErrors.length;
}

export function clearErrors(): void {
  networkErrors.length = 0;
  consoleErrors.length = 0;
  notify();
}

/** Builds a snapshot context for a bug report. */
export function buildContext(): FeedbackContext {
  let activeTeam: string | null = null;
  let activePeriod: string | null = null;
  let theme: string | null = null;
  try {
    const params = new URLSearchParams(window.location.search);
    activeTeam = params.get('team') || params.get('teams');
    const y = params.get('year');
    const q = params.get('quarter');
    if (y && q) activePeriod = `${y}Q${q}`;
    theme = document.documentElement.getAttribute('data-theme');
  } catch {
    // ignore
  }
  return {
    user_agent: navigator.userAgent,
    language: navigator.language,
    screen_w: window.screen.width,
    screen_h: window.screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    active_team: activeTeam,
    active_period: activePeriod,
    theme,
    console_errors: [...consoleErrors],
    network_errors: [...networkErrors],
  };
}
```

Backwards-compat note: `client.ts` calls `pushError(...)` — signature unchanged.

- [ ] **Step 2: Write `consoleCapture.ts`**

```ts
// frontend/src/utils/consoleCapture.ts
/** Перехватывает console.error / window.onerror / unhandledrejection в ring-buffer. */
import { pushConsoleError } from './errorStore';

let installed = false;

export function installConsoleCapture(): void {
  if (installed) return;
  installed = true;

  const originalError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    try {
      const msg = args
        .map((a) => (a instanceof Error ? a.message : typeof a === 'string' ? a : JSON.stringify(a)))
        .join(' ');
      const stack = args.find((a) => a instanceof Error)?.stack as string | undefined;
      pushConsoleError({ ts: new Date().toISOString(), message: msg, stack });
    } catch {
      // never let logging crash the app
    }
    originalError(...args);
  };

  window.addEventListener('error', (ev) => {
    pushConsoleError({
      ts: new Date().toISOString(),
      message: ev.message,
      stack: ev.error?.stack,
      source: ev.filename ? `${ev.filename}:${ev.lineno}` : undefined,
    });
  });

  window.addEventListener('unhandledrejection', (ev) => {
    const reason = ev.reason;
    pushConsoleError({
      ts: new Date().toISOString(),
      message: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
      source: 'unhandledrejection',
    });
  });
}
```

- [ ] **Step 3: Wire bootstrap in `main.tsx`**

Open `frontend/src/main.tsx`. Near the top imports add:

```ts
import { installConsoleCapture } from './utils/consoleCapture';
```

Inside the bootstrap (before `createRoot(...)`) add:

```ts
installConsoleCapture();
```

- [ ] **Step 4: Verify `client.ts` still compiles**

Run typecheck:

```bash
cd frontend && npm run lint
```

Expected: no `pushError` import errors. (Signature kept; only re-exports changed.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/errorStore.ts frontend/src/utils/consoleCapture.ts frontend/src/main.tsx
git commit -m "feat(feedback): console + network ring buffers, context builder"
```

---

### Task B2: API client module

**Files:**
- Create: `frontend/src/api/feedback.ts`

- [ ] **Step 1: Write API client**

```ts
// frontend/src/api/feedback.ts
import { api } from './client';

export type FeedbackKind = 'bug' | 'idea';

export interface AttachmentRef {
  filename: string;
  mime: string;
  size: number;
  path: string;
}

export interface FeedbackAuthor {
  id: string;
  display_name: string;
  email: string;
}

export interface FeedbackItem {
  id: string;
  kind: FeedbackKind;
  author: FeedbackAuthor;
  title: string;
  body: string;
  page_url: string | null;
  read_at: string | null;
  read_by: string | null;
  steps_to_reproduce: string | null;
  expected: string | null;
  actual: string | null;
  context: Record<string, unknown> | null;
  attachments: AttachmentRef[];
  created_at: string;
  updated_at: string;
}

export interface BugCreatePayload {
  title: string;
  body: string;
  page_url?: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
  context?: Record<string, unknown>;
  attachments?: AttachmentRef[];
}

export interface IdeaCreatePayload {
  title: string;
  body: string;
  page_url?: string;
}

export const feedbackApi = {
  createBug: (p: BugCreatePayload) => api.post<FeedbackItem>('/feedback/bugs', p),
  createIdea: (p: IdeaCreatePayload) => api.post<FeedbackItem>('/feedback/ideas', p),
  my: () => api.get<FeedbackItem[]>('/feedback/my'),
  ideasFeed: () => api.get<FeedbackItem[]>('/feedback/ideas', { scope: 'all' }),
  adminListBugs: (filter: 'unread' | 'all' | 'read' = 'unread') =>
    api.get<FeedbackItem[]>('/feedback/admin/bugs', { filter }),
  adminListIdeas: (filter: 'unread' | 'all' | 'read' = 'unread') =>
    api.get<FeedbackItem[]>('/feedback/admin/ideas', { filter }),
  markRead: (ids: string[]) => api.post<void>('/feedback/admin/mark-read', { ids }),
  markUnread: (ids: string[]) => api.post<void>('/feedback/admin/mark-unread', { ids }),
  uploadAttachment: async (file: File): Promise<AttachmentRef> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(
      `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/feedback/attachments`,
      { method: 'POST', body: form, credentials: 'include' },
    );
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  exportUrl: (): string =>
    `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/feedback/admin/export`,
};
```

If the project's `client.ts` doesn't expose a generic `api.get`/`api.post`, check the actual exported names by reading `frontend/src/api/client.ts` and using whatever is available (e.g. wrap the lower-level `request` helper). Match existing usage in other `frontend/src/api/*.ts` modules.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/feedback.ts
git commit -m "feat(feedback): frontend API client"
```

---

## Phase C — Submit Drawer

### Task C1: FeedbackDrawer component

**Files:**
- Create: `frontend/src/components/feedback/FeedbackDrawer.tsx`

- [ ] **Step 1: Write component**

```tsx
// frontend/src/components/feedback/FeedbackDrawer.tsx
import { useState } from 'react';
import { Drawer, Form, Input, Radio, Button, Upload, App, Alert, Space } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { InboxOutlined } from '@ant-design/icons';
import { feedbackApi, type AttachmentRef } from '../../api/feedback';
import { buildContext, clearErrors } from '../../utils/errorStore';

interface Props {
  open: boolean;
  initialKind?: 'bug' | 'idea';
  onClose: () => void;
  onSubmitted?: () => void;
}

export default function FeedbackDrawer({ open, initialKind = 'bug', onClose, onSubmitted }: Props) {
  const { notification } = App.useApp();
  const [kind, setKind] = useState<'bug' | 'idea'>(initialKind);
  const [form] = Form.useForm();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      // Upload files first.
      const refs: AttachmentRef[] = [];
      for (const f of files) {
        if (f.originFileObj) {
          const ref = await feedbackApi.uploadAttachment(f.originFileObj as File);
          refs.push(ref);
        }
      }

      if (kind === 'bug') {
        await feedbackApi.createBug({
          title: values.title,
          body: values.body,
          steps_to_reproduce: values.steps,
          expected: values.expected,
          actual: values.actual,
          page_url: window.location.pathname + window.location.search,
          context: buildContext() as unknown as Record<string, unknown>,
          attachments: refs,
        });
        clearErrors();
      } else {
        await feedbackApi.createIdea({
          title: values.title,
          body: values.body,
          page_url: window.location.pathname + window.location.search,
        });
      }
      notification.success({
        title: kind === 'bug' ? 'Баг отправлен' : 'Идея отправлена',
        message: 'Спасибо за обратную связь',
      });
      form.resetFields();
      setFiles([]);
      onSubmitted?.();
      onClose();
    } catch (e) {
      if (e instanceof Error) {
        notification.error({ title: 'Не удалось отправить', message: e.message });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Обратная связь"
      width={560}
      destroyOnClose
      extra={
        <Button type="primary" onClick={handleSubmit} loading={submitting}>
          Отправить
        </Button>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Radio.Group
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          options={[
            { label: 'Сообщить о баге', value: 'bug' },
            { label: 'Предложить улучшение', value: 'idea' },
          ]}
          optionType="button"
        />

        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            label="Заголовок"
            name="title"
            rules={[{ required: true, message: 'Укажите заголовок' }]}
          >
            <Input placeholder="Кратко — что случилось / что предложить" />
          </Form.Item>

          <Form.Item
            label={kind === 'bug' ? 'Что случилось' : 'Описание идеи'}
            name="body"
            rules={[{ required: true, message: 'Опишите подробнее' }]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>

          {kind === 'bug' && (
            <>
              <Form.Item label="Шаги воспроизведения" name="steps">
                <Input.TextArea rows={3} placeholder="1. Открыл страницу…&#10;2. Нажал кнопку…" />
              </Form.Item>
              <Form.Item label="Что ожидал увидеть" name="expected">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item label="Что получилось на самом деле" name="actual">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item label="Файлы (опционально, до 5 шт по 5 МБ)">
                <Upload.Dragger
                  multiple
                  maxCount={5}
                  beforeUpload={() => false}
                  onChange={(info) => setFiles(info.fileList)}
                  fileList={files}
                >
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p>Перетащите файл или нажмите для выбора</p>
                </Upload.Dragger>
              </Form.Item>
              <Alert
                type="info"
                showIcon
                message="К багу автоматически прикрепится: URL страницы, браузер, активная команда и период, последние ошибки из консоли и сети."
              />
            </>
          )}
        </Form>
      </Space>
    </Drawer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/feedback/FeedbackDrawer.tsx
git commit -m "feat(feedback): submit drawer (bug+idea toggle)"
```

---

### Task C2: Replace BugReportButton with FeedbackButton

**Files:**
- Create: `frontend/src/components/feedback/FeedbackButton.tsx`
- Delete: `frontend/src/components/BugReportButton.tsx`
- Modify: wherever `BugReportButton` is imported (likely `frontend/src/App.tsx` or layout)

- [ ] **Step 1: Find current usage**

```bash
cd frontend && grep -rn "BugReportButton" src/
```

Note the import location for use in step 3.

- [ ] **Step 2: Write `FeedbackButton.tsx`**

```tsx
// frontend/src/components/feedback/FeedbackButton.tsx
import { useState } from 'react';
import { useSyncExternalStore } from 'react';
import { FloatButton } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import { getErrorCount, subscribe } from '../../utils/errorStore';
import FeedbackDrawer from './FeedbackDrawer';

export default function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const errCount = useSyncExternalStore(subscribe, getErrorCount);

  return (
    <>
      <FloatButton
        icon={<MessageOutlined />}
        tooltip="Обратная связь"
        badge={errCount > 0 ? { count: errCount, overflowCount: 99 } : undefined}
        onClick={() => setOpen(true)}
      />
      <FeedbackDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
```

- [ ] **Step 3: Swap the import**

In the file found at step 1 (commonly `frontend/src/App.tsx`), replace:

```ts
import BugReportButton from './components/BugReportButton';
```
with
```ts
import FeedbackButton from './components/feedback/FeedbackButton';
```

and the JSX usage `<BugReportButton />` → `<FeedbackButton />`.

- [ ] **Step 4: Delete old file**

```bash
git rm frontend/src/components/BugReportButton.tsx
```

- [ ] **Step 5: Lint check + commit**

```bash
cd frontend && npm run lint
git add -A frontend/src/components/feedback/FeedbackButton.tsx frontend/src/App.tsx
git commit -m "feat(feedback): replace BugReportButton with FeedbackButton + drawer"
```

Expected: lint passes.

---

## Phase D — User Page `/feedback`

### Task D1: FeedbackList reusable table

**Files:**
- Create: `frontend/src/components/feedback/FeedbackList.tsx`

- [ ] **Step 1: Write component**

```tsx
// frontend/src/components/feedback/FeedbackList.tsx
import { Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckCircleTwoTone, ClockCircleOutlined } from '@ant-design/icons';
import type { FeedbackItem } from '../../api/feedback';

interface Props {
  items: FeedbackItem[];
  loading?: boolean;
  showAuthor?: boolean;
  showReadStatus?: boolean;
  rowSelection?: {
    selectedRowKeys: string[];
    onChange: (keys: string[]) => void;
  };
  onRowClick?: (item: FeedbackItem) => void;
}

export default function FeedbackList({
  items,
  loading,
  showAuthor = false,
  showReadStatus = false,
  rowSelection,
  onRowClick,
}: Props) {
  const cols: ColumnsType<FeedbackItem> = [
    {
      title: 'Тип',
      dataIndex: 'kind',
      width: 90,
      render: (k: string) => <Tag color={k === 'bug' ? 'red' : 'blue'}>{k === 'bug' ? 'Баг' : 'Идея'}</Tag>,
    },
    {
      title: 'Заголовок',
      dataIndex: 'title',
      render: (t: string, r) => (
        <div>
          <Typography.Text strong>{t}</Typography.Text>
          <div style={{ color: '#888', fontSize: 12 }}>{r.body.slice(0, 120)}{r.body.length > 120 ? '…' : ''}</div>
        </div>
      ),
    },
    ...(showAuthor
      ? [{ title: 'Автор', dataIndex: ['author', 'display_name'], width: 160 }]
      : []),
    {
      title: 'Создан',
      dataIndex: 'created_at',
      width: 160,
      render: (s: string) => new Date(s).toLocaleString('ru-RU'),
    },
    ...(showReadStatus
      ? [{
          title: 'Статус',
          dataIndex: 'read_at',
          width: 110,
          render: (s: string | null) =>
            s ? (
              <Tooltip title={`Прочитано ${new Date(s).toLocaleString('ru-RU')}`}>
                <Tag icon={<CheckCircleTwoTone twoToneColor="#52c41a" />} color="success">Прочитано</Tag>
              </Tooltip>
            ) : (
              <Tag icon={<ClockCircleOutlined />} color="orange">Новый</Tag>
            ),
        }]
      : []),
  ];

  return (
    <Table
      rowKey="id"
      size="small"
      dataSource={items}
      columns={cols}
      loading={loading}
      pagination={{ pageSize: 25, showSizeChanger: false }}
      rowSelection={
        rowSelection
          ? {
              selectedRowKeys: rowSelection.selectedRowKeys,
              onChange: (keys) => rowSelection.onChange(keys as string[]),
            }
          : undefined
      }
      onRow={onRowClick ? (r) => ({ onClick: () => onRowClick(r) }) : undefined}
    />
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/feedback/FeedbackList.tsx
git commit -m "feat(feedback): reusable list component"
```

---

### Task D2: FeedbackDetailDrawer

**Files:**
- Create: `frontend/src/components/feedback/FeedbackDetailDrawer.tsx`

- [ ] **Step 1: Write component**

```tsx
// frontend/src/components/feedback/FeedbackDetailDrawer.tsx
import { Drawer, Descriptions, Typography, Tag, Empty, Space, Button } from 'antd';
import type { FeedbackItem } from '../../api/feedback';

interface Props {
  item: FeedbackItem | null;
  onClose: () => void;
}

export default function FeedbackDetailDrawer({ item, onClose }: Props) {
  if (!item) {
    return <Drawer open={false} onClose={onClose} />;
  }

  const ctx = (item.context ?? {}) as Record<string, unknown>;
  const consoleErrs = (ctx.console_errors as Array<Record<string, unknown>>) ?? [];
  const networkErrs = (ctx.network_errors as Array<Record<string, unknown>>) ?? [];

  return (
    <Drawer open={!!item} onClose={onClose} width={720} title={item.title} destroyOnClose>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="Тип">
            <Tag color={item.kind === 'bug' ? 'red' : 'blue'}>{item.kind === 'bug' ? 'Баг' : 'Идея'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Автор">{item.author.display_name} ({item.author.email})</Descriptions.Item>
          <Descriptions.Item label="Создан">{new Date(item.created_at).toLocaleString('ru-RU')}</Descriptions.Item>
          {item.page_url && <Descriptions.Item label="URL">{item.page_url}</Descriptions.Item>}
        </Descriptions>

        <div>
          <Typography.Title level={5}>Описание</Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{item.body}</Typography.Paragraph>
        </div>

        {item.kind === 'bug' && (
          <>
            {item.steps_to_reproduce && (
              <div>
                <Typography.Title level={5}>Шаги воспроизведения</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{item.steps_to_reproduce}</Typography.Paragraph>
              </div>
            )}
            {item.expected && (
              <div>
                <Typography.Title level={5}>Ожидание</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{item.expected}</Typography.Paragraph>
              </div>
            )}
            {item.actual && (
              <div>
                <Typography.Title level={5}>Факт</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{item.actual}</Typography.Paragraph>
              </div>
            )}
            <div>
              <Typography.Title level={5}>Контекст</Typography.Title>
              <Descriptions column={1} size="small" bordered>
                {ctx.user_agent && <Descriptions.Item label="Браузер">{String(ctx.user_agent)}</Descriptions.Item>}
                {ctx.screen_w && <Descriptions.Item label="Экран">{String(ctx.screen_w)}×{String(ctx.screen_h)}</Descriptions.Item>}
                {ctx.active_team && <Descriptions.Item label="Команда">{String(ctx.active_team)}</Descriptions.Item>}
                {ctx.active_period && <Descriptions.Item label="Период">{String(ctx.active_period)}</Descriptions.Item>}
                {ctx.theme && <Descriptions.Item label="Тема">{String(ctx.theme)}</Descriptions.Item>}
              </Descriptions>
            </div>
            <div>
              <Typography.Title level={5}>Консольные ошибки ({consoleErrs.length})</Typography.Title>
              {consoleErrs.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Нет" />
              ) : (
                <ol>
                  {consoleErrs.map((e, i) => (
                    <li key={i}><code>{String(e.message)}</code></li>
                  ))}
                </ol>
              )}
            </div>
            <div>
              <Typography.Title level={5}>Сетевые ошибки ({networkErrs.length})</Typography.Title>
              {networkErrs.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Нет" />
              ) : (
                <ol>
                  {networkErrs.map((e, i) => (
                    <li key={i}><code>{String(e.method)} {String(e.url)} {String(e.status)}</code></li>
                  ))}
                </ol>
              )}
            </div>
            {item.attachments.length > 0 && (
              <div>
                <Typography.Title level={5}>Приложения ({item.attachments.length})</Typography.Title>
                <ul>
                  {item.attachments.map((a) => (
                    <li key={a.path}>
                      <Button
                        type="link"
                        href={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/feedback/attachments/${a.path}`}
                        target="_blank"
                      >
                        {a.filename} ({Math.round(a.size / 1024)} КБ)
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Space>
    </Drawer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/feedback/FeedbackDetailDrawer.tsx
git commit -m "feat(feedback): detail drawer"
```

---

### Task D3: FeedbackPage + route

**Files:**
- Create: `frontend/src/pages/FeedbackPage.tsx`
- Modify: `frontend/src/pages/lazyPages.tsx`
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (or equivalent — find with grep)

- [ ] **Step 1: Write the page**

```tsx
// frontend/src/pages/FeedbackPage.tsx
import { useState } from 'react';
import { Tabs, Button, Space, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { feedbackApi, type FeedbackItem } from '../api/feedback';
import FeedbackList from '../components/feedback/FeedbackList';
import FeedbackDrawer from '../components/feedback/FeedbackDrawer';
import FeedbackDetailDrawer from '../components/feedback/FeedbackDetailDrawer';

export default function FeedbackPage() {
  const [tab, setTab] = useState<'my' | 'ideas'>('my');
  const [submitOpen, setSubmitOpen] = useState(false);
  const [detail, setDetail] = useState<FeedbackItem | null>(null);

  const myQ = useQuery({
    queryKey: ['feedback', 'my'],
    queryFn: () => feedbackApi.my(),
    enabled: tab === 'my',
  });
  const ideasQ = useQuery({
    queryKey: ['feedback', 'ideas-feed'],
    queryFn: () => feedbackApi.ideasFeed(),
    enabled: tab === 'ideas',
  });

  return (
    <div style={{ padding: 16 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Обратная связь</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setSubmitOpen(true)}>
          Создать
        </Button>
      </Space>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'my' | 'ideas')}
        items={[
          {
            key: 'my',
            label: 'Мои обращения',
            children: (
              <FeedbackList
                items={myQ.data ?? []}
                loading={myQ.isLoading}
                onRowClick={(it) => setDetail(it)}
              />
            ),
          },
          {
            key: 'ideas',
            label: 'Лента идей',
            children: (
              <FeedbackList
                items={ideasQ.data ?? []}
                loading={ideasQ.isLoading}
                showAuthor
                onRowClick={(it) => setDetail(it)}
              />
            ),
          },
        ]}
      />

      <FeedbackDrawer
        open={submitOpen}
        onClose={() => setSubmitOpen(false)}
        onSubmitted={() => {
          myQ.refetch();
          ideasQ.refetch();
        }}
      />
      <FeedbackDetailDrawer item={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
```

- [ ] **Step 2: Register lazy page**

Add to `frontend/src/pages/lazyPages.tsx` (match existing pattern of `React.lazy(() => import(...))`):

```ts
export const FeedbackPage = lazy(() => import('./FeedbackPage'));
```

- [ ] **Step 3: Add route**

In `frontend/src/routes.tsx`, alongside other authenticated routes, add:

```tsx
{ path: 'feedback', element: <FeedbackPage /> },
```

(Use the actual structure of `routes.tsx` — wrap with whatever `ProtectedRoute`/`AuthLayout` the other routes use.)

Import `FeedbackPage` from `./pages/lazyPages`.

- [ ] **Step 4: Add menu link**

Find the sidebar/menu component:

```bash
cd frontend && grep -rln "RP\|/resource-planning\|Sider\|<Menu" src/ | head
```

Add a menu item «Обратная связь» pointing to `/feedback` (icon: `MessageOutlined`). Match the existing menu-item shape exactly.

- [ ] **Step 5: Lint + manual smoke**

```bash
cd frontend && npm run lint
```

Then run dev server (`npm run dev`) and verify:
1. `/feedback` page loads.
2. Click «Создать» → drawer opens.
3. Switch tabs «Мои / Идеи».

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/FeedbackPage.tsx frontend/src/pages/lazyPages.tsx frontend/src/routes.tsx frontend/src/components/layout/
git commit -m "feat(feedback): /feedback page + menu link"
```

---

## Phase E — Admin tab

### Task E1: FeedbackAdminTab component

**Files:**
- Create: `frontend/src/components/feedback/FeedbackAdminTab.tsx`

- [ ] **Step 1: Write component**

```tsx
// frontend/src/components/feedback/FeedbackAdminTab.tsx
import { useState } from 'react';
import { Tabs, Space, Button, Radio, App, Popconfirm } from 'antd';
import { DownloadOutlined, CheckOutlined, RollbackOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { feedbackApi, type FeedbackItem } from '../../api/feedback';
import FeedbackList from './FeedbackList';
import FeedbackDetailDrawer from './FeedbackDetailDrawer';

type Filter = 'unread' | 'all';
type Kind = 'bug' | 'idea';

export default function FeedbackAdminTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>('bug');
  const [filter, setFilter] = useState<Filter>('unread');
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<FeedbackItem | null>(null);

  const listKey = ['feedback', 'admin', kind, filter] as const;
  const q = useQuery({
    queryKey: listKey,
    queryFn: () =>
      kind === 'bug' ? feedbackApi.adminListBugs(filter) : feedbackApi.adminListIdeas(filter),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['feedback'] });
    setSelected([]);
  };

  const handleMarkRead = async () => {
    if (selected.length === 0) return;
    await feedbackApi.markRead(selected);
    notification.success({ title: 'Отмечено прочитанными', message: `${selected.length} шт.` });
    invalidate();
  };

  const handleMarkUnread = async () => {
    if (selected.length === 0) return;
    await feedbackApi.markUnread(selected);
    invalidate();
  };

  const downloadMarkdown = async (params: {
    ids: string[] | null; only_unread: boolean; mark_after: boolean;
  }) => {
    const url = feedbackApi.exportUrl();
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ kind, ...params }),
    });
    if (!res.ok) {
      notification.error({ title: 'Ошибка экспорта', message: String(res.status) });
      return;
    }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    a.download = `feedback-${kind}s-${today}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    if (params.mark_after) invalidate();
  };

  const handleExportSelected = () => downloadMarkdown({
    ids: selected, only_unread: false, mark_after: false,
  });

  const handleExportAllUnreadAndMark = () => downloadMarkdown({
    ids: null, only_unread: true, mark_after: true,
  });

  return (
    <div>
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Radio.Group
          value={kind}
          onChange={(e) => { setKind(e.target.value); setSelected([]); }}
          options={[
            { label: 'Баги', value: 'bug' },
            { label: 'Идеи', value: 'idea' },
          ]}
          optionType="button"
        />
        <Radio.Group
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          options={[
            { label: 'Только новые', value: 'unread' },
            { label: 'Все', value: 'all' },
          ]}
          optionType="button"
        />
        <Button
          icon={<DownloadOutlined />}
          disabled={selected.length === 0}
          onClick={handleExportSelected}
        >
          Выгрузить выбранные ({selected.length})
        </Button>
        <Popconfirm
          title="Выгрузить все новые и пометить прочитанными?"
          okText="Да"
          cancelText="Отмена"
          onConfirm={handleExportAllUnreadAndMark}
        >
          <Button type="primary" icon={<DownloadOutlined />}>
            Выгрузить новые и отметить прочитанными
          </Button>
        </Popconfirm>
        <Button
          icon={<CheckOutlined />}
          disabled={selected.length === 0}
          onClick={handleMarkRead}
        >
          Отметить прочитанными
        </Button>
        <Button
          icon={<RollbackOutlined />}
          disabled={selected.length === 0}
          onClick={handleMarkUnread}
        >
          Снять отметку
        </Button>
      </Space>

      <FeedbackList
        items={q.data ?? []}
        loading={q.isLoading}
        showAuthor
        showReadStatus
        rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
        onRowClick={(it) => setDetail(it)}
      />

      <FeedbackDetailDrawer item={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/feedback/FeedbackAdminTab.tsx
git commit -m "feat(feedback): admin tab with bulk export + mark-read"
```

---

### Task E2: Wire admin tab into `/settings`

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add tab**

Find the tabs array/items in `SettingsPage.tsx` (search for `key: 'users'`) and add a new entry **after** `users`:

```tsx
{
  key: 'feedback',
  label: 'Обратная связь',
  children: <FeedbackAdminTab />,
},
```

Add the import:

```ts
import FeedbackAdminTab from '../components/feedback/FeedbackAdminTab';
```

- [ ] **Step 2: Lint + commit**

```bash
cd frontend && npm run lint
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat(feedback): wire admin tab into /settings"
```

---

## Phase F — Verification

### Task F1: Backend test sweep

- [ ] **Step 1: Run full backend test**

```bash
py -3.10 -m pytest tests/test_feedback_service.py tests/test_feedback_endpoints.py -v
```

Expected: all green.

- [ ] **Step 2: Lint**

```bash
ruff check app/api/endpoints/feedback.py app/services/feedback_service.py app/models/feedback.py app/schemas/feedback.py
mypy app/api/endpoints/feedback.py app/services/feedback_service.py
```

Fix any complaints. Commit fixes if needed.

---

### Task F2: Frontend manual smoke

- [ ] **Step 1: Restart backend (kill PID :8000)**

```powershell
Get-Process | Where-Object {$_.MainWindowTitle -like '*uvicorn*'} | Stop-Process -Force; uvicorn app.main:app --reload --port 8000
```

(Per memory: Windows uvicorn --reload hangs — kill + restart.)

- [ ] **Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Manual smoke checklist**

Open browser at the dev URL, log in as a manager:
- Plavashka в углу → click → drawer открылся.
- Заполнить «Баг» → отправить → toast «Баг отправлен».
- Перейти на `/feedback` → вкладка «Мои» → видно отправленный баг.
- Кликнуть строку → detail drawer показывает контекст + консольные/сетевые ошибки.
- Создать «Идею» → она появилась в обеих вкладках («Мои» + «Лента идей»).

Перелогиниться админом:
- `/settings` → вкладка «Обратная связь» → видно баг от менеджера.
- Выбрать → «Выгрузить выбранные» → скачался `.md` файл, статус не изменился.
- «Выгрузить новые и отметить прочитанными» → скачался `.md`, после refresh строки исчезли из «Только новые».
- Переключить «Все» → строки видны, статус «Прочитано».

- [ ] **Step 4: Document gaps**

If something doesn't work, fix it in additional commits. Do **not** mark this task complete until smoke passes.

---

### Task F3: E2E happy path

**Files:**
- Create: `frontend/e2e/feedback.spec.ts`

- [ ] **Step 1: Write E2E spec**

```ts
// frontend/e2e/feedback.spec.ts
import { test, expect } from '@playwright/test';

test('user submits bug, admin sees + exports', async ({ page, context }) => {
  // Login as a seeded user (use whatever helper existing e2e specs use; see
  // e2e/auth-helpers.ts or similar).
  await page.goto('/login');
  await page.getByLabel('Email').fill('e2e@example.com');
  await page.getByLabel('Пароль').fill('e2e');
  await page.getByRole('button', { name: /войти/i }).click();
  await expect(page).toHaveURL(/dashboard|\/$/);

  // Open floating button.
  await page.getByRole('button', { name: /обратная связь/i }).click();
  await page.getByLabel('Заголовок').fill('E2E bug');
  await page.getByLabel('Что случилось').fill('Page froze on click');
  await page.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByText('Баг отправлен')).toBeVisible();

  // Go to /feedback and see it.
  await page.goto('/feedback');
  await expect(page.getByText('E2E bug')).toBeVisible();
});
```

If the project's e2e setup needs admin login for the admin-side check, copy the existing admin-login helper. If absent, the user-side path above is the minimum acceptable E2E.

- [ ] **Step 2: Run E2E**

```bash
cd frontend && npm run e2e -- feedback.spec.ts
```

Expected: passes. If the existing e2e seed (`scripts/seed_e2e.py`) doesn't include a usable login, document the gap in a comment at the top of the spec instead of forcing the test to pass with mocks.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/feedback.spec.ts
git commit -m "test(feedback): e2e happy path"
```

---

## Phase G — Wrap-up

### Task G1: Push + memory update

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: Update auto-memory**

Save a project memory `project_feedback_shipped.md` summarising:
- Date 2026-05-25
- Endpoints under /feedback
- Replaces BugReportButton clipboard flow
- Admin export markdown for Claude Code handoff
- Idea stream visible to all users

Add to `MEMORY.md` index.

---

## Self-Review Notes

- All schemas, methods, endpoint paths used in later tasks are defined in earlier tasks (model in A1, schemas in A3, service methods in A4–A7, endpoints in A8–A10, frontend api in B2).
- No "TBD" / placeholder steps — every code block is complete.
- Admin permission check uses existing `require_admin` from `app/core/auth_deps.py:45`.
- Migration revision number `052` follows the existing numbered convention (latest was `051_add_allocation_overrides.py`).
- Frontend `client.ts` `pushError` signature kept stable — extends without breaking existing imports.
- `BugReportButton` deletion is explicit (`git rm`), preserving git history.
- Markdown export is non-destructive when `mark_after=False`; atomic when `mark_after=True`.
