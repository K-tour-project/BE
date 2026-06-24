"""users — 사용자(자체 JWT 인증).

password_hash에는 bcrypt 해시만 저장한다(평문 비밀번호 저장 금지).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum as SAEnum,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import AuthProvider, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 소셜(google/kakao) 사용자는 비밀번호가 없고, 카카오는 이메일 미제공 가능 → 둘 다 nullable
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # local 전용(bcrypt)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(AuthProvider, name="auth_provider"),
        server_default=text("'local'"),
        nullable=False,
    )
    provider_user_id: Mapped[str | None] = mapped_column(String(255))  # 소셜 제공자측 고유 ID
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )

    courses: Mapped[list["Course"]] = relationship(  # noqa: F821
        "Course", back_populates="user", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["Favorite"]] = relationship(  # noqa: F821
        "Favorite", back_populates="user", cascade="all, delete-orphan"
    )
    searches: Mapped[list["SearchHistory"]] = relationship(  # noqa: F821
        "SearchHistory", back_populates="user"
    )

    __table_args__ = (
        # 같은 소셜 제공자+제공자측 ID 조합은 유일(local은 provider_user_id가 NULL이라 무관)
        UniqueConstraint("auth_provider", "provider_user_id", name="uq_users_provider"),
    )
