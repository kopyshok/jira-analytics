"""One-off: pull Confluence page + Jira issue for architectural committee doc."""
import asyncio
import json
import re
import sys
from html.parser import HTMLParser

from app.connectors.confluence_client import ConfluenceClient
from app.connectors.jira_client import JiraClient
from app.database import get_db

PAGE_ID = "5237899268"
ISSUE_KEY = "PRJ-10685"


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def html_to_text(html: str) -> str:
    s = _Stripper()
    s.feed(html)
    return s.text()


def adf_to_text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    out: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for child in node.get("content", []) or []:
            out.append(adf_to_text(child))
        if node.get("type") in ("paragraph", "heading", "listItem", "tableRow"):
            out.append("\n")
    elif isinstance(node, list):
        for child in node:
            out.append(adf_to_text(child))
    return "".join(out)


async def main():
    db = next(get_db())

    # Confluence
    async with ConfluenceClient.from_db(db) as cc:
        page = await cc.get_page(PAGE_ID)

    page_text = html_to_text(page.body_html)

    # Jira
    async with JiraClient.from_db(db) as jc:
        data = await jc._request(
            "GET",
            f"/issue/{ISSUE_KEY}",
            params={"fields": "summary,description,status,issuetype,priority,assignee,reporter,labels,components,parent,subtasks,comment,created,updated,customfield_15258,customfield_15223,customfield_11421"},
        )

    f = data.get("fields", {})
    issue_dump = {
        "key": data.get("key"),
        "summary": f.get("summary"),
        "status": (f.get("status") or {}).get("name"),
        "type": (f.get("issuetype") or {}).get("name"),
        "priority": (f.get("priority") or {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "reporter": (f.get("reporter") or {}).get("displayName"),
        "labels": f.get("labels"),
        "components": [c.get("name") for c in f.get("components") or []],
        "parent": (f.get("parent") or {}).get("key"),
        "subtasks": [s.get("key") for s in f.get("subtasks") or []],
        "created": f.get("created"),
        "updated": f.get("updated"),
        "goal_cf_15258": adf_to_text(f.get("customfield_15258")),
        "current_behavior_cf_15223": adf_to_text(f.get("customfield_15223")),
        "goals_cf_11421": adf_to_text(f.get("customfield_11421")),
        "description": adf_to_text(f.get("description")),
        "comments": [
            {
                "author": (c.get("author") or {}).get("displayName"),
                "created": c.get("created"),
                "body": adf_to_text(c.get("body")),
            }
            for c in (f.get("comment") or {}).get("comments", []) or []
        ],
    }

    out = {
        "confluence": {
            "id": page.id,
            "title": page.title,
            "text": page_text,
            "raw_html_len": len(page.body_html),
        },
        "jira": issue_dump,
    }

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
