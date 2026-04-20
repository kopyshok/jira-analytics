"""Сервис квартального планирования (v2, per-role).

Жадная раскладка элементов бэклога по приоритету с учётом
доступной ёмкости команды **по ролям** (analyst / dev / qa).

Алгоритм:
1. Берём все `BacklogItem` для заданного (year, quarter) — либо
   явный список id, если передан.
2. Считаем ёмкость команды через
   `CapacityService.team_role_capacity(year, quarter)` — словарь
   `{analyst, dev, qa}`.
3. Сортируем элементы: priority ASC (None в конец) → estimate_hours ASC
   → title.
4. Для каждого элемента считаем per-role demand:
       analyst = estimate_analyst_hours + estimate_opo_hours × ratio
       dev     = estimate_dev_hours     + estimate_opo_hours × (1-ratio)
       qa      = estimate_qa_hours
   где ``ratio = opo_analyst_ratio`` (дефолт 0.5 если None).
5. Item fits, если **все три** `remaining[role] ≥ demand[role]`. Если да —
   включаем (included=True, planned_hours=estimate_hours), вычитаем
   demand из remaining. Иначе — пропускаем.
6. Сохраняем `PlanningScenario` + `ScenarioAllocation` для всех
   рассмотренных элементов.

Reasons:
- ``fit``             — всё уместилось;
- ``no_estimate``     — у item ``estimate_hours <= 0`` И все per-role
                        оценки/ОПЭ тоже 0 (нет осмысленного спроса);
- ``no_capacity_left``— спрос есть, но хотя бы одна роль переполнена.

Сервис коммитит внутри себя, поэтому тесты должны чистить таблицы
после каждого прогона (см. conftest.py).
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
from app.services.capacity_service import CapacityService, ROLE_WHITELIST


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
    capacity_by_role: dict[str, float] = field(default_factory=dict)
    planned_by_role: dict[str, float] = field(default_factory=dict)
    leftover_by_role: dict[str, float] = field(default_factory=dict)
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

    @staticmethod
    def _normalize_quarter(quarter) -> tuple[int, str]:
        """Принимает int 1..4 или "Q1".."Q4"; возвращает (int, "Qn")."""
        if isinstance(quarter, str):
            raw = quarter.strip().upper()
            if raw.startswith("Q"):
                raw = raw[1:]
            try:
                q_int = int(raw)
            except ValueError as exc:
                raise ValueError(f"Quarter must be 1..4, got {quarter!r}") from exc
        else:
            q_int = int(quarter)
        if q_int not in (1, 2, 3, 4):
            raise ValueError(f"Quarter must be 1..4, got {quarter}")
        return q_int, f"Q{q_int}"

    # === Main ===

    def generate_scenario(
        self,
        name: str,
        year: int,
        quarter,
        backlog_item_ids: Optional[list[str]] = None,
    ) -> PlanningResult:
        """Сгенерировать новый сценарий методом жадной раскладки per-role.

        Args:
            name: название сценария (для отображения).
            year: календарный год.
            quarter: номер квартала 1..4 или строка "Q1".."Q4".
            backlog_item_ids: опциональный явный список id элементов
                бэклога. Если не задан — берутся все элементы с
                соответствующими year и ``quarter = "Q{quarter}"``.
        """
        q_int, q_str = self._normalize_quarter(quarter)

        capacity = CapacityService(self.db).team_role_capacity(year, q_int)
        remaining = dict(capacity)
        total_capacity = sum(capacity.values())

        items = self._load_backlog(year, q_str, backlog_item_ids)
        items.sort(key=self._sort_key)

        scenario = PlanningScenario(
            name=name,
            year=year,
            quarter=q_str,
        )
        self.db.add(scenario)
        self.db.flush()

        allocations: list[AllocationEntry] = []
        total_planned = 0.0
        planned_by_role: dict[str, float] = {r: 0.0 for r in ROLE_WHITELIST}

        for item in items:
            demand = self._demand_by_role(item)
            demand_total = sum(demand.values())
            estimate = item.estimate_hours or 0.0

            if demand_total <= 0 and estimate <= 0:
                included = False
                planned = 0.0
                reason = "no_estimate"
            elif all(
                remaining.get(r, 0.0) + 1e-9 >= h for r, h in demand.items()
            ):
                included = True
                planned = estimate if estimate > 0 else demand_total
                for r, h in demand.items():
                    remaining[r] -= h
                    planned_by_role[r] += h
                total_planned += planned
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

        leftover_by_role = {r: max(0.0, remaining[r]) for r in ROLE_WHITELIST}

        return PlanningResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            year=year,
            quarter=q_int,
            total_capacity_hours=total_capacity,
            total_planned_hours=total_planned,
            leftover_capacity_hours=sum(leftover_by_role.values()),
            capacity_by_role=capacity,
            planned_by_role=planned_by_role,
            leftover_by_role=leftover_by_role,
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
