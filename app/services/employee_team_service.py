"""Авто-определение команды сотрудника по ворклогам.

Мода берётся по суммарным часам на задачах с заданным `issue.team`,
в окне последних `lookback_days` дней. Возвращает None, если у сотрудника
нет worklog'ов с ненулевым team за окно.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Category, Employee, EmployeeTeam, Issue, Worklog


# Коды категорий, исключаемые из скана: «Архив прочих задач» + «Инициативы».
# Остальные — «Активный стек» ∪ «Архив квартальных задач».
EXCLUDED_CATEGORY_CODES: set[str] = {"archive", "initiatives_rfa"}


@dataclass
class AutoDetectSummary:
    assigned: int
    skipped: int
    details: list[dict]


class EmployeeTeamService:
    def __init__(self, db: Session):
        self.db = db

    def _target_category_codes(self) -> set[str]:
        all_codes = {c.code for c in self.db.query(Category).all()}
        return all_codes - EXCLUDED_CATEGORY_CODES

    def auto_detect_team(
        self, employee_id: str, *, lookback_days: Optional[int] = None
    ) -> Optional[str]:
        target_codes = self._target_category_codes()
        q = (
            self.db.query(
                Issue.team.label("team"),
                func.coalesce(func.sum(Worklog.time_spent_seconds), 0).label("seconds"),
            )
            .join(Worklog, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.employee_id == employee_id,
                Issue.team.isnot(None),
                Issue.team != "",
                Issue.category.in_(target_codes),
            )
        )
        if lookback_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            q = q.filter(Worklog.started_at >= cutoff)
        rows = (
            q.group_by(Issue.team)
            .order_by(func.sum(Worklog.time_spent_seconds).desc())
            .all()
        )
        if not rows:
            return None
        return rows[0].team

    def auto_detect_all_missing(self) -> AutoDetectSummary:
        assigned = 0
        skipped = 0
        details: list[dict] = []
        employees = (
            self.db.query(Employee)
            .filter(Employee.is_active == True)  # noqa: E712
            .all()
        )
        for emp in employees:
            if emp.team:
                skipped += 1
                continue
            team = self.auto_detect_team(emp.id)
            if team is None:
                skipped += 1
                continue
            emp.team = team
            assigned += 1
            details.append({"employee_id": emp.id, "team": team})
        self.db.commit()
        return AutoDetectSummary(assigned=assigned, skipped=skipped, details=details)

    def _recompute_legacy_team(self, employee_id: str) -> None:
        """Обновить ``Employee.team`` = имя primary membership (или None).

        Derived-колонка для backward-compat с кодом, который ещё читает
        ``Employee.team`` напрямую. Вызывается из всех мутаций.
        """
        primary = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.is_primary == True)  # noqa: E712
            .one_or_none()
        )
        emp = self.db.query(Employee).filter(Employee.id == employee_id).one()
        emp.team = primary.team if primary else None

    def list_teams(self, employee_id: str) -> list[EmployeeTeam]:
        return (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .order_by(EmployeeTeam.is_primary.desc(), EmployeeTeam.team)
            .all()
        )

    def add_team(self, employee_id: str, team: str, *, is_primary: bool = False) -> EmployeeTeam:
        """Добавить команду. Если у сотрудника ещё нет команд — становится primary
        автоматически, независимо от ``is_primary`` аргумента.
        """
        existing = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if existing is not None:
            if is_primary and not existing.is_primary:
                self.set_primary(employee_id, team)
                self.db.refresh(existing)
            return existing

        has_any = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .count()
        ) > 0
        make_primary = is_primary or not has_any
        if make_primary:
            # Сбросить у других
            self.db.query(EmployeeTeam).filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.is_primary == True,  # noqa: E712
            ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")

        row = EmployeeTeam(
            employee_id=employee_id,
            team=team,
            is_primary=make_primary,
        )
        self.db.add(row)
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def remove_team(self, employee_id: str, team: str) -> None:
        row = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if row is None:
            return
        was_primary = row.is_primary
        self.db.delete(row)
        self.db.flush()
        if was_primary:
            # Промоутим любую оставшуюся (отсортировано по team для детерминизма).
            leftover = (
                self.db.query(EmployeeTeam)
                .filter(EmployeeTeam.employee_id == employee_id)
                .order_by(EmployeeTeam.team)
                .first()
            )
            if leftover is not None:
                leftover.is_primary = True
                self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def set_primary(self, employee_id: str, team: str) -> None:
        target = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .one_or_none()
        )
        if target is None:
            raise ValueError(f"Employee {employee_id} not in team {team!r}")
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
        ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")
        target.is_primary = True
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def replace_teams(
        self,
        employee_id: str,
        teams: list[str],
        primary: Optional[str] = None,
    ) -> list[EmployeeTeam]:
        """Заменить весь набор. Если primary указан и входит в teams — делает
        его primary, иначе — первую команду в списке. Пустой список очищает всё.
        """
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
        ).delete(synchronize_session=False)
        self.db.flush()
        chosen_primary = primary if primary in teams else (teams[0] if teams else None)
        for t in teams:
            self.db.add(EmployeeTeam(
                employee_id=employee_id,
                team=t,
                is_primary=(t == chosen_primary),
            ))
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        return self.list_teams(employee_id)
