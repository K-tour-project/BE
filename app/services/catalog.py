"""검색·지도 조회 로직 (5단계).

계약서(API_CONTRACT.md)의 응답을 만들기 위한 DB 질의를 모아둔다.
라우터는 얇게 두고 여기서 데이터를 완성해 돌려준다.

설계 메모
- 좌표는 `geography` 컬럼이라 ST_X/ST_Y를 쓰려면 geometry로 캐스팅해야 한다.
- 장소 목록에 붙는 `contents` 배열은 장소마다 따로 조회하면 N+1이 되므로,
  place_id 목록을 모아 **한 번에** 가져와 파이썬에서 묶는다.
- 지역이 시도면 그 아래 시군구의 장소까지 포함한다(사용자는 '강원도'로도 찾는다).
"""
from __future__ import annotations

from geoalchemy2 import Geography, Geometry
from sqlalchemy import Float, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Content, ContentPlaceMapping, Place, Region
from app.schemas.common import Location, RegionRef
from app.schemas.content import (
    ContentCandidate,
    ContentDetail,
    ContentOnPlace,
    ContentSummary,
)
from app.schemas.place import PlaceInContent, PlaceOnMap
from app.schemas.region import RegionCandidate, RegionChild, RegionNode

# geography → geometry 캐스팅 후 좌표 추출
_LAT = func.ST_Y(cast(Place.geom, Geometry))
_LNG = func.ST_X(cast(Place.geom, Geometry))


def _full_name(parent_name: str | None, name: str) -> str:
    """'전라북도 전주시'처럼 사용자에게 그대로 보여줄 수 있는 이름."""
    return f"{parent_name} {name}" if parent_name else name


def _region_ref(region_id: int | None, name: str | None, parent_name: str | None) -> RegionRef | None:
    if region_id is None or name is None:
        return None
    return RegionRef(region_id=region_id, name=name, full_name=_full_name(parent_name, name))


# ── 작품 ──────────────────────────────────────────────────────────────────

def _place_count_sq():
    """작품별 촬영지 수(상관 서브쿼리). GROUP BY 없이 붙일 수 있어 페이지네이션이 단순해진다."""
    return (
        select(func.count())
        .select_from(ContentPlaceMapping)
        .where(ContentPlaceMapping.content_id == Content.content_id)
        .scalar_subquery()
    )


def _title_score(q: str):
    """정확일치 1.0 > 접두일치 0.8 > 부분일치 0.5.

    부분일치라 '기생'으로 검색하면 「기생충」과 「음란 기생」이 함께 걸린다.
    관련도로 정렬해 의도한 작품이 위로 오게 한다.
    """
    return cast(
        case(
            (Content.title_ko == q, 1.0),
            (Content.title_ko.ilike(f"{q}%"), 0.8),
            else_=0.5,
        ),
        Float,
    )


