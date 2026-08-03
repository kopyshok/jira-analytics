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

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Query, Session, aliased

from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.project import Project


class ConditionError(ValueError):
    """Условие метрики ссылается на неизвестный атрибут, сравнение или значение.

    От раздела KPI считают премии, поэтому опечатка в настройке метрики не
    должна тихо ослаблять фильтр (пропуская условие) — она обязана
    провалить сохранение или расчёт понятным сообщением на русском.
    """

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

# Числовые поля задачи, пригодные как «факт» метрики «норматив к факту»
# (конструктор метрики в настройках, см. ревью, BLOCKER 4). Список сознательно
# закрытый — движок расчёта берёт значение через ``getattr`` по этому же имени
# (``kpi_service.fact_field_name``), поэтому опечатка в имени поля должна
# провалить сохранение метрики понятной ошибкой, а не тихо считать «нет данных»
# на каждом расчёте.
NUMERIC_FACT_FIELDS = {
    "cycle_time_fact": "Фактический Cycle Time",
}

PERSON_FIELDS = {"author", "assignee", "linked_issue_author", "worklog_author"}
PERIOD_WINDOWS = {"closed_in", "created_and_closed_in"}
UNITS = {"issues", "worklogs"}

# Атрибуты, не завязанные на конкретную колонку (обработка в _apply_condition),
# плюс всё из ATTR_COLUMNS — вместе полный список допустимых значений `attr`.
KNOWN_ATTRS = {"project_key", "field_filled", "resolved_on_time", "has_linked_bug", *ATTR_COLUMNS}
KNOWN_OPS = {"in", "not_in", "eq", "ne", "all", "is_true"}

