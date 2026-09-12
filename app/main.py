"""FastAPI 앱 진입점. uvicorn이 여기의 `app` 객체를 띄운다."""
from fastapi import FastAPI
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.core.config import settings
from app.features.auth.router import router as auth_router
from app.features.products.router import router as contents_router
from app.features.health.router import router as health_router
from app.features.home.router import router as home_router
from app.features.mypage.router import router as mypage_router
from app.features.places.router import router as places_router
from app.features.regions.router import router as regions_router
from app.features.places.tourism import router as tourism_router

app = FastAPI(title=settings.APP_NAME)

if settings.FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)

# 라우터(창구) 등록 — 기능 폴더를 app/features/ 에 추가한 뒤 여기 한 줄만 더하면 연결된다.
app.include_router(health_router)
app.include_router(home_router)
app.include_router(auth_router)      # 3단계: 회원가입·로그인·로그아웃·소셜
app.include_router(mypage_router)
app.include_router(contents_router)  # 5단계: 작품 검색·상세·촬영지
app.include_router(regions_router)   # 5단계: 지역 검색·목록·지역 내 촬영지
app.include_router(places_router)    # 5단계: 반경 조회 (4단계에서 상세가 추가된다)
app.include_router(tourism_router)


@app.get("/")
def root():
    """루트. 동작 확인용 + 자동 문서 위치 안내."""
    return {"message": f"{settings.APP_NAME} API", "docs": "/docs"}
