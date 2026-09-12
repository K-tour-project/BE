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
    RegionOption,
    RegionResolveResponse,
)
from app.shared.schema import Page

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/sidos", response_model=Page[RegionOption])
async def list_sidos(db: AsyncSession = Depends(get_db)):
    items, total = await service.list_sidos(db)
    return Page[RegionOption](items=items, total=total)


@router.get("/resolve", response_model=RegionResolveResponse)
async def resolve_region(
    name: str = Query(..., min_length=1, description="지역명(부분일치)"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """지역명으로 시도·시군구 후보를 찾는다."""
    return RegionResolveResponse(
        candidates=await service.resolve_regions(db, name, limit=limit)
    )


@router.get("/{sido_id}/children", response_model=Page[RegionOption])
async def list_region_children(sido_id: int, db: AsyncSession = Depends(get_db)):
    result = await service.list_children(db, sido_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sido not found.")
    items, total = result
    return Page[RegionOption](items=items, total=total)


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
