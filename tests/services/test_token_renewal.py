"""Самопродление персональных токенов Jira и Confluence."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def _issued(token_id=7, raw="new", expiring="2026-11-01T18:30:00.000+0300"):
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
    assert state["expires_at"] == "2026-11-01T15:30:00+00:00"
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
    respx.delete(f"{PAT}/7").mock(return_value=httpx.Response(204))
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(401))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "old"
    assert "проверка нового ключа" in load_state(db_session, "jira")["error"]


@respx.mock
async def test_new_token_failing_check_is_revoked(db_session):
    _jira(db_session)
    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(401))
    revoke = respx.delete(f"{PAT}/7").mock(return_value=httpx.Response(204))

    await renew_system(db_session, "jira", NOW)

    assert revoke.calls.last.request.headers["Authorization"] == "Bearer old"
    assert _get(db_session, "jira_api_token") == "old"
    assert "проверка нового ключа" in load_state(db_session, "jira")["error"]


@respx.mock
async def test_new_token_check_network_error_is_revoked(db_session):
    _jira(db_session)
    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(side_effect=httpx.ConnectError("boom"))
    revoke = respx.delete(f"{PAT}/7").mock(return_value=httpx.Response(204))

    await renew_system(db_session, "jira", NOW)

    assert revoke.called
    assert _get(db_session, "jira_api_token") == "old"
    assert "нет связи" in load_state(db_session, "jira")["error"]


@respx.mock
async def test_revoke_network_failure_does_not_block_renewal(db_session):
    _jira(db_session, state={
        "id": 5, "expires_at": (NOW + timedelta(days=1)).isoformat(),
        "prev_id": 4, "replaced_at": (NOW - timedelta(days=2)).isoformat(),
    })
    respx.delete(f"{PAT}/4").mock(side_effect=httpx.ConnectTimeout("slow"))
    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(return_value=httpx.Response(200, json={}))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "new"
    state = load_state(db_session, "jira")
    assert "error" not in state
    assert state["id"] == 7


@respx.mock
async def test_manual_token_pasted_during_renewal_wins(db_session):
    _jira(db_session)

    def check(request):
        # Администратор вставил свой ключ, пока продление ждало Jira.
        _put(db_session, "jira_api_token", "pasted")
        _put(db_session, state_key("jira"), None)
        return httpx.Response(200, json={})

    respx.post(PAT).mock(return_value=_issued())
    respx.get(f"{JIRA}/rest/api/2/myself").mock(side_effect=check)
    revoke = respx.delete(f"{PAT}/7").mock(return_value=httpx.Response(204))

    await renew_system(db_session, "jira", NOW)

    assert _get(db_session, "jira_api_token") == "pasted"
    assert load_state(db_session, "jira") == {}
    assert revoke.calls.last.request.headers["Authorization"] == "Bearer old"


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


async def test_job_continues_after_one_system_fails(monkeypatch):
    called = []

    async def fake_renew(db, system, now=None):
        if system == "jira":
            raise RuntimeError("boom")
        called.append(system)

    monkeypatch.setattr(token_renewal, "get_settings", lambda: SimpleNamespace(token_auto_renew=True))
    monkeypatch.setattr(token_renewal, "renew_system", fake_renew)
    monkeypatch.setattr("app.database.SessionLocal", lambda: MagicMock())

    await token_renewal.renew_tokens_job()

    assert called == ["confluence"]


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
