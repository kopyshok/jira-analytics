"""SnapshotWriter — заполнение всех snapshot-таблиц при создании ревизии сценария.

Один экземпляр = один проход. Все методы add()-ят строки в сессию;
commit делает вызывающий код.
"""
import calendar
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    AbsenceReason,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    Role,
    ScenarioCalendarSnapshot,
    ScenarioDictionarySnapshot,
    ScenarioRevision,
    ScenarioRule,
    ScenarioRulesSnapshot,
    ScenarioTeamSnapshot,
)
from app.services.capacity_service import QUARTER_MONTHS


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
        """Snapshot scenario_rules + резолв work_type_label."""
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
                    code=None,
                    label=ar.label,
                    sort_order=ar.sort_order,
                    extra_json={
                        "is_planned": bool(ar.is_planned),
                        "color": ar.color,
                        "is_active": bool(ar.is_active),
                    },
                )
            )
