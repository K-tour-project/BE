"""작품(contents) 응답 스키마 — API_CONTRACT.md §3~§4.

`| None` 이 붙은 필드는 계약서에서 `?` 로 표시한 것들이다. 실제로 비는 비율이 높아
(포스터 18%, 장르 18%) 프론트가 반드시 null 처리를 해야 한다.
"""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, Field

ProductCategory = Literal["MOVIE", "DRAMA"]


class ContentSummary(BaseModel):
    """검색 결과 한 줄. `GET /contents/search`"""

    product_id: int
    title: str
    first_air_date: str | None = None
    category: ProductCategory
    product_type: str | None = None
    genres: str | None = None
    poster_url: str | None = None  # 296편(18%)이 null
    rating: float | None = None
    place_count: int


class ContentCandidate(BaseModel):
    """리졸브 후보. `POST /contents/resolve`

    ★ 동명 작품이 실재하므로(만추 1966·1981) 항상 배열로 돌려준다.
    """

    product_id: int
    title: str
    first_air_date: str | None = None
    category: ProductCategory
    poster_url: str | None = None
    score: float  # 0.0~1.0 관련도


class ContentResolveRequest(BaseModel):
    query: str


class ContentResolveResponse(BaseModel):
    candidates: list[ContentCandidate]


class ContentOnPlace(BaseModel):
    """장소에 붙는 작품 요약 — 지도 포스터 마커용."""

    product_id: int
    title: str
    category: ProductCategory
    poster_url: str | None = None
    detail_path: str


class FilmingLocationSummary(BaseModel):
    """TourAPI 관광지와 매칭된 작품 촬영지."""

    place_id: int
    tour_content_id: str
    name: str
    sido_name: str | None = None
    sigungu_name: str | None = None
    detail_path: str


class RelatedProductSummary(BaseModel):
    """상세 화면에 노출할 장르 유사 작품."""

    product_id: int
    title: str
    category: ProductCategory
    poster_url: str | None = None
    detail_path: str


class ProductCommonDetail(BaseModel):
    """products의 공통 정보. 전용 필드는 카테고리별 응답에만 포함한다."""

    product_id: int
    title: str
    overview: str | None = None
    first_air_date: str | None = None
    poster_url: str | None = None
    genres: str | None = None
    rating: float | None = None
    popularity: float | None = None
    place_count: int
    filming_location_count: int = 0
    filming_locations: list[FilmingLocationSummary] = Field(default_factory=list)
    related_products: list[RelatedProductSummary] = Field(default_factory=list)


class MovieProductDetail(ProductCommonDetail):
    category: Literal["MOVIE"] = "MOVIE"
    runtime: int | None = None


class DramaProductDetail(ProductCommonDetail):
    category: Literal["DRAMA"] = "DRAMA"
    is_overview_translated: bool | None = None
    product_type: str | None = None
    networks: str | None = None
    episode_count: int | None = None
    lead_actors: str | None = None


ProductDetail = Annotated[MovieProductDetail | DramaProductDetail, Field(discriminator="category")]
