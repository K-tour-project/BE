"""구글·카카오에 "이 토큰 주인이 누구야?"를 물어보는 어댑터.

## 우리가 쓰는 방식 — 앱 SDK 토큰 전달
```
[앱] 카카오/구글 SDK로 로그인 → 토큰 받음
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
    )


# ─────────────────────────────────── 카카오 ──────────────────────────────────


# ⚠️ 아래 verify_kakao()는 **미구현**이다. 팀 분담상 카카오는 윤영이 맡는다
#    (지도 API 때문에 카카오 개발자센터 앱을 이미 만들어 둔 쪽이 로그인까지 담당).
#    구현하는 사람이 바로 시작할 수 있게 무엇을 어떻게 해야 하는지 아래에 다 적어 둔다.
async def verify_kakao(access_token: str) -> SocialProfile:
    """카카오 액세스 토큰을 검증하고 프로필을 돌려준다.  ← **구현 필요**

    ## 구글과 달리 두 번 호출해야 한다
    카카오 액세스 토큰은 아무 정보도 담고 있지 않은 **불투명한 문자열**이다.
    (구글 `id_token`은 정보가 담긴 서명된 JWT라 한 번이면 된다.)
    그래서 두 가지를 각각 물어봐야 한다. 상수는 위에 이미 선언돼 있다.

    ① `KAKAO_TOKEN_INFO_URL` — 이 토큰이 **우리 앱 것인지** 확인
       헤더 `Authorization: Bearer {access_token}`
       응답 `{"id": 3812947, "expires_in": 21599, "app_id": 1234567}`
       → `app_id`가 `settings.KAKAO_APP_ID`와 같은지 대조한다.

       ⚠️ **이게 이 함수에서 제일 중요한 검증이다.** 토큰이 '진짜'인지만 보면 부족하다 —
          아무 앱에서 발급된 카카오 토큰도 진짜이기 때문이다. 이 확인이 없으면
          **남의 앱 사용자가 우리 서버에 로그인할 수 있다.**
          `KAKAO_APP_ID`가 비어 있으면 이 호출을 건너뛰되 `logger.warning`을 남긴다
          (개발 편의 — 위 `verify_google()`이 같은 패턴이니 그대로 따르면 된다).

    ② `KAKAO_USER_ME_URL` — 사용자 정보 조회
       헤더 동일. 필요한 항목만 요청한다(안 쓰는 개인정보는 애초에 안 받는다):
       `params={"property_keys": '["kakao_account.email","kakao_account.profile"]'}`
       응답 `{"id":3812947, "kakao_account":{"email":"...", "is_email_verified":true,
                                             "profile":{"nickname":"은서"}}}`

    ## 돌려줄 것
    ```python
    return SocialProfile(
        provider=AuthProvider.kakao,
        provider_user_id=str(kakao_id),   # ★ 문자열로.
        email=email,                      # 없을 수 있다 (아래 주의사항)
        email_verified=email_verified,
        nickname=profile.get("nickname"),
    )
    ```
    이것만 돌려주면 나머지는 **이미 다 되어 있다** — `service.social_login()`이
    회원 조회·자동가입·토큰 발급을 알아서 한다(구글과 공용 코드).
    그다음 `router.py`의 표시된 자리에 엔드포인트 4줄만 추가하면 끝이다.

    ★ 사람을 알아보는 열쇠는 **이메일이 아니라 `(제공자, provider_user_id)`** 다.
      이메일은 사용자가 카카오에서 바꿀 수 있지만 id는 바뀌지 않기 때문이다.

    ## 주의할 점
    · **카카오 이메일은 선택 동의**라 아예 안 올 수 있다 → `email=None`이 **정상 경로**다.
      게다가 사업자 심사를 통과해야 이메일 항목을 켤 수 있어 개발 중엔 대개 없다.
      계약서 §2.3과 프론트 체크리스트에도 "null 가능"으로 명시돼 있다.
    · 토큰이 위조·만료면 `_invalid_token(...)` → **401**
    · 카카오 서버가 죽었으면 `_provider_down("카카오")` → **502**
      (401로 주면 앱이 '로그인 실패'로 오해해 사용자를 로그아웃시킨다)
    · `httpx.AsyncClient(timeout=settings.SOCIAL_API_TIMEOUT)`를 쓴다.

    구현 예시는 바로 위 `verify_google()`을 보면 된다 — 구조가 거의 같다.
    """
    raise NotImplementedError(
        "카카오 로그인은 아직 구현되지 않았습니다. "
        "app/features/auth/social.py의 verify_kakao() 주석을 참고해 구현해 주세요."
    )
