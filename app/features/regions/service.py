"""Region query service."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.regions.schema import (
    RegionBoundaryResponse,
    RegionCandidate,
    RegionChild,
    RegionNode,
)
from app.models import Region
from app.shared.schema import Location, RegionRef


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


def _centroid_lat():
    return func.ST_Y(func.ST_PointOnSurface(Region.boundary)).label("lat")


def _centroid_lng():
    return func.ST_X(func.ST_PointOnSurface(Region.boundary)).label("lng")


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


def _base_region_columns(parent, include_boundary: bool = False):
    columns = [
        Region.region_id,
        Region.name,
        Region.level,
        Region.parent_id,
        parent.name.label("parent_name"),
        _centroid_lat(),
        _centroid_lng(),
    ]
    if include_boundary:
        columns.append(_boundary_geojson())
    return columns


async def resolve_regions(
    db: AsyncSession,
    name: str,
    limit: int = 20,
    include_boundary: bool = False,
) -> list[RegionCandidate]:
    name = name.strip()
    if not name:
        return []

    parent = aliased(Region)
    stmt = (
        select(*_base_region_columns(parent, include_boundary))
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
            centroid=_location(r.lat, r.lng),
            boundary=_load_geojson(getattr(r, "boundary_geojson", None)),
        )
        for r in rows
    ]


async def get_region_boundary(db: AsyncSession, region_id: int) -> RegionBoundaryResponse | None:
    parent = aliased(Region)
    row = (
        await db.execute(
            select(*_base_region_columns(parent, include_boundary=True))
            .select_from(Region)
            .outerjoin(parent, parent.region_id == Region.parent_id)
            .where(Region.region_id == region_id)
        )
    ).first()
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
        centroid=_location(row.lat, row.lng),
        boundary=boundary,
    )


async def resolve_region_exists(db: AsyncSession, region_id: int) -> bool:
    return (
        await db.scalar(select(func.count()).select_from(Region).where(Region.region_id == region_id))
    ) > 0


async def list_regions(
    db: AsyncSession,
    flat: bool,
    include_boundary: bool = False,
) -> tuple[list[RegionNode], int]:
    columns = [
        Region.region_id,
        Region.name,
        Region.level,
        Region.parent_id,
        _centroid_lat(),
        _centroid_lng(),
    ]
    if include_boundary:
        columns.append(_boundary_geojson())

    rows = (
        await db.execute(select(*columns).order_by(Region.level.desc(), Region.name))
    ).all()

    def boundary(r) -> dict[str, Any] | None:
        return _load_geojson(getattr(r, "boundary_geojson", None))

    def child(r) -> RegionChild:
        return RegionChild(
            region_id=r.region_id,
            name=r.name,
            level=r.level,
            centroid=_location(r.lat, r.lng),
            boundary=boundary(r),
        )

    def node(r, children=None) -> RegionNode:
        return RegionNode(
            region_id=r.region_id,
            name=r.name,
            level=r.level,
            parent_region_id=r.parent_id,
            centroid=_location(r.lat, r.lng),
            boundary=boundary(r),
            children=children,
        )

    if flat:
        items = [node(r) for r in rows]
        return items, len(items)

    kids: dict[int, list[RegionChild]] = {}
    for r in rows:
        if r.level == "sigungu" and r.parent_id:
            kids.setdefault(r.parent_id, []).append(child(r))

    sidos = [r for r in rows if r.level == "sido"]
    items = [node(r, kids.get(r.region_id, [])) for r in sorted(sidos, key=lambda x: x.name)]
    return items, len(items)
