"""인증 부속 테이블 2개 — refresh_tokens · email_verifications.

**refresh_tokens** — "진짜 로그아웃"을 가능하게 하는 테이블.
  JWT(access token)는 서버가 저장하지 않아 서명만 보고 통과시킨다. 빠른 대신,
  한번 발급하면 만료 전까지 서버가 취소할 방법이 없다 → 로그아웃 버튼이 무력해진다.
  그래서 수명을 둘로 쪼갠다.
    · access  (1시간, 저장 안 함) — 실제 API 호출용
    · refresh (30일, **여기 저장**) — 오직 access 재발급용
  로그아웃 = 이 행의 `revoked_at`을 찍는 것. 이후 재발급이 막히므로 최대 1시간 뒤 완전 차단된다.

  ⚠️ 토큰 원문이 아니라 **SHA-256 해시**를 저장한다. DB가 통째로 유출돼도 그것만으론
     로그인할 수 없다. 비밀번호와 달리 bcrypt를 안 쓰는 이유는 토큰이 이미 난수 48바이트라
     사전공격 대상이 아니고, 매 재발급마다 조회해야 해서 느리면 안 되기 때문이다.

**email_verifications** — 회원가입 이메일 인증코드(6자리).
  users 행을 먼저 만들지 않는다. "인증 안 끝난 유령 계정"이 쌓이는 걸 막기 위해,
  코드 확인까지 끝난 뒤에야 users에 INSERT한다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin


class RefreshToken(Base, CreatedAtMixin):
    __tablename__ = "refresh_tokens"

    token_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex 64자. 원문은 발급 순간 응답에 한 번 실리고 서버엔 남지 않는다.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    # NULL이면 살아 있음. 로그아웃·재발급(회전) 시 시각이 찍힌다.
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # "어느 기기에서 로그인했는지" 목록을 보여줄 때 쓴다(지금은 기록만).
    user_agent: Mapped[str | None] = mapped_column(String(200))

    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="refresh_tokens"
    )

    __table_args__ = (
        # 로그아웃 전체(한 유저의 살아있는 토큰 모두 폐기) 질의용
        Index("ix_refresh_tokens_user_id", "user_id"),
    )


class EmailVerification(Base, CreatedAtMixin):
    __tablename__ = "email_verifications"

    verification_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # 코드도 해시로 저장 — 서버 로그·DB 덤프에 6자리 평문이 남지 않게.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    # 무차별 대입 방지. 6자리는 100만 조합이라 횟수 제한이 없으면 뚫린다.
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # 이 인증으로 실제 가입이 완료된 시각. 한 번 쓴 인증은 재사용할 수 없다.
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (
        # "이 이메일의 가장 최근 인증건" 조회 — 발송·확인 양쪽에서 매번 쓴다.
        Index("ix_email_verifications_email_created", "email", "created_at"),
    )
