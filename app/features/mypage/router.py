"""Authenticated My Page, saved lists, save buttons and profile settings."""
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Path, Query, UploadFile

from app.deps import CurrentUser, DbSession
from app.features.auth.schema import MessageOut
from app.features.mypage import service
from app.features.mypage.schema import FavoritePlaceOut, MyPageOut, ProfileOut, SavedProductOut, SaveState
from app.integrations.r2 import MAX_PROFILE_IMAGE_BYTES, identify_profile_image
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
async def update_profile(
    user: CurrentUser,
    db: DbSession,
    profile_image: Annotated[UploadFile | None, File()] = None,
    remove_image: Annotated[bool, Form()] = False,
):
    """프로필 이미지 파일 교체. remove_image=true이면 기본 이미지로 초기화한다."""
    if profile_image is not None and remove_image:
        raise HTTPException(status_code=400, detail="이미지 교체와 초기화를 동시에 요청할 수 없습니다.")
    if profile_image is None and not remove_image:
        raise HTTPException(status_code=422, detail="프로필 이미지 파일 또는 remove_image=true가 필요합니다.")

    image: tuple[bytes, str, str] | None = None
    if profile_image is not None:
        try:
            content = await profile_image.read(MAX_PROFILE_IMAGE_BYTES + 1)
        finally:
            await profile_image.close()
        if not content:
            raise HTTPException(status_code=422, detail="프로필 이미지 파일이 비어 있습니다.")
        if len(content) > MAX_PROFILE_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="프로필 이미지는 최대 5MB까지 업로드할 수 있습니다.")
        try:
            content_type, extension = identify_profile_image(content)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from None
        image = content, content_type, extension

    return await service.update_profile(db, user, image, remove_image=remove_image)


@router.delete("/account", response_model=MessageOut)
async def delete_account(user: CurrentUser, db: DbSession):
    """회원 탈퇴. 계정과 사용자가 소유한 데이터를 영구 삭제한다."""
    await service.delete_account(db, user)
    return MessageOut(message="회원 탈퇴가 완료되었습니다.")
