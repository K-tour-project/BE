"""contents — 작품(영화·드라마·예능). 최소 컬럼.

연도·줄거리·장르·외부ID(kmdb/tmdb)·채널·인기/추천 등은 그 기능 붙일 때 추가한다.
poster_url은 KMDb/TMDB 등으로 보강한 '이미지 URL'만 저장(다운로드 금지).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import ContentType


class Content(Base):
    __tablename__ = "contents"

    content_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, name="content_type"), nullable=False
    )
    title_ko: Mapped[str] = mapped_column(String(200), nullable=False)
    poster_url: Mapped[str | None] = mapped_column(Text)

    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="content", cascade="all, delete-orphan"
    )
