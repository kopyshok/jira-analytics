"""Три способа расчёта метрики. Ничего предметного здесь нет — только арифметика."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class MetricResult:
    """Результат расчёта одной метрики для одного человека и периода."""

    value: Optional[float]
    has_data: bool
    numerator: Optional[float] = None
    denominator: Optional[float] = None


def _cap(value: float, cap_at_100: bool) -> float:
    capped = min(value, 100.0) if cap_at_100 else value
    return max(capped, 0.0)


def ratio(numerator: int, denominator: int, invert: bool, cap_at_100: bool) -> MetricResult:
    """Доля одного множества в другом, в процентах."""
    if denominator <= 0:
        return MetricResult(value=None, has_data=False, numerator=numerator, denominator=denominator)
    pct = numerator / denominator * 100.0
    if invert:
        pct = 100.0 - pct
    return MetricResult(
        value=_cap(pct, cap_at_100), has_data=True,
        numerator=numerator, denominator=denominator,
    )


def norm_to_fact(norm: Optional[float], facts: list[float]) -> MetricResult:
    """Норматив к среднему факту. Потолок 100 всегда — превышение норматива не премируется."""
    usable = [f for f in facts if f is not None and f > 0]
    if not norm or not usable:
        return MetricResult(value=None, has_data=False, numerator=norm,
                            denominator=len(usable) or None)
    avg_fact = sum(usable) / len(usable)
    return MetricResult(
        value=_cap(norm / avg_fact * 100.0, True), has_data=True,
        numerator=norm, denominator=avg_fact,
    )


def score_to_max(scores: list[list[float]], score_max: float) -> MetricResult:
    """Средний балл к максимуму. Каждая задача даёт среднее своих оценок."""
    per_issue = []
    for row in scores:
        usable = [x for x in row if x is not None]
        if usable:
            per_issue.append(sum(usable) / len(usable))
    if not per_issue or not score_max:
        return MetricResult(value=None, has_data=False)
    avg = sum(per_issue) / len(per_issue)
    return MetricResult(
        value=_cap(avg / score_max * 100.0, True), has_data=True,
        numerator=avg, denominator=score_max,
    )
