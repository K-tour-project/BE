"""한국관광공사 TourAPI 클라이언트 (async).

⚠️ 공모전 필수 요건: KTO 오픈API를 **실시간 호출**해야 하며 공사가 호출 내역을 확인한다.
   파일 데이터만 쓰면 심사에서 제외되므로, 장소 상세는 반드시 이 클라이언트를 통해 매 요청 조회한다.

⚠️ 컴플라이언스
   · 응답 본문(운영시간·개요·이미지 등)은 **DB에 저장하지 않는다(무캐싱)**. 매번 실시간 조회.
     예외적으로 `contentid`(우리 장소 ↔ 관광공사 관광지 연결키)만 `places.tour_content_id`에 둔다.
   · 이미지는 **URL만** 전달하고 서버가 내려받지 않는다.
   · 금지 오퍼레이션: 지역코드(areaCode2)·서비스분류코드(categoryCode2)·산악관광정보 → 여기 구현하지 않음.
   · 위치기반 조회 반경은 20km(20000m)를 넘기지 않는다.

키가 없으면 `TourApiKeyMissing`을 던지고, 나머지 서버 기능은 정상 동작한다.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

# 위치기반 조회 반경 상한 (공모전 규칙).
MAX_RADIUS_M = 20_000


class TourApiError(RuntimeError):
    """TourAPI 호출 실패 (네트워크·HTTP·공사 측 에러코드)."""


class TourApiKeyMissing(TourApiError):
    """TOUR_API_KEY가 .env에 없음."""

    def __init__(self) -> None:
        super().__init__(
            "TOUR_API_KEY가 설정되지 않았습니다. .env에 키를 넣어주세요. "
            "발급 방법은 .env.example의 '4단계(TourAPI)' 주석 참고."
        )


class TourApiClient:
    """TourAPI 호출기. `async with TourApiClient() as api:` 로 쓴다."""

    def __init__(self, *, timeout: float | None = None) -> None:
        if not settings.tour_api_ready:
            raise TourApiKeyMissing()
        self._client = httpx.AsyncClient(
            timeout=timeout or settings.TOUR_API_TIMEOUT,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> "TourApiClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    # ── 내부 공통 호출 ────────────────────────────────────────────────────
    async def _get(self, base: str, operation: str, **params: Any) -> list[dict]:
        """공통 파라미터를 붙여 호출하고 items 목록을 돌려준다."""
        query = {
            # httpx가 인코딩하므로 **Decoding 키**를 그대로 넣어야 한다.
            "serviceKey": settings.TOUR_API_KEY,
            "MobileOS": "ETC",
            "MobileApp": settings.TOUR_API_APP_NAME,
            "_type": "json",
            **{k: v for k, v in params.items() if v is not None},
        }
        url = f"{base}/{operation}"
        try:
            res = await self._client.get(url, params=query)
        except httpx.HTTPError as e:
            raise TourApiError(f"{operation} 호출 실패: {e}") from e

        if res.status_code != 200:
            raise TourApiError(f"{operation} HTTP {res.status_code}: {res.text[:200]}")

        # 키가 잘못되면 공사 서버가 JSON이 아니라 XML 에러를 준다 → 원문을 살려 진단한다.
        try:
            body = res.json()
        except ValueError:
            raise TourApiError(
                f"{operation} 응답이 JSON이 아닙니다(키 오류일 가능성이 큽니다): {res.text[:300]}"
            ) from None

        header = body.get("response", {}).get("header", {})
        code = header.get("resultCode")
        if code not in ("0000", "00", None):
            raise TourApiError(f"{operation} 실패 [{code}] {header.get('resultMsg')}")

        items = body.get("response", {}).get("body", {}).get("items")
        if not items:  # 결과 0건이면 items가 빈 문자열로 온다.
            return []
        item = items.get("item", [])
        return item if isinstance(item, list) else [item]

    # ── 장소 상세 (4단계 핵심) ────────────────────────────────────────────
    async def detail_common(self, content_id: str) -> dict | None:
        """공통정보 — 이름·주소·개요·좌표·홈페이지. 저장 금지(실시간 조회 전용)."""
        rows = await self._get(
            settings.TOUR_API_BASE, "detailCommon2", contentId=content_id
        )
        return rows[0] if rows else None

    async def detail_images(self, content_id: str) -> list[dict]:
        """이미지 목록 — URL만 전달한다(다운로드 금지)."""
        return await self._get(
            settings.TOUR_API_BASE,
            "detailImage2",
            contentId=content_id,
            imageYN="Y",
        )

    # ── 우리 장소 ↔ 관광공사 관광지 매칭용 ────────────────────────────────
    async def location_based(
        self, lat: float, lon: float, radius_m: int = 1000, rows: int = 20
    ) -> list[dict]:
        """좌표 반경 내 관광지. 촬영지 좌표로 TourAPI contentid를 찾을 때 쓴다."""
        return await self._get(
            settings.TOUR_API_BASE,
            "locationBasedList2",
            mapX=lon,
            mapY=lat,
            radius=min(radius_m, MAX_RADIUS_M),
            numOfRows=rows,
            pageNo=1,
        )

    async def search_keyword(self, keyword: str, rows: int = 10) -> list[dict]:
        """키워드(장소명) 검색. 좌표 매칭이 애매할 때 이름으로 보조 확인."""
        return await self._get(
            settings.TOUR_API_BASE,
            "searchKeyword2",
            keyword=keyword,
            numOfRows=rows,
            pageNo=1,
        )

    # ── 관광사진 (포토코리아) ─────────────────────────────────────────────
    async def gallery_search(self, keyword: str, rows: int = 10) -> list[dict]:
        """관광사진 갤러리 검색 — 사진 제목·촬영지·웹용 이미지 URL."""
        return await self._get(
            settings.TOUR_PHOTO_API_BASE,
            "galleryKeywordList2",
            keyword=keyword,
            numOfRows=rows,
            pageNo=1,
        )
