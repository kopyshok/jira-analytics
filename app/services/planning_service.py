"""Хелперы планирования: per-role спрос одной задачи и суммарная ёмкость
команды. Используются в ExportService.

Ранее сервис содержал жадный алгоритм автораскладки `generate_scenario` —
удалён: сценарии теперь формируются вручную отметками в UI.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem
from app.services.allocation_estimates import (
    effective_estimate_hours,
    has_override,
)
from app.services.capacity_service import CapacityService

if TYPE_CHECKING:
    from app.models import ScenarioAllocation


class PlanningService:
    """Тонкий сервис: ёмкость команды и per-role спрос одной задачи."""

    def __init__(self, db: Session):
        self.db = db

    def _team_capacity_hours(self, year: int, quarter: int) -> float:
        """Суммарная per-role ёмкость активной команды за квартал.

        Используется ExportService для шапки scenario.xlsx / pptx.
        """
        caps = CapacityService(self.db).team_role_capacity(year, quarter)
        return sum(caps.values())

    @staticmethod
    def _demand_by_role(item: BacklogItem) -> dict[str, float]:
        """Часы по ролям с учётом ОПЭ-сплита.

        ``opo_analyst_ratio`` дефолт — 0.5 (половина ОПЭ аналитику,
        половина разработке).
        """
        ea = item.estimate_analyst_hours or 0.0
        ed = item.estimate_dev_hours or 0.0
        eq = item.estimate_qa_hours or 0.0
        eo = item.estimate_opo_hours or 0.0
        r = (
            item.opo_analyst_ratio
            if item.opo_analyst_ratio is not None
            else 0.5
        )
        return {
            "analyst": ea + eo * r,
            "dev": ed + eo * (1.0 - r),
            "qa": eq,
        }

    @staticmethod
    def demand_by_role_from_allocation(
        allocation: "ScenarioAllocation",
    ) -> dict[str, float]:
        """Per-role demand: effective оценка + ОПЭ-сплит.

        Старый ``_demand_by_role(BacklogItem)`` оставлен для consumers где
        override на allocation не применим (preview backlog без сценария).
        """
        eff = effective_estimate_hours(allocation)
        bi = allocation.backlog_item
        r = (
            bi.opo_analyst_ratio
            if bi is not None and bi.opo_analyst_ratio is not None
            else 0.5
        )
        return {
            "analyst": eff["analyst"] + eff["opo"] * r,
            "dev": eff["dev"] + eff["opo"] * (1.0 - r),
            "qa": eff["qa"],
        }


def should_skip_in_plan(
    allocation: Any, continuation_info_row: Optional[dict]
) -> bool:
    """Allocation не учитывается в норме если она continuation без override.

    Используется потребителями, которые суммируют allocations в норму.
    """
    if continuation_info_row is None:
        return False
    if not continuation_info_row.get("is_continuation"):
        return False
    return not has_override(allocation)
