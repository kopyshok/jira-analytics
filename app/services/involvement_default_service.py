"""Справочник вовлечённости: поиск действующего значения и запись в задачи."""
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import BacklogItem, InvolvementDefault
from app.models.involvement_default import INVOLVEMENT_ROLES

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


def team_defaults(
    db: Session, team: Optional[str], year: Optional[int], quarter: Optional[int],
) -> dict[str, float]:
    """Действующие значения справочника команды на квартал: роль → вовлечённость."""
    if not team or not year or not quarter:
        return {}
    out: dict[str, float] = {}
    for role in INVOLVEMENT_ROLES:
        val = lookup_involvement(db, team, role, year, quarter)
        if val is not None:
            out[role] = val
    return out


# Фаза плана → поле вовлечённости в BacklogItem.
PHASE_FIELD = {
    "analyst": "involvement_analyst",
    "dev": "involvement_dev",
    "qa": "involvement_qa",
    "opo": "involvement_launch",
}


def effective_for_phase(
    item: BacklogItem, phase: str, defaults: dict[str, float],
) -> Optional[float]:
    """Вовлечённость фазы: своё значение задачи, иначе значение справочника."""
    field = PHASE_FIELD.get(phase)
    if not field:
        return None
    own = getattr(item, field, None)
    return own if own is not None else defaults.get(phase)
