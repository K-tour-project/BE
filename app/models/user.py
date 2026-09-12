"""users — 사용자. 자체 회원가입(local)과 소셜 로그인(google·kakao)을 한 테이블에 담는다.

한 테이블로 합친 이유: `courses.user_id` 같은 FK가 가입 경로별로 갈라지면 안 되기 때문이다.
대신 경로마다 채워지는 칼럼이 달라서, 아래 CHECK 제약으로 "빈칸 조합"을 DB가 막는다.

| auth_provider | email | password_hash | provider_user_id |
|---|---|---|---|
| `local`  | 필수 | 필수 | NULL |
| `google` | 있으면 저장 | NULL | 필수(구글 sub) |
| `kakao`  | 동의 시에만 | NULL | 필수(카카오 id) |
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import AuthProvider, CreatedAtMixin


class User(Base, CreatedAtMixin):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(AuthProvider, name="auth_provider"), nullable=False
    )

    # 소셜 전용 — 구글 sub / 카카오 id. local 가입자는 NULL.
    provider_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ★ 가입 경로와 무관하게 이메일은 전역 유일하다.
    #   같은 주소로 구글 가입 후 다시 일반 가입하면 계정이 둘로 쪼개져 "내 코스가 사라졌다"가 된다.
    #   → 중복이면 409로 막고 "구글로 로그인하세요"라고 알려준다(service.py).
    #   NULL은 여럿 허용된다(PostgreSQL UNIQUE 규칙) — 이메일 동의를 안 한 카카오 가입자용.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # bcrypt 해시(60자). 평문 비밀번호는 어디에도 남기지 않는다. local 전용.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # local: 인증코드 확인을 마쳐야 true. 소셜: 제공자가 확인해 준 주소면 가입 시 true.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    courses: Mapped[list["Course"]] = relationship(  # noqa: F821
        "Course", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # noqa: F821
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    profile: Mapped["UserProfile | None"] = relationship(  # noqa: F821
        "UserProfile", back_populates="user", lazy="selectin",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def profile_image_url(self) -> str | None:
        return self.profile.profile_image_url if self.profile else None

    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_user_id", name="uq_users_provider"),
        # 경로별 필수 칼럼을 DB 차원에서 강제 — 코드 버그로 반쪽짜리 계정이 생기는 걸 막는다.
        CheckConstraint(
            "(auth_provider = 'local'"
            "  AND email IS NOT NULL AND password_hash IS NOT NULL"
            "  AND provider_user_id IS NULL)"
            " OR (auth_provider <> 'local'"
            "  AND provider_user_id IS NOT NULL AND password_hash IS NULL)",
            name="provider_fields",
        ),
    )

    @property
    def is_local(self) -> bool:
        return self.auth_provider == AuthProvider.local
