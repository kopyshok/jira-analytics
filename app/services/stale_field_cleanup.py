"""Чистка «мёртвых» значений полей у переехавших задач.

Jira при переносе задачи в другой проект сохраняет ранее заполненные кастомные
поля, даже если в новом проекте таких полей нет. Значение продолжает приезжать
по API, поэтому задача, уехавшая из проекта разработки в проект управления, до
сих пор числится за разработчиком — и попадает на стол тимлида, в KPI и в
аналитику.

**Решение принимается по проекту, а не по типу задачи.** Отдельный тип задач
может не показывать поле на экране редактирования, хотя в проекте поле живое и
заполняется (так в проекте разработки устроены заявки поддержки: поля на карточке
нет, а значение осмысленное — часы списывает именно указанный разработчик).
Поэтому проект считается «живым», если поле доступно хотя бы на одном из его
типов задач; чистим только те проекты, где поля нет нигде.

Доступность спрашиваем у Jira: она отдаёт список полей карточки конкретной
задачи. Опрашиваем по одному представителю на связку «проект + тип» — таких
связок десятки, а не сотни тысяч, — и останавливаемся, как только у проекта
нашлась связка с полем.

Тот же приём применим к любому другому кастомному полю: достаточно передать его
id и колонки, которые нужно обнулить.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AppSetting, Issue, Project

logger = logging.getLogger(__name__)

# Сколько задач связки опрашиваем, прежде чем признать поле недоступным.
# Одна карточка — слабое основание: доступность полей зависит и от прав, и от
# настроек рабочего процесса.
PROBE_LIMIT = 3

# Размер порции для UPDATE ... WHERE id IN (...) — у SQLite лимит на параметры.
CHUNK = 500


async def _field_available(
    jira, field_id: str, issue_keys: list[str]
) -> Optional[bool]:
    """Доступно ли поле на карточках этих задач. ``None`` — выяснить не удалось.

    Достаточно одной карточки, где поле есть. Ошибки опроса (нет прав, сеть) не
    считаются ответом — иначе сбой связи затирал бы данные.
    """
    answers: list[bool] = []
    for key in issue_keys:
        try:
            available = await jira.get_editable_field_ids(key)
        except Exception as exc:  # noqa: BLE001 — любой сбой опроса не ответ
            logger.warning("Не удалось получить поля карточки %s: %s", key, exc)
            continue
        answers.append(field_id in available)
    if not answers:
        return None
    return any(answers)


async def _projects_without_field(
    db: Session, jira, field_id: str, project_keys: set[str]
) -> set[str]:
    """Проекты, где поля нет ни на одном типе задач.

    По каждому типу берём представителя и спрашиваем Jira. Как только у проекта
    нашлась карточка с полем — остальные типы не опрашиваем: проект живой.
    Проект, по которому ничего выяснить не удалось, в результат не попадает.
    """
    rows = (
        db.query(Project.key, Issue.issue_type, Issue.key)
        .join(Project, Project.id == Issue.project_id)
        .filter(Project.key.in_(project_keys))
        .all()
    )
    samples: dict[str, dict[str, list[str]]] = {}
    for project_key, issue_type, issue_key in rows:
        by_type = samples.setdefault(project_key, {})
        keys = by_type.setdefault(issue_type or "", [])
        if len(keys) < PROBE_LIMIT:
            keys.append(issue_key)

    dead: set[str] = set()
    for project_key, by_type in samples.items():
        verdicts: list[Optional[bool]] = []
        for issue_type, keys in by_type.items():
            verdict = await _field_available(jira, field_id, keys)
            verdicts.append(verdict)
            if verdict:
                logger.info(
                    "Поле есть на карточках %s / %s — проект не трогаем",
                    project_key, issue_type or "без типа",
                )
                break
        if any(v for v in verdicts):
            continue
        if all(v is None for v in verdicts):
            # Ни одного внятного ответа — данные не трогаем.
            logger.warning("Про проект %s выяснить не удалось", project_key)
            continue
        dead.add(project_key)
    return dead


async def clear_stale_developer_field(
    db: Session, jira, dry_run: bool = False
) -> dict:
    """Обнулить поле «Разработчик» в проектах, где этого поля нет.

    ``dry_run`` — только посчитать, ничего не записывая: нужен разовому скрипту,
    чтобы показать масштаб до правки данных.

    Возвращает сводку: сколько проектов проверено, в сколких поля нет и сколько
    задач очищено.
    """
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == "jira_developer_field_id")
        .first()
    )
    field_id = (row.value or "").strip() if row else ""
    if not field_id:
        # Поле не настроено — чистить нечего и не по чему.
        return {"projects_checked": 0, "projects_stale": 0, "issues_cleared": 0}

    filled = (
        db.query(Issue.id, Project.key)
        .join(Project, Project.id == Issue.project_id)
        .filter(Issue.developer_account_id.isnot(None))
        .all()
    )
    if not filled:
        return {"projects_checked": 0, "projects_stale": 0, "issues_cleared": 0}

    ids_by_project: dict[str, list[str]] = {}
    for issue_id, project_key in filled:
        ids_by_project.setdefault(project_key, []).append(issue_id)

    dead = await _projects_without_field(
        db, jira, field_id, set(ids_by_project.keys())
    )
    stale_ids = [i for key in dead for i in ids_by_project[key]]
    for key in sorted(dead):
        logger.info(
            "Поля «Разработчик» нет в проекте %s — чистим %d задач",
            key, len(ids_by_project[key]),
        )

    if stale_ids and not dry_run:
        for start in range(0, len(stale_ids), CHUNK):
            db.query(Issue).filter(Issue.id.in_(stale_ids[start:start + CHUNK])).update(
                {"developer_account_id": None, "developer_display_name": None},
                synchronize_session=False,
            )
        db.commit()

    return {
        "projects_checked": len(ids_by_project),
        "projects_stale": len(dead),
        "issues_cleared": len(stale_ids),
    }
