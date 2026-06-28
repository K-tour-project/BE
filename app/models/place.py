"""places — 장소(좌표 + TourAPI 연결키). 최소 컬럼.

주소·분류·지역코드 등 부가정보와 TourAPI 상세는 그 기능 붙일 때 추가/실시간 호출.
⚠️ 컴플라이언스: TourAPI 응답값은 저장하지 않는다(무캐싱). 여기엔 우리 큐레이션
   (이름·좌표)과 외부 참조 ID(tour_content_id)만 둔다.
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

    region: Mapped["Region"] = relationship("Region")  # noqa: F821
    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="place", cascade="all, delete-orphan"
    )
