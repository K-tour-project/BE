"""인증 로직 — 가입시킬지 · 로그인시킬지 · 토큰을 살릴지 죽일지 판단하는 층.

암호 기술은 `app/core/security.py`, 제공자 통신은 `social.py`·`mailer.py`가 맡는다.
여기는 그것들을 조합해 **규칙을 집행**한다.

## 회원가입은 3단계다 (이메일 인증 때문)

    ① POST /auth/email/send-code   {email}         → 6자리 코드 메일 발송
    ② POST /auth/email/verify-code {email, code}   → 확인, 30분짜리 통과권 부여
    ③ POST /auth/signup  {email, password, nickname} → 계정 생성

②까지는 `users` 행을 만들지 않는다. 인증을 중간에 포기한 "유령 계정"이 쌓이지 않게 하고,
이메일 중복 검사도 실제 가입 시점에 한 번만 하면 되기 때문이다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    access_token_expires_in,
    create_access_token,
    create_email_code,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_email_code,
    verify_password,
)
from app.features.auth import mailer
from app.features.auth.schema import TokenPair, UserOut
from app.features.auth.social import SocialProfile
from app.models.auth import EmailVerification, RefreshToken
from app.models.common import AuthProvider
from app.models.user import User

# 제공자별 사람이 읽는 이름 — "구글로 가입된 계정입니다" 같은 안내 문구에 쓴다.
_PROVIDER_LABEL = {
    AuthProvider.local: "이메일",
    AuthProvider.google: "구글",
    AuthProvider.kakao: "카카오",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    """이메일은 소문자로 통일해 저장·조회한다.

    'Kim@Gmail.com'과 'kim@gmail.com'이 다른 계정이 되면 사용자는 로그인에 실패하고도
    이유를 알 수 없다. 도메인은 원래 대소문자를 구분하지 않고, 실무상 로컬파트도 마찬가지다.
    """
    return email.strip().lower()


# ═══════════════════════════════ 토큰 발급·회전·폐기 ═══════════════════════════════


async def issue_tokens(
    db: AsyncSession, user: User, user_agent: str | None = None
) -> TokenPair:
    """로그인 성공 시 access + refresh 한 쌍을 발급한다.

    refresh는 **원문이 아니라 해시**로 저장된다. 원문은 이 응답에 한 번 실려 나가고 끝이다.
    """
    raw_refresh, token_hash, expires_at = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    # 만료된 토큰 청소. 로그인할 때마다 자기 것만 지우므로 별도 배치가 필요 없다.
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.user_id,
            RefreshToken.expires_at < _now(),
        )
    )
    await db.commit()

    return TokenPair(
        access_token=create_access_token(user.user_id),
        refresh_token=raw_refresh,
        expires_in=access_token_expires_in(),
        user=UserOut.model_validate(user),
    )


async def rotate_tokens(
    db: AsyncSession, raw_refresh: str, user_agent: str | None = None
) -> TokenPair:
    """`POST /auth/refresh` — 낡은 refresh를 새 한 쌍으로 바꾼다(회전).

    쓴 refresh는 즉시 폐기하고 새것을 준다. 한 번 쓴 토큰이 계속 유효하면,
    유출된 토큰으로 30일 내내 access를 뽑아낼 수 있기 때문이다.

    ⚠️ **재사용 감지**: 이미 폐기된 refresh가 다시 들어오면 정상 흐름일 수 없다
       (정상 앱은 새 토큰을 받아 갔다). 탈취를 의심해 그 계정의 **모든 세션을 끊는다.**
    """
    token_hash = hash_refresh_token(raw_refresh)
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if row is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 refresh 토큰입니다.")

    if row.revoked_at is not None:
        await revoke_all_tokens(db, row.user_id)
        raise HTTPException(
            status_code=401,
            detail="이미 사용된 refresh 토큰입니다. 보안을 위해 모든 기기에서 로그아웃했습니다.",
        )

    if row.expires_at <= _now():
        raise HTTPException(status_code=401, detail="refresh 토큰이 만료되었습니다.")

    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="탈퇴한 계정입니다.")

    row.revoked_at = _now()
    return await issue_tokens(db, user, user_agent)


async def revoke_token(db: AsyncSession, raw_refresh: str) -> None:
    """`POST /auth/logout` — 이 기기의 refresh만 폐기한다.

    없는 토큰이어도 조용히 성공시킨다. 로그아웃이 실패로 보이면 앱은 재시도를 반복하는데,
    사용자 입장에선 "이미 로그아웃된 상태"라 결과가 같기 때문이다.
    """
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw_refresh),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    await db.commit()


async def revoke_all_tokens(db: AsyncSession, user_id: int) -> int:
    """그 사용자의 살아있는 refresh를 전부 폐기한다(모든 기기 로그아웃)."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()
    return result.rowcount or 0


