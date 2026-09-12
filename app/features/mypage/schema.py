"""My Page contract: profile/counts plus the initial favorite-place page."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.features.products.schema import ProductCategory
from app.shared.schema import Page


class ProfileOut(BaseModel):
    user_id: int
    nickname: str
    email: str | None = None
    profile_image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    # A required nullable field distinguishes reset from an accidentally empty body.
    profile_image_url: HttpUrl | None

    model_config = ConfigDict(extra="forbid")


class SavedCounts(BaseModel):
    favorite_place_count: int = Field(description="찜한 장소 개수")
    saved_product_count: int = Field(description="저장한 영화·드라마 작품 개수")


class FavoritePlaceOut(BaseModel):
    favorite_id: int
    place_id: int | None = None
    tour_content_id: str | None = None
    name: str | None = None
    thumbnail_url: str | None = None
    sido_name: str | None = None
    sigungu_name: str | None = None
    saved_at: datetime = Field(description="장소를 찜한 시각")
    detail_path: str = Field(description="목록 클릭 시 GET 요청할 기존 장소 상세 API 경로")
    # Keep saved rows/counts visible even when the external service is unavailable.
    tour_status: Literal["ok", "unmatched", "not_found", "unavailable"]


class SavedProductOut(BaseModel):
    product_id: int
    title: str
    poster_url: str | None = None
    category: ProductCategory
    release_year: int | None = None
    saved_at: datetime = Field(description="작품을 저장한 시각")
    detail_path: str = Field(description="목록 클릭 시 GET 요청할 기존 작품 상세 API 경로")


class MyPageOut(BaseModel):
    user: ProfileOut
    counts: SavedCounts
    favorite_places: Page[FavoritePlaceOut]


class SaveState(SavedCounts):
    is_saved: bool = Field(description="장소 API에서는 찜 여부, 작품 API에서는 저장 여부")
    favorite_id: int | None = None
