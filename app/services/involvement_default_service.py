"""Справочник вовлечённости: поиск действующего значения и запись в задачи."""
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import BacklogItem, InvolvementDefault

# role справочника -> поле BacklogItem
_ROLE_FIELD = {
    "analyst": "involvement_analyst",
    "dev": "involvement_dev",
    "qa": "involvement_qa",
    "opo": "involvement_launch",
}


def lookup_involvement(
    db: Session, team: str, role: str, year: int, quarter: int,
) -> Optional[float]:
    """Значение вовлечённости для (team, role), действующее на (year, quarter):
    последняя запись с началом действия не позже (year, quarter). Иначе None."""
    row = (
        db.query(InvolvementDefault)
        .filter(
            InvolvementDefault.team == team,
            InvolvementDefault.role == role,
            or_(
                InvolvementDefault.effective_year < year,
                and_(
                    InvolvementDefault.effective_year == year,
                    InvolvementDefault.effective_quarter <= quarter,
                ),
            ),
        )
        .order_by(
            InvolvementDefault.effective_year.desc(),
            InvolvementDefault.effective_quarter.desc(),
        )
        .first()
    )
    return row.involvement if row else None


def fill_empty_involvement(
    db: Session, items: list[BacklogItem], team: str, year: int, quarter: int,
) -> int:
    """Заполнить пустые поля вовлечённости целевых задач значениями справочника.
    Возвращает число заполненных полей. Непустые значения не трогает."""
    filled = 0
    for role, field in _ROLE_FIELD.items():
        val = lookup_involvement(db, team, role, year, quarter)
        if val is None:
            continue
        for item in items:
            if getattr(item, field) is None:
                setattr(item, field, val)
                filled += 1
    return filled
