# Release Notes Feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Лента «Что нового» внутри сервиса — модалка при первом заходе после релиза + красная точка на иконке справки пока не прочитано + полная история версий + админ-CRUD на `/settings` + CLI для накопления заметок + интеграция в релиз-скрипт.

**Architecture:** Бэк — таблица `release_notes` (одна запись = один пункт «что нового»), поле `last_seen_release_version` на `users`, эндпоинты для пользователей и для админов. CLI `scripts/release_note.py` пишет черновики, `scripts/release.py` после `git tag` привязывает черновики к новой версии. Фронт — модалка + вкладка в HelpDrawer + админ-таб; модалка появляется на основе сравнения `last_seen_release_version` пользователя с максимально опубликованной версией.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (batch для SQLite), Pydantic, React 19 + AntD 6 + TanStack Query, pytest.

**Спека:** `docs/superpowers/specs/2026-06-01-release-notes-feed-design.md`

---

## Phase 1 — Backend: модель и миграция

### Task 1: Модель ReleaseNote + миграция

**Files:**
- Create: `app/models/release_note.py`
- Modify: `app/models/__init__.py` — добавить импорт `ReleaseNote`
- Modify: `app/models/user.py` — добавить поле `last_seen_release_version`
- Create: `alembic/versions/056_release_notes.py`

- [ ] **Step 1: Создать миграцию (черновик)**

`alembic/versions/056_release_notes.py`:

```python
"""release_notes + user.last_seen_release_version

Revision ID: 056_release_notes
Revises: eff9e06ce1f5
Create Date: 2026-06-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056_release_notes"
down_revision: Union[str, None] = "eff9e06ce1f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "release_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=True, index=True),
        sa.Column(
            "note_type",
            sa.String(length=20),
            nullable=False,
        ),  # new | improvement | fix
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("help_link", sa.String(length=255), nullable=True),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_release_notes_version_type",
        "release_notes",
        ["version", "note_type"],
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("last_seen_release_version", sa.String(length=32), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_seen_release_version")
    op.drop_index("ix_release_notes_version_type", table_name="release_notes")
    op.drop_table("release_notes")
```

- [ ] **Step 2: Создать модель**

`app/models/release_note.py`:

```python
"""ReleaseNote — запись в ленте «Что нового»."""
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

NOTE_TYPES = ("new", "improvement", "fix")
SECTIONS = (
    "scenarios", "resources", "analytics", "issues",
    "dashboard", "backlog", "sync", "settings", "general",
)


class ReleaseNote(Base, TimestampMixin):
    __tablename__ = "release_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    note_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    help_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
```

- [ ] **Step 3: Добавить импорт и поле user**

В `app/models/__init__.py` добавить:
```python
from app.models.release_note import ReleaseNote
```

В `app/models/user.py` после `appearance_settings_raw` добавить:
```python
    last_seen_release_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
```

- [ ] **Step 4: Применить миграцию**

```bash
py -3.10 -m alembic upgrade head
```

Ожидание: `INFO  [alembic.runtime.migration] Running upgrade eff9e06ce1f5 -> 056_release_notes`.

- [ ] **Step 5: Smoke-проверка**

```bash
py -3.10 -c "from app.models import ReleaseNote; from app.models.user import User; print(ReleaseNote.__table__.columns.keys()); print('last_seen_release_version' in User.__table__.columns.keys())"
```

Ожидание: список колонок + `True`.

- [ ] **Step 6: Commit**

```bash
git add app/models/release_note.py app/models/__init__.py app/models/user.py alembic/versions/056_release_notes.py
git commit -m "feat(release-notes): модель ReleaseNote + поле user.last_seen_release_version (миграция 056)"
```

---

## Phase 2 — Backend: сервис и API

### Task 2: Сервис ReleaseNoteService + тесты

**Files:**
- Create: `app/services/release_note_service.py`
- Create: `tests/test_release_note_service.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_release_note_service.py`:

```python
"""Тесты ReleaseNoteService."""
from sqlalchemy.orm import Session

from app.models.release_note import ReleaseNote
from app.models.user import User, UserRole
from app.services.release_note_service import ReleaseNoteService


def _make_note(db, **kwargs):
    defaults = dict(
        note_type="improvement",
        section="general",
        title="Test note",
        description="Test description",
    )
    defaults.update(kwargs)
    svc = ReleaseNoteService(db)
    return svc.create_draft(**defaults)


def test_create_draft_no_version(db_session: Session):
    note = _make_note(db_session)
    assert note.version is None
    assert note.note_type == "improvement"


def test_invalid_note_type_rejected(db_session: Session):
    svc = ReleaseNoteService(db_session)
    try:
        svc.create_draft(
            note_type="wat", section="general", title="x", description="y"
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid note_type")


def test_publish_drafts_assigns_version(db_session: Session):
    _make_note(db_session)
    _make_note(db_session, note_type="new")
    svc = ReleaseNoteService(db_session)
    n = svc.publish_drafts("v1.2.0")
    assert n == 2
    notes = db_session.query(ReleaseNote).all()
    assert all(note.version == "v1.2.0" for note in notes)


def test_publish_drafts_zero_when_none(db_session: Session):
    svc = ReleaseNoteService(db_session)
    assert svc.publish_drafts("v1.2.0") == 0


def test_versions_listing_excludes_drafts(db_session: Session):
    _make_note(db_session)
    n = _make_note(db_session)
    n.version = "v1.0.0"
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    versions = svc.list_published_versions()
    assert versions == ["v1.0.0"]


def test_mark_user_seen_updates_field(db_session: Session):
    user = User(
        email="u@x", password_hash="x", display_name="U", role=UserRole.manager
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    svc.mark_user_seen(user, "v1.2.0")
    assert user.last_seen_release_version == "v1.2.0"


def test_unread_for_user_returns_versions_after(db_session: Session):
    for v in ["v1.0.0", "v1.1.0", "v1.2.0"]:
        n = _make_note(db_session)
        n.version = v
        db_session.commit()
    user = User(
        email="u@x", password_hash="x", display_name="U",
        role=UserRole.manager, last_seen_release_version="v1.0.0",
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    unread = svc.unread_versions_for(user)
    assert unread == ["v1.1.0", "v1.2.0"]


def test_unread_for_user_skips_hidden(db_session: Session):
    n = _make_note(db_session)
    n.version = "v1.1.0"
    n.is_hidden = True
    db_session.commit()
    user = User(
        email="u@x", password_hash="x", display_name="U",
        role=UserRole.manager, last_seen_release_version="v1.0.0",
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    assert svc.unread_versions_for(user) == []
```

- [ ] **Step 2: Запустить тесты — убедиться что падают**

```bash
py -3.10 -m pytest tests/test_release_note_service.py -v
```

Ожидание: ImportError `app.services.release_note_service`.

- [ ] **Step 3: Реализовать сервис**

`app/services/release_note_service.py`:

```python
"""Сервис ленты «Что нового»."""
from sqlalchemy.orm import Session

from app.models.release_note import NOTE_TYPES, SECTIONS, ReleaseNote
from app.models.user import User

# SemVer-ish сравнение: "v1.10.0" > "v1.2.0".
def _ver_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.lstrip("v").split(".") if p.isdigit())


class ReleaseNoteService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft(
        self,
        *,
        note_type: str,
        section: str,
        title: str,
        description: str,
        help_link: str | None = None,
        created_by: str | None = None,
    ) -> ReleaseNote:
        if note_type not in NOTE_TYPES:
            raise ValueError(f"Неизвестный тип записи: {note_type!r}")
        if section not in SECTIONS:
            raise ValueError(f"Неизвестный раздел: {section!r}")
        note = ReleaseNote(
            note_type=note_type,
            section=section,
            title=title.strip(),
            description=description.strip(),
            help_link=help_link,
            created_by=created_by,
        )
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def publish_drafts(self, version: str) -> int:
        drafts = (
            self.db.query(ReleaseNote)
            .filter(ReleaseNote.version.is_(None))
            .all()
        )
        for n in drafts:
            n.version = version
        self.db.commit()
        return len(drafts)

    def list_published_versions(self) -> list[str]:
        rows = (
            self.db.query(ReleaseNote.version)
            .filter(ReleaseNote.version.isnot(None))
            .distinct()
            .all()
        )
        versions = [r[0] for r in rows]
        return sorted(versions, key=_ver_key)

    def unread_versions_for(self, user: User) -> list[str]:
        all_versions = self.list_published_versions()
        # пользователь видел до last_seen → возвращаем только новее
        baseline = user.last_seen_release_version
        unread = []
        for v in all_versions:
            if baseline and _ver_key(v) <= _ver_key(baseline):
                continue
            # есть ли хотя бы одна не-скрытая запись?
            has_visible = (
                self.db.query(ReleaseNote.id)
                .filter(
                    ReleaseNote.version == v,
                    ReleaseNote.is_hidden.is_(False),
                )
                .first()
                is not None
            )
            if has_visible:
                unread.append(v)
        return unread

    def mark_user_seen(self, user: User, version: str) -> None:
        user.last_seen_release_version = version
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

    def notes_for_versions(
        self, versions: list[str], *, include_hidden: bool = False
    ) -> list[ReleaseNote]:
        q = self.db.query(ReleaseNote).filter(ReleaseNote.version.in_(versions))
        if not include_hidden:
            q = q.filter(ReleaseNote.is_hidden.is_(False))
        return q.order_by(ReleaseNote.version, ReleaseNote.sort_order, ReleaseNote.created_at).all()

    def list_drafts(self) -> list[ReleaseNote]:
        return (
            self.db.query(ReleaseNote)
            .filter(ReleaseNote.version.is_(None))
            .order_by(ReleaseNote.sort_order, ReleaseNote.created_at)
            .all()
        )
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
py -3.10 -m pytest tests/test_release_note_service.py -v
```

Ожидание: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/release_note_service.py tests/test_release_note_service.py
git commit -m "feat(release-notes): ReleaseNoteService + 7 unit-тестов"
```

---

### Task 3: Pydantic-схемы + пользовательский API

**Files:**
- Create: `app/schemas/release_note.py`
- Create: `app/api/endpoints/release_notes.py`
- Modify: `app/api/router.py`
- Create: `tests/api/test_release_notes_user_api.py`

- [ ] **Step 1: Схемы**

`app/schemas/release_note.py`:

```python
"""Pydantic-схемы ReleaseNote."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ReleaseNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: str | None
    note_type: str
    section: str
    title: str
    description: str
    help_link: str | None
    is_hidden: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ReleaseNoteCreate(BaseModel):
    note_type: str
    section: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    help_link: str | None = None


class ReleaseNoteUpdate(BaseModel):
    note_type: str | None = None
    section: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1)
    help_link: str | None = None
    is_hidden: bool | None = None
    sort_order: int | None = None


class VersionFeed(BaseModel):
    version: str
    notes: list[ReleaseNoteResponse]


class UnreadResponse(BaseModel):
    unread_versions: list[str]
    feeds: list[VersionFeed]


class MarkSeenRequest(BaseModel):
    version: str
```

- [ ] **Step 2: Падающие тесты пользовательского API**

`tests/api/test_release_notes_user_api.py`:

```python
"""GET /release-notes/unread, /release-notes/all, POST /release-notes/mark-seen."""
from app.models.release_note import ReleaseNote
from app.models.user import UserRole


def _create_note(db, version: str, **kw):
    defaults = dict(
        note_type="improvement", section="general",
        title="Title", description="Desc", version=version,
    )
    defaults.update(kw)
    n = ReleaseNote(**defaults)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_unread_empty_for_fresh_user(client_auth, db_session, current_user):
    current_user.last_seen_release_version = "v1.0.0"
    db_session.commit()
    r = client_auth.get("/api/v1/release-notes/unread")
    assert r.status_code == 200
    body = r.json()
    assert body == {"unread_versions": [], "feeds": []}


def test_unread_returns_published_after_last_seen(
    client_auth, db_session, current_user
):
    _create_note(db_session, "v1.0.0")
    _create_note(db_session, "v1.1.0")
    _create_note(db_session, "v1.1.0", note_type="new")
    current_user.last_seen_release_version = "v1.0.0"
    db_session.commit()
    r = client_auth.get("/api/v1/release-notes/unread")
    assert r.status_code == 200
    body = r.json()
    assert body["unread_versions"] == ["v1.1.0"]
    assert len(body["feeds"]) == 1
    assert body["feeds"][0]["version"] == "v1.1.0"
    assert len(body["feeds"][0]["notes"]) == 2


def test_unread_hides_hidden_records(client_auth, db_session, current_user):
    _create_note(db_session, "v1.1.0", is_hidden=True)
    current_user.last_seen_release_version = "v1.0.0"
    db_session.commit()
    r = client_auth.get("/api/v1/release-notes/unread")
    assert r.json()["unread_versions"] == []


def test_all_returns_published_versions_excluding_drafts(client_auth, db_session):
    _create_note(db_session, "v1.0.0")
    _create_note(db_session, None)  # черновик
    r = client_auth.get("/api/v1/release-notes/all")
    assert r.status_code == 200
    body = r.json()
    versions = [f["version"] for f in body["feeds"]]
    assert versions == ["v1.0.0"]


def test_mark_seen_updates_user(client_auth, db_session, current_user):
    _create_note(db_session, "v1.1.0")
    r = client_auth.post(
        "/api/v1/release-notes/mark-seen", json={"version": "v1.1.0"}
    )
    assert r.status_code == 204
    db_session.refresh(current_user)
    assert current_user.last_seen_release_version == "v1.1.0"


def test_unread_requires_auth(client):
    r = client.get("/api/v1/release-notes/unread")
    assert r.status_code == 401
```

- [ ] **Step 3: Запустить — должны падать (route не существует)**

```bash
py -3.10 -m pytest tests/api/test_release_notes_user_api.py -v
```

Ожидание: 404 на всех endpoints.

- [ ] **Step 4: Реализовать роутер**

`app/api/endpoints/release_notes.py`:

```python
"""Пользовательские эндпоинты ленты «Что нового»."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.release_note import (
    MarkSeenRequest,
    ReleaseNoteResponse,
    UnreadResponse,
    VersionFeed,
)
from app.services.release_note_service import ReleaseNoteService

router = APIRouter(prefix="/release-notes", tags=["release-notes"])


def _build_feeds(svc: ReleaseNoteService, versions: list[str]) -> list[VersionFeed]:
    notes = svc.notes_for_versions(versions)
    by_version: dict[str, list] = {v: [] for v in versions}
    for n in notes:
        by_version.setdefault(n.version, []).append(ReleaseNoteResponse.model_validate(n))
    # новые версии сверху
    versions_desc = sorted(versions, reverse=True, key=lambda v: tuple(
        int(p) for p in v.lstrip("v").split(".") if p.isdigit()
    ))
    return [VersionFeed(version=v, notes=by_version.get(v, [])) for v in versions_desc]


