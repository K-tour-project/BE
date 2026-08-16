"""지역 조회 로직 (5단계).

계약서(API_CONTRACT.md §3)의 응답을 만들기 위한 DB 질의.

설계 메모
- 좌표는 `geography` 컬럼이라 ST_X/ST_Y를 쓰려면 geometry로 캐스팅해야 한다.
- `full_name`·`region_ref`·`region_scope_ids`는 **장소 기능도 함께 쓴다**(장소 응답에
  소속 지역이 붙고, 시도로 조회하면 하위 시군구까지 포함해야 하므로).
  지역 도메인 지식이라 여기가 주인이고, places 쪽에서 import해 간다.
"""
from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.regions.schema import RegionCandidate, RegionChild, RegionNode
from app.models import Region
from app.shared.schema import Location, RegionRef


def full_name(parent_name: str | None, name: str) -> str:
    """'전라북도 전주시'처럼 사용자에게 그대로 보여줄 수 있는 이름."""
    return f"{parent_name} {name}" if parent_name else name


def region_ref(region_id: int | None, name: str | None, parent_name: str | None) -> RegionRef | None:
    if region_id is None or name is None:
        return None
    return RegionRef(region_id=region_id, name=name, full_name=full_name(parent_name, name))


async def region_scope_ids(db: AsyncSession, region_id: int) -> list[int]:
    """시도면 자기 + 자식 시군구, 시군구면 자기만.

    사용자는 '강원도'로도 촬영지를 찾기 때문에, 시도로 조회하면 하위 시군구의 장소까지 포함한다.
    """
    children = (
        await db.execute(
            select(Region.region_id).where(Region.parent_region_id == region_id)
        )
    ).scalars().all()
    return [region_id, *children]


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
            parent.name.label("parent_name"),
            func.ST_Y(cast(Region.centroid, Geometry)).label("lat"),
            func.ST_X(cast(Region.centroid, Geometry)).label("lng"),
        )
        .select_from(Region)
        .outerjoin(parent, parent.region_id == Region.parent_region_id)
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
            full_name=full_name(r.parent_name, r.name),
            level=r.level,
            centroid=Location(lat=r.lat, lng=r.lng) if r.lat is not None else None,
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
                Region.parent_region_id,
                func.ST_Y(cast(Region.centroid, Geometry)).label("lat"),
                func.ST_X(cast(Region.centroid, Geometry)).label("lng"),
            ).order_by(Region.level.desc(), Region.name)
        )
    ).all()

    def node(r, children=None) -> RegionNode:
        return RegionNode(
            region_id=r.region_id,
            name=r.name,
            level=r.level,
            parent_region_id=r.parent_region_id,
            centroid=Location(lat=r.lat, lng=r.lng) if r.lat is not None else None,
            children=children,
        )

    if flat:
        items = [node(r) for r in rows]
        return items, len(items)

    kids: dict[int, list[RegionChild]] = {}
    for r in rows:
        if r.level == "sigungu" and r.parent_region_id:
            kids.setdefault(r.parent_region_id, []).append(
                RegionChild(region_id=r.region_id, name=r.name, level=r.level)
            )
    sidos = [r for r in rows if r.level == "sido"]
    items = [node(r, kids.get(r.region_id, [])) for r in sorted(sidos, key=lambda x: x.name)]
    return items, len(items)
