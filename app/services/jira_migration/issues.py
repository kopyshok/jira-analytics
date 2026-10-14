"""Задачи при переезде: новые id по ключам и задачи, которых нет в новой Jira.

Ключи задач при переезде сохранились, внутренние id — нет. Задача, которой
нет в новой Jira, без служебных данных сервиса удаляется при применении;
со служебными данными — решает администратор.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.connectors.jql import jql_quote
from app.models import (
    BacklogItem,
    CategoryOverride,
    Issue,
    IssueClassification,
    PlanAudit,
    Project,
    ScenarioAllocationSnapshot,
    ScopeProject,
    ScopeRoot,
    TeamDeskDailyRate,
    TeamDeskMark,
)

CHUNK = 500
PROGRESS_EVERY = 5000
MANUAL_CLASSIFICATION = "manual"
HUMAN_PLAN_AUDIT_SOURCES = (
    "manual_edit", "manual_revert", "conflict_accepted", "conflict_ignored", "dispute_choice",
)

REASON_BACKLOG = "В бэклоге"
REASON_CLASSIFICATION = "Ручная классификация вида работ"
REASON_PLAN_AUDIT = "Правки плановых часов"
REASON_TEAM_DESK_MARK = "Отметки на столе тимлида"
REASON_DAILY_RATE = "Дневная норма на столе тимлида"
REASON_SCENARIO = "В утверждённом сценарии"
REASON_CATEGORY_OVERRIDE = "Исключение категории"
REASON_SCOPE_ROOT = "Корень категории"
REASON_MANUAL_CATEGORY = "Категория задана вручную"
REASON_MANUAL_SUBGROUP = "Группа задана вручную"
REASON_MANUAL_HOURS = "Плановые часы заданы вручную"
REASON_HOURS_CHOICE = "Выбрана оценка в споре"


def chunks(items: Sequence[Any], size: int = CHUNK) -> Iterator[Sequence[Any]]:
    """Порции для ``IN (...)``: SQLite ограничивает число параметров запроса."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def service_data_reasons(db: Session, keys: Sequence[str]) -> dict[str, list[str]]:
    """Служебные данные сервиса по задачам: ``{ключ: [что есть]}``, задачи без данных не попадают.

    Служебные — только то, что завёл человек. Не служебные: значения по
    умолчанию и пометки сервиса (включена в анализ, подтверждена, сменился
    родитель), кэш саммари ИИ, классификация вида работ моделью, записи
    истории оценок от синка — всё это восстанавливается или теряет смысл
    вместе с задачей.
    """
    reasons: dict[str, list[str]] = {}

    def add(key: str, reason: str) -> None:
        bucket = reasons.setdefault(key, [])
        if reason not in bucket:
            bucket.append(reason)

    unique_keys = list(dict.fromkeys(keys))
    for chunk in chunks(unique_keys):
        rows = (
            db.query(
                Issue.id, Issue.key, Issue.assigned_category, Issue.assigned_subgroup_id,
                Issue.planned_analyst_hours_manual, Issue.planned_dev_hours_manual,
                Issue.planned_qa_hours_manual, Issue.planned_opo_hours_manual,
                Issue.planned_hours_choice,
            )
            .filter(Issue.key.in_(chunk))
            .all()
        )
        key_by_id: dict[str, str] = {}
        for row in rows:
            key_by_id[row.id] = row.key
            if row.assigned_category:
                add(row.key, REASON_MANUAL_CATEGORY)
            if row.assigned_subgroup_id:
                add(row.key, REASON_MANUAL_SUBGROUP)
            manual_hours = (
                row.planned_analyst_hours_manual, row.planned_dev_hours_manual,
                row.planned_qa_hours_manual, row.planned_opo_hours_manual,
            )
            if any(value is not None for value in manual_hours):
                add(row.key, REASON_MANUAL_HOURS)
            if row.planned_hours_choice:
                add(row.key, REASON_HOURS_CHOICE)
        ids = list(key_by_id)
        if ids:
            checks = (
                (BacklogItem.issue_id, REASON_BACKLOG, None),
                (IssueClassification.issue_id, REASON_CLASSIFICATION,
                 IssueClassification.prompt_version == MANUAL_CLASSIFICATION),
                (PlanAudit.issue_id, REASON_PLAN_AUDIT, PlanAudit.source.in_(HUMAN_PLAN_AUDIT_SOURCES)),
                (TeamDeskMark.issue_id, REASON_TEAM_DESK_MARK, None),
                (TeamDeskDailyRate.issue_id, REASON_DAILY_RATE, None),
                (ScenarioAllocationSnapshot.issue_id, REASON_SCENARIO, None),
            )
            for column, reason, condition in checks:
                query = db.query(column).filter(column.in_(ids))
                if condition is not None:
                    query = query.filter(condition)
                for (issue_id,) in query.distinct().all():
                    add(key_by_id[issue_id], reason)
        for (key,) in db.query(CategoryOverride.jira_issue_key).filter(
            CategoryOverride.jira_issue_key.in_(chunk)
        ).all():
            add(key, REASON_CATEGORY_OVERRIDE)
        for (key,) in db.query(ScopeRoot.jira_issue_key).filter(
            ScopeRoot.jira_issue_key.in_(chunk)
        ).distinct().all():
            add(key, REASON_SCOPE_ROOT)
    return reasons


