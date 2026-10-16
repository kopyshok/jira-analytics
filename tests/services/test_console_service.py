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
