"""content_place_mappings — 작품↔장소 연결 (★핵심 자산★).

TourAPI엔 "어떤 작품이 어디서 촬영됐는지"가 없다. 이 연결이 앱의 차별점이고,
1차 데이터는 `data/data.csv`(KMDb 촬영지 원본) 13,761행이 그대로 여기 들어간다.

`scene_description`(장면설명)·`characters`(등장인물)는 촬영지 '맥락'이라 이 연결에만
의미가 있다 — 같은 장소라도 작품마다 다른 장면이므로 places가 아니라 여기에 둔다.
(CSV에선 각각 74.9% / 95.2%가 비어 있어 nullable.)
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ContentPlaceMapping(Base):
    __tablename__ = "content_place_mappings"

    mapping_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.place_id", ondelete="CASCADE"), nullable=False
    )

    # KMDb 사건일련번호(예: K17686-A-011). CSV 13,761행 전부 고유해 재시드 시 중복을 막는 자연키.
    kmdb_case_id: Mapped[str | None] = mapped_column(String(40), unique=True)

    # ── 촬영지 맥락 (큐레이션) ──
    scene_description: Mapped[str | None] = mapped_column(Text)  # 장면설명
    characters: Mapped[str | None] = mapped_column(String(300))  # 등장인물
    # 드라마 확장 대비 — "도깨비 16화" 같은 촬영회차. 영화 시드에선 전부 NULL.
    episode: Mapped[str | None] = mapped_column(String(50))

    content: Mapped["Content"] = relationship("Content", back_populates="mappings")  # noqa: F821
    place: Mapped["Place"] = relationship("Place", back_populates="mappings")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("content_id", "place_id", name="uq_cpm_content_place"),
        # 장소 목록에 작품을 붙일 때(N+1 방지 쿼리)가 가장 뜨거운 경로다.
        # ⚠️ 모델에 선언해두지 않으면 alembic autogenerate가 '군더더기'로 보고 DROP을 만든다.
        Index("ix_cpm_place_id", "place_id"),
    )
