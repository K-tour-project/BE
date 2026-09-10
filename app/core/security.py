"""인증 원시 도구 — JWT 발급/검증 · refresh 토큰 생성/해시 · 비밀번호 해싱.

여기엔 "암호 기술"만 둔다. 누가 로그인했는지·가입시킬지 같은 **판단은 하지 않는다**
(그건 `app/features/auth/service.py`). 그래서 이 파일은 DB를 모른다.

## 토큰이 두 개인 이유
JWT는 서버가 저장하지 않고 서명만 검증한다 — 빠르지만 **취소할 수 없다**.
로그아웃을 실제로 동작시키려고 역할을 쪼갰다.

| | access token | refresh token |
|---|---|---|
| 정체 | JWT (서명된 문자열) | 그냥 난수 48바이트 |
| 용도 | 모든 API 호출의 출입증 | 오직 access 재발급 |
| 수명 | 1시간 (`ACCESS_TOKEN_EXPIRE_MINUTES`) | 30일 (`REFRESH_TOKEN_EXPIRE_DAYS`) |
| 저장 | 안 함 | `refresh_tokens` 테이블에 **해시로** |
| 취소 | 불가 (만료 대기) | 가능 → 이게 로그아웃 |

refresh를 JWT로 만들지 않은 건 의도적이다. 어차피 DB를 조회해야 취소가 되므로
JWT의 장점(무조회 검증)이 쓸모없고, 난수가 더 짧고 단순하다.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ─────────────────────────────── access token (JWT) ───────────────────────────────

_TOKEN_TYPE_ACCESS = "access"


def create_access_token(user_id: int) -> str:
    """user_id를 담은 access JWT를 발급한다.

    `typ` 클레임을 넣는 이유: 나중에 다른 용도의 JWT(비밀번호 재설정 링크 등)를 추가했을 때
    그걸 API 출입증으로 재사용하는 **토큰 혼동 공격**을 막는다.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": _TOKEN_TYPE_ACCESS,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """access JWT를 검증·해독해 user_id를 돌려준다. 위조·만료·형식오류·타입불일치면 None."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError:
        return None
    if payload.get("typ") != _TOKEN_TYPE_ACCESS:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def access_token_expires_in() -> int:
    """앱이 "언제 갱신할지" 계산할 수 있게 남은 초를 알려준다(응답의 `expires_in`)."""
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


# ─────────────────────────────── refresh token (난수) ──────────────────────────────


def create_refresh_token() -> tuple[str, str, datetime]:
    """(원문, 해시, 만료시각)을 만든다.

    **원문은 이 순간 응답에 실려 나가는 게 전부다.** 서버는 해시만 갖고 있어서,
    DB가 통째로 유출돼도 그것만으론 로그인할 수 없다.
    """
    raw = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    return raw, hash_refresh_token(raw), expires_at


def hash_refresh_token(raw: str) -> str:
    """refresh 토큰 → SHA-256 hex(64자).

    비밀번호와 달리 bcrypt를 쓰지 않는다. 이건 사람이 고른 단어가 아니라 난수 48바이트라
    사전공격 대상이 아니고, 조회 키로 써야 해서(=`WHERE token_hash = ?`) 매번 값이 같아야 한다.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_device_id(device_id: str) -> str:
    """기기 식별자는 원문을 저장하지 않고 서버 SECRET_KEY로 HMAC 처리한다."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        device_id.strip().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ─────────────────────────────── 이메일 인증코드 ────────────────────────────────


def create_email_code() -> tuple[str, str]:
    """(6자리 코드, 해시)를 만든다. `secrets`라서 예측 불가하다(`random`은 예측 가능해 금지)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    return code, hash_email_code(code)


def hash_email_code(code: str) -> str:
    """인증코드 → SHA-256 hex. 서버 로그·DB에 6자리 평문이 남지 않게."""
    return hashlib.sha256(code.encode()).hexdigest()


def verify_email_code(code: str, code_hash: str) -> bool:
    """인증코드 대조. `==` 대신 `compare_digest` — 응답 시간차로 코드를 알아내는 걸 막는다."""
    return hmac.compare_digest(hash_email_code(code), code_hash)


# ─────────────────────────────── 비밀번호 (bcrypt) ─────────────────────────────


def hash_password(plain: str) -> str:
    """비밀번호 → bcrypt 해시(60자). 평문은 절대 저장·로깅하지 않는다.

    bcrypt는 **일부러 느린** 해시다(설계상 ~0.1초). 유출돼도 대입 공격이 실용적이지 않게 만든다.
    salt가 해시 문자열 안에 포함되므로 따로 칼럼을 두지 않는다.

    ⚠️ bcrypt는 72바이트까지만 본다. 초과분이 조용히 잘려나가면 서로 다른 긴 비밀번호가
       같은 걸로 취급되므로, 길이 제한은 스키마(`schema.py`)에서 미리 막는다.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str | None) -> bool:
    """비밀번호 대조. 해시가 없으면(=소셜 가입자) 항상 False."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # 해시 형식이 깨진 경우 — 예외를 밖으로 흘리면 500이 되므로 '불일치'로 처리한다.
        return False
