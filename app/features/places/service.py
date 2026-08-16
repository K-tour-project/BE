"""촬영지 조회 로직 (5단계).

계약서(API_CONTRACT.md §4~§6)의 응답을 만들기 위한 DB 질의.

★ 장소 목록을 만드는 함수는 **작품 화면·지역 화면에서도 쓰인다**(작품의 촬영지, 지역 내 촬영지).
  장소 응답을 조립하는 주인이 여기이므로, contents·regions 라우터가 여기 함수를 가져다 쓴다.

설계 메모
- 좌표는 `geography` 컬럼이라 ST_X/ST_Y를 쓰려면 geometry로 캐스팅해야 한다.
- 장소에 붙는 `contents` 배열은 장소마다 따로 조회하면 N+1이 되므로,
  place_id 목록을 모아 **한 번에** 가져와 파이썬에서 묶는다.
- 지역이 시도면 그 아래 시군구의 장소까지 포함한다(`region_scope_ids`).

`GET /places/{place_id}`(TourAPI 실시간 상세)는 4단계에서 여기에 추가한다.
그때 [`app/integrations/tour_api.py`](../../integrations/tour_api.py)를 호출한다.
"""
from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.contents.schema import ContentOnPlace
from app.features.places.schema import PlaceInContent, PlaceOnMap
from app.features.regions.service import region_ref, region_scope_ids
from app.models import Content, ContentPlaceMapping, Place, Region
from app.shared.schema import Location

# geography → geometry 캐스팅 후 좌표 추출
_LAT = func.ST_Y(cast(Place.geom, Geometry))
_LNG = func.ST_X(cast(Place.geom, Geometry))


def _place_select():
    """장소 + 소속 지역(+상위 지역명)을 한 번에 뽑는 공통 select."""
    parent = aliased(Region)
    return (
        select(
            Place.place_id,
            Place.name,
            Place.address,
            Place.road_address,
            Place.region_id,
            Region.name.label("region_name"),
            parent.name.label("parent_name"),
            _LAT.label("lat"),
            _LNG.label("lng"),
        )
        .select_from(Place)
        .outerjoin(Region, Region.region_id == Place.region_id)
        .outerjoin(parent, parent.region_id == Region.parent_region_id)
    )


async def _contents_by_place(
    db: AsyncSession, place_ids: list[int], content_id: int | None = None
) -> dict[int, list[ContentOnPlace]]:
    """N+1 방지: 여러 장소의 작품을 한 번에 가져와 place_id로 묶는다."""
    if not place_ids:
        return {}
    stmt = (
        select(
            ContentPlaceMapping.place_id,
            Content.content_id,
            Content.title_ko,
            Content.production_year,
            Content.poster_url,
            ContentPlaceMapping.scene_description,
        )
        .join(Content, Content.content_id == ContentPlaceMapping.content_id)
        .where(ContentPlaceMapping.place_id.in_(place_ids))
        .order_by(Content.production_year.desc().nulls_last())
    )
    if content_id is not None:
        stmt = stmt.where(ContentPlaceMapping.content_id == content_id)

    out: dict[int, list[ContentOnPlace]] = {}
    for r in (await db.execute(stmt)).all():
        out.setdefault(r.place_id, []).append(
            ContentOnPlace(
                content_id=r.content_id,
                title_ko=r.title_ko,
                production_year=r.production_year,
                poster_url=r.poster_url,
                scene_description=r.scene_description,
            )
        )
    return out


async def places_of_content(
    db: AsyncSession, content_id: int, limit: int, offset: int
) -> tuple[list[PlaceInContent], int]:
    """작품의 촬영지 목록. 장면설명은 그 작품 기준으로 붙인다. (`GET /contents/{id}/places`)"""
    base = _place_select().add_columns(
        ContentPlaceMapping.scene_description, ContentPlaceMapping.episode
    ).join(
        ContentPlaceMapping, ContentPlaceMapping.place_id == Place.place_id
    ).where(ContentPlaceMapping.content_id == content_id)

    total = await db.scalar(
        select(func.count())
        .select_from(ContentPlaceMapping)
        .where(ContentPlaceMapping.content_id == content_id)
    )
    rows = (await db.execute(base.order_by(Place.name).limit(limit).offset(offset))).all()

    return [
        PlaceInContent(
            place_id=r.place_id,
            name=r.name,
            location=Location(lat=r.lat, lng=r.lng),
            address=r.address,
            road_address=r.road_address,
            region=region_ref(r.region_id, r.region_name, r.parent_name),
            scene_description=r.scene_description,
            episode=r.episode,
        )
        for r in rows
    ], (total or 0)


async def places_in_region(
    db: AsyncSession, region_id: int, content_id: int | None, limit: int, offset: int
) -> tuple[list[PlaceOnMap], int]:
    """지역 내 촬영지. (`GET /regions/{id}/places`)"""
    scope = await region_scope_ids(db, region_id)

    stmt = _place_select().where(Place.region_id.in_(scope))
    count_stmt = select(func.count()).select_from(Place).where(Place.region_id.in_(scope))

    if content_id is not None:
        # 유저플로우 4b — 지도에서 영화 하나를 골랐을 때 그 작품 촬영지만 남긴다.
        sub = (
            select(ContentPlaceMapping.place_id)
            .where(ContentPlaceMapping.content_id == content_id)
            .scalar_subquery()
        )
        stmt = stmt.where(Place.place_id.in_(sub))
        count_stmt = count_stmt.where(Place.place_id.in_(sub))

    total = await db.scalar(count_stmt)
    rows = (await db.execute(stmt.order_by(Place.name).limit(limit).offset(offset))).all()
    by_place = await _contents_by_place(db, [r.place_id for r in rows], content_id)

    return [
        PlaceOnMap(
            place_id=r.place_id,
            name=r.name,
            location=Location(lat=r.lat, lng=r.lng),
            address=r.address,
            road_address=r.road_address,
            region=region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
        )
        for r in rows
    ], (total or 0)


async def places_near_region(
    db: AsyncSession, region_id: int, radius_km: float, limit: int, offset: int
) -> tuple[list[PlaceOnMap], int] | None:
    """지역 중심점 반경 내 장소. 중심점이 없으면 None. (`GET /places?near=`)"""
    centroid = (
        await db.execute(select(Region.centroid).where(Region.region_id == region_id))
    ).scalar_one_or_none()
    if centroid is None:
        return None

    radius_m = radius_km * 1000
    dist = func.ST_Distance(Place.geom, centroid).label("dist_m")
    where = func.ST_DWithin(Place.geom, centroid, radius_m)

    total = await db.scalar(select(func.count()).select_from(Place).where(where))
    rows = (
        await db.execute(
            _place_select().add_columns(dist).where(where).order_by(dist).limit(limit).offset(offset)
        )
    ).all()
    by_place = await _contents_by_place(db, [r.place_id for r in rows])

    return [
        PlaceOnMap(
            place_id=r.place_id,
            name=r.name,
            location=Location(lat=r.lat, lng=r.lng),
            address=r.address,
            road_address=r.road_address,
            region=region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
            distance_km=round(r.dist_m / 1000, 2),
        )
        for r in rows
    ], (total or 0)
