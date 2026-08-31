"""공통 의존성. 라우터에서 `Depends(...)`로 주입받는 것들.

## 로그인이 필요한 API 만드는 법

    from app.deps import CurrentUser

    @router.post("/courses")
    async def create_course(user: CurrentUser, ...):
        ...  # 여기 도달했으면 이미 인증된 사용자다

`Authorization: Bearer <access_token>` 헤더가 없거나 위조·만료면 **401**로 알아서 막힌다.
로그인해도 되고 안 해도 되는 API(예: 즐겨찾기 표시가 붙는 목록)는 `OptionalUser`를 쓴다.
"""
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.user import User

# auto_error=False: 헤더가 없을 때 FastAPI 기본 문구(영어) 대신 우리 메시지를 쓰기 위함.
# 이 스킴을 선언해 두면 /docs 우측 상단에 'Authorize' 버튼이 생겨 토큰을 붙여 테스트할 수 있다.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="로그인 응답의 access_token을 넣는다. 'Bearer '는 자동으로 붙는다.",
)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """로그인한 사용자를 돌려준다. 아니면 401.

    ⚠️ 토큰이 만료된 것과 위조된 것을 **구분해서 알려주지 않는다.** 앱 입장에선 대응이
       똑같고(= refresh 시도), 구분해 주면 공격자에게 힌트가 되기 때문이다.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
            headers=_UNAUTHORIZED_HEADERS,
        )

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="토큰이 유효하지 않거나 만료되었습니다.",
            headers=_UNAUTHORIZED_HEADERS,
        )

    user = await db.get(User, user_id)
    if user is None:
        # 토큰은 멀쩡한데 계정이 사라진 경우(탈퇴). 토큰 수명이 1시간이라 잠깐 생길 수 있다.
        raise HTTPException(
            status_code=401,
            detail="존재하지 않는 계정입니다.",
            headers=_UNAUTHORIZED_HEADERS,
        )
    return user


async def get_current_user_optional(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """로그인했으면 사용자, 아니면 None. **잘못된 토큰도 조용히 None**으로 본다.

    "비로그인도 되는" API에서 쓴다. 여기서 401을 던지면 손님 사용자가 화면을 못 보게 된다.
    """
    if credentials is None or not credentials.credentials:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return await db.get(User, user_id)


# 라우터에서 짧게 쓰는 별칭
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_user_optional",
    "CurrentUser",
    "OptionalUser",
    "DbSession",
    "bearer_scheme",
]
