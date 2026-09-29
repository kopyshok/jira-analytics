"""Личные настройки сотрудника: действующая запись на квартал.

Запись действует с квартала до следующей записи этого сотрудника. Запись
«как обычно» (без вовлечённости, нормированные работы по правилам роли)
тоже возвращается — она отменяет более раннюю.
"""
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import EmployeePersonalNormed, EmployeePersonalSetting


@dataclass(frozen=True)
class PersonalSetting:
    """Личная настройка сотрудника на квартал. involvement=None — как обычно;
    normed=None — по правилам роли, {} — нормированных работ нет."""
    involvement: Optional[float]
    normed: Optional[Dict[str, float]]


def personal_for(
    db: Session, employee_ids: Iterable[str], year: int, quarter: int,
) -> Dict[str, PersonalSetting]:
    """Последняя запись сотрудника с (год, квартал) ≤ заданного. Константа запросов.

    Сотрудники без такой записи в ответ не попадают. ``normed`` — вид работ →
    процент нормы.
    """
    ids = list(set(employee_ids))
    if not ids:
        return {}
    S = EmployeePersonalSetting
    rows = (
        db.query(S.id, S.employee_id, S.involvement, S.normed_custom)
        .filter(
            S.employee_id.in_(ids),
            or_(S.effective_year < year,
                and_(S.effective_year == year, S.effective_quarter <= quarter)),
        )
        .order_by(S.employee_id, S.effective_year.desc(), S.effective_quarter.desc())
        .all()
    )
    latest: Dict[str, Any] = {}
    for r in rows:
        latest.setdefault(r.employee_id, r)

    custom_ids = [r.id for r in latest.values() if r.normed_custom]
    normed: Dict[str, Dict[str, float]] = {sid: {} for sid in custom_ids}
    if custom_ids:
        N = EmployeePersonalNormed
        for sid, wt_id, pct in (
            db.query(N.setting_id, N.work_type_id, N.percent_of_norm)
            .filter(N.setting_id.in_(custom_ids))
            .all()
        ):
            normed[sid][wt_id] = pct

    return {
        emp: PersonalSetting(r.involvement, normed[r.id] if r.normed_custom else None)
        for emp, r in latest.items()
    }
