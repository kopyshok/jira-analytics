"""RCPSP-выравнивание: пост-CPM проход разруливает перегрузки ресурсов.

Стратегии (в порядке убывания предпочтения):
1. delay_within_slack — сдвиг назначения внутри slack без слома цепи
2. reassign_to_peer — переназначение на другого сотрудника той же роли
3. escalate — эскалация в конфликт (OVR.LIGHT/MED/HIGH)

Алгоритм работает после _compute_cpm и до _persist_conflicts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional, Tuple

from app.models import ResourcePlanAssignment


def _per_day_hours(a: ResourcePlanAssignment, availability: Dict[str, Dict[date, float]]) -> Dict[date, float]:
    """Реальная нагрузка фазы по дням.

    Приоритет: assignment.daily_hours_json (план фактической дневной траты).
    Fallback: hours_allocated равномерно по рабочим дням сегмента, но
    capped на per-day availability — иначе при involvement<1 (allocator
    кэпил дневную ёмкость ниже avail) равномерный fallback мог приписать
    8ч/день и поднять false overload.
    """
    if a.daily_hours_json:
        try:
            raw = json.loads(a.daily_hours_json)
            return {date.fromisoformat(k): float(v) for k, v in raw.items() if float(v) > 0}
        except (json.JSONDecodeError, ValueError):
            pass
    if (
        not a.start_date
        or not a.end_date
        or a.hours_allocated is None
        or not a.employee_id
    ):
        return {}
    avail_map = availability.get(a.employee_id, {})
    working: List[date] = []
    d = a.start_date
    while d <= a.end_date:
        if avail_map.get(d, 0.0) > 0.0:
            working.append(d)
        d += timedelta(days=1)
    if not working:
        return {}
    per = a.hours_allocated / len(working)
    return {d: min(per, avail_map.get(d, per)) for d in working}


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

    def __init__(self) -> None:
        self._escalated_keys: set[tuple[date, str]] = set()

    def level(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
        q_end: date,
        role_pools: Optional[Dict[str, List[str]]] = None,
    ) -> List[LevelingEvent]:
        """Главный entrypoint. Мутирует assignments на месте, возвращает событий."""
        if not assignments:
            return []
        self._escalated_keys = set()
        role_pools = role_pools or {}
        events: List[LevelingEvent] = []
        max_passes = 50  # увеличено с 20: reassign может потребовать больше итераций в сложных графах
        for _ in range(max_passes):
            overloads = self._detect_overload(assignments, availability)
            overloads = {
                k: v for k, v in overloads.items() if k not in self._escalated_keys
            }
            if not overloads:
                break

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
                # Defensive: _detect_overload only flags employees with demand, so this
                # should be unreachable. Break terminates the pass cleanly if it ever happens.
                break

            # MSL: выбрать наиболее ограниченный (min slack) среди подвижных — сохраняем большой slack для будущих перегрузок
            movable = [a for a in candidates if (a.slack_days or 0.0) > 0.01]

            applied = False
            delay_failed_reason: Optional[str] = (
                None  # "no_slack" | "no_capacity_in_window"
            )
            reassign_failed_reason: Optional[str] = (
                None  # "no_peers" | "all_peers_busy"
            )

            # Try delay first
            if movable:
                movable.sort(key=lambda a: a.slack_days or 0.0)
                target = movable[0]
                shift = 1
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
                    delay_failed_reason = "no_capacity_in_window"
            else:
                delay_failed_reason = "no_slack"

            if applied:
                continue

            # Try reassign — pick any candidate (not just movable), prefer one with no slack
            # Расширено: пробуем все кандидаты (не только первый), поскольку peer может быть
            # несовместим с конкретным окном; перебираем от наиболее ограниченного.
            candidates.sort(key=lambda a: a.slack_days or 0.0)
            peers_for_target = role_pools.get(target_emp, [])
            peers_excl_self = [p for p in peers_for_target if p != target_emp]
            if not peers_excl_self:
                reassign_failed_reason = "no_peers"
            else:
                for target in candidates:
                    reassigned = False
                    for peer_id in peers_excl_self:
                        original_emp = target.employee_id
                        if self._try_reassign(
                            target, peer_id, availability, assignments
                        ):
                            events.append(
                                LevelingEvent(
                                    assignment_id=target.id,
                                    action="reassign",
                                    reason=f"Переназначен с {original_emp} на {peer_id} (peer той же роли)",
                                    from_employee_id=original_emp,
                                    to_employee_id=peer_id,
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
                            reassigned = True
                            break
                    if reassigned:
                        break
                if not applied:
                    reassign_failed_reason = "all_peers_busy"

            if not applied:
                # Эскалация: ни delay, ни reassign не смогли разрешить перегрузку
                # Берём первого кандидата как детерминированную цель для escalate
                esc_target = candidates[0]
                day_key = (target_day, target_emp)
                parts: List[str] = []
                if delay_failed_reason == "no_slack":
                    parts.append("нет slack")
                elif delay_failed_reason == "no_capacity_in_window":
                    parts.append("нет окон у текущего исполнителя")
                if reassign_failed_reason == "no_peers":
                    parts.append("нет peers той же роли")
                elif reassign_failed_reason == "all_peers_busy":
                    parts.append("все peers заняты")
                reason = (
                    f"Не удалось разрешить перегрузку {target_emp} {target_day}: "
                    + ("; ".join(parts) if parts else "неизвестная причина")
                )
                events.append(
                    LevelingEvent(
                        assignment_id=esc_target.id,
                        action="escalate",
                        reason=reason,
                        overload_pct=(
                            overloads[day_key]
                            / max(
                                0.01,
                                availability.get(target_emp, {}).get(target_day, 0.0),
                            )
                        )
                        * 100,
                        affected_dates=[target_day],
                    )
                )
                # Помечаем (day, emp) как escalated чтобы не зациклиться
                self._escalated_keys.add((target_day, target_emp))
                # Не делаем break — продолжаем: могут быть другие перегрузки
        return events

    def _try_reassign(
        self,
        assignment: ResourcePlanAssignment,
        peer_id: str,
        availability: Dict[str, Dict[date, float]],
        all_assignments: List[ResourcePlanAssignment],
    ) -> bool:
        """Переназначить на peer если у него хватает доступности в окне assignment.

        Часы распределяются только по рабочим дням (где availability > 0) —
        как в _detect_overload.
        """
        if (
            not assignment.start_date
            or not assignment.end_date
            or assignment.hours_allocated is None
        ):
            return False
        # Считаем peer_per_day без учёта старого daily_hours_json — он
        # привязан к рабочим дням исходного сотрудника. Временно скрываем JSON
        # и employee, чтобы _per_day_hours прошёл по fallback'у peer'а.
        original_emp = assignment.employee_id
        original_json = assignment.daily_hours_json
        assignment.employee_id = peer_id
        assignment.daily_hours_json = None
        peer_per_day = _per_day_hours(assignment, availability)
        assignment.employee_id = original_emp
        assignment.daily_hours_json = original_json
        if not peer_per_day:
            return False

        # Текущая нагрузка peer от остальных назначений.
        peer_demand: Dict[date, float] = defaultdict(float)
        for a in all_assignments:
            if a.employee_id != peer_id or a.id == assignment.id:
                continue
            for dd, h in _per_day_hours(a, availability).items():
                peer_demand[dd] += h

        peer_avail = availability.get(peer_id, {})
        for d, need in peer_per_day.items():
            free = peer_avail.get(d, 0.0) - peer_demand.get(d, 0.0)
            if free < need - 0.01:
                return False
        assignment.employee_id = peer_id
        # daily_hours_json привязан к старому сотруднику (его рабочие дни
        # и отсутствия). Сбрасываем — пусть последующий компут перестроит,
        # либо overload-расчёт пройдёт по fallback'у peer'а.
        assignment.daily_hours_json = None
        return True

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
        # Синхронизировать daily_hours_json — иначе клампы в сервисе вернут
        # фазу на старые ключи дней, и overload-расчёт увидит и старый, и
        # новый диапазон.
        if assignment.daily_hours_json and delta_days != 0:
            try:
                daily = json.loads(assignment.daily_hours_json)
            except (json.JSONDecodeError, ValueError):
                daily = {}
            if daily:
                shifted: Dict[str, float] = {}
                for k, v in daily.items():
                    try:
                        new_key = (
                            date.fromisoformat(k) + timedelta(days=delta_days)
                        ).isoformat()
                    except ValueError:
                        continue
                    shifted[new_key] = float(v)
                assignment.daily_hours_json = (
                    json.dumps(shifted) if shifted else None
                )
        return True

    def _detect_overload(
        self,
        assignments: List[ResourcePlanAssignment],
        availability: Dict[str, Dict[date, float]],
    ) -> Dict[Tuple[date, str], float]:
        """Возвращает {(date, employee_id): demand_hours} там где demand > available.

        Demand распределяется равномерно ТОЛЬКО по рабочим дням сегмента
        (где availability[emp][d] > 0). Выходные/праздники/отсутствия не
        получают часов — иначе ловится фантомный 57143%-overload на субботе.
        """
        demand: Dict[Tuple[date, str], float] = defaultdict(float)
        for a in assignments:
            if not a.employee_id:
                continue
            for d, h in _per_day_hours(a, availability).items():
                demand[(d, a.employee_id)] += h

        overloads: Dict[Tuple[date, str], float] = {}
        for key, dem in demand.items():
            d, emp = key
            avail = availability.get(emp, {}).get(d, 0.0)
            if dem > avail + 0.01:
                overloads[key] = dem
        return overloads
