"""Сервис операций над таблицей employees.

Сейчас содержит только пересчёт ``is_active`` на основе categorisation активных
задач. Набор сотрудников, имеющих worklog'и на задачи с категориями
«Активный стек» и «Архив квартальных задач», становится активным; все остальные
помечаются неактивными.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Category, Employee, Issue, Worklog


# Коды категорий, исключаемые из «активного» набора.
EXCLUDED_CODES: set[str] = {"archive", "initiatives_rfa"}


@dataclass
class RecalcStats:
    """Сводка пересчёта активных сотрудников."""

    activated: int
    deactivated: int
    total_active: int


class EmployeeService:
    """Сервис операций над employees."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _target_category_codes(self) -> set[str]:
        """Коды, относящиеся к «Активный стек» ∪ «Архив квартальных задач».

        Совпадают с определением матчера вкладок на фронте: всё, что не
        ``archive`` и не ``initiatives_rfa``.
        """
        all_codes = {c.code for c in self.db.query(Category).all()}
        return all_codes - EXCLUDED_CODES

    def recalc_active_by_categories(self) -> RecalcStats:
        target = self._target_category_codes()

        active_ids = {
            row[0]
            for row in self.db.query(Worklog.employee_id)
            .join(Issue, Worklog.issue_id == Issue.id)
            .filter(Issue.assigned_category.in_(target))
            .distinct()
            .all()
        }

        before = {
            e.id: e.is_active for e in self.db.query(Employee).all()
        }

        activated = 0
        deactivated = 0
        for emp_id, was_active in before.items():
            target_state = emp_id in active_ids
            if target_state == was_active:
                continue
            self.db.query(Employee).filter(Employee.id == emp_id).update(
                {"is_active": target_state},
                synchronize_session=False,
            )
            if target_state:
                activated += 1
            else:
                deactivated += 1

        self.db.commit()
        return RecalcStats(
            activated=activated,
            deactivated=deactivated,
            total_active=len(active_ids),
        )
