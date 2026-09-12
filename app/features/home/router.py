"""홈 화면 API."""
from fastapi import APIRouter, HTTPException

from app.deps import DbSession
from app.features.home import service
from app.features.home.schema import HomeOut
from app.integrations.tour_api import TourApiError, TourApiKeyMissing

router = APIRouter(tags=["home"])


@router.get("/home", response_model=HomeOut, summary="홈 화면 인기 작품·관광지")
async def get_home(db: DbSession):
    """별점 상위 작품과 찜 순위·초기 대체 관광지를 각각 최대 10개 반환한다."""
    try:
        return await service.home(db)
    except TourApiKeyMissing as exc:
        raise HTTPException(503, "관광 공공데이터 API 키가 설정되지 않았습니다.") from exc
    except TourApiError as exc:
        raise HTTPException(502, "인기 관광지 조회에 실패했습니다.") from exc
