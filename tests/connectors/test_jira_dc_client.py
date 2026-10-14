"""Клиент Jira Data Center: вход по токену, REST API v2, поиск со смещением."""
import logging

import httpx
import pytest
import respx

from app.connectors import jira_client
from app.connectors.jira_client import (
    JiraAuthError,
    JiraClient,
    JiraClientError,
    JiraNetworkError,
    JiraServerError,
)
from app.models.app_setting import AppSetting
from tests.dc_fixtures import load_dc

BASE = "https://jira.example.test"
API = f"{BASE}/rest/api/2"


def _client() -> JiraClient:
    return JiraClient(base_url=BASE, api_token="secret-token", max_retries=1)


def _params(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


@respx.mock
async def test_bearer_token_and_api_v2():
    me = load_dc("user_search_single.json")[0]
    route = respx.get(f"{API}/myself").mock(return_value=httpx.Response(200, json=me))
    async with _client() as jira:
        user = await jira.get_myself()
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"
    assert user.jira_account_id == me["key"]
    assert user.name == me["name"]


def test_from_db_needs_only_url_and_token(db_session):
    db_session.add_all([
        AppSetting(key="jira_base_url", value=BASE),
        AppSetting(key="jira_api_token", value="secret-token"),
    ])
    db_session.commit()
    jira = JiraClient.from_db(db_session)
    assert jira.base_url == BASE
    assert jira.api_token == "secret-token"


def test_missing_token_is_an_error(monkeypatch):
    class _NoEnv:
        jira_base_url = None
        jira_api_token = None

    monkeypatch.setattr(jira_client, "get_settings", lambda: _NoEnv())
    with pytest.raises(JiraClientError):
        JiraClient(base_url=BASE, api_token=None)


@respx.mock
async def test_iter_issues_pages_by_start_at_with_stable_order():
    issues = [load_dc(f"issue_{k}.json") for k in ("OS-91030", "OS-91031", "RFA-4610")]
    pages = {0: issues[:2], 2: issues[2:]}
    seen: list[dict] = []

    def handler(request):
        params = _params(request)
        seen.append(params)
        start = int(params["startAt"])
        return httpx.Response(200, json={
            "startAt": start, "maxResults": 2, "total": 3, "issues": pages[start],
        })

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        keys = [i.key async for i in jira.iter_issues('project = "OS"', max_results=2, expand="changelog")]

    assert keys == ["OS-91030", "OS-91031", "RFA-4610"]
    assert [p["startAt"] for p in seen] == ["0", "2"]
    assert seen[0]["jql"] == 'project = "OS" ORDER BY key ASC'
    assert "validateQuery" not in seen[0]
    assert seen[0]["expand"] == "changelog"


@respx.mock
async def test_iter_issues_keeps_explicit_order():
    seen: list[str] = []

    def handler(request):
        seen.append(_params(request)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 0, "issues": []})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        assert [i async for i in jira.iter_issues("project = OS ORDER BY created DESC")] == []
    assert seen == ["project = OS ORDER BY created DESC"]


@respx.mock
async def test_iter_issue_keys_reads_only_keys():
    seen: list[dict] = []

    def handler(request):
        params = _params(request)
        seen.append(params)
        start = int(params["startAt"])
        batch = (
            [{"id": "258783", "key": "OS-91030"}, {"id": "258784", "key": "OS-91031"}]
            if start == 0 else [{"id": 94555, "key": "RFA-4610"}]
        )
        return httpx.Response(200, json={"startAt": start, "maxResults": 1000, "total": 3, "issues": batch})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        pairs = [p async for p in jira.iter_issue_keys('project = "OS"')]

    assert pairs == [("OS-91030", "258783"), ("OS-91031", "258784"), ("RFA-4610", "94555")]
    assert seen[0]["fields"] == "key"
    assert seen[0]["maxResults"] == "1000"
    assert seen[0]["jql"] == 'project = "OS" ORDER BY key ASC'
    assert [p["startAt"] for p in seen] == ["0", "2"]


