"""Константы и описания управленческих категорий работ."""

from enum import Enum


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
    QUALITY_RULE = "quality_rule"  # Сработало правило качества worklog
    FALLBACK = "fallback"          # Категория по умолчанию (unfilled)
