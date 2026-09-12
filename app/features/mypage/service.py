"""User-scoped saves and profile editing, with live TourAPI place cards."""
from __future__ import annotations

import asyncio

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.mypage.schema import (
    FavoritePlaceOut, MyPageOut, ProfileOut, SavedCounts, SavedProductOut, SaveState,
)
from app.integrations.call_log import save_calls
from app.integrations.tour_api import TourApiClient, TourApiError
from app.models import Place, PlaceFavorite, Product, ProductFavorite, Region, User, UserProfile
from app.shared.schema import Page


async def saved_counts(db: AsyncSession, user_id: int) -> SavedCounts:
    row = (await db.execute(select(
        select(func.count()).select_from(PlaceFavorite).where(PlaceFavorite.user_id == user_id).scalar_subquery(),
        select(func.count()).select_from(ProductFavorite).where(ProductFavorite.user_id == user_id).scalar_subquery(),
    ))).one()
    return SavedCounts(favorite_place_count=row[0], saved_product_count=row[1])


async def mypage(db: AsyncSession, user: User, limit: int, offset: int) -> MyPageOut:
    # Materialize user data before optional call-log persistence can roll back a session.
    profile = ProfileOut.model_validate(user)
    counts = await saved_counts(db, user.user_id)
    places = await favorite_places(db, user.user_id, limit, offset, total=counts.favorite_place_count)
    return MyPageOut(user=profile, counts=counts, favorite_places=places)


async def _live_places(db: AsyncSession, user_id: int, content_ids: set[str]) -> dict:
    if not content_ids:
        return {}
    try:
        api = TourApiClient()
    except TourApiError:
        return {cid: (None, "unavailable") for cid in content_ids}
    semaphore = asyncio.Semaphore(5)

    async def fetch(cid):
        async with semaphore:
            try:
                row = await api.detail_common(cid)
                return cid, (row, "ok" if row else "not_found")
            except TourApiError:
                return cid, (None, "unavailable")

    try:
        async with api:
            return dict(await asyncio.gather(*(fetch(cid) for cid in sorted(content_ids))))
    finally:
        # Only HTTP work is concurrent; a shared AsyncSession is used sequentially.
        await save_calls(db, api.calls, user_id=user_id)


async def favorite_places(
    db: AsyncSession, user_id: int, limit: int, offset: int, *, total: int | None = None,
) -> Page[FavoritePlaceOut]:
    if total is None:
        total = await db.scalar(select(func.count()).select_from(PlaceFavorite).where(PlaceFavorite.user_id == user_id)) or 0
    parent = aliased(Region)
    rows = (await db.execute(
        select(
            PlaceFavorite.favorite_id, PlaceFavorite.place_id, PlaceFavorite.created_at,
            func.coalesce(PlaceFavorite.tour_content_id, Place.tour_content_id).label("tour_content_id"),
            Place.name, Region.name.label("region_name"), Region.level.label("region_level"),
            parent.name.label("parent_name"),
        )
        .outerjoin(Place, Place.place_id == PlaceFavorite.place_id)
        .outerjoin(Region, Region.region_id == Place.region_id)
        .outerjoin(parent, parent.region_id == Region.parent_id)
        .where(PlaceFavorite.user_id == user_id)
        .order_by(PlaceFavorite.created_at.desc(), PlaceFavorite.favorite_id.desc())
        .limit(limit).offset(offset)
    )).all()
    if not rows:
        return Page(items=[], total=total)

    content_ids = {r.tour_content_id for r in rows if r.tour_content_id}
    regions = (await db.execute(select(Region.bjd_cd, Region.name, Region.level))).all() if content_ids else []
    sido_names = {r.bjd_cd[:2]: r.name for r in regions if r.level == "1"}
    sigungu_names = {r.bjd_cd[:5]: r.name for r in regions if r.level == "2"}
    live = await _live_places(db, user_id, content_ids)
    items = []
    for row in rows:
        common, tour_status = live.get(row.tour_content_id, (None, "unmatched"))
        common = common or {}
        sido_code = str(common.get("lDongRegnCd") or "")
        sigungu_code = str(common.get("lDongSignguCd") or "")
        region_key = sigungu_code if len(sigungu_code) == 5 else sido_code + sigungu_code.zfill(3)
        items.append(FavoritePlaceOut(
            favorite_id=row.favorite_id, place_id=row.place_id,
            tour_content_id=row.tour_content_id,
            name=common.get("title") or row.name,
            thumbnail_url=common.get("firstimage2") or common.get("firstimage") or None,
            sido_name=sido_names.get(sido_code) or (row.region_name if row.region_level == "1" else row.parent_name),
            sigungu_name=sigungu_names.get(region_key) or (row.region_name if row.region_level == "2" else None),
            saved_at=row.created_at,
            detail_path=f"/places/{row.place_id}" if row.place_id is not None else f"/tourism-places/{row.tour_content_id}",
            tour_status=tour_status,
        ))
    return Page(items=items, total=total)


