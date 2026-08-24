"""FastAPI 앱 진입점. uvicorn이 여기의 `app` 객체를 띄운다."""
from fastapi import FastAPI

from app.core.config import settings
from app.region import router as region_router
from app.routers import contents, health, places

app = FastAPI(title=settings.APP_NAME)

# 라우터(창구) 등록 — 앞으로 만드는 라우터는 여기에 include_router 로 연결한다.
app.include_router(health.router)
app.include_router(region_router.router)
app.include_router(contents.router)  # 5단계: 작품 검색·상세·촬영지
app.include_router(places.router)    # 5단계: 반경 조회 (4단계에서 상세가 추가된다)


@app.get("/")
def root():
    """루트. 동작 확인용 + 자동 문서 위치 안내."""
    return {"message": f"{settings.APP_NAME} API", "docs": "/docs"}
