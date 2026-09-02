"""Region query service."""
from __future__ import annotations

import json
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.regions.schema import (
    RegionBoundaryResponse,
    RegionCandidate,
    RegionOption,
)
from app.models import Region
from app.shared.schema import Location, RegionRef

SIDO_LEVEL = "1"
SIGUNGU_LEVEL = "2"


def full_name(parent_name: str | None, name: str) -> str:
    return f"{parent_name} {name}" if parent_name else name


def region_ref(region_id: int | None, name: str | None, parent_name: str | None) -> RegionRef | None:
    if region_id is None or name is None:
        return None
    return RegionRef(region_id=region_id, name=name, full_name=full_name(parent_name, name))


async def region_scope_ids(db: AsyncSession, region_id: int) -> list[int]:
    children = (
        await db.execute(select(Region.region_id).where(Region.parent_id == region_id))
    ).scalars().all()
    return [region_id, *children]


def _centroid_point():
    return func.ST_PointOnSurface(Region.boundary)


def _centroid_lat():
    return func.ST_Y(_centroid_point()).label("lat")


def _centroid_lng():
    return func.ST_X(_centroid_point()).label("lng")


def _boundary_geojson():
    return func.ST_AsGeoJSON(Region.boundary).label("boundary_geojson")


def _location(lat: float | None, lng: float | None) -> Location | None:
    if lat is None or lng is None:
        return None
    return Location(lat=lat, lng=lng)


def _load_geojson(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return json.loads(raw)


def _option_columns(parent, child_count):
    return [
        Region.region_id,
        Region.name,
        Region.level,
        Region.parent_id,
        Region.bjd_cd,
        parent.name.label("parent_name"),
        child_count.label("child_count"),
        _centroid_lat(),
        _centroid_lng(),
    ]


def _child_count_subquery():
    child = Region.__table__.alias("child")
    return (
        select(func.count())
        .select_from(child)
        .where(child.c.parent_id == Region.region_id)
        .scalar_subquery()
    )


def _to_option(row) -> RegionOption:
    return RegionOption(
        region_id=row.region_id,
        name=row.name,
        full_name=full_name(row.parent_name, row.name),
        level=row.level,
        parent_region_id=row.parent_id,
        bjd_cd=row.bjd_cd,
        has_children=(row.child_count or 0) > 0,
        centroid=_location(row.lat, row.lng),
    )


async def list_sidos(db: AsyncSession) -> tuple[list[RegionOption], int]:
    parent = aliased(Region)
    child_count = _child_count_subquery()
    rows = (
        await db.execute(
            select(*_option_columns(parent, child_count))
            .select_from(Region)
            .outerjoin(parent, parent.region_id == Region.parent_id)
            .where(Region.level == SIDO_LEVEL)
            .order_by(Region.region_id.asc())
        )
    ).all()
    items = [_to_option(row) for row in rows]
    return items, len(items)


async def list_children(db: AsyncSession, sido_id: int) -> tuple[list[RegionOption], int] | None:
    exists = await db.scalar(
        select(func.count()).select_from(Region).where(
            Region.region_id == sido_id,
            Region.level == SIDO_LEVEL,
        )
    )
    if not exists:
        return None

    parent = aliased(Region)
    child_count = _child_count_subquery()
    rows = (
        await db.execute(
            select(*_option_columns(parent, child_count))
            .select_from(Region)
            .outerjoin(parent, parent.region_id == Region.parent_id)
            .where(Region.parent_id == sido_id)
            .order_by(Region.region_id.asc())
        )
    ).all()
    items = [_to_option(row) for row in rows]
    return items, len(items)


async def resolve_regions(db: AsyncSession, name: str, limit: int = 20) -> list[RegionCandidate]:
    name = name.strip()
    if not name:
        return []

    parent = aliased(Region)
    child_count = _child_count_subquery()
    stmt = (
        select(*_option_columns(parent, child_count))
        .select_from(Region)
        .outerjoin(parent, parent.region_id == Region.parent_id)
    )

    tokens = name.split()
    if len(tokens) >= 2:
        hint, target = " ".join(tokens[:-1]), tokens[-1]
        stmt = stmt.where(
            Region.name.ilike(f"%{target}%"),
            or_(parent.name.ilike(f"%{hint}%"), Region.name.ilike(f"%{hint}%")),
        )
    else:
        stmt = stmt.where(Region.name.ilike(f"%{name}%"))

    rows = (
        await db.execute(
            stmt.order_by(
                case((Region.name == tokens[-1], 0), else_=1),
                case((Region.level == SIGUNGU_LEVEL, 0), else_=1),
                Region.name,
            ).limit(limit)
        )
    ).all()

    return [RegionCandidate(**_to_option(row).model_dump()) for row in rows]


async def get_region_boundary(db: AsyncSession, region_id: int) -> RegionBoundaryResponse | None:
    parent = aliased(Region)
    row = (
        await db.execute(
            select(
                Region.region_id,
                Region.name,
                Region.level,
                Region.parent_id,
                Region.bjd_cd,
                parent.name.label("parent_name"),
                _centroid_lat(),
                _centroid_lng(),
                _boundary_geojson(),
            )
            .select_from(Region)
            .outerjoin(parent, parent.region_id == Region.parent_id)
            .where(Region.region_id == region_id)
        )
    ).first()
    return _boundary_response(row)


async def get_region_boundary_by_name(db: AsyncSession, name: str) -> RegionBoundaryResponse | None:
    matches = await resolve_regions(db, name, limit=2)
    if len(matches) != 1:
        return None
    return await get_region_boundary(db, matches[0].region_id)


def _boundary_response(row) -> RegionBoundaryResponse | None:
    if row is None:
        return None

    boundary = _load_geojson(row.boundary_geojson)
    if boundary is None:
        return None

    return RegionBoundaryResponse(
        region_id=row.region_id,
        name=row.name,
        full_name=full_name(row.parent_name, row.name),
        level=row.level,
        parent_region_id=row.parent_id,
        bjd_cd=row.bjd_cd,
        centroid=_location(row.lat, row.lng),
        boundary=boundary,
    )


async def resolve_region_exists(db: AsyncSession, region_id: int) -> bool:
    return (
        await db.scalar(select(func.count()).select_from(Region).where(Region.region_id == region_id))
    ) > 0


def boundary_point_for_distance():
    return cast(_centroid_point(), Geography)
