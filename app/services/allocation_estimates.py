"""Effective per-role часы allocation: override если задан, иначе BacklogItem."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import ScenarioAllocation


_OVERRIDE_FIELDS = (
    "override_estimate_analyst_hours",
    "override_estimate_dev_hours",
    "override_estimate_qa_hours",
    "override_estimate_opo_hours",
)


def has_override(allocation: "ScenarioAllocation") -> bool:
    """True если хотя бы одно из 4 override-полей не NULL."""
    return any(getattr(allocation, f) is not None for f in _OVERRIDE_FIELDS)


def effective_estimate_hours(allocation: "ScenarioAllocation") -> dict[str, float]:
    """Per-role часы allocation: override приоритетнее BacklogItem.

    Правило inherit:
      - has_override(allocation) is True  → берём 4 цифры из override (NULL → 0.0)
      - has_override(allocation) is False → берём из allocation.backlog_item.estimate_*
    """
    if has_override(allocation):
        return {
            "analyst": float(allocation.override_estimate_analyst_hours or 0.0),
            "dev": float(allocation.override_estimate_dev_hours or 0.0),
            "qa": float(allocation.override_estimate_qa_hours or 0.0),
            "opo": float(allocation.override_estimate_opo_hours or 0.0),
        }
    bi = allocation.backlog_item
    return {
        "analyst": float(getattr(bi, "estimate_analyst_hours", 0) or 0.0),
        "dev": float(getattr(bi, "estimate_dev_hours", 0) or 0.0),
        "qa": float(getattr(bi, "estimate_qa_hours", 0) or 0.0),
        "opo": float(getattr(bi, "estimate_opo_hours", 0) or 0.0),
    }
