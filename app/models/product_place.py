"""Explicit filming relation between a product and a database place."""
from sqlalchemy import BigInteger, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProductPlace(Base):
    __tablename__ = "product_places"
    __table_args__ = (Index("ix_product_places_place_id", "place_id"),)

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True
    )
    place_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("places.place_id", ondelete="CASCADE"), primary_key=True
    )
