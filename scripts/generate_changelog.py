"""Генерирует Markdown-ченджлог из release_notes/<version>.json.

Использование:
    py -3.10 scripts/generate_changelog.py v1.2.1
    py -3.10 scripts/generate_changelog.py v1.2.1 --out CHANGELOG-v1.2.1.md
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SECTION_TITLES = {
    "scenarios": "Сценарии",
    "resources": "Планирование ресурсов",
    "analytics": "Аналитика",
    "issues": "Категоризация задач",
    "dashboard": "Дашборд",
    "backlog": "Бэклог",
    "sync": "Синхронизация",
    "settings": "Настройки",
    "general": "Общее",
}

TYPE_TITLES = {
    "new": "Новое",
    "improvement": "Улучшения",
    "fix": "Исправления",
}

TYPE_ORDER = ("new", "improvement", "fix")


def render(version: str, notes: list[dict]) -> str:
    grouped: dict[str, list[dict]] = {t: [] for t in TYPE_ORDER}
    for n in notes:
        t = n.get("type") or n.get("note_type")
        if t in grouped:
            grouped[t].append(n)

    out: list[str] = []
    out.append(f"# {version} — Что нового")
    out.append("")

    for t in TYPE_ORDER:
        items = grouped[t]
        if not items:
            continue
        out.append(f"## {TYPE_TITLES[t]}")
        out.append("")

        by_section: dict[str, list[dict]] = {}
        for n in items:
            by_section.setdefault(n["section"], []).append(n)

        for section, entries in by_section.items():
            out.append(f"### {SECTION_TITLES.get(section, section)}")
            out.append("")
            for n in entries:
                out.append(f"**{n['title']}**")
                out.append("")
                out.append(n["description"])
                out.append("")

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Markdown changelog from release_notes JSON")
    p.add_argument("version", help="Версия, например v1.2.1")
    p.add_argument("--out", default=None, help="Файл (по умолчанию stdout)")
    args = p.parse_args()

    version = args.version if args.version.startswith("v") else f"v{args.version}"
    src = REPO_ROOT / "release_notes" / f"{version}.json"
    if not src.exists():
        sys.stderr.write(f"Нет файла {src}\n")
        return 1

    payload = json.loads(src.read_text(encoding="utf-8"))
    md = render(version, payload.get("notes") or [])

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        sys.stdout.write(f"OK: {args.out}\n")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
