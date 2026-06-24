"""헬스체크 라우터 — 서버가 살아있는지 확인하는 가장 단순한 엔드포인트."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """서버 상태 확인. 정상이면 {"status": "ok"} 를 돌려준다."""
    return {"status": "ok"}
