"""content_place_mappings — 작품↔장소 (M:N). 이 프로젝트의 ★핵심 자산★.

TourAPI엔 '작품-촬영지' 매핑이 없다 → 우리가 직접 큐레이션한다.
- relation_type: 관계를 6종으로 분류
- relevance_reason: 추천 이유(앱 상세화면에 노출)
- confidence: 검증 수준(verified/likely/inferred)
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import Confidence, RelationType, TimestampMixin


class ContentPlaceMapping(Base, TimestampMixin):
    __tablename__ = "content_place_mappings"

    mapping_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.place_id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[RelationType] = mapped_column(
        SAEnum(RelationType, name="relation_type"), nullable=False
    )
    episode: Mapped[str | None] = mapped_column(String(50))  # 촬영회차(예: "16화")
    scene_description: Mapped[str | None] = mapped_column(Text)  # 촬영 장면/관련 설명
    relevance_reason: Mapped[str | None] = mapped_column(Text)  # 추천 이유(노출)
    confidence: Mapped[Confidence] = mapped_column(
        SAEnum(Confidence, name="confidence_level"),
        server_default=text("'inferred'"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)

    content: Mapped["Content"] = relationship("Content", back_populates="mappings")  # noqa: F821
    place: Mapped["Place"] = relationship("Place", back_populates="mappings")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("content_id", "place_id", name="uq_cpm_content_place"),
        Index("ix_cpm_content_id", "content_id"),
        Index("ix_cpm_place_id", "place_id"),
    )
