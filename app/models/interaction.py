"""Deferred search history; active saves are defined in favorite.py."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin
from app.models.favorite import PlaceFavorite as Favorite, ProductFavorite  # noqa: F401


class SearchHistory(Base, CreatedAtMixin):
    __tablename__ = "search_history"

    search_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    search_type: Mapped[str | None] = mapped_column(String(20))  # content / place / region
    result_count: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship("User")  # noqa: F821

    __table_args__ = (
        Index("ix_search_history_user_created", "user_id", "created_at"),
    )
