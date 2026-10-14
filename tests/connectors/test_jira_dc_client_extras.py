"""Клиент DC: ворклоги потоком, справочник статусов, история задачи, опции полей."""
from datetime import datetime, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.connectors import jira_client
from app.connectors.jira_client import JiraClient, JiraClientError, jql_field_ref
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from tests.dc_fixtures import load_dc

BASE = "https://jira.example.test"
API = f"{BASE}/rest/api/2"


def _client() -> JiraClient:
    return JiraClient(base_url=BASE, api_token="secret-token", max_retries=1)


async def test_worklogs_stream_in_batches(monkeypatch):
    """Пачка уходит в POST /worklog/list, как только набралась."""
    monkeypatch.setattr(jira_client, "WORKLOG_LIST_BATCH", 10)
    updated = load_dc("worklog_updated.json")
    ids = [v["worklogId"] for v in updated["values"]]
    listed = load_dc("worklog_list.json")
    get_params: list[dict] = []
    post_batches: list[list[int]] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            assert path == "/worklog/updated"
            get_params.append(dict(params))
            return updated
        assert path == "/worklog/list"
        post_batches.append(list(json["ids"]))
        return listed

    client = JiraClient.__new__(JiraClient)
    client._request = fake_request  # type: ignore[method-assign]

    got = [wl async for wl in client.iter_worklogs_updated_since(0)]

    assert get_params == [{"since": 0}]
    assert [len(b) for b in post_batches[:-1]] == [10] * (len(post_batches) - 1)
    assert sum(post_batches, []) == ids
    assert len(got) == len(listed) * len(post_batches)
    assert got[0].author.jira_account_id == listed[0]["author"]["key"]


async def test_worklog_batch_posted_before_next_page(monkeypatch):
    """Набравшаяся пачка уходит в POST до запроса следующей страницы id."""
    monkeypatch.setattr(jira_client, "WORKLOG_LIST_BATCH", 2)
    pages = {
        500: {"values": [{"worklogId": i} for i in (1, 2, 3)], "until": 900, "lastPage": False},
        900: {"values": [{"worklogId": 4}], "until": 950, "lastPage": True},
    }
    calls: list[tuple] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            calls.append(("GET", params["since"]))
            return pages[params["since"]]
        calls.append(("POST", list(json["ids"])))
        return []

    client = JiraClient.__new__(JiraClient)
    client._request = fake_request  # type: ignore[method-assign]
    assert [wl async for wl in client.iter_worklogs_updated_since(500)] == []
    assert calls == [("GET", 500), ("POST", [1, 2]), ("GET", 900), ("POST", [3, 4])]


def _stalled_client(path_seen: list[str], until):
    async def fake_request(method, path, params=None, json=None):
        path_seen.append(path)
        if method == "GET":
            page = {"values": [{"worklogId": 7}], "lastPage": False}
            if until is not None:
                page["until"] = until
            return page
        return []

    client = JiraClient.__new__(JiraClient)
    client._request = fake_request  # type: ignore[method-assign]
    return client


@pytest.mark.parametrize("until", [500, 400, None])
async def test_worklogs_stalled_page_raises(until):
    """``until`` не сдвинулся / ушёл назад / отсутствует на непоследней странице — ошибка."""
    paths: list[str] = []
    client = _stalled_client(paths, until)
    with pytest.raises(JiraClientError, match="неполный"):
        [wl async for wl in client.iter_worklogs_updated_since(500)]
    assert paths == ["/worklog/updated"]


@pytest.mark.parametrize("until", [500, None])
async def test_deleted_ids_stalled_page_yields_ids_then_raises(until):
    paths: list[str] = []
    client = _stalled_client(paths, until)
    got: list[int] = []
    since = datetime.fromtimestamp(0.5, tz=timezone.utc)
    with pytest.raises(JiraClientError, match="неполный"):
        async for worklog_id in client.iter_deleted_worklog_ids(since):
            got.append(worklog_id)
    assert got == [7]
    assert paths == ["/worklog/deleted"]


@respx.mock
async def test_get_statuses_and_issue_changelog():
    statuses = [{"id": "3", "name": "В работе", "statusCategory": {"key": "indeterminate"}}]
    respx.get(f"{API}/status").mock(return_value=httpx.Response(200, json=statuses))
    changelog = {"startAt": 0, "maxResults": 1, "total": 1, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000",
         "items": [{"field": "status", "from": "1", "to": "3", "toString": "В работе"}]},
    ]}
    route = respx.get(f"{API}/issue/OS-91030").mock(
        return_value=httpx.Response(200, json={"key": "OS-91030", "changelog": changelog})
    )
    async with _client() as jira:
        assert await jira.get_statuses() == statuses
        assert await jira.get_issue_changelog("OS-91030") == changelog
        assert await jira.get_status_changes("OS-91030") == [
            ("2026-09-12T08:00:00.000+0000", "В работе"),
        ]
    assert dict(route.calls.last.request.url.params) == {"fields": "status", "expand": "changelog"}


