"""작품 조회 로직 (5단계).

계약서(API_CONTRACT.md §3~§4)의 응답을 만들기 위한 DB 질의.
라우터는 얇게 두고 여기서 데이터를 완성해 돌려준다.

작품의 '촬영지 목록'은 장소 도메인이라 여기가 아니라
[`app/features/places/service.py`](../places/service.py)의 `places_of_content`에 있다.
"""
from __future__ import annotations

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.contents.category import category_label
from app.features.contents.schema import (
    ContentCandidate,
    ContentSummary,
    ProductDetail,
)
from app.models import Place, Product


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
            category=category_label(c.product_type),
            product_type=c.product_type,
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
            category=category_label(c.product_type),
            poster_url=c.poster_url,
            score=round(float(s), 2),
        )
        for c, s in rows
    ]


async def get_product(db: AsyncSession, product_id: int) -> ProductDetail | None:
    product = await db.scalar(select(Product).where(Product.product_id == product_id))
    if product is None:
        return None
    return ProductDetail(
        product_id=product.product_id,
        title=product.title,
        overview=product.overview,
        first_air_date=product.first_air_date.isoformat() if product.first_air_date else None,
        category=category_label(product.product_type),
        product_type=product.product_type,
        poster_url=product.poster_url,
        genres=product.genres,
        networks=product.networks,
        episode_count=product.episode_count,
        rating=float(product.rating) if product.rating is not None else None,
        popularity=float(product.popularity) if product.popularity is not None else None,
        lead_actors=product.lead_actors,
    )
