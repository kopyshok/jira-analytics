# Консоль Jira и Confluence — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** раздел админки, где администратор вставляет строки-запросы к Jira/Confluence, сервер выполняет их своим токеном (только чтение) и отдаёт ответы одним текстом с историей.

**Architecture:** сервис `app/services/console_service.py` (разбор и проверка строк, скрытие имён/почты, выполнение через httpx) + модель `ConsoleRun` с миграцией `dc05_console_runs` + админ-роутер `/admin/console` + вкладка настроек `JiraConsoleTab`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, httpx (MockTransport в тестах), pytest (asyncio_mode=auto), React 19 + AntD 6 + TanStack Query.

Спецификация: `docs/superpowers/specs/2026-10-16-jira-console-design.md`.

**Общие правила для исполнителя**

- Рабочая папка: `D:\ClaudeDev\JiraAnalysis\.worktrees\jira-console`, ветка `feature/jira-console`. Перед каждым коммитом `git branch --show-current` должен показать `feature/jira-console`.
- Python запускать как `py -3.10`. Тесты — в переднем плане, не в фоне.
- Полный прогон: `py -3.10 -m pytest tests/ -q -x --ignore=tests/api/test_llm.py` (LLM-тесты висят без сети).
- Коммит — `git add <конкретные файлы>` и `git commit -F <файл>` или heredoc; не `git commit -- пути`.
- В конце сообщения коммита строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Docstring и комментарии — по-русски, коротко, как в соседнем коде.

---

## Карта файлов

| Файл | Что |
|---|---|
| Create `app/models/console_run.py` | модель запуска консоли |
| Modify `app/models/__init__.py` | регистрация модели |
| Create `alembic/versions/dc05_console_runs.py` | таблица `console_runs` |
| Create `tests/test_migration_dc05_console_runs.py` | миграция вверх/вниз, повторный запуск |
| Create `app/services/console_service.py` | разбор, проверка, скрытие, выполнение |
| Create `tests/services/test_console_service.py` | тесты сервиса |
| Create `app/api/endpoints/admin_console.py` | эндпоинты |
| Modify `app/api/router.py` | подключение роутера (админ) |
| Create `tests/api/test_admin_console.py` | доступ, история, хранение 30 |
| Create `frontend/src/api/console.ts` | клиент API |
| Create `frontend/src/components/settings/JiraConsoleTab.tsx` | экран |
| Modify `frontend/src/pages/SettingsPage.tsx` | пункт меню |

---

### Task 1: Модель и миграция

**Files:**
- Create: `app/models/console_run.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/dc05_console_runs.py`
- Test: `tests/test_migration_dc05_console_runs.py`

- [ ] **Step 1: Тест миграции**

`tests/test_migration_dc05_console_runs.py`:

```python
"""dc05: таблица истории консоли; повторный запуск на базе из create_all не падает."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

from app.models.console_run import ConsoleRun

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _tables(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_and_downgrade_drops(tmp_path):
    db = tmp_path / "m.db"
    _alembic(db, "upgrade", "dc05_console_runs")
    assert "console_runs" in _tables(db)

    _alembic(db, "downgrade", "dc04_drop_local_embeddings")
    assert "console_runs" not in _tables(db)


def test_upgrade_skips_table_from_create_all(tmp_path):
    db = tmp_path / "pre.db"
    _alembic(db, "upgrade", "dc04_drop_local_embeddings")
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        ConsoleRun.__table__.create(engine)
    finally:
        engine.dispose()

    _alembic(db, "upgrade", "dc05_console_runs")
    assert "console_runs" in _tables(db)
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/test_migration_dc05_console_runs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.console_run'`.

- [ ] **Step 3: Модель**

`app/models/console_run.py`:

```python
"""Запуск консоли Jira/Confluence: что спросили и что ответила система.

Хранятся последние 30 запусков (чистит эндпоинт при записи нового). Токена тут
нет; при включённом скрытии результат уже без имён и почты.
"""
from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class ConsoleRun(Base, TimestampMixin):
    """Один запуск консоли. Имя автора — снимком: учётку могут удалить."""

    __tablename__ = "console_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_console_runs_created_at", "created_at"),)
```

В `app/models/__init__.py` после строки
`from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport  # noqa: F401`
добавить:

```python
from app.models.console_run import ConsoleRun  # noqa: F401
```

и в конец списка `__all__` (после `"JiraMigrationDecision",`) добавить `"ConsoleRun",`.

- [ ] **Step 4: Миграция**

`alembic/versions/dc05_console_runs.py`:

```python
"""console_runs

Revision ID: dc05_console_runs
Revises: dc04_drop_local_embeddings
Create Date: 2026-10-16

История консоли Jira/Confluence в админке. Самодостаточна: не импортирует
код приложения. Локальная база может уже иметь таблицу от create_all в
tests/conftest.py — тогда пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc05_console_runs"
down_revision: Union[str, None] = "dc04_drop_local_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has("console_runs"):
        return
    op.create_table(
        "console_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("user_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("masked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_console_runs_created_at", "console_runs", ["created_at"])


def downgrade() -> None:
    if _has("console_runs"):
        op.drop_index("ix_console_runs_created_at", table_name="console_runs")
        op.drop_table("console_runs")
```

- [ ] **Step 5: Тесты зелёные**

Run: `py -3.10 -m pytest tests/test_migration_dc05_console_runs.py tests/test_migrations_fresh_db.py -q`
Expected: PASS (Postgres-тест в `test_migrations_fresh_db.py` может быть пропущен без базы — это нормально).

- [ ] **Step 6: Commit**

