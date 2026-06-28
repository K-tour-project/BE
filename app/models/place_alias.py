"""place_aliases — 장소 매칭용 별칭 (⏸ 지연: TourAPI 매칭 파이프라인 4~5단계 시 활성화).

활성화: app/models/__init__.py에서 import 추가. (원하면 Place에 aliases 관계도 추가)
이 파일은 아직 __init__에서 import하지 않으므로 테이블이 생성되지 않는다.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin


class PlaceAlias(Base, CreatedAtMixin):
    __tablename__ = "place_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.place_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50))

    place: Mapped["Place"] = relationship("Place")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("place_id", "alias", name="uq_place_aliases_place_alias"),
        Index(
            "ix_place_aliases_alias_trgm",
            "alias",
            postgresql_using="gin",
            postgresql_ops={"alias": "gin_trgm_ops"},
        ),
    )
