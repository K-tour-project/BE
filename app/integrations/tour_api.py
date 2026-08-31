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

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

# ⚠️⚠️ 인증키 유출 차단 (§3.3) — 지우지 말 것.
#   httpx는 INFO 레벨에서 요청 URL을 통째로 로그에 남긴다. TourAPI는 serviceKey를
#   **쿼리스트링**으로 받기 때문에, 그대로 두면 인증키가 서버 로그에 평문으로 쌓인다.
#   ("HTTP Request: GET ...?serviceKey=cvFOcS8at... 200 OK")
#   로그는 파일로 남고 공유·커밋되기 쉬우므로 실질적인 키 노출이다.
#   TourAPI를 쓰는 모든 경로(앱·배치 스크립트)가 이 모듈을 거치므로 여기서 막는다.
logging.getLogger("httpx").setLevel(logging.WARNING)

# 위치기반 조회 반경 상한 (공모전 규칙).
MAX_RADIUS_M = 20_000


@dataclass
class CallRecord:
    """호출 1건의 기록 — `api_call_logs` 한 행이 된다.

    ⚠️ `params`엔 serviceKey가 절대 들어가지 않는다(§3.3 인증키 저장 금지).
    실패한 호출도 기록한다 — '호출을 시도했다'는 사실 자체가 입증 자료다.
    """

    operation: str
    params: dict[str, Any]
    http_status: int | None = None
    response_time_ms: int = 0
    result_count: int | None = None
    error: str | None = None


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
        # ★ 이 클라이언트를 거친 모든 호출이 여기 쌓인다. 호출부가 잊어버릴 수 없게
        #   기록을 _get 안에 넣어뒀다 — 입증 누락은 곧 실격이라 옵션으로 두지 않았다.
        #   DB 저장은 app/integrations/call_log.py 가 맡는다(클라이언트는 DB를 모른다).
        self.calls: list[CallRecord] = []

    async def __aenter__(self) -> "TourApiClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    # ── 내부 공통 호출 ────────────────────────────────────────────────────
    async def _get(self, base: str, operation: str, **params: Any) -> list[dict]:
        """공통 파라미터를 붙여 호출하고 items 목록을 돌려준다.

        성공·실패와 무관하게 `self.calls`에 기록을 남긴다(입증용). 기록에 serviceKey는 없다.
        """
        safe_params = {k: v for k, v in params.items() if v is not None}
        query = {
            # httpx가 인코딩하므로 **Decoding 키**를 그대로 넣어야 한다.
            "serviceKey": settings.TOUR_API_KEY,
            "MobileOS": "ETC",
            "MobileApp": settings.TOUR_API_APP_NAME,
            "_type": "json",
            **safe_params,
        }
        record = CallRecord(operation=operation, params=safe_params)
        self.calls.append(record)
        started = time.perf_counter()

        def elapsed() -> int:
            return int((time.perf_counter() - started) * 1000)

        try:
            res = await self._client.get(f"{base}/{operation}", params=query)
        except httpx.HTTPError as e:
            record.response_time_ms = elapsed()
            record.error = str(e)[:200]
            raise TourApiError(f"{operation} 호출 실패: {e}") from e

        record.response_time_ms = elapsed()
        record.http_status = res.status_code

        if res.status_code != 200:
            record.error = res.text[:200]
            raise TourApiError(f"{operation} HTTP {res.status_code}: {res.text[:200]}")

        # 키가 잘못되면 공사 서버가 JSON이 아니라 XML 에러를 준다 → 원문을 살려 진단한다.
        try:
            body = res.json()
        except ValueError:
            record.error = "non-JSON response"
            raise TourApiError(
                f"{operation} 응답이 JSON이 아닙니다(키 오류일 가능성이 큽니다): {res.text[:300]}"
            ) from None

        header = body.get("response", {}).get("header", {})
        code = header.get("resultCode")
        if code not in ("0000", "00", None):
            record.error = f"[{code}] {header.get('resultMsg')}"[:200]
            raise TourApiError(f"{operation} 실패 [{code}] {header.get('resultMsg')}")

        items = body.get("response", {}).get("body", {}).get("items")
        if not items:  # 결과 0건이면 items가 빈 문자열로 온다.
            record.result_count = 0
            return []
        item = items.get("item", [])
        rows = item if isinstance(item, list) else [item]
        record.result_count = len(rows)
        return rows

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

    async def detail_intro(self, content_id: str, content_type_id: str) -> dict | None:
        """운영시간·휴무일 등 타입별 소개정보.

        `detailCommon2`엔 운영시간이 없어서 계약서의 `use_time`·`rest_date`를 채우려면
        이 호출이 따로 필요하다. `contentTypeId`는 detailCommon2 응답에서 얻는다.
        """
        rows = await self._get(
            settings.TOUR_API_BASE,
            "detailIntro2",
            contentId=content_id,
            contentTypeId=content_type_id,
        )
        return rows[0] if rows else None

    # ── 촬영지 주변 관광정보 ──────────────────────────────────────────────
    async def location_based(
        self, lat: float, lon: float, radius_m: int = 1000, rows: int = 20
    ) -> list[dict]:
        """좌표 반경 내 관광정보.

        ⚠️ 매칭용이 아니다. 실측 결과 이 오퍼레이션은 **관광지(contenttypeid=12)를
        반환하지 않는다**(강릉선교장: 좌표 7m 차이인데도 반경 5km에서 미검출).
        돌려주는 타입은 39·38·28·14·32뿐이라 촬영지 매칭에는 쓸 수 없고,
        '촬영지 주변 맛집·카페' 보강 용도다. 매칭은 `search_keyword`가 주 수단.
        """
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
        """키워드(장소명) 검색 — ★우리 장소 ↔ 관광공사 관광지 매칭의 주(主) 수단."""
        return await self._get(
            settings.TOUR_API_BASE,
            "searchKeyword2",
            keyword=keyword,
            numOfRows=rows,
            pageNo=1,
        )

    # ── 관광사진 (포토코리아) ─────────────────────────────────────────────
    # ⚠️ 이 서비스는 `PhotoGalleryService1`이다(2는 존재하지 않음). 오퍼레이션도 `~1`.
    #    한때 `galleryKeywordList2`로 잘못 적혀 있었는데 그런 경로는 없다(12번 오류).
    async def gallery_search(self, keyword: str, rows: int = 10) -> list[dict]:
        """관광사진 키워드 검색 — 사진 제목·촬영지·촬영자·웹용 이미지 URL.

        주요 필드: galTitle · galWebImageUrl · galPhotographyLocation ·
                  galPhotographer · galPhotographyMonth · galSearchKeyword
        ⚠️ 이미지는 URL만 쓴다(다운로드 금지). 저작권 표기를 위해 촬영자를 함께 노출한다.
        """
        return await self._get(
            settings.TOUR_PHOTO_API_BASE,
            "gallerySearchList1",
            keyword=keyword,
            numOfRows=rows,
            pageNo=1,
        )

    async def gallery_list(self, rows: int = 10, page: int = 1) -> list[dict]:
        """관광사진 전체 목록(최신순). 검색어 없이 둘러볼 때."""
        return await self._get(
            settings.TOUR_PHOTO_API_BASE, "galleryList1", numOfRows=rows, pageNo=page
        )

    # ── 기초지자체 중심 관광지 / 연관 관광지 ──────────────────────────────
    async def related_spots(
        self,
        area_cd: str,
        signgu_cd: str,
        *,
        base_ym: str | None = None,
        rows: int = 100,
        page: int = 1,
    ) -> list[dict]:
        """지자체의 '중심 관광지'와 그에 연결되는 '연관 관광지' 목록.

        ★ 이 앱에 특히 잘 맞는다 — 강릉시 1위가 「도깨비촬영지/(영진해변)」다.
          `locationBasedList2`가 관광지(contenttypeid=12)를 안 돌려주는 문제의 우회로이자,
          6단계 코스 추천에서 '촬영지 주변 볼거리·먹거리'를 붙일 재료다.

        ⚠️ `areaCd`/`signguCd`는 TourAPI 지역코드가 **아니라 법정동 코드**다.
           (강원특별자치도=51, 강릉시=51150 / TourAPI 지역코드로는 강원=32)
           `regions.area_code`·`sigungu_code`를 채워야 호출할 수 있다.

        주요 필드: tAtsNm(중심관광지) · rlteTatsNm(연관관광지) · rlteRank(순위) ·
                  rlteCtgryLclsNm(대분류: 관광지/음식/숙박) · rlteCtgryMclsNm(중분류)
        """
        return await self._get(
            settings.TOUR_RLTE_API_BASE,
            "areaBasedList1",
            baseYm=base_ym or settings.TOUR_RLTE_BASE_YM,
            areaCd=area_cd,
            signguCd=signgu_cd,
            numOfRows=rows,
            pageNo=page,
        )


# ── detailIntro2 필드 이름 정규화 ─────────────────────────────────────────
# 같은 '운영시간'인데 콘텐츠 타입마다 필드 이름이 다르다. 계약서는 use_time·rest_date
# 하나로 약속했으므로 여기서 흡수한다. 32(숙박)는 체크인/아웃이라 대응 필드가 없다.
_INTRO_FIELDS: dict[str, tuple[str, str]] = {
    "12": ("usetime", "restdate"),  # 관광지
    "14": ("usetimeculture", "restdateculture"),  # 문화시설
    "28": ("usetimeleports", "restdateleports"),  # 레포츠
    "38": ("opentime", "restdateshopping"),  # 쇼핑
    "39": ("opentimefood", "restdatefood"),  # 음식점
}


def intro_hours(row: dict | None, content_type_id: str | None) -> tuple[str | None, str | None]:
    """detailIntro2 응답 → `(운영시간, 휴무일)`. 대응 필드가 없으면 (None, None)."""
    fields = _INTRO_FIELDS.get(str(content_type_id or ""))
    if not row or not fields:
        return None, None
    use_key, rest_key = fields
    return (row.get(use_key) or None), (row.get(rest_key) or None)