```bash
git add app/models/console_run.py app/models/__init__.py alembic/versions/dc05_console_runs.py tests/test_migration_dc05_console_runs.py
git commit -F - <<'EOF'
feat(console): таблица истории консоли Jira/Confluence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Сервис — настройки и проверка строк

**Files:**
- Create: `app/services/console_service.py`
- Test: `tests/services/test_console_service.py`

- [ ] **Step 1: Тесты разбора**

`tests/services/test_console_service.py`:

```python
"""Консоль Jira/Confluence: разбор строк, скрытие имён, выполнение."""
import json

import httpx
import pytest

from app.models.app_setting import AppSetting
from app.services import console_service as cs

BASE = "https://jira.example.ru"


def _one(text: str, base: str = BASE) -> cs.Line:
    lines = cs.parse_lines(text, base, "jira")
    assert len(lines) == 1
    return lines[0]


def test_relative_paths_are_joined_to_base():
    assert _one("/rest/api/2/field").url == f"{BASE}/rest/api/2/field"
    assert _one("rest/api/2/field").url == f"{BASE}/rest/api/2/field"
    assert _one("  /rest/api/2/search?jql=key = OS-1  ").url == (
        f"{BASE}/rest/api/2/search?jql=key = OS-1"
    )


def test_full_link_to_own_host_is_accepted():
    assert _one(f"{BASE}/rest/api/2/serverInfo").url == f"{BASE}/rest/api/2/serverInfo"
    assert _one("HTTPS://JIRA.example.ru/rest/api/2/serverInfo").reject is None


def test_base_with_subfolder():
    base = "https://host.ru/jira"
    assert _one("/rest/api/2/field", base).url == "https://host.ru/jira/rest/api/2/field"
    assert _one("https://host.ru/jira/rest/api/2/field", base).url == (
        "https://host.ru/jira/rest/api/2/field"
    )
    assert _one("https://host.ru/rest/api/2/field", base).reject


@pytest.mark.parametrize("line", [
    "https://evil.com/rest/api/2/field",
    "http://jira.example.ru/rest/api/2/field",
    "https://jira.example.ru:8443/rest/api/2/field",
    "https://user@jira.example.ru/rest/api/2/field",
    "//evil.com/rest/api/2/field",
    "/secure/Dashboard.jspa",
    "/rest/api/2/../../admin",
    "/rest/api/2/%2e%2e/admin",
    "\\\\evil.com\\rest",
    "http:/evil.com/rest/api/2/field",
])
def test_unsafe_lines_are_rejected(line):
    got = _one(line)
    assert got.reject and got.url is None


def test_comments_and_blank_lines():
    lines = cs.parse_lines("# поля\n\n/rest/api/2/field\n", BASE, "jira")
    assert [(l.comment, l.text) for l in lines] == [(True, "# поля"), (False, "/rest/api/2/field")]


def test_too_many_requests_rejects_whole_run():
    text = "\n".join(["# пояснение"] + ["/rest/api/2/field"] * cs.MAX_REQUESTS)
    assert len(cs.parse_lines(text, BASE, "jira")) == cs.MAX_REQUESTS + 1
    with pytest.raises(cs.ConsoleError):
        cs.parse_lines(text + "\n/rest/api/2/field", BASE, "jira")


def test_no_requests_is_an_error():
    with pytest.raises(cs.ConsoleError):
        cs.parse_lines("# только пояснение\n\n", BASE, "jira")


def _set(db, key, value):
    db.add(AppSetting(key=key, value=value))


def test_credentials_from_settings(db_session):
    _set(db_session, "jira_base_url", "https://jira.example.ru/")
    _set(db_session, "jira_api_token", "t1")
    _set(db_session, "confluence_base_url", "https://wiki.example.ru")
    _set(db_session, "confluence_api_token", "t2")
    db_session.commit()
    assert cs.credentials(db_session, "jira") == ("https://jira.example.ru", "t1")
    assert cs.credentials(db_session, "confluence") == ("https://wiki.example.ru", "t2")


def test_missing_confluence_credentials(db_session):
    with pytest.raises(cs.ConsoleError, match="Подключение к Confluence"):
        cs.credentials(db_session, "confluence")
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'console_service'`.

- [ ] **Step 3: Реализация**

`app/services/console_service.py`:

```python
"""Консоль Jira и Confluence: запросы на чтение от имени сервера.

Машина разработки Jira не видит, сервер видит. Администратор вставляет строки-
запросы, сервер отправляет их своим токеном и отдаёт ответы одним текстом.
Только GET, только на адрес системы из настроек и только пути `rest/…` —
иначе токен ушёл бы на чужой сервер.
"""
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

MAX_REQUESTS = 50
TARGET_TITLES = {"jira": "Jira", "confluence": "Confluence"}


class ConsoleError(Exception):
    """Запуск целиком невозможен: нет настроек, нет запросов, их слишком много."""


@dataclass
class Line:
    """Строка ввода: пояснение, проверенный запрос (`url`) или отказ (`reject`)."""

    text: str
    comment: bool = False
    url: Optional[str] = None
    reject: Optional[str] = None


def _setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else None


def credentials(db: Session, target: str) -> tuple[str, str]:
    """Адрес и токен системы. У Jira — запасной вариант из .env, как у синка."""
    if target == "jira":
        env = get_settings()
        base = _setting(db, "jira_base_url") or env.jira_base_url
        token = _setting(db, "jira_api_token") or env.jira_api_token
        section = "«Подключение к Jira»"
    else:
        base = _setting(db, "confluence_base_url")
        token = _setting(db, "confluence_api_token")
        section = "«Подключение к Confluence»"
    if not (base and token):
        raise ConsoleError(f"Не указаны адрес или токен — заполните раздел настроек {section}")
    return base.rstrip("/"), token