@router.get("/unread", response_model=UnreadResponse)
def get_unread(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadResponse:
    svc = ReleaseNoteService(db)
    unread = svc.unread_versions_for(user)
    return UnreadResponse(unread_versions=unread, feeds=_build_feeds(svc, unread))


@router.get("/all", response_model=UnreadResponse)
def get_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadResponse:
    svc = ReleaseNoteService(db)
    all_versions = svc.list_published_versions()
    return UnreadResponse(
        unread_versions=svc.unread_versions_for(user),
        feeds=_build_feeds(svc, all_versions),
    )


@router.post("/mark-seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(
    body: MarkSeenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = ReleaseNoteService(db)
    svc.mark_user_seen(user, body.version)
```

- [ ] **Step 5: Зарегистрировать роутер**

В `app/api/router.py` найти секцию authenticated routers и добавить:

```python
from app.api.endpoints import release_notes  # noqa: E402
...
authenticated_router.include_router(release_notes.router)
```

(Точное место — туда же, где `analytics`, `sync` и т.д., с `Depends(get_current_user)`.)

- [ ] **Step 6: Прогнать тесты**

```bash
py -3.10 -m pytest tests/api/test_release_notes_user_api.py -v
```

Ожидание: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/release_note.py app/api/endpoints/release_notes.py app/api/router.py tests/api/test_release_notes_user_api.py
git commit -m "feat(release-notes): пользовательский API /release-notes/{unread,all,mark-seen}"
```

---

### Task 4: Админ-эндпоинты + тесты

**Files:**
- Create: `app/api/endpoints/admin_release_notes.py`
- Modify: `app/api/router.py`
- Create: `tests/api/test_release_notes_admin_api.py`

- [ ] **Step 1: Падающие тесты**

`tests/api/test_release_notes_admin_api.py`:

```python
"""Админ-CRUD ленты «Что нового»."""


def test_list_drafts_admin_only(client_auth, current_user, db_session):
    # обычный пользователь — 403
    r = client_auth.get("/api/v1/admin/release-notes/drafts")
    assert r.status_code == 403


def test_admin_list_drafts(client_admin, db_session):
    from app.models.release_note import ReleaseNote
    n = ReleaseNote(
        note_type="new", section="general",
        title="Draft", description="Desc",
    )
    db_session.add(n)
    db_session.commit()
    r = client_admin.get("/api/v1/admin/release-notes/drafts")
    assert r.status_code == 200
    drafts = r.json()
    assert len(drafts) == 1
    assert drafts[0]["version"] is None


def test_admin_create_note(client_admin, db_session):
    r = client_admin.post(
        "/api/v1/admin/release-notes",
        json={
            "note_type": "fix",
            "section": "sync",
            "title": "Кнопка работает",
            "description": "Тестовый фикс",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Кнопка работает"
    assert body["version"] is None


def test_admin_create_rejects_unknown_type(client_admin):
    r = client_admin.post(
        "/api/v1/admin/release-notes",
        json={
            "note_type": "wat", "section": "general",
            "title": "X", "description": "Y",
        },
    )
    assert r.status_code == 400


def test_admin_update_note(client_admin, db_session):
    from app.models.release_note import ReleaseNote
    n = ReleaseNote(
        note_type="new", section="general",
        title="Old", description="Old desc",
    )
    db_session.add(n)
    db_session.commit()
    r = client_admin.patch(
        f"/api/v1/admin/release-notes/{n.id}",
        json={"title": "New title", "is_hidden": True},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "New title"
    assert r.json()["is_hidden"] is True


def test_admin_delete_note(client_admin, db_session):
    from app.models.release_note import ReleaseNote
    n = ReleaseNote(
        note_type="new", section="general",
        title="X", description="Y",
    )
    db_session.add(n)
    db_session.commit()
    r = client_admin.delete(f"/api/v1/admin/release-notes/{n.id}")
    assert r.status_code == 204
    assert db_session.query(ReleaseNote).filter_by(id=n.id).first() is None


def test_admin_publish_drafts(client_admin, db_session):
    from app.models.release_note import ReleaseNote
    db_session.add(ReleaseNote(
        note_type="new", section="general",
        title="X", description="Y",
    ))
    db_session.add(ReleaseNote(
        note_type="fix", section="sync",
        title="A", description="B",
    ))
    db_session.commit()
    r = client_admin.post(
        "/api/v1/admin/release-notes/publish",
        json={"version": "v1.2.0"},
    )
    assert r.status_code == 200
    assert r.json()["published_count"] == 2
    all_notes = db_session.query(ReleaseNote).all()
    assert all(n.version == "v1.2.0" for n in all_notes)


def test_admin_publish_no_drafts_returns_zero(client_admin):
    r = client_admin.post(
        "/api/v1/admin/release-notes/publish",
        json={"version": "v1.2.0"},
    )
    assert r.status_code == 400  # запрещаем пустую публикацию


def test_admin_delete_version_reverts_to_drafts(client_admin, db_session):
    from app.models.release_note import ReleaseNote
    db_session.add(ReleaseNote(
        note_type="new", section="general", title="X",
        description="Y", version="v1.5.0",
    ))
    db_session.commit()
    r = client_admin.delete("/api/v1/admin/release-notes/version/v1.5.0")
    assert r.status_code == 204
    notes = db_session.query(ReleaseNote).all()
    assert all(n.version is None for n in notes)
```

- [ ] **Step 2: Запустить — должны падать**

```bash
py -3.10 -m pytest tests/api/test_release_notes_admin_api.py -v
```

Ожидание: 404 на роутах.

- [ ] **Step 3: Реализовать роутер**

`app/api/endpoints/admin_release_notes.py`:

```python
"""Админ-эндпоинты ленты «Что нового»."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import require_admin
from app.database import get_db
from app.models.release_note import ReleaseNote
from app.models.user import User
from app.schemas.release_note import (
    ReleaseNoteCreate,
    ReleaseNoteResponse,
    ReleaseNoteUpdate,
)
from app.services.release_note_service import ReleaseNoteService

router = APIRouter(prefix="/admin/release-notes", tags=["release-notes-admin"])


class PublishRequest(BaseModel):
    version: str


class PublishResponse(BaseModel):
    published_count: int
    version: str


@router.get("/drafts", response_model=list[ReleaseNoteResponse])
def list_drafts(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ReleaseNote]:
    return ReleaseNoteService(db).list_drafts()


@router.get("/versions/{version}", response_model=list[ReleaseNoteResponse])
def list_version(
    version: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ReleaseNote]:
    return ReleaseNoteService(db).notes_for_versions([version], include_hidden=True)


@router.post(
    "", response_model=ReleaseNoteResponse, status_code=status.HTTP_201_CREATED
)
def create_note(
    body: ReleaseNoteCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReleaseNote:
    try:
        return ReleaseNoteService(db).create_draft(
            note_type=body.note_type,
            section=body.section,
            title=body.title,
            description=body.description,
            help_link=body.help_link,
            created_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{note_id}", response_model=ReleaseNoteResponse)
def update_note(
    note_id: str,
    body: ReleaseNoteUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReleaseNote:
    note = db.query(ReleaseNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    note = db.query(ReleaseNote).filter_by(id=note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(note)
    db.commit()


@router.post("/publish", response_model=PublishResponse)
def publish_drafts(
    body: PublishRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PublishResponse:
    svc = ReleaseNoteService(db)
    n = svc.publish_drafts(body.version)
    if n == 0:
        raise HTTPException(
            status_code=400, detail="Нет черновиков для публикации"
        )
    return PublishResponse(published_count=n, version=body.version)


@router.delete(
    "/version/{version}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_version(
    version: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    notes = db.query(ReleaseNote).filter_by(version=version).all()
    for n in notes:
        n.version = None
    db.commit()
```

- [ ] **Step 4: Зарегистрировать роутер**

В `app/api/router.py` (в admin-only секции, рядом с `admin_users`):
```python
from app.api.endpoints import admin_release_notes
...
admin_router.include_router(admin_release_notes.router)
```

- [ ] **Step 5: Прогнать тесты**

```bash
py -3.10 -m pytest tests/api/test_release_notes_admin_api.py -v
```

Ожидание: 9 passed.

Возможны проблемы с фикстурой `client_admin` — если её нет, проверить `tests/conftest.py` и создать по аналогии с `client_auth`.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/admin_release_notes.py app/api/router.py tests/api/test_release_notes_admin_api.py
git commit -m "feat(release-notes): админ-CRUD + publish/delete-version"
```

---

### Task 4.5: Инициализация last_seen для нового пользователя

При создании пользователя ставим `last_seen_release_version` в максимальную опубликованную версию — иначе новенький получит модалку со всеми старыми релизами при первом входе.

**Files:**
- Modify: `app/api/endpoints/admin_users.py`
- Modify: `tests/api/test_admin_users.py` (или создать `test_admin_users_release_init.py`)

- [ ] **Step 1: Падающий тест**

В `tests/api/test_release_notes_admin_api.py` (тот же файл) добавить:

```python
def test_new_user_inherits_latest_version(client_admin, db_session):
    """Новый пользователь получает last_seen_release_version = последняя опубликованная."""
    from app.models.release_note import ReleaseNote
    from app.models.user import User
    db_session.add(ReleaseNote(
        note_type="new", section="general",
        title="X", description="Y", version="v1.5.0",
    ))
    db_session.commit()
    r = client_admin.post(
        "/api/v1/admin/users/",
        json={
            "email": "new@x.com", "password": "secret123",
            "display_name": "Newbie", "role": "manager",
        },
    )
    assert r.status_code == 201
    u = db_session.query(User).filter_by(email="new@x.com").first()
    assert u.last_seen_release_version == "v1.5.0"


def test_new_user_no_versions_yet_keeps_null(client_admin, db_session):
    from app.models.user import User
    r = client_admin.post(
        "/api/v1/admin/users/",
        json={
            "email": "empty@x.com", "password": "secret123",
            "display_name": "Empty", "role": "manager",
        },
    )
    assert r.status_code == 201
    u = db_session.query(User).filter_by(email="empty@x.com").first()
    assert u.last_seen_release_version is None
```

- [ ] **Step 2: Запустить — должны падать (last_seen не выставляется)**

```bash
py -3.10 -m pytest tests/api/test_release_notes_admin_api.py::test_new_user_inherits_latest_version -v
```

- [ ] **Step 3: Изменить `admin_users.create_user`**

В `app/api/endpoints/admin_users.py` в функции `create_user` после `User(...)` объекта (перед `_repo.create`) добавить:

```python
    from app.services.release_note_service import ReleaseNoteService
    versions = ReleaseNoteService(db).list_published_versions()
    if versions:
        user.last_seen_release_version = versions[-1]  # max — последний после sort
```

- [ ] **Step 4: Тесты проходят**

```bash
py -3.10 -m pytest tests/api/test_release_notes_admin_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/endpoints/admin_users.py tests/api/test_release_notes_admin_api.py
git commit -m "feat(release-notes): новый юзер не получает модалку со старыми релизами"
```

---

## Phase 3 — CLI и интеграция в релиз

### Task 5: CLI-скрипт `release_note.py`

**Files:**
- Create: `scripts/release_note.py`
- Create: `tests/test_release_note_cli.py`

- [ ] **Step 1: Падающие тесты CLI**

`tests/test_release_note_cli.py`:

```python
"""Тесты CLI-скрипта добавления заметок."""
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.release_note import ReleaseNote


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "release_note.py"


def _run(*args: str, env_db_url: str) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    env["DATABASE_URL"] = env_db_url
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def test_add_command_creates_draft(db_session: Session, tmp_path):
    # реальный CLI не используем — вызываем main() напрямую с подменой
    from scripts.release_note import main
    rc = main([
        "add",
        "--type", "fix",
        "--section", "sync",
        "--title", "Test",
        "--description", "Desc",
    ], db=db_session)
    assert rc == 0
    notes = db_session.query(ReleaseNote).all()
    assert len(notes) == 1
    assert notes[0].note_type == "fix"
    assert notes[0].section == "sync"
    assert notes[0].version is None


def test_add_with_version_publishes_directly(db_session: Session):
    from scripts.release_note import main
    rc = main([
        "add",
        "--type", "new",
        "--section", "scenarios",
        "--title", "Retro entry",
        "--description", "Description",
        "--version", "v1.1.0",
    ], db=db_session)
    assert rc == 0
    note = db_session.query(ReleaseNote).first()
    assert note.version == "v1.1.0"


def test_bind_drafts_to_version(db_session: Session):
    from scripts.release_note import main
    main(["add", "--type", "fix", "--section", "sync",
          "--title", "X", "--description", "Y"], db=db_session)
    main(["add", "--type", "new", "--section", "general",
          "--title", "A", "--description", "B"], db=db_session)
    rc = main(["bind", "--version", "v1.2.0"], db=db_session)
    assert rc == 0
    notes = db_session.query(ReleaseNote).all()
    assert all(n.version == "v1.2.0" for n in notes)


def test_invalid_type_returns_nonzero(db_session: Session, capsys):
    from scripts.release_note import main
    rc = main([
        "add", "--type", "wat", "--section", "general",
        "--title", "X", "--description", "Y",
    ], db=db_session)
    assert rc != 0
```

- [ ] **Step 2: Запустить — должны падать**

```bash
py -3.10 -m pytest tests/test_release_note_cli.py -v
```

Ожидание: ImportError `scripts.release_note`.

- [ ] **Step 3: Реализовать CLI**

`scripts/release_note.py`:

```python
"""CLI для добавления записей в ленту «Что нового».

Использование:
    py -3.10 scripts/release_note.py add --type fix --section sync \
        --title "..." --description "..."
    py -3.10 scripts/release_note.py add --type new --section scenarios \
        --title "..." --description "..." --version v1.1.0  # ретро
    py -3.10 scripts/release_note.py bind --version v1.2.0
"""
from __future__ import annotations

import argparse
import io
import sys
from typing import Optional

from sqlalchemy.orm import Session


def _get_db() -> Session:
    from app.database import SessionLocal
    return SessionLocal()


def cmd_add(args, db: Session) -> int:
    from app.services.release_note_service import ReleaseNoteService
    svc = ReleaseNoteService(db)
    try:
        note = svc.create_draft(
            note_type=args.type,
            section=args.section,
            title=args.title,
            description=args.description,
            help_link=args.help_link,
        )
    except ValueError as e:
        sys.stderr.write(f"Ошибка: {e}\n")
        return 2
    if args.version:
        note.version = args.version
        db.commit()
    sys.stdout.write(f"OK: {note.id} (version={note.version or 'draft'})\n")
    return 0


def cmd_bind(args, db: Session) -> int:
    from app.services.release_note_service import ReleaseNoteService
    n = ReleaseNoteService(db).publish_drafts(args.version)
    sys.stdout.write(f"Привязано {n} заметок к {args.version}\n")
    return 0


def main(argv: Optional[list[str]] = None, db: Optional[Session] = None) -> int:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    p = argparse.ArgumentParser(description="Release notes CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Добавить запись (черновик или ретро)")
    p_add.add_argument("--type", required=True, choices=["new", "improvement", "fix"])
    p_add.add_argument("--section", required=True)
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--description", required=True)
    p_add.add_argument("--help-link", default=None)
    p_add.add_argument("--version", default=None, help="Сразу под версию (ретро)")
    p_add.set_defaults(func=cmd_add)

    p_bind = sub.add_parser("bind", help="Привязать черновики к версии")
    p_bind.add_argument("--version", required=True)
    p_bind.set_defaults(func=cmd_bind)

    args = p.parse_args(argv)
    if db is None:
        db = _get_db()
        try:
            return args.func(args, db)
        finally:
            db.close()
    return args.func(args, db)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Прогнать тесты**

```bash
py -3.10 -m pytest tests/test_release_note_cli.py -v
```

Ожидание: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/release_note.py tests/test_release_note_cli.py
git commit -m "feat(release-notes): CLI scripts/release_note.py — add + bind"
```

---

### Task 6: Интеграция в `scripts/release.py`

**Files:**
- Modify: `scripts/release.py`

- [ ] **Step 1: Изменить release.py**

После успешного `subprocess.run(["make", "release", ...])` (строка 199) добавить шаг привязки:

```python
    print(f"\nЗапуск: make release VERSION={target}")
    result = subprocess.run(
        ["make", "release", f"VERSION={target}"], cwd=REPO_ROOT, check=False
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    # Привязать накопленные черновики release notes к новой версии.
    print(f"\nПривязка черновиков release notes к {target}...")
    bind = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "release_note.py"),
         "bind", "--version", target],
        cwd=REPO_ROOT, check=False,
    )
    if bind.returncode != 0:
        sys.stderr.write(
            "Не удалось привязать черновики. Сделай вручную: "
            f"py -3.10 scripts/release_note.py bind --version {target}\n"
        )
    print(
        "\nГотово. Открой /settings → «Что нового» — проверь записи "
        "и опубликуй пользователям."
    )
