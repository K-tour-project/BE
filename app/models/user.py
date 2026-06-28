"""users — 사용자(구글·카카오 소셜 로그인). 최소 컬럼.

이메일/비밀번호 로그인을 추가하려면 email·password_hash 컬럼과 AuthProvider.local을 되살린다.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import AuthProvider


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(AuthProvider, name="auth_provider"), nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    courses: Mapped[list["Course"]] = relationship(  # noqa: F821
        "Course", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_user_id", name="uq_users_provider"),
    )
