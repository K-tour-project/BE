"""contents — 작품(영화·드라마·예능).

1차 시드는 `data/data.csv`(KMDb 촬영지 + TMDB 보강) 기준이라 **사실상 전부 영화**다.
드라마는 나중에 INSERT만으로 추가할 수 있게 설계했다:
  - `content_type` enum에 drama/show를 그대로 남겨둠 (좁히면 enum 변경 마이그레이션 필요)
  - 영화 전용 값(`kmdb_code`·`runtime`)은 전부 nullable
  - `source`로 어디서 넣은 데이터인지 구분 ('KMDb' | 'manual' | 'TMDB')

poster_url·overview 등은 외부(TMDB) 이미지·텍스트의 **URL/텍스트만** 저장한다(이미지 다운로드 금지).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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

    # ── 원본 식별자 (재시드 시 중복 방지용 자연키) ──
    # KMDb 영화작품코드(예: K17686). 영화 전용이라 드라마 추가 시엔 NULL.
    kmdb_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    source: Mapped[str | None] = mapped_column(String(20))  # 'KMDb' | 'manual' | 'TMDB'
    source_url: Mapped[str | None] = mapped_column(Text)  # 출처 웹페이지주소

    # ── 작품 정보 ──
    production_year: Mapped[int | None] = mapped_column(Integer)
    original_title: Mapped[str | None] = mapped_column(String(300))
    overview: Mapped[str | None] = mapped_column(Text)
    # 장르는 배열 컬럼으로 (별도 테이블 없이 GIN 인덱스로 필터 가능).
    genre_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))

    # ── TMDB 보강 ──
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    tmdb_type: Mapped[str | None] = mapped_column(String(10))  # 'movie' | 'tv'
    vote_average: Mapped[float | None] = mapped_column(Numeric(3, 1))
    runtime: Mapped[int | None] = mapped_column(Integer)  # 분. 드라마엔 없음 → nullable

    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="content", cascade="all, delete-orphan"
    )
