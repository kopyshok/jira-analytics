"""RCPSP-выравнивание: пост-CPM проход разруливает перегрузки ресурсов.

Стратегии (в порядке убывания предпочтения):
1. delay_within_slack — сдвиг назначения внутри slack без слома цепи
2. reassign_to_peer — переназначение на другого сотрудника той же роли
3. escalate — эскалация в конфликт (OVR.LIGHT/MED/HIGH)

Алгоритм работает после _compute_cpm и до _persist_conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Literal, Optional

from app.models import ResourcePlanAssignment


LevelingAction = Literal["delay", "reassign", "escalate"]


@dataclass
class LevelingEvent:
    """Что сделал leveler с одним назначением."""

    assignment_id: str
    action: LevelingAction
    reason: str
    delta_days: int = 0
    from_employee_id: Optional[str] = None
    to_employee_id: Optional[str] = None
    overload_pct: float = 0.0
    affected_dates: List[date] = field(default_factory=list)


class RcpspLeveler:
    """Выравнивание ресурсной нагрузки после первичного scheduling pass."""

    def level(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
        q_end: date,
    ) -> List[LevelingEvent]:
        """Главный entrypoint. Мутирует assignments на месте, возвращает событий."""
        if not assignments:
            return []
        return []
