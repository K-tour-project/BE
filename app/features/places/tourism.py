"""지역 관광지 목록 및 content_id 기반 상세. 외부 응답은 저장하지 않는다."""
import math
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from geoalchemy2 import Geometry
from pydantic import BaseModel, Field
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.features.places.service import _clean_text, _clean_url
from app.integrations.call_log import save_calls
from app.integrations.tour_api import TourApiClient, TourApiError
from app.models import Place, Region
from app.shared.schema import Location

router = APIRouter(tags=["tourism"])


class TourismPlace(BaseModel):
    content_id: str
    name: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    location: Location | None = None
    sido_code: str | None = None
    sigungu_code: str | None = None
    sido_name: str | None = None
    sigungu_name: str | None = None
    category: Literal["촬영지", "관광지"] = "관광지"
    place_ids: list[int] = Field(default_factory=list)


class TourismPage(BaseModel):
    items: list[TourismPlace]
    total: int
    count: int
    page: int
    size: int
    has_next: bool


class TourismDetail(BaseModel):
    content_id: str
    name: str
    overview: str | None = None
    homepage: str | None = None
    tel: str | None = None
    address: str | None = None
    address_detail: str | None = None
    images: list[str] = Field(default_factory=list)


def normalize(value):
    return re.sub(r"[\W_]+", "", value or "").casefold()


def location(row):
    try:
        lat, lng = float(row.get("mapy")), float(row.get("mapx"))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
            return None
        return Location(lat=lat, lng=lng)
    except (ValueError, TypeError):
        return None


def matches(row, place):
    if place.tour_content_id:
        return str(place.tour_content_id) == str(row["contentid"])
    if not normalize(place.name) or normalize(place.name) != normalize(row.get("title")):
        return False
    point = location(row)
    if point is not None and place.lat is not None and place.lng is not None:
        lat1, lat2 = math.radians(point.lat), math.radians(float(place.lat))
        dlat = lat2 - lat1
        dlng = math.radians(float(place.lng) - point.lng)
        a = math.sin(dlat / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng / 2)**2
        return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a)))) <= 200
    address = normalize(row.get("addr1"))
    return bool(address) and address == normalize(place.address)


async def list_tourism(db, region_id, page, size):
    region = await db.get(Region, region_id)
    if region is None:
        raise HTTPException(404, "해당 지역을 찾을 수 없습니다.")
    sido = region.bjd_cd[:2]
    sigungu = region.bjd_cd[2:5] if region.level == "2" else None
    api = TourApiClient()
    try:
        async with api:
            rows, total = await api.area_based(sido, sigungu, page=page, size=size)
        regions = (await db.execute(select(Region.bjd_cd, Region.name, Region.level))).all()
        sido_names = {r.bjd_cd[:2]: r.name for r in regions if r.level == "1"}
        sigungu_names = {r.bjd_cd[:5]: r.name for r in regions if r.level == "2"}
        # 페이지 전체를 한 번의 DB 질의로 비교. CSV의 region_id가 비어 있어도 매칭한다.
        titles = [normalize(row.get("title")) for row in rows]
        ids = [str(row["contentid"]) for row in rows]
        candidates = (await db.execute(select(
            Place.place_id, Place.name, Place.address, Place.tour_content_id,
            func.coalesce(Place.latitude, func.ST_Y(cast(Place.geom, Geometry))).label("lat"),
            func.coalesce(Place.longitude, func.ST_X(cast(Place.geom, Geometry))).label("lng"),
        ).where(
            Place.tour_content_id.in_(ids) |
            func.lower(func.regexp_replace(Place.name, "[^[:alnum:]]", "", "g")).in_(titles)
        ))).all() if rows else []
        items = []
        for row in rows:
            matched = sorted({p.place_id for p in candidates if matches(row, p)})
            sc = str(row.get("lDongRegnCd") or sido)
            gc = str(row.get("lDongSignguCd") or sigungu or "") or None
            items.append(TourismPlace(
                content_id=str(row["contentid"]), name=row["title"],
                image_url=row.get("firstimage") or None,
                thumbnail_url=row.get("firstimage2") or row.get("firstimage") or None,
                location=location(row), sido_code=sc, sigungu_code=gc,
                sido_name=sido_names.get(sc), sigungu_name=sigungu_names.get(sc + gc) if gc else None,
                category="촬영지" if matched else "관광지", place_ids=matched,
            ))
        return TourismPage(items=items, total=total, count=len(items), page=page, size=size, has_next=page*size < total)
    finally:
        await save_calls(db, api.calls)


async def tourism_detail(db, content_id):
    api = TourApiClient()
    try:
        async with api:
            common = await api.detail_common(content_id)
            if not common:
                raise HTTPException(404, "해당 관광지를 찾을 수 없습니다.")
            images = await api.detail_images(content_id)
        return TourismDetail(
            content_id=content_id, name=common.get("title") or "",
            overview=_clean_text(common.get("overview")), homepage=_clean_url(common.get("homepage")),
            tel=common.get("tel") or None, address=common.get("addr1") or None,
            address_detail=common.get("addr2") or None,
            images=list(dict.fromkeys(img["originimgurl"] for img in images if img.get("originimgurl"))),
        )
    finally:
        await save_calls(db, api.calls)


@router.get("/regions/{region_id}/tourism-places", response_model=TourismPage)
async def get_tourism_places(region_id: int, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    """관광지(contentTypeId=12) 목록. 코드는 법정동 시도 2자리·시군구 3자리."""
    try:
        return await list_tourism(db, region_id, page, size)
    except TourApiError as exc:
        raise HTTPException(502, "관광공사 API 조회에 실패했습니다.") from exc


@router.get("/tourism-places/{content_id}", response_model=TourismDetail)
async def get_tourism_detail(content_id: str = Path(..., pattern=r"^\d+$", max_length=20), db: AsyncSession = Depends(get_db)):
    """목록의 content_id로 공통 정보와 원본 이미지 전체 목록 조회."""
    try:
        return await tourism_detail(db, content_id)
    except TourApiError as exc:
        raise HTTPException(502, "관광공사 API 조회에 실패했습니다.") from exc
