"""Сервис ресурсного планирования — расписание фаз инициатив на квартал."""

from __future__ import annotations

import calendar as cal_module
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, select
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

    @staticmethod
    def _daily_role_capacity(
        avail_hours: float,
        involvement: Optional[float],
        parallel_count: int,
    ) -> float:
        """Дневная ёмкость роли в фазе.

        avail_hours — доступно_по_календарю_сотрудника (производственный
        календарь минус отсутствия и блокировки).
        involvement — коэф вовлечённости (0..1). None → 1.0 (legacy для
        задач без Jira-данных, ёмкость не урезается).
        parallel_count — число параллельных исполнителей этой роли (>=1).
        """
        inv = 1.0 if involvement is None else max(0.0, min(1.0, involvement))
        return avail_hours * inv * max(1, parallel_count)

    @staticmethod
    def _involvement_for_phase(item: BacklogItem, phase: str) -> Optional[float]:
        """Коэф вовлечённости из BacklogItem для указанной фазы (None если не задан)."""
        field = {
            "analyst": "involvement_analyst",
            "dev": "involvement_dev",
            "qa": "involvement_qa",
            "opo": "involvement_launch",
        }.get(phase)
        if not field:
            return None
        return getattr(item, field, None)

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

        # Build role_code → role_id map for block resolution.
        # ScheduledBlock.roles[].role_id is a UUID FK → roles.id;
        # Employee.role is a role code. We load the mapping once.
        role_code_to_id: Dict[str, str] = {}
        role_id_to_code: Dict[str, str] = {}
        role_ids_needed: set[str] = set()
        for b in scheduled_blocks:
            for r in b.roles:
                role_ids_needed.add(r.role_id)
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
        """Resolve which employee IDs are affected by a ScheduledBlock.

        Block applies to:
          - all employees with one of `block.roles` codes, AND
          - any explicitly listed employee in `block.employees`.
        Если оба списка пусты — блок действует на всю команду
        (или на всех сотрудников, если `block.team` is None).
        """
        if not block.roles and not block.employees:
            if block.team:
                return [e.id for e in employees if e.team == block.team]
            return [e.id for e in employees]
        targets: set[str] = set()
        role_ids = {r.role_id for r in block.roles}
        for r_id in role_ids:
            code = role_id_to_code.get(r_id, "")
            targets.update(
                e.id for e in employees if (e.role or "").lower() == code.lower()
            )
        targets.update(e.employee_id for e in block.employees)
        return list(targets)

    # ------------------------------------------------------------------
    # Schedule computation
    # ------------------------------------------------------------------

    def compute_schedule(self, plan_id: str) -> None:
        """Рассчитать расписание фаз для всех инициатив плана.

        Назначения с любым из флагов `pinned_employee`/`pinned_start`/`pinned_split`=True
        не пересчитываются и не удаляются: используются как фиксированный
        сотрудник/дата/разбивка в `_assign_employees`, а старые строки сохраняются
        в БД и сливаются с новыми non-pinned результатами.
        """
        plan = self.db.get(ResourcePlan, plan_id)
        if not plan:
            raise ValueError(f"ResourcePlan {plan_id} not found")

        # Снимок логических ключей рёбер до удаления назначений (CASCADE
        # предшественников). После пересоздания назначений рёбра восстанавливаются
        # по (item_id, phase, part_number, employee_id).
        pred_snapshot = self._snapshot_predecessors(plan_id)

        # Сохранить pinned до удаления, удалить только non-pinned
        pinned_existing = list(
            self.db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    or_(
                        ResourcePlanAssignment.pinned_employee == True,  # noqa: E712
                        ResourcePlanAssignment.pinned_start == True,  # noqa: E712
                        ResourcePlanAssignment.pinned_split == True,  # noqa: E712
                    ),
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
                ResourcePlanAssignment.pinned_employee == False,  # noqa: E712
                ResourcePlanAssignment.pinned_start == False,  # noqa: E712
                ResourcePlanAssignment.pinned_split == False,  # noqa: E712
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
                    # ОПЭ = 2 параллельные части: аналитик + разработчик.
                    # Гарантируем, что эти части идут на сотрудников из разных пулов
                    # и не совпадают по идентификатору; иначе обе строки бьются
                    # в один и тот же `remaining[emp]` и выглядят как один отрезок.
                    opo_analyst_pool = [
                        e.id for e in employees
                        if (e.role or "").lower() in ANALYST_ROLES
                    ]
                    opo_dev_pool = [
                        e.id for e in employees
                        if (e.role or "").lower() in DEV_ROLES
                    ]
                    analyst_id = assignments_by_role["analyst"].get(item.id)
                    dev_id = assignments_by_role["dev"].get(item.id)

                    # Аналитика для ОПЭ — только из аналитического пула.
                    if (not analyst_id or analyst_id not in opo_analyst_pool) and opo_analyst_pool:
                        analyst_id = min(
                            opo_analyst_pool,
                            key=lambda eid: -sum(remaining.get(eid, {}).values()),
                        )

                    # Разработчика для ОПЭ — только из dev пула и обязательно
                    # отличного от аналитика.
                    dev_candidates = [x for x in opo_dev_pool if x != analyst_id]
                    if (not dev_id or dev_id not in opo_dev_pool or dev_id == analyst_id) and dev_candidates:
                        dev_id = min(
                            dev_candidates,
                            key=lambda eid: -sum(remaining.get(eid, {}).values()),
                        )

                    parts = self._opo_split(item, analyst_id, dev_id)
                    last_end: Optional[date] = None
                    opo_involvement = self._involvement_for_phase(item, "opo")
                    opo_daily_cap = self._daily_role_capacity(
                        avail_hours=8.0,
                        involvement=opo_involvement,
                        parallel_count=1,
                    )
                    for emp_id, p_hours in parts:
                        if not emp_id or p_hours <= 0:
                            continue
                        segments = self._allocate_hours(
                            emp_id, p_hours, earliest_start, q_end, remaining,
                            daily_capacity=opo_daily_cap,
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

                # Дневная ёмкость фазы для сотрудника (involvement × parallel).
                phase_involvement = self._involvement_for_phase(item, phase)
                phase_daily_cap = self._daily_role_capacity(
                    avail_hours=8.0,
                    involvement=phase_involvement,
                    parallel_count=parallel_n,
                )

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
                            employee_id, chunk_hours, chunk_start, q_end, remaining,
                            daily_capacity=phase_daily_cap,
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
                    employee_id, hours, earliest_start, alloc_deadline, remaining,
                    daily_capacity=phase_daily_cap,
                )

                # Если жёсткое окно из Jira (duration/involvement) не вмещает
                # часы — расширяем deadline до конца квартала, чтобы фаза не
                # пропала из расписания. Перегрузку зафиксирует RCPSP-leveler.
                if jira_cal_set and not segments and hours > 0:
                    segments = self._allocate_hours(
                        employee_id, hours, earliest_start, q_end, remaining,
                        daily_capacity=phase_daily_cap,
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

        # Получить ID новых назначений и восстановить рёбра предшественников
        # по логическим ключам, затем посеять дефолтную цепочку для первого
        # compute (когда снапшот пуст). Сдвиг по графу выполняем после.
        self.db.flush()
        self._restore_predecessors(new_assignments, pred_snapshot)
        self.db.flush()
        self._ensure_default_predecessors(plan_id, new_assignments)
        self.db.flush()
        preds = self._load_predecessors(plan_id)
        self._shift_to_obey_predecessors(new_assignments, preds, q_start, q_end)

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

        # Persist conflicts (Stage B): сначала агрегатор склеивает daily
        # OVERLOAD-события в диапазоны и проштамповывает шаблонные сообщения.
        from app.services.conflict_aggregator import aggregate_conflicts

        detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
        detected = aggregate_conflicts(detected, db_session=self.db)
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
        daily_capacity: Optional[float] = None,
    ) -> List[Tuple[date, date, float, int]]:
        """Распределить total_hours по рабочим дням начиная с earliest_start.

        Возвращает один сегмент (start, end, hours, 1) — единый бар фазы без
        разбиения на части. Часы по-прежнему распределяются только по дням с
        ненулевой доступностью (выходные/отсутствия пропускаются), но конечный
        бар покрывает диапазон от первого до последнего использованного дня
        одной непрерывной полосой.

        Если задан ``daily_capacity`` — за один день фаза не возьмёт больше
        этой величины, даже если у сотрудника свободно больше. Это удерживает
        длительность фазы в соответствии с коэф вовлечённости и предотвращает
        перегрузки от параллельных назначений.

        День занимается фазой целиком: следующая фаза того же сотрудника
        начинается со следующего дня, даже если involvement < 1 оставляет
        часть рабочего времени неиспользованной. Это сохраняет порядок
        приоритетов между инициативами одного исполнителя.

        involvement < 1 (через daily_capacity) растягивает фазу по календарю,
        но не позволяет другим фазам делить тот же день.
        """
        emp_days = remaining.get(employee_id, {})
        remaining_h = total_hours
        used_total = 0.0
        seg_start: Optional[date] = None
        seg_end: Optional[date] = None

        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            avail_h = emp_days.get(d, 0.0)
            cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
            if cap > 0:
                if seg_start is None:
                    seg_start = d
                used = min(cap, remaining_h)
                # Блокируем весь рабочий день сотрудника. used (≤ cap)
                # идёт в hours_allocated как фактически списанные часы;
                # неиспользованная часть дня (avail_h − used) не достанется
                # следующей фазе того же исполнителя.
                emp_days[d] = 0.0
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
    # Phase predecessor graph (свободный граф зависимостей)
    # ------------------------------------------------------------------

    def _snapshot_predecessors(
        self, plan_id: str
    ) -> List[Tuple[Tuple[str, str, int, Optional[str]], Tuple[str, str, int, Optional[str]]]]:
        """Снимок рёбер графа предшественников плана как пары логических ключей.

        Ключ: (backlog_item_id, phase, part_number, employee_id). После удаления
        и пересоздания назначений рёбра восстанавливаются по этим ключам.
        """
        from app.models import PhasePredecessor

        rows = (
            self.db.execute(
                select(PhasePredecessor)
                .join(
                    ResourcePlanAssignment,
                    PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
                )
                .where(ResourcePlanAssignment.plan_id == plan_id)
            )
            .scalars()
            .all()
        )
        if not rows:
            return []
        plan_assignments = (
            self.db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == plan_id
                )
            )
            .scalars()
            .all()
        )
        by_id = {a.id: a for a in plan_assignments}
        snap: List[Tuple[Tuple[str, str, int, Optional[str]], Tuple[str, str, int, Optional[str]]]] = []
        for r in rows:
            s = by_id.get(r.successor_assignment_id)
            p = by_id.get(r.predecessor_assignment_id)
            if not s or not p:
                continue
            snap.append(
                (
                    (s.backlog_item_id, s.phase, s.part_number, s.employee_id),
                    (p.backlog_item_id, p.phase, p.part_number, p.employee_id),
                )
            )
        return snap

    def _restore_predecessors(
        self,
        assignments: List[ResourcePlanAssignment],
        snapshot: List[
            Tuple[Tuple[str, str, int, Optional[str]], Tuple[str, str, int, Optional[str]]]
        ],
    ) -> None:
        """Воссоздать рёбра PhasePredecessor по снимку логических ключей."""
        if not snapshot:
            return
        from app.models import PhasePredecessor

        by_key: Dict[Tuple[str, str, int, Optional[str]], ResourcePlanAssignment] = {}
        for a in assignments:
            key = (a.backlog_item_id, a.phase, a.part_number, a.employee_id)
            by_key[key] = a
        seen: set[Tuple[str, str]] = set()
        for succ_key, pred_key in snapshot:
            s = by_key.get(succ_key)
            p = by_key.get(pred_key)
            if not s or not p or not s.id or not p.id or s.id == p.id:
                continue
            pair = (s.id, p.id)
            if pair in seen:
                continue
            seen.add(pair)
            self.db.add(
                PhasePredecessor(
                    successor_assignment_id=s.id,
                    predecessor_assignment_id=p.id,
                )
            )

    def _ensure_default_predecessors(
        self,
        plan_id: str,
        assignments: List[ResourcePlanAssignment],
    ) -> None:
        """Посеять дефолтную цепочку analyst→dev→qa→opo если рёбер ещё нет."""
        from app.models import PhasePredecessor

        existing = (
            self.db.execute(
                select(PhasePredecessor)
                .join(
                    ResourcePlanAssignment,
                    PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
                )
                .where(ResourcePlanAssignment.plan_id == plan_id)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            return
        by_item: Dict[str, Dict[str, ResourcePlanAssignment]] = defaultdict(dict)
        for a in assignments:
            # Несколько строк opo (analyst-кусок + dev-кусок) — берём последнюю,
            # дефолтная цепочка ссылается на одну строку фазы.
            by_item[a.backlog_item_id][a.phase] = a
        for phases in by_item.values():
            chain = [phases.get(p) for p in PHASE_ORDER if phases.get(p) is not None]
            for i in range(1, len(chain)):
                succ = chain[i]
                pred = chain[i - 1]
                if not succ or not pred or not succ.id or not pred.id:
                    continue
                self.db.add(
                    PhasePredecessor(
                        successor_assignment_id=succ.id,
                        predecessor_assignment_id=pred.id,
                    )
                )

    def _load_predecessors(self, plan_id: str) -> Dict[str, List[str]]:
        """Загрузить рёбра предшественников плана: {succ_id: [pred_id, ...]}."""
        from app.models import PhasePredecessor

        rows = (
            self.db.execute(
                select(PhasePredecessor)
                .join(
                    ResourcePlanAssignment,
                    PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
                )
                .where(ResourcePlanAssignment.plan_id == plan_id)
            )
            .scalars()
            .all()
        )
        out: Dict[str, List[str]] = defaultdict(list)
        for r in rows:
            out[r.successor_assignment_id].append(r.predecessor_assignment_id)
        return out

    def _topological_order(
        self,
        assignments: List[ResourcePlanAssignment],
        preds: Dict[str, List[str]],
    ) -> List[ResourcePlanAssignment]:
        """Kahn — топологическая сортировка по графу preds. Cycle → ValueError."""
        by_id: Dict[str, ResourcePlanAssignment] = {a.id: a for a in assignments if a.id}
        indeg: Dict[str, int] = {aid: 0 for aid in by_id}
        for succ_id, p_list in preds.items():
            if succ_id not in by_id:
                continue
            for p_id in p_list:
                if p_id in by_id:
                    indeg[succ_id] += 1
        queue = [aid for aid, d in indeg.items() if d == 0]
        result: List[ResourcePlanAssignment] = []
        while queue:
            aid = queue.pop(0)
            result.append(by_id[aid])
            for succ_id, p_list in preds.items():
                if succ_id not in by_id or aid not in p_list:
                    continue
                indeg[succ_id] -= 1
                if indeg[succ_id] == 0:
                    queue.append(succ_id)
        if len(result) != len(by_id):
            raise ValueError("phase predecessor cycle detected")
        return result

    def _shift_to_obey_predecessors(
        self,
        assignments: List[ResourcePlanAssignment],
        preds: Dict[str, List[str]],
        q_start: date,
        q_end: date,
    ) -> None:
        """Сдвинуть start/end по графу preds, сохраняя длительность фазы.

        Walks in topological order. Сдвиг применяется ТОЛЬКО для назначений
        с явными предшественниками — если у фазы preds=[], раскладку оставляет
        allocator (учитывает доступность сотрудника + порядок приоритета). Это
        важно: иначе topo-сдвиг втащил бы все analyst-фазы к q_start, наплодив
        перегрузок и сломав порядок приоритетов между инициативами.

        Двигает только тогда, когда start_date РАНЬШЕ требуемого preds (вперёд)
        или ПОЗЖЕ (назад) — для случая, когда пользователь rewires цепочку,
        делая фазу параллельной (qa→analyst вместо qa→dev). Pinned-start/
        Pinned-split не сдвигаются.
        """
        order = self._topological_order(assignments, preds)
        by_id = {a.id: a for a in assignments if a.id}
        for a in order:
            if a.pinned_start or a.pinned_split:
                continue
            if a.start_date is None or a.end_date is None:
                continue
            pred_ids = preds.get(a.id, [])
            if not pred_ids:
                # Без предшественников — оставляем allocator-выбор. Не двигаем
                # к q_start, чтобы не ломать порядок приоритетов.
                continue
            ends = [
                by_id[pid].end_date
                for pid in pred_ids
                if pid in by_id and by_id[pid].end_date
            ]
            if not ends:
                continue
            new_start = max(ends) + timedelta(days=1)
            if new_start == a.start_date:
                continue
            duration = (a.end_date - a.start_date).days
            if new_start > q_end:
                new_start = q_end
            a.start_date = new_start
            new_end = new_start + timedelta(days=duration)
            if new_end > q_end:
                new_end = q_end
            a.end_date = new_end

    def split_assignment(
        self,
        assignment_id: str,
        parts_hours: List[float],
        cascade: bool,
    ) -> Tuple[List[ResourcePlanAssignment], List[ResourcePlanAssignment]]:
        """Разбить single-part фазу на N частей. Возвращает (parts, cascaded).

        - parts_hours: список часов на каждую часть (2..10).
        - cascade=True: пропорционально дробит downstream-фазы того же item.
        - Сумма parts_hours должна совпадать с hours_allocated исходной фазы.
        - Каждый кусок наследует employee_id, помечается pinned_split=True.
        - Между частями ставятся PhasePredecessor part[i] ← part[i-1].
        """
        from app.models.phase_predecessor import PhasePredecessor

        a = self.db.get(ResourcePlanAssignment, assignment_id)
        if not a:
            raise ValueError("assignment not found")
        if a.part_number != 1:
            raise ValueError("can split only single-part phase")
        siblings_count = (
            self.db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == a.plan_id,
                    ResourcePlanAssignment.backlog_item_id == a.backlog_item_id,
                    ResourcePlanAssignment.phase == a.phase,
                )
            )
            .scalars()
            .all()
        )
        if len(siblings_count) > 1:
            raise ValueError("phase already split")
        if len(parts_hours) < 2 or len(parts_hours) > 10:
            raise ValueError("parts must be 2..10")
        total = float(a.hours_allocated or 0.0)
        if abs(sum(parts_hours) - total) > 0.01:
            raise ValueError(
                f"parts sum {sum(parts_hours)} != phase hours {total}"
            )

        plan_id = a.plan_id
        item_id = a.backlog_item_id
        phase = a.phase
        employee_id = a.employee_id
        start = a.start_date
        end = a.end_date

        self.db.delete(a)
        self.db.flush()

        parts: List[ResourcePlanAssignment] = []
        prev_id: Optional[str] = None
        # Поделить даты пропорционально часам, чтобы куски шли подряд.
        if start and end:
            total_days = max(1, (end - start).days + 1)
        else:
            total_days = 0
        cursor = start
        consumed_days = 0
        for idx, h in enumerate(parts_hours, start=1):
            ratio = h / total if total > 0 else 1.0 / len(parts_hours)
            seg_days = max(1, int(round(total_days * ratio)))
            if idx == len(parts_hours) and start and end:
                seg_end = end
            elif cursor and total_days > 0:
                seg_end = cursor + timedelta(days=seg_days - 1)
            else:
                seg_end = None
            p = ResourcePlanAssignment(
                plan_id=plan_id,
                backlog_item_id=item_id,
                phase=phase,
                employee_id=employee_id,
                part_number=idx,
                hours_allocated=float(h),
                start_date=cursor,
                end_date=seg_end,
                pinned_split=True,
                manual_edit_at=datetime.utcnow(),
            )
            self.db.add(p)
            self.db.flush()
            parts.append(p)
            if prev_id:
                self.db.add(
                    PhasePredecessor(
                        successor_assignment_id=p.id,
                        predecessor_assignment_id=prev_id,
                    )
                )
            prev_id = p.id
            consumed_days += seg_days
            if seg_end:
                cursor = seg_end + timedelta(days=1)

        cascaded: List[ResourcePlanAssignment] = []
        if cascade:
            cascaded = self._cascade_split(item_id, phase, parts_hours, parts)

        # Пометить план stale, чтобы фронт показал необходимость пересчёта.
        plan = self.db.get(ResourcePlan, plan_id)
        if plan:
            plan.status = "stale"
        self.db.commit()
        return parts, cascaded

    def _cascade_split(
        self,
        item_id: str,
        source_phase: str,
        proportions: List[float],
        source_parts: List[ResourcePlanAssignment],
    ) -> List[ResourcePlanAssignment]:
        """Пропорционально разбить downstream-фазы того же item.

        Каждая часть K новой downstream-фазы зависит от части K source-фазы
        (PhasePredecessor) и от части K-1 той же фазы (последовательность).
        """
        from app.models.phase_predecessor import PhasePredecessor

        total_src = sum(proportions)
        if total_src <= 0:
            return []
        ratios = [p / total_src for p in proportions]
        try:
            src_idx = PHASE_ORDER.index(source_phase)
        except ValueError:
            return []
        downstream = PHASE_ORDER[src_idx + 1 :]
        cascaded: List[ResourcePlanAssignment] = []
        for phase in downstream:
            existing = (
                self.db.execute(
                    select(ResourcePlanAssignment).where(
                        ResourcePlanAssignment.backlog_item_id == item_id,
                        ResourcePlanAssignment.phase == phase,
                    )
                )
                .scalars()
                .all()
            )
            if len(existing) != 1:
                continue
            orig = existing[0]
            total_h = float(orig.hours_allocated or 0.0)
            if total_h <= 0:
                continue
            plan_id = orig.plan_id
            emp_id = orig.employee_id
            start = orig.start_date
            end = orig.end_date

            hours_parts: List[float] = []
            for r in ratios[:-1]:
                hours_parts.append(round(total_h * r, 2))
            hours_parts.append(round(total_h - sum(hours_parts), 2))

            self.db.delete(orig)
            self.db.flush()

            if start and end:
                total_days = max(1, (end - start).days + 1)
            else:
                total_days = 0
            cursor = start
            prev_id: Optional[str] = None
            for idx, (h, src) in enumerate(
                zip(hours_parts, source_parts), start=1
            ):
                ratio = h / total_h if total_h > 0 else 1.0 / len(hours_parts)
                seg_days = max(1, int(round(total_days * ratio)))
                if idx == len(hours_parts) and start and end:
                    seg_end = end
                elif cursor and total_days > 0:
                    seg_end = cursor + timedelta(days=seg_days - 1)
                else:
                    seg_end = None
                p = ResourcePlanAssignment(
                    plan_id=plan_id,
                    backlog_item_id=item_id,
                    phase=phase,
                    employee_id=emp_id,
                    part_number=idx,
                    hours_allocated=float(h),
                    start_date=cursor,
                    end_date=seg_end,
                    pinned_split=True,
                    manual_edit_at=datetime.utcnow(),
                )
                self.db.add(p)
                self.db.flush()
                cascaded.append(p)
                # ребро на одноимённый кусок source-фазы
                self.db.add(
                    PhasePredecessor(
                        successor_assignment_id=p.id,
                        predecessor_assignment_id=src.id,
                    )
                )
                if prev_id:
                    self.db.add(
                        PhasePredecessor(
                            successor_assignment_id=p.id,
                            predecessor_assignment_id=prev_id,
                        )
                    )
                prev_id = p.id
                if seg_end:
                    cursor = seg_end + timedelta(days=1)
        return cascaded

    def merge_assignment(self, assignment_id: str) -> ResourcePlanAssignment:
        """Слить все части одной (item, phase) обратно в одну строку."""
        a = self.db.get(ResourcePlanAssignment, assignment_id)
        if not a:
            raise ValueError("assignment not found")
        siblings = (
            self.db.execute(
                select(ResourcePlanAssignment)
                .where(
                    ResourcePlanAssignment.plan_id == a.plan_id,
                    ResourcePlanAssignment.backlog_item_id == a.backlog_item_id,
                    ResourcePlanAssignment.phase == a.phase,
                )
                .order_by(ResourcePlanAssignment.part_number)
            )
            .scalars()
            .all()
        )
        if len(siblings) <= 1:
            return a
        total_h = sum((s.hours_allocated or 0.0) for s in siblings)
        first = siblings[0]
        last = siblings[-1]
        first.part_number = 1
        first.hours_allocated = total_h
        first.pinned_split = False
        first.manual_edit_at = datetime.utcnow()
        if last.end_date and (first.end_date is None or last.end_date > first.end_date):
            first.end_date = last.end_date
        for s in siblings[1:]:
            self.db.delete(s)
        plan = self.db.get(ResourcePlan, a.plan_id)
        if plan:
            plan.status = "stale"
        self.db.commit()
        return first

    def add_predecessor(self, successor_id: str, predecessor_id: str) -> None:
        """Добавить ребро с проверкой на цикл. ValueError если цикл."""
        from app.models import PhasePredecessor

        existing = (
            self.db.execute(select(PhasePredecessor)).scalars().all()
        )
        edges: Dict[str, List[str]] = defaultdict(list)
        for e in existing:
            edges[e.successor_assignment_id].append(e.predecessor_assignment_id)
        edges[successor_id].append(predecessor_id)
        if self._has_cycle(edges):
            raise ValueError("cycle")
        self.db.add(
            PhasePredecessor(
                successor_assignment_id=successor_id,
                predecessor_assignment_id=predecessor_id,
            )
        )
        self.db.commit()

    def _has_cycle(self, edges: Dict[str, List[str]]) -> bool:
        """DFS-обход с тремя цветами; True если граф содержит цикл."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = defaultdict(lambda: WHITE)

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for nxt in edges.get(node, []):
                if color[nxt] == GRAY:
                    return True
                if color[nxt] == WHITE and dfs(nxt):
                    return True
            color[node] = BLACK
            return False

        nodes: set[str] = set(edges.keys())
        for vs in edges.values():
            nodes.update(vs)
        for n in nodes:
            if color[n] == WHITE and dfs(n):
                return True
        return False

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

        # Карты для resolve assignment → backlog_item / employee_id.
        assignment_by_id: Dict[str, ResourcePlanAssignment] = {
            a.id: a for a in assignments
        }
        emp_name_by_id: Dict[str, str] = {
            e.id: e.display_name or e.id for e in employees
        }

        def _emp_name(eid: Optional[str]) -> str:
            if not eid:
                return "сотрудник"
            return emp_name_by_id.get(eid, eid)

        # OVERLOAD_* + LEVELING_* from leveling events
        for ev in self._last_leveling_events:
            assignment = assignment_by_id.get(ev.assignment_id)
            bi_id = assignment.backlog_item_id if assignment else None
            assigned_emp = assignment.employee_id if assignment else None
            if ev.action == "escalate":
                pct = ev.overload_pct
                if pct > 120:
                    sev, type_ = "critical", "OVERLOAD_HIGH"
                elif pct > 110:
                    sev, type_ = "warning", "OVERLOAD_MED"
                else:
                    sev, type_ = "warning", "OVERLOAD_LIGHT"
                day = ev.affected_dates[0] if ev.affected_dates else None
                # employee_id берём с фактического исполнителя assignment.
                emp_id = assigned_emp
                emp_label = _emp_name(emp_id)
                result.append(
                    {
                        "type": type_,
                        "severity": sev,
                        "detection_key": f"{type_}:{ev.assignment_id}:{day}",
                        "message": f"{emp_label} перегружен {pct:.0f}% на {day}",
                        "metric_value": pct,
                        "assignment_id": ev.assignment_id,
                        "backlog_item_id": bi_id,
                        "employee_id": emp_id,
                        "window_start": _dt.combine(day, _dt.min.time())
                        if day
                        else None,
                        "window_end": _dt.combine(day, _dt.min.time()) if day else None,
                    }
                )
            elif ev.action == "delay":
                day = ev.affected_dates[0] if ev.affected_dates else None
                emp_label = _emp_name(assigned_emp)
                item_label = item_titles.get(bi_id, "") if bi_id else ""
                msg = (
                    f"«{item_label}» сдвинута на {ev.delta_days} д. для разрешения "
                    f"перегрузки {emp_label}"
                    if item_label
                    else f"Сдвиг на {ev.delta_days} д. для разрешения перегрузки {emp_label}"
                )
                result.append(
                    {
                        "type": "LEVELING_DELAY",
                        "severity": "info",
                        "detection_key": f"LEVELING_DELAY:{ev.assignment_id}:{day}",
                        "message": msg,
                        "metric_value": float(ev.delta_days),
                        "assignment_id": ev.assignment_id,
                        "backlog_item_id": bi_id,
                        "employee_id": assigned_emp,
                    }
                )
            elif ev.action == "reassign":
                from_label = _emp_name(ev.from_employee_id)
                to_label = _emp_name(ev.to_employee_id)
                item_label = item_titles.get(bi_id, "") if bi_id else ""
                msg = (
                    f"«{item_label}»: переназначено с {from_label} на {to_label}"
                    if item_label
                    else f"Переназначено с {from_label} на {to_label}"
                )
                result.append(
                    {
                        "type": "LEVELING_REASSIGN",
                        "severity": "info",
                        "detection_key": f"LEVELING_REASSIGN:{ev.assignment_id}",
                        "message": msg,
                        "assignment_id": ev.assignment_id,
                        "backlog_item_id": bi_id,
                        "employee_id": ev.to_employee_id,
                    }
                )

        return result
