"""Optional shared-primary-key details for each product category."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.product import Product


class MovieDetail(Base):
    __tablename__ = "movie_details"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="CASCADE"),
        primary_key=True, autoincrement=False,
    )
    runtime: Mapped[int | None] = mapped_column(Integer)
    product: Mapped[Product] = relationship(back_populates="movie_detail")


class DramaDetail(Base):
    __tablename__ = "drama_details"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="CASCADE"),
        primary_key=True, autoincrement=False,
    )
    overview_translated: Mapped[bool | None] = mapped_column(Boolean)
    content_type: Mapped[str | None] = mapped_column(Text)
    networks: Mapped[str | None] = mapped_column(Text)
    episode_count: Mapped[int | None] = mapped_column(Integer)
    cast: Mapped[str | None] = mapped_column(Text)
    product: Mapped[Product] = relationship(back_populates="drama_detail")
