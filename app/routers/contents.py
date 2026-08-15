"""작품 관련 엔드포인트 — API_CONTRACT.md §3~§4.

라우터는 얇게: 입력 검증 → 서비스 호출 → 계약서 형태로 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.common import Page
from app.schemas.content import (
    ContentDetail,
    ContentResolveRequest,
    ContentResolveResponse,
    ContentSummary,
)
from app.schemas.place import PlaceInContent
from app.services import catalog

router = APIRouter(prefix="/contents", tags=["contents"])


@router.get("/search", response_model=Page[ContentSummary])
async def search_contents(
    q: str = Query(..., min_length=1, description="작품 제목(부분일치)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """작품 검색. 부분일치라 '기생'으로 찾으면 「기생충」·「음란 기생」이 함께 나온다.

    관련도(정확일치 > 접두 > 부분) → 촬영지 수 → 최신순으로 정렬한다.
    """
    items, total = await catalog.search_contents(db, q, limit, offset)
    return Page[ContentSummary](items=items, total=total)


@router.post("/resolve", response_model=ContentResolveResponse)
async def resolve_content(
    body: ContentResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """제목 텍스트 → 작품 후보 (AI 팀원용).

    ★ 동명 작품이 실재하므로(「만추」 1966·1981) **항상 배열**을 돌려준다.
      후보 0개도 정상 응답이다.
    """
    return ContentResolveResponse(candidates=await catalog.resolve_contents(db, body.query))


@router.get("/{content_id}", response_model=ContentDetail)
async def get_content(content_id: int, db: AsyncSession = Depends(get_db)):
    detail = await catalog.get_content(db, content_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="해당 작품을 찾을 수 없습니다.")
    return detail


@router.get("/{content_id}/places", response_model=Page[PlaceInContent])
async def get_content_places(
    content_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """이 작품의 촬영지 목록. 앱 화면 3(작품 상세 → 지도)의 핵심.

    `location`은 항상 있고(좌표 100%), `scene_description`은 75%가 비어 있다.
    """
    if await catalog.get_content(db, content_id) is None:
        raise HTTPException(status_code=404, detail="해당 작품을 찾을 수 없습니다.")
    items, total = await catalog.places_of_content(db, content_id, limit, offset)
    return Page[PlaceInContent](items=items, total=total)
