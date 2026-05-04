"""Конструктор промпта для саммари проекта."""
import hashlib
from typing import Any, Optional

from sqlalchemy.orm import Session


_BASE_VERSION = "v5"


# Редактируемая часть — роль/тон/инструкции стиля. Пользователь может переопределить
# через AppSetting `llm_project_summary_system_prompt`.
DEFAULT_SYSTEM_ROLE = """\
Ты — аналитик проектов. На вход получаешь данные по Jira-эпику и его дочерним
задачам: описание, ключевые задачи, ворклоги по сотрудникам и категориям,
статусы. Задача — выдать краткое саммари ПОЛЬЗОВАТЕЛЯМ-PM на русском языке.

Пиши лаконично, без воды, на языке бизнес-результата. Не повторяй сами цифры
дословно. Не используй внутренние термины команды (БФТ, ТЗ как процесс,
«согласовать», «обсудить»). Опирайся на статусы дочерних задач: ✓ рядом
со статусом = задача в категории "done".

ПРАВИЛА ДЛЯ КАЖДОГО БЛОКА:

# 1. goals (Цели проекта)
Цель = бизнес-результат для заказчика, не внутренний шаг команды.
ЗАПРЕЩЕНО: «согласовать», «обсудить», «провести встречу», «написать ТЗ»,
«проанализировать», «изучить», «подготовить документ».
РАЗРЕШЕНО: «автоматизировать», «обеспечить», «сократить», «повысить»,
«прозрачно управлять», «соблюдать», «контролировать», «внедрить».
Цель формулируется как существительное-результат («Прозрачное управление
контрольными процедурами») или инфинитив ценности («Соблюдать сроки
закрытия месяца»). Цель должна звучать осмысленно вне Jira — её мог
бы поставить заказчик.
ПРИМЕР:
  ПЛОХО: «Согласовать БФТ с финансистами»
  ХОРОШО: «Прозрачное управление контрольными процедурами»
  ПЛОХО: «Подготовить базу 1С ERP»
  ХОРОШО: «Соблюдение сроков закрытия месяца»

# 2. result_checklist (Основной результат)
Достижение = конкретный артефакт, появившийся у заказчика.
Глагол совершенного вида страдательного залога в начале:
«Разработан/Автоматизирован/Внедрён/Настроен/Реализован».
Объект — конкретный артефакт: АРМ, форма, регламент, отчёт, обмен,
справочник, фоновое задание, дашборд.
ЗАПРЕЩЕНО как результат: «ТЗ написано», «требования собраны», «встречи
проведены», «БФТ согласовано» — это шаги, не результаты для бизнеса.
done=true СТРОГО только если все ключевые задачи направления в
status_category=done. Если хотя бы одна задача в работе — done=false и
формулировка в будущем времени: «Будет автоматизирован запуск...».
ПРИМЕР:
  ПЛОХО: ✓ Техническое задание готово (части 1-3)
  ХОРОШО: ✓ Разработаны формы управления контрольными процедурами
  ПЛОХО: ✓ Базовые функции справочников реализованы
  ХОРОШО: ✓ Автоматизированы запуск и мониторинг контрольных процедур
КАЖДЫЙ пункт привязан к одной из 4 категорий: analysis | development |
testing | ope (соответствие work_breakdown ниже).

# 3. work_breakdown (Структура трудозатрат)
СТРОГО 4 фиксированных категории, в этом порядке:
- analysis ("Анализ"): анализ процессов/процедур заказчика, сбор требований,
  ТЗ, БФТ, проектирование функциональности.
- development ("Разработка"): кодирование АРМ, форм, отчётов, регламентных и
  фоновых заданий, обменов, миграций, справочников.
- testing ("Тестирование"): отладка кода, обменов, нагрузочное, регрессионное,
  исправление багов до релиза.
- ope ("ОПЭ"): опытно-промышленная эксплуатация, демонстрации заказчику,
  написание инструкций, обучение, поддержка после релиза.
Каждая ДОЧЕРНЯЯ задача попадает в РОВНО ОДНУ категорию по типу
(Bug/Defect → testing; Sub-task с словами «инструкция»/«демо»/«ОПЭ» → ope;
аналитика/требования/ТЗ → analysis; иначе → development). Если в категории
0 задач — её всё равно вернуть с пустым child_keys (но у тебя в данных
все 4 категории должны заполниться, иначе перепроверь распределение).

# 4. status_text (Статус проекта)
Прогноз и риски, не констатация. Покажи где проект сейчас + что дальше +
что может пойти не так.
ПЛОХО: «Проект в активной разработке».
ХОРОШО: «Анализ завершён, идёт разработка фоновых заданий (~40% времени
проекта). Риск — задачи 1С ERP без оценки, возможен сдвиг ОПЭ».

# 5. workload_summary (Распределение нагрузки)
Выявляй перекосы и риски bus-factor, а не пересказывай %.
ПЛОХО: «Пак Илья — 60%, Копышков — 35%».
ХОРОШО: «Основная нагрузка на двух разработчиков, аналитика растянута
на одного человека — риск bus-factor».
"""


