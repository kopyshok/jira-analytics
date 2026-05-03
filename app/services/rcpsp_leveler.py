"""RCPSP-выравнивание: пост-CPM проход разруливает перегрузки ресурсов.

Стратегии (в порядке убывания предпочтения):
1. delay_within_slack — сдвиг назначения внутри slack без слома цепи
2. reassign_to_peer — переназначение на другого сотрудника той же роли
3. escalate — эскалация в конфликт (OVR.LIGHT/MED/HIGH)

Алгоритм работает после _compute_cpm и до _persist_conflicts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional, Tuple

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
        events: List[LevelingEvent] = []
        max_passes = 10
        for _ in range(max_passes):
            overloads = self._detect_overload(assignments, availability)
            if not overloads:
                break

            # Выбрать assignment с max slack для сдвига (наиболее «безопасный»)
            target_day, target_emp = next(iter(overloads.keys()))
            candidates = [
                a
                for a in assignments
                if a.employee_id == target_emp
                and a.start_date
                and a.end_date
                and a.start_date <= target_day <= a.end_date
            ]
            if not candidates:
                break
            # Оставить только те, у кого есть slack для сдвига (slack > 0)
            movable = [a for a in candidates if (a.slack_days or 0.0) > 0]
            if not movable:
                break
            # Выбрать кандидата с минимальным slack (наиболее ограниченный, но подвижный)
            movable.sort(key=lambda a: a.slack_days or 0.0)
            target = movable[0]
            shift = 1
            applied = False
            while shift <= int(target.slack_days or 0):
                if self._try_delay(target, shift, availability, q_end):
                    events.append(
                        LevelingEvent(
                            assignment_id=target.id,
                            action="delay",
                            reason=f"Сдвинут на {shift} д. для разрешения перегрузки {target_emp} {target_day}",
                            delta_days=shift,
                            overload_pct=(
                                overloads[(target_day, target_emp)]
                                / max(
                                    0.01,
                                    availability.get(target_emp, {}).get(
                                        target_day, 0.0
                                    ),
                                )
                            )
                            * 100,
                            affected_dates=[target_day],
                        )
                    )
                    applied = True
                    break
                shift += 1
            if not applied:
                # Не смогли сдвинуть — эскалация (Task A.5)
                break
        return events

    def _try_delay(
        self,
        assignment: ResourcePlanAssignment,
        delta_days: int,
        availability: Dict[str, Dict[date, float]],
        q_end: date,
    ) -> bool:
        """Сдвинуть assignment на delta_days вперёд, если позволяет slack и доступность.

        Возвращает True если сдвиг применён.
        """
        if not assignment.start_date or not assignment.end_date:
            return False
        slack = assignment.slack_days or 0.0
        if delta_days > slack:
            return False
        new_start = assignment.start_date + timedelta(days=delta_days)
        new_end = assignment.end_date + timedelta(days=delta_days)
        if new_end > q_end:
            return False
        # Проверить что новые даты доступны (не нулевая availability)
        emp = assignment.employee_id
        if emp:
            d = new_start
            while d <= new_end:
                if availability.get(emp, {}).get(d, 0.0) <= 0.01:
                    return False
                d += timedelta(days=1)
        assignment.start_date = new_start
        assignment.end_date = new_end
        assignment.slack_days = max(0.0, slack - delta_days)
        return True

    def _detect_overload(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
    ) -> Dict[Tuple[date, str], float]:
        """Возвращает {(date, employee_id): demand_hours} там где demand > available.

        Demand на день = hours_allocated, распределённые равномерно по дням сегмента.
        """
        demand: Dict[Tuple[date, str], float] = defaultdict(float)
        for a in assignments:
            if (
                not a.start_date
                or not a.end_date
                or not a.employee_id
                or a.hours_allocated is None
            ):
                continue
            days = (a.end_date - a.start_date).days + 1
            if days <= 0:
                continue
            per_day = a.hours_allocated / days
            d = a.start_date
            while d <= a.end_date:
                demand[(d, a.employee_id)] += per_day
                d += timedelta(days=1)

        overloads: Dict[Tuple[date, str], float] = {}
        for key, dem in demand.items():
            d, emp = key
            avail = availability.get(emp, {}).get(d, 0.0)
            if dem > avail + 0.01:
                overloads[key] = dem
        return overloads
