"""작품(contents) 응답 스키마 — API_CONTRACT.md §3~§4.

`| None` 이 붙은 필드는 계약서에서 `?` 로 표시한 것들이다. 실제로 비는 비율이 높아
(포스터 18%, 장르 18%) 프론트가 반드시 null 처리를 해야 한다.
"""
from __future__ import annotations

from pydantic import BaseModel


class ContentSummary(BaseModel):
    """검색 결과 한 줄. `GET /contents/search`"""

    content_id: int
    title_ko: str
    production_year: int | None = None
    content_type: str  # movie | drama | show
    genre_tags: list[str] | None = None
    poster_url: str | None = None  # 296편(18%)이 null
    vote_average: float | None = None
    place_count: int


class ContentCandidate(BaseModel):
    """리졸브 후보. `POST /contents/resolve`

    ★ 동명 작품이 실재하므로(만추 1966·1981) 항상 배열로 돌려준다.
    """

    content_id: int
    title_ko: str
    production_year: int | None = None
    content_type: str
    poster_url: str | None = None
    score: float  # 0.0~1.0 관련도


class ContentResolveRequest(BaseModel):
    query: str


class ContentResolveResponse(BaseModel):
    candidates: list[ContentCandidate]


class ContentDetail(BaseModel):
    """`GET /contents/{content_id}`"""

    content_id: int
    title_ko: str
    original_title: str | None = None
    production_year: int | None = None
    content_type: str
    genre_tags: list[str] | None = None
    overview: str | None = None
    poster_url: str | None = None
    vote_average: float | None = None
    runtime: int | None = None  # 분. 드라마는 null
    tmdb_id: int | None = None
    place_count: int


class ContentOnPlace(BaseModel):
    """장소에 붙는 작품 요약 — 지도 포스터 마커용."""

    content_id: int
    title_ko: str
    production_year: int | None = None
    poster_url: str | None = None
    scene_description: str | None = None  # 이 작품이 이 장소에서 찍은 장면
