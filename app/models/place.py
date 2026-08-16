"""places — 장소(좌표 + 주소 + TourAPI 연결키).

⚠️ 컴플라이언스: TourAPI 응답값(운영시간·이미지·소개글 등)은 **저장하지 않는다(무캐싱)**.
   여기 있는 주소는 TourAPI가 아니라 CSV(KMDb 촬영지 원본)에서 온 우리 데이터다.
   TourAPI 상세는 4단계에서 `tour_content_id`로 매 요청마다 실시간 조회한다.

주소는 `address`(지번)를 기준으로 쓴다 — CSV에서 지번은 0.5%만 비어 있는 반면
도로명은 15.4%가 비어 있기 때문.
"""
from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Place(Base):
    __tablename__ = "places"

    place_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    geom = mapped_column(  # 큐레이션 좌표 (GeoAlchemy2가 GIST 공간 인덱스 자동 생성)
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.region_id", ondelete="SET NULL")
    )
    tour_content_id: Mapped[str | None] = mapped_column(String(20))  # TourAPI contentid

    # 마지막으로 TourAPI 매칭을 시도한 시각 (성공·실패 무관).
    # ★ 왜 필요한가: 촬영지의 절반 가까이는 관광공사 등록 관광지가 아니다. 이 기록이 없으면
    #   그런 장소를 열 때마다 이름검색 3회를 다시 태워 일일 한도(개발계정 1,000건)를 갉아먹는다.
    #   남양주종합촬영소(촬영 118회)처럼 인기 있는데 매칭 안 되는 곳이 특히 위험하다.
    # ⚠️ 무캐싱 규정과 무관하다 — TourAPI 응답 본문이 아니라 '우리가 언제 시도했나'는 자체 기록.
    tour_matched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # ── 원본 식별자 (재시드 시 중복 방지용 자연키) ──
    # KMDb 장소일련번호(예: GG-P-1113).
    kmdb_place_id: Mapped[str | None] = mapped_column(String(30), unique=True)
    source: Mapped[str | None] = mapped_column(String(20))  # 'KMDb' | 'manual'

    # ── 주소 ──
    address: Mapped[str | None] = mapped_column(String(300))  # 지번주소 (기준)
    road_address: Mapped[str | None] = mapped_column(String(300))  # 도로명주소

    region: Mapped["Region"] = relationship("Region")  # noqa: F821
    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="place", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 지역 내 촬영지 조회(지도 화면)의 기본 필터.
        # ⚠️ 모델에 선언해두지 않으면 alembic autogenerate가 '군더더기'로 보고 DROP을 만든다.
        # geom의 GIST 인덱스(idx_places_geom)는 GeoAlchemy2가 자동 생성하므로 여기 없어도 된다.
        Index("ix_places_region_id", "region_id"),
    )
