"""지역 관련 엔드포인트 — API_CONTRACT.md §3, §6."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.common import Page
from app.schemas.place import PlaceOnMap
from app.schemas.region import RegionNode, RegionResolveResponse
from app.services import catalog

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/resolve", response_model=RegionResolveResponse)
async def resolve_region(
    name: str = Query(..., min_length=1, description="지역명. '서울 중구'처럼 시도를 붙이면 후보가 좁혀진다"),
    db: AsyncSession = Depends(get_db),
):
    """지역명 → 후보 목록 (AI 팀원용).

    ★ 「중구」는 6개 시도에, 「남구」는 5개 시도에 있다. **단일 답이 없으므로 배열**이다.
      `full_name`("서울특별시 중구")을 그대로 사용자에게 보여주면 된다.
    """
    return RegionResolveResponse(candidates=await catalog.resolve_regions(db, name))


@router.get("", response_model=Page[RegionNode])
async def list_regions(
    flat: bool = Query(False, description="true면 children 없이 244개를 평평하게"),
    db: AsyncSession = Depends(get_db),
):
    """지역 목록. 시도(17) → 시군구(227) 2단계."""
    items, total = await catalog.list_regions(db, flat)
    return Page[RegionNode](items=items, total=total)


@router.get("/{region_id}/places", response_model=Page[PlaceOnMap])
async def get_region_places(
    region_id: int,
    content_id: int | None = Query(None, description="작품으로 좁히기(유저플로우 4b)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """지역 내 촬영지 + 각 장소에서 촬영된 작품(지도 포스터 마커).

    `region_id`가 시도면 그 아래 시군구의 장소까지 포함한다.
    `content_id`를 주면 그 작품의 촬영지만 남는다 — 필터 전/후 응답 구조는 동일.
    """
    items, total = await catalog.places_in_region(db, region_id, content_id, limit, offset)
    if total == 0 and not items:
        # 지역 자체가 없는 경우와 '장소가 0건'인 경우를 구분해준다.
        if not await catalog.resolve_region_exists(db, region_id):
            raise HTTPException(status_code=404, detail="해당 지역을 찾을 수 없습니다.")
    return Page[PlaceOnMap](items=items, total=total)
