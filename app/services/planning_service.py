"""Хелперы планирования: per-role спрос одной задачи и суммарная ёмкость
команды. Используются в `/planning/capacity-preview` и ExportService.

Ранее сервис содержал жадный алгоритм автораскладки `generate_scenario` —
удалён: сценарии теперь формируются вручную отметками в UI.
"""

from sqlalchemy.orm import Session

from app.models import BacklogItem
from app.services.capacity_service import CapacityService


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
