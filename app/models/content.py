"""contents / content_translations — 작품(영화·드라마·예능)과 다국어.

- poster_url: KMDb/TMDB 등으로 보강한 '이미지 URL'만 저장(다운로드·파일저장 금지, §3.4).
- era·keywords: TourAPI 매칭 실패 시 폴백 추천에 쓰는 보조 단서.
- 기본 언어(ko)는 contents에, 추가 언어(en 등)는 content_translations에 둔다(§9 다국어 입증).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import ContentType, TimestampMixin


class Content(Base, TimestampMixin):
    __tablename__ = "contents"

    content_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, name="content_type"), nullable=False
    )
    title_ko: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200))
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    poster_url: Mapped[str | None] = mapped_column(Text)  # URL 표시용(저장 금지 아님: 우리 메타)
    synopsis: Mapped[str | None] = mapped_column(Text)
    genres: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    kmdb_id: Mapped[str | None] = mapped_column(String(50))  # 외부 식별자
    tmdb_id: Mapped[str | None] = mapped_column(String(50))  # 외부 식별자
    era: Mapped[str | None] = mapped_column(String(50))  # 사극 시대 등(폴백 추천)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))  # 인물·사건 키워드(폴백)
    network: Mapped[str | None] = mapped_column(String(50))  # 방송사/채널(tvN, Netflix 등)
    popularity: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )  # '오늘의 추천 작품' 노출용

    translations: Mapped[list["ContentTranslation"]] = relationship(
        "ContentTranslation", back_populates="content", cascade="all, delete-orphan"
    )
    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="content", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("kmdb_id", name="uq_contents_kmdb_id"),
        UniqueConstraint("tmdb_id", name="uq_contents_tmdb_id"),
        # 한글 부분검색/자동완성용 트라이그램 인덱스 (pg_trgm 확장 필요 → 마이그레이션에서 생성)
        Index(
            "ix_contents_title_ko_trgm",
            "title_ko",
            postgresql_using="gin",
            postgresql_ops={"title_ko": "gin_trgm_ops"},
        ),
    )


class ContentTranslation(Base):
    __tablename__ = "content_translations"

    translation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(String(5), nullable=False)  # ko, en, ...
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    synopsis: Mapped[str | None] = mapped_column(Text)

    content: Mapped["Content"] = relationship("Content", back_populates="translations")

    __table_args__ = (
        UniqueConstraint(
            "content_id", "lang", name="uq_content_translations_content_lang"
        ),
    )
