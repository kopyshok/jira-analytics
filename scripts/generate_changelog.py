"""Генерирует ченджлог из release_notes/<version>.json в Markdown или HTML.

Использование:
    py -3.10 scripts/generate_changelog.py v1.2.1                          # stdout, md
    py -3.10 scripts/generate_changelog.py v1.2.1 --out v1.2.1.md
    py -3.10 scripts/generate_changelog.py v1.2.1 --format html --out v1.2.1.html
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

TYPE_BADGE_COLOR = {
    "new": ("#0f5132", "#d1e7dd"),          # text, bg — зелёный
    "improvement": ("#055160", "#cff4fc"),  # синий
    "fix": ("#664d03", "#fff3cd"),          # янтарный
}


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


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(version: str, notes: list[dict]) -> str:
    grouped: dict[str, list[dict]] = {t: [] for t in TYPE_ORDER}
    for n in notes:
        t = n.get("type") or n.get("note_type")
        if t in grouped:
            grouped[t].append(n)

    counts = {t: len(items) for t, items in grouped.items()}
    total = sum(counts.values())

    sections_html: list[str] = []
    for t in TYPE_ORDER:
        items = grouped[t]
        if not items:
            continue
        text_c, bg_c = TYPE_BADGE_COLOR[t]
        by_section: dict[str, list[dict]] = {}
        for n in items:
            by_section.setdefault(n["section"], []).append(n)

        section_blocks: list[str] = []
        for section, entries in by_section.items():
            cards: list[str] = []
            for n in entries:
                cards.append(
                    f"""<article class="card">
  <h3>{_html_escape(n["title"])}</h3>
  <p>{_html_escape(n["description"])}</p>
</article>"""
                )
            section_blocks.append(
                f"""<div class="section">
  <h2 class="section-title">{_html_escape(SECTION_TITLES.get(section, section))}</h2>
  {"".join(cards)}
</div>"""
            )

        sections_html.append(
            f"""<section class="type-block">
  <header class="type-header">
    <span class="badge" style="color:{text_c};background:{bg_c}">
      {_html_escape(TYPE_TITLES[t])}
    </span>
    <span class="count">{len(items)}</span>
  </header>
  {"".join(section_blocks)}
</section>"""
        )

    summary_chips = "".join(
        f'<span class="chip" style="color:{TYPE_BADGE_COLOR[t][0]};background:{TYPE_BADGE_COLOR[t][1]}">'
        f'{_html_escape(TYPE_TITLES[t])} · {counts[t]}</span>'
        for t in TYPE_ORDER if counts[t]
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_escape(version)} · Что нового</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1f2329;
    background: #f5f7fa;
    line-height: 1.55;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 48px 32px 80px; }}
  .hero {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5085 100%);
    color: #fff;
    padding: 40px 32px;
    border-radius: 16px;
    margin-bottom: 32px;
    box-shadow: 0 8px 24px rgba(30, 58, 95, 0.15);
  }}
  .hero .label {{ font-size: 13px; letter-spacing: 1.5px; text-transform: uppercase; opacity: 0.75; }}
  .hero h1 {{ margin: 4px 0 12px; font-size: 38px; font-weight: 700; }}
  .hero .sub {{ font-size: 16px; opacity: 0.9; }}
  .summary {{ margin-top: 20px; display: flex; gap: 8px; flex-wrap: wrap; }}
  .chip {{
    display: inline-block;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 600;
  }}
  .type-block {{ margin-bottom: 40px; }}
  .type-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .badge {{
    display: inline-block;
    padding: 6px 16px;
    border-radius: 8px;
    font-size: 18px;
    font-weight: 700;
  }}
  .count {{ color: #6b7280; font-size: 14px; }}
  .section {{ margin: 24px 0; }}
  .section-title {{
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #6b7280;
    margin: 0 0 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #e5e7eb;
  }}
  .card {{
    background: #fff;
    padding: 20px 24px;
    border-radius: 12px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
    border-left: 3px solid #e5e7eb;
  }}
  .card h3 {{ margin: 0 0 8px; font-size: 17px; font-weight: 600; color: #1f2329; }}
  .card p {{ margin: 0; color: #4b5563; font-size: 15px; }}
  .print-hint {{
    margin-top: 48px;
    padding: 16px 20px;
    background: #fff;
    border-radius: 8px;
    color: #6b7280;
    font-size: 13px;
    text-align: center;
  }}
  @media print {{
    body {{ background: #fff; }}
    .wrap {{ padding: 0; max-width: none; }}
    .hero {{ box-shadow: none; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .card, .badge, .chip {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .print-hint {{ display: none; }}
    .type-block {{ break-inside: avoid; }}
    .card {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="label">Релиз</div>
    <h1>{_html_escape(version)}</h1>
    <div class="sub">Что нового — {total} {"запись" if total == 1 else "записи" if 2 <= total <= 4 else "записей"}</div>
    <div class="summary">{summary_chips}</div>
  </div>
  {"".join(sections_html)}
  <div class="print-hint">Сохранить в PDF: Ctrl/⌘+P → «Сохранить как PDF»</div>
</div>
</body>
</html>
"""


def main() -> int:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Changelog from release_notes JSON")
    p.add_argument("version", help="Версия, например v1.2.1")
    p.add_argument("--out", default=None, help="Файл (по умолчанию stdout)")
    p.add_argument(
        "--format", choices=("md", "html"), default="md",
        help="md (по умолчанию) или html (красивый, для печати/PDF)",
    )
    args = p.parse_args()

    version = args.version if args.version.startswith("v") else f"v{args.version}"
    src = REPO_ROOT / "release_notes" / f"{version}.json"
    if not src.exists():
        sys.stderr.write(f"Нет файла {src}\n")
        return 1

    payload = json.loads(src.read_text(encoding="utf-8"))
    notes = payload.get("notes") or []
    body = render_html(version, notes) if args.format == "html" else render(version, notes)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        sys.stdout.write(f"OK: {args.out}\n")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
