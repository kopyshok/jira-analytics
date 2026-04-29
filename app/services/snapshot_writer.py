"""SnapshotWriter — заполнение всех snapshot-таблиц при создании ревизии сценария.

Один экземпляр = один проход. Все методы add()-ят строки в сессию;
commit делает вызывающий код.
"""
import calendar
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Absence,
    AbsenceReason,
    BacklogItem,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    Role,
    ScenarioAllocation,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioAllocationSnapshot,
    ScenarioCalendarSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioDictionarySnapshot,
    ScenarioNormSnapshot,
    ScenarioRevision,
    ScenarioRule,
    ScenarioRulesSnapshot,
    ScenarioTeamSnapshot,
)
from app.services.capacity_service import QUARTER_MONTHS


def _split_proportional(total: float, weights: list[float]) -> list[float]:
    """Делит total по весам пропорционально; последний элемент компенсирует ошибку округления.

    Если sum(weights) == 0 — равномерный split. sum(result) == total точно.
    """
    n = len(weights)
    if n == 0:
        return []
    s = sum(weights)
    if s <= 0:
        # равномерный split
        equal = round(total / n, 2)
        return [equal] * (n - 1) + [round(total - equal * (n - 1), 2)]
    out: list[float] = []
    accumulated = 0.0
    for i, w in enumerate(weights):
        if i == n - 1:
            out.append(round(total - accumulated, 2))
        else:
            v = round(total * w / s, 2)
            out.append(v)
            accumulated += v
    return out


def _quarter_bounds(year: int, quarter_str: str) -> tuple[date, date]:
    """Возвращает первый и последний день квартала.

    quarter_str — `Q1`/`Q2`/`Q3`/`Q4` или просто `1`/`2`/`3`/`4`.
    """
    q = int(str(quarter_str).replace("Q", ""))
    months = QUARTER_MONTHS[q]
    start = date(year, months[0], 1)
    end_day = calendar.monthrange(year, months[-1])[1]
    end = date(year, months[-1], end_day)
    return start, end


