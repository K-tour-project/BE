"""Region response schemas."""
from __future__ import annotations

from pydantic import BaseModel


class RegionCandidate(BaseModel):
    """`GET /regions/resolve?name=`"""

    region_id: int
    name: str
    full_name: str
    level: str
    bjd_cd: str


class RegionResolveResponse(BaseModel):
    candidates: list[RegionCandidate]


class RegionChild(BaseModel):
    region_id: int
    name: str
    level: str
    bjd_cd: str


class RegionNode(BaseModel):
    """`GET /regions`."""

    region_id: int
    parent_id: int | None = None
    level: str
    name: str
    bjd_cd: str
    children: list[RegionChild] | None = None
