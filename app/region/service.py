"""Business logic for region selection APIs."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.region import repository
from app.region.schemas import (
    RegionOption,
    RegionSelectionRequest,
    RegionSelectionResponse,
    SidoOption,
    SigunguListResponse,
)


def _to_region_option(row) -> RegionOption:
    return RegionOption(region_id=row.region_id, name=row.name)


async def list_sidos(db: AsyncSession) -> list[SidoOption]:
    rows = await repository.list_sidos(db)
    return [
        SidoOption(
            region_id=row.region_id,
            name=row.name,
            has_sigungu=row.sigungu_count > 0,
        )
        for row in rows
    ]


async def list_sigungu(db: AsyncSession, sido_id: int) -> SigunguListResponse | None:
    sido_row = await repository.get_sido(db, sido_id)
    if sido_row is None:
        return None

    sigungu_rows = await repository.list_sigungu_by_sido(db, sido_id)
    items = [_to_region_option(row) for row in sigungu_rows]
    sido = SidoOption(
        region_id=sido_row.region_id,
        name=sido_row.name,
        has_sigungu=bool(items),
    )
    return SigunguListResponse(
        sido=sido,
        disable_sigungu_select=not items,
        items=items,
    )


async def select_region(
    db: AsyncSession, request: RegionSelectionRequest
) -> RegionSelectionResponse | None:
    sigungu_rows = await repository.list_sigungu_by_sido(db, request.sido_id)
    sigungu_items = [_to_region_option(row) for row in sigungu_rows]

    sido_row = await repository.get_sido(db, request.sido_id)
    if sido_row is None:
        return None

    sido = SidoOption(
        region_id=sido_row.region_id,
        name=sido_row.name,
        has_sigungu=bool(sigungu_items),
    )

    if not sigungu_items:
        return RegionSelectionResponse(
            sido=sido,
            sigungu=None,
            selected_region_id=sido.region_id,
        )

    if request.sigungu_id is None:
        raise ValueError("sigungu_id is required for this sido.")

    sigungu_row = await repository.get_sigungu(db, request.sigungu_id)
    if sigungu_row is None or sigungu_row.parent_id != request.sido_id:
        raise ValueError("sigungu_id does not belong to sido_id.")

    sigungu = _to_region_option(sigungu_row)
    return RegionSelectionResponse(
        sido=sido,
        sigungu=sigungu,
        selected_region_id=sigungu.region_id,
    )
