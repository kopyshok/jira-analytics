"""Tests for JiraClient.get_worklogs_updated_since (bulk worklog API)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.jira_client import JiraClient


def _make_client() -> JiraClient:
    """JiraClient с минимальными настройками (не инициализирован через context manager)."""
    client = JiraClient.__new__(JiraClient)
    client.max_retries = 3
    client.request_delay = 0.0
    client._client = MagicMock()  # не None — чтобы _request прошёл проверку
    return client


@pytest.mark.asyncio
async def test_get_worklogs_updated_since_paginates():
    """Если lastPage=false — делает второй запрос с since=until из первого ответа."""
    client = _make_client()

    page1 = {
        "values": [{"worklogId": 1}, {"worklogId": 2}],
        "since": 1000,
        "until": 2000,
        "lastPage": False,
    }
    page2 = {
        "values": [{"worklogId": 3}],
        "since": 2000,
        "until": 3000,
        "lastPage": True,
    }
    # POST /worklog/list возвращает пустой список (не тестируем содержимое здесь)
    post_response: list = []

    get_call_params: list[dict] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            get_call_params.append(dict(params or {}))
            return page1 if len(get_call_params) == 1 else page2
        return post_response

    client._request = fake_request  # type: ignore[method-assign]

    since = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    results = []
    async for wl in client.get_worklogs_updated_since(since):
        results.append(wl)

    assert len(get_call_params) == 2
    # Первый вызов — since из аргумента
    since_ms = int(since.timestamp() * 1000)
    assert get_call_params[0]["since"] == since_ms
    # Второй вызов — since=until из первой страницы
    assert get_call_params[1]["since"] == 2000


@pytest.mark.asyncio
async def test_get_worklogs_updated_since_batches_1000():
    """1001 worklog ID → 2 вызова POST /worklog/list."""
    client = _make_client()

    # Один GET со списком 1001 ID
    worklog_ids = list(range(1, 1002))
    page = {
        "values": [{"worklogId": i} for i in worklog_ids],
        "since": 0,
        "until": 9999,
        "lastPage": True,
    }

    # POST возвращает пустой список (тест только считает вызовы)
    post_calls: list[list] = []

    async def fake_request(method, path, params=None, json=None):
        if method == "GET":
            return page
        if method == "POST":
            post_calls.append(json["ids"])
            return []
        return {}

    client._request = fake_request  # type: ignore[method-assign]

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async for _ in client.get_worklogs_updated_since(since):
        pass

    assert len(post_calls) == 2
    assert len(post_calls[0]) == 1000
    assert len(post_calls[1]) == 1
    assert post_calls[0][0] == 1
    assert post_calls[1][0] == 1001