# Хардкод — описание JSON-схемы. Менять нельзя без правки GEMINI_RESPONSE_SCHEMA
# в gemini.py и моделей в types.py.
FORMAT_SPEC = """\
Формат строго JSON со следующими полями:
- goals: массив 3-5 строк — бизнес-цели проекта (правила см. в роли).
  Максимум 80 символов на пункт.
- result_checklist: массив 3-7 объектов {label, done, category}. Достижения
  проекта. category ∈ ["analysis","development","testing","ope"] —
  привязка к work_breakdown. done=true ТОЛЬКО для готовых артефактов
  (все ключевые задачи направления в status_category=done).
- status_text: 1-3 предложения — текущий этап + прогноз + риски.
- workload_summary: 1-2 предложения — перекосы нагрузки и bus-factor.
- work_breakdown: массив РОВНО 4 объектов {bucket, label, child_keys}
  в строгом порядке:
    {"bucket":"analysis","label":"Анализ","child_keys":[...]}
    {"bucket":"development","label":"Разработка","child_keys":[...]}
    {"bucket":"testing","label":"Тестирование","child_keys":[...]}
    {"bucket":"ope","label":"ОПЭ","child_keys":[...]}
  Каждая дочерняя задача попадает в ровно одну категорию.
  Пустая категория допустима (child_keys=[]), но проверь — обычно
  все 4 заполнены.
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
    """Build user prompt из агрегированных данных по эпику."""
    role = get_system_role(db)
    parts: list[str] = [role, "", FORMAT_SPEC, "", "ВХОДНЫЕ ДАННЫЕ:"]
    parts.append(f"Проект: {epic_data['summary']} ({epic_data['key']})")
    if epic_data.get("description"):
        desc = epic_data["description"][:8000]
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
        parts.append("\nДОЧЕРНИЕ ЗАДАЧИ:")
        for s in summaries:
            status = s.get("status") or "—"
            done_mark = " ✓" if s.get("is_done") else ""
            issue_type = s.get("issue_type") or ""
            type_tag = f" <{issue_type}>" if issue_type else ""
            parts.append(f"\n— {s['key']} [{status}{done_mark}]{type_tag} — {s['summary']}")
            if s.get("goal_text"):
                parts.append(f"  Цель: {s['goal_text'][:8000]}")
            if s.get("current_behavior"):
                parts.append(f"  Текущее поведение: {s['current_behavior'][:8000]}")
            if s.get("description"):
                parts.append(f"  Описание: {s['description'][:8000]}")

    pages = epic_data.get("confluence_pages", [])
    if pages:
        parts.append("\nCONFLUENCE-СТРАНИЦЫ (полные ТЗ по ссылкам из задач):")
        for pg in pages[:10]:
            parts.append(f"\n— {pg['title']} ({pg['url']})")
            parts.append(pg['body_text'][:8000])

    parts.append("\nВЫДАЙ JSON РЕЗУЛЬТАТ.")
    return "\n".join(parts)