def _check(s: str, base: str, title: str) -> Line:
    """Привести строку к адресу внутри системы или отклонить с причиной."""
    b = urlsplit(base)
    base_path = b.path.rstrip("/")
    if s.startswith("//") or "\\" in s:
        return Line(s, reject=f"ссылка ведёт не на {title}")
    if "://" in s.split("?", 1)[0]:
        u = urlsplit(s)
        same = (u.scheme.lower(), u.netloc.lower()) == (b.scheme.lower(), b.netloc.lower())
        if not same or not u.path.startswith(base_path + "/"):
            return Line(s, reject=f"ссылка ведёт не на {title}")
        rel, query = u.path[len(base_path) + 1:], u.query
    else:
        rel, _, query = s.lstrip("/").partition("?")
    if not rel.startswith("rest/"):
        return Line(s, reject="путь после адреса должен начинаться с rest/")
    if ".." in rel or "%2e" in rel.lower():
        return Line(s, reject="в пути нельзя «..»")
    url = f"{base}/{rel}" + (f"?{query}" if query else "")
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return Line(s, reject="неверная ссылка")
    # ponytail: страховка поверх разбора выше — хост итогового адреса = хост системы.
    if (parsed.scheme, parsed.host) != (b.scheme.lower(), b.hostname or ""):
        return Line(s, reject=f"ссылка ведёт не на {title}")
    return Line(s, url=url)


def parse_lines(text: str, base: str, target: str) -> list[Line]:
    """Разобрать ввод: `#` — пояснение, пустые строки пропускаются."""
    title = TARGET_TITLES[target]
    lines: list[Line] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        lines.append(Line(s, comment=True) if s.startswith("#") else _check(s, base, title))
    count = sum(1 for line in lines if not line.comment)
    if count == 0:
        raise ConsoleError("Нет ни одного запроса")
    if count > MAX_REQUESTS:
        raise ConsoleError(f"Не больше {MAX_REQUESTS} запросов за один запуск, сейчас {count}")
    return lines
```

Примечание к проверке хоста: порт сравнивается раньше — через `netloc` у полной ссылки; у относительной адрес собран из адреса системы. `parsed.host` у httpx и `b.hostname` у urlsplit — оба в нижнем регистре.

- [ ] **Step 4: Тесты зелёные**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/console_service.py tests/services/test_console_service.py
git commit -F - <<'EOF'
feat(console): разбор и проверка строк-запросов консоли

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Сервис — скрытие имён и почты

**Files:**
- Modify: `app/services/console_service.py`
- Test: `tests/services/test_console_service.py`

- [ ] **Step 1: Тесты**

Дописать в `tests/services/test_console_service.py`:

```python
def test_masker_replaces_names_and_mail_consistently():
    m = cs.Masker()
    data = {
        "author": {"name": "Ivanov_I_I", "key": "JIRAUSER1", "displayName": "Иванов Иван",
                   "emailAddress": "Ivanov@corp.ru"},
        "comments": [{"author": {"displayName": "Иванов Иван", "emailAddress": "ivanov@corp.ru"}},
                     {"author": {"displayName": "Петров Пётр", "email": "p@corp.ru"}}],
    }
    got = m.walk(data)
    assert got["author"] == {"name": "Ivanov_I_I", "key": "JIRAUSER1",
                             "displayName": "Человек-1", "emailAddress": "почта-1"}
    assert got["comments"][0]["author"] == {"displayName": "Человек-1", "emailAddress": "почта-1"}
    assert got["comments"][1]["author"] == {"displayName": "Человек-2", "email": "почта-2"}


def test_masker_scrubs_free_text():
    m = cs.Masker()
    m.walk({"displayName": "Иванов Иван"})
    text = 'Согласовано: Иванов Иван, копия ivanov@corp.ru, Sprint@4e7c[id=5]'
    assert m.scrub(text) == "Согласовано: Человек-1, копия почта-1, Sprint@4e7c[id=5]"


def test_masker_keeps_short_names_in_text():
    m = cs.Masker()
    m.walk({"displayName": "Jira"})
    assert m.scrub("Jira Software") == "Jira Software"
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q -k masker`
Expected: FAIL — `AttributeError: module ... has no attribute 'Masker'`.

- [ ] **Step 3: Реализация**

В `app/services/console_service.py`:
- в импорты добавить `import re` и `from typing import Any, Optional` (заменить `from typing import Optional`);
- после класса `Line` добавить:

```python
_MAIL_KEYS = {"emailAddress", "email"}
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class Masker:
    """Заменяет имена и почту метками «Человек-N» / «почта-N» в рамках запуска.

    Логины, `key` и номера учёток не трогает — по ним сверяем людей.
    """

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self._count = {"Человек": 0, "почта": 0}

    def _label(self, value: str, kind: str) -> str:
        key = value.strip().lower() if kind == "почта" else value.strip()
        if key not in self._labels:
            self._count[kind] += 1
            self._labels[key] = f"{kind}-{self._count[kind]}"
        return self._labels[key]

    def walk(self, data: Any) -> Any:
        """Заменить значения полей имени и почты в разобранном ответе."""
        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for k, v in data.items():
                if k == "displayName" and isinstance(v, str) and v.strip():
                    out[k] = self._label(v, "Человек")
                elif k in _MAIL_KEYS and isinstance(v, str) and v.strip():
                    out[k] = self._label(v, "почта")
                else:
                    out[k] = self.walk(v)
            return out
        if isinstance(data, list):
            return [self.walk(v) for v in data]
        return data

    def scrub(self, text: str) -> str:
        """Заменить в тексте уже встреченные имена и любые адреса почты."""
        names = [k for k in self._labels if " " in k and len(k) >= 5]
        # ponytail: имя из одного слова («Jira», «Admin») в тексте не ищем — заденет обычные слова.
        for name in sorted(names, key=len, reverse=True):
            text = text.replace(name, self._labels[name])
        return _EMAIL_RE.sub(lambda m: self._label(m.group(0), "почта"), text)
