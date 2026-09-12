"""작품 조회 로직 (5단계).

계약서(API_CONTRACT.md §3~§4)의 응답을 만들기 위한 DB 질의.
라우터는 얇게 두고 여기서 데이터를 완성해 돌려준다.

작품의 '촬영지 목록'은 장소 도메인이라 여기가 아니라
[`app/features/places/service.py`](../places/service.py)의 `places_of_content`에 있다.
"""
from __future__ import annotations

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.features.contents.schema import (
    ContentCandidate,
    ContentSummary,
    ProductDetail,
    MovieProductDetail,
    DramaProductDetail,
    FilmingLocationSummary,
    RelatedProductSummary,
)
from app.models import Place, Product, Region


RELATED_PRODUCT_LIMIT = 6


def _place_count_sq():
    """products.title과 연결된 places 행 수."""
    return (
        select(func.count())
        .select_from(Place)
        .where(Place.title == Product.title)
        .scalar_subquery()
    )


def _title_score(q: str):
    """정확일치 1.0 > 접두일치 0.8 > 부분일치 0.5.

    부분일치라 '기생'으로 검색하면 「기생충」과 「음란 기생」이 함께 걸린다.
    관련도로 정렬해 의도한 작품이 위로 오게 한다.
    """
    return cast(
        case(
            (Product.title == q, 1.0),
            (Product.title.ilike(f"{q}%"), 0.8),
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

    where = Product.title.ilike(f"%{q}%")
    total = await db.scalar(select(func.count()).select_from(Product).where(where))

    pc = _place_count_sq().label("place_count")
    score = _title_score(q).label("score")
    rows = (
        await db.execute(
            select(Product, pc, score)
            .options(selectinload(Product.drama_detail))
            .where(where)
            .order_by(score.desc(), pc.desc(), Product.first_air_date.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [
        ContentSummary(
            product_id=c.product_id,
            title=c.title,
            first_air_date=c.first_air_date.isoformat() if c.first_air_date else None,
            category=c.category,
            product_type=c.drama_detail.content_type if c.category == "DRAMA" and c.drama_detail else None,
            genres=c.genres,
            poster_url=c.poster_url,
            rating=float(c.rating) if c.rating is not None else None,
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
            select(Product, score)
            .where(Product.title.ilike(f"%{query}%"))
            .order_by(score.desc(), pc.desc(), Product.first_air_date.desc().nulls_last())
            .limit(limit)
        )
    ).all()

    return [
        ContentCandidate(
            product_id=c.product_id,
            title=c.title,
            first_air_date=c.first_air_date.isoformat() if c.first_air_date else None,
            category=c.category,
            poster_url=c.poster_url,
            score=round(float(s), 2),
        )
        for c, s in rows
    ]


async def get_product(db: AsyncSession, product_id: int) -> ProductDetail | None:
    row = (
        await db.execute(
            select(Product, _place_count_sq().label("pc"))
            .options(selectinload(Product.movie_detail), selectinload(Product.drama_detail))
            .where(Product.product_id == product_id)
        )
    ).first()
    if row is None:
        return None
    product, place_count = row

    filming_locations, filming_location_count = await _filming_locations(db, product.title)
    related_products = await _related_products(db, product, RELATED_PRODUCT_LIMIT)
    common = dict(
        product_id=product.product_id,
        title=product.title,
        overview=product.overview,
        first_air_date=product.first_air_date.isoformat() if product.first_air_date else None,
        category=product.category,
        poster_url=product.poster_url,
        genres=product.genres,
        rating=float(product.rating) if product.rating is not None else None,
        popularity=float(product.popularity) if product.popularity is not None else None,
        place_count=place_count,
        filming_location_count=filming_location_count,
        filming_locations=filming_locations,
        related_products=related_products,
    )
    if product.category == "MOVIE":
        movie = product.movie_detail
        return MovieProductDetail(**common, runtime=movie.runtime if movie else None)
    if product.category == "DRAMA":
        drama = product.drama_detail
        return DramaProductDetail(
            **common,
            is_overview_translated=drama.overview_translated if drama else None,
            product_type=drama.content_type if drama else None,
            networks=drama.networks if drama else None,
            episode_count=drama.episode_count if drama else None,
            lead_actors=drama.cast if drama else None,
        )
    raise ValueError(f"Invalid product category: {product.category}")


def _genre_set(raw: str | None) -> set[str]:
    """CSV의 `|` 구분 장르를 비교 가능한 집합으로 바꾼다."""
    return {genre.strip().casefold() for genre in (raw or "").split("|") if genre.strip()}


async def _related_products(
    db: AsyncSession, product: Product, limit: int
) -> list[RelatedProductSummary]:
    """공통 장르가 있는 작품을 별점 내림차순으로 반환한다."""
    source_genres = _genre_set(product.genres)
    if not source_genres:
        return []

    candidates = (
        await db.scalars(
            select(Product)
            .where(
                Product.product_id != product.product_id,
                Product.genres.is_not(None),
            )
        )
    ).all()

    ranked: list[tuple[float, float, float, int, Product]] = []
    for candidate in candidates:
        candidate_genres = _genre_set(candidate.genres)
        overlap = source_genres & candidate_genres
        if not overlap:
            continue
        similarity = len(overlap) / len(source_genres | candidate_genres)
        popularity = float(candidate.popularity or 0)
        rating = float(candidate.rating or 0)
        ranked.append((rating, similarity, popularity, candidate.product_id, candidate))

    ranked.sort(key=lambda item: item[:4], reverse=True)
    return [
        RelatedProductSummary(
            product_id=candidate.product_id,
            title=candidate.title,
            category=candidate.category,
            poster_url=candidate.poster_url,
            detail_path=f"/contents/{candidate.product_id}",
        )
        for *_, candidate in ranked[:limit]
    ]


async def _filming_locations(
    db: AsyncSession, title: str
) -> tuple[list[FilmingLocationSummary], int]:
    """TourAPI content ID가 확인된 촬영지만 상세 화면에 노출한다."""
    parent = aliased(Region)
    where = (Place.title == title, Place.tour_content_id.is_not(None))
    total = await db.scalar(select(func.count()).select_from(Place).where(*where))
    rows = (
        await db.execute(
            select(
                Place.place_id,
                Place.tour_content_id,
                Place.name,
                Region.name.label("region_name"),
                parent.name.label("parent_name"),
            )
            .select_from(Place)
            .outerjoin(Region, Region.region_id == Place.region_id)
            .outerjoin(parent, parent.region_id == Region.parent_id)
            .where(*where)
            .order_by(Place.name, Place.place_id)
        )
    ).all()

    return [
        FilmingLocationSummary(
            place_id=row.place_id,
            tour_content_id=row.tour_content_id,
            name=row.name,
            sido_name=row.parent_name if row.parent_name else row.region_name,
            sigungu_name=row.region_name if row.parent_name else None,
            detail_path=f"/places/{row.place_id}",
        )
        for row in rows
    ], (total or 0)
