"""Pydantic-схемы для override и continuation-info."""
from typing import Optional
from pydantic import BaseModel, Field


class AllocationOverrideRequest(BaseModel):
    """4 цифры или 4 null. Mixed (часть null, часть значение) валиден — null → 0.0 на чтении."""
    analyst: Optional[float] = Field(default=None, ge=0)
    dev: Optional[float] = Field(default=None, ge=0)
    qa: Optional[float] = Field(default=None, ge=0)
    opo: Optional[float] = Field(default=None, ge=0)
