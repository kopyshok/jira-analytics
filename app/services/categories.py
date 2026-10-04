"""Константы и описания управленческих категорий работ."""

from enum import Enum

from sqlalchemy.orm import Session


class CategoryCode(str, Enum):
    """Коды управленческих категорий работ.

    Соответствуют категориям из документа архитектуры.
    """

    SUPPORT_CONSULTATION = "support_consultation"
    BUSINESS_ANALYSIS = "business_analysis"
    MEETINGS = "meetings"
    ADMIN_LOSSES = "admin_losses"
    INTERNAL_COMMUNICATIONS = "internal_communications"
    TECH_DEBT = "tech_debt"
    UNFILLED_WORKLOG = "unfilled_worklog"


CATEGORY_LABELS: dict[str, str] = {
    CategoryCode.SUPPORT_CONSULTATION: "Сопровождение и консультация",
    CategoryCode.BUSINESS_ANALYSIS: "Анализ/развитие бизнес-процессов",
    CategoryCode.MEETINGS: "Встречи вне развития и консультации",
    CategoryCode.ADMIN_LOSSES: "Административные потери",
    CategoryCode.INTERNAL_COMMUNICATIONS: "Внутренние коммуникации",
    CategoryCode.TECH_DEBT: "Технический долг / прочее",
    CategoryCode.UNFILLED_WORKLOG: "Незаполненные / сомнительные worklog",
}


# Источники правил для category_mappings.source_rule
class MappingSource(str, Enum):
    """Источник присвоения категории."""

    OVERRIDE = "override"          # Явное переопределение (category_overrides)
    SCOPE_ROOT = "scope_root"      # Наследование от корневого эпика
    ASSIGNED = "assigned"          # Явное назначение на задаче (assigned_category)
    QUALITY_RULE = "quality_rule"  # Сработало правило качества worklog
    FALLBACK = "fallback"          # Категория по умолчанию (unfilled)


UNFILLED_WORKLOG_CODE = "unfilled_worklog"


def get_category_labels(db: Session) -> dict[str, str]:
    """Загрузить labels из таблицы categories (fallback на хардкод)."""
    from app.models.category import Category

    rows = db.query(Category).all()
    if rows:
        return {r.code: r.label for r in rows}
    return dict(CATEGORY_LABELS)


def get_category_work_types(db: Session) -> dict[str, str]:
    """Код категории → id вида работ; категории без вида работ не попадают.

    Вид работ списания определяется категорией его задачи (``Issue.category`` —
    уже с наследованием от родителя). Единая карта для дашборда нормированных
    работ и фактической вовлечённости.
    """
    from app.models.category import Category

    rows = (
        db.query(Category.code, Category.work_type_id)
        .filter(Category.work_type_id.isnot(None))
        .all()
    )
    return {code: wt_id for code, wt_id in rows}


def get_category_colors(db: Session) -> dict[str, str]:
    """Загрузить colors из таблицы categories."""
    from app.models.category import Category

    rows = db.query(Category).all()
    return {r.code: r.color for r in rows if r.color}
