"""Конструктор промпта для саммари проекта."""
import hashlib
from typing import Any, Optional

from sqlalchemy.orm import Session


_BASE_VERSION = "v2"


# Редактируемая часть — роль/тон/инструкции стиля. Пользователь может переопределить
# через AppSetting `llm_project_summary_system_prompt`.
DEFAULT_SYSTEM_ROLE = """\
Ты — аналитик проектов. На вход получаешь данные по Jira-эпику и его дочерним
задачам: описание, ключевые задачи, ворклоги по сотрудникам и категориям,
статус. Твоя задача — выдать краткое саммари ПОЛЬЗОВАТЕЛЯМ-PM на русском языке.

Пиши лаконично, без воды. Не повторяй сами цифры из данных дословно.
"""


# Хардкод — описание JSON-схемы. Менять нельзя без правки GEMINI_RESPONSE_SCHEMA
# в gemini.py и моделей в types.py.
FORMAT_SPEC = """\
Формат строго JSON со следующими полями:
- goals: массив 3 строк, цели проекта (на основе описания эпика и задач). Максимум 80 символов на пункт.
- result_flow_blocks: массив 3-5 объектов {label, status}. Это интеграционный/процессный flow проекта. status ∈ ["source", "flow", "done"]. Первый — обычно "source", последний — "done" если проект готов, иначе "flow".
- result_checklist: массив 3-5 объектов {label, done}. Чек-лист достижений (например "11 дочерних задач", "полный контур").
- status_text: 1-2 предложения о текущем статусе проекта.
- workload_summary: 1 предложение о распределении нагрузки между сотрудниками.
- work_breakdown: массив 3-6 групп {label, child_keys}. Каждая группа — это содержательное направление работ (например «Обмены и регламенты», «Аналитика», «Багфиксы», «Проверка», «Форма/UI»). Названия — на русском, до 40 символов, конкретные для этого проекта (НЕ общие как «Прочее»). child_keys — список Jira-ключей дочерних задач, относящихся к группе. Каждая дочерняя задача должна попасть в ровно одну группу. Если задач мало (<3) — можно одну общую группу «Все работы».
"""


SETTING_KEY = "llm_project_summary_system_prompt"


def get_system_role(db: Optional[Session]) -> str:
    """Вернуть пользовательский override роли или дефолт."""
    if db is None:
        return DEFAULT_SYSTEM_ROLE
    from app.models.app_setting import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row and row.value and row.value.strip():
        return row.value
    return DEFAULT_SYSTEM_ROLE


def compute_prompt_version(system_role: str) -> str:
    """Версия промпта = base + хеш редактируемой части.

    При смене текста в UI старые саммари автоматически считаются устаревшими
    (см. `regenerate_outdated_summaries`).
    """
    h = hashlib.sha256(system_role.encode("utf-8")).hexdigest()[:8]
    return f"{_BASE_VERSION}-{h}"


def current_prompt_version(db: Optional[Session]) -> str:
    return compute_prompt_version(get_system_role(db))


# Backward compat — статическая константа для дефолтного промпта.
PROMPT_VERSION = compute_prompt_version(DEFAULT_SYSTEM_ROLE)


def build_prompt(epic_data: dict[str, Any], db: Optional[Session] = None) -> str:
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
        "child_summaries": [{"key": "PMD-1", "summary": "..."}, ...]  # max 30 элементов
    }
    """
    role = get_system_role(db)
    parts: list[str] = [role, "", FORMAT_SPEC, "", "ВХОДНЫЕ ДАННЫЕ:"]
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
        parts.append("\nКЛЮЧИ ДОЧЕРНИХ ЗАДАЧ С ОПИСАНИЕМ:")
        for s in summaries:
            parts.append(f"  • {s['key']}: {s['summary']}")

    parts.append("\nВЫДАЙ JSON РЕЗУЛЬТАТ.")
    return "\n".join(parts)
