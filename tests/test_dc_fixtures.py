"""Фикстуры Jira DC: на месте и без персональных данных."""
import json
import re

from tests.dc_fixtures import FIXTURE_DIR, load_dc

EXPECTED = {
    "server_info.json",
    "issue_OS-91030.json", "issue_OS-91031.json", "issue_RFA-4610.json",
    "issue_OS-92392.json", "issue_OS-93622.json", "issue_OS-89194.json",
    "issue_RFA-5020.json",
    "worklogs_OS-91030.json", "worklogs_OS-91031.json", "worklogs_RFA-4610.json",
    "worklog_list.json", "worklog_updated.json", "search_count_OS.json",
    "custom_field_options_error.json", "fields.json",
    "user_search.json", "user_search_single.json",
}
ALLOWED_HOSTS = {"jira.example.test", "confluence.example.test"}
URL_HOST_RE = re.compile(r"https?://([^/\s\"'\]|)<>]+)")
EMAIL_RE =re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _users(node):
    if isinstance(node, dict):
        if "key" in node and "name" in node and ("displayName" in node or "emailAddress" in node):
            yield node
        for value in node.values():
            yield from _users(value)
    elif isinstance(node, list):
        for value in node:
            yield from _users(value)


def test_all_fixture_files_present():
    assert EXPECTED <= {p.name for p in FIXTURE_DIR.glob("*.json")}


def test_no_real_host_or_email():
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for host in URL_HOST_RE.findall(text):
            assert host in ALLOWED_HOSTS, (path.name, host)
        for email in EMAIL_RE.findall(text):
            assert email.endswith("@example.test"), (path.name, email)


def test_people_are_replaced_consistently():
    seen = 0
    for path in FIXTURE_DIR.glob("*.json"):
        for user in _users(json.loads(path.read_text(encoding="utf-8"))):
            seen += 1
            assert re.fullmatch(r"JIRAUSER9\d{4}", user["key"]), (path.name, user["key"])
            assert re.fullmatch(r"user_\d+", user["name"]), (path.name, user["name"])
            assert user["displayName"].startswith("Сотрудник "), path.name
    assert seen > 20


def test_issue_ids_and_links_kept():
    issue = load_dc("issue_OS-91030.json")
    assert issue["id"] == "258783"
    assert issue["fields"]["customfield_10107"] == "OS-84096"
    assert load_dc("issue_OS-89194.json")["fields"]["customfield_10100"] == "RFA-4599"
    assert load_dc("worklog_updated.json")["lastPage"] is True
    assert len(load_dc("worklog_updated.json")["values"]) >= 30


def test_no_internal_addresses():
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for domain in re.findall(r"\b[\w-]+\.local\b", text):
            assert domain == "internal.local", (path.name, domain)
