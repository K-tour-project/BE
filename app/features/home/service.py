"""홈 화면 인기 작품과 인기 관광지 조립."""
from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.home.schema import HomeOut, PopularProduct, PopularTourismPlace
from app.integrations.call_log import save_calls
from app.integrations.tour_api import TourApiClient, TourApiError
from app.models import Place, PlaceFavorite, Product

HOME_ITEM_LIMIT = 10


async def popular_products(
    db: AsyncSession, limit: int = HOME_ITEM_LIMIT
) -> list[PopularProduct]:
    """별점 내림차순 작품. 동점은 인기도와 ID로 항상 같은 순서를 만든다."""
    products = (
        await db.scalars(
            select(Product)
            .order_by(
                Product.rating.desc().nulls_last(),
                Product.popularity.desc().nulls_last(),
                Product.product_id.asc(),
            )
            .limit(limit)
        )
    ).all()
    return [
        PopularProduct(
            product_id=product.product_id,
            title=product.title,
            category=product.category,
            poster_url=product.poster_url,
            rating=float(product.rating) if product.rating is not None else None,
            release_year=product.first_air_date.year if product.first_air_date else None,
            detail_path=f"/contents/{product.product_id}",
        )
        for product in products
    ]


async def popular_tourism_places(
    db: AsyncSession, limit: int = HOME_ITEM_LIMIT
) -> list[PopularTourismPlace]:
    """무료·유료 구분 없이 앱에서 많이 찜한 관광지를 TourAPI 카드와 연결한다.

    DB 촬영지 찜은 ``places.tour_content_id``, TourAPI 관광지 직접 찜은
    ``favorites.tour_content_id``를 사용한다. 같은 사용자가 같은 TourAPI 장소를 여러
    경로로 찜한 과거 데이터가 있어도 한 명으로 집계한다.
    """
    content_id = func.coalesce(
        PlaceFavorite.tour_content_id, Place.tour_content_id
    ).label("content_id")
    favorite_count = func.count(func.distinct(PlaceFavorite.user_id)).label(
        "favorite_count"
    )
    rows = (
        await db.execute(
            select(content_id, favorite_count)
            .select_from(PlaceFavorite)
            .outerjoin(Place, Place.place_id == PlaceFavorite.place_id)
            .where(content_id.is_not(None))
            .group_by(content_id)
            .order_by(favorite_count.desc(), content_id.asc())
            .limit(limit)
        )
    ).all()
    api = TourApiClient()
    try:
        async with api:
            results = await asyncio.gather(
                *(api.detail_common(str(row.content_id)) for row in rows),
                return_exceptions=True,
            )
            items: list[PopularTourismPlace] = []
            failures: list[TourApiError] = []
            for ranked, result in zip(rows, results, strict=True):
                if isinstance(result, TourApiError):
                    failures.append(result)
                    continue
                if isinstance(result, BaseException):
                    raise result
                if result is None:
                    continue
                items.append(
                    _tourism_card(
                        result,
                        content_id=str(ranked.content_id),
                        favorite_count=int(ranked.favorite_count),
                        ranking_source="FAVORITE_COUNT",
                    )
                )

            if len(items) < limit:
                recent, _ = await api.nationwide_recent_with_image(
                    size=max(limit * 2, 20)
                )
                seen = {item.content_id for item in items}
                for row in recent:
                    cid = str(row.get("contentid") or "")
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    items.append(
                        _tourism_card(
                            row,
                            content_id=cid,
                            favorite_count=0,
                            ranking_source="TOUR_API_RECENT",
                        )
                    )
                    if len(items) == limit:
                        break

            if failures and not items and len(failures) == len(rows):
                raise failures[0]
            return items
    finally:
        await save_calls(db, api.calls)


def _tourism_card(
    row: dict,
    *,
    content_id: str,
    favorite_count: int,
    ranking_source: Literal["FAVORITE_COUNT", "TOUR_API_RECENT"],
) -> PopularTourismPlace:
    address_parts = str(row.get("addr1") or "").split()
    return PopularTourismPlace(
        content_id=content_id,
        name=str(row.get("title") or ""),
        image_url=row.get("firstimage") or None,
        thumbnail_url=row.get("firstimage2") or row.get("firstimage") or None,
        sido_name=address_parts[0] if address_parts else None,
        sigungu_name=address_parts[1] if len(address_parts) > 1 else None,
        favorite_count=favorite_count,
        ranking_source=ranking_source,
        detail_path=f"/tourism-places/{content_id}",
    )


async def home(db: AsyncSession) -> HomeOut:
    products = await popular_products(db)
    tourism_places = await popular_tourism_places(db)
    return HomeOut(
        popular_products=products,
        popular_tourism_places=tourism_places,
    )