```

- [ ] **Step 2: Smoke — dry-run должен работать**

```bash
py -3.10 scripts/release.py --dry-run
```

Ожидание: выводит предложение, не падает.

- [ ] **Step 3: Commit**

```bash
git add scripts/release.py
git commit -m "feat(release-notes): release.py привязывает черновики после тэга"
```

---

## Phase 4 — Frontend: API + типы

### Task 7: Типы + API-клиент + хуки

**Files:**
- Create: `frontend/src/types/releaseNotes.ts`
- Create: `frontend/src/api/releaseNotes.ts`
- Create: `frontend/src/hooks/useReleaseNotes.ts`

- [ ] **Step 1: Типы**

`frontend/src/types/releaseNotes.ts`:

```typescript
export type ReleaseNoteType = 'new' | 'improvement' | 'fix';

export type ReleaseSection =
  | 'scenarios' | 'resources' | 'analytics' | 'issues'
  | 'dashboard' | 'backlog' | 'sync' | 'settings' | 'general';

export interface ReleaseNote {
  id: string;
  version: string | null;
  note_type: ReleaseNoteType;
  section: ReleaseSection;
  title: string;
  description: string;
  help_link: string | null;
  is_hidden: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface VersionFeed {
  version: string;
  notes: ReleaseNote[];
}

export interface UnreadFeed {
  unread_versions: string[];
  feeds: VersionFeed[];
}

export interface ReleaseNoteCreate {
  note_type: ReleaseNoteType;
  section: ReleaseSection;
  title: string;
  description: string;
  help_link?: string | null;
}

export interface ReleaseNoteUpdate {
  note_type?: ReleaseNoteType;
  section?: ReleaseSection;
  title?: string;
  description?: string;
  help_link?: string | null;
  is_hidden?: boolean;
  sort_order?: number;
}

export const NOTE_TYPE_LABELS: Record<ReleaseNoteType, string> = {
  new: 'Новое',
  improvement: 'Улучшение',
  fix: 'Исправление',
};

export const NOTE_TYPE_COLORS: Record<ReleaseNoteType, string> = {
  new: '#52c41a',
  improvement: '#1677ff',
  fix: '#8c8c8c',
};

export const SECTION_LABELS: Record<ReleaseSection, string> = {
  scenarios: 'Сценарии',
  resources: 'Ресурсы',
  analytics: 'Аналитика',
  issues: 'Анализ задач',
  dashboard: 'Дашборд',
  backlog: 'Бэклог',
  sync: 'Синхронизация',
  settings: 'Настройки',
  general: 'Общее',
};
```

- [ ] **Step 2: API-клиент**

`frontend/src/api/releaseNotes.ts`:

```typescript
import { api } from './client';
import type {
  ReleaseNote, ReleaseNoteCreate, ReleaseNoteUpdate, UnreadFeed,
} from '../types/releaseNotes';

export const releaseNotesApi = {
  getUnread: () => api.get<UnreadFeed>('/release-notes/unread'),
  getAll: () => api.get<UnreadFeed>('/release-notes/all'),
  markSeen: (version: string) =>
    api.post<void>('/release-notes/mark-seen', { version }),

  // admin
  listDrafts: () =>
    api.get<ReleaseNote[]>('/admin/release-notes/drafts'),
  listVersion: (version: string) =>
    api.get<ReleaseNote[]>(`/admin/release-notes/versions/${version}`),
  create: (body: ReleaseNoteCreate) =>
    api.post<ReleaseNote>('/admin/release-notes', body),
  update: (id: string, body: ReleaseNoteUpdate) =>
    api.patch<ReleaseNote>(`/admin/release-notes/${id}`, body),
  remove: (id: string) =>
    api.delete<void>(`/admin/release-notes/${id}`),
  publish: (version: string) =>
    api.post<{ published_count: number; version: string }>(
      '/admin/release-notes/publish', { version }
    ),
  deleteVersion: (version: string) =>
    api.delete<void>(`/admin/release-notes/version/${version}`),
};
```

- [ ] **Step 3: Хуки TanStack Query**

`frontend/src/hooks/useReleaseNotes.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { releaseNotesApi } from '../api/releaseNotes';
import type { ReleaseNoteCreate, ReleaseNoteUpdate } from '../types/releaseNotes';

const KEY_UNREAD = ['release-notes', 'unread'] as const;
const KEY_ALL = ['release-notes', 'all'] as const;
const KEY_DRAFTS = ['release-notes', 'drafts'] as const;

export function useUnreadReleaseNotes() {
  return useQuery({
    queryKey: KEY_UNREAD,
    queryFn: () => releaseNotesApi.getUnread(),
    staleTime: 60_000,
  });
}

export function useAllReleaseNotes() {
  return useQuery({
    queryKey: KEY_ALL,
    queryFn: () => releaseNotesApi.getAll(),
    staleTime: 60_000,
  });
}

export function useMarkSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.markSeen(version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_UNREAD });
      qc.invalidateQueries({ queryKey: KEY_ALL });
    },
  });
}

