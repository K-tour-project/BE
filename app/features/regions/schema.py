"""Region response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.shared.schema import Location

GeoJsonGeometry = dict[str, Any]


class RegionCandidate(BaseModel):
    """`GET /regions/resolve?name=`."""

    region_id: int
    name: str
    full_name: str
    level: str  # sido | sigungu
    centroid: Location | None = None
    boundary: GeoJsonGeometry | None = None


class RegionResolveResponse(BaseModel):
    candidates: list[RegionCandidate]


class RegionChild(BaseModel):
    region_id: int
    name: str
    level: str
    centroid: Location | None = None
    boundary: GeoJsonGeometry | None = None


class RegionNode(BaseModel):
    """`GET /regions`."""

    region_id: int
    name: str
    level: str
    parent_region_id: int | None = None
    centroid: Location | None = None
    boundary: GeoJsonGeometry | None = None
    children: list[RegionChild] | None = None


class RegionBoundaryResponse(BaseModel):
    """`GET /regions/{region_id}/boundary`."""

    region_id: int
    name: str
    full_name: str
    level: str
    parent_region_id: int | None = None
    centroid: Location | None = None
    boundary: GeoJsonGeometry
