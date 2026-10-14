"""Поиск пользователей Jira DC: параметр username, пользователь по key."""
from unittest.mock import AsyncMock

from app.connectors.jira_client import JiraClient


async def test_search_users_parses_dc_response():
    fake_response = [
        {
            "key": "JIRAUSER1",
            "name": "ivanov",
            "displayName": "Иванов",
            "emailAddress": "ivanov@example.com",
            "active": True,
            "avatarUrls": {"48x48": "https://example.com/a.png"},
        },
        {
            "key": "JIRAUSER2",
            "name": "petrov",
            "displayName": "Петров",
            "emailAddress": None,
            "active": False,
            "avatarUrls": {"48x48": "https://example.com/b.png"},
        },
    ]

    client = JiraClient(base_url="https://jira.example.test", api_token="t")
    client._request = AsyncMock(return_value=fake_response)

    users = await client.search_users("ив")
    client._request.assert_awaited_once_with(
        "GET", "/user/search", params={"username": "ив", "maxResults": 20},
    )
    assert len(users) == 2
    assert users[0].jira_account_id == "JIRAUSER1"
    assert users[0].name == "ivanov"
    assert users[0].display_name == "Иванов"
    assert users[0].is_active is True
    assert users[1].email is None
