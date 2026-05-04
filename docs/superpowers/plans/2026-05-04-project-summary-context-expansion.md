# Project Summary Context Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Расширить AI-саммари проектов: убрать жёсткий лимит описания эпика 1500, тянуть описания дочерних задач, два новых кастомных поля «Цель задачи» / «Текущее поведение», подмешивать в промпт текст Confluence-страниц по ссылкам из описаний эпика и детей.

**Architecture:** Backend — две новые колонки `Issue` + sync читает кастомные поля → новый `ConfluenceClient` (тот же Atlassian token, base `/wiki/rest/api/content/{id}?expand=body.storage`) + DB-кэш страниц с TTL 7 дней + extractor ссылок (regex по `pages/{id}/`, `/x/{tinyId}`, `/display/...`) → расширенный `_build_epic_data` + новый `build_prompt` (лимит 8000 для description, 8000 на дочернюю description + goal/behavior, отдельная секция «Confluence-страницы»). Frontend — добавить два инпута в существующий `JiraFieldsCard.tsx`. Промпт-версия `_BASE_VERSION` бьётся `v2 → v3` — nightly job сам перегенерит саммари.

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy 2.0 + Alembic batch migrations + httpx + React 19 + AntD 6 + pytest.

---

## File Structure

**Create:**
- `alembic/versions/047_issue_description_extra_fields.py` — миграция: 2 колонки в `issues` + seed двух AppSetting ключей
- `alembic/versions/048_confluence_page_cache.py` — миграция: таблица `confluence_page_cache`
- `app/models/confluence_page_cache.py` — модель кэша
- `app/connectors/confluence_client.py` — async клиент Confluence Cloud
- `app/services/confluence_service.py` — оркестратор: extract links + cache + fetch + html→text
- `tests/services/test_confluence_service.py` — тесты сервиса
- `tests/connectors/test_confluence_client.py` — тесты клиента
- `tests/test_sync_extra_fields.py` — тест extract goal/behavior

**Modify:**
- `app/models/issue.py` — 2 поля `goal_text`, `current_behavior`
- `app/models/__init__.py` — экспорт `ConfluencePageCache`
- `app/services/sync_service.py` — читать `jira_goal_field_id` и `jira_current_behavior_field_id` из AppSetting, писать в Issue (3 места: `sync_issues`, `sync_issues_by_team`, `refresh_issues_by_keys`)
- `app/services/project_summary_service.py` — `_build_epic_data` обогащает child_summaries + собирает Confluence-страницы
- `app/services/llm/prompt.py` — `_BASE_VERSION = "v3"`, лимит 8000, новый формат `child_summaries`, секция Confluence
- `frontend/src/components/JiraFieldsCard.tsx` — новая группа `description_extra` с двумя селектами
- `tests/services/test_project_summary_service.py` — обновить ожидания промпта

---

## Task 1: Migration — Issue.goal_text + Issue.current_behavior + seed AppSetting

**Files:**
- Create: `alembic/versions/047_issue_description_extra_fields.py`

- [ ] **Step 1: Write migration**

```python
"""add issue.goal_text + issue.current_behavior, seed jira_goal_field_id + jira_current_behavior_field_id

Revision ID: 047_issue_description_extra_fields
Revises: 7f9c9e09d8bd
Create Date: 2026-05-04
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "047_issue_description_extra_fields"
down_revision: Union[str, None] = "7f9c9e09d8bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("goal_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("current_behavior", sa.Text(), nullable=True))

    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    for key in ("jira_goal_field_id", "jira_current_behavior_field_id"):
        exists = bind.execute(
            sa.text("SELECT 1 FROM app_settings WHERE key = :k"), {"k": key}
        ).scalar()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
                    "VALUES (:id, :k, '', :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "k": key, "now": now},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM app_settings WHERE key IN ('jira_goal_field_id', 'jira_current_behavior_field_id')"
    ))
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("current_behavior")
        batch_op.drop_column("goal_text")
```

- [ ] **Step 2: Run migration**

```
py -3.10 -m alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 7f9c9e09d8bd -> 047_issue_description_extra_fields`

- [ ] **Step 3: Commit**

```
git add alembic/versions/047_issue_description_extra_fields.py
git commit -m "feat(summary): add issue.goal_text + current_behavior columns + seed AppSetting"
```

---

## Task 2: Update Issue model

**Files:**
- Modify: `app/models/issue.py`

- [ ] **Step 1: Write failing test**

`tests/test_issue_model_extra_fields.py`:

```python
from app.models.issue import Issue


def test_issue_has_goal_text_and_current_behavior_columns():
    cols = {c.name for c in Issue.__table__.columns}
    assert "goal_text" in cols
    assert "current_behavior" in cols
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/test_issue_model_extra_fields.py -v
```

Expected: FAIL — `'goal_text' not in cols`

- [ ] **Step 3: Add columns to Issue model**

After existing `goals` field in `app/models/issue.py:64`, before `planned_analyst_hours`:

```python
    # Кастомные текстовые поля Jira: «Цель задачи», «Описание текущего поведения».
    # IDs настраиваются через AppSetting (`jira_goal_field_id`, `jira_current_behavior_field_id`).
    goal_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_behavior: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Run test, expect pass**

```
py -3.10 -m pytest tests/test_issue_model_extra_fields.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add app/models/issue.py tests/test_issue_model_extra_fields.py
git commit -m "feat(summary): Issue.goal_text + Issue.current_behavior fields"
```

---

## Task 3: Sync service — extract new custom fields

**Files:**
- Modify: `app/services/sync_service.py` (3 места: `sync_issues` ~656-755, `sync_issues_by_team` ~821-884, `refresh_issues_by_keys` ~915-1001)

- [ ] **Step 1: Write failing test**

`tests/test_sync_extra_fields.py`:

```python
import pytest
from unittest.mock import MagicMock
from app.services.sync_service import _extract_text_field


def test_extract_text_field_string():
    extra = {"customfield_99": "цель задачи"}
    assert _extract_text_field(extra, "customfield_99") == "цель задачи"


def test_extract_text_field_adf():
    extra = {"customfield_99": {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "цель"}]}
    ]}}
    assert _extract_text_field(extra, "customfield_99") == "цель"


def test_extract_text_field_missing():
    assert _extract_text_field({}, "customfield_99") is None


def test_extract_text_field_empty_id():
    assert _extract_text_field({"customfield_99": "x"}, "") is None
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/test_sync_extra_fields.py -v
```

Expected: FAIL — `cannot import name '_extract_text_field'`

- [ ] **Step 3: Add `_extract_text_field` helper near top of `app/services/sync_service.py` (рядом с `_extract_team_values`)**

```python
def _extract_text_field(extra: dict, field_id: str) -> Optional[str]:
    """Достать text/ADF-значение кастомного поля из `_extra`.

    Поддерживает форматы:
    - plain string: "текст"
    - ADF doc: {type: "doc", content: [{type: "paragraph", content: [{type: "text", text: "..."}]}]}
    """
    if not field_id:
        return None
    value = extra.get(field_id)
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict) and value.get("type") == "doc":
        return _adf_to_text(value).strip() or None
    return None


def _adf_to_text(node: dict) -> str:
    """Рекурсивный обход ADF дерева — конкатенация text-нод с переводами строк после параграфов."""
    if not isinstance(node, dict):
        return ""
    parts: list[str] = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content", []) or []:
        parts.append(_adf_to_text(child))
    text = "".join(parts)
    if node.get("type") in {"paragraph", "heading", "listItem", "bulletList", "orderedList"}:
        text += "\n"
    return text
```

- [ ] **Step 4: Add reading of AppSetting + extract в `sync_issues`. После строки `goals_field_id = self._get_setting("jira_goals_field_id")` (около [sync_service.py:658](app/services/sync_service.py#L658)) добавить:**

```python
        goal_field_id = self._get_setting("jira_goal_field_id")
        behavior_field_id = self._get_setting("jira_current_behavior_field_id")
```

- [ ] **Step 5: Расширить `extra_fields` в той же функции (около [sync_service.py:660](app/services/sync_service.py#L660))**

```python
        extra_fields = [
            fid for fid in (
                product_field_id, participating_field_id, goals_field_id,
                goal_field_id, behavior_field_id,
            ) if fid
        ]
```

- [ ] **Step 6: В блоке `if extra_fields:` (около [sync_service.py:744](app/services/sync_service.py#L744)) добавить после `goals_list`:**

```python
                    if goal_field_id:
                        extra_kwargs["goal_text"] = _extract_text_field(extra, goal_field_id)
                    if behavior_field_id:
                        extra_kwargs["current_behavior"] = _extract_text_field(extra, behavior_field_id)
```

- [ ] **Step 7: Повторить шаги 4-6 в `sync_issues_by_team` (около [sync_service.py:821-884](app/services/sync_service.py#L821-L884)) и `refresh_issues_by_keys` (около [sync_service.py:915-1001](app/services/sync_service.py#L915-L1001)).**

В каждой функции:
- добавить чтение `goal_field_id` / `behavior_field_id` рядом с `goals_field_id`
- добавить их в `extra_fields` фильтр
- в блоке `if extra_fields:` добавить два `if` для `goal_text` / `current_behavior`

- [ ] **Step 8: Run helper test, expect pass**

```
py -3.10 -m pytest tests/test_sync_extra_fields.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 9: Commit**

```
git add app/services/sync_service.py tests/test_sync_extra_fields.py
git commit -m "feat(sync): extract goal_text + current_behavior from configured Jira custom fields"
```

---

## Task 4: Frontend — add two field selectors to JiraFieldsCard

**Files:**
- Modify: `frontend/src/components/JiraFieldsCard.tsx`