# ═══════════════════════════════ 이메일 인증 (①·②) ════════════════════════════════


async def send_email_code(db: AsyncSession, email: str) -> tuple[int, str | None]:
    """① 인증코드 발송. (유효시간 초, 개발용 코드) 를 돌려준다.

    개발용 코드는 SMTP 미설정일 때만 채워진다.
    """
    email = _normalize_email(email)

    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail=_already_registered(existing))

    # 재발송 쿨다운 — 없으면 메일 폭탄(남의 주소로 무한 발송)에 쓰인다.
    cooldown_since = _now() - timedelta(
        seconds=settings.EMAIL_CODE_RESEND_COOLDOWN_SECONDS
    )
    too_soon = await db.scalar(
        select(EmailVerification.verification_id).where(
            EmailVerification.email == email,
            EmailVerification.created_at > cooldown_since,
        )
    )
    if too_soon is not None:
        raise HTTPException(
            status_code=429,
            detail=f"{settings.EMAIL_CODE_RESEND_COOLDOWN_SECONDS}초 후에 다시 시도해 주세요.",
        )

    # 이전에 보낸 미사용 코드는 무효화한다. 옛 코드가 계속 살아 있으면 시도 제한이 무의미해진다.
    await db.execute(
        update(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.consumed_at.is_(None),
        )
        .values(consumed_at=_now())
    )

    code, code_hash = create_email_code()
    db.add(
        EmailVerification(
            email=email,
            code_hash=code_hash,
            expires_at=_now() + timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    sent = await mailer.send_verification_code(email, code)
    return settings.EMAIL_CODE_EXPIRE_MINUTES * 60, (None if sent else code)


async def confirm_email_code(db: AsyncSession, email: str, code: str) -> None:
    """② 코드 확인. 성공하면 30분짜리 '가입 통과권'이 생긴다(행에 `verified_at` 기록)."""
    email = _normalize_email(email)

    row = await db.scalar(
        select(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.consumed_at.is_(None),
        )
        .order_by(EmailVerification.verification_id.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(status_code=400, detail="인증코드를 먼저 요청해 주세요.")
    if row.expires_at <= _now():
        raise HTTPException(
            status_code=400, detail="인증코드가 만료되었습니다. 다시 요청해 주세요."
        )
    if row.attempt_count >= settings.EMAIL_CODE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="시도 횟수를 초과했습니다. 인증코드를 다시 요청해 주세요.",
        )

    # ⚠️ 대조 **전에** 시도 횟수를 올리고 커밋한다. 나중에 올리면, 틀렸을 때 응답을
    #    중간에 끊는 식으로 카운트를 회피할 수 있다.
    row.attempt_count += 1
    await db.commit()

    if not verify_email_code(code, row.code_hash):
        raise HTTPException(status_code=400, detail="인증코드가 일치하지 않습니다.")

    row.verified_at = _now()
    await db.commit()


# ═══════════════════════════════ 회원가입 · 로그인 (③) ═════════════════════════════


def _already_registered(user: User) -> str:
    """이미 가입된 이메일 안내 문구.

    ⚠️ 의도적 트레이드오프: 이 메시지는 "그 이메일이 가입돼 있다"는 사실을 노출한다.
       엄격한 보안 관점에선 계정 존재 여부를 숨기는 게 맞지만, 숨기면 사용자가
       "구글로 가입해 놓고 일반 로그인에서 계속 실패"하는 상황을 빠져나올 수 없다.
       회원가입은 어차피 중복을 알려줘야 하므로 실익도 없다.
    """
    label = _PROVIDER_LABEL.get(user.auth_provider, "다른 방법")
    if user.auth_provider == AuthProvider.local:
        return "이미 가입된 이메일입니다."
    return f"이미 {label} 계정으로 가입된 이메일입니다. {label} 로그인을 이용해 주세요."


async def signup(
    db: AsyncSession,
    email: str,
    password: str,
    nickname: str,
) -> UserOut:
    """③ 회원가입. ②의 통과권이 살아 있어야만 성공한다."""
    email = _normalize_email(email)

    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail=_already_registered(existing))

    verified_since = _now() - timedelta(minutes=settings.EMAIL_VERIFIED_VALID_MINUTES)
    verification = await db.scalar(
        select(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.consumed_at.is_(None),
            EmailVerification.verified_at.is_not(None),
            EmailVerification.verified_at > verified_since,
        )
        .order_by(EmailVerification.verification_id.desc())
        .limit(1)
    )
    if verification is None:
        raise HTTPException(
            status_code=403,
            detail="이메일 인증을 먼저 완료해 주세요. (인증 후 "
            f"{settings.EMAIL_VERIFIED_VALID_MINUTES}분이 지나면 다시 인증해야 합니다)",
        )

    user = User(
        nickname=nickname,
        auth_provider=AuthProvider.local,
        provider_user_id=None,
        email=email,
        password_hash=hash_password(password),
        email_verified=True,
    )
    db.add(user)
    verification.consumed_at = _now()
    try:
        await db.flush()
    except IntegrityError:
        # 같은 이메일로 동시에 두 번 가입 요청이 온 경우 — UNIQUE 제약이 잡아준다.
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="이미 가입된 이메일입니다."
        ) from None

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


async def login(
    db: AsyncSession, email: str, password: str, user_agent: str | None = None
) -> TokenPair:
    """이메일 + 비밀번호 로그인."""
    email = _normalize_email(email)
    user = await db.scalar(select(User).where(User.email == email))

    if user is not None and user.auth_provider != AuthProvider.local:
        # 소셜로 가입한 사람은 비밀번호 자체가 없다. 그냥 401을 주면 영원히 헤맨다.
        raise HTTPException(status_code=409, detail=_already_registered(user))

    if user is None or not verify_password(password, user.password_hash):
        # 계정 없음과 비밀번호 틀림을 **같은 문구**로 답한다 —
        # 다르게 답하면 이메일 목록을 대입해 가입 여부를 캐낼 수 있다.
        raise HTTPException(
            status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다."
        )

    return await issue_tokens(db, user, user_agent)


# ═══════════════════════════════════ 소셜 로그인 ══════════════════════════════════


def _fallback_nickname(profile: SocialProfile) -> str:
    """제공자가 닉네임을 안 줬을 때(동의 안 함) 쓸 이름."""
    if profile.nickname and profile.nickname.strip():
        return profile.nickname.strip()[:20]
    return f"여행자{profile.provider_user_id[-4:]}"


async def social_login(
    db: AsyncSession, profile: SocialProfile, user_agent: str | None = None
) -> TokenPair:
    """소셜 로그인. **처음이면 자동 가입**한다(별도 회원가입 API 없음).

    같은 사람을 알아보는 열쇠는 이메일이 아니라 `(제공자, 제공자측 id)`다.
    이메일은 사용자가 카카오에서 바꿀 수 있지만 id는 바뀌지 않기 때문이다.
    """
    user = await db.scalar(
        select(User).where(
            User.auth_provider == profile.provider,
            User.provider_user_id == profile.provider_user_id,
        )
    )
    if user is not None:
        return await issue_tokens(db, user, user_agent)

    # 신규 — 같은 이메일이 다른 경로로 이미 쓰이고 있으면 계정이 쪼개지므로 막는다.
    email = _normalize_email(profile.email) if profile.email else None
    if email:
        clash = await db.scalar(select(User).where(User.email == email))
        if clash is not None:
            raise HTTPException(status_code=409, detail=_already_registered(clash))

    user = User(
        nickname=_fallback_nickname(profile),
        auth_provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        email=email,
        password_hash=None,
        email_verified=profile.email_verified,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # 같은 사용자가 동시에 두 번 로그인한 경우 — 먼저 만들어진 행을 찾아 그대로 진행한다.
        await db.rollback()
        user = await db.scalar(
            select(User).where(
                User.auth_provider == profile.provider,
                User.provider_user_id == profile.provider_user_id,
            )
        )
        if user is None:
            raise HTTPException(
                status_code=409, detail="계정 생성에 실패했습니다. 다시 시도해 주세요."
            ) from None
        return await issue_tokens(db, user, user_agent)

    await db.commit()
    await db.refresh(user)
    return await issue_tokens(db, user, user_agent)
