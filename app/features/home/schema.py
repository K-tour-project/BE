"""홈 화면 응답 계약."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.features.products.schema import ProductCategory


class PopularProduct(BaseModel):
    product_id: int
    title: str
    category: ProductCategory
    poster_url: str | None = None
    rating: float | None = None
    release_year: int | None = None
    detail_path: str


class PopularTourismPlace(BaseModel):
    content_id: str
    name: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    sido_name: str | None = None
    sigungu_name: str | None = None
    favorite_count: int = Field(ge=0)
    ranking_source: Literal["FAVORITE_COUNT", "TOUR_API_RECENT"]
    detail_path: str


class HomeOut(BaseModel):
    popular_products: list[PopularProduct]
    popular_tourism_places: list[PopularTourismPlace]
    tourism_ranking_basis: Literal["FAVORITE_COUNT_THEN_TOUR_API_RECENT"] = (
        "FAVORITE_COUNT_THEN_TOUR_API_RECENT"
    )
