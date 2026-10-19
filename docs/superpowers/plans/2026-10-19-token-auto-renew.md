# Самопродление токенов Jira и Confluence — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сервис сам продлевает персональные токены Jira и Confluence (срок 14 дней по требованию СБ), предупреждает администратора при сбое.

**Architecture:** новый модуль `app/services/token_renewal.py` (httpx напрямую, без JiraClient — нужен путь `/rest/pat/...` вне `/rest/api/2`), задание APScheduler раз в час, состояние — JSON в одной записи AppSetting на систему. Включается флагом `TOKEN_AUTO_RENEW` (в Docker-образе `true`, по умолчанию `false`). Интерфейс: эндпоинт статуса под `/settings`, строка в карточках подключения, плашка админу в оболочке.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, httpx, respx (тесты), APScheduler 3; React 19, AntD 6, TanStack Query, dayjs.

Спека: `docs/superpowers/specs/2026-10-19-token-auto-renew-design.md`.

Общие правила:
- Рабочая папка — worktree `D:\ClaudeDev\JiraAnalysis\.worktrees\token-renew`, ветка `feature/token-auto-renew`. Не переключать ветки, не трогать другие worktree, не делать push.
- Тесты: `py -3.10 -m pytest ...` (pytest под дефолтным Python не стоит). Тесты запускать в переднем плане.
- Docstrings/комментарии — на русском, в стиле соседнего кода.
- Коммит после каждой задачи: `git add <файлы>` + `git commit -F <файл сообщения>` (не `-m @'...'`). В конце сообщения строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Планировщик не снимает чужие задания при смене расписания синка

Сейчас `register_jobs` вызывает `remove_all_jobs()`: при правке расписания синка в UI (`app/api/endpoints/sync.py` ~1080) пропадают задания `regenerate_summaries`, `aggregate_usage` (и будущее `renew_tokens`) до перезапуска.

**Files:**
- Modify: `app/services/scheduler.py` (`__init__`, `register_jobs`)
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Тест**

В `tests/test_scheduler.py` в `test_register_jobs_creates_one_per_enabled_schedule` заменить строку `mock_scheduler.remove_all_jobs.assert_called_once()` на `mock_scheduler.remove_all_jobs.assert_not_called()`. Добавить в конец файла:

```python
def test_register_jobs_keeps_service_jobs():
    """Смена расписаний синка не снимает служебные задания (сводки, продление токенов)."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    svc = SchedulerService(scheduler=scheduler, trigger_runner=MagicMock())
    scheduler.add_job(MagicMock(), trigger="interval", hours=1, id="renew_tokens")

    first = MagicMock(id="s1", enabled=True, cron_expr="0 6 * * *", mode="normal", team=None)
    svc.register_jobs([first])
    second = MagicMock(id="s2", enabled=True, cron_expr="0 7 * * *", mode="normal", team=None)
    svc.register_jobs([second])

    ids = {job.id for job in scheduler.get_jobs()}
    assert ids == {"renew_tokens", "s2"}
```

- [ ] **Step 2: Убедиться, что падает**

Run: `py -3.10 -m pytest tests/test_scheduler.py -v`
Expected: FAIL оба изменённых теста (`remove_all_jobs` вызывается; `renew_tokens` пропал).

- [ ] **Step 3: Реализация**

В `SchedulerService.__init__` после `self._trigger_runner = trigger_runner` добавить:

```python
        #: id заданий расписаний синка — только их снимает register_jobs
        self._schedule_job_ids: set[str] = set()
```

`register_jobs` заменить на:

```python
    def register_jobs(self, schedules: list) -> None:
        """Перерегистрировать задания расписаний синка: по одному на включённое расписание.

        Служебные задания (сводки, агрегация, продление токенов) не трогаются —
        раньше ``remove_all_jobs`` снимал и их до перезапуска сервиса.
        """
        for job_id in self._schedule_job_ids:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
        self._schedule_job_ids = set()
        if self._trigger_runner is None:
            return

        for sched in schedules:
            if not sched.enabled:
                continue
            try:
                cron_fields = _parse_cron(sched.cron_expr)
                self.scheduler.add_job(
                    self._trigger_runner,
                    trigger="cron",
                    id=sched.id,
                    kwargs={
                        "schedule_id": sched.id,
                        "mode": sched.mode,
                        "team": sched.team,
                    },
                    replace_existing=True,
                    **cron_fields,
                )
                self._schedule_job_ids.add(sched.id)
            except Exception:
                logger.exception("scheduler: failed to register job for schedule %s", sched.id)
```

