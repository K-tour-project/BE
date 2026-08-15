"""자체 JWT 발급/검증.

소셜 로그인(구글·카카오) 성공 후, 우리 서버가 직접 발급하는 "출입증"(access token).
이후 앱은 이 JWT를 `Authorization: Bearer <token>` 헤더로 보내 인증한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(user_id: int) -> str:
    """user_id를 담은 JWT를 발급한다. sub(주체)=user_id, exp(만료시각) 포함."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """JWT를 검증·해독해 user_id를 돌려준다. 위조·만료·형식오류면 None."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    sub = payload.get("sub")
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
