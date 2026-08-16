"""우리 촬영지 ↔ 한국관광공사 관광지 매칭 (4단계).

★ 왜 이름 검색이 주(主) 수단인가 — 실측으로 뒤집힌 설계
  원래 계획은 "우리 좌표로 반경 검색해서 contentid를 찾는다"였는데 통하지 않았다.
  `locationBasedList2`가 **관광지(contenttypeid=12)를 아예 반환하지 않는다.**
  강릉선교장은 우리 좌표와 TourAPI 좌표가 7m 차이인데도 반경 1/2/5km에서 전부 미검출.
  → 이름으로 찾고(searchKeyword2), 좌표는 **검증용**으로 쓴다.

  ① 이름 변형을 순서대로 검색 → ② 후보 좌표가 우리 좌표와 500m 이내인지 확인 → ③ 채택

★ 왜 이름 변형이 필요한가
  TourAPI「강릉 선교장」 vs 우리「강릉선교장」. 완전일치가 안 된다.
  `searchKeyword2("강릉선교장")` = 0건 / `searchKeyword2("선교장")` = 1건.

★ 호출 예산
  개발계정이 1,000건/일이라 변형을 무한정 시도할 수 없다. `MAX_KEYWORD_TRIES`로 묶는다.
  실측 적중률은 상위 15곳 기준 47%(7/15)이고, 실패의 상당수는 애초에 관광지가 아니다
  (방송사 사옥·촬영 스튜디오·세트장). 못 찾는 게 정상 경로다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt

from app.integrations.tour_api import TourApiClient, TourApiError

# 이름으로 찾은 후보를 '같은 장소'로 인정하는 거리.
#
# ★ 거리 검증이 실제로 막는 것은 '이름은 같은데 다른 지역'이다 (실측)
#     수원올림픽공원 30km · 올림픽공원(창원) 290km → 확실히 배제
#   반대로 '같은 곳인데 대표좌표가 다른' 경우가 있어 500m는 너무 좁았다
#     올림픽공원: 우리 촬영지점 vs 공사 대표좌표 663m (유사도 1.00인데 탈락했었다)
#     넓은 장소(공원·휴양림·궁궐)는 어느 지점을 대표로 잡느냐에 따라 수백 m가 벌어진다.
#
#   → 1km로 넓혔다. 근처의 엉뚱한 시설(다이소 서울역점 95m)은 거리가 아니라
#     이름 유사도(MIN_TITLE_SIMILARITY)가 막으므로 이 완화로 오탐이 늘지 않는다.
NAME_MATCH_RADIUS_M = 1_000

# ★ 거리만으로는 부족하다 — 실측 오탐 사례
#   「서울역」을 검색하니 「게스 롯데아울렛 서울역점」(95m)·「다이소 서울역점」(95m)이
#   걸렸다. 좌표 검증은 통과하지만 기차역이 아니라 아울렛 옷가게·생활용품점이다.
#   도심은 500m 안에 무관한 시설이 수십 개고, 상업시설은 "OO 서울역점"처럼 짧은 지명을
#   통째로 품는다. → 이름이 얼마나 닮았는지도 함께 본다.
#
#   기준을 0.7로 둔 이유 (실측값)
#     탈락  게스 롯데아울렛 서울역점 0.43 · 다이소 서울역점 0.60
#     통과  강릉 선교장 1.0 · 합천 영상테마파크 1.0 · 용산역사박물관 1.0
#           "지역명+이름" 패턴도 안전하다 — 강릉 오죽헌↔오죽헌 0.75
#   오탐(엉뚱한 가게 정보를 촬영지 상세로 보여주는 것)이 미검출보다 훨씬 나쁘다.
#   계약서상 detail=null은 정상 경로이므로 정밀도를 우선한다.
MIN_TITLE_SIMILARITY = 0.7

# 한 장소를 매칭할 때 최대 몇 개의 이름 변형까지 검색할지 (일 1,000건 한도 보호).
MAX_KEYWORD_TRIES = 3

# 매칭에 실패한 장소를 다시 시도하기까지 기다리는 기간.
# 실패를 기억하지 않으면 '관광지가 아닌 인기 촬영지'를 열 때마다 검색 3회를 다시 태운다.
# 그렇다고 영원히 포기할 순 없다 — 관광공사에 새로 등록되는 곳이 있으므로 주기적으로 재시도한다.
RETRY_AFTER_DAYS = 30

# 지역명 꼬리 — "강릉시" → "강릉" 처럼 접두어를 잘라낼 때 쓴다.
_REGION_SUFFIX = re.compile(r"(특별자치도|특별자치시|특별시|광역시|시|군|구|도)$")
_PARENS = re.compile(r"[(\[（][^)\]）]*[)\]）]")


@dataclass
class MatchResult:
    """매칭 성공 결과. 어떤 변형이 통했는지 남겨야 규칙을 개선할 수 있다."""

    tour_content_id: str
    matched_title: str
    keyword: str  # 실제로 적중한 검색어
    distance_m: float
    similarity: float  # 이름 유사도 0~1


def region_stem(region_name: str | None) -> str | None:
    """'강릉시' → '강릉', '종로구' → '종로'. 접두어 절단에 쓸 어간."""
    if not region_name:
        return None
    stem = _REGION_SUFFIX.sub("", region_name.strip())
    return stem or None


def name_variants(name: str, region_name: str | None = None) -> list[str]:
    """검색해볼 이름 변형을 적중 가능성이 높은 순으로. (순수 함수 — 네트워크 불필요)

    >>> name_variants("강릉선교장", "강릉시")
    ['강릉선교장', '선교장', '강릉 선교장']
    """
    base = name.strip()
    if not base:
        return []

    out = [base]

    # ① 괄호·대괄호 제거 ("합천영상테마파크(주)" → "합천영상테마파크")
    cleaned = _PARENS.sub("", base).strip() or base
    if cleaned != base:
        out.append(cleaned)

    # ② 지역 접두 절단 — 실측에서 가장 효과가 컸다 ("강릉선교장" → "선교장").
    #    괄호를 걷어낸 이름에서만 파생시킨다. 괄호가 붙은 채로 자른 "영상테마파크(주)"는
    #    적중 가능성이 낮은데 호출 한 건을 그대로 먹는다(일 1,000건).
    stem = region_stem(region_name)
    if stem and cleaned.startswith(stem) and len(cleaned) > len(stem):
        tail = cleaned[len(stem):].strip()
        if tail:
            out.append(tail)
            out.append(f"{stem} {tail}")  # ③ TourAPI 표기법("강릉 선교장")

    # 순서를 지키며 중복 제거
    seen: set[str] = set()
    return [v for v in out if not (v in seen or seen.add(v))]


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 거리(m). 하버사인 — 500m 판정엔 충분하고 DB를 안 거친다."""
    r = 6_371_000
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _normalize(s: str) -> str:
    """비교용 정규화 — 공백·구두점을 없앤다. TourAPI「강릉 선교장」 = 우리「강릉선교장」."""
    return re.sub(r"[\s·,.\-_'\"()\[\]（）]", "", s)