export function useDraftReleaseNotes() {
  return useQuery({
    queryKey: KEY_DRAFTS,
    queryFn: () => releaseNotesApi.listDrafts(),
    staleTime: 30_000,
  });
}

export function useCreateReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReleaseNoteCreate) => releaseNotesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useUpdateReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReleaseNoteUpdate }) =>
      releaseNotesApi.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useDeleteReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => releaseNotesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function usePublishReleaseNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.publish(version),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useDeleteVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.deleteVersion(version),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}
```

- [ ] **Step 4: Билд проходит**

```bash
cd frontend && npm run build
```

Ожидание: успешный билд.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/releaseNotes.ts frontend/src/api/releaseNotes.ts frontend/src/hooks/useReleaseNotes.ts
git commit -m "feat(release-notes): фронт-типы + API-обёртки + хуки"
```

---

## Phase 5 — Frontend: пользовательский UI

### Task 8: Модалка «Что нового»

**Files:**
- Create: `frontend/src/components/release-notes/WhatsNewModal.tsx`
- Create: `frontend/src/components/release-notes/NoteCard.tsx`

- [ ] **Step 1: NoteCard — одна карточка пункта**

`frontend/src/components/release-notes/NoteCard.tsx`:

```typescript
import { Tag } from 'antd';
import {
  NOTE_TYPE_COLORS, NOTE_TYPE_LABELS, SECTION_LABELS,
} from '../../types/releaseNotes';
import type { ReleaseNote } from '../../types/releaseNotes';

interface Props {
  note: ReleaseNote;
}

export default function NoteCard({ note }: Props) {
  return (
    <div
      style={{
        padding: '12px 16px',
        background: 'rgba(255,255,255,0.03)',
        borderRadius: 6,
        borderLeft: `3px solid ${NOTE_TYPE_COLORS[note.note_type]}`,
        marginBottom: 8,
      }}
    >
      <div style={{ marginBottom: 4 }}>
        <Tag color={NOTE_TYPE_COLORS[note.note_type]} style={{ marginRight: 8 }}>
          {NOTE_TYPE_LABELS[note.note_type]}
        </Tag>
        <Tag style={{ marginRight: 8 }}>{SECTION_LABELS[note.section]}</Tag>
        <span style={{ fontWeight: 600 }}>{note.title}</span>
      </div>
      <div style={{ color: 'rgba(255,255,255,0.65)', whiteSpace: 'pre-line' }}>
        {note.description}
      </div>
      {note.help_link && (
        <div style={{ marginTop: 4 }}>
          <a href={note.help_link} target="_blank" rel="noreferrer">
            Подробнее в справке →
          </a>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: WhatsNewModal**

`frontend/src/components/release-notes/WhatsNewModal.tsx`:

```typescript
import { useMemo, useState } from 'react';
import { Modal, Button, Collapse, Space, Empty } from 'antd';
import NoteCard from './NoteCard';
import type { VersionFeed, ReleaseNote } from '../../types/releaseNotes';