```

- [ ] **Step 4: Тесты зелёные**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/console_service.py tests/services/test_console_service.py
git commit -F - <<'EOF'
feat(console): скрытие имён и почты в ответах консоли

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Сервис — выполнение и текст результата

**Files:**
- Modify: `app/services/console_service.py`
- Test: `tests/services/test_console_service.py`

- [ ] **Step 1: Тесты**

Дописать в `tests/services/test_console_service.py`:

```python
def _transport(routes: dict):
    """Ответы по пути; значение — httpx.Response или исключение."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        got = routes[request.url.path]
        if isinstance(got, Exception):
            raise got
        return got

    return httpx.MockTransport(handler), seen


async def _run(text, routes, mask=False, **kw):
    transport, seen = _transport(routes)
    lines = cs.parse_lines(text, BASE, "jira")
    result = await cs.execute(lines, "jira", mask, BASE, "secret-token", transport=transport, **kw)
    return result, seen


async def test_execute_formats_blocks_and_counts():
    result, seen = await _run(
        "# сервер\n/rest/api/2/serverInfo\n/rest/api/2/issue/OS-1\n//evil.com/x",
        {
            "/rest/api/2/serverInfo": httpx.Response(200, json={"version": "11.3.7"}),
            "/rest/api/2/issue/OS-1": httpx.Response(404, json={"errorMessages": ["Issue Does Not Exist"]}),
        },
    )
    out = result.output
    assert out.startswith("=== Jira ===\nЗапросов: 3, с ошибкой: 1, отклонено: 1, не выполнено: 0")
    assert "# сервер\n### 1. /rest/api/2/serverInfo\n→ 200 · " in out
    assert '{\n  "version": "11.3.7"\n}' in out
    assert "### 2. /rest/api/2/issue/OS-1\n→ 404 · " in out
    assert "Issue Does Not Exist" in out
    assert "### 3. //evil.com/x\n→ отклонено: ссылка ведёт не на Jira" in out
    assert (result.request_count, result.error_count, result.rejected_count) == (3, 1, 1)
    assert [r.method for r in seen] == ["GET", "GET"]
    assert seen[0].headers["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in out


async def test_execute_non_json_redirect_and_network_error():
    result, _ = await _run(
        "/rest/a\n/rest/b\n/rest/c",
        {
            "/rest/a": httpx.Response(200, text="<html>вход</html>"),
            "/rest/b": httpx.Response(302, headers={"location": "https://sso.example.ru/login"}),
            "/rest/c": httpx.ConnectError("refused"),
        },
    )
    assert "<html>вход</html>" in result.output
    assert "→ 302 · " in result.output and "Перенаправление: https://sso.example.ru/login" in result.output
    assert "### 3. /rest/c\n→ нет ответа: ConnectError" in result.output
    assert result.error_count == 1


async def test_execute_masks_across_requests():
    result, _ = await _run(
        "/rest/a\n/rest/b",
        {
            "/rest/a": httpx.Response(200, text="Ответственный: Иванов Иван"),
            "/rest/b": httpx.Response(200, json={"assignee": {"displayName": "Иванов Иван",
                                                              "name": "Ivanov_I_I"}}),
        },
        mask=True,
    )
    assert result.output.startswith("=== Jira · имена и почта скрыты ===")
    assert "Иванов Иван" not in result.output
    assert "Ответственный: Человек-1" in result.output
    assert '"name": "Ivanov_I_I"' in result.output


async def test_execute_truncates_long_response(monkeypatch):
    monkeypatch.setattr(cs, "MAX_RESPONSE_CHARS", 10)
    result, _ = await _run("/rest/a", {"/rest/a": httpx.Response(200, text="x" * 50)})
    assert "xxxxxxxxxx\n… обрезано, показано" in result.output
    assert "x" * 11 not in result.output


async def test_execute_stops_on_output_limit(monkeypatch):
    monkeypatch.setattr(cs, "MAX_OUTPUT_CHARS", 10)
    result, seen = await _run("/rest/a\n/rest/b",
                              {"/rest/a": httpx.Response(200, text="x" * 20),
                               "/rest/b": httpx.Response(200, text="y")})
    assert len(seen) == 1
    assert "### 2. /rest/b\n→ не выполнено — результат слишком большой" in result.output


async def test_execute_stops_on_time_budget():
    ticks = iter([0.0, 0.0, 0.0, 200.0, 200.0, 200.0, 200.0])
    result, seen = await _run("/rest/a\n/rest/b",
                              {"/rest/a": httpx.Response(200, text="a"),
                               "/rest/b": httpx.Response(200, text="b")},
                              clock=lambda: next(ticks))
    assert len(seen) == 1
    assert "### 2. /rest/b\n→ не выполнено — вышло общее время" in result.output
```

Как считается `ticks` в последнем тесте: `start` (0) → запрос 1: остаток бюджета (0) → начало запроса (0) → конец запроса (200) → запрос 2: остаток бюджета (200 → бюджет вышел) → итоговое время (200) → длительность (200). Если реализация зовёт часы в другом порядке — поправь список `ticks` под реализацию, а не реализацию под список; смысл теста: первый запрос выполнен, второй — нет.

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q -k execute`
Expected: FAIL — `AttributeError: ... has no attribute 'execute'`.

- [ ] **Step 3: Реализация**

В `app/services/console_service.py`:
- в импорты добавить `import json`, `import time`, `from typing import Any, Callable, Optional`;
- после `MAX_REQUESTS = 50` добавить константы:

```python
REQUEST_TIMEOUT_S = 60.0
# Прокси на сервере рвёт запрос через 120 с — оставляем запас.
RUN_BUDGET_S = 100.0
MAX_RESPONSE_CHARS = 5 * 1024 * 1024
MAX_OUTPUT_CHARS = 10 * 1024 * 1024
```

- в конец файла добавить:

```python
@dataclass
class RunResult:
    output: str
    request_count: int
    error_count: int
    rejected_count: int
    duration_ms: int


def _secs(seconds: float, digits: int = 2) -> str:
    return f"{seconds:.{digits}f}".replace(".", ",")


def _mb(chars: int) -> str:
    return f"{chars / 1024 / 1024:.1f}".replace(".", ",")


def _body(resp: httpx.Response, masker: Optional[Masker]) -> str:
    """Тело ответа: JSON с отступами, иначе текст; длинное — обрезать."""
    if 300 <= resp.status_code < 400:
        return f"Перенаправление: {resp.headers.get('location', '—')}"
    try:
        data = resp.json()
    except ValueError:
        text = resp.text
    else:
        if masker:
            data = masker.walk(data)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > MAX_RESPONSE_CHARS:
        text = (
            text[:MAX_RESPONSE_CHARS]
            + f"\n… обрезано, показано {_mb(MAX_RESPONSE_CHARS)} МБ из {_mb(len(text))} МБ"
        )
    return text


async def execute(
    lines: list[Line],
    target: str,
    mask: bool,
    base: str,
    token: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Выполнить запросы по очереди и собрать один текст.

    Ошибка одного запроса пакет не останавливает. Когда вышло общее время или
    результат стал слишком большим, оставшиеся строки помечаются невыполненными.
    """
    masker = Masker() if mask else None
    start = clock()
    # (заголовок, тело или None, пустая строка после блока)
    blocks: list[tuple[list[str], Optional[str], bool]] = []
    count = errors = rejected = skipped = total = 0
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=False, transport=transport,
    ) as client:
        for line in lines:
            if line.comment:
                blocks.append(([line.text], None, False))
                continue
            count += 1
            head = [f"### {count}. {line.text}"]
            if line.reject or not line.url:
                rejected += 1
                blocks.append((head + [f"→ отклонено: {line.reject}"], None, True))
                continue
            left = RUN_BUDGET_S - (clock() - start)
            if left <= 0:
                skipped += 1
                blocks.append((head + ["→ не выполнено — вышло общее время, запустите эти строки отдельно"], None, True))
                continue
            if total >= MAX_OUTPUT_CHARS:
                skipped += 1
                blocks.append((head + ["→ не выполнено — результат слишком большой"], None, True))
                continue
            t0 = clock()
            try:
                resp = await client.get(line.url, timeout=min(REQUEST_TIMEOUT_S, left))
            except httpx.TimeoutException:
                errors += 1
                blocks.append((head + [f"→ нет ответа за {_secs(clock() - t0)} с"], None, True))
                continue
            except (httpx.HTTPError, httpx.InvalidURL) as e:
                errors += 1
                blocks.append((head + [f"→ нет ответа: {type(e).__name__}: {e}"], None, True))
                continue
            if resp.status_code >= 400:
                errors += 1
            body = _body(resp, masker)
            total += len(body)
            blocks.append((head + [f"→ {resp.status_code} · {_secs(clock() - t0)} с"], body, True))

    elapsed = clock() - start
    out = [
        f"=== {TARGET_TITLES[target]}{' · имена и почта скрыты' if mask else ''} ===",
        f"Запросов: {count}, с ошибкой: {errors}, отклонено: {rejected}, "
        f"не выполнено: {skipped}, время: {_secs(elapsed, 1)} с",
        "",
    ]
    for head, body, gap in blocks:
        out.extend(head)
        if body is not None:
            # Имена из поздних ответов скрываем и в ранних — поэтому в самом конце.
            out.append(masker.scrub(body) if masker else body)
        if gap:
            out.append("")
    return RunResult(
        output="\n".join(out).rstrip() + "\n",
        request_count=count,
        error_count=errors,
        rejected_count=rejected,
        duration_ms=int(elapsed * 1000),
    )
