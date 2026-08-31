"""인증 요청·응답 스키마 — API_CONTRACT.md §2.

여기서 정한 모양이 곧 프론트와의 약속이다. 바꾸면 계약서도 함께 고친다.
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# 영문·숫자를 각각 최소 1개. 특수문자까지 강제하진 않는다 —
# 요구사항을 늘릴수록 사용자가 'Password1!'류로 수렴해 오히려 예측하기 쉬워진다.
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


class _PasswordField(BaseModel):
    """비밀번호 규칙을 공유하는 믹스인 성격의 베이스."""

    # ⚠️ max_length=72는 취향이 아니라 bcrypt의 한계다. 72바이트 초과분은 조용히 잘려서
    #    서로 다른 긴 비밀번호가 같은 것으로 취급된다. 그래서 입력 단계에서 막는다.
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def _check_strength(cls, v: str) -> str:
        if not _HAS_LETTER.search(v) or not _HAS_DIGIT.search(v):
            raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다.")
        if len(v.encode("utf-8")) > 72:
            # 한글 비밀번호는 글자당 3바이트라 24자만 넘어도 걸린다.
            raise ValueError("비밀번호가 너무 깁니다(최대 72바이트).")
        return v


# ─────────────────────────── 이메일 인증 (가입 1·2단계) ───────────────────────────


class EmailCodeRequest(BaseModel):
    """`POST /auth/email/send-code` — 가입할 이메일로 6자리 코드를 보낸다."""

    email: EmailStr


class EmailCodeSent(BaseModel):
    expires_in: int = Field(..., description="코드 유효시간(초)")
    # ⚠️ 개발 편의용. SMTP 미설정일 때만 채워지고, 설정되면 항상 null이다.
    dev_code: str | None = Field(
        None, description="SMTP 미설정 시에만 코드를 그대로 돌려준다(개발용)"
    )


class EmailVerifyRequest(BaseModel):
    """`POST /auth/email/verify-code`"""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailVerified(BaseModel):
    verified: bool = True
    signup_deadline_minutes: int = Field(
        ..., description="이 시간 안에 회원가입을 마쳐야 한다"
    )


# ─────────────────────────────── 회원가입 · 로그인 ────────────────────────────────


class SignupRequest(_PasswordField):
    """`POST /auth/signup` — 이메일 인증을 마친 뒤에만 성공한다."""

    email: EmailStr
    nickname: str = Field(..., min_length=2, max_length=20)

    @field_validator("nickname")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("닉네임은 2자 이상이어야 합니다.")
        return v


class LoginRequest(BaseModel):
    """`POST /auth/login` — 이메일 + 비밀번호.

    로그인은 회원가입과 달리 비밀번호 **형식을 검사하지 않는다.**
    규칙이 바뀌기 전에 가입한 사람이 로그인조차 못 하게 되는 걸 막기 위함이다.
    """

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


# ─────────────────────────────────── 소셜 로그인 ─────────────────────────────────


class GoogleLoginRequest(BaseModel):
    """`POST /auth/google` — 앱이 구글 SDK에서 받은 **ID 토큰**(JWT)."""

    id_token: str = Field(..., min_length=1)


class KakaoLoginRequest(BaseModel):
    """`POST /auth/kakao` — 앱이 카카오 SDK에서 받은 **액세스 토큰**.

    ⚠️ 구글과 필드 이름이 다른 건 실수가 아니다. 구글은 사용자 정보가 담긴 서명된 JWT를,
       카카오는 정보가 없는 불투명 토큰을 준다. 그래서 검증 방식도 다르다(social.py).

    📌 카카오 엔드포인트 자체는 **윤영 담당으로 아직 미구현**이지만, 이 요청 형태는
       계약서 §2.3에 이미 프론트와 약속돼 있으므로 여기 남겨 둔다. 구현할 때 그대로 쓰면
       스펙이 어긋나지 않는다. (`router.py`·`social.py`의 안내 주석 참고)
    """

    access_token: str = Field(..., min_length=1)


# ─────────────────────────────── 토큰 · 사용자 응답 ───────────────────────────────


class UserOut(BaseModel):
    user_id: int
    nickname: str
    auth_provider: str  # local | google | kakao
    email: str | None = None
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    """로그인·가입·재발급의 공통 응답.

    앱은 두 토큰을 **안전한 저장소**에 넣는다(안드로이드 EncryptedSharedPreferences /
    iOS Keychain / RN Keychain). 일반 SharedPreferences·AsyncStorage는 피한다.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="access_token 남은 수명(초)")
    user: UserOut


class RefreshRequest(BaseModel):
    """`POST /auth/refresh` — access가 만료됐을 때 앱이 자동으로 호출한다."""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """`POST /auth/logout` — 이 기기의 refresh 토큰만 폐기한다."""

    refresh_token: str = Field(..., min_length=1)


class MessageOut(BaseModel):
    message: str