interface Props {
  open: boolean;
  feeds: VersionFeed[];
  onClose: () => void;
  onMarkSeen: (latestVersion: string) => void;
  onShowAllVersions?: () => void;
}

function groupByType(notes: ReleaseNote[]) {
  return {
    new: notes.filter((n) => n.note_type === 'new'),
    improvement: notes.filter((n) => n.note_type === 'improvement'),
    fix: notes.filter((n) => n.note_type === 'fix'),
  };
}

export default function WhatsNewModal({
  open, feeds, onClose, onMarkSeen, onShowAllVersions,
}: Props) {
  const latestVersion = feeds[0]?.version ?? '';
  const handleOk = () => {
    if (latestVersion) onMarkSeen(latestVersion);
    onClose();
  };

  if (feeds.length === 0) {
    return (
      <Modal open={open} onCancel={onClose} footer={null} title="Что нового">
        <Empty description="Пока ничего нового" />
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={720}
      title={
        feeds.length === 1
          ? `Что нового в ${feeds[0].version}`
          : `Что нового (${feeds.length} версий)`
      }
      footer={[
        onShowAllVersions && (
          <Button key="all" type="link" onClick={onShowAllVersions}>
            Все версии
          </Button>
        ),
        <Button key="ok" type="primary" onClick={handleOk}>
          Понятно
        </Button>,
      ].filter(Boolean) as React.ReactNode[]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {feeds.map((feed) => {
          const groups = groupByType(feed.notes);
          return (
            <div key={feed.version}>
              {feeds.length > 1 && (
                <h3 style={{ marginTop: 0, marginBottom: 12 }}>{feed.version}</h3>
              )}
              {groups.new.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <h4 style={{ color: '#52c41a', marginBottom: 8 }}>Новое</h4>
                  {groups.new.map((n) => <NoteCard key={n.id} note={n} />)}
                </section>
              )}
              {groups.improvement.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <h4 style={{ color: '#1677ff', marginBottom: 8 }}>Улучшения</h4>
                  {groups.improvement.map((n) => <NoteCard key={n.id} note={n} />)}
                </section>
              )}
              {groups.fix.length > 0 && (
                <FixesSection notes={groups.fix} />
              )}
            </div>
          );
        })}
      </Space>
    </Modal>
  );
}

function FixesSection({ notes }: { notes: ReleaseNote[] }) {
  return (
    <Collapse
      ghost
      items={[
        {
          key: 'fixes',
          label: (
            <span style={{ color: '#8c8c8c' }}>
              Исправления ({notes.length})
            </span>
          ),
          children: notes.map((n) => <NoteCard key={n.id} note={n} />),
        },
      ]}
    />
  );
}
```

- [ ] **Step 3: Билд проходит**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/release-notes/
git commit -m "feat(release-notes): WhatsNewModal + NoteCard"
```

---

### Task 9: Встраивание модалки + красная точка

**Files:**
- Modify: `frontend/src/components/Layout/AppLayout.tsx`
- Modify: `frontend/src/components/Layout/GlobalHelpButton.tsx`

- [ ] **Step 1: Найти AppLayout и добавить модалку**

Открыть `frontend/src/components/Layout/AppLayout.tsx`, понять структуру (где живёт Layout/контент). Внутрь корневого `<Layout>` добавить компонент-обёртку с модалкой, например `<WhatsNewGate />`:

Создать `frontend/src/components/release-notes/WhatsNewGate.tsx`:

```typescript
import { useEffect, useState } from 'react';
import { useUnreadReleaseNotes, useMarkSeen } from '../../hooks/useReleaseNotes';
import { useAuth } from '../../hooks/useAuth';
import WhatsNewModal from './WhatsNewModal';

export default function WhatsNewGate() {
  const { user } = useAuth();
  const { data } = useUnreadReleaseNotes();
  const markSeen = useMarkSeen();
  const [open, setOpen] = useState(false);
  const [shownVersion, setShownVersion] = useState<string | null>(null);

  // Открыть модалку при первом получении непрочитанных версий.
  useEffect(() => {
    if (!user) return;
    if (!data) return;
    if (data.unread_versions.length === 0) return;
    const top = data.unread_versions[data.unread_versions.length - 1]; // latest
    if (top !== shownVersion) {
      setOpen(true);
      setShownVersion(top);
    }
  }, [user, data, shownVersion]);

  if (!user || !data) return null;
  if (data.feeds.length === 0) return null;

  return (
    <WhatsNewModal
      open={open}
      feeds={data.feeds}
      onClose={() => setOpen(false)}
      onMarkSeen={(v) => markSeen.mutate(v)}
    />
  );
}
```

В `AppLayout.tsx` импортировать и добавить `<WhatsNewGate />` в корень (рядом с другими глобальными компонентами).

- [ ] **Step 2: Красная точка на иконке справки**

Изменить `frontend/src/components/Layout/GlobalHelpButton.tsx`. Добавить `Badge` от AntD когда есть непрочитанные:

```typescript
import { useState } from 'react';
import { Button, Badge } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import HelpDrawer from '../shared/HelpDrawer';
import { useHelpContext } from '../../contexts/HelpContext';
import { useUnreadReleaseNotes } from '../../hooks/useReleaseNotes';

export default function GlobalHelpButton() {
  const { current } = useHelpContext();
  const [open, setOpen] = useState(false);
  const { data: unread } = useUnreadReleaseNotes();
  const hasUnread = (unread?.unread_versions.length ?? 0) > 0;
  const disabled = !current && !hasUnread;

  return (
    <>
      <Badge dot={hasUnread} offset={[-4, 4]} color="red">
        <Button
          type="text"
          size="small"
          icon={<QuestionCircleOutlined />}
          onClick={() => setOpen(true)}
          disabled={disabled}
          title={
            hasUnread
              ? 'Есть новые обновления — посмотри «Что нового»'
              : disabled ? 'Для этого раздела справки пока нет' : 'Справка'
          }
          style={{
            color: disabled ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.55)',
          }}
        />
      </Badge>
      <HelpDrawer
        open={open}
        onClose={() => setOpen(false)}
        title={current?.title || 'Справка'}
        content={current?.content || ''}
        imageBase="/help-assets/"
        defaultTab={hasUnread ? 'whats-new' : 'help'}
      />
    </>
  );
}
```

Внутри `HelpDrawer.tsx` нужна вкладка «Все версии» — это Task 10.

- [ ] **Step 3: Билд проходит**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/release-notes/WhatsNewGate.tsx frontend/src/components/Layout/
git commit -m "feat(release-notes): встроена модалка + красная точка на иконке справки"
```

---

### Task 10: Вкладка «Все версии» в HelpDrawer

**Files:**
- Modify: `frontend/src/components/shared/HelpDrawer.tsx`
- Create: `frontend/src/components/release-notes/AllVersionsView.tsx`

- [ ] **Step 1: AllVersionsView**

`frontend/src/components/release-notes/AllVersionsView.tsx`:

```typescript
import { useState } from 'react';
import { Checkbox, Collapse, Empty } from 'antd';
import { useAllReleaseNotes } from '../../hooks/useReleaseNotes';
import NoteCard from './NoteCard';

