from pydantic import BaseModel
from datetime import date


class AbsenceChange(BaseModel):
    type: str            # "added" | "removed"
    start_date: date
    end_date: date
    reason: str | None
    hours: float


class MonthDiff(BaseModel):
    year: int
    month: int
    snapshot_available_hours: float
    current_available_hours: float
    delta_hours: float
    absence_changes: list[AbsenceChange]


class EmployeeDiff(BaseModel):
    employee_id: str
    employee_name: str
    months: list[MonthDiff]


class CapacityDiffResponse(BaseModel):
    has_changes: bool
    changed_employees: list[EmployeeDiff]
