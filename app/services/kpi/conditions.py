"""Трансляция условий отбора KPI в запросы SQLAlchemy.

Условия хранятся в метрике как JSON. Ни одно условие не зашито в код расчёта —
здесь только словарь допустимых атрибутов и способ их сравнения. Словарь
``ATTRIBUTE_CHOICES`` предназначен для выдачи наружу (выпадающие списки
интерфейса настроек, Фаза 4) — держать его в актуальном состоянии при
добавлении новых атрибутов.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Query, Session, aliased

from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.project import Project

# Атрибут условия → колонка задачи
ATTR_COLUMNS = {
    "issue_type": Issue.issue_type,
    "subtype": Issue.subtype,
    "status": Issue.status,
    "resolution": Issue.resolution,
    "environment": Issue.environment,
    "cost_type": Issue.cost_type,
    "direction": Issue.direction,
    "category": Issue.category,
}

# Поля, заполненность которых можно проверять
FILLABLE_FIELDS = {
    "goal_text": Issue.goal_text,
    "current_behavior": Issue.current_behavior,
    "description": Issue.description,
    "goals": Issue.goals,
}

PERSON_FIELDS = {"author", "assignee", "linked_issue_author", "worklog_author"}
PERIOD_WINDOWS = {"closed_in", "created_and_closed_in"}

# Словарь допустимых атрибутов условий — источник истины для выпадающих
# списков конструктора метрики в настройках (Фаза 4). Единственное место в
# коде, где предметная специфика (какие атрибуты вообще бывают) зашита явно —
# сами значения условий («какой проект», «какой статус» и т. п.) остаются
# данными в справочнике метрик.
ATTRIBUTE_CHOICES: list[dict] = [
    {"key": "project_key", "label": "Проект", "value_type": "list"},
    {"key": "issue_type", "label": "Тип задачи", "value_type": "list"},
    {"key": "subtype", "label": "Подтип", "value_type": "list"},
    {"key": "status", "label": "Статус", "value_type": "list"},
    {"key": "resolution", "label": "Резолюция", "value_type": "list"},
    {"key": "environment", "label": "Окружение", "value_type": "list"},
    {"key": "cost_type", "label": "Тип затрат", "value_type": "list"},
    {"key": "direction", "label": "Продуктовое направление", "value_type": "list"},
    {"key": "field_filled", "label": "Поле заполнено", "value_type": "list"},
    {"key": "resolved_on_time", "label": "Резолюция не позже плановой даты", "value_type": "none"},
    {"key": "has_linked_bug", "label": "Есть связанный баг", "value_type": "none"},
]


@dataclass
class Condition:
    """Одно условие отбора: атрибут, сравнение, значение."""

    attr: str
    op: str
    value: object = None


@dataclass
class ConditionSet:
    """Набор условий отбора одной стороны метрики (числителя или знаменателя)."""

    unit: str = "issues"
    person_field: str = "author"
    period_window: str = "closed_in"
    conditions: list[Condition] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "ConditionSet":
        """Разобрать набор условий из JSON, хранящегося в метрике."""
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(
            unit=data.get("unit", "issues"),
            person_field=data.get("person_field", "author"),
            period_window=data.get("period_window", "closed_in"),
            conditions=[
                Condition(attr=c["attr"], op=c.get("op", "in"), value=c.get("value"))
                for c in data.get("conditions", [])
            ],
        )


def _apply_condition(clauses: list, cond: Condition) -> None:
    """Одно условие → предикат. Неизвестный атрибут молча пропускается."""
    if cond.attr == "project_key":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        sub = select(Project.id).where(Project.key.in_(values))
        clauses.append(
            Issue.project_id.in_(sub) if cond.op != "not_in"
            else ~Issue.project_id.in_(sub)
        )
        return

    if cond.attr == "field_filled":
        names = cond.value if isinstance(cond.value, list) else [cond.value]
        for name in names:
            col = FILLABLE_FIELDS.get(str(name))
            if col is None:
                continue
            clauses.append(and_(col.isnot(None), col != ""))
        return

    if cond.attr == "resolved_on_time":
        clauses.append(
            and_(
                Issue.resolved_at.isnot(None),
                Issue.planned_end_date.isnot(None),
                Issue.resolved_at <= Issue.planned_end_date,
            )
        )
        return

    if cond.attr == "has_linked_bug":
        linked = aliased(Issue)
        sub = (
            select(IssueLink.target_issue_id)
            .join(linked, linked.id == IssueLink.source_issue_id)
            .where(linked.issue_type == "Баг")
        )
        clauses.append(Issue.id.in_(sub))
        return

    col = ATTR_COLUMNS.get(cond.attr)
    if col is None:
        return
    if cond.op == "in":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        clauses.append(col.in_(values))
    elif cond.op == "not_in":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        clauses.append(~col.in_(values))
    elif cond.op == "eq":
        clauses.append(col == cond.value)
    elif cond.op == "ne":
        clauses.append(col != cond.value)


def _person_clause(cs: ConditionSet, account_id: str):
    """Как задача связана с оцениваемым человеком."""
    if cs.person_field == "assignee":
        return Issue.assignee_account_id == account_id
    if cs.person_field == "linked_issue_author":
        linked = aliased(Issue)
        sub = (
            select(IssueLink.source_issue_id)
            .join(linked, linked.id == IssueLink.target_issue_id)
            .where(linked.reporter_account_id == account_id)
        )
        return Issue.id.in_(sub)
    return Issue.reporter_account_id == account_id


def _period_clause(cs: ConditionSet, period_start: date, period_end: date):
    """Задача закрыта в периоде, а для окна ``created_and_closed_in`` — ещё и создана в нём.

    Создана в Jira проверяется по ``jira_created_at`` — дате создания в Jira,
    а не по ``created_at`` (дате вставки строки в нашу базу).
    """
    start = datetime.combine(period_start, datetime.min.time())
    end = datetime.combine(period_end, datetime.max.time())
    closed = and_(Issue.resolved_at.isnot(None), Issue.resolved_at.between(start, end))
    if cs.period_window == "created_and_closed_in":
        return and_(closed, Issue.jira_created_at.between(start, end))
    return closed


def build_issue_query(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    period_start: date,
    period_end: date,
    excluded_statuses: list[str],
    teams: Optional[list[str]],
) -> Query:
    """Запрос задач, попадающих под набор условий, для одного человека и периода."""
    clauses = [_person_clause(cs, account_id), _period_clause(cs, period_start, period_end)]
    for cond in cs.conditions:
        _apply_condition(clauses, cond)
    if excluded_statuses:
        clauses.append(or_(Issue.status.is_(None), ~Issue.status.in_(excluded_statuses)))
    if teams:
        clauses.append(Issue.team.in_(teams))
    return db.query(Issue).filter(and_(*clauses))
