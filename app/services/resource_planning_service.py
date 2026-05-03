"""Сервис ресурсного планирования — расписание фаз инициатив на квартал."""

from __future__ import annotations

import calendar as cal_module
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    BacklogItem,
    Employee,
    ProductionCalendarDay,
    ResourcePlan,
    ResourcePlanAssignment,
    Role,
    ScheduledBlock,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.rcpsp_leveler import RcpspLeveler

PHASE_ORDER = ["analyst", "dev", "qa", "opo"]
PHASE_HOURS_FIELD = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
}
DEFAULT_HOURS_PER_DAY = 6.0


class ResourcePlanningService:
    def __init__(self, db: Session):
        self.db = db
        self._last_leveling_events: List = []

    def build_availability(
        self,
        employees: List[Employee],
        start: date,
        end: date,
        scheduled_blocks: List[ScheduledBlock],
    ) -> Dict[str, Dict[date, float]]:
        """Returns {employee_id: {date: available_hours}}.

        available_hours = production calendar hours if working day,
        0.0 if weekend/holiday/absence/blocked period.
        """
        emp_ids = [e.id for e in employees]

        # Production calendar — only anomaly days are stored
        cal_rows = (
            self.db.execute(
                select(ProductionCalendarDay).where(
                    and_(
                        ProductionCalendarDay.date >= start,
                        ProductionCalendarDay.date <= end,
                    )
                )
            )
            .scalars()
            .all()
        )
        # is_workday=True means hours>0 (перенесённый рабочий день или сокращённый);
        # is_workday=False means hours=0 (праздник / нерабочий перенос).
        cal: Dict[date, float] = {row.date: row.hours for row in cal_rows}

        # Absences
        absences = (
            self.db.execute(
                select(Absence).where(
                    and_(
                        Absence.employee_id.in_(emp_ids),
                        Absence.start_date <= end,
                        Absence.end_date >= start,
                    )
                )
            )
            .scalars()
            .all()
        )
        absent_days: Dict[str, set] = defaultdict(set)
        for a in absences:
            d = max(a.start_date, start)
            while d <= min(a.end_date, end):
                absent_days[a.employee_id].add(d)
                d += timedelta(days=1)

        # Build role_code → role_id map for block resolution
        # ScheduledBlock.role_id is a UUID FK → roles.id; Employee.role is a role code.
        # We need to match them, so load the mapping once.
        role_code_to_id: Dict[str, str] = {}
        role_id_to_code: Dict[str, str] = {}
        role_ids_needed = {b.role_id for b in scheduled_blocks if b.role_id}
        if role_ids_needed:
            role_rows = (
                self.db.execute(select(Role).where(Role.id.in_(role_ids_needed)))
                .scalars()
                .all()
            )
            for r in role_rows:
                role_code_to_id[r.code] = r.id
                role_id_to_code[r.id] = r.code

        # Blocked periods
        blocked_days: Dict[str, set] = defaultdict(set)
        for b in scheduled_blocks:
            targets = self._block_targets(b, employees, role_id_to_code)
            d = max(b.start_date, start)
            while d <= min(b.end_date, end):
                for eid in targets:
                    blocked_days[eid].add(d)
                d += timedelta(days=1)

        # Build result
        result: Dict[str, Dict[date, float]] = {}
        for emp in employees:
            daily: Dict[date, float] = {}
            d = start
            while d <= end:
                if d in absent_days[emp.id] or d in blocked_days[emp.id]:
                    daily[d] = 0.0
                else:
                    cal_hours = cal.get(d, None)
                    if cal_hours is None:
                        # No anomaly record → default weekday logic
                        cal_hours = DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0
                    daily[d] = cal_hours
                d += timedelta(days=1)
            result[emp.id] = daily
        return result

    def _block_targets(
        self,
        block: ScheduledBlock,
        employees: List[Employee],
        role_id_to_code: Dict[str, str],
    ) -> List[str]:
        """Resolve which employee IDs are affected by a ScheduledBlock."""
        if block.employee_id:
            return [block.employee_id]
        if block.role_id:
            role_code = role_id_to_code.get(block.role_id, "")
            return [e.id for e in employees if e.role == role_code]
        if block.team:
            return [e.id for e in employees if e.team == block.team]
        # No filter → all employees
        return [e.id for e in employees]

    # ------------------------------------------------------------------
    # Schedule computation
    # ------------------------------------------------------------------

    def compute_schedule(self, plan_id: str) -> None:
        """Рассчитать расписание фаз для всех инициатив плана."""
        plan = self.db.get(ResourcePlan, plan_id)
        if not plan:
            raise ValueError(f"ResourcePlan {plan_id} not found")

        # Delete old assignments
        self.db.execute(
            ResourcePlanAssignment.__table__.delete().where(
                ResourcePlanAssignment.plan_id == plan_id
            )
        )

        items = self._load_items(plan)
        if not items:
            plan.status = "ready"
            plan.computed_at = datetime.utcnow()
            self.db.commit()
            return

        q_start, q_end = self._quarter_bounds(plan)
        employees = self._load_employees(plan)
        if not employees:
            plan.status = "ready"
            plan.computed_at = datetime.utcnow()
            self.db.commit()
            return

        blocks = (
            self.db.execute(
                select(ScheduledBlock).where(ScheduledBlock.team == plan.team)
            )
            .scalars()
            .all()
        )

        avail = self.build_availability(employees, q_start, q_end, list(blocks))

        assignments_by_role = self._assign_employees(items, employees)

        # Mutable remaining hours copy
        remaining: Dict[str, Dict[date, float]] = {
            eid: dict(days) for eid, days in avail.items()
        }

        new_assignments: List[ResourcePlanAssignment] = []
        for item in items:
            phase_end: Optional[date] = None
            for phase in PHASE_ORDER:
                hours_field = PHASE_HOURS_FIELD[phase]
                hours = getattr(item, hours_field) or 0.0
                if hours <= 0:
                    continue

                employee_id = assignments_by_role.get(phase, {}).get(item.id)
                if not employee_id:
                    continue

                earliest_start = max(
                    q_start,
                    (phase_end + timedelta(days=1)) if phase_end else q_start,
                )

                segments = self._allocate_hours(
                    employee_id, hours, earliest_start, q_end, remaining
                )
                for seg_start, seg_end, seg_hours, part_num in segments:
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase=phase,
                        employee_id=employee_id,
                        part_number=part_num,
                        hours_allocated=seg_hours,
                        start_date=seg_start,
                        end_date=seg_end,
                    )
                    new_assignments.append(a)

                if segments:
                    phase_end = segments[-1][1]

        for a in new_assignments:
            self.db.add(a)

        # CPM на первичных датах
        self._compute_cpm(new_assignments, q_end)

        # RCPSP-выравнивание перегрузок
        leveler = RcpspLeveler()
        role_pools = self._build_role_pools(employees)
        leveling_events = leveler.level(new_assignments, avail, q_end, role_pools)
        # Always recompute CPM — leveling may have shifted dates; cheap O(N) anyway
        self._compute_cpm(new_assignments, q_end)
        # Cache events for Stage B persist_conflicts
        self._last_leveling_events = leveling_events

        # Persist conflicts (Stage B)
        detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
        self._persist_conflicts(plan_id, detected)

        plan.status = "ready"
        plan.computed_at = datetime.utcnow()
        self.db.commit()

    def _allocate_hours(
        self,
        employee_id: str,
        total_hours: float,
        earliest_start: date,
        deadline: date,
        remaining: Dict[str, Dict[date, float]],
    ) -> List[Tuple[date, date, float, int]]:
        """Распределить total_hours по рабочим дням начиная с earliest_start.

        Возвращает список (start_date, end_date, hours, part_number).
        Создаёт split-сегменты при разрывах нулевой доступности.
        """
        emp_days = remaining.get(employee_id, {})
        remaining_h = total_hours
        segments: List[Tuple[date, date, float, int]] = []
        part_num = 1
        seg_start: Optional[date] = None
        seg_hours = 0.0
        seg_end: Optional[date] = None
        in_gap = False

        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            avail_h = emp_days.get(d, 0.0)
            if avail_h > 0:
                if seg_start is None:
                    seg_start = d
                    in_gap = False
                elif in_gap:
                    # Close previous segment, start new one
                    if seg_start is not None and seg_hours > 0 and seg_end is not None:
                        segments.append((seg_start, seg_end, seg_hours, part_num))
                    part_num += 1
                    seg_start = d
                    seg_hours = 0.0
                    in_gap = False
                used = min(avail_h, remaining_h)
                emp_days[d] -= used
                remaining_h -= used
                seg_hours += used
                seg_end = d
            else:
                if seg_start is not None and seg_hours > 0:
                    in_gap = True
            d += timedelta(days=1)

        # Close last open segment
        if seg_start is not None and seg_hours > 0 and seg_end is not None:
            segments.append((seg_start, seg_end, seg_hours, part_num))

        return segments

    def _load_items(self, plan: ResourcePlan) -> List[BacklogItem]:
        """Загрузить включённые инициативы сценария, отсортированные по приоритету."""
        if plan.scenario_id:
            rows = (
                self.db.execute(
                    select(BacklogItem)
                    .join(
                        ScenarioAllocation,
                        ScenarioAllocation.backlog_item_id == BacklogItem.id,
                    )
                    .where(
                        ScenarioAllocation.scenario_id == plan.scenario_id,
                        ScenarioAllocation.included_flag == True,  # noqa: E712
                    )
                    .order_by(BacklogItem.priority.nullslast())
                )
                .scalars()
                .all()
            )
            return list(rows)
        return []

    def _load_employees(self, plan: ResourcePlan) -> List[Employee]:
        """Загрузить активных сотрудников команды плана."""
        rows = (
            self.db.execute(
                select(Employee)
                .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
                .where(
                    EmployeeTeam.team == plan.team,
                    Employee.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    def _quarter_bounds(self, plan: ResourcePlan) -> Tuple[date, date]:
        """Вернуть (начало, конец) квартала плана."""
        from app.services.capacity_service import QUARTER_MONTHS

        quarter_num = int(str(plan.quarter).replace("Q", ""))
        months = QUARTER_MONTHS.get(quarter_num, (1, 2, 3))
        year = plan.year or date.today().year
        q_start = date(year, months[0], 1)
        last_month = months[-1]
        last_day = cal_module.monthrange(year, last_month)[1]
        q_end = date(year, last_month, last_day)
        return q_start, q_end

    def _assign_employees(
        self, items: List[BacklogItem], employees: List[Employee]
    ) -> Dict[str, Dict[str, str]]:
        """Greedy assignment: {phase: {item_id: employee_id}}.

        Назначает аналитика и разработчика на инициативу по минимальной нагрузке.
        Employee.role — строковый код из реестра ролей (напр. 'analyst', 'аналитик').
        """
        role_emp: Dict[str, List[str]] = defaultdict(list)
        for e in employees:
            if e.role:
                role_emp[e.role.lower()].append(e.id)

        analyst_ids = (
            role_emp.get("аналитик", [])
            or role_emp.get("analyst", [])
            or role_emp.get("an", [])
        )
        dev_ids = (
            role_emp.get("разработчик", [])
            or role_emp.get("developer", [])
            or role_emp.get("dev", [])
            or role_emp.get("rp", [])
        )
        qa_ids = role_emp.get("qa", []) or role_emp.get("тестировщик", [])

        # Fallback: if roles not resolved, use all employees
        all_ids = [e.id for e in employees]
        if not analyst_ids:
            analyst_ids = all_ids
        if not dev_ids:
            dev_ids = all_ids
        if not qa_ids:
            qa_ids = all_ids

        load: Dict[str, float] = defaultdict(float)
        result: Dict[str, Dict[str, str]] = {p: {} for p in PHASE_ORDER}

        for item in items:
            for phase, pool in [
                ("analyst", analyst_ids),
                ("dev", dev_ids),
                ("qa", qa_ids),
                ("opo", analyst_ids + dev_ids),
            ]:
                if not pool:
                    continue
                chosen = min(pool, key=lambda eid: load[eid])
                hours_field = PHASE_HOURS_FIELD[phase]
                load[chosen] += getattr(item, hours_field) or 0.0
                result[phase][item.id] = chosen

        return result

    def _build_role_pools(self, employees: List[Employee]) -> Dict[str, List[str]]:
        """{employee_id: [peer_ids same role]} для reassign-стратегии."""
        by_role: Dict[str, List[str]] = defaultdict(list)
        for e in employees:
            if e.role:
                by_role[e.role.lower()].append(e.id)
        result: Dict[str, List[str]] = {}
        for e in employees:
            if e.role:
                result[e.id] = by_role[e.role.lower()]
        return result

    def _compute_cpm(
        self,
        assignments: List["ResourcePlanAssignment"],
        q_end: date,
    ) -> None:
        """Вычислить slack_days и is_on_critical_path для всех назначений.

        В последовательной цепи фаз (analyst→dev→qa→opo) каждая фаза
        инициативы имеет одинаковый total float = q_end - last_phase_end.
        """

        by_item: Dict[str, List["ResourcePlanAssignment"]] = defaultdict(list)
        for a in assignments:
            by_item[a.backlog_item_id].append(a)

        for item_assignments in by_item.values():
            opo = [a for a in item_assignments if a.phase == "opo" and a.end_date]
            all_dated = [a for a in item_assignments if a.end_date]
            if not all_dated:
                continue
            last_end = max(a.end_date for a in (opo if opo else all_dated))
            slack = (q_end - last_end).days
            for a in item_assignments:
                a.slack_days = float(slack)
                a.is_on_critical_path = slack <= 0

    # ------------------------------------------------------------------
    # Stage B — conflict detection & persistence
    # ------------------------------------------------------------------

    def _persist_conflicts(
        self,
        plan_id: str,
        detected: List[dict],
    ) -> None:
        """Upsert конфликтов по detection_key. Сохраняет status существующих.

        Удаляет конфликты которых больше нет в detected (помимо muted — они остаются).
        """
        from app.models import PlanConflict

        existing = (
            self.db.execute(select(PlanConflict).where(PlanConflict.plan_id == plan_id))
            .scalars()
            .all()
        )
        existing_by_key = {c.detection_key: c for c in existing}
        detected_keys = {d["detection_key"] for d in detected}

        for d in detected:
            key = d["detection_key"]
            if key in existing_by_key:
                c = existing_by_key[key]
                c.severity = d["severity"]
                c.message = d["message"]
                c.metric_value = d.get("metric_value")
                c.window_start = d.get("window_start")
                c.window_end = d.get("window_end")
                c.backlog_item_id = d.get("backlog_item_id")
                c.employee_id = d.get("employee_id")
                c.assignment_id = d.get("assignment_id")
            else:
                self.db.add(
                    PlanConflict(
                        plan_id=plan_id,
                        type=d["type"],
                        severity=d["severity"],
                        status="open",
                        detection_key=key,
                        message=d["message"],
                        metric_value=d.get("metric_value"),
                        window_start=d.get("window_start"),
                        window_end=d.get("window_end"),
                        backlog_item_id=d.get("backlog_item_id"),
                        employee_id=d.get("employee_id"),
                        assignment_id=d.get("assignment_id"),
                    )
                )

        for key, c in existing_by_key.items():
            if key not in detected_keys and c.status != "muted":
                self.db.delete(c)

    def _build_conflict_dicts(
        self,
        plan: ResourcePlan,
        assignments: List[ResourcePlanAssignment],
        employees: List[Employee],
        q_end: date,
    ) -> List[dict]:
        """Собрать единый список dict-конфликтов для _persist_conflicts.

        Включает:
        - QUARTER_OVERFLOW (опэ-фаза заходит за квартал)
        - SPLIT_REQUIRED (part_number > 1)
        - NO_ANALYST / NO_DEV (нет в команде)
        - OVERLOAD_LIGHT/MED/HIGH из _last_leveling_events (action='escalate')
        - LEVELING_DELAY / LEVELING_REASSIGN (info — что leveler сделал)
        - LATE_START (фаза стартует позже целевой даты — slack_days < 0)
        """
        from datetime import datetime as _dt

        result: List[dict] = []
        item_titles: Dict[str, str] = {}
        for a in assignments:
            if a.backlog_item_id and a.backlog_item:
                item_titles[a.backlog_item_id] = a.backlog_item.title

        # QUARTER_OVERFLOW
        for a in assignments:
            if a.phase == "opo" and a.end_date and a.end_date > q_end:
                result.append(
                    {
                        "type": "QUARTER_OVERFLOW",
                        "severity": "critical",
                        "detection_key": f"QUARTER_OVERFLOW:{a.backlog_item_id}",
                        "message": f"Инициатива «{item_titles.get(a.backlog_item_id, '')}» не вмещается в квартал: ОПЭ заканчивается {a.end_date}",
                        "backlog_item_id": a.backlog_item_id,
                        "assignment_id": a.id,
                    }
                )

        # SPLIT_REQUIRED — once per item when any phase has part_number > 1
        max_part: Dict[tuple, int] = defaultdict(int)
        for a in assignments:
            max_part[(a.backlog_item_id, a.phase)] = max(
                max_part[(a.backlog_item_id, a.phase)], a.part_number
            )
        seen_split: set = set()
        for (item_id, _phase), mp in max_part.items():
            if mp > 1 and item_id not in seen_split:
                seen_split.add(item_id)
                result.append(
                    {
                        "type": "SPLIT_REQUIRED",
                        "severity": "info",
                        "detection_key": f"SPLIT_REQUIRED:{item_id}",
                        "message": f"Инициатива «{item_titles.get(item_id, '')}» разбита на части из-за заблокированного периода",
                        "backlog_item_id": item_id,
                    }
                )

        # LATE_START — slack_days < 0
        for a in assignments:
            if a.slack_days is not None and a.slack_days < 0:
                result.append(
                    {
                        "type": "LATE_START",
                        "severity": "warning",
                        "detection_key": f"LATE_START:{a.id}",
                        "message": f"Фаза «{a.phase}» инициативы «{item_titles.get(a.backlog_item_id, '')}» стартует слишком поздно (отставание {abs(a.slack_days):.0f} д.)",
                        "metric_value": float(a.slack_days),
                        "backlog_item_id": a.backlog_item_id,
                        "assignment_id": a.id,
                        "employee_id": a.employee_id,
                    }
                )

        # NO_ANALYST / NO_DEV
        ANALYST_CODES = {"аналитик", "analyst", "an"}
        DEV_CODES = {"разработчик", "developer", "dev", "rp"}
        if plan.team:
            has_analyst = any(
                e.role and e.role.lower() in ANALYST_CODES for e in employees
            )
            has_dev = any(e.role and e.role.lower() in DEV_CODES for e in employees)
            if not has_analyst:
                result.append(
                    {
                        "type": "NO_ANALYST",
                        "severity": "critical",
                        "detection_key": f"NO_ANALYST:{plan.team}",
                        "message": f"В команде «{plan.team}» нет аналитиков. Расписание аналитической фазы невозможно.",
                    }
                )
            if not has_dev:
                result.append(
                    {
                        "type": "NO_DEV",
                        "severity": "critical",
                        "detection_key": f"NO_DEV:{plan.team}",
                        "message": f"В команде «{plan.team}» нет разработчиков. Расписание фазы разработки невозможно.",
                    }
                )

        # OVERLOAD_* + LEVELING_* from leveling events
        for ev in self._last_leveling_events:
            if ev.action == "escalate":
                pct = ev.overload_pct
                if pct > 120:
                    sev, type_ = "critical", "OVERLOAD_HIGH"
                elif pct > 110:
                    sev, type_ = "warning", "OVERLOAD_MED"
                else:
                    sev, type_ = "warning", "OVERLOAD_LIGHT"
                day = ev.affected_dates[0] if ev.affected_dates else None
                result.append(
                    {
                        "type": type_,
                        "severity": sev,
                        "detection_key": f"{type_}:{ev.assignment_id}:{day}",
                        "message": f"Перегрузка {pct:.0f}% на {day}: {ev.reason}",
                        "metric_value": pct,
                        "assignment_id": ev.assignment_id,
                        "window_start": _dt.combine(day, _dt.min.time())
                        if day
                        else None,
                        "window_end": _dt.combine(day, _dt.min.time()) if day else None,
                    }
                )
            elif ev.action == "delay":
                day = ev.affected_dates[0] if ev.affected_dates else None
                result.append(
                    {
                        "type": "LEVELING_DELAY",
                        "severity": "info",
                        "detection_key": f"LEVELING_DELAY:{ev.assignment_id}:{day}",
                        "message": ev.reason,
                        "metric_value": float(ev.delta_days),
                        "assignment_id": ev.assignment_id,
                    }
                )
            elif ev.action == "reassign":
                result.append(
                    {
                        "type": "LEVELING_REASSIGN",
                        "severity": "info",
                        "detection_key": f"LEVELING_REASSIGN:{ev.assignment_id}",
                        "message": ev.reason,
                        "assignment_id": ev.assignment_id,
                        "employee_id": ev.to_employee_id,
                    }
                )

        return result
