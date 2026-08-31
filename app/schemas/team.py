"""Схемы реестра команд и групп внутри команды."""

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
