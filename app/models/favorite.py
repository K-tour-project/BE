"""User-owned place favorites and independently saved products."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import CreatedAtMixin


class PlaceFavorite(Base, CreatedAtMixin):
    __tablename__ = "favorites"

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.place_id", ondelete="CASCADE"))
    tour_content_id: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        UniqueConstraint("user_id", "place_id", name="uq_favorites_user_place"),
        UniqueConstraint("user_id", "tour_content_id", name="uq_favorites_user_tour_content"),
        CheckConstraint("place_id IS NOT NULL OR tour_content_id IS NOT NULL", name="favorite_has_target"),
        Index("ix_favorites_user_created", "user_id", "created_at", "favorite_id"),
        Index("ix_favorites_place_id", "place_id"),
    )


class ProductFavorite(Base, CreatedAtMixin):
    __tablename__ = "product_favorites"

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"))

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_product_favorites_user_product"),
        Index("ix_product_favorites_user_created", "user_id", "created_at", "favorite_id"),
        Index("ix_product_favorites_product_id", "product_id"),
    )
