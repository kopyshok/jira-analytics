"""Конструктор промпта для саммари проекта."""
from typing import Any


PROMPT_VERSION = "v1"


SYSTEM_INSTRUCTION = """\
Ты — аналитик проектов. На вход получаешь данные по Jira-эпику и его дочерним
задачам: описание, ключевые задачи, ворклоги по сотрудникам и категориям,
статус. Твоя задача — выдать краткое саммари ПОЛЬЗОВАТЕЛЯМ-PM на русском языке.

Формат строго JSON со следующими полями:
- goals: массив 3 строк, цели проекта (на основе описания эпика и задач). Максимум 80 символов на пункт.
- result_flow_blocks: массив 3-5 объектов {label, status}. Это интеграционный/процессный flow проекта. status ∈ ["source", "flow", "done"]. Первый — обычно "source", последний — "done" если проект готов, иначе "flow".
- result_checklist: массив 3-5 объектов {label, done}. Чек-лист достижений (например "11 дочерних задач", "полный контур").
- status_text: 1-2 предложения о текущем статусе проекта.
- workload_summary: 1 предложение о распределении нагрузки между сотрудниками.

Пиши лаконично, без воды. Не повторяй сами цифры из данных дословно.
"""


def build_prompt(epic_data: dict[str, Any]) -> str:
    """Build user prompt из агрегированных данных по эпику.

    epic_data ожидается в форме:
    {
        "key": "PRJ-1", "summary": "...", "description": "...",
        "status": "Done", "is_done": True,
        "child_count": 11, "employee_count": 7, "total_hours": 187.4,
        "period_start": "2026-02-12", "period_end": "2026-03-25",
        "categories": [{"label": "Аналитика", "hours": 57}, ...],
        "employees": [{"name": "Копышков Н.", "hours": 70.5, "pct": 37.6}, ...],
        "top_issues": [{"key": "PMD-1", "summary": "...", "hours": 49.5}, ...],
        "child_summaries": ["...", "..."]  # max 30 элементов
    }
    """
    parts: list[str] = [SYSTEM_INSTRUCTION, "", "ВХОДНЫЕ ДАННЫЕ:"]
    parts.append(f"Проект: {epic_data['summary']} ({epic_data['key']})")
    if epic_data.get("description"):
        desc = epic_data["description"][:1500]
        parts.append(f"Описание: {desc}")
    parts.append(f"Статус: {epic_data['status']} (закрыт: {epic_data.get('is_done', False)})")
    parts.append(
        f"Период: {epic_data.get('period_start')} → {epic_data.get('period_end')} "
        f"(всего {epic_data.get('total_hours', 0)} ч, {epic_data.get('child_count', 0)} задач, "
        f"{epic_data.get('employee_count', 0)} участников)"
    )

    parts.append("\nКатегории трудозатрат:")
    for c in epic_data.get("categories", [])[:8]:
        parts.append(f"  • {c['label']}: {c['hours']} ч")

    parts.append("\nУчастники:")
    for e in epic_data.get("employees", [])[:10]:
        parts.append(f"  • {e['name']}: {e['hours']} ч ({e.get('pct', 0)}%)")

    parts.append("\nТоп-задачи:")
    for t in epic_data.get("top_issues", [])[:5]:
        parts.append(f"  • {t['key']} — {t['summary']} ({t['hours']} ч)")

    summaries = epic_data.get("child_summaries", [])[:30]
    if summaries:
        parts.append("\nКраткий список дочерних задач:")
        for s in summaries:
            parts.append(f"  • {s}")

    parts.append("\nВЫДАЙ JSON РЕЗУЛЬТАТ.")
    return "\n".join(parts)
