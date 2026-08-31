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
    """가입·로그인 경로. `local`은 이메일+비밀번호 자체 회원가입이다.

    ⚠️ PostgreSQL 네이티브 enum이라 값 추가는 `ALTER TYPE auth_provider ADD VALUE`가 필요하다
       (마이그레이션 `9a1c7d2e5b40`에서 `local`을 추가했다). 코드에만 넣으면 DB가 거부한다.
    """

    local = "local"    # 이메일 + 비밀번호
    google = "google"
    kakao = "kakao"


class CreatedAtMixin:
    """생성 시각만 필요한 테이블용."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