@respx.mock
async def test_get_projects_reads_bare_list():
    respx.get(f"{API}/project").mock(return_value=httpx.Response(200, json=[
        {"id": "10901", "key": "OS", "name": "1С", "projectTypeKey": "software"},
        {"id": "10500", "key": "RFA", "name": "Инициативы", "projectTypeKey": "business"},
    ]))
    async with _client() as jira:
        projects = await jira.get_projects()
        iterated = [p.key async for p in jira.iter_projects()]
    assert [(p.id, p.key) for p in projects] == [("10901", "OS"), ("10500", "RFA")]
    assert iterated == ["OS", "RFA"]


@respx.mock
async def test_search_users_uses_username_param():
    users_raw = load_dc("user_search.json")
    route = respx.get(f"{API}/user/search").mock(return_value=httpx.Response(200, json=users_raw))
    async with _client() as jira:
        users = await jira.search_users("Иванов", max_results=20)
    assert _params(route.calls.last.request) == {"username": "Иванов", "maxResults": "20"}
    assert [u.jira_account_id for u in users] == [u["key"] for u in users_raw]
    assert [u.name for u in users] == [u["name"] for u in users_raw]


@respx.mock
async def test_search_users_can_include_inactive():
    route = respx.get(f"{API}/user/search").mock(return_value=httpx.Response(200, json=[]))
    async with _client() as jira:
        await jira.search_users("Иванов", max_results=1000, include_inactive=True)
    assert _params(route.calls.last.request) == {
        "username": "Иванов", "maxResults": "1000", "includeInactive": "true",
    }