- [ ] **Step 4: Тесты проходят**

Run: `py -3.10 -m pytest tests/test_scheduler.py tests/test_scheduler_trigger.py tests/test_lifespan.py tests/test_sync_schedule_api.py -v`
Expected: PASS. Если какой-то тест проверял `remove_all_jobs` — поправить под новое поведение.

- [ ] **Step 5: Commit** — `fix(scheduler): смена расписания синка больше не снимает служебные задания`

---

### Task 2: Флаг `TOKEN_AUTO_RENEW`

**Files:**
- Modify: `app/config.py` (рядом с блоком `perf_*`)
- Modify: `Dockerfile` (блок `ENV` у строк ~80-82)
- Modify: `.env.example`, `deploy/staging/.env.example`, `deploy/prod/.env.example`, `deploy/SYSADMIN.md`
- Test: `tests/test_config.py`

- [ ] **Step 1: Тест** — в `tests/test_config.py` (посмотреть, как там создаётся `Settings`, и повторить приём):

```python
def test_token_auto_renew_off_by_default(monkeypatch):
    monkeypatch.delenv("TOKEN_AUTO_RENEW", raising=False)
    assert Settings(_env_file=None).token_auto_renew is False


def test_token_auto_renew_from_env(monkeypatch):
    monkeypatch.setenv("TOKEN_AUTO_RENEW", "true")
    assert Settings(_env_file=None).token_auto_renew is True
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_config.py -v` → FAIL (нет поля).

- [ ] **Step 3: Реализация** — в `Settings` после `perf_retention_days`:

```python
    # Самопродление персональных токенов Jira/Confluence (СБ: срок 14 дней).
    # Включено только в серверном образе (Dockerfile): копия базы на другой
    # машине иначе выпустила бы свой токен и отозвала токен рабочего сервера.
    token_auto_renew: bool = False
```

`Dockerfile` — к строкам `ENV TZ=...`/`ENV PYTHONUNBUFFERED=1` добавить:

```dockerfile
# Самопродление токенов Jira/Confluence — только на сервере (см. app/config.py)
ENV TOKEN_AUTO_RENEW=true
```

`deploy/staging/.env.example` — добавить:

```
# Staging поднимается из копии прод-базы: не продлевать токены, иначе отзовёт токен прода
TOKEN_AUTO_RENEW=false
```

`.env.example` (корень) — добавить закомментированно:

```
# Самопродление токенов Jira/Confluence. Локально не включать: копия прод-базы отзовёт токен прода
# TOKEN_AUTO_RENEW=false
```

`deploy/prod/.env.example` — комментарий `# TOKEN_AUTO_RENEW включён в образе; false — выключить самопродление токенов`.

