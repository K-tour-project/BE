"""Region selection routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.region import service
from app.region.schemas import (
    RegionSelectionRequest,
    RegionSelectionResponse,
    SidoOption,
    SigunguListResponse,
)

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/sidos", response_model=list[SidoOption])
async def list_sidos(db: AsyncSession = Depends(get_db)):
    return await service.list_sidos(db)


@router.get("/{sido_id}/sigungu", response_model=SigunguListResponse)
async def list_sigungu(sido_id: int, db: AsyncSession = Depends(get_db)):
    result = await service.list_sigungu(db, sido_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sido not found.")
    return result


@router.post("/selection", response_model=RegionSelectionResponse)
async def select_region(
    request: RegionSelectionRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await service.select_region(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Sido not found.")
    return result