def title_similarity(candidate_title: str, variants: list[str]) -> float:
    """후보 이름이 우리 이름(변형 포함)과 얼마나 닮았는지 0~1.

    변형 전체와 비교해 가장 높은 값을 쓴다 — 적중한 검색어가 '영상테마파크'라도
    원래 이름 '합천영상테마파크'와 후보 '합천 영상테마파크'가 사실상 같기 때문이다.
    """
    cand = _normalize(candidate_title)
    if not cand:
        return 0.0
    return max(
        (SequenceMatcher(None, cand, _normalize(v)).ratio() for v in variants if v),
        default=0.0,
    )


def _coords(row: dict) -> tuple[float, float] | None:
    """TourAPI 행에서 (lat, lng). mapx=경도, mapy=위도이고 문자열로 온다."""
    try:
        lat, lng = float(row.get("mapy") or 0), float(row.get("mapx") or 0)
    except (TypeError, ValueError):
        return None
    return (lat, lng) if lat and lng else None


async def match_place(
    api: TourApiClient,
    *,
    name: str,
    lat: float,
    lng: float,
    region_name: str | None = None,
    max_tries: int = MAX_KEYWORD_TRIES,
) -> MatchResult | None:
    """이름 검색 + 좌표 검증으로 TourAPI contentid를 찾는다. 못 찾으면 None.

    None은 오류가 아니라 **정상 결과**다 — 촬영지의 절반 가까이는 관광지가 아니다.
    """
    variants = name_variants(name, region_name)
    for keyword in variants[:max_tries]:
        try:
            hits = await api.search_keyword(keyword, rows=10)
        except TourApiError:
            # 한 변형이 실패해도 다음 변형은 시도해볼 가치가 있다.
            # (호출 자체는 api.calls에 이미 기록됐다.)
            continue

        # 좌표(500m 이내)와 이름 유사도(0.6 이상)를 **둘 다** 통과해야 채택한다.
        # 통과한 후보가 여럿이면 이름이 더 닮은 쪽, 그다음 가까운 쪽.
        best: MatchResult | None = None
        for h in hits:
            cid = h.get("contentid")
            pos = _coords(h)
            if not cid or pos is None:
                continue

            d = distance_m(lat, lng, pos[0], pos[1])
            if d > NAME_MATCH_RADIUS_M:
                continue

            title = str(h.get("title") or "")
            sim = title_similarity(title, variants)
            if sim < MIN_TITLE_SIMILARITY:
                continue

            if best is None or (sim, -d) > (best.similarity, -best.distance_m):
                best = MatchResult(
                    tour_content_id=str(cid),
                    matched_title=title,
                    keyword=keyword,
                    distance_m=round(d, 1),
                    similarity=round(sim, 2),
                )
        if best is not None:
            return best

    return None