async def saved_products(db: AsyncSession, user_id: int, limit: int, offset: int) -> Page[SavedProductOut]:
    total = await db.scalar(select(func.count()).select_from(ProductFavorite).where(ProductFavorite.user_id == user_id)) or 0
    rows = (await db.execute(
        select(Product.product_id, Product.title, Product.poster_url, Product.category,
               Product.first_air_date, ProductFavorite.created_at)
        .join(ProductFavorite, ProductFavorite.product_id == Product.product_id)
        .where(ProductFavorite.user_id == user_id)
        .order_by(ProductFavorite.created_at.desc(), ProductFavorite.favorite_id.desc())
        .limit(limit).offset(offset)
    )).all()
    return Page(items=[SavedProductOut(
        product_id=r.product_id, title=r.title, poster_url=r.poster_url, category=r.category,
        release_year=r.first_air_date.year if r.first_air_date else None,
        saved_at=r.created_at, detail_path=f"/contents/{r.product_id}",
    ) for r in rows], total=total)


async def _state(db: AsyncSession, user_id: int, saved: bool, favorite_id: int | None = None) -> SaveState:
    return SaveState(is_saved=saved, favorite_id=favorite_id, **(await saved_counts(db, user_id)).model_dump())


async def add_place(db: AsyncSession, user_id: int, place_id: int) -> SaveState:
    place = await db.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "해당 장소를 찾을 수 없습니다.")
    return await _insert_place(db, user_id, place_id, place.tour_content_id)


async def add_tourism(db: AsyncSession, user_id: int, content_id: str) -> SaveState:
    existing = await db.scalar(select(PlaceFavorite.favorite_id).where(
        PlaceFavorite.user_id == user_id, _tourism_filter(content_id),
    ))
    if existing is not None:
        return await _state(db, user_id, True, existing)
    try:
        api = TourApiClient()
        try:
            async with api:
                common = await api.detail_common(content_id)
        finally:
            await save_calls(db, api.calls, user_id=user_id)
    except TourApiError as exc:
        raise HTTPException(502, "관광공사 API 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.") from exc
    if not common:
        raise HTTPException(404, "해당 관광지를 찾을 수 없습니다.")
    place_id = await db.scalar(select(Place.place_id).where(Place.tour_content_id == content_id).order_by(Place.place_id).limit(1))
    return await _insert_place(db, user_id, place_id, content_id)


def _tourism_filter(content_id: str):
    return or_(
        PlaceFavorite.tour_content_id == content_id,
        PlaceFavorite.place_id.in_(select(Place.place_id).where(Place.tour_content_id == content_id)),
    )


async def _insert_place(db: AsyncSession, user_id: int, place_id: int | None, content_id: str | None) -> SaveState:
    filters = [PlaceFavorite.place_id == place_id] if place_id is not None else []
    if content_id:
        filters.append(_tourism_filter(content_id))
    lookup = select(PlaceFavorite.favorite_id).where(
        PlaceFavorite.user_id == user_id, or_(*filters),
    ).order_by(PlaceFavorite.favorite_id).limit(1)
    favorite_id = await db.scalar(lookup)
    if favorite_id is not None:
        return await _state(db, user_id, True, favorite_id)
    await db.execute(insert(PlaceFavorite).values(
        user_id=user_id, place_id=place_id, tour_content_id=content_id,
    ).on_conflict_do_nothing())
    await db.commit()
    favorite_id = await db.scalar(lookup)
    return await _state(db, user_id, True, favorite_id)


async def remove_place(
    db: AsyncSession, user_id: int, *, favorite_id: int | None = None,
    place_id: int | None = None, content_id: str | None = None,
) -> SaveState:
    if favorite_id is not None:
        target = PlaceFavorite.favorite_id == favorite_id
    elif place_id is not None:
        content_id = await db.scalar(select(Place.tour_content_id).where(Place.place_id == place_id))
        target = PlaceFavorite.place_id == place_id
        if content_id:
            target = or_(target, _tourism_filter(content_id))
    elif content_id is not None:
        target = _tourism_filter(content_id)
    else:
        raise ValueError("A favorite target is required")
    await db.execute(delete(PlaceFavorite).where(PlaceFavorite.user_id == user_id, target))
    await db.commit()
    return await _state(db, user_id, False)


async def save_product(db: AsyncSession, user_id: int, product_id: int) -> SaveState:
    if await db.scalar(select(Product.product_id).where(Product.product_id == product_id)) is None:
        raise HTTPException(404, "해당 작품을 찾을 수 없습니다.")
    await db.execute(insert(ProductFavorite).values(user_id=user_id, product_id=product_id).on_conflict_do_nothing())
    await db.commit()
    return await _state(db, user_id, True)


async def remove_product(db: AsyncSession, user_id: int, product_id: int) -> SaveState:
    await db.execute(delete(ProductFavorite).where(ProductFavorite.user_id == user_id, ProductFavorite.product_id == product_id))
    await db.commit()
    return await _state(db, user_id, False)


async def update_profile(db: AsyncSession, user: User, image_url: str | None) -> ProfileOut:
    if image_url is None:
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user.user_id))
    else:
        await db.execute(insert(UserProfile).values(user_id=user.user_id, profile_image_url=image_url)
                         .on_conflict_do_update(index_elements=[UserProfile.user_id], set_={"profile_image_url": image_url}))
    await db.commit()
    await db.refresh(user, attribute_names=["profile"])
    return ProfileOut.model_validate(user)
