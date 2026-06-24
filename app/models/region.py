"""regions — TourAPI 지역코드(areacode/sigungucode) 매핑 테이블.

⚠️ 공모전 금지 API: areaCode2(지역코드 조회)는 런타임 호출 금지(§3.6)
   → 이 표는 고정 코드값을 미리 시드(seed)로 채워 쓴다.
"""
from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import CreatedAtMixin


class Region(Base, CreatedAtMixin):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_code: Mapped[str] = mapped_column(String(10), nullable=False)
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_name: Mapped[str | None] = mapped_column(String(100))  # 시도명
    # 지역 중심 좌표(선택). 코드 테이블이라 공간 인덱스는 만들지 않음.
    centroid = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("area_code", "sigungu_code", name="uq_regions_area_sigungu"),
    )