```

- [ ] **Step 4: Тесты зелёные**

Run: `py -3.10 -m pytest tests/services/test_console_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/console_service.py tests/services/test_console_service.py
git commit -F - <<'EOF'
feat(console): выполнение запросов консоли и текст результата

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Эндпоинты и история

**Files:**
- Create: `app/api/endpoints/admin_console.py`
- Modify: `app/api/router.py`
- Test: `tests/api/test_admin_console.py`

- [ ] **Step 1: Тесты**

`tests/api/test_admin_console.py`:

```python
"""Консоль Jira/Confluence: доступ, запуск, история."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from app.models.console_run import ConsoleRun
from app.models.user import User, UserRole
from app.services import console_service as cs

URL = "/api/v1/admin/console"


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def jira_settings(testclient_db_session):
    testclient_db_session.add(AppSetting(key="jira_base_url", value="https://jira.example.ru"))
    testclient_db_session.add(AppSetting(key="jira_api_token", value="t"))
    testclient_db_session.commit()


@pytest.fixture
def fake_execute(monkeypatch):
    calls = []

    async def fake(lines, target, mask, base, token, **kw):
        calls.append((lines, target, mask, base, token))
        return cs.RunResult(output="=== Jira ===\nok\n", request_count=1,
                            error_count=0, rejected_count=0, duration_ms=5)

    monkeypatch.setattr(cs, "execute", fake)
    return calls


@pytest.mark.no_auth_bypass
def test_only_admin(testclient_db_session):
    email = f"console_{uuid.uuid4().hex[:8]}@example.com"
    testclient_db_session.add(User(id=str(uuid.uuid4()), email=email,
                                   password_hash=hash_password("pass123"),
                                   display_name="Менеджер", role=UserRole.manager))
    testclient_db_session.commit()
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        c = TestClient(app)
        token = c.post("/api/v1/auth/login", json={"email": email, "password": "pass123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert c.get(f"{URL}/runs", headers=headers).status_code == 403
        assert c.post(f"{URL}/run", headers=headers,
                      json={"target": "jira", "text": "/rest/api/2/field"}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_run_saves_history(client, jira_settings, fake_execute):
    r = client.post(f"{URL}/run", json={"target": "jira", "text": "# x\n/rest/api/2/field", "mask": True})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["output_text"] == "=== Jira ===\nok\n"
    assert run["first_line"] == "/rest/api/2/field"
    assert run["user_name"] == "Test User" and run["masked"] is True
    assert run["created_at"].endswith("Z")
    assert fake_execute[0][1:] == ("jira", True, "https://jira.example.ru", "t")

    items = client.get(f"{URL}/runs").json()["items"]
    assert [i["id"] for i in items] == [run["id"]]
    assert "output_text" not in items[0]

    full = client.get(f"{URL}/runs/{run['id']}").json()
    assert full["input_text"] == "# x\n/rest/api/2/field"

    assert client.delete(f"{URL}/runs/{run['id']}").status_code == 204
    assert client.get(f"{URL}/runs/{run['id']}").status_code == 404


def test_run_without_settings_is_400(client, fake_execute):
    r = client.post(f"{URL}/run", json={"target": "confluence", "text": "/rest/api/space"})
    assert r.status_code == 400
    assert "Подключение к Confluence" in r.json()["detail"]
    assert fake_execute == []


def test_keeps_last_30_runs(client, jira_settings, fake_execute, testclient_db_session):
    old = datetime.utcnow() - timedelta(days=1)
    for i in range(30):
        testclient_db_session.add(ConsoleRun(
            target="jira", input_text=f"/rest/{i}", output_text="", user_name="x",
            created_at=old + timedelta(minutes=i), updated_at=old,
        ))
    testclient_db_session.commit()

    new_id = client.post(f"{URL}/run", json={"target": "jira", "text": "/rest/api/2/field"}).json()["id"]
    items = client.get(f"{URL}/runs").json()["items"]
    assert len(items) == 30
    assert items[0]["id"] == new_id
    assert "/rest/0" not in [i["first_line"] for i in items]
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `py -3.10 -m pytest tests/api/test_admin_console.py -q`
Expected: FAIL — 404 на `/api/v1/admin/console/...` (роутера нет).

- [ ] **Step 3: Эндпоинты**

`app/api/endpoints/admin_console.py`:

```python
"""Консоль Jira и Confluence — запросы на чтение от имени сервера. Только администратор."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.console_run import ConsoleRun
from app.models.user import User
from app.services import console_service

router = APIRouter()

KEEP_RUNS = 30


class RunIn(BaseModel):
    target: Literal["jira", "confluence"]
    text: str = Field(max_length=100_000)
    mask: bool = True


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _first_line(text: str) -> str:
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _brief(r: ConsoleRun) -> dict:
    return {
        "id": r.id,
        "created_at": _iso(r.created_at),
        "user_name": r.user_name,
        "target": r.target,
        "masked": r.masked,
        "first_line": _first_line(r.input_text),
        "request_count": r.request_count,
        "error_count": r.error_count,
        "rejected_count": r.rejected_count,
        "duration_ms": r.duration_ms,
    }


def _full(r: ConsoleRun) -> dict:
    return {**_brief(r), "input_text": r.input_text, "output_text": r.output_text}


def _prune(db: Session) -> None:
    """Оставить последние KEEP_RUNS запусков."""
    old = [
        row.id for row in db.query(ConsoleRun.id)
        .order_by(ConsoleRun.created_at.desc(), ConsoleRun.id.desc())
        .offset(KEEP_RUNS)
    ]
    if old:
        db.query(ConsoleRun).filter(ConsoleRun.id.in_(old)).delete(synchronize_session=False)
        db.commit()


@router.post("/run")
async def run(
    body: RunIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Выполнить строки и сохранить запуск в историю."""
    try:
        base, token = console_service.credentials(db, body.target)
        lines = console_service.parse_lines(body.text, base, body.target)
    except console_service.ConsoleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await console_service.execute(lines, body.target, body.mask, base, token)
    row = ConsoleRun(
        user_id=user.id,
        user_name=user.display_name or user.email,
        target=body.target,
        masked=body.mask,
        input_text=body.text,
        output_text=result.output,
        request_count=result.request_count,
        error_count=result.error_count,
        rejected_count=result.rejected_count,
        duration_ms=result.duration_ms,
    )
    db.add(row)
    db.commit()
    _prune(db)
    db.refresh(row)
    return _full(row)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)) -> dict:
    """Свежие запуски первыми, без текста результата."""
    rows = db.query(ConsoleRun).order_by(ConsoleRun.created_at.desc(), ConsoleRun.id.desc()).all()
    return {"items": [_brief(r) for r in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(ConsoleRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return _full(row)


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, db: Session = Depends(get_db)) -> None:
    row = db.get(ConsoleRun, run_id)
    if row:
        db.delete(row)
        db.commit()
```

Важно: `console_service.execute` вызывается через модуль (`console_service.execute(...)`), а не импортом имени — тест подменяет его `monkeypatch.setattr(cs, "execute", ...)`.

- [ ] **Step 4: Подключить роутер**

В `app/api/router.py`:
- рядом с импортом `admin_errors` добавить
  `from app.api.endpoints import admin_console as admin_console_endpoints`
- после блока `admin_errors_endpoints.router` (prefix `/admin/errors`) добавить:

```python
api_router.include_router(
    admin_console_endpoints.router,
    prefix="/admin/console",
    tags=["admin-console"],
    dependencies=_admin_dep,
)
```

- [ ] **Step 5: Тесты зелёные**

Run: `py -3.10 -m pytest tests/api/test_admin_console.py tests/services/test_console_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/endpoints/admin_console.py app/api/router.py tests/api/test_admin_console.py
git commit -F - <<'EOF'
feat(console): эндпоинты консоли и история последних 30 запусков

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Экран в настройках

**Files:**
- Create: `frontend/src/api/console.ts`
- Create: `frontend/src/components/settings/JiraConsoleTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Клиент API**

`frontend/src/api/console.ts`:

```ts
import { api } from './client';

export type ConsoleTarget = 'jira' | 'confluence';

export interface ConsoleRunBrief {
  id: string;
  created_at: string;
  user_name: string;
  target: ConsoleTarget;
  masked: boolean;
  first_line: string;
  request_count: number;
  error_count: number;
  rejected_count: number;
  duration_ms: number;
}

export interface ConsoleRun extends ConsoleRunBrief {
  input_text: string;
  output_text: string;
}

export const consoleApi = {
  run: (body: { target: ConsoleTarget; text: string; mask: boolean }) =>
    api.post<ConsoleRun>('/admin/console/run', body),
  list: () => api.get<{ items: ConsoleRunBrief[] }>('/admin/console/runs'),
  get: (id: string) => api.get<ConsoleRun>(`/admin/console/runs/${id}`),
  remove: (id: string) => api.del<void>(`/admin/console/runs/${id}`),
};
```

- [ ] **Step 2: Экран**

`frontend/src/components/settings/JiraConsoleTab.tsx`:

```tsx
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Checkbox, Input, Popconfirm, Segmented, Space, Table, Typography } from 'antd';
import { CopyOutlined, DeleteOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { consoleApi } from '../../api/console';
import type { ConsoleRun, ConsoleRunBrief, ConsoleTarget } from '../../api/console';

const { Text, Paragraph } = Typography;

const TITLES: Record<ConsoleTarget, string> = { jira: 'Jira', confluence: 'Confluence' };

// Готовые запросы: кнопка дописывает строки в конец поля, КЛЮЧ/НОМЕР заменить руками.
const PRESETS: Record<ConsoleTarget, { label: string; lines: string[] }[]> = {
  jira: [
    { label: 'Сведения о сервере', lines: ['/rest/api/2/serverInfo'] },
    { label: 'Все поля', lines: ['/rest/api/2/field'] },
    { label: 'Задача по ключу', lines: ['/rest/api/2/issue/КЛЮЧ'] },
    { label: 'Списания задачи', lines: ['/rest/api/2/issue/КЛЮЧ/worklog'] },
    { label: 'Поиск по условию', lines: ['/rest/api/2/search?jql=project = КЛЮЧ_ПРОЕКТА&maxResults=5'] },
    {
      label: 'Диагностический пакет',
      lines: [
        '# Диагностический пакет',
        '/rest/api/2/serverInfo',
        '/rest/api/2/myself',
        '/rest/api/2/field',
        '/rest/api/2/issuetype',
        '/rest/api/2/status',
        '/rest/api/2/priority',
        '/rest/api/2/resolution',
        '/rest/api/2/issueLinkType',
        '/rest/api/2/project',
      ],
    },
  ],
  confluence: [
    { label: 'Текущий пользователь', lines: ['/rest/api/user/current'] },
    { label: 'Пространства', lines: ['/rest/api/space?limit=50'] },
    { label: 'Страница по номеру', lines: ['/rest/api/content/НОМЕР?expand=version,space'] },
  ],
};

function fmt(dt: string): string {
  return new Date(dt).toLocaleString('ru-RU');
}

// Буфер обмена доступен только на https; иначе — через скрытое поле.
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  }
}

