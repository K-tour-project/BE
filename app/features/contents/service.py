"""작품 조회 로직 (5단계).

계약서(API_CONTRACT.md §3~§4)의 응답을 만들기 위한 DB 질의.
라우터는 얇게 두고 여기서 데이터를 완성해 돌려준다.

작품의 '촬영지 목록'은 장소 도메인이라 여기가 아니라
[`app/features/places/service.py`](../places/service.py)의 `places_of_content`에 있다.
"""
from __future__ import annotations

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.contents.schema import (
    ContentCandidate,
    ContentDetail,
    ContentSummary,
)
from app.models import Content, ContentPlaceMapping


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
