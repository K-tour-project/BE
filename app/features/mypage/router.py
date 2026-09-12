"""Authenticated My Page, saved lists, save buttons and profile settings."""
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.deps import CurrentUser, DbSession
from app.features.mypage import service
from app.features.mypage.schema import (
    FavoritePlaceOut, MyPageOut, ProfileOut, ProfileUpdate, SavedProductOut, SaveState,
)
from app.shared.schema import Page

router = APIRouter(prefix="/me", tags=["mypage"])
PositiveId = Annotated[int, Path(gt=0)]
TourContentId = Annotated[str, Path(pattern=r"^[1-9][0-9]{0,19}$")]
PageLimit = Annotated[int, Query(ge=1, le=50)]
PageOffset = Annotated[int, Query(ge=0)]


@router.get("/mypage", response_model=MyPageOut)
async def get_mypage(user: CurrentUser, db: DbSession, limit: PageLimit = 20, offset: PageOffset = 0):
    """화면 진입: 내 정보, 두 개수, 찜한 장소 첫 페이지. 작품 목록은 별도 조회."""
    return await service.mypage(db, user, limit, offset)


@router.get("/favorite-places", response_model=Page[FavoritePlaceOut])
async def favorite_places(user: CurrentUser, db: DbSession, limit: PageLimit = 20, offset: PageOffset = 0):
    """찜한 촬영지·관광지 통합 목록. 최신 찜 순이며 TourAPI는 실시간 호출."""
    return await service.favorite_places(db, user.user_id, limit, offset)


@router.delete("/favorite-places/{favorite_id}", response_model=SaveState)
async def delete_favorite(favorite_id: PositiveId, user: CurrentUser, db: DbSession):
    """목록의 favorite_id로 내 찜 취소. 이미 취소했어도 성공."""
    return await service.remove_place(db, user.user_id, favorite_id=favorite_id)


@router.put("/favorites/places/{place_id}", response_model=SaveState, summary="장소 찜")
async def add_place_favorite(place_id: PositiveId, user: CurrentUser, db: DbSession):
    """DB place_id로 촬영지 찜. 중복 요청은 한 건만 저장."""
    return await service.add_place(db, user.user_id, place_id)


@router.delete("/favorites/places/{place_id}", response_model=SaveState, summary="장소 찜 취소")
async def remove_place_favorite(place_id: PositiveId, user: CurrentUser, db: DbSession):
    return await service.remove_place(db, user.user_id, place_id=place_id)


@router.put("/favorites/tourism/{content_id}", response_model=SaveState, summary="관광지 찜")
async def add_tourism_favorite(content_id: TourContentId, user: CurrentUser, db: DbSession):
    """TourAPI content_id로 일반 관광지 또는 촬영지 찜."""
    return await service.add_tourism(db, user.user_id, content_id)


@router.delete("/favorites/tourism/{content_id}", response_model=SaveState, summary="관광지 찜 취소")
async def remove_tourism_favorite(content_id: TourContentId, user: CurrentUser, db: DbSession):
    return await service.remove_place(db, user.user_id, content_id=content_id)


@router.get("/saved-products", response_model=Page[SavedProductOut])
async def saved_products(user: CurrentUser, db: DbSession, limit: PageLimit = 20, offset: PageOffset = 0):
    """저장한 작품 탭 클릭 시 조회. 영화 개봉/드라마 최초 방영 연도 제공."""
    return await service.saved_products(db, user.user_id, limit, offset)


@router.put("/saved-products/{product_id}", response_model=SaveState, summary="작품 저장")
async def save_product(product_id: PositiveId, user: CurrentUser, db: DbSession):
    return await service.save_product(db, user.user_id, product_id)


@router.delete("/saved-products/{product_id}", response_model=SaveState, summary="작품 저장 취소")
async def remove_product(product_id: PositiveId, user: CurrentUser, db: DbSession):
    return await service.remove_product(db, user.user_id, product_id)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession):
    """내 프로필 이미지 URL 수정. null은 기본 프로필로 초기화."""
    return await service.update_profile(db, user, str(body.profile_image_url) if body.profile_image_url else None)