- [ ] **Step 1: Add new group to `GROUPS` array. Insert after `core` group (around [JiraFieldsCard.tsx:30](frontend/src/components/JiraFieldsCard.tsx#L30)):**

```tsx
  {
    panelKey: 'description_extra',
    title: 'Описание задачи (для AI-саммари)',
    subtitle: 'Кастомные поля с целями и текущим поведением — попадают в промпт LLM',
    fields: [
      { key: 'jira_goal_field_id', label: 'Цель задачи' },
      { key: 'jira_current_behavior_field_id', label: 'Текущее поведение' },
    ],
  },
```

- [ ] **Step 2: Add `description_extra` to `defaultActiveKey` (around [JiraFieldsCard.tsx:155](frontend/src/components/JiraFieldsCard.tsx#L155)):**

```tsx
          defaultActiveKey={['core', 'description_extra', 'planned_hours', 'prioritization', 'customer_rating']}
```

- [ ] **Step 3: Verify lint passes**

```
cd frontend && npm run lint
```

Expected: 0 errors. (If unrelated existing errors block, ignore.)

- [ ] **Step 4: Commit**

```
git add frontend/src/components/JiraFieldsCard.tsx
git commit -m "feat(settings): add Goal/Current-behavior field selectors to JiraFieldsCard"
```

---

## Task 5: Migration — confluence_page_cache table

**Files:**
- Create: `alembic/versions/048_confluence_page_cache.py`

- [ ] **Step 1: Write migration**

```python
"""add confluence_page_cache

Revision ID: 048_confluence_page_cache
Revises: 047_issue_description_extra_fields
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "048_confluence_page_cache"
down_revision: Union[str, None] = "047_issue_description_extra_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "confluence_page_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("page_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("confluence_page_cache")
```

- [ ] **Step 2: Run migration**

```
py -3.10 -m alembic upgrade head
```

Expected: `Running upgrade 047_issue_description_extra_fields -> 048_confluence_page_cache`

- [ ] **Step 3: Commit**

```
git add alembic/versions/048_confluence_page_cache.py
git commit -m "feat(confluence): add confluence_page_cache table"
```

---

## Task 6: ConfluencePageCache model

**Files:**
- Create: `app/models/confluence_page_cache.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write failing test**

`tests/test_confluence_page_cache_model.py`:

```python
from app.models.confluence_page_cache import ConfluencePageCache


def test_model_has_expected_columns():
    cols = {c.name for c in ConfluencePageCache.__table__.columns}
    expected = {
        "id", "page_id", "source_url", "title",
        "body_text", "error", "fetched_at",
        "created_at", "updated_at",
    }
    assert expected <= cols
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/test_confluence_page_cache_model.py -v
```

Expected: FAIL — `No module named 'app.models.confluence_page_cache'`

- [ ] **Step 3: Create model**

```python
"""ConfluencePageCache — кэш Confluence-страниц для AI-саммари."""
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from datetime import datetime


class ConfluencePageCache(Base, TimestampMixin):
    """Кэш текста Confluence-страниц по page_id.

    Используется в `ConfluenceService` для подмешивания текста ТЗ в промпт LLM.
    """

    __tablename__ = "confluence_page_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    page_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

- [ ] **Step 4: Add to `app/models/__init__.py`**

Найти строку с экспортом модели (например `from app.models.project_ai_summary import ProjectAISummary`) и добавить рядом:

```python
from app.models.confluence_page_cache import ConfluencePageCache
```

И в `__all__` (если есть) — `"ConfluencePageCache"`.

- [ ] **Step 5: Run test, expect pass**

```
py -3.10 -m pytest tests/test_confluence_page_cache_model.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```
git add app/models/confluence_page_cache.py app/models/__init__.py tests/test_confluence_page_cache_model.py
git commit -m "feat(confluence): ConfluencePageCache model"
```

---

## Task 7: ConfluenceClient

**Files:**
- Create: `app/connectors/confluence_client.py`
- Create: `tests/connectors/test_confluence_client.py`

Атлассианский токен общий — переиспользуем те же `jira_email` / `jira_api_token` / `jira_base_url` из AppSetting. Confluence Cloud REST: `GET /wiki/rest/api/content/{pageId}?expand=body.storage`. Tinyurl: `GET /wiki/x/{tinyId}` отдаёт 302 на `/wiki/spaces/.../pages/{id}/`.

- [ ] **Step 1: Write failing test**

`tests/connectors/test_confluence_client.py`:

```python
import pytest
import respx
import httpx
from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError


@pytest.mark.asyncio
@respx.mock
async def test_get_page_content_returns_html_body():
    respx.get("https://itgri.atlassian.net/wiki/rest/api/content/12345").mock(
        return_value=httpx.Response(200, json={
            "id": "12345",
            "title": "ТЗ Анализ себестоимости",
            "body": {"storage": {"value": "<p>Полный текст ТЗ</p>", "representation": "storage"}},
        })
    )
    async with ConfluenceClient(
        base_url="https://itgri.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        page = await c.get_page("12345")
    assert page.id == "12345"
    assert page.title == "ТЗ Анализ себестоимости"
    assert "Полный текст ТЗ" in page.body_html


@pytest.mark.asyncio
@respx.mock
async def test_resolve_tinyurl_follows_redirect():
    respx.get("https://itgri.atlassian.net/wiki/x/abc123").mock(
        return_value=httpx.Response(302, headers={"Location": "/wiki/spaces/PR/pages/98765/Title"})
    )
    async with ConfluenceClient(
        base_url="https://itgri.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        page_id = await c.resolve_tinyurl("https://itgri.atlassian.net/wiki/x/abc123")
    assert page_id == "98765"


@pytest.mark.asyncio
@respx.mock
async def test_get_page_404_raises():
    respx.get("https://itgri.atlassian.net/wiki/rest/api/content/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    async with ConfluenceClient(
        base_url="https://itgri.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        with pytest.raises(ConfluenceClientError):
            await c.get_page("missing")
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/connectors/test_confluence_client.py -v
```

Expected: FAIL — `No module named 'app.connectors.confluence_client'`

- [ ] **Step 3: Write client**

```python
"""Confluence Cloud REST client. Переиспользует Atlassian creds (тот же токен, что Jira)."""
import base64
import re
from dataclasses import dataclass
from typing import Optional

import httpx


class ConfluenceClientError(Exception):
    pass


@dataclass
class ConfluencePage:
    id: str
    title: str
    body_html: str


class ConfluenceClient:
    """Async Confluence Cloud client. Same Basic auth as Jira."""

    @classmethod
    def from_db(cls, db) -> "ConfluenceClient":
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(
            base_url=_get("jira_base_url") or "",
            email=_get("jira_email") or "",
            api_token=_get("jira_api_token") or "",
        )

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        if not (base_url and email and api_token):
            raise ConfluenceClientError("Confluence credentials missing")
        self.base_url = base_url.rstrip("/")
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {creds}", "Accept": "application/json"}
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "ConfluenceClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers, timeout=30.0,
            follow_redirects=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def get_page(self, page_id: str) -> ConfluencePage:
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        r = await self._client.get(
            f"/wiki/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        if r.status_code != 200:
            raise ConfluenceClientError(
                f"GET page {page_id} → HTTP {r.status_code}: {r.text[:200]}"
            )
        data = r.json()
        return ConfluencePage(
            id=data["id"],
            title=data.get("title", ""),
            body_html=data.get("body", {}).get("storage", {}).get("value", ""),
        )

    async def resolve_tinyurl(self, url: str) -> Optional[str]:
        """Tinyurl `/wiki/x/{id}` → page_id через 302 redirect."""
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        path = url.replace(self.base_url, "")
        if not path.startswith("/wiki/x/"):
            return None
        r = await self._client.get(path)
        if r.status_code != 302:
            return None
        loc = r.headers.get("Location", "")
        m = re.search(r"/pages/(\d+)", loc)
        return m.group(1) if m else None
```

- [ ] **Step 4: Install respx if missing**

```
py -3.10 -m pip install respx
```

- [ ] **Step 5: Run tests, expect pass**

```
py -3.10 -m pytest tests/connectors/test_confluence_client.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```
git add app/connectors/confluence_client.py tests/connectors/test_confluence_client.py
git commit -m "feat(confluence): add ConfluenceClient with shared Atlassian token"
```

---

## Task 8: ConfluenceService — link extraction + cache + html→text

**Files:**
- Create: `app/services/confluence_service.py`
- Create: `tests/services/test_confluence_service.py`

- [ ] **Step 1: Write failing tests**

`tests/services/test_confluence_service.py`:

```python
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.services.confluence_service import (
    extract_confluence_urls,
    html_to_text,
    parse_page_id,
    ConfluenceService,
)


def test_extract_confluence_urls_basic():
    text = "См ТЗ https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title и tinyurl https://itgri.atlassian.net/wiki/x/abcDEF"
    urls = extract_confluence_urls(text, "https://itgri.atlassian.net")
    assert "https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title" in urls
    assert "https://itgri.atlassian.net/wiki/x/abcDEF" in urls


def test_extract_confluence_urls_dedup_and_skip_other_hosts():
    text = "https://other.atlassian.net/wiki/spaces/X/pages/1/T https://itgri.atlassian.net/wiki/spaces/X/pages/2/T https://itgri.atlassian.net/wiki/spaces/X/pages/2/T"
    urls = extract_confluence_urls(text, "https://itgri.atlassian.net")
    assert urls == ["https://itgri.atlassian.net/wiki/spaces/X/pages/2/T"]


def test_html_to_text_strips_tags():
    html = "<h1>Заголовок</h1><p>Параграф <b>жирный</b></p><ul><li>пункт</li></ul>"
    text = html_to_text(html)
    assert "Заголовок" in text
    assert "жирный" in text
    assert "пункт" in text
    assert "<" not in text


def test_parse_page_id_from_pages_url():
    assert parse_page_id("https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title") == "12345"
    assert parse_page_id("https://itgri.atlassian.net/wiki/x/abcDEF") is None  # tinyurl needs resolve


@pytest.mark.asyncio
async def test_service_returns_cached_when_fresh(db_session):
    from app.models.confluence_page_cache import ConfluencePageCache
    db_session.add(ConfluencePageCache(
        page_id="12345",
        source_url="https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T",
        title="Cached", body_text="cached body", error=None,
        fetched_at=datetime.utcnow() - timedelta(days=1),
    ))
    db_session.commit()

    svc = ConfluenceService(db_session)
    pages = await svc.fetch_pages(
        ["https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T"]
    )
    assert len(pages) == 1
    assert pages[0].body_text == "cached body"


@pytest.mark.asyncio
async def test_service_refetches_when_stale(db_session):
    from app.models.confluence_page_cache import ConfluencePageCache
    db_session.add(ConfluencePageCache(
        page_id="99",
        source_url="https://itgri.atlassian.net/wiki/spaces/X/pages/99/T",
        title="Old", body_text="old body", error=None,
        fetched_at=datetime.utcnow() - timedelta(days=10),
    ))
    db_session.commit()

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get_page.return_value = type("P", (), {
        "id": "99", "title": "Fresh", "body_html": "<p>fresh</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        svc = ConfluenceService(db_session)
        pages = await svc.fetch_pages(
            ["https://itgri.atlassian.net/wiki/spaces/X/pages/99/T"]
        )
    assert pages[0].body_text.strip() == "fresh"
```

- [ ] **Step 2: Run tests, expect fail**

```
py -3.10 -m pytest tests/services/test_confluence_service.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Write service**

```python
"""ConfluenceService — extract Confluence-ссылок, fetch с кэшем, html→text."""
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError
from app.models.app_setting import AppSetting
from app.models.confluence_page_cache import ConfluencePageCache


logger = logging.getLogger("jira_analytics.confluence")

CACHE_TTL = timedelta(days=7)
MAX_BODY_CHARS = 8000  # обрезаем перед сохранением — лимит для промпта


@dataclass
class FetchedPage:
    page_id: str
    source_url: str
    title: str
    body_text: str


_URL_RE = re.compile(
    r"https?://[\w\.\-]+\.atlassian\.net/wiki/(?:spaces/[^\s/]+/pages/\d+[^\s)]*|x/[A-Za-z0-9]+)"
)


def extract_confluence_urls(text: Optional[str], base_url: str) -> list[str]:
    """Достать уникальные Confluence-ссылки на тот же tenant."""
    if not text or not base_url:
        return []
    host = urlparse(base_url).netloc
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,);")
        if urlparse(url).netloc != host:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_page_id(url: str) -> Optional[str]:
    """`/wiki/spaces/.../pages/{id}/...` → id. Tinyurl возвращает None — резолв через client."""
    m = re.search(r"/pages/(\d+)", url)
    return m.group(1) if m else None


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "br", "h1", "h2", "h3", "h4", "li", "div"}:
            self.parts.append("\n")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _Stripper()
    s.feed(html)
    text = "".join(s.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class ConfluenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _base_url(self) -> Optional[str]:
        row = self.db.query(AppSetting).filter(AppSetting.key == "jira_base_url").first()
        return row.value if row and row.value else None

    async def fetch_pages(self, urls: list[str]) -> list[FetchedPage]:
        """Для каждого URL вернуть FetchedPage. Кэш TTL 7 дней. Ошибки тихо пропускаем (логируем)."""
        if not urls:
            return []
        base = self._base_url()
        if not base:
            return []

        # 1. Резолвим page_id (tinyurl → fetch redirect, прочее regex)
        url_to_pid: dict[str, Optional[str]] = {u: parse_page_id(u) for u in urls}
        unresolved = [u for u, pid in url_to_pid.items() if pid is None]

        client_cm = ConfluenceClient.from_db(self.db)
        results: list[FetchedPage] = []
        try:
            async with client_cm as client:
                for u in unresolved:
                    try:
                        url_to_pid[u] = await client.resolve_tinyurl(u)
                    except Exception as e:
                        logger.warning("tinyurl resolve %s failed: %s", u, e)

                # 2. Для каждого page_id — кэш или fetch
                for url, pid in url_to_pid.items():
                    if not pid:
                        continue
                    cached = self.db.execute(
                        select(ConfluencePageCache).where(ConfluencePageCache.page_id == pid)
                    ).scalar_one_or_none()
                    fresh = (
                        cached is not None
                        and cached.fetched_at >= datetime.utcnow() - CACHE_TTL
                        and cached.body_text is not None
                    )
                    if fresh:
                        results.append(FetchedPage(
                            page_id=pid, source_url=cached.source_url,
                            title=cached.title or "", body_text=cached.body_text or "",
                        ))
                        continue

                    try:
                        page = await client.get_page(pid)
                        text = html_to_text(page.body_html)[:MAX_BODY_CHARS]
                        if cached:
                            cached.source_url = url
                            cached.title = page.title
                            cached.body_text = text
                            cached.error = None
                            cached.fetched_at = datetime.utcnow()
                        else:
                            cached = ConfluencePageCache(
                                page_id=pid, source_url=url,
                                title=page.title, body_text=text,
                                error=None, fetched_at=datetime.utcnow(),
                            )
                            self.db.add(cached)
                        self.db.commit()
                        results.append(FetchedPage(
                            page_id=pid, source_url=url,
                            title=page.title, body_text=text,
                        ))
                    except ConfluenceClientError as e:
                        logger.warning("Confluence fetch %s failed: %s", pid, e)
                        if cached:
                            cached.error = str(e)[:512]
                            cached.fetched_at = datetime.utcnow()
                            self.db.commit()
        except ConfluenceClientError as e:
            logger.warning("Confluence client unavailable: %s", e)
            return []

        return results
```

- [ ] **Step 4: Run tests, expect pass**

```
py -3.10 -m pytest tests/services/test_confluence_service.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```
git add app/services/confluence_service.py tests/services/test_confluence_service.py
git commit -m "feat(confluence): ConfluenceService with link extract, html→text, 7d DB cache"
```

---

## Task 9: project_summary_service — enrich child_summaries + Confluence

**Files:**
- Modify: `app/services/project_summary_service.py`

- [ ] **Step 1: Write failing test**

`tests/services/test_project_summary_enrichment.py`:

```python
from unittest.mock import patch, AsyncMock
import pytest

from app.services.confluence_service import FetchedPage


@pytest.mark.asyncio
async def test_build_epic_data_includes_child_extras_and_confluence(db_session, monkeypatch):
    # Setup: epic + 1 child через фикстуры (используем существующий seed pattern)
    from app.models.project import Project
    from app.models.issue import Issue
    p = Project(jira_project_id="P1", key="PRJ", name="P")
    db_session.add(p); db_session.commit()
    epic = Issue(
        jira_issue_id="1", key="PRJ-1", summary="Эпик",
        description="См ТЗ https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T",
        issue_type="Epic", status="In Progress",
        project_id=p.id, category="initiatives_in_progress",
    )
    child = Issue(
        jira_issue_id="2", key="PRJ-2", summary="Доработка",
        description="Описание ТЗ", goal_text="Цель", current_behavior="Сейчас не работает",
        issue_type="Task", status="Done",
        project_id=p.id, parent_id=epic.id,
    )
    db_session.add_all([epic, child]); db_session.commit()

    fake_pages = [FetchedPage(
        page_id="12345",
        source_url="https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T",
        title="Полное ТЗ", body_text="Контент ТЗ из confluence",
    )]
    with patch(
        "app.services.project_summary_service.ConfluenceService"
    ) as mock_svc:
        mock_svc.return_value.fetch_pages = AsyncMock(return_value=fake_pages)
        from app.services.project_summary_service import ProjectSummaryService
        data = await ProjectSummaryService(db_session)._build_epic_data_async(epic)

    cs = data["child_summaries"]
    assert any(c["key"] == "PRJ-2" and c.get("description") == "Описание ТЗ" for c in cs)
    assert any(c.get("goal_text") == "Цель" for c in cs)
    assert any(c.get("current_behavior") == "Сейчас не работает" for c in cs)
    assert data["confluence_pages"][0]["title"] == "Полное ТЗ"
    assert "Контент ТЗ из confluence" in data["confluence_pages"][0]["body_text"]
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/services/test_project_summary_enrichment.py -v
```

Expected: FAIL — `_build_epic_data_async` not defined / KeyError 'description' on child

- [ ] **Step 3: Refactor `_build_epic_data` to async + use enriched fields. Полностью переписать метод в `app/services/project_summary_service.py:83-121`:**

```python
    async def _build_epic_data_async(self, epic: Issue) -> dict:
        """Собрать данные для промпта (async — fetch Confluence)."""
        detail = ProjectsService(self.db).get_project_detail(epic.key)
        if not detail:
            return {"key": epic.key, "summary": epic.summary}

        child_ids = ProjectsService(self.db)._collect_subtree(epic.id)
        child_issues = self.db.execute(
            select(Issue).where(Issue.id.in_(child_ids))
        ).scalars().all()
        child_summaries = [
            {
                "key": i.key,
                "summary": i.summary,
                "description": (i.description or "")[:8000] or None,
                "goal_text": (i.goal_text or "") or None,
                "current_behavior": (i.current_behavior or "") or None,
            }
            for i in child_issues[:30]
        ]

        # Confluence: ссылки из эпика + всех детей
        from app.services.confluence_service import (
            ConfluenceService, extract_confluence_urls,
        )
        from app.models.app_setting import AppSetting
        base = self.db.query(AppSetting).filter(
            AppSetting.key == "jira_base_url"
        ).first()
        base_url = base.value if base and base.value else ""
        all_urls: list[str] = []
        seen: set[str] = set()
        for txt in [epic.description] + [i.description for i in child_issues]:
            for u in extract_confluence_urls(txt, base_url):
                if u not in seen:
                    seen.add(u)
                    all_urls.append(u)
        # лимит 10 страниц на эпик чтобы не раздувать токены
        confluence = await ConfluenceService(self.db).fetch_pages(all_urls[:10])
        confluence_pages = [
            {
                "title": p.title,
                "url": p.source_url,
                "body_text": p.body_text[:8000],
            }
            for p in confluence
        ]

        total_hours = detail.total_hours or 0.0
        return {
            "key": epic.key,
            "summary": epic.summary,
            "description": epic.description or "",
            "status": epic.status,
            "is_done": epic.status_category == "done",
            "child_count": detail.child_count,
            "employee_count": detail.employee_count,
            "total_hours": total_hours,
            "period_start": detail.period_start.date().isoformat() if detail.period_start else None,
            "period_end": detail.period_end.date().isoformat() if detail.period_end else None,
            "categories": [{"label": c.label, "hours": c.hours} for c in detail.categories],
            "employees": [
                {
                    "name": e.name,
                    "hours": e.hours,
                    "pct": round(e.hours / total_hours * 100, 1) if total_hours else 0.0,
                }
                for e in detail.employees
            ],
            "top_issues": [
                {"key": t.key, "summary": t.summary, "hours": t.hours}
                for t in detail.top_issues
            ],
            "child_summaries": child_summaries,
            "confluence_pages": confluence_pages,
        }
```

- [ ] **Step 4: Удалить старый sync `_build_epic_data` и обновить `regenerate` чтобы вызывал async-версию (`app/services/project_summary_service.py:35`):**

```python
        epic_data = await self._build_epic_data_async(epic)
```

- [ ] **Step 5: Run test, expect pass**

```
py -3.10 -m pytest tests/services/test_project_summary_enrichment.py -v
```

Expected: PASS

- [ ] **Step 6: Run existing summary service tests, fix breakages**

```
py -3.10 -m pytest tests/services/test_project_summary_service.py -v
```

Если ломается на отсутствии `_build_epic_data` — переименовать вызовы в тестах на `_build_epic_data_async` и пометить `@pytest.mark.asyncio`.

- [ ] **Step 7: Commit**

```
git add app/services/project_summary_service.py tests/services/test_project_summary_enrichment.py tests/services/test_project_summary_service.py
git commit -m "feat(summary): enrich epic_data with child desc/goal/behavior + Confluence pages"
```

---

## Task 10: Prompt — bump version, lift limits, new sections

**Files:**
- Modify: `app/services/llm/prompt.py`
- Modify: `tests/services/llm/test_prompt.py` (if exists; иначе создать `tests/test_prompt_build.py`)

- [ ] **Step 1: Write failing test**

`tests/test_prompt_build.py`:

```python
from app.services.llm.prompt import build_prompt, PROMPT_VERSION


def test_prompt_uses_v3_base():
    assert PROMPT_VERSION.startswith("v3-")


def test_prompt_includes_full_8000_description():
    long_desc = "x" * 12000
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик",
        "description": long_desc, "status": "In Progress",
        "is_done": False, "child_count": 0, "employee_count": 0,
        "total_hours": 0,
    }
    p = build_prompt(epic_data)
    # был бы 1500, стал 8000
    assert "x" * 8000 in p
    assert "x" * 8001 not in p


def test_prompt_includes_child_extras():
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик", "description": "", "status": "In Progress",
        "is_done": False, "child_count": 1, "employee_count": 1, "total_hours": 5,
        "child_summaries": [{
            "key": "PRJ-2", "summary": "Доработка",
            "description": "Технические детали ТЗ",
            "goal_text": "Цель аналитика",
            "current_behavior": "Сейчас не работает",
        }],
    }
    p = build_prompt(epic_data)
    assert "Технические детали ТЗ" in p
    assert "Цель аналитика" in p
    assert "Сейчас не работает" in p


def test_prompt_includes_confluence_pages():
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик", "description": "", "status": "Done",
        "is_done": True, "child_count": 0, "employee_count": 0, "total_hours": 0,
        "confluence_pages": [{
            "title": "ТЗ полное", "url": "https://x/p/1",
            "body_text": "Содержимое спецификации",
        }],
    }
    p = build_prompt(epic_data)
    assert "ТЗ полное" in p
    assert "Содержимое спецификации" in p
```

- [ ] **Step 2: Run test, expect fail**

```
py -3.10 -m pytest tests/test_prompt_build.py -v
```

Expected: FAIL on все 4 кейса (v2-, лимит 1500, child fields отсутствуют, Confluence отсутствует).

- [ ] **Step 3: Update `app/services/llm/prompt.py`**

Заменить `_BASE_VERSION = "v2"` на:

```python
_BASE_VERSION = "v3"
```

Заменить `build_prompt` на:

```python
def build_prompt(epic_data: dict[str, Any], db: Optional[Session] = None) -> str:
    """Build user prompt из агрегированных данных по эпику."""
    role = get_system_role(db)
    parts: list[str] = [role, "", FORMAT_SPEC, "", "ВХОДНЫЕ ДАННЫЕ:"]
    parts.append(f"Проект: {epic_data['summary']} ({epic_data['key']})")
    if epic_data.get("description"):
        desc = epic_data["description"][:8000]
        parts.append(f"Описание: {desc}")
    parts.append(f"Статус: {epic_data['status']} (закрыт: {epic_data.get('is_done', False)})")
    parts.append(
        f"Период: {epic_data.get('period_start')} → {epic_data.get('period_end')} "
        f"(всего {epic_data.get('total_hours', 0)} ч, {epic_data.get('child_count', 0)} задач, "
        f"{epic_data.get('employee_count', 0)} участников)"
    )

    parts.append("\nКатегории трудозатрат:")
    for c in epic_data.get("categories", [])[:8]:
        parts.append(f"  • {c['label']}: {c['hours']} ч")

    parts.append("\nУчастники:")
    for e in epic_data.get("employees", [])[:10]:
        parts.append(f"  • {e['name']}: {e['hours']} ч ({e.get('pct', 0)}%)")

    parts.append("\nТоп-задачи:")
    for t in epic_data.get("top_issues", [])[:5]:
        parts.append(f"  • {t['key']} — {t['summary']} ({t['hours']} ч)")

    summaries = epic_data.get("child_summaries", [])[:30]
    if summaries:
        parts.append("\nДОЧЕРНИЕ ЗАДАЧИ:")
        for s in summaries:
            parts.append(f"\n— {s['key']} — {s['summary']}")
            if s.get("goal_text"):
                parts.append(f"  Цель: {s['goal_text'][:8000]}")
            if s.get("current_behavior"):
                parts.append(f"  Текущее поведение: {s['current_behavior'][:8000]}")
            if s.get("description"):
                parts.append(f"  Описание: {s['description'][:8000]}")

    pages = epic_data.get("confluence_pages", [])
    if pages:
        parts.append("\nCONFLUENCE-СТРАНИЦЫ (полные ТЗ по ссылкам из задач):")
        for pg in pages[:10]:
            parts.append(f"\n— {pg['title']} ({pg['url']})")
            parts.append(pg['body_text'][:8000])

    parts.append("\nВЫДАЙ JSON РЕЗУЛЬТАТ.")
    return "\n".join(parts)
```

- [ ] **Step 4: Run prompt tests, expect pass**

```
py -3.10 -m pytest tests/test_prompt_build.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```
git add app/services/llm/prompt.py tests/test_prompt_build.py
git commit -m "feat(prompt): v3 — 8000-char limit, child desc/goal/behavior, Confluence pages"
```

---

## Task 11: Verify nightly job triggers regen

**Files:**
- Modify: existing `tests/test_jobs_regenerate_summaries.py` (if exists) — sanity check that bumped version triggers `_needs_regeneration`

- [ ] **Step 1: Run full test suite — поиск регрессий**

```
py -3.10 -m pytest tests/ -v -x
```

Если что-то падает по причине наших изменений (например тест опирался на `_build_epic_data` sync) — починить.

- [ ] **Step 2: Run alembic stamp check**

```
py -3.10 -m alembic current
```

Expected: `048_confluence_page_cache (head)`

- [ ] **Step 3: Manual trigger nightly regen на одном эпике (smoke). Опциональный — выполнить только если есть локальный seed:**

```
py -3.10 -c "import asyncio; from app.jobs.regenerate_summaries import regenerate_outdated_summaries; print(asyncio.run(regenerate_outdated_summaries()))"
```

Expected: `{processed: N, regenerated: M, skipped: 0, errors: ...}` где `M ≥ 1` (поскольку `prompt_version` поменялся).

- [ ] **Step 4: Commit (если правки в тестах)**

```
git add tests/
git commit -m "test: align tests with v3 prompt + async _build_epic_data"
```

---

## Task 12: Push to origin/main

- [ ] **Step 1: Verify clean state**

```
git status
git log origin/main..HEAD --oneline
```

- [ ] **Step 2: Push**

```
git push origin main
```

Expected: успешный push 9-12 коммитов.

---

## Notes

- Промпт-версия `v2 → v3` автоматически запустит nightly job (`_needs_regeneration` сравнивает `prompt_version`). Все саммари перегенерятся в течение одного цикла.
- Confluence-кэш TTL 7 дней. На первой генерации эпика fetch ~200-500ms на страницу. После — мгновенно.
- Если у токена нет прав на space — Confluence-запрос падает с 403, логгируется warning, в `cache.error` сохраняется сообщение, `body_text=None` — промпт просто не получает контента, без падения.
- Лимит 10 Confluence-страниц на эпик + 8000 символов на страницу = до 80k символов конкретно из Confluence сверх описаний задач. Gemini 2.0 Flash контекст 1M — спокойно влезает.
- Не покрыто этим планом: подмешивание Confluence в frontend UI (отображение ссылок саммари). Пользователь видит только финальный текст саммари — этого достаточно.