`deploy/SYSADMIN.md` — в раздел «10. Частые проблемы» (или рядом с описанием `.env`) абзац: токены Jira и Confluence сервис продлевает сам (за 7 дней до конца выпускает новый на 14 дней, прежний свой отзывает через сутки); выключить — `TOKEN_AUTO_RENEW=false` в `.env`; на staging всегда `false`.

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_config.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(config): флаг самопродления токенов, включён в серверном образе`

---

### Task 3: Модуль продления `app/services/token_renewal.py`

**Files:**
- Create: `app/services/token_renewal.py`
- Test: `tests/services/test_token_renewal.py`

- [ ] **Step 1: Тесты** — `tests/services/test_token_renewal.py`:

```python
"""Самопродление персональных токенов Jira и Confluence."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import respx

from app.models.app_setting import AppSetting
from app.services import token_renewal
from app.services.token_renewal import load_state, renew_system, state_key

JIRA = "https://jira.example.test"
WIKI = "https://wiki.example.test"
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
PAT = f"{JIRA}/rest/pat/latest/tokens"


def _put(db, key, value):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _get(db, key):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _jira(db, token="old", state=None):
    _put(db, "jira_base_url", JIRA)
    _put(db, "jira_api_token", token)
    _put(db, state_key("jira"), json.dumps(state) if state is not None else None)


def _issued(token_id=7, raw="new", expiring="2026-11-02T15:00:00.000+0300"):
    return httpx.Response(201, json={"id": token_id, "name": "x", "rawToken": raw, "expiringAt": expiring})


@respx.mock
async def test_manual_token_is_renewed_at_once(db_session):
    _jira(db_session)
    create = respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(200, json={"name": "svc"}))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "new"
    request = create.calls.last.request
    assert request.headers["Authorization"] == "Bearer old"
    assert json.loads(request.content) == {"name": token_renewal.TOKEN_NAME, "expirationDuration": 14}
    state = load_state(db_session, "jira")
    assert state["id"] == 7
    assert state["expires_at"] == "2026-11-02T12:00:00+00:00"
    assert "prev_id" not in state  # ручной токен сервис не отзывает


@respx.mock
async def test_far_from_expiry_nothing_happens(db_session):
    # Маршрутов нет: любой запрос уронит тест (respx не пропускает незамоканное).
    _jira(db_session, state={"id": 7, "expires_at": (NOW + timedelta(days=10)).isoformat()})

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "old"


@respx.mock
async def test_own_token_renewed_week_before_expiry_and_queued_for_revoke(db_session):
    _jira(db_session, state={"id": 5, "expires_at": (NOW + timedelta(days=6)).isoformat()})
    respx.post(PAT).mock(return_value=_issued(token_id=8))
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(200, json={}))
    # Маршрута отзыва нет: отзыв сейчас уронил бы тест — он через сутки.

    await renew_system(db_session, "jira", NOW)

    state = load_state(db_session, "jira")
    assert state["id"] == 8
    assert state["prev_id"] == 5
    assert state["replaced_at"] == NOW.isoformat()


@respx.mock
async def test_previous_token_revoked_after_a_day(db_session):
    _jira(db_session, token="current", state={
        "id": 8, "expires_at": (NOW + timedelta(days=13)).isoformat(),
        "prev_id": 5, "replaced_at": (NOW - timedelta(hours=25)).isoformat(),
    })
    revoke = respx.delete(f"{PAT}/5").mock(return_value=httpx.Response(204))

    await renew_system(db_session, "jira", NOW)

    assert revoke.calls.last.request.headers["Authorization"] == "Bearer current"
    state = load_state(db_session, "jira")
    assert "prev_id" not in state and "replaced_at" not in state


@respx.mock
async def test_previous_token_kept_within_a_day(db_session):
    _jira(db_session, state={
        "id": 8, "expires_at": (NOW + timedelta(days=13)).isoformat(),
        "prev_id": 5, "replaced_at": (NOW - timedelta(hours=2)).isoformat(),
    })
    # Маршрута отзыва нет: преждевременный отзыв уронил бы тест.

    await renew_system(db_session, "jira", NOW)

    assert load_state(db_session, "jira")["prev_id"] == 5


@respx.mock
async def test_failed_revoke_is_retried_later_without_error(db_session):
    _jira(db_session, state={
        "id": 8, "expires_at": (NOW + timedelta(days=13)).isoformat(),
        "prev_id": 5, "replaced_at": (NOW - timedelta(days=2)).isoformat(),
    })
    respx.delete(f"{PAT}/5").mock(return_value=httpx.Response(500))

    await renew_system(db_session, "jira", NOW)

    state = load_state(db_session, "jira")
    assert state["prev_id"] == 5
    assert "error" not in state


@respx.mock
async def test_refused_issue_keeps_old_token_and_records_error(db_session):
    _jira(db_session)
    respx.post(PAT).mock(return_value=httpx.Response(403, text="Forbidden"))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "old"
    state = load_state(db_session, "jira")
    assert "выпуск нового ключа" in state["error"] and "403" in state["error"]
    assert state["error_at"] == NOW.isoformat()


@respx.mock
async def test_new_token_failing_check_is_not_saved(db_session):
    _jira(db_session)
    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(401))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "old"
    assert "проверка нового ключа" in load_state(db_session, "jira")["error"]


@respx.mock
async def test_network_failure_recorded(db_session):
    _jira(db_session)
    respx.post(PAT).mock(side_effect=httpx.ConnectError("boom"))

    await renew_system(db_session, "jira", NOW)

    assert "нет связи" in load_state(db_session, "jira")["error"]


@respx.mock
async def test_success_clears_previous_error(db_session):
    _jira(db_session, state={"error": "старое", "error_at": NOW.isoformat()})
    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(200, json={}))

    await renew_system(db_session, "jira", NOW)

    state = load_state(db_session, "jira")
    assert "error" not in state and "error_at" not in state


@respx.mock
async def test_confluence_uses_its_own_address_and_check(db_session):
    _put(db_session, "confluence_base_url", WIKI)
    _put(db_session, "confluence_api_token", "wiki-old")
    _put(db_session, state_key("confluence"), None)
    respx.post(f"{WIKI}/rest/pat/latest/tokens").mock(return_value=_issued(raw="wiki-new"))
    check = respx.get(f"{WIKI}/rest/api/user/current").mock(return_value=httpx.Response(200, json={}))

    await renew_system(db_session, "confluence", NOW)

    assert check.calls.last.request.headers["Authorization"] == "Bearer wiki-new"
    assert _get(db_session, "confluence_api_token") == "wiki-new"


async def test_system_without_token_is_skipped(db_session):
    _put(db_session, "confluence_base_url", WIKI)
    _put(db_session, "confluence_api_token", None)

    await renew_system(db_session, "confluence", NOW)  # без сети: respx не подключён

    assert load_state(db_session, "confluence") == {}


async def test_job_does_nothing_when_disabled(monkeypatch):
    called = []

    async def fake_renew(db, system, now=None):
        called.append(system)

    monkeypatch.setattr(token_renewal, "get_settings", lambda: SimpleNamespace(token_auto_renew=False))
    monkeypatch.setattr(token_renewal, "renew_system", fake_renew)

    await token_renewal.renew_tokens_job()

    assert called == []


def test_status_for_settings_and_banner(db_session, monkeypatch):
    monkeypatch.setattr(token_renewal, "get_settings", lambda: SimpleNamespace(token_auto_renew=True))
    _jira(db_session, state={"id": 7, "expires_at": "2026-11-02T12:00:00+00:00", "error": "сбой"})
    _put(db_session, "confluence_api_token", None)

    status = token_renewal.renewal_status(db_session)

    assert status["enabled"] is True
    assert status["jira"] == {
        "expires_at": "2026-11-02T12:00:00+00:00", "renewed_at": None, "error": "сбой", "error_at": None,
    }
    assert status["confluence"] is None
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/services/test_token_renewal.py -v` → FAIL (модуля нет).

- [ ] **Step 3: Реализация** — `app/services/token_renewal.py`:

```python
"""Самопродление персональных токенов Jira и Confluence.

