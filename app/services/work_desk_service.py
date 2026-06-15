"""WorkDeskService — выпуск токенов и жизненный цикл рабочих столов аналитиков."""

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.work_desk import WorkDesk


class WorkDeskService:
    """Управляет публичными рабочими столами: токены, отзыв, перевыпуск."""

    def create(
        self,
        db: Session,
        employee_id: str,
        enabled_widgets: list[str],
        created_by_user_id: str,
    ) -> WorkDesk:
        """Создать новый стол для сотрудника, отозвав предыдущий активный."""
        existing = self.get_active_by_employee(db, employee_id)
        if existing is not None:
            existing.revoked_at = datetime.utcnow()

        desk = WorkDesk(
            employee_id=employee_id,
            token=secrets.token_urlsafe(32),
            created_by_user_id=created_by_user_id,
        )
        desk.enabled_widgets = list(enabled_widgets or [])
        db.add(desk)
        db.commit()
        db.refresh(desk)
        return desk

    def get_active_by_employee(self, db: Session, employee_id: str) -> WorkDesk | None:
        """Активный (не отозванный) стол сотрудника или None."""
        return db.execute(
            select(WorkDesk).where(
                WorkDesk.employee_id == employee_id,
                WorkDesk.revoked_at.is_(None),
            )
        ).scalar_one_or_none()

    def get_by_token(self, db: Session, token: str) -> WorkDesk | None:
        """Активный стол по токену; отозванные не возвращаются."""
        return db.execute(
            select(WorkDesk).where(
                WorkDesk.token == token,
                WorkDesk.revoked_at.is_(None),
            )
        ).scalar_one_or_none()

    def revoke(self, db: Session, desk_id: str) -> None:
        """Отозвать стол."""
        desk = db.get(WorkDesk, desk_id)
        if desk is None:
            return
        desk.revoked_at = datetime.utcnow()
        db.commit()

    def regenerate(self, db: Session, desk_id: str) -> WorkDesk:
        """Отозвать стол и выпустить новый с теми же настройками."""
        desk = db.get(WorkDesk, desk_id)
        if desk is None:
            raise ValueError(f"Стол {desk_id} не найден")
        employee_id = desk.employee_id
        widgets = desk.enabled_widgets
        created_by = desk.created_by_user_id
        self.revoke(db, desk_id)
        return self.create(db, employee_id, widgets, created_by)

    def set_widgets(self, db: Session, desk_id: str, widgets: list[str]) -> WorkDesk:
        """Обновить набор виджетов стола."""
        desk = db.get(WorkDesk, desk_id)
        if desk is None:
            raise ValueError(f"Стол {desk_id} не найден")
        desk.enabled_widgets = list(widgets or [])
        db.commit()
        db.refresh(desk)
        return desk