async def search_contents(
    db: AsyncSession, q: str, limit: int, offset: int
) -> tuple[list[ContentSummary], int]:
    q = q.strip()
    if not q:
        return [], 0

    where = Content.title_ko.ilike(f"%{q}%")
    total = await db.scalar(select(func.count()).select_from(Content).where(where))

    pc = _place_count_sq().label("place_count")
    score = _title_score(q).label("score")
    rows = (
        await db.execute(
            select(Content, pc, score)
            .where(where)
            .order_by(score.desc(), pc.desc(), Content.production_year.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [
        ContentSummary(
            content_id=c.content_id,
            title_ko=c.title_ko,
            production_year=c.production_year,
            content_type=c.content_type.value if hasattr(c.content_type, "value") else str(c.content_type),
            genre_tags=c.genre_tags,
            poster_url=c.poster_url,
            vote_average=float(c.vote_average) if c.vote_average is not None else None,
            place_count=n,
        )
        for c, n, _ in rows
    ], (total or 0)


async def resolve_contents(db: AsyncSession, query: str, limit: int = 10) -> list[ContentCandidate]:
    """AI가 뽑은 제목 문자열 → 후보 목록. 동명 작품이 있어 항상 배열."""
    query = query.strip()
    if not query:
        return []

    pc = _place_count_sq().label("place_count")
    score = _title_score(query).label("score")
    rows = (
        await db.execute(
            select(Content, score)
            .where(Content.title_ko.ilike(f"%{query}%"))
            .order_by(score.desc(), pc.desc(), Content.production_year.desc().nulls_last())
            .limit(limit)
        )
    ).all()

    return [
        ContentCandidate(
            content_id=c.content_id,
            title_ko=c.title_ko,
            production_year=c.production_year,
            content_type=c.content_type.value if hasattr(c.content_type, "value") else str(c.content_type),
            poster_url=c.poster_url,
            score=round(float(s), 2),
        )
        for c, s in rows
    ]


async def get_content(db: AsyncSession, content_id: int) -> ContentDetail | None:
    row = (
        await db.execute(
            select(Content, _place_count_sq().label("pc")).where(Content.content_id == content_id)
        )
    ).first()
    if row is None:
        return None
    c, pc = row
    return ContentDetail(
        content_id=c.content_id,
        title_ko=c.title_ko,
        original_title=c.original_title,
        production_year=c.production_year,
        content_type=c.content_type.value if hasattr(c.content_type, "value") else str(c.content_type),
        genre_tags=c.genre_tags,
        overview=c.overview,
        poster_url=c.poster_url,
        vote_average=float(c.vote_average) if c.vote_average is not None else None,
        runtime=c.runtime,
        tmdb_id=c.tmdb_id,
        place_count=pc,
    )


# ── 지역 ──────────────────────────────────────────────────────────────────

async def resolve_regions(db: AsyncSession, name: str, limit: int = 20) -> list[RegionCandidate]:
    """지역명 → 후보 목록.

    ★ 「중구」는 6곳, 「남구」는 5곳이라 단일 답이 없다.
    '서울 중구'처럼 시도가 함께 오면 그걸 힌트로 써서 후보를 1개로 좁힌다.
    """
    name = name.strip()
    if not name:
        return []

    parent = aliased(Region)
    stmt = (
        select(
            Region.region_id,
            Region.name,
            Region.level,
            Region.bjd_cd,
            parent.name.label("parent_name"),
        )
        .select_from(Region)
        .outerjoin(parent, parent.region_id == Region.parent_id)
    )

    tokens = name.split()
    if len(tokens) >= 2:
        # 마지막 토큰이 찾는 지역, 앞쪽은 상위 지역 힌트 ("서울 중구" → hint=서울, target=중구)
        hint, target = " ".join(tokens[:-1]), tokens[-1]
        stmt = stmt.where(
            Region.name.ilike(f"%{target}%"),
            or_(parent.name.ilike(f"%{hint}%"), Region.name.ilike(f"%{hint}%")),
        )
    else:
        stmt = stmt.where(Region.name.ilike(f"%{name}%"))

    # 정확일치 우선 → 시군구 우선(사용자는 보통 구·시 단위를 말한다)
    rows = (
        await db.execute(
            stmt.order_by(
                case((Region.name == tokens[-1], 0), else_=1),
                case((Region.level == "sigungu", 0), else_=1),
                Region.name,
            ).limit(limit)
        )
    ).all()

    return [
        RegionCandidate(
            region_id=r.region_id,
            name=r.name,
            full_name=_full_name(r.parent_name, r.name),
            level=r.level,
            bjd_cd=r.bjd_cd,
        )
        for r in rows
    ]


async def resolve_region_exists(db: AsyncSession, region_id: int) -> bool:
    """지역이 실제로 있는지. '장소 0건'과 '지역 없음'을 구분해 404를 내기 위함."""
    return (
        await db.scalar(select(func.count()).select_from(Region).where(Region.region_id == region_id))
    ) > 0


async def list_regions(db: AsyncSession, flat: bool) -> tuple[list[RegionNode], int]:
    rows = (
        await db.execute(
            select(
                Region.region_id,
                Region.name,
                Region.level,
                Region.parent_id,
                Region.bjd_cd,
            ).order_by(Region.level.desc(), Region.name)
        )
    ).all()

    def node(r, children=None) -> RegionNode:
        return RegionNode(
            region_id=r.region_id,
            name=r.name,
            level=r.level,
            parent_id=r.parent_id,
            bjd_cd=r.bjd_cd,
            children=children,
        )

    if flat:
        items = [node(r) for r in rows]
        return items, len(items)

    kids: dict[int, list[RegionChild]] = {}
    for r in rows:
        if r.level == "2" and r.parent_id:
            kids.setdefault(r.parent_id, []).append(
                RegionChild(region_id=r.region_id, name=r.name, level=r.level, bjd_cd=r.bjd_cd)
            )
    sidos = [r for r in rows if r.level == "1"]
    items = [node(r, kids.get(r.region_id, [])) for r in sorted(sidos, key=lambda x: x.name)]
    return items, len(items)


# ── 장소 ──────────────────────────────────────────────────────────────────

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
        .outerjoin(parent, parent.region_id == Region.parent_id)
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
    """작품의 촬영지 목록. 장면설명은 그 작품 기준으로 붙인다."""
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
            region=_region_ref(r.region_id, r.region_name, r.parent_name),
            scene_description=r.scene_description,
            episode=r.episode,
        )
        for r in rows
    ], (total or 0)


async def _region_scope_ids(db: AsyncSession, region_id: int) -> list[int]:
    """시도면 자기 + 자식 시군구, 시군구면 자기만."""
    children = (
        await db.execute(
            select(Region.region_id).where(Region.parent_id == region_id)
        )
    ).scalars().all()
    return [region_id, *children]


async def places_in_region(
    db: AsyncSession, region_id: int, content_id: int | None, limit: int, offset: int
) -> tuple[list[PlaceOnMap], int]:
    scope = await _region_scope_ids(db, region_id)

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
            region=_region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
        )
        for r in rows
    ], (total or 0)


async def places_near_region(
    db: AsyncSession, region_id: int, radius_km: float, limit: int, offset: int
) -> tuple[list[PlaceOnMap], int] | None:
    """지역 중심점 반경 내 장소. 중심점이 없으면 None."""
    region_point = (
        await db.execute(
            select(cast(func.ST_PointOnSurface(Region.boundary), Geography)).where(
                Region.region_id == region_id
            )
        )
    ).scalar_one_or_none()
    if region_point is None:
        return None

    radius_m = radius_km * 1000
    dist = func.ST_Distance(Place.geom, region_point).label("dist_m")
    where = func.ST_DWithin(Place.geom, region_point, radius_m)

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
            region=_region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
            distance_km=round(r.dist_m / 1000, 2),
        )
        for r in rows
    ], (total or 0)