@respx.mock
async def test_custom_field_options_from_dc_endpoint():
    route = respx.get(f"{API}/customFields/11092/options").mock(return_value=httpx.Response(200, json={
        "startAt": 0, "maxResults": 100, "total": 3, "isLast": True,
        "values": [
            {"id": "1", "value": "Команда Б", "disabled": False},
            {"id": "2", "value": "Команда А", "disabled": False},
            {"id": "3", "value": "Старая команда", "disabled": True},
        ],
    }))
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11092") == ["Команда А", "Команда Б"]
    assert dict(route.calls.last.request.url.params) == {
        "page": "1", "maxResults": "100", "useAllContexts": "true",
    }


@respx.mock
async def test_custom_field_options_page_numbers_and_server_ignoring_paging():
    """Страницы идут ``page=1,2,…``; сервер, отдающий одно и то же с isLast=false, не зацикливает."""
    pages: list[str] = []

    def handler(request):
        pages.append(request.url.params["page"])
        return httpx.Response(200, json={
            "isLast": False,
            "values": [{"id": "1", "value": "Команда А", "disabled": False}],
        })

    respx.get(f"{API}/customFields/11092/options").mock(side_effect=handler)
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11092") == ["Команда А"]
    assert pages == ["1", "2"]


@respx.mock
async def test_custom_field_options_page_cap_gives_empty_list(monkeypatch, caplog):
    """Опции не кончились за предел страниц — пусто (перебор задач) и запись в журнал."""
    monkeypatch.setattr(jira_client, "OPTIONS_MAX_PAGES", 3)

    def handler(request):
        n = request.url.params["page"]
        return httpx.Response(200, json={
            "isLast": False, "values": [{"id": n, "value": f"Команда {n}"}],
        })

    route = respx.get(f"{API}/customFields/11092/options").mock(side_effect=handler)
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11092") == []
    assert route.call_count == 3
    assert "customfield_11092" in caplog.text


@respx.mock
async def test_custom_field_options_error_gives_empty_list():
    respx.get(f"{API}/customFields/11526/options").mock(
        return_value=httpx.Response(404, json=load_dc("custom_field_options_error.json"))
    )
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11526") == []
        assert await jira.get_field_configured_options("summary") == []


@respx.mock
async def test_custom_field_options_error_on_next_page_gives_empty_list():
    """Обрыв на второй странице — пусто, а не неполный список под видом полного."""
    respx.get(f"{API}/customFields/11092/options").mock(side_effect=[
        httpx.Response(200, json={
            "startAt": 0, "maxResults": 1, "total": 2, "isLast": False,
            "values": [{"id": "1", "value": "Команда А", "disabled": False}],
        }),
        httpx.Response(404, json=load_dc("custom_field_options_error.json")),
    ])
    async with _client() as jira:
        assert await jira.get_field_configured_options("customfield_11092") == []


@respx.mock
async def test_distinct_values_fallback_uses_cf_reference():
    respx.get(f"{API}/customFields/11092/options").mock(
        return_value=httpx.Response(200, json={"values": [], "isLast": True})
    )
    issue = load_dc("issue_OS-91030.json")
    seen: list[str] = []

    def handler(request):
        seen.append(dict(request.url.params)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 100, "total": 1, "issues": [issue]})

    respx.get(f"{API}/search").mock(side_effect=handler)
    async with _client() as jira:
        values = await jira.get_field_distinct_values("customfield_11092")
    assert seen == ["cf[11092] is not EMPTY ORDER BY updated DESC"]
    assert values == [issue["fields"]["customfield_11092"]["value"]]


def test_jql_field_ref():
    assert jql_field_ref("customfield_11092") == "cf[11092]"
    assert jql_field_ref("summary") == '"summary"'


@respx.mock
def test_project_team_filter_uses_cf_reference(db_session):
    """Фильтр проектов по команде: поле — ``cf[N]``, значение — экранированный литерал."""
    for key, value in (
        ("jira_base_url", BASE),
        ("jira_api_token", "secret-token"),
        ("jira_team_field_id", "customfield_11092"),
    ):
        db_session.add(AppSetting(key=key, value=value))
    db_session.commit()
    respx.get(f"{API}/project").mock(return_value=httpx.Response(200, json=[
        {"id": "1", "key": "OS", "name": "Операционный"},
    ]))
    seen: list[str] = []

    def handler(request):
        seen.append(dict(request.url.params)["jql"])
        return httpx.Response(200, json={"startAt": 0, "maxResults": 1, "total": 0, "issues": []})

    respx.get(f"{API}/search").mock(side_effect=handler)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).get("/api/v1/sync/jira-projects", params={"team": 'Команда "А"'})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json() == []
    assert seen == ['project = "OS" AND (cf[11092] = "Команда \\"А\\"")']
