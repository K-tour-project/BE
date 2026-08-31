"""TourAPI 호출 기록을 `api_call_logs`에 남긴다 (★공모전 합격 핵심★).

⚠️ 왜 별도 파일인가
  공모전 §3.1 — KTO 오픈API를 실시간 호출하고 그 내역을 **입증**해야 한다.
  파일 데이터만 쓴 것으로 보이면 심사에서 제외된다.

⚠️ 설계
  · `TourApiClient`는 DB를 모른다(호출 기록만 메모리에 쌓는다). 저장은 여기가 맡는다.
    → 클라이언트를 테스트할 때 DB가 필요 없고, 저장 정책을 여기서만 바꾸면 된다.
  · **응답 본문은 저장하지 않는다.** 무캐싱 규정(§3.2) 때문에 남기는 건 '언제·무엇을·
    얼마나 걸려 호출했나'라는 메타데이터뿐이다.
  · serviceKey는 애초에 `CallRecord.params`에 들어가지 않는다(§3.3).
  · 저장 실패가 요청을 깨뜨리지 않게 한다 — 로그 때문에 사용자 응답이 500이 되면 곤란하다.
    (다만 조용히 넘기지 않고 경고를 남긴다. 입증 자료가 비는 건 심각한 문제다.)
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.tour_api import CallRecord
from app.models import ApiCallLog

logger = logging.getLogger(__name__)


async def save_calls(
    db: AsyncSession,
    calls: list[CallRecord],
    *,
    request_id: str | None = None,
    user_id: int | None = None,
) -> int:
    """호출 기록들을 한 번에 저장하고 저장된 건수를 돌려준다.

    실패해도 예외를 밖으로 내보내지 않는다(요청 자체는 성공해야 하므로).
    """
    if not calls:
        return 0

    try:
        db.add_all(
            [
                ApiCallLog(
                    operation=c.operation,
                    request_params=c.params,
                    http_status=c.http_status,
                    response_time_ms=c.response_time_ms,
                    result_count=c.result_count,
                    request_id=request_id,
                    user_id=user_id,
                )
                for c in calls
            ]
        )
        await db.commit()
        return len(calls)
    except Exception:  # noqa: BLE001 — 로깅 실패로 사용자 요청을 깨뜨리지 않는다
        await db.rollback()
        logger.exception("api_call_logs 저장 실패 (호출 %d건) — 입증 자료가 누락됩니다", len(calls))
        return 0
