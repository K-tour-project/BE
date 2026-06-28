"""모델 공통 요소 — Enum 타입과 created_at 믹스인 (최소 버전).

지연/확장 시 추가될 enum(transport_mode·relation_type·confidence_level)은
해당 컬럼을 되살릴 때 함께 추가한다.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column


class ContentType(str, enum.Enum):
    """작품 유형."""

    movie = "movie"
    drama = "drama"
    show = "show"  # 예능 등


class AuthProvider(str, enum.Enum):
    """소셜 로그인 제공자."""

    google = "google"
    kakao = "kakao"


class CreatedAtMixin:
    """생성 시각만 필요한 테이블용."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
