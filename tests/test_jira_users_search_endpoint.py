from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.connectors.schemas import JiraUserSchema
from app.database import get_db
from app.main import app


def test_search_rejects_short_query(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/jira/users/search", params={"query": "a"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_search_returns_users(db_session):
    # Construct JiraUserSchema via the Jira-payload (camelCase alias) shape —
    # that's what the real HTTP path produces, and what the schema's aliases
    # are designed for.
    fake = [
        JiraUserSchema(
            accountId="a1",
            displayName="Иванов",
            emailAddress="i@example.com",
            active=True,
            avatarUrls={"48x48": "https://example.com/a.png"},
        )
    ]

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_jira_ctx(_db):
        jira = AsyncMock()
        jira.search_users = AsyncMock(return_value=fake)
        yield jira

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with patch(
            "app.api.endpoints.sync.JiraClient.from_db",
            new=_fake_jira_ctx,
        ):
            client = TestClient(app)
            resp = client.get("/api/v1/jira/users/search", params={"query": "ив"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["jira_account_id"] == "a1"
    assert body[0]["display_name"] == "Иванов"
    assert body[0]["email"] == "i@example.com"
    assert body[0]["is_active"] is True
    assert body[0]["avatar_url"] == "https://example.com/a.png"
