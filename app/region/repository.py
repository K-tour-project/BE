"""Database access for region APIs."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Region


async def list_sidos(db: AsyncSession):
    child = Region.__table__.alias("child")
    sigungu_count = (
        select(func.count())
        .select_from(child)
        .where(child.c.parent_id == Region.region_id, child.c.level == "2")
        .scalar_subquery()
    )

    stmt = (
        select(
            Region.region_id,
            Region.name,
            sigungu_count.label("sigungu_count"),
        )
        .where(Region.level == "1")
        .order_by(Region.name)
    )
    return (await db.execute(stmt)).all()


async def get_sido(db: AsyncSession, sido_id: int):
    stmt = select(Region.region_id, Region.name).where(
        Region.region_id == sido_id,
        Region.level == "1",
    )
    return (await db.execute(stmt)).first()


async def get_sigungu(db: AsyncSession, sigungu_id: int):
    stmt = select(Region.region_id, Region.parent_id, Region.name).where(
        Region.region_id == sigungu_id,
        Region.level == "2",
    )
    return (await db.execute(stmt)).first()


async def list_sigungu_by_sido(db: AsyncSession, sido_id: int):
    stmt = (
        select(Region.region_id, Region.name)
        .where(Region.parent_id == sido_id, Region.level == "2")
        .order_by(Region.name)
    )
    return (await db.execute(stmt)).all()