export default function AllVersionsView() {
  const { data, isLoading } = useAllReleaseNotes();
  const [hideFixes, setHideFixes] = useState(false);

  if (isLoading) return <div>Загрузка…</div>;
  if (!data || data.feeds.length === 0) {
    return <Empty description="Версий пока нет" />;
  }

  return (
    <div>
      <Checkbox
        checked={hideFixes}
        onChange={(e) => setHideFixes(e.target.checked)}
        style={{ marginBottom: 16 }}
      >
        Скрыть исправления
      </Checkbox>
      <Collapse
        defaultActiveKey={data.feeds.length > 0 ? [data.feeds[0].version] : []}
        items={data.feeds.map((feed) => {
          const visible = hideFixes
            ? feed.notes.filter((n) => n.note_type !== 'fix')
            : feed.notes;
          return {
            key: feed.version,
            label: feed.version,
            children: visible.length === 0
              ? <Empty description="Здесь нет записей с учётом фильтра" />
              : visible.map((n) => <NoteCard key={n.id} note={n} />),
          };
        })}
      />
    </div>
  );
}
```

- [ ] **Step 2: Добавить вкладку в HelpDrawer**

Существующий `HelpDrawer.tsx` рендерит один markdown через `ReactMarkdown` с custom `components` (h1-h4, table, img с `imageBase`, p, code, a). Сохранить весь этот рендер, обернуть в `Tabs`.

Полностью переписать `frontend/src/components/shared/HelpDrawer.tsx`:

```typescript
import { useMemo, type ReactNode } from 'react';
import { Drawer, Tabs, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DARK_THEME } from '../../utils/constants';
import AllVersionsView from '../release-notes/AllVersionsView';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Raw markdown content. Import via `?raw` from docs/help/*.md */
  content: string;
  /** Base URL for relative image paths inside markdown. Default: /docs/help/ */
  imageBase?: string;
  /** Если есть непрочитанные релизы — открыть вкладку «Что нового» по умолчанию. */
  defaultTab?: 'help' | 'whats-new';
}

export default function HelpDrawer({
  open, onClose, title, content, imageBase = '/docs/help/', defaultTab = 'help',
}: Props) {
  const components = useMemo(() => ({
    h1: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={2} style={{ marginTop: 0, color: DARK_THEME.cyanPrimary }}>
        {children}
      </Typography.Title>
    ),
    h2: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={3} style={{ marginTop: 28, color: DARK_THEME.cyanPrimary }}>
        {children}
      </Typography.Title>
    ),
    h3: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={4} style={{ marginTop: 22 }}>{children}</Typography.Title>
    ),
    h4: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={5} style={{ marginTop: 18 }}>{children}</Typography.Title>
    ),
    table: ({ children }: { children?: ReactNode }) => (
      <div className="help-table-wrap">
        <table className="help-table">{children}</table>
      </div>
    ),
    img: (props: { src?: string; alt?: string }) => {
      const src = props.src && !/^https?:|^\//.test(props.src)
        ? imageBase + props.src.replace(/^\.\//, '')
        : props.src;
      return (
        <img
          src={src} alt={props.alt} title={props.alt}
          style={{
            display: 'block', maxWidth: '100%', borderRadius: 6,
            border: `1px solid ${DARK_THEME.border}`, margin: '12px 0 6px 0',
          }}
        />
      );
    },
    p: ({ children }: { children?: ReactNode }) => {
      const arr = Array.isArray(children) ? children : [children];
      const first = arr.find(c => c !== null && c !== undefined && c !== '');
      if (
        arr.filter(c => c !== null && c !== undefined && c !== '' && !(typeof c === 'string' && c.trim() === '')).length === 1
        && first && typeof first === 'object' && 'type' in (first as object)
        && (first as { type?: unknown }).type === 'img'
      ) {
        return <>{children}</>;
      }
      return <p>{children}</p>;
    },
    code: ({ children, className }: { children?: ReactNode; className?: string }) => {
      const isBlock = className?.startsWith('language-');
      if (isBlock) return <pre className="help-code-block"><code>{children}</code></pre>;
      return <code className="help-code-inline">{children}</code>;
    },
    a: ({ href, children }: { href?: string; children?: ReactNode }) => (
      <Typography.Link href={href} target={href?.startsWith('http') ? '_blank' : undefined} rel="noreferrer">
        {children}
      </Typography.Link>
    ),
  }), [imageBase]);

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      placement="right"
      destroyOnClose
      styles={{
        body: { padding: '20px 28px', background: DARK_THEME.cardBg },
        header: { background: DARK_THEME.cardBg, borderBottom: `1px solid ${DARK_THEME.border}` },
        wrapper: { width: 'min(960px, 70vw)' },
      }}
    >
      <Tabs
        defaultActiveKey={defaultTab}
        items={[
          {
            key: 'help',
            label: 'Справка',
            disabled: !content,
            children: (
              <div className="help-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
                  {content}
                </ReactMarkdown>
              </div>
            ),
          },
          {
            key: 'whats-new',
            label: 'Что нового',
            children: <AllVersionsView />,
          },
        ]}
      />
    </Drawer>
  );
}
```

Также обновить `GlobalHelpButton.tsx` чтобы передавать `defaultTab` вместо `showWhatsNew`:

```typescript
<HelpDrawer
  open={open}
  onClose={() => setOpen(false)}
  title={current?.title || 'Справка'}
  content={current?.content || ''}
  imageBase="/help-assets/"
  defaultTab={hasUnread ? 'whats-new' : 'help'}
/>
```

- [ ] **Step 3: Билд проходит**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/release-notes/AllVersionsView.tsx frontend/src/components/shared/HelpDrawer.tsx
git commit -m "feat(release-notes): вкладка «Что нового» в HelpDrawer с фильтром «Скрыть исправления»"
```

---

## Phase 6 — Admin UI

### Task 11: Админ-вкладка `/settings` → «Что нового»

**Files:**
- Create: `frontend/src/components/settings/ReleaseNotesAdminTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: ReleaseNotesAdminTab**

`frontend/src/components/settings/ReleaseNotesAdminTab.tsx`:

```typescript
import { useState } from 'react';
import {
  Button, Table, Form, Input, Modal, Select, Space, Popconfirm,
  App, Switch, Tag, Collapse, Empty,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined, EyeOutlined, RocketOutlined,
} from '@ant-design/icons';
import {
  useDraftReleaseNotes, useAllReleaseNotes,
  useCreateReleaseNote, useUpdateReleaseNote, useDeleteReleaseNote,
  usePublishReleaseNotes, useDeleteVersion,
} from '../../hooks/useReleaseNotes';
import {
  NOTE_TYPE_LABELS, NOTE_TYPE_COLORS, SECTION_LABELS,
} from '../../types/releaseNotes';
import type {
  ReleaseNote, ReleaseNoteCreate, ReleaseNoteUpdate, ReleaseNoteType, ReleaseSection,
} from '../../types/releaseNotes';
import WhatsNewModal from '../release-notes/WhatsNewModal';

