"""api_call_logs — KTO TourAPI 실시간 호출 입증 로그 (★공모전 합격 핵심★).

⚠️ §3.1: 파일 데이터만 쓰면 심사 제외 → 모든 TourAPI 호출을 여기 기록해 '실시간 호출'을 입증.
⚠️ §3.3: serviceKey(인증키)는 절대 저장하지 않는다 → request_params엔 키를 뺀 파라미터만.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    TIMESTAMP,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)  # areaBasedList2 등
    request_params: Mapped[dict | None] = mapped_column(JSONB)  # serviceKey 제외
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    result_count: Mapped[int | None] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(64))  # 요청 추적용(§8)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    called_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_api_call_logs_operation_called", "operation", "called_at"),
    )