СБ ограничила срок персонального токена 14 днями. Раз в час сервис смотрит,
сколько осталось жить токену, и за неделю до конца (или сразу, если срок
неизвестен — токен вставлен вручную) выпускает текущим токеном новый,
проверяет его и переключается. Свой прежний токен отзывает через сутки —
синхронизация, начатая на нём, успевает закончиться. Токен, вставленный
вручную, не отзывается: Jira не говорит, какой это из токенов пользователя, —
он истечёт сам.

Работает только при ``TOKEN_AUTO_RENEW=true`` (включено в серверном образе):
копия базы на другом компьютере иначе выпустила бы свой токен и отозвала
токен рабочего сервера.

Состояние — JSON в AppSetting ``<система>_token_renewal``:
``id``, ``expires_at``, ``renewed_at``, ``prev_id``, ``replaced_at``, ``error``, ``error_at``.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

TOKEN_DAYS = 14
RENEW_WHEN_LEFT = timedelta(days=7)
REVOKE_PREVIOUS_AFTER = timedelta(days=1)
TOKEN_NAME = "Jira Analytics — автопродление"
PAT_PATH = "/rest/pat/latest/tokens"
TIMEOUT = httpx.Timeout(30.0, connect=15.0)

#: система → (ключ адреса, ключ токена, запрос проверки токена)
SYSTEMS = {
    "jira": ("jira_base_url", "jira_api_token", "/rest/api/2/myself"),
    "confluence": ("confluence_base_url", "confluence_api_token", "/rest/api/user/current"),
}

_DATETIME: TypeAdapter[datetime] = TypeAdapter(datetime)


class RenewalError(Exception):
    """Продлить не удалось; текст показывается администратору."""


def state_key(system: str) -> str:
    return f"{system}_token_renewal"


def _get(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set(db: Session, key: str, value: Optional[str]) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def load_state(db: Session, system: str) -> dict[str, Any]:
    """Состояние продления системы; нет записи или мусор — пустое."""
    raw = _get(db, state_key(system))
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_dt(value: Any) -> Optional[datetime]:
    """Дата из ответа Jira (``+0300`` и ``+03:00``) или из состояния, в UTC; мусор — None."""
    if not value:
        return None
    try:
        dt = _DATETIME.validate_python(value)
    except ValidationError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Atlassian-Token": "no-check",
    }


