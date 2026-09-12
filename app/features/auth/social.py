"""구글·카카오에 "이 토큰 주인이 누구야?"를 물어보는 어댑터.

## 우리가 쓰는 방식 — 앱 SDK 토큰 전달
```
[앱] 구글/카카오 SDK로 로그인 → 토큰 받음
  ↓  POST /auth/kakao {"access_token": "..."}
[우리 서버] → [카카오/구글] "이 토큰 주인 누구야?"
  ↓
[우리 서버] users 조회 → 없으면 자동 가입 → 우리 JWT 발급
```
서버 OAuth 리다이렉트 방식이 아니므로 **client secret도 redirect_uri 등록도 필요 없다.**

## ⚠️ 가장 중요한 검증: "이 토큰이 *우리 앱* 것이 맞는가"
토큰이 진짜인지만 보면 부족하다. 아무 앱에서나 발급된 구글/카카오 토큰을 가져와도
"진짜 토큰"이기 때문이다. 그래서 토큰에 적힌 **앱 식별자**가 우리 것인지 대조한다.
  · 구글 → `aud` == `GOOGLE_CLIENT_ID`
  · 카카오 → `app_id` == `KAKAO_APP_ID`
설정이 비어 있으면 이 검증을 건너뛰고 **경고를 로그에 남긴다**(개발 편의). 배포 전엔 반드시 채운다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.core.config import settings
from app.models.common import AuthProvider

logger = logging.getLogger(__name__)

# 구글이 ID 토큰(JWT)의 서명·만료를 대신 검증해 주는 공개 엔드포인트.
# 우리가 직접 JWKS를 받아 검증할 수도 있지만, 키 캐싱·회전을 떠안게 되어 이쪽을 택했다.
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

KAKAO_TOKEN_INFO_URL = "https://kapi.kakao.com/v1/user/access_token_info"
KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me"


@dataclass(frozen=True)
class SocialProfile:
    """제공자가 알려준 사용자 정보. 여기서부터는 구글·카카오를 구분하지 않는다."""

    provider: AuthProvider
    provider_user_id: str
    email: str | None
    email_verified: bool
    nickname: str | None
    profile_image_url: str | None = None


def _profile_image_url(value: object) -> str | None:
    if not value:
        return None
    try:
        return str(TypeAdapter(HttpUrl).validate_python(value))
    except ValidationError:
        return None


def _invalid_token(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _provider_down(name: str) -> HTTPException:
    # 제공자 장애를 401로 돌려주면 앱이 "로그인 실패"로 오해해 사용자를 로그아웃시킨다.
    return HTTPException(status_code=502, detail=f"{name} 서버에 연결하지 못했습니다.")


# ──────────────────────────────────── 구글 ───────────────────────────────────


async def verify_google(id_token: str) -> SocialProfile:
    """구글 ID 토큰(JWT)을 검증하고 프로필을 돌려준다.

    ID 토큰은 사용자 정보가 **담긴** 서명된 JWT라, 검증 한 번으로 정보까지 같이 얻는다.
    """
    try:
        async with httpx.AsyncClient(timeout=settings.SOCIAL_API_TIMEOUT) as client:
            res = await client.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
    except httpx.HTTPError:
        raise _provider_down("구글") from None

    if res.status_code != 200:
        # 위조·만료·형식 오류를 구글이 400으로 알려준다.
        raise _invalid_token("구글 토큰이 유효하지 않습니다.")

    data = res.json()

    if data.get("iss") not in GOOGLE_VALID_ISSUERS:
        raise _invalid_token("구글 토큰의 발급자가 올바르지 않습니다.")

    allowed = settings.google_client_ids
    if allowed:
        if data.get("aud") not in allowed:
            raise _invalid_token("이 앱을 위해 발급된 구글 토큰이 아닙니다.")
    else:
        logger.warning(
            "GOOGLE_CLIENT_ID가 비어 있어 aud 검증을 건너뜁니다. "
            "배포 전 .env에 반드시 설정하세요."
        )

    sub = data.get("sub")
    if not sub:
        raise _invalid_token("구글 토큰에 사용자 식별자가 없습니다.")

    # tokeninfo는 값이 전부 문자열로 온다("true"/"false"). bool로 비교하면 항상 False가 된다.
    email_verified = str(data.get("email_verified", "")).lower() == "true"

    return SocialProfile(
        provider=AuthProvider.google,
        provider_user_id=str(sub),
        email=data.get("email"),
        email_verified=email_verified,
        nickname=data.get("name") or data.get("given_name"),
        profile_image_url=_profile_image_url(data.get("picture")),
    )


# ─────────────────────────────────── 카카오 ──────────────────────────────────


async def verify_kakao(access_token: str) -> SocialProfile:
    """카카오 액세스 토큰을 검증하고 프로필을 돌려준다.

    카카오 access token은 사용자 정보가 들어 있지 않은 불투명 토큰이라,
    토큰 정보 조회로 앱과 사용자 식별자를 검증한 뒤 사용자 정보를 따로 조회한다.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient(timeout=settings.SOCIAL_API_TIMEOUT) as client:
            token_res = await client.get(KAKAO_TOKEN_INFO_URL, headers=headers)
            if token_res.status_code != 200:
                raise _invalid_token("카카오 토큰이 유효하지 않습니다.")

            try:
                token_data = token_res.json()
            except ValueError:
                raise _provider_down("카카오") from None

            configured_app_id = settings.KAKAO_APP_ID.strip()
            if configured_app_id:
                if str(token_data.get("app_id", "")) != configured_app_id:
                    raise _invalid_token("이 앱을 위해 발급된 카카오 토큰이 아닙니다.")
            else:
                logger.warning(
                    "KAKAO_APP_ID가 비어 있어 app_id 검증을 건너뜁니다. "
                    "배포 전 .env에 반드시 설정하세요."
                )

            user_res = await client.get(
                KAKAO_USER_ME_URL,
                headers=headers,
                params={
                    "property_keys": (
                        '["kakao_account.email","kakao_account.profile"]'
                    )
                },
            )
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise _provider_down("카카오") from None

    if user_res.status_code != 200:
        raise _invalid_token("카카오 사용자 정보를 조회할 수 없습니다.")

    try:
        data = user_res.json()
    except ValueError:
        raise _provider_down("카카오") from None

    kakao_id = data.get("id")
    if kakao_id is None:
        raise _invalid_token("카카오 응답에 사용자 식별자가 없습니다.")

    # 토큰 정보와 사용자 정보가 같은 회원을 가리키는지 한 번 더 확인한다.
    token_user_id = token_data.get("id")
    if token_user_id is not None and str(token_user_id) != str(kakao_id):
        raise _invalid_token("카카오 토큰의 사용자 정보가 일치하지 않습니다.")

    account = data.get("kakao_account") or {}
    profile = account.get("profile") or {}
    email = account.get("email")

    return SocialProfile(
        provider=AuthProvider.kakao,
        provider_user_id=str(kakao_id),
        email=email if isinstance(email, str) else None,
        email_verified=bool(email) and account.get("is_email_verified") is True,
        nickname=profile.get("nickname"),
        profile_image_url=_profile_image_url(profile.get("profile_image_url")),
    )
