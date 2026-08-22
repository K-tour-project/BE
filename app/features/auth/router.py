"""인증 엔드포인트 — API_CONTRACT.md §2.

라우터는 얇게 유지한다. 요청을 받아 `service`에 넘기고 결과를 돌려줄 뿐,
판단(가입 가능한가·토큰이 살아있나)은 전부 service가 한다.

## 전체 그림

    [회원가입]  send-code → verify-code → signup ──┐
    [일반로그인] login ────────────────────────────┤
    [소셜로그인] google / kakao ───────────────────┴→ access(1h) + refresh(30d)
                                                        │
                                            access 만료 → refresh → 새 한 쌍
                                                        │
                                              [로그아웃] logout → refresh 폐기
"""
from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.core.config import settings
from app.deps import CurrentUser, DbSession
from app.features.auth import service, social
from app.features.auth.schema import (
    EmailCodeRequest,
    EmailCodeSent,
    EmailVerified,
    EmailVerifyRequest,
    GoogleLoginRequest,
    KakaoLoginRequest,
    LoginRequest,
    LogoutRequest,
    MessageOut,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _ua(request: Request) -> str | None:
    """어느 기기에서 로그인했는지 기록용. 없어도 로그인은 정상 동작한다."""
    return request.headers.get("user-agent")


# ───────────────────────────── 회원가입 ① 이메일 인증 ─────────────────────────────


@router.post("/email/send-code", response_model=EmailCodeSent)
async def send_email_code(body: EmailCodeRequest, db: DbSession):
    """가입할 이메일로 6자리 인증코드를 보낸다.

    - `409` 이미 가입된 이메일 (어느 경로로 가입했는지 안내 문구에 담긴다)
    - `429` 재발송 쿨다운(60초) 중

    ⚠️ SMTP 미설정이면 메일 대신 **서버 로그에 코드를 찍고 응답의 `dev_code`에도 담는다.**
       메일 계정 없이 개발·시연하기 위한 장치이며, `.env`에 SMTP를 채우면 자동으로 사라진다.
    """
    expires_in, dev_code = await service.send_email_code(db, body.email)
    return EmailCodeSent(expires_in=expires_in, dev_code=dev_code)


@router.post("/email/verify-code", response_model=EmailVerified)
async def verify_email_code(body: EmailVerifyRequest, db: DbSession):
    """인증코드를 확인한다. 성공하면 정해진 시간 안에 `/auth/signup`을 호출하면 된다.

    - `400` 코드 불일치·만료, 또는 코드를 요청한 적이 없음
    - `429` 시도 횟수 초과(5회) — 코드를 새로 받아야 한다
    """
    await service.confirm_email_code(db, body.email, body.code)
    return EmailVerified(
        signup_deadline_minutes=settings.EMAIL_VERIFIED_VALID_MINUTES
    )


# ───────────────────────────── 회원가입 ② · 일반 로그인 ────────────────────────────


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request, db: DbSession):
    """회원가입. 성공하면 **바로 로그인 상태**가 된다(토큰을 함께 준다).

    - `403` 이메일 인증을 아직 안 했거나 인증이 만료됨
    - `409` 이미 가입된 이메일
    - `422` 비밀번호 규칙(8자 이상, 영문+숫자) 미달 — FastAPI가 자동으로 낸다
    """
    return await service.signup(
        db, body.email, body.password, body.nickname, _ua(request)
    )


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request, db: DbSession):
    """이메일 + 비밀번호 로그인.

    - `401` 이메일 또는 비밀번호 불일치 (**둘을 구분해 알려주지 않는다**)
    - `409` 그 이메일은 소셜(구글·카카오)로 가입돼 있음 → 해당 버튼으로 로그인
    """
    return await service.login(db, body.email, body.password, _ua(request))


# ─────────────────────────────────── 소셜 로그인 ─────────────────────────────────


@router.post("/google", response_model=TokenPair)
async def google_login(body: GoogleLoginRequest, request: Request, db: DbSession):
    """구글 로그인. 앱이 구글 SDK에서 받은 **id_token**을 넘긴다.

    처음이면 회원이 자동 생성된다(별도 회원가입 없음).

    - `401` 구글 토큰이 위조·만료됐거나 다른 앱용임
    - `409` 그 구글 계정의 이메일이 이미 다른 경로로 가입돼 있음
    - `502` 구글 서버에 연결 실패
    """
    profile = await social.verify_google(body.id_token)
    return await service.social_login(db, profile, _ua(request))


@router.post("/kakao", response_model=TokenPair)
async def kakao_login(body: KakaoLoginRequest, request: Request, db: DbSession):
    """카카오 로그인. 앱이 카카오 SDK에서 받은 **access_token**을 넘긴다.

    ⚠️ 필드명이 구글(`id_token`)과 다르다 — 카카오는 ID 토큰을 주지 않기 때문이다.

    - `401` 카카오 토큰이 위조·만료됐거나 다른 앱용임
    - `409` 그 카카오 계정의 이메일이 이미 다른 경로로 가입돼 있음
    - `502` 카카오 서버에 연결 실패

    참고: 카카오 이메일은 **선택 동의**라 `user.email`이 null일 수 있다(정상).
    """
    profile = await social.verify_kakao(body.access_token)
    return await service.social_login(db, profile, _ua(request))


# ──────────────────────────────── 토큰 갱신 · 로그아웃 ───────────────────────────────


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request, db: DbSession):
    """access가 만료됐을 때 새 한 쌍을 받는다. **앱이 401을 만나면 자동으로 호출**한다.

    쓴 refresh는 즉시 폐기되고 새 refresh가 함께 나온다(회전). 앱은 **응답의 새
    refresh로 반드시 교체**해야 한다 — 옛것을 계속 쓰면 아래 재사용 감지에 걸린다.

    - `401` refresh가 없음·만료·이미 사용됨.
      **이미 사용된 토큰이 들어오면 탈취로 간주해 그 계정의 모든 세션을 끊는다.**
    """
    return await service.rotate_tokens(db, body.refresh_token, _ua(request))


@router.post("/logout", response_model=MessageOut)
async def logout(body: LogoutRequest, db: DbSession):
    """로그아웃 — 이 기기의 refresh를 서버에서 폐기한다.

    이미 없는 토큰이어도 `200`이다(멱등). 앱은 이 호출 후 저장해 둔 두 토큰을 모두 지운다.

    ⚠️ 남아 있는 access는 최대 1시간 더 유효하다. 즉시 전부 끊으려면 `/auth/logout-all`.
    """
    await service.revoke_token(db, body.refresh_token)
    return MessageOut(message="로그아웃되었습니다.")


@router.post("/logout-all", response_model=MessageOut)
async def logout_all(user: CurrentUser, db: DbSession):
    """🔒 모든 기기에서 로그아웃. 폰을 잃어버렸을 때 쓰는 기능이다."""
    count = await service.revoke_all_tokens(db, user.user_id)
    return MessageOut(message=f"{count}개 기기에서 로그아웃되었습니다.")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    """🔒 내 정보. 앱 시작 시 토큰이 아직 유효한지 확인하는 용도로도 쓴다."""
    return UserOut.model_validate(user)
