"""products.csv의 작품 정보."""
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    overview: Mapped[str | None] = mapped_column(Text)
    is_overview_translated: Mapped[bool | None] = mapped_column(Boolean)
    first_air_date: Mapped[date | None] = mapped_column(Date)
    product_type: Mapped[str | None] = mapped_column(Text)
    poster_url: Mapped[str | None] = mapped_column(Text)
    genres: Mapped[str | None] = mapped_column(Text)
    networks: Mapped[str | None] = mapped_column(Text)
    episode_count: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric)
    popularity: Mapped[Decimal | None] = mapped_column(Numeric)
    lead_actors: Mapped[str | None] = mapped_column(Text)
    match_similarity: Mapped[Decimal | None] = mapped_column(Numeric)
    csv_row_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
