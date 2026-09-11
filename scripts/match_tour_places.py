"""인기 촬영지를 TourAPI 관광지에 미리 매칭해 `places.tour_content_id`를 채운다 (4단계).

실행:
    .venv/Scripts/python.exe -m scripts.match_tour_places --limit 50
    .venv/Scripts/python.exe -m scripts.match_tour_places --limit 50 --dry-run

★ 왜 전수 매칭을 안 하나
  개발계정이 **1,000건/일**이다. 촬영지 9,811곳을 전부 매칭하려면 장소당 평균 2~3회
  검색으로도 20,000건이 넘어 20일이 걸린다. 그래서 전략은 **온디맨드 + 인기곳 사전매칭**:
    · 평소엔 사용자가 실제로 연 장소만 그때 매칭한다(`GET /places/{id}`가 알아서 한다).
    · 시연에서 자주 열릴 인기 촬영지 몇백 곳만 이 스크립트로 미리 채워둔다.
  '실시간 호출' 요건에도 자연스럽게 맞는다 — 상세는 언제나 매 요청 조회다.

★ 재실행 안전
  이미 `tour_content_id`가 있는 장소는 건너뛴다. 중단됐다 다시 돌려도 이어서 진행된다.

★ 예산 관리
  `--limit`은 '시도할 장소 수'다. 장소당 최대 3회 검색하므로 실제 호출은 그보다 많을 수
  있다. 종료 시 실제 호출 수를 출력하니 남은 한도를 보며 나눠 돌리면 된다.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, text, update

from app.core.db import AsyncSessionLocal, engine
from app.features.places.matching import RETRY_AFTER_DAYS, match_place
from app.integrations.call_log import save_calls
from app.integrations.tour_api import TourApiClient, TourApiError, TourApiKeyMissing
from app.models import Place

# 촬영 횟수가 많은 곳 = 앱에서 실제로 자주 열릴 곳.
TARGETS_SQL = text(
    """
    SELECT p.place_id,
           p.name,
           r.name AS region_name,
           ST_Y(p.geom::geometry) AS lat,
           ST_X(p.geom::geometry) AS lng,
           count(DISTINCT sibling.title) AS shoot_count
    FROM places p
    LEFT JOIN regions r ON r.region_id = p.region_id
    LEFT JOIN places sibling ON sibling.name = p.name
    WHERE p.tour_content_id IS NULL
      AND p.geom IS NOT NULL
      -- 최근에 시도해 실패한 곳은 건너뛴다(--retry-failed로 무시 가능).
      AND (:retry OR p.tour_matched_at IS NULL
           OR p.tour_matched_at < now() - make_interval(days => :retry_days))
    GROUP BY p.place_id, p.name, r.name, p.geom
    ORDER BY shoot_count DESC, p.place_id
    LIMIT :limit
    """
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="인기 촬영지 TourAPI 사전 매칭")
    parser.add_argument("--limit", type=int, default=50, help="시도할 장소 수 (기본 50)")
    parser.add_argument(
        "--dry-run", action="store_true", help="DB에 저장하지 않고 결과만 출력"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=f"최근 {RETRY_AFTER_DAYS}일 내 실패한 곳도 다시 시도 (이름 변형 규칙을 고친 뒤 유용)",
    )
    args = parser.parse_args()

    try:
        api = TourApiClient()
    except TourApiKeyMissing as e:
        print(f"[중단] {e}")
        await engine.dispose()
        return

    print("=" * 66)
    print(f"인기 촬영지 사전 매칭 — 최대 {args.limit}곳{' (dry-run)' if args.dry_run else ''}")
    print("=" * 66)

    matched = failed = 0
    async with AsyncSessionLocal() as db:
        targets = (
            await db.execute(
                TARGETS_SQL,
                {
                    "limit": args.limit,
                    "retry": args.retry_failed,
                    "retry_days": RETRY_AFTER_DAYS,
                },
            )
        ).all()
        if not targets:
            print("대상이 없습니다 — 이미 전부 매칭됐거나 시드가 안 됐습니다.")
            await api.close()
            await engine.dispose()
            return

        try:
            async with api:
                for i, t in enumerate(targets, 1):
                    try:
                        hit = await match_place(
                            api,
                            name=t.name,
                            lat=t.lat,
                            lng=t.lng,
                            region_name=t.region_name,
                        )
                    except TourApiError as e:
                        # 할당량 소진·장애면 더 돌려봐야 낭비다. 여기까지 저장하고 멈춘다.
                        print(f"\n[중단] TourAPI 오류: {e}")
                        break

                    # 성공·실패 무관하게 시도 시각을 남긴다 → 다음 실행에서 건너뛴다.
                    if not args.dry_run:
                        values: dict = {"tour_matched_at": func.now()}
                        if hit is not None:
                            values["tour_content_id"] = hit.tour_content_id
                        await db.execute(
                            update(Place).where(Place.place_id == t.place_id).values(**values)
                        )
                        await db.commit()

                    if hit is None:
                        failed += 1
                        print(f"  {i:3}/{len(targets)} ✗ {t.name} (촬영 {t.shoot_count}회) — 관광지 아님/미검출")
                        continue

                    matched += 1
                    print(
                        f"  {i:3}/{len(targets)} ✓ {t.name} (촬영 {t.shoot_count}회) → "
                        f"{hit.matched_title} [{hit.tour_content_id}] "
                        f"검색어='{hit.keyword}' {hit.distance_m:.0f}m 유사도={hit.similarity}"
                    )
        finally:
            # 호출 입증 로그는 중단·오류와 무관하게 남긴다.
            saved = await save_calls(db, api.calls, request_id="batch:match_tour_places")

    tried = matched + failed
    print()
    print("=" * 66)
    print(f"시도 {tried}곳 · 매칭 {matched}곳 · 미검출 {failed}곳", end="")
    if tried:
        print(f" (적중률 {matched / tried * 100:.0f}%)")
    else:
        print()
    print(f"TourAPI 호출 {len(api.calls)}건 (api_call_logs에 {saved}건 기록)")
    print("남은 일일 한도를 보고 --limit을 조절해 나눠 돌리세요 (개발계정 1,000건/일).")
    print("=" * 66)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
