"""places / place_aliases — 장소와 매칭용 별칭.

⚠️ 컴플라이언스(§3.2 '무캐싱'): TourAPI 응답값(개요·전화·홈페이지·운영시간·휴무·
   대표이미지 등)은 DB에 저장하지 않는다. 여기엔 다음만 둔다.
     ① 우리 큐레이션(이름·주소·분류)  ② 큐레이션 좌표(geom)  ③ 외부 참조 ID(tour_content_id)
   상세정보는 조회 시점에 TourAPI를 실시간 호출해서 채운다.
place_aliases: 같은 장소의 다른 이름(별칭)으로 검색·TourAPI 매칭 정확도를 높인다.
"""
from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin, TimestampMixin


class Place(Base, TimestampMixin):
    __tablename__ = "places"

    place_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # 우리 큐레이션 장소명
    # 큐레이션 좌표 — geography(Point,4326). GeoAlchemy2가 GIST 공간 인덱스를 자동 생성.
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    address: Mapped[str | None] = mapped_column(Text)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.region_id", ondelete="SET NULL")
    )
    area_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    tour_content_id: Mapped[str | None] = mapped_column(String(20))  # TourAPI contentid
    tour_content_type_id: Mapped[int | None] = mapped_column(
        SmallInteger
    )  # 12관광지/14문화시설/39음식 등
    category: Mapped[str | None] = mapped_column(String(20))  # 큐레이션 분류(촬영지/명소/맛집)
    source: Mapped[str | None] = mapped_column(String(50))  # 데이터 출처 표기
    popularity: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )  # '인기 여행지' 정렬용

    region: Mapped["Region"] = relationship("Region")  # noqa: F821
    aliases: Mapped[list["PlaceAlias"]] = relationship(
        "PlaceAlias", back_populates="place", cascade="all, delete-orphan"
    )
    mappings: Mapped[list["ContentPlaceMapping"]] = relationship(  # noqa: F821
        "ContentPlaceMapping", back_populates="place", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tour_content_id", name="uq_places_tour_content_id"),
        # 장소명 부분검색용 트라이그램 인덱스 (pg_trgm 확장 필요)
        Index(
            "ix_places_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class PlaceAlias(Base, CreatedAtMixin):
    __tablename__ = "place_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.place_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50))

    place: Mapped["Place"] = relationship("Place", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("place_id", "alias", name="uq_place_aliases_place_alias"),
        Index(
            "ix_place_aliases_alias_trgm",
            "alias",
            postgresql_using="gin",
            postgresql_ops={"alias": "gin_trgm_ops"},
        ),
    )
