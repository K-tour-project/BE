"""Region response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.shared.schema import Location

GeoJsonGeometry = dict[str, Any]


class RegionOption(BaseModel):
    """Lightweight region option for Android selection UI."""

    region_id: int
    name: str
    full_name: str
    level: str  # 1=sido, 2=sigungu
    parent_region_id: int | None = None
    bjd_cd: str
    has_children: bool = False
    centroid: Location | None = None


class RegionCandidate(RegionOption):
    """`GET /regions/resolve?name=` item."""


class RegionResolveResponse(BaseModel):
    candidates: list[RegionCandidate]


class RegionBoundaryResponse(BaseModel):
    """Region boundary as GeoJSON geometry."""

    region_id: int
    name: str
    full_name: str
    level: str
    parent_region_id: int | None = None
    bjd_cd: str
    centroid: Location | None = None
    boundary: GeoJsonGeometry