def _issue(n: int) -> dict:
    return {
        "id": str(1000 + n),
        "key": f"OS-{n}",
        "fields": {
            "summary": f"Задача {n}",
            "issuetype": {"id": "1", "name": "Task"},
            "status": {"id": "1", "name": "Open"},
            "project": {"id": "10901", "key": "OS", "name": "1С"},
        },
    }


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Паузы клиента записываются, но не ждутся."""
    calls: list[float] = []

    async def _fake_sleep(delay):
        calls.append(delay)

    monkeypatch.setattr(jira_client.asyncio, "sleep", _fake_sleep)
    return calls


@respx.mock
async def test_iter_issues_follows_server_capped_page_size():
    all_issues = [_issue(n) for n in range(5)]
    starts: list[int] = []

    def handler(request):
        start = int(_params(request)["startAt"])
        starts.append(start)
        # Просили 100, сервер отдаёт по 2.
        return httpx.Response(200, json={
            "startAt": start, "maxResults": 2, "total": 5, "issues": all_issues[start:start + 2],
        })

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        keys = [i.key async for i in jira.iter_issues("project = OS", max_results=100)]
    assert keys == [f"OS-{n}" for n in range(5)]
    assert starts == [0, 2, 4]


@respx.mock
async def test_iter_issues_stops_on_empty_page_before_total():
    def handler(request):
        start = int(_params(request)["startAt"])
        page = [_issue(0), _issue(1)] if start == 0 else []
        return httpx.Response(200, json={"startAt": start, "maxResults": 100, "total": 10, "issues": page})

    route = respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        keys = [i.key async for i in jira.iter_issues("project = OS")]
    assert keys == ["OS-0", "OS-1"]
    assert route.call_count == 2


@respx.mock
async def test_iter_issues_keeps_lowercase_order_by():
    seen: list[str] = []

    def handler(request):
        seen.append(_params(request)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 0, "issues": []})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        assert [i async for i in jira.iter_issues("project = OS order by created desc")] == []
    assert seen == ["project = OS order by created desc"]


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_are_not_retried(status, sleeps):
    with respx.mock:
        route = respx.get(f"{API}/myself").mock(return_value=httpx.Response(status))
        async with JiraClient(base_url=BASE, api_token="t", max_retries=3) as jira:
            with pytest.raises(JiraAuthError):
                await jira.get_myself()
    assert route.call_count == 1


@respx.mock
async def test_rate_limit_then_success(sleeps):
    me = load_dc("user_search_single.json")[0]
    route = respx.get(f"{API}/myself").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json=me),
    ])
    async with JiraClient(base_url=BASE, api_token="t", max_retries=3) as jira:
        user = await jira.get_myself()
    assert user.jira_account_id == me["key"]
    assert route.call_count == 2
    assert 7 in sleeps


@respx.mock
async def test_rate_limit_with_date_retry_after_uses_default_pause(sleeps):
    me = load_dc("user_search_single.json")[0]
    respx.get(f"{API}/myself").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        httpx.Response(200, json=me),
    ])
    async with JiraClient(base_url=BASE, api_token="t", max_retries=3) as jira:
        await jira.get_myself()
    assert jira_client.DEFAULT_RETRY_AFTER in sleeps


@respx.mock
async def test_network_failure_after_retries_is_network_error(sleeps):
    """Сеть не ответила и после повторов — отдельная ошибка: вызывающий отличит её от 404."""
    route = respx.get(f"{API}/myself").mock(side_effect=httpx.ConnectError("нет связи"))
    async with JiraClient(base_url=BASE, api_token="t", max_retries=2) as jira:
        with pytest.raises(JiraNetworkError, match="Request failed"):
            await jira.get_myself()
    assert route.call_count == 2


@respx.mock
async def test_server_error_is_retried(sleeps):
    me = load_dc("user_search_single.json")[0]
    route = respx.get(f"{API}/myself").mock(side_effect=[
        httpx.Response(502),
        httpx.Response(200, json=me),
    ])
    async with JiraClient(base_url=BASE, api_token="t", max_retries=3) as jira:
        await jira.get_myself()
    assert route.call_count == 2


@respx.mock
async def test_server_error_after_retries_is_server_error(sleeps):
    """Сервер Jira сбоит и после повторов — отдельная ошибка: вызывающий отличит её от 404."""
    route = respx.get(f"{API}/myself").mock(return_value=httpx.Response(503))
    async with JiraClient(base_url=BASE, api_token="t", max_retries=2) as jira:
        with pytest.raises(JiraServerError):
            await jira.get_myself()
    assert route.call_count == 2
    assert issubclass(JiraServerError, JiraClientError)

@respx.mock
async def test_bad_request_carries_jira_error_messages_without_retry(sleeps):
    route = respx.get(f"{API}/search").mock(return_value=httpx.Response(400, json={
        "errorMessages": ["Поле «Команда» не существует или у вас нет прав на его просмотр."],
        "errors": {},
    }))
    async with JiraClient(base_url=BASE, api_token="t", max_retries=3) as jira:
        with pytest.raises(JiraClientError, match="Поле «Команда» не существует"):
            await jira.search_issues('"Команда" = "Альфа"')
    assert route.call_count == 1


@respx.mock
async def test_lenient_flag_controls_validate_query_and_warnings_are_logged(caplog):
    seen: list[dict] = []

    def handler(request):
        seen.append(_params(request))
        return httpx.Response(200, json={
            "startAt": 0, "maxResults": 100, "total": 0, "issues": [],
            "warningMessages": ["Задачи с ключом «OS-404» не существует."],
        })

    respx.get(f"{API}/search").mock(side_effect=handler)
    with caplog.at_level(logging.WARNING, logger="app.connectors.jira_client"):
        async with _client() as jira:
            await jira.search_issues('key in ("OS-404")')
            assert [i async for i in jira.iter_issues('key in ("OS-404")', lenient=True)] == []
    assert "validateQuery" not in seen[0]
    assert seen[1]["validateQuery"] == "warn"
    assert "OS-404" in caplog.text
