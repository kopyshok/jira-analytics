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
    r"\\evil.com\rest",
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
