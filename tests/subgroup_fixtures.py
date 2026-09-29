"""Приписка сотрудника к группе в тестах — строкой распределения."""

from datetime import date
from typing import Optional

from app.models import EmployeeSubgroupShare


def share(
    employee_id: str,
    team: str,
    subgroup_id: str,
    percent: int = 100,
    valid_from: Optional[date] = None,
) -> EmployeeSubgroupShare:
    """Строка распределения; по умолчанию — «100 % с начала участия»."""
    return EmployeeSubgroupShare(
        employee_id=employee_id,
        team=team,
        subgroup_id=subgroup_id,
        percent=percent,
        valid_from=valid_from,
    )