def _failure(what: str, resp: httpx.Response) -> RenewalError:
    """Ошибка шага с кодом ответа и коротким текстом (страница вместо данных — без текста)."""
    detail = resp.text.strip()[:200]
    if detail.startswith("<"):
        detail = ""
    return RenewalError(f"{what}: ответ {resp.status_code}" + (f" — {detail}" if detail else ""))


async def _revoke_previous(
    client: httpx.AsyncClient, token: str, state: dict[str, Any], now: datetime,
) -> None:
    """Отозвать свой прежний токен через сутки после замены; сбой — повтор на следующей проверке."""
    prev_id = state.get("prev_id")
    replaced_at = _parse_dt(state.get("replaced_at"))
    if not prev_id or (replaced_at and now - replaced_at < REVOKE_PREVIOUS_AFTER):
        return
    resp = await client.delete(f"{PAT_PATH}/{prev_id}", headers=_headers(token))
    if resp.is_success or resp.status_code == 404:
        state.pop("prev_id", None)
        state.pop("replaced_at", None)
    else:
        logger.warning("token renewal: прежний токен %s не отозван, ответ %s", prev_id, resp.status_code)


async def _issue(
    client: httpx.AsyncClient, token: str, check_path: str, state: dict[str, Any], now: datetime,
) -> str:
    """Выпустить текущим токеном новый, проверить его, записать в состояние; вернуть новый."""
    resp = await client.post(
        PAT_PATH, headers=_headers(token),
        json={"name": TOKEN_NAME, "expirationDuration": TOKEN_DAYS},
    )
    if not resp.is_success:
        raise _failure("выпуск нового ключа", resp)
    data = resp.json()
    new_token = data.get("rawToken") if isinstance(data, dict) else None
    if not new_token:
        raise RenewalError("выпуск нового ключа: в ответе нет ключа")
    check = await client.get(check_path, headers=_headers(new_token))
    if check.status_code != 200:
        raise _failure("проверка нового ключа", check)
    if state.get("id"):
        state["prev_id"] = state["id"]
        state["replaced_at"] = now.isoformat()
    expires = _parse_dt(data.get("expiringAt")) or now + timedelta(days=TOKEN_DAYS)
    state.update(id=data.get("id"), expires_at=expires.isoformat(), renewed_at=now.isoformat())
    return new_token


async def renew_system(db: Session, system: str, now: Optional[datetime] = None) -> None:
    """Проверить токен системы и продлить, если срок неизвестен или до конца ≤ 7 дней."""
    now = now or datetime.now(timezone.utc)
    url_key, token_key, check_path = SYSTEMS[system]
    base_url, token = _get(db, url_key), _get(db, token_key)
    if not (base_url and token):
        return
    state = load_state(db, system)
    error: Optional[str]
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=TIMEOUT, follow_redirects=False,
        ) as client:
            await _revoke_previous(client, token, state, now)
            expires = _parse_dt(state.get("expires_at"))
            if expires is None or expires - now <= RENEW_WHEN_LEFT:
                _set(db, token_key, await _issue(client, token, check_path, state, now))
    except RenewalError as exc:
        error = str(exc)
    except httpx.HTTPError as exc:
        error = f"нет связи с сервером ({type(exc).__name__})"
    except ValueError:
        error = "сервер ответил не данными — проверьте адрес"
    else:
        error = None
    if error:
        state.update(error=error, error_at=now.isoformat())
        logger.warning("token renewal %s: %s", system, error)
    else:
        state.pop("error", None)
        state.pop("error_at", None)
    _set(db, state_key(system), json.dumps(state, ensure_ascii=False))
    db.commit()


async def renew_tokens_job() -> None:
    """Задание планировщика: продлить токены Jira и Confluence, если включено на этом сервере."""
    if not get_settings().token_auto_renew:
        return
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for system in SYSTEMS:
            await renew_system(db, system)
    finally:
        db.close()


def renewal_status(db: Session) -> dict[str, Any]:
    """Состояние продления для настроек и плашки администратора; без токена — ``None``."""
    result: dict[str, Any] = {"enabled": get_settings().token_auto_renew}
    for system, (_, token_key, _) in SYSTEMS.items():
        if not _get(db, token_key):
            result[system] = None
            continue
        state = load_state(db, system)
        result[system] = {k: state.get(k) for k in ("expires_at", "renewed_at", "error", "error_at")}
    return result
