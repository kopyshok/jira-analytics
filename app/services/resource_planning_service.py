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

# Допустимые роли исполнителя для аналитической фазы.
ANALYST_ROLES = {
    "аналитик", "analyst", "an",
    "рп", "rp",
    "консультант", "consultant",
}
# Роли пула разработки.
DEV_ROLES = {"разработчик", "developer", "dev", "программист"}

# Phase 3: маппинг phase → (поле duration_days, поле involvement) в BacklogItem.
PHASE_DURATION_FIELDS: Dict[str, Tuple[str, str]] = {
    "analyst": ("duration_analyst_days", "involvement_analyst"),
    "dev":     ("duration_dev_days",     "involvement_dev"),
    "qa":      ("duration_qa_days",      "involvement_qa"),
    "opo":     ("duration_launch_days",  "involvement_launch"),
}

def _resolve_phase_calendar_days(
    item: "BacklogItem", phase: str, hours: float
) -> Tuple[float, bool]:
    """Вычислить длину фазы в календарных рабочих днях.

    Возвращает (cal_days, jira_field_set).
    jira_field_set=True если duration_days или involvement задан явно (из Jira).

    Fallback-цепочка:
      1. duration_<phase>_days (из Jira) — используется напрямую.
      2. estimate_hours / (involvement × 8) — если задана занятость.
      3. estimate_hours / 8 — базовый fallback.
    """
    dur_field, inv_field = PHASE_DURATION_FIELDS.get(phase, (None, None))
    if dur_field:
        dur = getattr(item, dur_field, None)
        if dur:
            return float(dur), True
    inv: float = 1.0
    jira_inv_set = False
    if inv_field:
        raw_inv = getattr(item, inv_field, None)
        if raw_inv:
            inv = float(raw_inv)
            jira_inv_set = True
    return max(1.0, hours / max(0.1, inv * 8.0)), jira_inv_set


def _resolve_parallel_count_legacy(item: "BacklogItem", phase: str) -> int:
    """Per-phase parallel count для legacy compute_schedule.

    Разрешение: item override → project default → 1.
    ОПЭ не параллелится (возвращает 1).
    """
    field = f"parallel_count_{phase}"
    if field not in ("parallel_count_analyst", "parallel_count_dev", "parallel_count_qa"):
        return 1
    n_item = getattr(item, field, None)
    if n_item and int(n_item) > 0:
        return int(n_item)
    proj = item.project if item else None
    n_proj = getattr(proj, field, None) if proj else None
    if n_proj and int(n_proj) > 0:
        return int(n_proj)
    return 1


