"""favorites / search_history — 사용자 상호작용 기록.

- favorites: 작품 또는 장소 중 '정확히 하나'를 즐겨찾기(CHECK 제약으로 강제).
- search_history: 검색어 로그(익명 검색 허용 → user_id NULL 가능).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin


class Favorite(Base, CreatedAtMixin):
    __tablename__ = "favorites"

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[int | None] = mapped_column(
        ForeignKey("contents.content_id", ondelete="CASCADE")
    )
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.place_id", ondelete="CASCADE")
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.course_id", ondelete="CASCADE")
    )  # 코스 '좋아요'(화면10의 좋아요 탭)

    user: Mapped["User"] = relationship("User", back_populates="favorites")  # noqa: F821

    __table_args__ = (
        # 작품/장소/코스 중 정확히 하나만 채워져야 함
        CheckConstraint(
            "(content_id IS NOT NULL)::int + (place_id IS NOT NULL)::int"
            " + (course_id IS NOT NULL)::int = 1",
            name="favorites_exactly_one_target",
        ),
        # NULLS NOT DISTINCT(PG15+): NULL을 같은 값으로 취급해야 중복 즐겨찾기를 진짜로 막음
        UniqueConstraint(
            "user_id",
            "content_id",
            "place_id",
            "course_id",
            name="uq_favorites_user_target",
            postgresql_nulls_not_distinct=True,
        ),
    )


class SearchHistory(Base, CreatedAtMixin):
    __tablename__ = "search_history"

    search_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    search_type: Mapped[str | None] = mapped_column(String(20))  # content / place / region
    result_count: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship("User", back_populates="searches")  # noqa: F821

    __table_args__ = (
        Index("ix_search_history_user_created", "user_id", "created_at"),
    )
