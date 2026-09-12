"""지역 관광지 목록 및 content_id 기반 상세. 외부 응답은 저장하지 않는다."""
import asyncio
import math
import re
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from geoalchemy2 import Geometry
from pydantic import BaseModel, Field
from sqlalchemy import cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.features.products.schema import ContentOnPlace
from app.features.places.matching import distance_m, name_variants, title_similarity
from app.features.places.service import (
    _clean_text,
    _clean_url,
    _contents_by_place,
    _related_tourism_places,
)
from app.features.places.schema import RelatedTourismPlace
from app.integrations.call_log import save_calls
from app.integrations.tour_api import TourApiClient, TourApiError, intro_details
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
    use_time: str | None = None
    rest_date: str | None = None
    parking: str | None = None
    pet_allowed: str | None = None
    images: list[str] = Field(default_factory=list)
    contents: list[ContentOnPlace] = Field(default_factory=list)
    related_places: list[RelatedTourismPlace] = Field(default_factory=list)


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


def matches(row, place, region_name=None):
    """요청 중인 TourAPI 관광지와 DB 촬영지가 같은 장소인지 판정한다.

    TourAPI content ID나 응답은 저장하지 않는다. 좌표로 먼저 후보를 제한하고,
    가까울수록 이름 표기 차이를 더 넓게 허용한다.
    """
    point = location(row)
    if point is not None and place.lat is not None and place.lng is not None:
        distance = distance_m(point.lat, point.lng, float(place.lat), float(place.lng))
        if distance > 1_000:
            return False
        similarity = title_similarity(
            str(row.get("title") or ""),
            name_variants(str(place.name or ""), region_name),
        )
        return (
            (distance <= 100 and similarity >= 0.70)
            or (distance <= 500 and similarity >= 0.75)
            or similarity >= 0.85
        )

    # 좌표가 없는 데이터는 오탐을 막기 위해 기존의 엄격한 기준을 유지한다.
    if not normalize(place.name) or normalize(place.name) != normalize(row.get("title")):
        return False
    address = normalize(row.get("addr1"))
    return bool(address) and address == normalize(place.address)


def candidate_bounds(rows):
    """한 페이지의 유효 좌표를 감싸는 1km 여유 bounding box."""
    points = [point for row in rows if (point := location(row)) is not None]
    if not points:
        return None
    min_lat = min(point.lat for point in points)
    max_lat = max(point.lat for point in points)
    min_lng = min(point.lng for point in points)
    max_lng = max(point.lng for point in points)
    mean_lat = (min_lat + max_lat) / 2
    lat_margin = 1_000 / 111_320
    lng_margin = 1_000 / max(1, 111_320 * math.cos(math.radians(mean_lat)))
    return (
        min_lat - lat_margin,
        max_lat + lat_margin,
        min_lng - lng_margin,
        max_lng + lng_margin,
    )


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
        # 페이지 전체를 한 번의 DB 질의로 비교한다. 이름 완전일치로 후보를
        # 잘라내지 않고 좌표 범위로 먼저 좁혀 표기 차이가 있는 장소도 판정한다.
        titles = [normalize(row.get("title")) for row in rows]
        lat_expr = func.coalesce(Place.latitude, func.ST_Y(cast(Place.geom, Geometry)))
        lng_expr = func.coalesce(Place.longitude, func.ST_X(cast(Place.geom, Geometry)))
        bounds = candidate_bounds(rows)
        filters = []
        if bounds is not None:
            min_lat, max_lat, min_lng, max_lng = bounds
            filters.append(lat_expr.between(min_lat, max_lat) & lng_expr.between(min_lng, max_lng))
        # 좌표 없는 TourAPI 행의 엄격한 이름+주소 fallback 후보.
        if titles:
            filters.append(func.lower(func.regexp_replace(Place.name, "[^[:alnum:]]", "", "g")).in_(titles))
        candidates = (await db.execute(select(
            Place.place_id, Place.name, Place.address,
            lat_expr.label("lat"), lng_expr.label("lng"),
        ).where(or_(*filters)))).all() if rows and filters else []
        items = []
        for row in rows:
            matched = sorted({
                p.place_id for p in candidates
                if matches(row, p, getattr(region, "name", None))
            })
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
            content_type_id = str(common.get("contenttypeid") or "")
            intro, images = await asyncio.gather(
                api.detail_intro(content_id, content_type_id),
                api.detail_images(content_id),
            )
            use_time, rest_date, parking, pet_allowed = intro_details(
                intro, content_type_id
            )
            # 장소 상세 화면 하단의 연관 관광지. 상세 이동이 가능한 TourAPI ID로 최대 6개를 해석한다.
            try:
                related_places = await _related_tourism_places(
                    api,
                    common,
                    SimpleNamespace(
                        name=common.get("title") or "",
                        region_bjd_cd="",
                    ),
                    limit=6,
                )
            except TourApiError:
                # 연관 관광지는 부가 정보이므로 해당 API 장애가 장소 상세 전체를 막지 않는다.
                related_places = []

        # 연관 관광지 상세에서도 이 장소에서 촬영된 작품을 함께 제공한다.
        lat_expr = func.coalesce(Place.latitude, func.ST_Y(cast(Place.geom, Geometry)))
        lng_expr = func.coalesce(Place.longitude, func.ST_X(cast(Place.geom, Geometry)))
        filters = [Place.tour_content_id == content_id]
        if (bounds := candidate_bounds([common])) is not None:
            min_lat, max_lat, min_lng, max_lng = bounds
            filters.append(
                lat_expr.between(min_lat, max_lat) & lng_expr.between(min_lng, max_lng)
            )
        candidates = (
            await db.execute(
                select(
                    Place.place_id,
                    Place.name,
                    Place.address,
                    lat_expr.label("lat"),
                    lng_expr.label("lng"),
                ).where(or_(*filters))
            )
        ).all()
        matched_ids = [p.place_id for p in candidates if matches(common, p)]
        by_place = await _contents_by_place(db, matched_ids)
        contents = []
        seen_content_ids = set()
        for place_id in matched_ids:
            for content in by_place.get(place_id, []):
                if content.product_id not in seen_content_ids:
                    seen_content_ids.add(content.product_id)
                    contents.append(content)
        return TourismDetail(
            content_id=content_id, name=common.get("title") or "",
            overview=_clean_text(common.get("overview")), homepage=_clean_url(common.get("homepage")),
            tel=common.get("tel") or None, address=common.get("addr1") or None,
            address_detail=common.get("addr2") or None,
            use_time=_clean_text(use_time), rest_date=_clean_text(rest_date),
            parking=_clean_text(parking), pet_allowed=_clean_text(pet_allowed),
            images=list(dict.fromkeys(img["originimgurl"] for img in images if img.get("originimgurl"))),
            contents=contents,
            related_places=related_places,
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