class SnapshotWriter:
    def __init__(self, db: Session):
        self.db = db

    def write_team_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot активных сотрудников команды сценария.

        Копирует display_name, role, hours_per_day=8.0, is_active.
        Если у сценария нет team или в команде нет сотрудников — ничего не пишет.
        """
        if not scenario.team:
            return
        employees = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(
                EmployeeTeam.team == scenario.team,
                Employee.is_active.is_(True),
            )
            .all()
        )
        for emp in employees:
            self.db.add(
                ScenarioTeamSnapshot(
                    revision_id=revision.id,
                    employee_id=emp.id,
                    display_name=emp.display_name,
                    role=emp.role,
                    hours_per_day=8.0,
                    is_active=bool(emp.is_active),
                    is_external=False,
                )
            )

    def write_calendar_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot производственного календаря квартала per-day.

        Берёт все ProductionCalendarDay в диапазоне [start, end] квартала
        сценария, копирует date/hours/is_workday/kind. Если у сценария нет
        year или quarter — ничего не пишет.
        """
        if not (scenario.year and scenario.quarter):
            return
        start, end = _quarter_bounds(scenario.year, scenario.quarter)
        days = (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= start,
                ProductionCalendarDay.date <= end,
            )
            .all()
        )
        for d in days:
            self.db.add(
                ScenarioCalendarSnapshot(
                    revision_id=revision.id,
                    date=d.date,
                    hours=float(d.hours),
                    is_workday=bool(d.is_workday),
                    kind=d.kind,
                )
            )

    def write_rules_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot scenario_rules сценария.

        Копирует role, work_type_id, pct_of_norm. Резолвит work_type_label
        одним батчевым запросом по всем используемым work_type_id.
        Если у сценария нет правил — ничего не пишет.
        """
        rules = (
            self.db.query(ScenarioRule)
            .filter(ScenarioRule.scenario_id == scenario.id)
            .all()
        )
        if not rules:
            return
        wt_ids = {r.work_type_id for r in rules if r.work_type_id}
        wt_label_by_id: dict[str, str] = {}
        if wt_ids:
            wt_label_by_id = {
                wt.id: wt.label
                for wt in self.db.query(MandatoryWorkType)
                .filter(MandatoryWorkType.id.in_(wt_ids))
                .all()
            }
        for r in rules:
            self.db.add(
                ScenarioRulesSnapshot(
                    revision_id=revision.id,
                    role=r.role,
                    work_type_id=r.work_type_id,
                    work_type_label=wt_label_by_id.get(r.work_type_id, ""),
                    pct_of_norm=float(r.percent_of_norm),
                )
            )

    def write_dictionary_snapshot(self, revision: ScenarioRevision) -> None:
        """Snapshot всех записей справочников (work_types, roles, absence_reasons).

        Копируются все записи (включая неактивные) — чтобы ревизия оставалась
        читаемой при удалении/переименовании оригиналов.
        """
        for wt in self.db.query(MandatoryWorkType).all():
            self.db.add(
                ScenarioDictionarySnapshot(
                    revision_id=revision.id,
                    kind="work_type",
                    original_id=wt.id,
                    code=wt.code,
                    label=wt.label,
                    sort_order=wt.sort_order,
                    extra_json={
                        "subtracts_from_pool": bool(wt.subtracts_from_pool),
                        "is_active": bool(wt.is_active),
                    },
                )
            )
        for role in self.db.query(Role).all():
            self.db.add(
                ScenarioDictionarySnapshot(
                    revision_id=revision.id,
                    kind="role",
                    original_id=role.id,
                    code=role.code,
                    label=role.label,
                    sort_order=role.sort_order,
                    extra_json={"is_active": bool(role.is_active)},
                )
            )
        for ar in self.db.query(AbsenceReason).all():
            self.db.add(
                ScenarioDictionarySnapshot(
                    revision_id=revision.id,
                    kind="absence_reason",
                    original_id=ar.id,
                    code=ar.code,
                    label=ar.label,
                    sort_order=ar.sort_order,
                    extra_json={
                        "is_planned": bool(ar.is_planned),
                        "color": ar.color,
                        "is_active": bool(ar.is_active),
                    },
                )
            )

    def write_capacity_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot capacity: gross/absence/available/mandatory/project per emp × month.

        Для каждого активного сотрудника команды сценария и каждого месяца квартала
        считает часы по производственному календарю с вычетом отсутствий и
        обязательных работ (subtracts_from_pool=True).
        """
        if not (scenario.team and scenario.year and scenario.quarter):
            return

        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]

        # Активные сотрудники команды
        employees = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(
                EmployeeTeam.team == scenario.team,
                Employee.is_active.is_(True),
            )
            .all()
        )
        if not employees:
            return

        # Производственный календарь за весь квартал
        start, end = _quarter_bounds(scenario.year, scenario.quarter)
        cal_days = (
            self.db.query(ProductionCalendarDay)
            .filter(
                ProductionCalendarDay.date >= start,
                ProductionCalendarDay.date <= end,
            )
            .all()
        )
        cal_by_date: dict[date, float] = {d.date: float(d.hours) for d in cal_days}

        # Отсутствия сотрудников команды за период
        emp_ids = [e.id for e in employees]
        absences = (
            self.db.query(Absence)
            .filter(
                Absence.employee_id.in_(emp_ids),
                Absence.start_date <= end,
                Absence.end_date >= start,
            )
            .all()
        )
        abs_by_emp: dict[str, list[tuple[date, date]]] = {}
        for a in absences:
            abs_by_emp.setdefault(a.employee_id, []).append((a.start_date, a.end_date))

        # Правила сценария: sum pct mandatory per role (только subtracts_from_pool)
        rules = (
            self.db.query(ScenarioRule)
            .filter(ScenarioRule.scenario_id == scenario.id)
            .all()
        )
        wt_subtracts: dict[str, bool] = {}
        if rules:
            wt_ids = {r.work_type_id for r in rules if r.work_type_id}
            if wt_ids:
                for wt in (
                    self.db.query(MandatoryWorkType)
                    .filter(MandatoryWorkType.id.in_(wt_ids))
                    .all()
                ):
                    wt_subtracts[wt.id] = bool(wt.subtracts_from_pool)

        def _sum_pct(role: str | None) -> float:
            return sum(
                r.percent_of_norm for r in rules
                if (r.role is None or r.role == role)
                and wt_subtracts.get(r.work_type_id, False)
            )

        now = datetime.utcnow()
        for emp in employees:
            pct_mandatory = _sum_pct(emp.role)
            emp_abs = abs_by_emp.get(emp.id, [])
            for month in months:
                month_start = date(scenario.year, month, 1)
                last_day = calendar.monthrange(scenario.year, month)[1]
                month_end = date(scenario.year, month, last_day)

                gross = 0.0
                absence_hrs = 0.0
                cur = month_start
                while cur <= month_end:
                    day_h = cal_by_date.get(cur, 0.0)
                    if day_h > 0:
                        # hours_per_day coefficient (day_h × emp.hours_per_day / 8) опущен:
                        # Employee пока не имеет hours_per_day, все работают по 8ч.
                        # Вернуть когда появится part-time поддержка.
                        gross += day_h
                        if any(s <= cur <= e for s, e in emp_abs):
                            absence_hrs += day_h
                    cur += timedelta(days=1)

                available = max(0.0, gross - absence_hrs)
                mandatory = round(available * pct_mandatory / 100, 2)
                project = round(max(0.0, available - mandatory), 2)

                self.db.add(
                    ScenarioCapacitySnapshot(
                        revision_id=revision.id,
                        employee_id=emp.id,
                        employee_name=emp.display_name,
                        year=scenario.year,
                        month=month,
                        norm_hours=round(gross, 2),
                        available_hours=round(available, 2),
                        backlog_pool_hours=None,  # deprecated в v2 — читать project_hours
                        gross_hours=round(gross, 2),
                        absence_hours=round(absence_hrs, 2),
                        mandatory_hours=mandatory,
                        project_hours=project,
                        snapshot_taken_at=now,
                    )
                )

    def write_norm_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Норм. часы = available × pct правила; для внешнего QA — отдельные строки.

        Читает available_hours из уже записанных ScenarioCapacitySnapshot строк
        (revision_id=revision.id) — вызывать после write_capacity_snapshot.
        Для внешнего QA (scenario.external_qa_hours > 0) добавляет строки
        с employee_id=None, is_external=True для каждого правила роли qa.
        """
        if not (scenario.team and scenario.year and scenario.quarter):
            return

        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]

        # Flush pending inserts so capacity rows are visible to the SELECT below.
        self.db.flush()

        # available_hours per emp×month — из уже записанных capacity snapshots
        cap_rows = (
            self.db.query(ScenarioCapacitySnapshot)
            .filter_by(revision_id=revision.id)
            .all()
        )
        available_by_emp_month: dict[tuple[str, int], float] = {
            (r.employee_id, r.month): float(r.available_hours)
            for r in cap_rows if r.employee_id
        }

        # Активные сотрудники команды
        employees = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(
                EmployeeTeam.team == scenario.team,
                Employee.is_active.is_(True),
            )
            .all()
        )

        # Правила сценария + work_type labels
        rules = (
            self.db.query(ScenarioRule)
            .filter(ScenarioRule.scenario_id == scenario.id)
            .all()
        )
        if not rules and (
            scenario.external_qa_hours is None or float(scenario.external_qa_hours or 0) <= 0
        ):
            return
        wt_label_by_id: dict[str, str] = {}
        if rules:
            wt_ids = {r.work_type_id for r in rules if r.work_type_id}
            if wt_ids:
                for wt in (
                    self.db.query(MandatoryWorkType)
                    .filter(MandatoryWorkType.id.in_(wt_ids))
                    .all()
                ):
                    wt_label_by_id[wt.id] = wt.label

        # 1. Штатные сотрудники
        for emp in employees:
            emp_role = emp.role
            for month in months:
                available = available_by_emp_month.get((emp.id, month), 0.0)
                for r in rules:
                    if r.role is None or r.role == emp_role:
                        norm = round(available * r.percent_of_norm / 100, 2)
                        self.db.add(
                            ScenarioNormSnapshot(
                                revision_id=revision.id,
                                employee_id=emp.id,
                                employee_name=emp.display_name,
                                role=emp_role,
                                year=scenario.year,
                                month=month,
                                work_type_id=r.work_type_id,
                                work_type_label=wt_label_by_id.get(r.work_type_id, ""),
                                norm_hours=norm,
                                is_external=False,
                            )
                        )

        # 2. Внешний QA
        if scenario.external_qa_hours is not None and float(scenario.external_qa_hours) > 0:
            ext_per_month = float(scenario.external_qa_hours) / len(months)
            qa_rules = [r for r in rules if r.role == "qa"]
            for month in months:
                for r in qa_rules:
                    norm = round(ext_per_month * r.percent_of_norm / 100, 2)
                    self.db.add(
                        ScenarioNormSnapshot(
                            revision_id=revision.id,
                            employee_id=None,
                            employee_name="(внешний QA)",
                            role="qa",
                            year=scenario.year,
                            month=month,
                            work_type_id=r.work_type_id,
                            work_type_label=wt_label_by_id.get(r.work_type_id, ""),
                            norm_hours=norm,
                            is_external=True,
                        )
                    )

    def write_allocation_snapshot(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Snapshot включённых allocations сценария с копией атрибутов BacklogItem.

        Для каждой ScenarioAllocation с included_flag=True данного сценария
        копирует все поля BacklogItem (title, issue_id, project_id, customer,
        cost_type, impact, risk, priority, estimate_*_hours, opo_analyst_ratio,
        assignee_employee_id) и поля allocation (allocation_id, backlog_item_id,
        sort_order, included_flag, involvement_coefficient).

        assignee_role_at_approval резолвится одним батчевым запросом по всем
        assignee_employee_id.

        Allocations с included_flag=False не попадают в snapshot.
        """
        rows = (
            self.db.query(ScenarioAllocation, BacklogItem)
            .join(BacklogItem, BacklogItem.id == ScenarioAllocation.backlog_item_id)
            .filter(
                ScenarioAllocation.scenario_id == scenario.id,
                ScenarioAllocation.included_flag.is_(True),
            )
            .all()
        )
        if not rows:
            return

        # Батчевый запрос ролей по всем assignee_employee_id
        assignee_ids = {
            bi.assignee_employee_id
            for _, bi in rows
            if bi.assignee_employee_id
        }
        role_by_employee_id: dict[str, str | None] = {}
        if assignee_ids:
            for emp in (
                self.db.query(Employee)
                .filter(Employee.id.in_(assignee_ids))
                .all()
            ):
                role_by_employee_id[emp.id] = emp.role

        for alloc, bi in rows:
            self.db.add(
                ScenarioAllocationSnapshot(
                    revision_id=revision.id,
                    allocation_id=alloc.id,
                    backlog_item_id=bi.id,
                    sort_order=alloc.sort_order,
                    included_flag=True,
                    involvement_coefficient=alloc.involvement_coefficient,
                    title=bi.title,
                    issue_id=bi.issue_id,
                    project_id=bi.project_id,
                    customer=bi.customer,
                    cost_type=bi.cost_type,
                    impact=bi.impact,
                    risk=bi.risk,
                    priority=bi.priority,
                    estimate_analyst_hours=bi.estimate_analyst_hours,
                    estimate_dev_hours=bi.estimate_dev_hours,
                    estimate_qa_hours=bi.estimate_qa_hours,
                    estimate_opo_hours=bi.estimate_opo_hours,
                    opo_analyst_ratio=bi.opo_analyst_ratio,
                    assignee_employee_id=bi.assignee_employee_id,
                    assignee_role_at_approval=role_by_employee_id.get(
                        bi.assignee_employee_id
                    ) if bi.assignee_employee_id else None,
                )
            )

    def write_allocation_breakdown(
        self, revision: ScenarioRevision, scenario: PlanningScenario
    ) -> None:
        """Помесячный сплит каждого allocation по ролям и сотрудникам.

        Для каждого included allocation вычисляет квартальные часы по ролям
        (analyst/consultant/RP/dev/qa), затем делит их по месяцам пропорционально
        available_hours из ScenarioCapacitySnapshot (уже записанного ранее).
        Вызывать после write_capacity_snapshot и write_allocation_snapshot.
        """
        if not (scenario.team and scenario.year and scenario.quarter):
            return

        q = int(str(scenario.quarter).replace("Q", ""))
        months = QUARTER_MONTHS[q]

        # Flush pending inserts so capacity rows are visible to the SELECT below.
        self.db.flush()

        # available_hours per emp×month из уже записанных capacity snapshots
        cap_rows = (
            self.db.query(ScenarioCapacitySnapshot)
            .filter_by(revision_id=revision.id)
            .all()
        )
        avail_emp_month: dict[tuple[str, int], float] = {
            (r.employee_id, r.month): float(r.available_hours)
            for r in cap_rows if r.employee_id
        }

        # Активные сотрудники команды
        emp_ids = [
            r[0] for r in self.db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team == scenario.team).all()
        ]
        employees = (
            self.db.query(Employee)
            .filter(Employee.id.in_(emp_ids), Employee.is_active.is_(True))
            .all()
        ) if emp_ids else []

        devs = [e for e in employees if e.role == "dev"]
        qas = [e for e in employees if e.role == "qa"]
        rps = [e for e in employees if e.role == "RP"]
        rp_emp_id = sorted(rps, key=lambda e: e.display_name)[0].id if rps else None

        def _avail_role_month(role_emps: list[Employee], month: int) -> float:
            return sum(avail_emp_month.get((e.id, month), 0.0) for e in role_emps)

        def _split_emp(total: float, emp_id: str | None) -> list[float]:
            if total == 0:
                return [0.0] * len(months)
            if emp_id is None:
                return _split_proportional(total, [1.0] * len(months))
            return _split_proportional(
                total, [avail_emp_month.get((emp_id, m), 0.0) for m in months]
            )

        def _split_pool(total: float, role_emps: list[Employee]) -> list[float]:
            if total == 0:
                return [0.0] * len(months)
            return _split_proportional(
                total, [_avail_role_month(role_emps, m) for m in months]
            )

        # Все included allocations
        allocs = (
            self.db.query(ScenarioAllocation, BacklogItem)
            .join(BacklogItem, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .filter(
                ScenarioAllocation.scenario_id == scenario.id,
                ScenarioAllocation.included_flag.is_(True),
            )
            .all()
        )
        role_by_emp: dict[str, str | None] = {e.id: e.role for e in employees}
        qa_external = (
            scenario.external_qa_hours is not None
            and float(scenario.external_qa_hours or 0) > 0
        )

        for alloc, bi in allocs:
            # 1. Квартальные часы по ролям
            opo = float(bi.estimate_opo_hours or 0)
            opo_an_ratio = float(
                bi.opo_analyst_ratio if bi.opo_analyst_ratio is not None else 0.5
            )
            an_total = float(bi.estimate_analyst_hours or 0) + opo * opo_an_ratio
            rp_total = opo * (1 - opo_an_ratio)
            dev_total = float(bi.estimate_dev_hours or 0)
            qa_total = float(bi.estimate_qa_hours or 0)

            # 2. Роль/сотрудник для аналитика
            assignee_role = (
                role_by_emp.get(bi.assignee_employee_id)
                if bi.assignee_employee_id else None
            )
            an_role = "consultant" if assignee_role == "consultant" else "analyst"
            an_emp_id = (
                bi.assignee_employee_id
                if assignee_role in {"analyst", "consultant"} else None
            )

            # 3. Сплит по месяцам — закрытия `_split_emp`/`_split_pool`
            #    определены выше, чтобы не пересоздаваться на каждой allocation.

            # analyst / consultant
            if an_total > 0:
                for month, h in zip(months, _split_emp(an_total, an_emp_id)):
                    self.db.add(ScenarioAllocationBreakdownSnapshot(
                        revision_id=revision.id,
                        allocation_id=alloc.id,
                        month=month,
                        role=an_role,
                        employee_id=an_emp_id,
                        is_external=False,
                        hours=h,
                    ))

            # RP
            if rp_total > 0:
                for month, h in zip(months, _split_emp(rp_total, rp_emp_id)):
                    self.db.add(ScenarioAllocationBreakdownSnapshot(
                        revision_id=revision.id,
                        allocation_id=alloc.id,
                        month=month,
                        role="RP",
                        employee_id=rp_emp_id,
                        is_external=False,
                        hours=h,
                    ))

            # dev (pool, NULL employee)
            if dev_total > 0:
                for month, h in zip(months, _split_pool(dev_total, devs)):
                    self.db.add(ScenarioAllocationBreakdownSnapshot(
                        revision_id=revision.id,
                        allocation_id=alloc.id,
                        month=month,
                        role="dev",
                        employee_id=None,
                        is_external=False,
                        hours=h,
                    ))

            # qa
            if qa_total > 0:
                if qa_external:
                    # Внешний QA: равномерный split, is_external=True
                    for month, h in zip(
                        months, _split_proportional(qa_total, [1.0] * len(months))
                    ):
                        self.db.add(ScenarioAllocationBreakdownSnapshot(
                            revision_id=revision.id,
                            allocation_id=alloc.id,
                            month=month,
                            role="qa",
                            employee_id=None,
                            is_external=True,
                            hours=h,
                        ))
                else:
                    # Штатный QA: pool
                    for month, h in zip(months, _split_pool(qa_total, qas)):
                        self.db.add(ScenarioAllocationBreakdownSnapshot(
                            revision_id=revision.id,
                            allocation_id=alloc.id,
                            month=month,
                            role="qa",
                            employee_id=None,
                            is_external=False,
                            hours=h,
                        ))