export default function ReleaseNotesAdminTab() {
  const { notification } = App.useApp();
  const drafts = useDraftReleaseNotes();
  const all = useAllReleaseNotes();
  const createMut = useCreateReleaseNote();
  const updateMut = useUpdateReleaseNote();
  const deleteMut = useDeleteReleaseNote();
  const publishMut = usePublishReleaseNotes();
  const deleteVersionMut = useDeleteVersion();

  const [editing, setEditing] = useState<ReleaseNote | null>(null);
  const [adding, setAdding] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [publishVersion, setPublishVersion] = useState('');

  const columns = [
    {
      title: 'Тип', dataIndex: 'note_type', width: 130,
      render: (t: ReleaseNoteType) => (
        <Tag color={NOTE_TYPE_COLORS[t]}>{NOTE_TYPE_LABELS[t]}</Tag>
      ),
    },
    {
      title: 'Раздел', dataIndex: 'section', width: 140,
      render: (s: ReleaseSection) => SECTION_LABELS[s],
    },
    { title: 'Заголовок', dataIndex: 'title' },
    {
      title: 'Скрыт?', dataIndex: 'is_hidden', width: 80,
      render: (h: boolean, row: ReleaseNote) => (
        <Switch
          checked={h}
          onChange={(v) => updateMut.mutate({
            id: row.id, body: { is_hidden: v },
          })}
        />
      ),
    },
    {
      title: '', key: 'actions', width: 100,
      render: (_: unknown, row: ReleaseNote) => (
        <Space>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => setEditing(row)}
          />
          <Popconfirm
            title="Удалить запись?"
            onConfirm={() => deleteMut.mutate(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>
          Добавить запись
        </Button>
        <Button
          icon={<EyeOutlined />}
          onClick={() => setPreviewOpen(true)}
          disabled={!drafts.data || drafts.data.length === 0}
        >
          Посмотреть как пользователь
        </Button>
        <Button
          type="primary"
          icon={<RocketOutlined />}
          onClick={() => setPublishOpen(true)}
          disabled={!drafts.data || drafts.data.length === 0}
        >
          Выпустить под версию…
        </Button>
      </Space>

      <h3>Готовится к выпуску ({drafts.data?.length ?? 0})</h3>
      <Table
        size="small"
        rowKey="id"
        loading={drafts.isLoading}
        dataSource={drafts.data ?? []}
        columns={columns}
        pagination={false}
      />

      <h3 style={{ marginTop: 32 }}>История версий</h3>
      {(!all.data || all.data.feeds.length === 0) ? (
        <Empty description="Нет опубликованных версий" />
      ) : (
        <Collapse
          items={all.data.feeds.map((feed) => ({
            key: feed.version,
            label: (
              <Space>
                <strong>{feed.version}</strong>
                <span style={{ color: '#888' }}>({feed.notes.length} зап.)</span>
              </Space>
            ),
            children: (
              <>
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={feed.notes}
                  columns={columns}
                  pagination={false}
                />
                <Popconfirm
                  title={`Удалить версию ${feed.version}?`}
                  description="Записи вернутся в черновики"
                  onConfirm={() => deleteVersionMut.mutate(feed.version)}
                >
                  <Button
                    danger size="small" style={{ marginTop: 8 }}
                    icon={<DeleteOutlined />}
                  >
                    Удалить версию
                  </Button>
                </Popconfirm>
              </>
            ),
          }))}
        />
      )}

      {/* модалка создания/редактирования */}
      <NoteEditor
        open={adding || editing !== null}
        initial={editing ?? undefined}
        onSubmit={(body) => {
          if (editing) {
            updateMut.mutate(
              { id: editing.id, body },
              { onSuccess: () => { setEditing(null); notification.success({ title: 'Сохранено' }); } }
            );
          } else {
            createMut.mutate(
              body as ReleaseNoteCreate,
              { onSuccess: () => { setAdding(false); notification.success({ message: 'Добавлено' }); } }
            );
          }
        }}
        onCancel={() => { setAdding(false); setEditing(null); }}
      />

      {/* модалка публикации */}
      <Modal
        title="Выпустить под версию"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={() => {
          if (!publishVersion) return;
          publishMut.mutate(publishVersion, {
            onSuccess: (res) => {
              setPublishOpen(false);
              notification.success({
                title: `Опубликовано ${res.published_count} зап. под ${res.version}`,
              });
            },
          });
        }}
      >
        <Input
          placeholder="v1.2.0"
          value={publishVersion}
          onChange={(e) => setPublishVersion(e.target.value)}
        />
      </Modal>

      {/* превью пользовательской модалки */}
      <WhatsNewModal
        open={previewOpen}
        feeds={[{
          version: 'Предпросмотр',
          notes: drafts.data ?? [],
        }]}
        onClose={() => setPreviewOpen(false)}
        onMarkSeen={() => {}}
      />
    </div>
  );
}

interface NoteEditorProps {
  open: boolean;
  initial?: ReleaseNote;
  onSubmit: (body: ReleaseNoteCreate | ReleaseNoteUpdate) => void;
  onCancel: () => void;
}

function NoteEditor({ open, initial, onSubmit, onCancel }: NoteEditorProps) {
  const [form] = Form.useForm();
  return (
    <Modal
      open={open}
      onCancel={onCancel}
      onOk={async () => {
        const values = await form.validateFields();
        onSubmit(values);
      }}
      title={initial ? 'Редактировать запись' : 'Добавить запись'}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initial ?? { note_type: 'new', section: 'general' }}
        preserve={false}
      >
        <Form.Item label="Тип" name="note_type" rules={[{ required: true }]}>
          <Select options={(Object.keys(NOTE_TYPE_LABELS) as ReleaseNoteType[]).map((k) => ({
            value: k, label: NOTE_TYPE_LABELS[k],
          }))} />
        </Form.Item>
        <Form.Item label="Раздел" name="section" rules={[{ required: true }]}>
          <Select options={(Object.keys(SECTION_LABELS) as ReleaseSection[]).map((k) => ({
            value: k, label: SECTION_LABELS[k],
          }))} />
        </Form.Item>
        <Form.Item label="Заголовок" name="title" rules={[{ required: true }]}>
          <Input maxLength={500} />
        </Form.Item>
        <Form.Item label="Описание" name="description" rules={[{ required: true }]}>
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item label="Ссылка на справку (опционально)" name="help_link">
          <Input placeholder="#help-categories или https://..." />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 2: Добавить вкладку в SettingsPage**

В `frontend/src/pages/SettingsPage.tsx`:

```typescript
import ReleaseNotesAdminTab from '../components/settings/ReleaseNotesAdminTab';
```

В `TAB_KEYS`:
```typescript
const TAB_KEYS = [
  'connection', 'scope', 'fields', 'hierarchy', 'reasons', 'categories',
  'worktypes', 'calendar', 'ai', 'visibility', 'users', 'feedback', 'usage',
  'whats-new',  // ← добавить
] as const;
```

В items внутри admin-only блока добавить:
```typescript
{ key: 'whats-new', label: 'Что нового', children: <ReleaseNotesAdminTab /> },
```

- [ ] **Step 3: Билд проходит**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/ReleaseNotesAdminTab.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(release-notes): админ-таб /settings → «Что нового»"
```

---

## Phase 7 — Ретроспектива v1.1.0

### Task 12: Заметки на v1.1.0 по 67 коммитам

**Files:**
- (нет файлов — только данные через CLI)

- [ ] **Step 1: Прочитать commit log v1.0.0..v1.1.0 целиком**

```bash
git log v1.0.0..v1.1.0 --pretty=format:"%h %s" --no-merges
```

- [ ] **Step 2: Сгруппировать значимые коммиты вручную**

Из 67 коммитов отметить значимые для пользователя (новые функции, заметные улучшения, исправления что мешали). Пропустить рефакторинг/тесты/доки.

- [ ] **Step 3: Добавить заметки через CLI с `--version v1.1.0`**

Для каждого значимого коммита:
```bash
py -3.10 scripts/release_note.py add \
    --type new --section categories \
    --title "Массовые операции на странице «Анализ»" \
    --description "Новая кнопка «Массовые операции» открывает помощник из трёх секций: архивировать по фильтру, принять подсказки категорий, каскад от эпика. Помогает разобрать большой объём задач." \
    --version v1.1.0
```

(N таких команд, по одной на значимый коммит.)

- [ ] **Step 4: Проверить в /settings → «Что нового»**

Открыть UI, во вкладке убедиться что v1.1.0 виден в «История версий», там все добавленные записи. Зайти в режим «Посмотреть как пользователь» — проверить модалку.

- [ ] **Step 5: Smoke прогон pytest**

```bash
py -3.10 -m pytest -v
```

Ожидание: все 1090+ существующих + новые тесты проходят.

- [ ] **Step 6: Commit (если CLI правил БД, коммитов нет; пометить fixture-файлом)**

Если миграция/seed нужны — сделать `scripts/seed_release_notes_v1_1_0.py`. Иначе фиксируем выполненной задачей в плане без коммита (данные живут в БД сервера).

---

## Финал

После Task 12:

- [ ] **Step 1: Полный прогон тестов**

```bash
py -3.10 -m pytest -v
cd frontend && npm run lint && npm run build
```

- [ ] **Step 2: Push всех коммитов**

```bash
git push origin main
```

- [ ] **Step 3: Обновить память проекта**

Через Write добавить запись:
- `release_notes_feed_shipped.md` — что зашипили, дата, основные точки

Обновить `MEMORY.md` индекс соответственно.
