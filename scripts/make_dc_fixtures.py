"""Обезличенные фикстуры Jira DC для тестов из ответа админа (data/jira_check.txt).

Формат входа: строка ``== <раздел>`` и следующая строка — сырой JSON ответа.
Имена, логины, почты, ключи пользователей, аватары и адрес сервера
заменяются выдуманными; структура ответов и id задач/ворклогов сохраняются.
Один и тот же человек во всех файлах получает одну и ту же замену.
Перед записью — проверка: ни одно настоящее имя/логин/почта не попали в вывод.

Запуск из корня репозитория:
    py -3.10 scripts/make_dc_fixtures.py
Пишет tests/fixtures/jira_dc/*.json. data/ в репозиторий не попадает.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "jira_check.txt"
OUT = ROOT / "tests" / "fixtures" / "jira_dc"
FAKE_HOST = "https://jira.example.test"

# Поля задачи, нужные тестам. Остальное (комментарии, вложения, ворклоги
# внутри задачи, текстовые поля) несёт рабочие тексты — выбрасываем.
ISSUE_FIELDS = (
    "summary", "description", "issuetype", "status", "priority", "project",
    "parent", "creator", "reporter", "assignee", "created", "updated",
    "duedate", "resolution", "resolutiondate", "issuelinks", "subtasks",
    "fixVersions",
    "customfield_10107",  # Ссылка на эпик
    "customfield_10100",  # Parent Link
    "customfield_10109",  # Спринт
    "customfield_11092",  # Продуктовая команда
    "customfield_11098",  # Разработчик
)
FIELD_KEYS = ("id", "name", "custom", "orderable", "navigable", "searchable", "clauseNames", "schema")
FAKE_DESCRIPTION = (
    "h2. Описание\nТекст задачи для теста.\n"
    "[Страница ТЗ|https://confluence.example.test/x/AbCdE]"
)
URL_HOST = re.compile(r"(https?://)([^/\s\"'\]|)<>]+)")
LOCAL_DOMAIN = re.compile(r"\b[\w-]+\.local\b")
SPRINT_GOAL = re.compile(r"goal=(?!<null>,)(.*?),incompleteIssuesDestinationId=")
UPDATED_ITEM = re.compile(r'\{"worklogId":(\d+),"updatedTime":(\d+)\}')


def read_sections(path: Path) -> dict[str, str]:
    """``{название раздела: строка JSON}``."""
    sections: dict[str, str] = {}
    name = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("== "):
            name = line[3:].strip()
        elif name is not None and line.strip():
            sections[name] = line
            name = None
    return sections


def _is_user(node: dict) -> bool:
    return "key" in node and "name" in node and ("displayName" in node or "emailAddress" in node)


def _mask_host(match: re.Match) -> str:
    host = match.group(2)
    if host.endswith("example.test"):
        return match.group(0)
    return match.group(1) + FAKE_HOST.split("://", 1)[1]


def mask_text(text: str) -> str:
    """Любой адрес http(s) -> jira.example.test; внутренние домены .local -> internal.local."""
    text = SPRINT_GOAL.sub("goal=<null>,incompleteIssuesDestinationId=", text)
    return LOCAL_DOMAIN.sub("internal.local", URL_HOST.sub(_mask_host, text))


class Sanitizer:
    """Заменяет людей и адрес сервера, запоминая настоящие значения для проверки."""

    def __init__(self, real_base_url: str) -> None:
        self.real_host = real_base_url.rstrip("/")
        self.people: dict[str, int] = {}
        self.secrets: set[str] = {urlparse(real_base_url).netloc}

    def _person(self, user: dict) -> int:
        ident = user.get("key") or user.get("name") or user.get("displayName")
        if ident not in self.people:
            self.people[ident] = len(self.people) + 1
        for field in ("name", "key", "displayName", "emailAddress"):
            value = user.get(field)
            if isinstance(value, str) and value:
                self.secrets.add(value)
                if field == "emailAddress" and "@" in value:
                    self.secrets.add(value.split("@", 1)[1])
        return self.people[ident]

    def user(self, user: dict) -> dict:
        n = self._person(user)
        out = dict(user)
        out["key"] = f"JIRAUSER9{n:04d}"
        out["name"] = f"user_{n}"
        out["displayName"] = f"Сотрудник {n}"
        if "emailAddress" in out:
            out["emailAddress"] = f"user_{n}@example.test"
        if isinstance(out.get("avatarUrls"), dict):
            out["avatarUrls"] = {
                size: f"{FAKE_HOST}/secure/useravatar?size={size}&avatarId=1"
                for size in out["avatarUrls"]
            }
        if "self" in out:
            out["self"] = f"{FAKE_HOST}/rest/api/2/user?username=user_{n}"
        return out

    def walk(self, node):
        if isinstance(node, dict):
            if _is_user(node):
                node = self.user(node)
            return {k: self.walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self.walk(v) for v in node]
        if isinstance(node, str):
            return mask_text(node)
        return node


def clean_issue(raw: dict, s: Sanitizer) -> dict:
    fields = raw.get("fields") or {}
    kept = {k: fields[k] for k in ISSUE_FIELDS if k in fields}
    kept["summary"] = f"Задача {raw['key']}"
    if kept.get("description") is not None:
        kept["description"] = FAKE_DESCRIPTION
    for link in kept.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            other = link.get(side)
            if isinstance(other, dict) and isinstance(other.get("fields"), dict):
                other["fields"]["summary"] = "Связанная задача"
    for sub in kept.get("subtasks") or []:
        if isinstance(sub.get("fields"), dict):
            sub["fields"]["summary"] = "Подзадача"
    parent = kept.get("parent")
    if isinstance(parent, dict) and isinstance(parent.get("fields"), dict):
        parent["fields"]["summary"] = "Родительская задача"
    out = {k: raw[k] for k in ("expand", "id", "self", "key") if k in raw}
    out["fields"] = kept
    return s.walk(out)


def clean_worklog(worklog: dict) -> dict:
    out = dict(worklog)
    if out.get("comment") is not None:
        out["comment"] = "Комментарий к списанию"
    return out


def parse_worklog_updated(text: str) -> dict:
    """Ответ /worklog/updated; в файле админа он обрезан — берём целые записи."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        values = [
            {"worklogId": int(wid), "updatedTime": int(ts)}
            for wid, ts in UPDATED_ITEM.findall(text)
        ]
        return {
            "values": values,
            "since": values[0]["updatedTime"],
            "until": values[-1]["updatedTime"],
            "lastPage": True,
        }