def _advance_working_days(start: date, days: int) -> date:
    """Вернуть дату через N рабочих дней начиная с start (включительно).

    Упрощённый расчёт без учёта праздников (только Пн–Пт). Используется
    для вычисления end-cursor при duration_days / parallel_count.
    """
    n = max(1, int(days))
    d = start
    counted = 0
    while counted < n:
        if d.weekday() < 5:
            counted += 1
            if counted < n:
                d += timedelta(days=1)
        else:
            d += timedelta(days=1)
    return d


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
        """Рассчитать расписание фаз для всех инициатив плана.

        Pinned-назначения (``is_pinned=True``) не пересчитываются и не удаляются:
        используются как фиксированный сотрудник в `_assign_employees`, а старые
        строки сохраняются в БД и сливаются с новыми non-pinned результатами.
        """
        plan = self.db.get(ResourcePlan, plan_id)
        if not plan:
            raise ValueError(f"ResourcePlan {plan_id} not found")

        # Сохранить pinned до удаления, удалить только non-pinned
        pinned_existing = list(
            self.db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    ResourcePlanAssignment.is_pinned == True,  # noqa: E712
                )
            ).scalars()
        )
        pinned_map: Dict[Tuple[str, str, int], str] = {
            (a.backlog_item_id, a.phase, a.part_number): a.employee_id
            for a in pinned_existing
            if a.employee_id is not None
        }

        self.db.execute(
            ResourcePlanAssignment.__table__.delete().where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.is_pinned == False,  # noqa: E712
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

        assignments_by_role = self._assign_employees(
            items, employees, pinned=pinned_map
        )

        # Mutable remaining hours copy
        remaining: Dict[str, Dict[date, float]] = {
            eid: dict(days) for eid, days in avail.items()
        }

        # Преварительно вычесть часы pinned-сегментов из remaining чтобы не
        # перегрузить тех же сотрудников при пересчёте non-pinned фаз.
        for a in pinned_existing:
            if (
                a.employee_id
                and a.start_date
                and a.end_date
                and a.hours_allocated
                and a.employee_id in remaining
            ):
                # Грубо: распределяем поровну по дням сегмента (только в дни с >0 avail)
                days_in_seg = [
                    d for d in remaining[a.employee_id]
                    if a.start_date <= d <= a.end_date
                    and remaining[a.employee_id][d] > 0
                ]
                if days_in_seg:
                    per_day = a.hours_allocated / len(days_in_seg)
                    for d in days_in_seg:
                        remaining[a.employee_id][d] = max(
                            0.0, remaining[a.employee_id][d] - per_day
                        )

        new_assignments: List[ResourcePlanAssignment] = list(pinned_existing)

        # Скип фаз/частей которые уже зафиксированы pin'ом
        pinned_phase_keys = {
            (a.backlog_item_id, a.phase) for a in pinned_existing
        }

        # Phase 5: вычислить решения о сплите аналитических фаз до основного цикла.
        # _analyst_split_map: {(item_id, "analyst") → N кусков}
        # _analyst_first_chunk_end: {item_id → end_date первого куска} — заполняется
        # в ходе основного цикла, затем используется для earliest_start dev-фазы.
        _analyst_split_map = self._compute_legacy_split_map(items, employees, q_start, q_end)
        _analyst_first_chunk_end: Dict[str, Optional[date]] = {}

        for item in items:
            phase_end: Optional[date] = None
            for phase in PHASE_ORDER:
                hours_field = PHASE_HOURS_FIELD[phase]
                hours = float(getattr(item, hours_field) or 0.0)
                if hours <= 0:
                    continue

                # Если фаза целиком pinned — её даты как «end» для cascade
                if (item.id, phase) in pinned_phase_keys:
                    phase_pinned = [
                        a for a in pinned_existing
                        if a.backlog_item_id == item.id and a.phase == phase
                    ]
                    pe = max(
                        (a.end_date for a in phase_pinned if a.end_date),
                        default=phase_end,
                    )
                    if pe:
                        phase_end = pe
                    continue

                # Phase 5: dev-фаза стартует после первого куска аналитической фазы,
                # если аналитик был разбит на куски (earlier_start эффект).
                if phase == "dev" and item.id in _analyst_first_chunk_end:
                    first_chunk_end = _analyst_first_chunk_end[item.id]
                    if first_chunk_end is not None:
                        earliest_start = max(
                            q_start,
                            first_chunk_end + timedelta(days=1),
                        )
                    else:
                        earliest_start = max(
                            q_start,
                            (phase_end + timedelta(days=1)) if phase_end else q_start,
                        )
                else:
                    earliest_start = max(
                        q_start,
                        (phase_end + timedelta(days=1)) if phase_end else q_start,
                    )

                if phase == "qa":
                    # QA — часы-only, без сотрудника. Длина = ceil(hours / 6) дней.
                    seg_start = earliest_start
                    days_needed = max(1, int((hours + DEFAULT_HOURS_PER_DAY - 0.001)
                                             // DEFAULT_HOURS_PER_DAY))
                    seg_end = seg_start + timedelta(days=days_needed - 1)
                    if seg_end > q_end:
                        seg_end = q_end
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase="qa",
                        employee_id=None,
                        part_number=1,
                        hours_allocated=hours,
                        start_date=seg_start,
                        end_date=seg_end,
                    )
                    new_assignments.append(a)
                    phase_end = seg_end
                    continue

                if phase == "opo":
                    analyst_id = assignments_by_role["analyst"].get(item.id)
                    dev_id = assignments_by_role["dev"].get(item.id)
                    # Если у инициативы нет исполнителя-аналитика — взять любого из
                    # пула аналитических ролей (независимо от assignee).
                    if not analyst_id:
                        opo_analyst_pool = [
                            e.id for e in employees
                            if (e.role or "").lower() in ANALYST_ROLES
                        ]
                        if opo_analyst_pool:
                            # min-load: выбрать наименее загруженного по remaining
                            analyst_id = min(
                                opo_analyst_pool,
                                key=lambda eid: -sum(remaining.get(eid, {}).values()),
                            )
                    parts = self._opo_split(item, analyst_id, dev_id)
                    last_end: Optional[date] = None
                    for emp_id, p_hours in parts:
                        if not emp_id or p_hours <= 0:
                            continue
                        segments = self._allocate_hours(
                            emp_id, p_hours, earliest_start, q_end, remaining
                        )
                        for seg_start, seg_end, seg_hours, part_num in segments:
                            a = ResourcePlanAssignment(
                                plan_id=plan_id,
                                backlog_item_id=item.id,
                                phase="opo",
                                employee_id=emp_id,
                                part_number=part_num,
                                hours_allocated=seg_hours,
                                start_date=seg_start,
                                end_date=seg_end,
                            )
                            new_assignments.append(a)
                        if segments:
                            seg_last = segments[-1][1]
                            if last_end is None or seg_last > last_end:
                                last_end = seg_last
                    if last_end:
                        phase_end = last_end
                    continue

                # analyst / dev — обычное allocation для одного сотрудника
                employee_id = assignments_by_role.get(phase, {}).get(item.id)
                if not employee_id:
                    continue

                # Phase 3+4: вычисляем календарную длину фазы с учётом
                # duration_days / involvement / parallel_count.
                cal_days, jira_cal_set = _resolve_phase_calendar_days(item, phase, hours)
                parallel_n = _resolve_parallel_count_legacy(item, phase)
                if parallel_n > 1:
                    jira_cal_set = True
                cal_days = max(1.0, cal_days / max(1, parallel_n))

                # Авто-сплит аналитической фазы (Phase 5): если для этого item
                # решение о сплите уже принято — используем его.
                analyst_split_chunks = _analyst_split_map.get((item.id, phase), 1)
                if analyst_split_chunks > 1:
                    # Делим фазу на N равных кусков; dev стартует после первого куска.
                    chunk_cal_days = max(1.0, cal_days / analyst_split_chunks)
                    chunk_hours = hours / analyst_split_chunks
                    first_chunk_end: Optional[date] = None
                    last_chunk_end: Optional[date] = None
                    for chunk_idx in range(1, analyst_split_chunks + 1):
                        chunk_start = earliest_start if chunk_idx == 1 else (
                            (last_chunk_end + timedelta(days=1)) if last_chunk_end else earliest_start
                        )
                        chunk_segs = self._allocate_hours(
                            employee_id, chunk_hours, chunk_start, q_end, remaining
                        )
                        for seg_start, seg_end, seg_hours, seg_part in chunk_segs:
                            a = ResourcePlanAssignment(
                                plan_id=plan_id,
                                backlog_item_id=item.id,
                                phase=phase,
                                employee_id=employee_id,
                                part_number=chunk_idx,
                                hours_allocated=seg_hours,
                                start_date=seg_start,
                                end_date=seg_end,
                            )
                            new_assignments.append(a)
                        # Calendar-based end for this chunk
                        cal_end = _advance_working_days(chunk_start, int(chunk_cal_days))
                        chunk_end = max(
                            chunk_segs[-1][1] if chunk_segs else chunk_start,
                            cal_end,
                        )
                        if first_chunk_end is None:
                            first_chunk_end = chunk_end
                        last_chunk_end = chunk_end
                    # Dev starts after first chunk; overall phase_end after last chunk.
                    _analyst_first_chunk_end[item.id] = first_chunk_end
                    phase_end = last_chunk_end
                    continue

                # Phase 3+4: when Jira fields are set, cal_end is authoritative.
                # - Limit alloc_deadline to cal_end so hours don't spill beyond it
                #   (parallel_count shortens; too many hours simply don't fit).
                # - Extend last segment's end_date to cal_end when hours exhaust early
                #   (involvement/duration makes phase longer than hours alone).
                # Without Jira fields — legacy behavior: deadline = q_end.
                cal_end = min(
                    _advance_working_days(earliest_start, int(cal_days)),
                    q_end,
                )
                alloc_deadline = cal_end if jira_cal_set else q_end

                segments = self._allocate_hours(
                    employee_id, hours, earliest_start, alloc_deadline, remaining
                )

                # Если жёсткое окно из Jira (duration/involvement) не вмещает
                # часы — расширяем deadline до конца квартала, чтобы фаза не
                # пропала из расписания. Перегрузку зафиксирует RCPSP-leveler.
                if jira_cal_set and not segments and hours > 0:
                    segments = self._allocate_hours(
                        employee_id, hours, earliest_start, q_end, remaining
                    )

                if jira_cal_set:
                    if segments and segments[-1][1] > cal_end:
                        effective_end = segments[-1][1]
                    else:
                        effective_end = cal_end
                elif segments:
                    effective_end = segments[-1][1]
                else:
                    effective_end = None

                for idx, (seg_start, seg_end, seg_hours, part_num) in enumerate(segments):
                    # When Jira cal sets a wider span, stretch the last segment's end.
                    if jira_cal_set and idx == len(segments) - 1:
                        seg_end = effective_end
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

                if effective_end is not None:
                    phase_end = effective_end

        for a in new_assignments:
            if a not in pinned_existing:
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

        Возвращает один сегмент (start, end, hours, 1) — единый бар фазы без
        разбиения на части. Часы по-прежнему распределяются только по дням с
        ненулевой доступностью (выходные/отсутствия пропускаются), но конечный
        бар покрывает диапазон от первого до последнего использованного дня
        одной непрерывной полосой.
        """
        emp_days = remaining.get(employee_id, {})
        remaining_h = total_hours
        used_total = 0.0
        seg_start: Optional[date] = None
        seg_end: Optional[date] = None

        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            avail_h = emp_days.get(d, 0.0)
            if avail_h > 0:
                if seg_start is None:
                    seg_start = d
                used = min(avail_h, remaining_h)
                emp_days[d] -= used
                remaining_h -= used
                used_total += used
                seg_end = d
            d += timedelta(days=1)

        if seg_start is not None and seg_end is not None and used_total > 0:
            return [(seg_start, seg_end, used_total, 1)]
        return []

    def _load_items(self, plan: ResourcePlan) -> List[BacklogItem]:
        """Загрузить включённые инициативы сценария, отсортированные по приоритету."""
        if plan.scenario_id:
            from sqlalchemy.orm import joinedload
            rows = (
                self.db.execute(
                    select(BacklogItem)
                    .options(joinedload(BacklogItem.issue))
                    .join(
                        ScenarioAllocation,
                        ScenarioAllocation.backlog_item_id == BacklogItem.id,
                    )
                    .where(
                        ScenarioAllocation.scenario_id == plan.scenario_id,
                        ScenarioAllocation.included_flag == True,  # noqa: E712
                    )
                    .order_by(BacklogItem.priority.desc().nullslast())
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
        self,
        items: List[BacklogItem],
        employees: List[Employee],
        pinned: Optional[Dict[Tuple[str, str, int], str]] = None,
    ) -> Dict[str, Dict[str, Optional[str]]]:
        """{phase: {item_id: employee_id|None}} с учётом ролей и закреплений.

        - analyst: исполнитель инициативы (`assignee_employee_id`), независимо от его роли.
                   Если у задачи нет исполнителя — None.
        - dev:     greedy по минимальной нагрузке в пуле DEV_ROLES (fallback — все).
        - qa:      всегда None (часы-only, дату назначаем без сотрудника).
        - opo:     placeholder analyst_id или dev_id; реально создаётся как 2 строки
                   через `_opo_split` в compute_schedule.

        ``pinned`` — словарь {(item_id, phase, part_number): employee_id}. Если
        для (item, phase, 1) есть pin — используется он, обычная логика игнорится.
        """
        pinned = pinned or {}

        by_id: Dict[str, Employee] = {e.id: e for e in employees}
        # Резолв по display_name для fallback (если bk.assignee_employee_id NULL,
        # но в связанной Issue есть assignee_display_name — пробуем найти сотрудника).
        by_name: Dict[str, str] = {}
        for e in employees:
            if e.display_name:
                # При коллизии имён берём первого; production-correct fix —
                # заполнять BacklogItem.assignee_employee_id при refresh-from-jira.
                by_name.setdefault(e.display_name.strip().lower(), e.id)

        dev_ids = [e.id for e in employees if (e.role or "").lower() in DEV_ROLES]
        if not dev_ids:
            dev_ids = [e.id for e in employees]

        analyst_ids = [e.id for e in employees if (e.role or "").lower() in ANALYST_ROLES]

        load: Dict[str, float] = defaultdict(float)
        result: Dict[str, Dict[str, Optional[str]]] = {p: {} for p in PHASE_ORDER}

        for item in items:
            # ── analyst — исполнитель из сценария ─────────────────────
            analyst_id: Optional[str] = None
            pin_an = pinned.get((item.id, "analyst", 1))
            if pin_an:
                analyst_id = pin_an
            elif item.assignee_employee_id and item.assignee_employee_id in by_id:
                analyst_id = item.assignee_employee_id
            elif item.issue_id:
                # Fallback: резолв по Issue.assignee_display_name
                issue = item.issue
                if issue and issue.assignee_display_name:
                    analyst_id = by_name.get(issue.assignee_display_name.strip().lower())
            # Если исполнитель не из команды плана (или вообще не задан) —
            # берём наименее загруженного из пула аналитиков команды, чтобы
            # фаза «Анализ» всё равно появилась в расписании.
            if not analyst_id and analyst_ids:
                analyst_id = min(analyst_ids, key=lambda eid: load[eid])
            if analyst_id:
                load[analyst_id] += item.estimate_analyst_hours or 0.0
            result["analyst"][item.id] = analyst_id

            # ── dev ────────────────────────────────────────────────────
            dev_id: Optional[str] = pinned.get((item.id, "dev", 1))
            if not dev_id and dev_ids:
                dev_id = min(dev_ids, key=lambda eid: load[eid])
            if dev_id:
                load[dev_id] += item.estimate_dev_hours or 0.0
            result["dev"][item.id] = dev_id

            # ── qa: без сотрудника ─────────────────────────────────────
            result["qa"][item.id] = None

            # ── opo: маркер для compute_schedule, реально 2 строки ────
            result["opo"][item.id] = analyst_id or dev_id

        return result

    def _opo_split(
        self,
        item: BacklogItem,
        analyst_id: Optional[str],
        dev_id: Optional[str],
    ) -> List[Tuple[Optional[str], float]]:
        """ОПЭ → 2 куска: [(analyst_id, an_hours), (dev_id, dev_hours)].

        Доля аналитика = ``item.opo_analyst_ratio`` (default 0.5).
        Часы округляются до 2 знаков; сумма равна total (последний кусок добирает остаток).
        """
        total = float(item.estimate_opo_hours or 0.0)
        ratio = (
            item.opo_analyst_ratio if item.opo_analyst_ratio is not None else 0.5
        )
        an_hours = round(total * ratio, 2)
        dev_hours = round(total - an_hours, 2)
        return [(analyst_id, an_hours), (dev_id, dev_hours)]

    def _compute_legacy_split_map(
        self,
        items: List[BacklogItem],
        employees: List[Employee],
        q_start: date,
        q_end: date,
    ) -> Dict[Tuple[str, str], int]:
        """Авто-сплит фаз отключён: декомпозиция задаётся пользователем вручную."""
        return {}

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
