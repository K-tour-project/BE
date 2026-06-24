"""모델 공통 요소 — Enum 타입과 타임스탬프 믹스인.

- Enum: DB에 '네이티브 ENUM 타입'으로 생성된다(자유 문자열이 아니라 정해진 값만
  허용 → 데이터 무결성 보장).
- Mixin: created_at/updated_at 같은 반복 컬럼을 모델마다 다시 쓰지 않도록 묶은 것.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column


# ── Enum 타입 ──────────────────────────────────────────────
class ContentType(str, enum.Enum):
    """작품 유형."""

    movie = "movie"
    drama = "drama"
    show = "show"  # 예능 등


class RelationType(str, enum.Enum):
    """작품↔장소 관계 유형 (핵심 자산 content_place_mappings에서 사용, 6종)."""

    filming_site = "filming_site"  # 실제 촬영지
    filming_candidate = "filming_candidate"  # 촬영지 후보
    background = "background"  # 작품 배경지
    historical = "historical"  # 역사 연관지
    fan_spot = "fan_spot"  # 팬 방문지
    nearby_recommend = "nearby_recommend"  # 주변 추천지


class Confidence(str, enum.Enum):
    """매핑 검증 수준."""

    verified = "verified"  # 검증됨
    likely = "likely"  # 유력
    inferred = "inferred"  # 추정


class TransportMode(str, enum.Enum):
    """코스 이동수단."""

    car = "car"
    transit = "transit"
    walk = "walk"


class AuthProvider(str, enum.Enum):
    """로그인 제공자. local=이메일/비밀번호, 나머지는 소셜 로그인."""

    local = "local"
    google = "google"
    kakao = "kakao"


# ── 믹스인 ────────────────────────────────────────────────
class CreatedAtMixin:
    """생성 시각만 필요한 테이블용."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """생성·수정 시각이 모두 필요한 테이블용."""

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