function downloadRun(run: ConsoleRun) {
  const d = new Date(run.created_at);
  const p = (n: number) => String(n).padStart(2, '0');
  const name = `${run.target}-console-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.txt`;
  const url = URL.createObjectURL(new Blob([run.output_text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function JiraConsoleTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [target, setTarget] = useState<ConsoleTarget>('jira');
  const [text, setText] = useState('');
  const [mask, setMask] = useState(true);
  const [current, setCurrent] = useState<ConsoleRun | null>(null);

  const history = useQuery({
    queryKey: ['admin', 'console-runs'],
    queryFn: () => consoleApi.list(),
  });

  const runMut = useMutation({
    mutationFn: () => consoleApi.run({ target, text, mask }),
    onSuccess: (run) => {
      setCurrent(run);
      qc.invalidateQueries({ queryKey: ['admin', 'console-runs'] });
    },
    onError: (e: Error) => notification.error({ title: 'Запуск не выполнен', description: e.message }),
  });

  const openMut = useMutation({
    mutationFn: (id: string) => consoleApi.get(id),
    onSuccess: (run) => {
      setCurrent(run);
      setTarget(run.target);
      setText(run.input_text);
      setMask(run.masked);
    },
    onError: () => notification.error({ title: 'Не удалось открыть запуск' }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => consoleApi.remove(id),
    onSuccess: (_, id) => {
      if (current?.id === id) setCurrent(null);
      qc.invalidateQueries({ queryKey: ['admin', 'console-runs'] });
    },
    onError: () => notification.error({ title: 'Не удалось удалить запуск' }),
  });

  const addPreset = (lines: string[]) =>
    setText((prev) => (prev.trim() ? `${prev.replace(/\s+$/, '')}\n` : '') + lines.join('\n'));

  const copy = async () => {
    if (!current) return;
    const ok = await copyText(current.output_text);
    if (ok) notification.success({ title: 'Результат скопирован' });
    else notification.error({ title: 'Не удалось скопировать — скачайте файлом' });
  };

  const columns = [
    { title: 'Когда', dataIndex: 'created_at', width: 170, render: (v: string) => fmt(v) },
    { title: 'Кто', dataIndex: 'user_name', width: 180 },
    { title: 'Система', dataIndex: 'target', width: 110, render: (v: ConsoleTarget) => TITLES[v] },
    {
      title: 'Запросов',
      width: 140,
      render: (_: unknown, r: ConsoleRunBrief) =>
        `${r.request_count}${r.error_count ? `, ошибок ${r.error_count}` : ''}`,
    },
    { title: 'Запрос', dataIndex: 'first_line', ellipsis: true },
    {
      title: '',
      width: 170,
      render: (_: unknown, r: ConsoleRunBrief) => (
        <Space>
          <Button size="small" onClick={() => openMut.mutate(r.id)}>Открыть</Button>
          <Popconfirm title="Удалить запуск из истории?" onConfirm={() => deleteMut.mutate(r.id)}>
            <Button size="small" icon={<DeleteOutlined />} aria-label="Удалить" />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        Сервер отправляет запросы на чтение своим токеном и показывает ответы одним текстом.
        Одна строка — один запрос: ссылка из браузера или её часть после адреса системы.
        Строки с «#» — пояснения. Изменить что-либо в Jira или Confluence отсюда нельзя.
      </Paragraph>

      <Space wrap>
        <Segmented
          value={target}
          onChange={(v) => setTarget(v as ConsoleTarget)}
          options={[{ value: 'jira', label: 'Jira' }, { value: 'confluence', label: 'Confluence' }]}
        />
        {PRESETS[target].map((p) => (
          <Button key={p.label} size="small" onClick={() => addPreset(p.lines)}>{p.label}</Button>
        ))}
      </Space>

      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        placeholder={'/rest/api/2/serverInfo\n# поля задач\n/rest/api/2/field'}
        style={{ fontFamily: 'monospace' }}
      />

      <Space wrap>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={runMut.isPending}
          disabled={!text.trim()}
          onClick={() => runMut.mutate()}
        >
          Выполнить
        </Button>
        <Checkbox checked={mask} onChange={(e) => setMask(e.target.checked)}>
          Скрыть имена и почту
        </Checkbox>
      </Space>

      {runMut.isPending && (
        <Alert type="info" showIcon title="Запросы выполняются по очереди — это может занять до полутора минут" />
      )}

      {current && (
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>Результат от {fmt(current.created_at)}</Text>
            <Button icon={<CopyOutlined />} onClick={copy}>Скопировать всё</Button>
            <Button icon={<DownloadOutlined />} onClick={() => downloadRun(current)}>Скачать файлом</Button>
          </Space>
          <Input.TextArea
            value={current.output_text}
            readOnly
            rows={24}
            style={{ fontFamily: 'monospace' }}
          />
        </Space>
      )}

      <div>
        <Text strong>История (последние 30 запусков)</Text>
        <Table
          rowKey="id"
          size="small"
          loading={history.isLoading}
          columns={columns}
          dataSource={history.data?.items ?? []}
          pagination={false}
          style={{ marginTop: 8 }}
        />
      </div>
    </Space>
  );
}
```

В AntD 6 этого проекта у `Alert` — `title` (не `message`), у `Space` — `orientation` (не `direction`), у `notification` — `title`; так и написано выше.

- [ ] **Step 3: Пункт меню**

В `frontend/src/pages/SettingsPage.tsx`:
- рядом с `import ServerErrorsTab from '../components/settings/ServerErrorsTab';` добавить
  `import JiraConsoleTab from '../components/settings/JiraConsoleTab';`
- в группе «Администрирование» сразу после строки `{ key: 'errors', ... ServerErrorsTab ... }` добавить:

```tsx
      { key: 'console', label: 'Консоль Jira и Confluence', adminOnly: true, render: () => <JiraConsoleTab /> },
```

- [ ] **Step 4: Линтер и сборка**

Run (из `frontend/`): `npx eslint src/api/console.ts src/components/settings/JiraConsoleTab.tsx src/pages/SettingsPage.tsx`
Expected: без ошибок в этих файлах.

Run (из `frontend/`): `npm run build`
Expected: сборка успешна. Если ругается на чужие файлы, которые ты не трогал, — зафиксировать в отчёте, не чинить.

Не забудь: сборка может создать `app/static` — не коммитить (проверь `git status`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/console.ts frontend/src/components/settings/JiraConsoleTab.tsx frontend/src/pages/SettingsPage.tsx
git commit -F - <<'EOF'
feat(console): раздел «Консоль Jira и Confluence» в настройках

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: Итоговая проверка

- [ ] **Step 1:** `ruff check app/ tests/` — без новых замечаний в файлах этой ветки.
- [ ] **Step 2:** `py -3.10 -m mypy app/services/console_service.py app/api/endpoints/admin_console.py app/models/console_run.py` — без ошибок.
- [ ] **Step 3:** `py -3.10 -m pytest tests/ -q -x --ignore=tests/api/test_llm.py` — зелёный.
- [ ] **Step 4:** Commit исправлений, если были.
