"""regions — 지역(시도 → 시군구 2단계 계층). 지역 검색·지도 범위용.

CSV(`data/data.csv`)의 `시도`·`시군구`를 그대로 계층으로 시드한다.
  level='sido'    → name='경기도',  parent_region_id=NULL
  level='sigungu' → name='용인시',  parent_region_id=(경기도의 region_id)

⚠️ `area_code`(TourAPI areacode)는 지금 비워둔다. 공모전에서 지역코드 조회
   API(areaCode2)가 **사용 금지**라 코드를 API로 받아올 수 없기 때문. 필요해지면
   정적 매핑표로 나중에 채운다. → nullable.
"""
from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 'sido' | 'sigungu' — 계층 깊이. 문자열로 둬서 3단계(읍면동) 확장 시 마이그레이션 불필요.
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.region_id", ondelete="CASCADE")
    )

    # TourAPI 연동용 코드 — 위 주석 참고. 지금은 비어 있다.
    area_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))

    centroid = mapped_column(  # 지도 중심 좌표(소속 장소들의 평균으로 시드)
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )

    parent: Mapped["Region | None"] = relationship(
        "Region", remote_side="Region.region_id", back_populates="children"
    )
    children: Mapped[list["Region"]] = relationship(
        "Region", back_populates="parent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 같은 상위 지역 안에서 이름 중복 불가 ('용인시'는 경기도 아래 하나만).
        # ⚠️ 시도 행은 parent_region_id가 NULL인데 PostgreSQL은 기본적으로 NULL을 서로
        #    다르게 봐서 '경기도'가 두 번 들어갈 수 있다 → NULLS NOT DISTINCT(PG15+)로 차단.
        UniqueConstraint(
            "parent_region_id",
            "name",
            name="uq_regions_parent_name",
            postgresql_nulls_not_distinct=True,
        ),
    )
