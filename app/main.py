"""FastAPI 앱 진입점. uvicorn이 여기의 `app` 객체를 띄운다."""
from fastapi import FastAPI

from app.core.config import settings
from app.routers import health

app = FastAPI(title=settings.APP_NAME)

# 라우터(창구) 등록 — 앞으로 만드는 라우터는 여기에 include_router 로 연결한다.
app.include_router(health.router)


@app.get("/")
def root():
    """루트. 동작 확인용 + 자동 문서 위치 안내."""
    return {"message": f"{settings.APP_NAME} API", "docs": "/docs"}