def main() -> int:
    if not SOURCE.exists():
        print(f"Нет файла {SOURCE}", file=sys.stderr)
        return 1
    sections = read_sections(SOURCE)
    server = json.loads(sections["serverInfo"])
    s = Sanitizer(server["baseUrl"])

    out: dict[str, object] = {"server_info.json": s.walk(server)}
    for name, text in sections.items():
        if name.startswith("issue "):
            raw = json.loads(text)
            out[f"issue_{raw['key']}.json"] = clean_issue(raw, s)
        elif name.startswith("worklog ") and not name.startswith("worklog/"):
            key = name.split(" ", 1)[1]
            page = json.loads(text)
            page["worklogs"] = [clean_worklog(w) for w in page.get("worklogs", [])]
            out[f"worklogs_{key}.json"] = s.walk(page)
    out["worklog_list.json"] = s.walk(
        [clean_worklog(w) for w in json.loads(sections["worklog/list"])]
    )
    out["worklog_updated.json"] = s.walk(parse_worklog_updated(sections["worklog/updated"]))
    out["search_count_OS.json"] = s.walk(json.loads(sections["count OS"]))
    out["custom_field_options_error.json"] = s.walk(json.loads(sections["team options"]))
    out["fields.json"] = s.walk([
        {k: f[k] for k in FIELD_KEYS if k in f} for f in json.loads(sections["fields"])
    ])
    user_lists = sorted(
        (json.loads(t) for n, t in sections.items() if n.startswith("user ")),
        key=len, reverse=True,
    )
    out["user_search.json"] = s.walk(user_lists[0])
    singles = [u for u in user_lists if len(u) == 1]
    if singles:
        out["user_search_single.json"] = s.walk(singles[0])

    texts = {
        name: json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        for name, data in out.items()
    }
    leaks = sorted(
        {name for name, text in texts.items() for secret in s.secrets
         if secret and secret.lower() in text.lower()}
    )
    for name, text in texts.items():
        for _, host in URL_HOST.findall(text):
            if not host.endswith("example.test"):
                leaks.append(f"{name} ({host})")
        if re.search(r"\b(?!internal\.)[\w-]+\.local\b", text):
            leaks.append(f"{name} (.local)")
    if leaks:
        print(f"Остались настоящие данные в: {', '.join(leaks)}", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"Записано {len(texts)} файлов в {OUT}, людей заменено: {len(s.people)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
