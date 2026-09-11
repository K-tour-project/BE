"""영화·드라마 공통 정보와 보존된 기존 컬럼."""
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    overview: Mapped[str | None] = mapped_column(Text)
    is_overview_translated: Mapped[bool | None] = mapped_column(Boolean)
    first_air_date: Mapped[date | None] = mapped_column(Date)
    product_type: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(10), nullable=False)
    poster_url: Mapped[str | None] = mapped_column(Text)
    genres: Mapped[str | None] = mapped_column(Text)
    networks: Mapped[str | None] = mapped_column(Text)
    episode_count: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric)
    popularity: Mapped[Decimal | None] = mapped_column(Numeric)
    lead_actors: Mapped[str | None] = mapped_column(Text)
    match_similarity: Mapped[Decimal | None] = mapped_column(Numeric)
    csv_row_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    __table_args__ = (
        CheckConstraint("category IN ('MOVIE', 'DRAMA')", name="product_category"),
    )

    movie_detail: Mapped["MovieDetail | None"] = relationship(
        "MovieDetail", back_populates="product", passive_deletes=True,
        cascade="all, delete-orphan",
    )
    drama_detail: Mapped["DramaDetail | None"] = relationship(
        "DramaDetail", back_populates="product", passive_deletes=True,
        cascade="all, delete-orphan",
    )