def classify_missing(db: Session, missing_keys: Sequence[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Задачи, которых нет в новой Jira: (удаляются сами, нужны решения ``[{key, summary, reasons}]``)."""
    unique_keys = list(dict.fromkeys(missing_keys))
    reasons = service_data_reasons(db, unique_keys)
    with_data_keys = [key for key in unique_keys if key in reasons]
    summaries: dict[str, str] = {}
    for chunk in chunks(with_data_keys):
        for key, summary in db.query(Issue.key, Issue.summary).filter(Issue.key.in_(chunk)).all():
            summaries[key] = summary
    deletable = [key for key in unique_keys if key not in reasons]
    with_data = [
        {"key": key, "summary": summaries.get(key, ""), "reasons": reasons[key]} for key in with_data_keys
    ]
    return deletable, with_data


@dataclass
class IssueScan:
    key_to_id: dict[str, str]   # ключ задачи базы → id в новой Jira
    db_total: int
    matched: int
    new_in_dc: int              # новые задачи проектов из scope — придут синком
    missing: list[str]          # ключи базы, которых нет в найденном проекте новой Jira
    # Проекты базы, которых нет в новой Jira (переименован, нет доступа): их задачи
    # не сверялись и не удаляются — остаются со старыми id, как и сам проект.
    project_not_found: list[dict[str, Any]]   # [{key, issues}]
    projects: list[dict[str, Any]]


async def scan_issue_ids(
    db: Session,
    jira: Any,
    dc_project_ids: Mapping[str, str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> IssueScan:
    """Пары (ключ, id) новой Jira по проектам задач базы и проектам из scope.

    Отсутствующими считаются только задачи проектов, найденных в новой Jira:
    задачи ненайденного проекта уходят в ``project_not_found``. Сбой чтения
    Jira не перехватывается — неполная выдача не должна стать «отсутствием».
    Перед чтением Jira коммитит: транзакция базы не висит открытой, пока
    читаются сотни тысяч ключей.
    """
    db_keys_by_project: dict[str, set[str]] = {}
    for key, project_key in db.query(Issue.key, Project.key).join(Project, Project.id == Issue.project_id).all():
        db_keys_by_project.setdefault(project_key, set()).add(key)
    scope = {
        key for (key,) in db.query(ScopeProject.jira_project_key)
        .filter(ScopeProject.is_enabled.is_(True)).all()
    }
    db.commit()
    all_ids: dict[str, str] = {}
    read = 0
    for project_key in sorted(set(db_keys_by_project) | scope):
        if project_key not in dc_project_ids:
            continue
        async for key, issue_id in jira.iter_issue_keys(f"project = {jql_quote(project_key)}"):
            all_ids[key] = str(issue_id)
            read += 1
            if on_progress is not None and read % PROGRESS_EVERY == 0:
                on_progress(read)
    if on_progress is not None:
        on_progress(read)
    db_keys: set[str] = set().union(*db_keys_by_project.values()) if db_keys_by_project else set()
    checked_keys: set[str] = set()
    project_not_found: list[dict[str, Any]] = []
    for project_key in sorted(db_keys_by_project):
        if project_key in dc_project_ids:
            checked_keys |= db_keys_by_project[project_key]
        else:
            project_not_found.append({"key": project_key, "issues": len(db_keys_by_project[project_key])})
    key_to_id = {key: all_ids[key] for key in db_keys if key in all_ids}
    new_in_dc = sum(1 for key in all_ids if key not in db_keys and key.rsplit("-", 1)[0] in scope)
    project_keys = {key for (key,) in db.query(Project.key).all()} | scope
    return IssueScan(
        key_to_id=key_to_id,
        db_total=len(db_keys),
        matched=len(key_to_id),
        new_in_dc=new_in_dc,
        missing=sorted(checked_keys - set(all_ids)),
        project_not_found=project_not_found,
        projects=[{"key": key, "found": key in dc_project_ids} for key in sorted(project_keys)],
    )
