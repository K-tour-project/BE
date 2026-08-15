"""TourAPI 키 자가진단 — 키를 .env에 넣은 뒤 이 스크립트로 실제 호출까지 확인한다.

실행:
    .venv/Scripts/python.exe -m scripts.check_tour_api

키가 없으면 발급 안내만 출력하고 조용히 끝난다(에러 트레이스 없음).
키가 있으면 우리 DB의 실제 촬영지 하나를 골라 4단계 파이프라인을 그대로 시연한다:
    ① 이름으로 검색 → ② 좌표 반경으로 검색 → ③ contentId로 상세 조회 → ④ 이미지 조회
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.core.db import AsyncSessionLocal, engine
from app.services.tour_api import TourApiClient, TourApiError

GUIDE = """
TOUR_API_KEY가 아직 .env에 없습니다.

  1. https://www.data.go.kr 회원가입 (팀장 1인 계정)
  2. 아래 두 서비스에 '활용신청'
       · 한국관광공사_국문 관광정보 서비스_GW   https://www.data.go.kr/data/15101578/openapi.do
       · 한국관광공사_관광사진 정보_GW          https://www.data.go.kr/data/15101914/openapi.do
  3. 마이페이지 > 개발계정 > **일반 인증키(Decoding)** 복사
  4. BE/.env 에 한 줄 추가:

       TOUR_API_KEY=여기에_붙여넣기

  5. 다시 실행: .venv/Scripts/python.exe -m scripts.check_tour_api

※ Encoding 키가 아니라 Decoding 키입니다(헷갈리면 호출이 전부 실패합니다).
"""


async def main() -> None:
    print("=" * 60)
    print("TourAPI 연결 확인")
    print("=" * 60)

    if not settings.tour_api_ready:
        print("[키 없음]")
        print(GUIDE)
        await engine.dispose()
        return

    key = settings.TOUR_API_KEY.strip()
    print(f"[키 있음] 길이 {len(key)}자, 끝 4자리 ...{key[-4:]}")
    print(f"  관광정보 : {settings.TOUR_API_BASE}")
    print(f"  관광사진 : {settings.TOUR_PHOTO_API_BASE}")
    print()

    # DB에서 실제 촬영지 하나를 골라 시연한다.
    # 좌표는 SQL에서 뽑는다 — geoalchemy2의 to_shape()는 Shapely(선택 의존성)를 요구하는데
    # 이 프로젝트는 설치하지 않았고, 굳이 넣을 이유도 없다.
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT name, address,
                           ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
                    FROM places
                    WHERE geom IS NOT NULL
                    ORDER BY (name = '강릉선교장') DESC, place_id
                    LIMIT 1
                    """
                )
            )
        ).first()

    if row is None:
        print("DB에 장소가 없습니다. 먼저 scripts.seed_from_csv 를 실행하세요.")
        await engine.dispose()
        return

    print(f"테스트 대상 촬영지: {row.name} ({row.address})")
    print()

    ok = True
    try:
        async with TourApiClient() as api:
            # ★ 실측 결과 locationBasedList는 관광지(contenttypeid=12)를 반환하지 않는다.
            #   따라서 이름 검색이 주(主) 수단이고 좌표는 검증용이다. (DEVELOPMENT_LOG 참고)
            print("① 이름으로 검색 (searchKeyword) ← 주 매칭 수단")
            hits = await api.search_keyword(row.name, rows=3)
            for h in hits[:3]:
                print(f"   - {h.get('title')} (contentid={h.get('contentid')})")
            if not hits:
                print("   (검색 결과 없음 — 관광지로 등록되지 않은 장소일 수 있음)")

            print("\n② 좌표 반경 1km 검색 (locationBasedList)")
            near = await api.location_based(lat=row.lat, lon=row.lng, radius_m=1000, rows=3)
            for h in near[:3]:
                print(f"   - {h.get('title')} ({h.get('dist','?')}m, contentid={h.get('contentid')})")
            if not near:
                print("   (반경 내 관광지 없음)")

            cid = (hits or near or [{}])[0].get("contentid")
            if cid:
                print(f"\n③ 상세 조회 (detailCommon, contentid={cid})")
                d = await api.detail_common(str(cid))
                if d:
                    print(f"   제목  : {d.get('title')}")
                    print(f"   주소  : {d.get('addr1')}")
                    print(f"   개요  : {str(d.get('overview',''))[:60]}...")

                print(f"\n④ 이미지 조회 (detailImage)")
                imgs = await api.detail_images(str(cid))
                print(f"   이미지 {len(imgs)}장")
                for i in imgs[:2]:
                    print(f"   - {i.get('originimgurl')}")
            else:
                print("\n③④ 건너뜀 — 매칭된 contentid가 없습니다.")
    except TourApiError as e:
        ok = False
        print(f"\n[실패] {e}")
        print(
            "\n점검할 것:"
            "\n  · Decoding 키를 넣었는지 (Encoding 키면 실패)"
            "\n  · 활용신청이 '승인' 상태인지 (신청 직후 반영에 시간이 걸릴 수 있음)"
            "\n  · 일일 호출 한도(개발계정 1,000건)를 넘지 않았는지"
        )

    print()
    print("=" * 60)
    print("결과:", "정상 — 4단계 진행 가능" if ok else "실패 — 위 점검사항 확인")
    print("=" * 60)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