```

- [ ] **Step 4:** `py -3.10 -m pytest tests/services/test_token_renewal.py -v` → PASS. Затем `ruff check app/services/token_renewal.py tests/services/test_token_renewal.py` и `mypy app/services/token_renewal.py` — чисто.
- [ ] **Step 5: Commit** — `feat(tokens): самопродление персональных токенов Jira и Confluence`

---

### Task 4: Задание планировщика раз в час

**Files:**
- Modify: `app/main.py` (lifespan, после `aggregate_usage`)
- Test: `tests/test_lifespan.py`

- [ ] **Step 1: Тест** — прочитать `tests/test_lifespan.py`, найти тест, который проверяет зарегистрированные задания после старта lifespan, и по его образцу добавить проверку: среди заданий есть `renew_tokens`, у него `max_instances == 1`, триггер — интервал 1 час. Если такого теста нет — добавить новый тем же приёмом патчей, что в файле.
- [ ] **Step 2:** `py -3.10 -m pytest tests/test_lifespan.py -v` → новый тест FAIL.
- [ ] **Step 3: Реализация** — в `app/main.py` после `add_job(aggregate_usage_job, ...)`:

```python
    # Самопродление токенов Jira/Confluence: раз в час, первый раз — через минуту после старта.
    sched_svc.scheduler.add_job(
        renew_tokens_job,
        trigger=IntervalTrigger(hours=1),
        id="renew_tokens",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(minutes=1),
    )
```

Импорты вверху (сверить, что `datetime`/`timedelta` ещё не импортированы иначе): `from datetime import datetime, timedelta`, `from apscheduler.triggers.interval import IntervalTrigger`, `from app.services.token_renewal import renew_tokens_job`.

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_lifespan.py tests/test_scheduler.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(tokens): проверка токенов раз в час`

---

### Task 5: Эндпоинт статуса и сброс при ручной замене токена

**Files:**
- Modify: `app/api/endpoints/settings.py`
- Test: `tests/test_settings_token_renewal.py` (новый)

- [ ] **Step 1: Тест** — `tests/test_settings_token_renewal.py`:

```python
"""Настройки: состояние самопродления токенов и сброс при ручной замене."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from app.services import token_renewal


def _put(db, key, value):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_status_endpoint(db_session, monkeypatch):
    monkeypatch.setattr(token_renewal, "get_settings", lambda: SimpleNamespace(token_auto_renew=True))
    _put(db_session, "jira_api_token", "tok")
    _put(db_session, "jira_token_renewal", json.dumps({"expires_at": "2026-11-02T12:00:00+00:00"}))
    _put(db_session, "confluence_api_token", None)
    try:
        got = _client(db_session).get("/api/v1/settings/token-renewal")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert got.status_code == 200
    body = got.json()
    assert body["enabled"] is True
    assert body["jira"]["expires_at"] == "2026-11-02T12:00:00+00:00"
    assert body["confluence"] is None


def test_manual_jira_token_resets_renewal_state(db_session):
    _put(db_session, "jira_token_renewal", json.dumps({"id": 5, "expires_at": "2026-11-02T12:00:00+00:00"}))
    try:
        put = _client(db_session).put("/api/v1/settings/jira", json={"api_token": "manual"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert token_renewal.load_state(db_session, "jira") == {}


def test_manual_confluence_token_resets_renewal_state(db_session):
    _put(db_session, "confluence_token_renewal", json.dumps({"id": 5}))
    try:
        put = _client(db_session).put("/api/v1/settings/confluence", json={"api_token": "manual"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert token_renewal.load_state(db_session, "confluence") == {}


def test_saving_only_address_keeps_renewal_state(db_session):
    _put(db_session, "jira_token_renewal", json.dumps({"id": 5}))
    try:
        _client(db_session).put("/api/v1/settings/jira", json={"base_url": "jira.example.test"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert token_renewal.load_state(db_session, "jira") == {"id": 5}
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_settings_token_renewal.py -v` → FAIL.
- [ ] **Step 3: Реализация** в `app/api/endpoints/settings.py`:

Импорт: `from app.services.token_renewal import renewal_status, state_key`.

В `save_jira_settings` ветка токена:

