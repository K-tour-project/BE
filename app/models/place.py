"""places — 장소(좌표 + 주소 + TourAPI 연결키).

⚠️ 컴플라이언스: TourAPI 응답값(운영시간·이미지·소개글 등)은 **저장하지 않는다(무캐싱)**.
   여기 있는 주소는 TourAPI가 아니라 CSV(KMDb 촬영지 원본)에서 온 우리 데이터다.
   TourAPI 상세는 4단계에서 `tour_content_id`로 매 요청마다 실시간 조회한다.

주소는 `address`(지번)를 기준으로 쓴다 — CSV에서 지번은 0.5%만 비어 있는 반면
도로명은 15.4%가 비어 있기 때문.
"""
from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, ForeignKey, String
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
