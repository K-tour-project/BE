"""장소 관련 엔드포인트 — API_CONTRACT.md §6.

⚠️ 컴플라이언스: 사용자의 raw GPS 좌표를 받는 파라미터는 제공하지 않는다.
   공모전 규정상 위치를 서버가 수신하면 위치기반서비스 사업자 등록이 필요해진다.
   "내 주변"은 앱이 GPS로 가장 가까운 region_id를 고른 뒤 그 id를 보내는 방식.

`GET /places/{place_id}`(TourAPI 실시간 상세)는 4단계에서 추가한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.common import Page
from app.schemas.place import PlaceOnMap
from app.services import catalog

router = APIRouter(prefix="/places", tags=["places"])

# 공모전 규정: 위치기반 조회 반경 상한
MAX_RADIUS_KM = 20.0


@router.get("", response_model=Page[PlaceOnMap])
async def list_places_near(
    near: int = Query(..., description="중심이 될 region_id (그 지역의 중심점 기준)"),
    radius_km: float = Query(5.0, gt=0, description=f"최대 {MAX_RADIUS_KM}km"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """지역 중심점 반경 내 촬영지. 가까운 순으로 `distance_km`가 붙는다."""
    if radius_km > MAX_RADIUS_KM:
        raise HTTPException(
            status_code=400,
            detail=f"radius_km는 {MAX_RADIUS_KM}를 넘을 수 없습니다(공모전 위치기반 조회 제한).",
        )

    result = await catalog.places_near_region(db, near, radius_km, limit, offset)
    if result is None:
        raise HTTPException(status_code=404, detail="해당 지역을 찾을 수 없거나 중심점이 없습니다.")
    items, total = result
    return Page[PlaceOnMap](items=items, total=total)
