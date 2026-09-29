"""Схемы реестра команд и групп внутри команды."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class SubgroupOut(BaseModel):
    id: str
    name: str
    sort_order: int

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    name: str
    has_subgroups: bool
    subgroups: List[SubgroupOut] = []


class TeamPatch(BaseModel):
    has_subgroups: bool


class SubgroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EmployeeSubgroupIn(BaseModel):
    team: str
    subgroup_id: Optional[str] = None


class SubgroupShareItem(BaseModel):
    subgroup_id: str
    percent: int


class SubgroupShareRecordIn(BaseModel):
    team: str
    valid_from: Optional[date] = None
    shares: List[SubgroupShareItem]


class SubgroupShareRecordOut(BaseModel):
    valid_from: Optional[date] = None
    shares: List[SubgroupShareItem]


class UngroupedEmployeeOut(BaseModel):
    """Активный участник команды с делением без группы в квартале."""

    employee_id: str
    display_name: str
    team: str