# Словарь допустимых атрибутов условий — источник истины для выпадающих
# списков конструктора метрики в настройках (Фаза 4). Единственное место в
# коде, где предметная специфика (какие атрибуты вообще бывают) зашита явно —
# сами значения условий («какой проект», «какой статус» и т. п.) остаются
# данными в справочнике метрик.
#
# Продуктового направления здесь нет: по дизайну (спека, раздел 6) оно —
# фильтр отчёта (см. ``with_direction``), а не часть условия метрики. Если
# позволить зашить его в саму метрику, переключатель направления на ведомости
# молча перестанет действовать на такую метрику. Колонка при этом остаётся в
# ``ATTR_COLUMNS`` — ей пользуется ``with_direction``.
ATTRIBUTE_CHOICES: list[dict] = [
    {"key": "project_key", "label": "Проект", "value_type": "list"},
    {"key": "issue_type", "label": "Тип задачи", "value_type": "list"},
    {"key": "subtype", "label": "Подтип", "value_type": "list"},
    {"key": "status", "label": "Статус", "value_type": "list"},
    {"key": "resolution", "label": "Резолюция", "value_type": "list"},
    {"key": "environment", "label": "Окружение", "value_type": "list"},
    {"key": "cost_type", "label": "Тип затрат", "value_type": "list"},
    {"key": "category", "label": "Категория", "value_type": "list"},
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


def _validate_condition(cond: Condition) -> None:
    """Проверить одно условие на опечатки в атрибуте/сравнении/имени поля.

    Вызывается при разборе JSON (``ConditionSet.from_json``) — то есть и при
    сохранении метрики в настройках, и при каждом расчёте, читающем уже
    сохранённые данные.
    """
    if cond.attr not in KNOWN_ATTRS:
        raise ConditionError(f"Неизвестный атрибут условия: {cond.attr!r}")
    if cond.op not in KNOWN_OPS:
        raise ConditionError(f"Неизвестное сравнение {cond.op!r} для атрибута {cond.attr!r}")
    if cond.attr == "field_filled":
        names = cond.value if isinstance(cond.value, list) else [cond.value]
        for name in names:
            if str(name) not in FILLABLE_FIELDS:
                raise ConditionError(f"Неизвестное поле для проверки заполненности: {name!r}")


@dataclass
class ConditionSet:
    """Набор условий отбора одной стороны метрики (числителя или знаменателя)."""

    unit: str = "issues"
    person_field: str = "author"
    period_window: str = "closed_in"
    conditions: list[Condition] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "ConditionSet":
        """Разобрать набор условий из JSON, хранящегося в метрике.

        Падает с ``ConditionError`` на любой опечатке (неизвестный атрибут,
        сравнение, признак «кто считается», окно периода, единица счёта или
        имя поля в проверке заполненности) — тихое ослабление фильтра для
        раздела, по которому считают премии, недопустимо (см. ревью Фазы 3).
        """
        if not raw:
            return cls()
        data = json.loads(raw)

        unit = data.get("unit", "issues")
        if unit not in UNITS:
            raise ConditionError(f"Неизвестная единица счёта: {unit!r}")
        person_field = data.get("person_field", "author")
        if person_field not in PERSON_FIELDS:
            raise ConditionError(f"Неизвестный признак «кто считается»: {person_field!r}")
        period_window = data.get("period_window", "closed_in")
        if period_window not in PERIOD_WINDOWS:
            raise ConditionError(f"Неизвестное окно периода: {period_window!r}")

        conditions = [
            Condition(attr=c["attr"], op=c.get("op", "in"), value=c.get("value"))
            for c in data.get("conditions", [])
        ]
        for cond in conditions:
            _validate_condition(cond)

        return cls(unit=unit, person_field=person_field, period_window=period_window,
                   conditions=conditions)


def _apply_condition(clauses: list, cond: Condition) -> None:
    """Одно условие → предикат.

    К моменту вызова атрибут/сравнение/имя поля уже проверены в
    ``ConditionSet.from_json`` — здесь только перевод в SQL. Фолбэки на
    неизвестный атрибут ниже — защита на случай прямого конструирования
    ``Condition`` в обход ``from_json``, а не штатный путь.
    """
    if cond.attr == "project_key":
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        sub = select(Project.id).where(Project.key.in_(values))
        clauses.append(
            Issue.project_id.in_(sub) if cond.op != "not_in"
            else ~Issue.project_id.in_(sub)
        )
        return

    if cond.attr == "field_filled":
        # Поле из одних пробелов/переводов строк — не заполнение (ВАЖНО 4).
        # func.trim() в SQLite снимает только пробелы по краям, поэтому
        # переводы строк/табуляция сначала схлопываются в пробел.
        names = cond.value if isinstance(cond.value, list) else [cond.value]
        for name in names:
            col = FILLABLE_FIELDS.get(str(name))
            if col is None:
                continue
            normalized = func.trim(
                func.replace(func.replace(col, "\n", " "), "\t", " ")
            )
            clauses.append(and_(col.isnot(None), normalized != ""))
        return

    if cond.attr == "resolved_on_time":
        # Плановая дата из Jira лежит полночью, дата резолюции — полный
        # момент времени. Сравнивать нужно календарные даты, а не моменты —
        # иначе задача, закрытая в день плана вечером, ложно числится
        # просроченной (BLOCKER 1 ревью Фазы 3).
        clauses.append(
            and_(
                Issue.resolved_at.isnot(None),
                Issue.planned_end_date.isnot(None),
                func.date(Issue.resolved_at) <= func.date(Issue.planned_end_date),
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
        # Пустое значение колонки — не "входит" ни в один список, поэтому
        # исключать его вместе с явно перечисленными значениями нельзя:
        # задача без направления/подтипа/типа затрат иначе выпадает из
        # выборки, хотя условие говорит только про конкретные значения.
        values = cond.value if isinstance(cond.value, list) else [cond.value]
        clauses.append(or_(col.is_(None), ~col.in_(values)))
    elif cond.op == "eq":
        clauses.append(col == cond.value)
    elif cond.op == "ne":
        clauses.append(or_(col.is_(None), col != cond.value))


def _person_clause(cs: ConditionSet, account_id: str):
    """Как задача связана с оцениваемым человеком."""
    return person_clause(cs, [account_id])


def person_clause(cs: ConditionSet, account_ids: list[str]):
    """Как задача связана с кем-то из перечисленных людей.

    Список нужен предпросмотру метрики: воронка отбора считается сразу по
    всей команде, а не по одному человеку (см. ``preview.py``). Расчёт
    отчёта передаёт список из одного элемента.
    """
    if cs.person_field == "assignee":
        return Issue.assignee_account_id.in_(account_ids)
    if cs.person_field == "linked_issue_author":
        linked = aliased(Issue)
        sub = (
            select(IssueLink.source_issue_id)
            .join(linked, linked.id == IssueLink.target_issue_id)
            .where(linked.reporter_account_id.in_(account_ids))
        )
        return Issue.id.in_(sub)
    return Issue.reporter_account_id.in_(account_ids)


def condition_clauses(cond: Condition) -> list:
    """Предикаты одного условия — по отдельности, для пошаговой воронки отбора.

    ``build_issue_query`` склеивает все условия сразу; предпросмотру нужно
    добавлять их по одному и считать остаток после каждого шага.
    """
    clauses: list = []
    _apply_condition(clauses, cond)
    return clauses


_ATTR_LABELS = {c["key"]: c["label"] for c in ATTRIBUTE_CHOICES}
_OP_LABELS = {
    "in": "из списка", "not_in": "не из списка", "eq": "равно", "ne": "не равно",
    "all": "все", "is_true": "да",
}
_PERSON_LABELS = {
    "author": "автор задачи",
    "assignee": "исполнитель задачи",
    "linked_issue_author": "автор связанной задачи",
    "worklog_author": "автор записи о часах",
}
_PERIOD_LABELS = {
    "closed_in": "задача закрыта в периоде",
    "created_and_closed_in": "задача создана и закрыта в периоде",
}


def describe_condition(cond: Condition) -> str:
    """Условие человеческими словами — подпись шага воронки отбора."""
    label = _ATTR_LABELS.get(cond.attr, cond.attr)
    if cond.attr == "field_filled":
        names = cond.value if isinstance(cond.value, list) else [cond.value]
        return f"Заполнены поля: {', '.join(str(n) for n in names)}"
    if cond.op in {"all", "is_true"} or cond.value is None:
        return label
    values = cond.value if isinstance(cond.value, list) else [cond.value]
    return f"{label} {_OP_LABELS.get(cond.op, cond.op)}: {', '.join(str(v) for v in values)}"


def describe_person(person_field: str) -> str:
    """Признак «кто считается» человеческими словами."""
    return _PERSON_LABELS.get(person_field, person_field)


def describe_period(period_window: str) -> str:
    """Окно периода человеческими словами."""
    return _PERIOD_LABELS.get(period_window, period_window)


def _one_period_clause(cs: ConditionSet, period_start: date, period_end: date):
    """Задача закрыта в одном конкретном периоде, а для окна ``created_and_closed_in`` —
    ещё и создана в нём.

    Создана в Jira проверяется по ``jira_created_at`` — дате создания в Jira,
    а не по ``created_at`` (дате вставки строки в нашу базу).
    """
    start = datetime.combine(period_start, datetime.min.time())
    end = datetime.combine(period_end, datetime.max.time())
    closed = and_(Issue.resolved_at.isnot(None), Issue.resolved_at.between(start, end))
    if cs.period_window == "created_and_closed_in":
        return and_(closed, Issue.jira_created_at.between(start, end))
    return closed


def _period_clause(cs: ConditionSet, periods: list[tuple[date, date]]):
    """Задача закрыта хотя бы в одном из периодов.

    Несколько периодов — фактические отрезки участия сотрудника в команде
    внутри месяца (ушёл — вернулся): считать по ним отдельно, а не по
    объединяющему диапазону от первого до последнего дня, иначе разрыв
    (например, 5-25 числа) молча превращается в «состоял весь месяц»
    (см. ревью Фазы 3, мелочь про интервалы).
    """
    return or_(*[_one_period_clause(cs, start, end) for start, end in periods])


def period_clause(cs: ConditionSet, periods: list[tuple[date, date]]):
    """Окно периода как отдельный предикат — нужен воронке отбора предпросмотра."""
    return _period_clause(cs, periods)


def issue_attribute_clauses(
    cs: ConditionSet, excluded_statuses: list[str], teams: Optional[list[str]],
) -> list:
    """Условия отбора задач по атрибутам, статусам и команде — без периода и без человека.

    Период для unit=«worklogs» проверяется по дате самой записи
    (``Worklog.started_at``), а не по дате закрытия задачи, а «кто
    считается» — по автору записи, а не по атрибуту задачи. Поэтому
    своевременность трудозатрат переиспользует именно эту часть транслятора
    (см. ``worklog_items`` в ``kpi_service.py``, ВАЖНО 5 ревью Фазы 3), а не
    весь ``build_issue_query`` целиком.
    """
    clauses: list = []
    for cond in cs.conditions:
        _apply_condition(clauses, cond)
    if excluded_statuses:
        clauses.append(or_(Issue.status.is_(None), ~Issue.status.in_(excluded_statuses)))
    if teams:
        clauses.append(Issue.team.in_(teams))
    return clauses


def build_issue_query(
    db: Session,
    cs: ConditionSet,
    account_id: str,
    periods: list[tuple[date, date]],
    excluded_statuses: list[str],
    teams: Optional[list[str]],
) -> Query:
    """Запрос задач, попадающих под набор условий, для одного человека и периода(ов)."""
    clauses = [
        _person_clause(cs, account_id),
        _period_clause(cs, periods),
        *issue_attribute_clauses(cs, excluded_statuses, teams),
    ]
    return db.query(Issue).filter(and_(*clauses))
