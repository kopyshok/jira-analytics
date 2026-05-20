"""Pull children of PRJ-10685 epic for arch doc."""
import asyncio
import json
import re
import sys
from html.parser import HTMLParser

from app.connectors.jira_client import JiraClient
from app.database import get_db

EPIC = "PRJ-10685"


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
    async with JiraClient.from_db(db) as jc:
        # Try several JQL variants
        for jql in [
            f'parent = {EPIC}',
            f'"Epic Link" = {EPIC}',
        ]:
            try:
                data = await jc._request(
                    "GET",
                    "/search/jql",
                    params={
                        "jql": jql,
                        "fields": "summary,status,issuetype,priority,assignee,description,parent",
                        "maxResults": 100,
                    },
                )
                issues = data.get("issues", [])
                if issues:
                    print(f"\n# JQL: {jql} → {len(issues)} issues", file=sys.stderr)
                    out = []
                    for it in issues:
                        f = it.get("fields", {})
                        out.append({
                            "key": it.get("key"),
                            "summary": f.get("summary"),
                            "type": (f.get("issuetype") or {}).get("name"),
                            "status": (f.get("status") or {}).get("name"),
                            "assignee": (f.get("assignee") or {}).get("displayName"),
                            "description": adf_to_text(f.get("description"))[:2000],
                        })
                    sys.stdout.reconfigure(encoding="utf-8")
                    print(json.dumps(out, ensure_ascii=False, indent=2))
                    return
            except Exception as e:
                print(f"JQL {jql} failed: {e}", file=sys.stderr)
        print("[]")


if __name__ == "__main__":
    asyncio.run(main())
