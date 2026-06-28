"""regions — 지역코드(지역 검색용 시드 테이블). 최소 컬럼."""
from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_code: Mapped[str] = mapped_column(String(10), nullable=False)  # TourAPI areacode
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    centroid = mapped_column(  # 지도 중심 좌표
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
