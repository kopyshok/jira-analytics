from unittest.mock import AsyncMock

import pytest

from app.connectors.jira_client import JiraClient


@pytest.mark.asyncio
async def test_search_users_parses_response():
    fake_response = [
        {
            "accountId": "a1",
            "displayName": "Иванов",
            "emailAddress": "ivanov@example.com",
            "active": True,
            "avatarUrls": {"48x48": "https://example.com/a.png"},
        },
        {
            "accountId": "a2",
            "displayName": "Петров",
            "emailAddress": None,
            "active": False,
            "avatarUrls": {"48x48": "https://example.com/b.png"},
        },
    ]

    client = JiraClient(
        base_url="https://x.atlassian.net", email="e", api_token="t"
    )
    # Patch the private request helper — whatever existing methods call.
    # Inspect the class first; `_request` or similar is common. Adapt.
    client._request = AsyncMock(return_value=fake_response)

    users = await client.search_users("ив")
    assert len(users) == 2
    assert users[0].jira_account_id == "a1"
    assert users[0].display_name == "Иванов"
    assert users[0].is_active is True
    assert users[1].email is None
