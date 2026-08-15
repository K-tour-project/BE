"""공통 의존성. 라우터에서 `Depends(...)`로 주입받는 것들.

`get_current_user`(로그인 사용자 확인)는 3단계에서 여기에 추가한다.
"""
from app.core.db import get_db

__all__ = ["get_db"]