```python
    if body.api_token is not None:
        _set_setting(db, "jira_api_token", body.api_token.strip())
        # Срок вставленного вручную токена неизвестен — самопродление начнёт заново.
        _set_setting(db, state_key("jira"), None)
```

В `save_confluence_settings` аналогично с `"confluence"`.

Новый эндпоинт (после `test_jira_credentials`):

```python
@router.get("/token-renewal")
async def get_token_renewal(db: Session = Depends(get_db)):
    """Самопродление токенов Jira и Confluence: включено ли, до какого числа ключ, последняя ошибка."""
    return renewal_status(db)
```

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_settings_token_renewal.py tests/test_settings_jira_endpoint.py tests/test_settings_confluence_endpoint.py tests/test_settings_endpoints.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(tokens): состояние самопродления в настройках, сброс при ручной замене`

---

### Task 6: Интерфейс — строка в карточках подключения и плашка администратору

**Files:**
- Modify: `frontend/src/types/api.ts` (рядом с `ConfluenceSettingsResponse`)
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/hooks/useSettings.ts`
- Create: `frontend/src/components/settings/TokenRenewalNote.tsx`
- Create: `frontend/src/components/layout/TokenRenewalAlert.tsx`
- Modify: `frontend/src/components/ConnectionCard.tsx`, `frontend/src/components/ConfluenceConnectionCard.tsx`
- Modify: `frontend/src/aurora/shell/AuroraShell.tsx`

- [ ] **Step 1: Типы** — `frontend/src/types/api.ts`:

```ts
/** Самопродление ключа одной системы (Jira или Confluence). */
export interface TokenRenewalSystem {
  expires_at: string | null;
  renewed_at: string | null;
  error: string | null;
  error_at: string | null;
}

export interface TokenRenewalStatus {
  enabled: boolean;
  jira: TokenRenewalSystem | null;
  confluence: TokenRenewalSystem | null;
}
```

- [ ] **Step 2: API** — `frontend/src/api/settings.ts`: добавить `TokenRenewalStatus` в импорт типов и

```ts
export const getTokenRenewal = () =>
  api.get<TokenRenewalStatus>('/settings/token-renewal');
```

- [ ] **Step 3: Хук** — `frontend/src/hooks/useSettings.ts`: добавить `getTokenRenewal` в импорт и

```ts
/** Самопродление ключей Jira и Confluence — только администратору (раздел настроек под админом). */
export function useTokenRenewal(enabled = true) {
  return useQuery({
    queryKey: ['settings', 'token-renewal'],
    queryFn: getTokenRenewal,
    enabled,
    staleTime: 5 * 60_000,
    refetchInterval: 30 * 60_000,
  });
}
```

В `useSaveJiraSettings` и `useSaveConfluenceSettings` в `onSuccess` дополнительно инвалидировать `['settings', 'token-renewal']`:

```ts
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings', 'jira'] });
      qc.invalidateQueries({ queryKey: ['settings', 'token-renewal'] });
    },
```

(для Confluence — `['settings', 'confluence']` + то же.)

- [ ] **Step 4: Строка в карточке** — `frontend/src/components/settings/TokenRenewalNote.tsx`:

```tsx
import { Typography } from 'antd';
import dayjs from 'dayjs';
import { useTokenRenewal } from '../../hooks/useSettings';

const { Text } = Typography;

/** Под полями подключения: до какого числа действует ключ и продлевается ли он сам. */
export default function TokenRenewalNote({ system }: { system: 'jira' | 'confluence' }) {
  const { data } = useTokenRenewal();
  const state = data?.[system];
  if (!data || !state) return null;
  if (!data.enabled) return <Text type="secondary">Автопродление ключа на этом сервере выключено</Text>;
  const until = state.expires_at ? dayjs(state.expires_at).format('DD.MM.YYYY') : null;
  if (state.error) {
    return (
      <Text type="danger">
        Не удалось продлить ключ: {state.error}{until ? `. Действует до ${until}` : ''}
      </Text>
    );
  }
  if (!until) return <Text type="secondary">Ключ продлится автоматически в течение часа</Text>;
  return <Text type="secondary">Ключ продлевается автоматически, действует до {until}</Text>;
}
```

