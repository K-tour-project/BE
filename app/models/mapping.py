"""content_place_mappings — 작품↔장소 연결 (★핵심 자산★). 최소 컬럼.

관계유형·촬영회차·추천이유·검증수준 등 큐레이션 상세는 그 기능 붙일 때 추가한다.
TourAPI엔 이 연결이 없어 우리가 직접 큐레이션 = 이 앱의 차별점.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
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

    content: Mapped["Content"] = relationship("Content", back_populates="mappings")  # noqa: F821
    place: Mapped["Place"] = relationship("Place", back_populates="mappings")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("content_id", "place_id", name="uq_cpm_content_place"),
    )
