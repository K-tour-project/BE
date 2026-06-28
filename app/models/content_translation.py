"""content_translations — 작품 다국어 (⏸ 지연: 9단계 다국어(en) 입증 시 활성화).

활성화: app/models/__init__.py에서 import 추가. (원하면 Content에 translations 관계도 추가)
이 파일은 아직 __init__에서 import하지 않으므로 테이블이 생성되지 않는다.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ContentTranslation(Base):
    __tablename__ = "content_translations"

    translation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(String(5), nullable=False)  # ko, en, ...
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    synopsis: Mapped[str | None] = mapped_column(Text)

    content: Mapped["Content"] = relationship("Content")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "content_id", "lang", name="uq_content_translations_content_lang"
        ),
    )
