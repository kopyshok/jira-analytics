"""Сервис квартального планирования.

Жадная раскладка элементов бэклога по приоритету с учётом
доступной ёмкости команды за квартал.

Алгоритм:
1. Берём все `BacklogItem` для заданного (year, quarter) — либо
   явный список id, если передан.
2. Считаем ёмкость команды = сумма `available_hours` по всем активным
   сотрудникам за квартал через `CapacityService.team_quarter_capacity`.
3. Сортируем элементы по приоритету (меньше = важнее; `None` в конец),
   с тайбрейком по `estimate_hours` (меньше раньше) и `title`.
4. По очереди пытаемся «упаковать» каждую задачу целиком в оставшуюся
   ёмкость. Если помещается — включаем (included_flag=True,
   planned_hours=estimate_hours), уменьшаем остаток. Иначе — пропускаем
   (included_flag=False, planned_hours=0).
5. Сохраняем `PlanningScenario` + `ScenarioAllocation` для всех
   рассмотренных элементов (как включённых, так и пропущенных).

Задачи без `estimate_hours` или с `estimate_hours <= 0` не могут быть
упакованы и отмечаются как пропущенные. Это намеренно: без оценки
сервис не принимает решение «на глаз».

Сервис коммитит внутри себя, поэтому тесты должны чистить таблицы
после каждого прогона (см. conftest.py).
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
from app.services.capacity_service import CapacityService


@dataclass
class AllocationEntry:
    """Результат раскладки одной задачи."""

    backlog_item_id: str
    title: str
    priority: Optional[int]
    estimate_hours: float
    planned_hours: float
    included: bool
    reason: str  # "fit", "no_estimate", "no_capacity_left"


@dataclass
class PlanningResult:
    """Итог генерации сценария."""

    scenario_id: str
    scenario_name: str
    year: int
    quarter: int
    total_capacity_hours: float
    total_planned_hours: float
    leftover_capacity_hours: float
    allocations: list[AllocationEntry] = field(default_factory=list)

    @property
    def included_count(self) -> int:
        return sum(1 for a in self.allocations if a.included)

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.allocations if not a.included)


class PlanningService:
    """Сервис генерации сценариев квартального планирования."""

    def __init__(self, db: Session):
        self.db = db

    # === Helpers ===

    def _team_capacity_hours(self, year: int, quarter: int) -> float:
        """Суммарная доступная ёмкость активной команды за квартал."""
        capacity = CapacityService(self.db).team_quarter_capacity(year, quarter)
        return sum(q.total_available_hours for q in capacity)

    def _load_backlog(
        self,
        year: int,
        quarter: str,
        backlog_item_ids: Optional[list[str]],
    ) -> list[BacklogItem]:
        """Загрузить кандидатов бэклога.

        Если `backlog_item_ids` передан — используем их буквально.
        Иначе — все `BacklogItem` с совпадающими year + quarter.
        """
        if backlog_item_ids:
            query = self.db.query(BacklogItem).filter(
                BacklogItem.id.in_(backlog_item_ids)
            )
        else:
            query = self.db.query(BacklogItem).filter(
                BacklogItem.year == year,
                BacklogItem.quarter == quarter,
            )
        return list(query.all())

    @staticmethod
    def _sort_key(item: BacklogItem) -> tuple:
        return (
            item.priority is None,
            item.priority if item.priority is not None else 0,
            item.estimate_hours if item.estimate_hours is not None else 0.0,
            item.title or "",
        )

    # === Main ===

    def generate_scenario(
        self,
        name: str,
        year: int,
        quarter: int,
        backlog_item_ids: Optional[list[str]] = None,
    ) -> PlanningResult:
        """Сгенерировать новый сценарий методом жадной раскладки.

        Args:
            name: название сценария (для отображения).
            year: календарный год.
            quarter: номер квартала 1..4.
            backlog_item_ids: опциональный явный список id элементов
                бэклога. Если не задан — берутся все элементы с
                соответствующими year и ``quarter = "Q{quarter}"``.
        """
        if quarter not in (1, 2, 3, 4):
            raise ValueError(f"Quarter must be 1..4, got {quarter}")

        quarter_tag = f"Q{quarter}"
        total_capacity = self._team_capacity_hours(year, quarter)
        remaining = total_capacity

        items = self._load_backlog(year, quarter_tag, backlog_item_ids)
        items.sort(key=self._sort_key)

        scenario = PlanningScenario(
            name=name,
            year=year,
            quarter=quarter_tag,
        )
        self.db.add(scenario)
        self.db.flush()

        allocations: list[AllocationEntry] = []
        total_planned = 0.0

        for item in items:
            estimate = item.estimate_hours or 0.0

            if estimate <= 0:
                included = False
                planned = 0.0
                reason = "no_estimate"
            elif estimate <= remaining + 1e-9:
                included = True
                planned = estimate
                remaining -= estimate
                total_planned += estimate
                reason = "fit"
            else:
                included = False
                planned = 0.0
                reason = "no_capacity_left"

            self.db.add(
                ScenarioAllocation(
                    scenario_id=scenario.id,
                    backlog_item_id=item.id,
                    planned_hours=planned,
                    included_flag=included,
                )
            )
            allocations.append(
                AllocationEntry(
                    backlog_item_id=item.id,
                    title=item.title,
                    priority=item.priority,
                    estimate_hours=estimate,
                    planned_hours=planned,
                    included=included,
                    reason=reason,
                )
            )

        self.db.commit()
        self.db.refresh(scenario)

        return PlanningResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            year=year,
            quarter=quarter,
            total_capacity_hours=total_capacity,
            total_planned_hours=total_planned,
            leftover_capacity_hours=max(0.0, remaining),
            allocations=allocations,
        )

    # === Inspection ===

    def get_scenario_allocations(
        self, scenario_id: str
    ) -> list[ScenarioAllocation]:
        """Получить все ScenarioAllocation для сценария."""
        return list(
            self.db.query(ScenarioAllocation)
            .filter(ScenarioAllocation.scenario_id == scenario_id)
            .all()
        )