В `ConnectionCard.tsx` внутри внешнего `<Space orientation="vertical">` последним элементом (после `<Space>` с кнопками) — `<TokenRenewalNote system="jira" />` + импорт `import TokenRenewalNote from './settings/TokenRenewalNote';`. В `ConfluenceConnectionCard.tsx` — так же с `system="confluence"` (сверить структуру разметки карточки, поставить строку под кнопками).

- [ ] **Step 5: Плашка** — `frontend/src/components/layout/TokenRenewalAlert.tsx`:

```tsx
import { Alert } from 'antd';
import { Link } from 'react-router';
import dayjs from 'dayjs';
import { useAuth } from '../../hooks/useAuth';
import { useTokenRenewal } from '../../hooks/useSettings';

const SYSTEMS = [
  { key: 'jira', name: 'Jira', section: 'connection', stops: 'синхронизация остановится' },
  { key: 'confluence', name: 'Confluence', section: 'confluence', stops: 'страницы Confluence перестанут загружаться' },
] as const;

/** Плашка администратору на всех страницах: ключ Jira или Confluence не продлился сам. */
export default function TokenRenewalAlert() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data } = useTokenRenewal(isAdmin);
  if (!isAdmin || !data?.enabled) return null;
  return (
    <>
      {SYSTEMS.map(({ key, name, section, stops }) => {
        const state = data[key];
        if (!state?.error) return null;
        const until = state.expires_at
          ? ` Ключ действует до ${dayjs(state.expires_at).format('DD.MM.YYYY')}, потом ${stops}.`
          : '';
        return (
          <Alert
            key={key}
            type="error"
            showIcon
            title={`Не удалось продлить ключ ${name}`}
            description={
              <span>
                {state.error}.{until} <Link to={`/settings#${section}`}>Вставить новый ключ</Link>
              </span>
            }
          />
        );
      })}
    </>
  );
}
```

В `AuroraShell.tsx`: импорт `import TokenRenewalAlert from '../../components/layout/TokenRenewalAlert';` и между `<AuroraTopbar />` и `<div className="scroll-y" ...>` вставить `<TokenRenewalAlert />`.

- [ ] **Step 6: Проверка** — из `frontend/`: `npx eslint` по изменённым и новым файлам — без ошибок (общий `npm run lint` красный и до правки); `npm run build` — успешно.
- [ ] **Step 7: Commit** — `feat(tokens): срок ключа в настройках и плашка администратору при сбое продления`

---

### Task 7: Документация и заметка «Что нового»

**Files:**
- Modify: `app/models/CLAUDE.md` (список ключей AppSetting — добавить `jira_token_renewal`, `confluence_token_renewal`: JSON состояния самопродления)
- Modify: `app/services/CLAUDE.md` (короткий пункт про `token_renewal`: что делает, флаг, часовое задание)
- Modify: `app/connectors/CLAUDE.md` (в абзац про credentials: токены в AppSetting сервис меняет сам при `TOKEN_AUTO_RENEW`)
- Modify: `release_notes/drafts.json` — через `py -3.10 scripts/release_note.py add` (не перезаписывать файл руками)

- [ ] **Step 1:** правки трёх CLAUDE.md — по одной-две строки, в стиле файла.
- [ ] **Step 2:** заметка:

```bash
py -3.10 scripts/release_note.py add --type new --section settings \
  --title "Ключи Jira и Confluence продлеваются сами" \
  --description "Срок ключа теперь 14 дней. Сервис сам выпускает новый ключ за неделю до окончания старого, проверяет его и переключается — вставлять ключ вручную раз в две недели больше не нужно. Срок действия ключа виден в настройках подключения. Если продлить не удалось, администратор увидит красную плашку вверху страниц."
```

```bash
py -3.10 scripts/release_note.py add --type fix --section sync \
  --title "Смена расписания синхронизации не отключает ночные задачи" \
  --description "Раньше после правки расписания синхронизации до перезапуска сервиса переставали обновляться ночные сводки по проектам и статистика использования."
```

- [ ] **Step 3: Commit** — `docs(tokens): самопродление в доках и заметки «Что нового»`

---

### Task 8: Итоговая проверка

- [ ] `py -3.10 -m pytest tests/ -q --ignore=tests/api/test_llm.py -p no:cacheprovider` — зелёное. Если что-то падает — проверить, касается ли тест изменённых файлов; не касается — перечислить в отчёте как давнее.
- [ ] `ruff check app/ tests/` и `mypy app/` — без новых замечаний.
- [ ] `cd frontend && npm run build` — успешно.
