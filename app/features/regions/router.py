"""Region API router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.features.places.schema import PlaceOnMap
from app.features.places.service import places_in_region
from app.features.regions import service
from app.features.regions.schema import (
    RegionBoundaryResponse,
    RegionNode,
    RegionResolveResponse,
)
from app.shared.schema import Page

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/resolve", response_model=RegionResolveResponse)
async def resolve_region(
    name: str = Query(..., min_length=1, description="Region name, e.g. Seoul Jung-gu"),
    include_boundary: bool = Query(False, description="Include boundary as GeoJSON geometry"),
    db: AsyncSession = Depends(get_db),
):
    candidates = await service.resolve_regions(db, name, include_boundary=include_boundary)
    return RegionResolveResponse(candidates=candidates)


@router.get("", response_model=Page[RegionNode])
async def list_regions(
    flat: bool = Query(False, description="Return a flat list instead of sido/sigungu tree"),
    include_boundary: bool = Query(False, description="Include boundary as GeoJSON geometry"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_regions(db, flat, include_boundary=include_boundary)
    return Page[RegionNode](items=items, total=total)


@router.get("/{region_id}/boundary", response_model=RegionBoundaryResponse)
async def get_region_boundary(region_id: int, db: AsyncSession = Depends(get_db)):
    region = await service.get_region_boundary(db, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="Region boundary not found.")
    return region


@router.get("/{region_id}/places", response_model=Page[PlaceOnMap])
async def get_region_places(
    region_id: int,
    content_id: int | None = Query(None, description="Filter places by content_id"),
    sort: str = Query("popular", pattern="^(popular|name)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    items, total = await places_in_region(db, region_id, content_id, limit, offset, sort)
    if total == 0 and not items:
        if not await service.resolve_region_exists(db, region_id):
            raise HTTPException(status_code=404, detail="Region not found.")
    return Page[PlaceOnMap](items=items, total=total)
