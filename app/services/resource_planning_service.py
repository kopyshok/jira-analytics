"""Сервис ресурсного планирования — расписание фаз инициатив на квартал."""

from __future__ import annotations

import calendar as cal_module
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from sqlalchemy import and_, func, or_, select
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
from app.services.allocation_estimates import effective_estimate_hours
from app.services.rcpsp_leveler import RcpspLeveler

PHASE_ORDER = ["analyst", "dev", "qa", "opo"]
PHASE_HOURS_FIELD = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
}
DEFAULT_HOURS_PER_DAY = 6.0

# Preempting phases: разрывают чужие фазы того же сотрудника. На фронте/UX это
# означает, что Анализ/Разработка младших по приоритету задач показывают зазор
# = окно preempting-фазы старшей задачи. Конфиг-флаг — расширяется в будущем
# (например, "Приоритет"/"Важный" на любой фазе).
PREEMPTING_PHASES: set = {"opo"}

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

        Семантика pin-флагов:
        - `pinned_start` / `pinned_split` → даты/раскладка зафиксированы:
          строка не удаляется и не пересчитывается, бар остаётся в выбранном
          окне.
        - `pinned_employee` → зафиксирован только сотрудник; строка удаляется
          и пересоздаётся, но `pinned_map` сохраняет выбор исполнителя, а флаг
          восстанавливается на одноимённой фазе после пересчёта. Даты считаются
          заново — чтобы расписание реагировало на снятие предшественников и
          доступность исполнителя.
        """
        plan = self.db.get(ResourcePlan, plan_id)
        if not plan:
            raise ValueError(f"ResourcePlan {plan_id} not found")

        # Снимок логических ключей рёбер до удаления назначений (CASCADE
        # предшественников). После пересоздания назначений рёбра восстанавливаются
        # по (item_id, phase, part_number, employee_id).
        pred_snapshot = self._snapshot_predecessors(plan_id)

        # Какие (item_id, phase) имеют входящие рёбра в снапшоте. Используется
        # вместе с `user_touched_items_snapshot`: для user-touched инициатив
        # фаза без входящих рёбер игнорирует phase_end внутри PHASE_ORDER и
        # стартует с q_start — пользователь явно убрал предшественника,
        # значит должна искать ресурс с начала квартала.
        phases_with_inbound_pred: set[Tuple[str, str]] = {
            (succ_key[0], succ_key[1]) for succ_key, _ in pred_snapshot
        }

        # Снимок инициатив, где пользователь явно правил предшественников
        # (флаг `predecessors_user_set` хотя бы у одной фазы). Удаляемые
        # назначения теряют флаг → запоминаем на уровне инициативы и
        # передаём в default-seeder.
        user_touched_items_snapshot: set[str] = {
            r[0]
            for r in self.db.execute(
                select(ResourcePlanAssignment.backlog_item_id)
                .where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    ResourcePlanAssignment.predecessors_user_set == True,  # noqa: E712
                )
                .distinct()
            ).all()
        }

        # Семантика флагов:
        #   pinned_start / pinned_split — фиксируют ДАТЫ/раскладку: фаза не
        #     пересчитывается, бар остаётся в выбранном окне.
        #   pinned_employee — фиксирует только СОТРУДНИКА: даты считаются
        #     заново, чтобы расписание реагировало на снятие предшественников
        #     и доступность исполнителя.
        # Поэтому date-pinned строки сохраняем целиком, а employee-only —
        # удаляем и пересоздаём; map исполнителей + флаг pinned_employee
        # снимаем в снапшоты заранее.
        pinned_existing = list(
            self.db.execute(
                select(ResourcePlanAssignment).where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    or_(
                        ResourcePlanAssignment.pinned_start == True,  # noqa: E712
                        ResourcePlanAssignment.pinned_split == True,  # noqa: E712
                    ),
                )
            ).scalars()
        )
        # pinned_map — выбор сотрудника для любых пин-флагов (date или employee).
        pinned_emp_rows = self.db.execute(
            select(
                ResourcePlanAssignment.backlog_item_id,
                ResourcePlanAssignment.phase,
                ResourcePlanAssignment.part_number,
                ResourcePlanAssignment.employee_id,
            ).where(
                ResourcePlanAssignment.plan_id == plan_id,
                or_(
                    ResourcePlanAssignment.pinned_employee == True,  # noqa: E712
                    ResourcePlanAssignment.pinned_start == True,  # noqa: E712
                    ResourcePlanAssignment.pinned_split == True,  # noqa: E712
                ),
                ResourcePlanAssignment.employee_id.is_not(None),
            )
        ).all()
        pinned_map: Dict[Tuple[str, str, int], str] = {
            (r[0], r[1], r[2]): r[3] for r in pinned_emp_rows
        }
        # Снимок (item_id, phase) с employee-pin независимо от других флагов —
        # после пересоздания восстановим флаг pinned_employee. Иначе сценарий
        # «pinned_employee + pinned_start → пользователь снимает date-pin →
        # recompute» теряет pinned_employee (раньше выпадал из снапшота из-за
        # фильтра pinned_start == False).
        pinned_employee_phase_snapshot: set[Tuple[str, str]] = {
            (r[0], r[1])
            for r in self.db.execute(
                select(
                    ResourcePlanAssignment.backlog_item_id,
                    ResourcePlanAssignment.phase,
                )
                .where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    ResourcePlanAssignment.pinned_employee == True,  # noqa: E712
                )
                .distinct()
            ).all()
        }

        self.db.execute(
            ResourcePlanAssignment.__table__.delete().where(
                ResourcePlanAssignment.plan_id == plan_id,
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

        # {item_id: allocation} — чтобы пер-роль часы читались через
        # effective_estimate_hours (override приоритетнее BacklogItem).
        alloc_by_item = self._load_alloc_by_item(plan)

        q_start, q_end = self._quarter_bounds(plan)
        # Allow allocation to spill +1 month past quarter end.  Assignments
        # with seg_end > q_end (any boundary crossing) get out_of_quarter=True.
        q_end_extended = q_end + relativedelta(months=1)
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

        avail = self.build_availability(employees, q_start, q_end_extended, list(blocks))

        # Календарь рабочих часов БЕЗ сотрудника — для фазы QA (часы-only,
        # без employee_id). Используется чтобы пропускать выходные/праздники
        # при раскладке часов QA, иначе фаза «теряет» часы, попавшие на
        # нерабочие дни (см. баг ITL-304: 20 ч QA, окно Чт-Вс → 14.4 ч).
        qa_cal_rows = (
            self.db.execute(
                select(ProductionCalendarDay).where(
                    and_(
                        ProductionCalendarDay.date >= q_start,
                        ProductionCalendarDay.date <= q_end_extended,
                    )
                )
            )
            .scalars()
            .all()
        )
        qa_cal_anomalies = {row.date: row.hours for row in qa_cal_rows}
        def _qa_daily_hours(d: date) -> float:
            h = qa_cal_anomalies.get(d)
            if h is None:
                return DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0
            return h

        # Снимок изначальной доступности (до любого расхода) — нужен для
        # split-логики `_allocate_hours`: отличаем «день занят preempting-фазой»
        # от «день недоступен по календарю». Глубокая копия по дням.
        original_avail: Dict[str, Dict[date, float]] = {
            eid: dict(days) for eid, days in avail.items()
        }

        # Дни, занятые preempting-фазами (см. PREEMPTING_PHASES) — заполняются
        # по ходу планирования. Если такой день попадает внутрь обычной фазы
        # младшей задачи — фаза разрывается на видимые куски.
        preempt_locked: Dict[str, set] = {eid: set() for eid in avail.keys()}

        assignments_by_role = self._assign_employees(
            items, employees, pinned=pinned_map, alloc_by_item=alloc_by_item
        )

        # Mutable remaining hours copy
        remaining: Dict[str, Dict[date, float]] = {
            eid: dict(days) for eid, days in avail.items()
        }

        # Преварительно вычесть часы pinned-сегментов из remaining чтобы не
        # перегрузить тех же сотрудников при пересчёте non-pinned фаз.
        # pinned_split — только структурный маркер, дата НЕ зафиксирована
        # (см. _shift_to_obey_predecessors); часы такой строки разложит
        # отдельный re-distribute проход после шага shift, поэтому здесь её
        # часы не учитываем — иначе resource дважды списан с тех дней, где
        # фактической работы не будет.
        for a in pinned_existing:
            if not a.pinned_start:
                continue
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
                # Pinned preempting-фазы тоже разрывают чужие фазы.
                if a.phase in PREEMPTING_PHASES:
                    locked_set = preempt_locked.setdefault(a.employee_id, set())
                    d_lock = a.start_date
                    while d_lock <= a.end_date:
                        locked_set.add(d_lock)
                        d_lock += timedelta(days=1)

        new_assignments: List[ResourcePlanAssignment] = list(pinned_existing)

        # Скип фаз/частей которые уже зафиксированы pin'ом
        pinned_phase_keys = {
            (a.backlog_item_id, a.phase) for a in pinned_existing
        }

        # Phase 5: вычислить решения о сплите аналитических фаз до основного цикла.
        # _analyst_split_map: {(item_id, "analyst") → N кусков}
        # _analyst_first_chunk_end: {item_id → end_date первого куска} — заполняется
        # в ходе основного цикла, затем используется для earliest_start dev-фазы.
        _analyst_split_map = self._compute_legacy_split_map(items, employees, q_start, q_end_extended)
        _analyst_first_chunk_end: Dict[str, Optional[date]] = {}

        for item in items:
            phase_end: Optional[date] = None
            for phase in PHASE_ORDER:
                hours = self._phase_hours(item, phase, alloc_by_item)
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

                # Пользователь снял предшественников этой фазы → не цепляться
                # к концу предыдущей фазы PHASE_ORDER, искать ресурс с начала
                # квартала. Защищает от автоматического каскада analyst→dev,
                # когда пользователь явно отвязал Разработку от Анализа.
                if (
                    item.id in user_touched_items_snapshot
                    and (item.id, phase) not in phases_with_inbound_pred
                ):
                    earliest_start = q_start

                if phase == "qa":
                    # QA — часы-only, без сотрудника. Раскладываем часы по
                    # рабочим дням производственного календаря (выходные и
                    # праздники пропускаем), дневная ёмкость = календарь ×
                    # involvement_qa. Старая логика `ceil(hours/6)` считала
                    # календарными днями и теряла часы, попавшие на выходные;
                    # промежуточный фикс брал 8ч/день и расходился с explain
                    # (там «Доступно» = 8 × involvement_qa = 7.2).
                    qa_inv = self._involvement_for_phase(item, "qa") or 1.0
                    qa_daily: Dict[date, float] = {}
                    remaining_h = hours
                    cursor = earliest_start
                    while remaining_h > 0.001 and cursor <= q_end_extended:
                        cal_h = _qa_daily_hours(cursor)
                        avail_h = cal_h * qa_inv
                        if avail_h > 0:
                            take = min(remaining_h, avail_h)
                            qa_daily[cursor] = take
                            remaining_h -= take
                        cursor += timedelta(days=1)
                    if not qa_daily:
                        phase_end = earliest_start
                        continue
                    seg_start = min(qa_daily.keys())
                    seg_end = max(qa_daily.keys())
                    daily_json = json.dumps(
                        {d.isoformat(): h for d, h in qa_daily.items()}
                    )
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase="qa",
                        employee_id=None,
                        part_number=1,
                        hours_allocated=hours,
                        start_date=seg_start,
                        end_date=seg_end,
                        out_of_quarter=(seg_end > q_end),
                        daily_hours_json=daily_json,
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

                    parts = self._opo_split(item, analyst_id, dev_id, alloc_by_item)
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
                        segments, daily = self._allocate_hours_with_breakdown(
                            emp_id, p_hours, earliest_start, q_end_extended, remaining,
                            daily_capacity=opo_daily_cap,
                            preempt_locked=preempt_locked,
                            original_capacity=original_avail,
                        )
                        # ОПЭ — preempting-фаза: помечаем её дни в locked,
                        # чтобы фазы младших задач этого сотрудника разрывались.
                        if "opo" in PREEMPTING_PHASES:
                            locked_set = preempt_locked.setdefault(emp_id, set())
                            for seg_start, seg_end, _h, _p in segments:
                                d_lock = seg_start
                                while d_lock <= seg_end:
                                    locked_set.add(d_lock)
                                    d_lock += timedelta(days=1)
                        for seg_start, seg_end, seg_hours, part_num in segments:
                            seg_daily = {
                                d.isoformat(): h
                                for d, h in daily.items()
                                if seg_start <= d <= seg_end
                            }
                            a = ResourcePlanAssignment(
                                plan_id=plan_id,
                                backlog_item_id=item.id,
                                phase="opo",
                                employee_id=emp_id,
                                part_number=part_num,
                                hours_allocated=seg_hours,
                                start_date=seg_start,
                                end_date=seg_end,
                                out_of_quarter=(seg_end > q_end),
                                daily_hours_json=json.dumps(seg_daily) if seg_daily else None,
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
                        chunk_segs, chunk_daily = self._allocate_hours_with_breakdown(
                            employee_id, chunk_hours, chunk_start, q_end_extended, remaining,
                            daily_capacity=phase_daily_cap,
                            preempt_locked=preempt_locked,
                            original_capacity=original_avail,
                        )
                        for seg_start, seg_end, seg_hours, seg_part in chunk_segs:
                            # Encode chunk + inner preempt-split: chunk_idx*10+(seg_part-1)
                            # e.g. chunk 2 seg 1 → 20, chunk 2 seg 2 → 21; ensures unique part_number.
                            composite_part = chunk_idx * 10 + (seg_part - 1)
                            seg_daily = {
                                d.isoformat(): h
                                for d, h in chunk_daily.items()
                                if seg_start <= d <= seg_end
                            }
                            a = ResourcePlanAssignment(
                                plan_id=plan_id,
                                backlog_item_id=item.id,
                                phase=phase,
                                employee_id=employee_id,
                                part_number=composite_part,
                                hours_allocated=seg_hours,
                                start_date=seg_start,
                                end_date=seg_end,
                                out_of_quarter=(seg_end > q_end),
                                daily_hours_json=json.dumps(seg_daily) if seg_daily else None,
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
                # ceil вместо int: cal_days=2.5 должно дать 3 рабочих дня,
                # иначе alloc_deadline урежет часы (20ч/8 = 2.5 → 2 дня → 16ч).
                import math as _math
                cal_end = min(
                    _advance_working_days(earliest_start, int(_math.ceil(cal_days))),
                    q_end_extended,
                )
                alloc_deadline = cal_end if jira_cal_set else q_end_extended

                segments, phase_daily = self._allocate_hours_with_breakdown(
                    employee_id, hours, earliest_start, alloc_deadline, remaining,
                    daily_capacity=phase_daily_cap,
                    preempt_locked=preempt_locked,
                    original_capacity=original_avail,
                )

                # Если жёсткое окно из Jira (duration/involvement) не вмещает
                # ВСЕ часы — добираем остаток до конца расширенного окна. Перегрузку
                # зафиксирует RCPSP-leveler.
                allocated_h = sum(s[2] for s in segments)
                if jira_cal_set and allocated_h + 0.01 < hours:
                    deficit = hours - allocated_h
                    extra_start = (
                        (segments[-1][1] + timedelta(days=1))
                        if segments
                        else earliest_start
                    )
                    extra_segs, extra_daily = self._allocate_hours_with_breakdown(
                        employee_id, deficit, extra_start, q_end_extended, remaining,
                        daily_capacity=phase_daily_cap,
                        preempt_locked=preempt_locked,
                        original_capacity=original_avail,
                    )
                    if extra_segs:
                        # Сливаем в один сегмент start..extra_end с суммарными часами,
                        # чтобы остался единый бар; штриховка покажет пропуски внутри.
                        merged_start = segments[0][0] if segments else extra_segs[0][0]
                        merged_end = extra_segs[-1][1]
                        merged_h = allocated_h + sum(s[2] for s in extra_segs)
                        segments = [(merged_start, merged_end, merged_h, 1)]
                        phase_daily.update(extra_daily)

                effective_end = segments[-1][1] if segments else None

                for seg_start, seg_end, seg_hours, part_num in segments:
                    seg_daily = {
                        d.isoformat(): h
                        for d, h in phase_daily.items()
                        if seg_start <= d <= seg_end
                    }
                    a = ResourcePlanAssignment(
                        plan_id=plan_id,
                        backlog_item_id=item.id,
                        phase=phase,
                        employee_id=employee_id,
                        part_number=part_num,
                        hours_allocated=seg_hours,
                        start_date=seg_start,
                        end_date=seg_end,
                        out_of_quarter=(seg_end > q_end),
                        daily_hours_json=json.dumps(seg_daily) if seg_daily else None,
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
        # Восстановить флаг «пользователь явно правил связи» на хотя бы одной
        # фазе каждой такой инициативы — чтобы default-seeder её пропустил.
        if user_touched_items_snapshot:
            for a in new_assignments:
                if a.backlog_item_id in user_touched_items_snapshot:
                    a.predecessors_user_set = True
        # Восстановить pinned_employee на той же фазе инициативы:
        # employee-only пин не препятствует пересчёту дат, но должен сохраниться
        # при следующих compute, чтобы исполнитель не «отъехал» обратно к
        # автовыбору allocator-а.
        if pinned_employee_phase_snapshot:
            for a in new_assignments:
                if (a.backlog_item_id, a.phase) in pinned_employee_phase_snapshot:
                    a.pinned_employee = True
        self.db.flush()
        self._ensure_default_predecessors(plan_id, new_assignments)
        self.db.flush()
        preds = self._load_predecessors(plan_id)
        self._shift_to_obey_predecessors(new_assignments, preds, q_start, q_end_extended)

        # Pinned_split — только структурный маркер N частей. После shift его
        # start_date может попасть на выходной/отпуск; перераскладываем часы
        # через allocator. earliest_start считаем тем же образом, что в основном
        # цикле: max(pred ends)+1, либо q_start для user_touched инициатив без
        # входящих рёбер. pinned_start (явная заморозка даты) — обходим.
        by_id_for_split = {x.id: x for x in new_assignments if x.id}
        # Идём в топологическом порядке, чтобы part2 видела обновлённый
        # end_date part1, а qa в том же item — обновлённый end последней
        # части dev.
        split_order = self._topological_order(new_assignments, preds)
        for a in split_order:
            if not a.pinned_split or a.pinned_start:
                continue
            if not a.employee_id or not a.hours_allocated:
                continue
            if a.employee_id not in remaining:
                continue
            pred_ids = preds.get(a.id, [])
            pred_ends = [
                by_id_for_split[pid].end_date
                for pid in pred_ids
                if pid in by_id_for_split and by_id_for_split[pid].end_date
            ]
            if pred_ends:
                earliest = max(max(pred_ends) + timedelta(days=1), q_start)
            elif (
                a.backlog_item_id in user_touched_items_snapshot
                and (a.backlog_item_id, a.phase) not in phases_with_inbound_pred
            ):
                # Зеркалим main-loop (lines ~581-585): пользователь снял
                # предшественников у этой фазы → ищем ресурс с q_start, не
                # от старого a.start_date.
                earliest = q_start
            elif a.backlog_item_id in user_touched_items_snapshot:
                earliest = q_start
            elif a.start_date:
                earliest = a.start_date
            else:
                earliest = q_start
            segments, daily = self._allocate_hours_with_breakdown(
                a.employee_id,
                float(a.hours_allocated),
                earliest,
                q_end_extended,
                remaining,
                preempt_locked=preempt_locked,
                original_capacity=original_avail,
            )
            if not segments:
                continue
            new_start = segments[0][0]
            new_end = segments[-1][1]
            a.start_date = new_start
            a.end_date = new_end
            a.out_of_quarter = new_end > q_end
            a.daily_hours_json = (
                json.dumps({d.isoformat(): h for d, h in daily.items()})
                if daily
                else None
            )
            # Если есть последующие части той же фазы (предшественник=эта),
            # они процессятся ниже в том же цикле; их earliest подтянется к
            # обновлённому end_date через pred_ends. by_id_for_split уже
            # ссылается на эти объекты — изменения видны.

        # CPM на первичных датах
        self._compute_cpm(new_assignments, q_end_extended)

        # RCPSP-выравнивание перегрузок
        leveler = RcpspLeveler()
        role_pools = self._build_role_pools(employees)
        leveling_events = leveler.level(new_assignments, avail, q_end_extended, role_pools)
        # Always recompute CPM — leveling may have shifted dates; cheap O(N) anyway
        self._compute_cpm(new_assignments, q_end_extended)
        # Cache events for Stage B persist_conflicts
        self._last_leveling_events = leveling_events

        # Защитный clamp дат к рабочим дням: start_date/end_date не должны
        # попадать на выходные, праздники или дни с нулевой доступностью
        # (отпуска). Иначе бар визуально «вылазит» на выходные, что выглядит
        # неаккуратно. Источник правды — daily_hours_json (если есть) или
        # availability сотрудника.
        for a in new_assignments:
            if not a.start_date or not a.end_date:
                continue
            # 1. Предпочитаем границы из daily_hours_json (там только дни с часами).
            if a.daily_hours_json:
                try:
                    daily_keys = [
                        date.fromisoformat(k)
                        for k, v in json.loads(a.daily_hours_json).items()
                        if float(v) > 0.0
                    ]
                except (json.JSONDecodeError, ValueError):
                    daily_keys = []
                if daily_keys:
                    a.start_date = min(daily_keys)
                    a.end_date = max(daily_keys)
                    continue
            # 2. Fallback: подтянуть start вперёд / end назад к первому/
            #    последнему дню с avail > 0 для сотрудника.
            emp_avail = avail.get(a.employee_id, {}) if a.employee_id else {}
            if not emp_avail:
                continue
            s = a.start_date
            while s <= a.end_date and emp_avail.get(s, 0.0) <= 0.01:
                s += timedelta(days=1)
            e = a.end_date
            while e >= a.start_date and emp_avail.get(e, 0.0) <= 0.01:
                e -= timedelta(days=1)
            if s <= e:
                a.start_date = s
                a.end_date = e

        # Persist conflicts (Stage B): сначала агрегатор склеивает daily
        # OVERLOAD-события в диапазоны и проштамповывает шаблонные сообщения.
        from app.services.conflict_aggregator import aggregate_conflicts

        detected = self._build_conflict_dicts(plan, new_assignments, employees, q_end)
        detected = aggregate_conflicts(detected, db_session=self.db)
        self._persist_conflicts(plan_id, detected)

        plan.status = "ready"
        plan.computed_at = datetime.utcnow()
        self.db.commit()

    def _allocate_hours_with_breakdown(
        self,
        employee_id: str,
        total_hours: float,
        earliest_start: date,
        deadline: date,
        remaining: Dict[str, Dict[date, float]],
        daily_capacity: Optional[float] = None,
        preempt_locked: Optional[Dict[str, set]] = None,
        original_capacity: Optional[Dict[str, Dict[date, float]]] = None,
    ) -> Tuple[List[Tuple[date, date, float, int]], Dict[date, float]]:
        """Распределить total_hours по рабочим дням начиная с earliest_start.

        Возвращает (segments, daily_used) где:
        - segments — список (start, end, hours, part_number).  Когда
          preempt_locked прерывает текущий сегмент, закрывается и открывается
          новый с part_number+1.
        - daily_used — {date: hours} использованные часы по каждому дню.

        Если задан ``daily_capacity`` — за один день фаза не возьмёт больше
        этой величины.
        """
        _ = original_capacity  # unused; kept for future
        locked: set = (preempt_locked or {}).get(employee_id, set())
        emp_days = remaining.get(employee_id, {})
        remaining_h = total_hours
        daily_used: Dict[date, float] = {}

        segments: List[Tuple[date, date, float, int]] = []
        seg_start: Optional[date] = None
        seg_end: Optional[date] = None
        seg_hours = 0.0
        part_num = 1

        d = earliest_start
        while remaining_h > 0.01 and d <= deadline:
            # Preempting-locked day: close current segment, skip this day
            if d in locked:
                if seg_start is not None and seg_end is not None and seg_hours > 0:
                    segments.append((seg_start, seg_end, seg_hours, part_num))
                    part_num += 1
                    seg_start = None
                    seg_end = None
                    seg_hours = 0.0
                d += timedelta(days=1)
                continue

            avail_h = emp_days.get(d, 0.0)
            cap = avail_h if daily_capacity is None else min(avail_h, daily_capacity)
            if cap > 0:
                if seg_start is None:
                    seg_start = d
                used = min(cap, remaining_h)
                # Списываем фактически использованные часы, остаток дня доступен
                # последующим фазам того же сотрудника (e.g. involvement<1 фаза
                # отъела 4h из 8h — оставшиеся 4h должны достаться следующей
                # фазе). Точное распределение часов внутри дня хранится в
                # daily_hours_json для OVERLOAD-расчёта. Preempting-фазы (ОПЭ)
                # идут отдельным путём через preempt_locked.
                emp_days[d] = max(0.0, emp_days[d] - used)
                remaining_h -= used
                seg_hours += used
                daily_used[d] = used
                seg_end = d
            d += timedelta(days=1)

        if seg_start is not None and seg_end is not None and seg_hours > 0:
            segments.append((seg_start, seg_end, seg_hours, part_num))

        return segments, daily_used

    def _allocate_hours(
        self,
        employee_id: str,
        total_hours: float,
        earliest_start: date,
        deadline: date,
        remaining: Dict[str, Dict[date, float]],
        daily_capacity: Optional[float] = None,
        preempt_locked: Optional[Dict[str, set]] = None,
        original_capacity: Optional[Dict[str, Dict[date, float]]] = None,
    ) -> List[Tuple[date, date, float, int]]:
        """Обёртка над _allocate_hours_with_breakdown (backward compat)."""
        segs, _ = self._allocate_hours_with_breakdown(
            employee_id, total_hours, earliest_start, deadline, remaining,
            daily_capacity=daily_capacity,
            preempt_locked=preempt_locked,
            original_capacity=original_capacity,
        )
        return segs

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

    def _load_alloc_by_item(self, plan: ResourcePlan) -> Dict[str, ScenarioAllocation]:
        """{backlog_item_id: ScenarioAllocation} для included allocations плана.

        Нужно чтобы консьюмеры пер-роль часов читали override через
        effective_estimate_hours, а не сырые BacklogItem.estimate_*.
        """
        if not plan.scenario_id:
            return {}
        rows = (
            self.db.execute(
                select(ScenarioAllocation).where(
                    ScenarioAllocation.scenario_id == plan.scenario_id,
                    ScenarioAllocation.included_flag == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        return {a.backlog_item_id: a for a in rows}

    @staticmethod
    def _phase_hours(
        item: BacklogItem,
        phase: str,
        alloc_by_item: Dict[str, ScenarioAllocation],
    ) -> float:
        """Часы фазы: через effective если есть allocation, иначе из BacklogItem."""
        alloc = alloc_by_item.get(item.id)
        if alloc is not None:
            eff = effective_estimate_hours(alloc)
            return float(eff.get(phase, 0.0) or 0.0)
        return float(getattr(item, PHASE_HOURS_FIELD[phase], 0) or 0.0)

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
        alloc_by_item: Optional[Dict[str, ScenarioAllocation]] = None,
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
        alloc_by_item = alloc_by_item or {}

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
                load[analyst_id] += self._phase_hours(item, "analyst", alloc_by_item)
            result["analyst"][item.id] = analyst_id

            # ── dev ────────────────────────────────────────────────────
            dev_id: Optional[str] = pinned.get((item.id, "dev", 1))
            if not dev_id and dev_ids:
                dev_id = min(dev_ids, key=lambda eid: load[eid])
            if dev_id:
                load[dev_id] += self._phase_hours(item, "dev", alloc_by_item)
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
        alloc_by_item: Optional[Dict[str, ScenarioAllocation]] = None,
    ) -> List[Tuple[Optional[str], float]]:
        """ОПЭ → 2 куска: [(analyst_id, an_hours), (dev_id, dev_hours)].

        Доля аналитика = ``item.opo_analyst_ratio`` (default 0.5).
        Часы округляются до 2 знаков; сумма равна total (последний кусок добирает остаток).
        """
        total = self._phase_hours(item, "opo", alloc_by_item or {})
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
        Здесь `q_end` — обычно q_end_extended (q_end + 1 месяц), spillover в
        пределах extended-квартала — by design и не должен подсвечиваться как
        critical/LATE_START.
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
                # Строгое неравенство: фаза, заканчивающаяся ровно на дедлайне,
                # не considered critical. Slack < 0 = инициатива переползла за
                # q_end_extended и реально требует внимания.
                a.is_on_critical_path = slack < 0

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
        """Воссоздать рёбра PhasePredecessor по снимку логических ключей.

        Lookup в две фазы:
        1. Точный 4-tuple (item, phase, part, employee_id) — для opo, где две
           строки на инициативу различаются только сотрудником.
        2. Fallback 3-tuple (item, phase, part) — для случаев, когда фаза
           reassigned на другого сотрудника (allocator выбрал другого peer).
           Берём единственного кандидата по 3-tuple; для phase=opo
           пропускаем 3-tuple fallback (дубликаты разруливать нечем).
        """
        if not snapshot:
            return
        from app.models import PhasePredecessor

        by_key_4: Dict[Tuple[str, str, int, Optional[str]], ResourcePlanAssignment] = {}
        by_key_3: Dict[Tuple[str, str, int], List[ResourcePlanAssignment]] = (
            defaultdict(list)
        )
        for a in assignments:
            by_key_4[(a.backlog_item_id, a.phase, a.part_number, a.employee_id)] = a
            by_key_3[(a.backlog_item_id, a.phase, a.part_number)].append(a)

        def resolve(
            key: Tuple[str, str, int, Optional[str]],
        ) -> Optional[ResourcePlanAssignment]:
            hit = by_key_4.get(key)
            if hit:
                return hit
            item_id, phase, part, _emp = key
            if phase == "opo":
                # Дубли OPO без точного employee_id-матча не resolved безопасно.
                return None
            candidates = by_key_3.get((item_id, phase, part), [])
            if len(candidates) == 1:
                return candidates[0]
            return None

        existing_pairs = self.db.execute(
            select(
                PhasePredecessor.successor_assignment_id,
                PhasePredecessor.predecessor_assignment_id,
            )
        ).all()
        seen: set[Tuple[str, str]] = {(r[0], r[1]) for r in existing_pairs}
        for succ_key, pred_key in snapshot:
            s = resolve(succ_key)
            p = resolve(pred_key)
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
        """Посеять дефолтную цепочку analyst→dev→qa→opo пер-инициативно.

        Сеется на уровне КАЖДОЙ инициативы у которой нет ни одной входящей
        связи. Это важно для инициатив, добавленных позже через
        auto-sync `initiatives_rfa` — раньше ранний выход «есть хоть одна
        связь в плане» оставлял новые инициативы без цепочки.
        """
        from app.models import PhasePredecessor

        # Какие инициативы уже имеют входящие рёбра — их не трогаем.
        rows = (
            self.db.execute(
                select(
                    ResourcePlanAssignment.backlog_item_id,
                )
                .join(
                    PhasePredecessor,
                    PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
                )
                .where(ResourcePlanAssignment.plan_id == plan_id)
                .distinct()
            )
            .all()
        )
        items_with_edges: set[str] = {r[0] for r in rows}

        # Инициативы, где пользователь явно правил связи хотя бы у одной фазы
        # (например, удалил Анализ из предшественников Разработки). Не сеем
        # дефолты, иначе восстановим ту самую связь, которую он только что
        # снял.
        user_set_rows = (
            self.db.execute(
                select(ResourcePlanAssignment.backlog_item_id)
                .where(
                    ResourcePlanAssignment.plan_id == plan_id,
                    ResourcePlanAssignment.predecessors_user_set == True,  # noqa: E712
                )
                .distinct()
            )
            .all()
        )
        items_user_touched: set[str] = {r[0] for r in user_set_rows}

        # Существующие пары — защита от UNIQUE-конфликта на повторной вставке.
        existing_pairs: set[Tuple[str, str]] = {
            (r[0], r[1])
            for r in self.db.execute(
                select(
                    PhasePredecessor.successor_assignment_id,
                    PhasePredecessor.predecessor_assignment_id,
                )
            ).all()
        }

        by_item: Dict[str, Dict[str, ResourcePlanAssignment]] = defaultdict(dict)
        # Все строки фазы opo (analyst-кусок + dev-кусок) — обе должны
        # получить ребро qa→opo, иначе одна остаётся без предшественника
        # и стартует с q_start.
        opo_rows_by_item: Dict[str, List[ResourcePlanAssignment]] = defaultdict(list)
        for a in assignments:
            if a.phase == "opo":
                opo_rows_by_item[a.backlog_item_id].append(a)
            by_item[a.backlog_item_id][a.phase] = a
        for item_id, phases in by_item.items():
            if item_id in items_with_edges or item_id in items_user_touched:
                continue
            chain = [phases.get(p) for p in PHASE_ORDER if phases.get(p) is not None]
            for i in range(1, len(chain)):
                succ = chain[i]
                pred = chain[i - 1]
                if not succ or not pred or not succ.id or not pred.id:
                    continue
                # Для opo звена цепочки сеем ребро на ОБЕ opo-строки
                # (analyst-кусок + dev-кусок), иначе одна остаётся без preds.
                if succ.phase == "opo":
                    succ_rows = opo_rows_by_item.get(item_id, [succ])
                else:
                    succ_rows = [succ]
                for sr in succ_rows:
                    if not sr.id:
                        continue
                    pair = (sr.id, pred.id)
                    if pair in existing_pairs:
                        continue
                    existing_pairs.add(pair)
                    self.db.add(
                        PhasePredecessor(
                            successor_assignment_id=sr.id,
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
        делая фазу параллельной (qa→analyst вместо qa→dev). Pinned-start
        зафиксирован пользователем явно — не двигаем. Pinned-split — только
        структурный маркер «фаза разбита на части», даты должны течь по
        графу предшественников.
        """
        order = self._topological_order(assignments, preds)
        by_id = {a.id: a for a in assignments if a.id}
        for a in order:
            if a.pinned_start:
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
            delta = (new_start - a.start_date).days
            if new_start > q_end:
                new_start = q_end
            a.start_date = new_start
            new_end = new_start + timedelta(days=duration)
            if new_end > q_end:
                new_end = q_end
            a.end_date = new_end
            # Сдвинуть daily_hours_json вместе с датами, иначе защитный clamp
            # после CPM/leveler вернёт фазу на старые ключи дней.
            if a.daily_hours_json and delta != 0:
                try:
                    daily = json.loads(a.daily_hours_json)
                except json.JSONDecodeError:
                    daily = {}
                if daily:
                    shifted = {}
                    for k, v in daily.items():
                        try:
                            new_key = (
                                date.fromisoformat(k) + timedelta(days=delta)
                            ).isoformat()
                        except ValueError:
                            continue
                        shifted[new_key] = v
                    a.daily_hours_json = json.dumps(shifted) if shifted else None
            # Если фаза упёрлась в q_end — обрезать ключи JSON в окне
            # [new_start, new_end]. Иначе бар визуально выходит за квартал,
            # потому что в JSON остались дни после клампа.
            if a.daily_hours_json:
                try:
                    daily = json.loads(a.daily_hours_json)
                except json.JSONDecodeError:
                    daily = {}
                if daily:
                    trimmed = {}
                    for k, v in daily.items():
                        try:
                            d = date.fromisoformat(k)
                        except ValueError:
                            continue
                        if new_start <= d <= new_end:
                            trimmed[k] = v
                    if len(trimmed) != len(daily):
                        a.daily_hours_json = (
                            json.dumps(trimmed) if trimmed else None
                        )

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

        # Pre-check для cascade: downstream-фазы не должны быть уже разбиты
        # пользователем (part_number > 1), иначе _cascade_split их молча
        # скипает и пропорции расходятся. OPO структурно имеет 2 строки
        # (analyst-кусок + dev-кусок) с part_number=1 — это не split.
        if cascade:
            try:
                src_idx = PHASE_ORDER.index(a.phase)
            except ValueError:
                src_idx = -1
            if src_idx >= 0:
                downstream_split_phases: List[str] = []
                for ph in PHASE_ORDER[src_idx + 1 :]:
                    max_part = (
                        self.db.execute(
                            select(
                                func.max(ResourcePlanAssignment.part_number)
                            ).where(
                                ResourcePlanAssignment.plan_id == a.plan_id,
                                ResourcePlanAssignment.backlog_item_id
                                == a.backlog_item_id,
                                ResourcePlanAssignment.phase == ph,
                            )
                        )
                        .scalar()
                    )
                    if max_part and max_part > 1:
                        downstream_split_phases.append(ph)
                if downstream_split_phases:
                    raise ValueError(
                        "cascade blocked: downstream phases already split: "
                        + ",".join(downstream_split_phases)
                        + ". Merge them first or split source without cascade."
                    )

        plan_id = a.plan_id
        item_id = a.backlog_item_id
        phase = a.phase
        employee_id = a.employee_id
        start = a.start_date
        end = a.end_date

        # Снимок рёбер ДО удаления: при cascade-delete PhasePredecessor строки
        # уйдут, а потом надо восстановить как minimum связь
        # «внешний предшественник → part 1» и «last part → внешний successor»,
        # иначе фаза после split окажется без attachment к графу и встанет
        # на старую дату исходной строки.
        predecessor_ids_external = [
            r[0]
            for r in self.db.execute(
                select(PhasePredecessor.predecessor_assignment_id).where(
                    PhasePredecessor.successor_assignment_id == a.id
                )
            ).all()
        ]
        successor_ids_external = [
            r[0]
            for r in self.db.execute(
                select(PhasePredecessor.successor_assignment_id).where(
                    PhasePredecessor.predecessor_assignment_id == a.id
                )
            ).all()
        ]

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

        # Восстановить внешние рёбра: внешний предшественник → part 1,
        # last part → внешний successor.
        if parts and predecessor_ids_external:
            first_id = parts[0].id
            for pid in predecessor_ids_external:
                self.db.add(
                    PhasePredecessor(
                        successor_assignment_id=first_id,
                        predecessor_assignment_id=pid,
                    )
                )
        if parts and successor_ids_external:
            last_id = parts[-1].id
            for sid in successor_ids_external:
                self.db.add(
                    PhasePredecessor(
                        successor_assignment_id=sid,
                        predecessor_assignment_id=last_id,
                    )
                )

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
        """Слить все части одной (item, phase) обратно в одну строку.

        Внешние outbound-рёбра удаляемых siblings переносятся на first.id —
        иначе CASCADE при delete теряет связи вроде `dev-part-3 → qa-part-3`,
        и после merge от cascade-split остаётся только то, что выходило из
        первой части.
        """
        from app.models import PhasePredecessor

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
        sibling_ids = {s.id for s in siblings}
        deleted_ids = {s.id for s in siblings[1:]}

        # Снимок outbound-рёбер удаляемых siblings: куда они вели наружу
        # (за пределы текущей группы siblings). Перенесём на first.id.
        outbound = (
            self.db.execute(
                select(PhasePredecessor).where(
                    PhasePredecessor.predecessor_assignment_id.in_(deleted_ids)
                )
            )
            .scalars()
            .all()
        )
        # Уже существующие outbound first.id — чтобы не плодить дубли при дедупе.
        existing_first_out = (
            self.db.execute(
                select(PhasePredecessor.successor_assignment_id).where(
                    PhasePredecessor.predecessor_assignment_id == first.id
                )
            )
            .scalars()
            .all()
        )
        first_out_set = set(existing_first_out)
        new_targets: set[str] = set()
        for edge in outbound:
            succ = edge.successor_assignment_id
            # Внутренние рёбра между siblings уйдут вместе с CASCADE — пропускаем.
            if succ in sibling_ids:
                continue
            if succ in first_out_set or succ in new_targets:
                continue
            new_targets.add(succ)

        first.part_number = 1
        first.hours_allocated = total_h
        first.pinned_split = False
        first.manual_edit_at = datetime.utcnow()
        if last.end_date and (first.end_date is None or last.end_date > first.end_date):
            first.end_date = last.end_date
        for s in siblings[1:]:
            self.db.delete(s)
        self.db.flush()  # CASCADE удалит исходные outbound siblings'ов
        for succ in new_targets:
            self.db.add(
                PhasePredecessor(
                    successor_assignment_id=succ,
                    predecessor_assignment_id=first.id,
                )
            )
        plan = self.db.get(ResourcePlan, a.plan_id)
        if plan:
            plan.status = "stale"
        self.db.commit()
        return first

    def add_predecessor(self, successor_id: str, predecessor_id: str) -> None:
        """Добавить ребро с проверкой на цикл. ValueError если цикл.

        Коммитит сама. Для bulk-обновления (несколько рёбер одновременно)
        используй set_predecessors — она атомарна по всему набору.
        """
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

    def set_predecessors(
        self, successor_id: str, predecessor_ids: List[str]
    ) -> None:
        """Атомарно заменить весь набор предшественников у successor_id.

        Проверка цикла по полному prospective edge-set ДО вставки. Если цикл —
        ValueError, состояние БД не меняется. Коммитит сама.
        """
        from app.models import PhasePredecessor

        for pid in predecessor_ids:
            if pid == successor_id:
                raise ValueError("cycle: self-reference")

        existing = (
            self.db.execute(select(PhasePredecessor)).scalars().all()
        )
        edges: Dict[str, List[str]] = defaultdict(list)
        for e in existing:
            # Рёбра текущего successor исключаем — мы их заменяем целиком.
            if e.successor_assignment_id == successor_id:
                continue
            edges[e.successor_assignment_id].append(e.predecessor_assignment_id)
        # Полный prospective набор для successor_id
        for pid in predecessor_ids:
            edges[successor_id].append(pid)
        if self._has_cycle(edges):
            raise ValueError("cycle")

        # Только тут трогаем БД: удаляем старые, вставляем новые, один commit.
        self.db.execute(
            PhasePredecessor.__table__.delete().where(
                PhasePredecessor.successor_assignment_id == successor_id
            )
        )
        for pid in predecessor_ids:
            self.db.add(
                PhasePredecessor(
                    successor_assignment_id=successor_id,
                    predecessor_assignment_id=pid,
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
