"""촬영지(places) 응답 스키마 — API_CONTRACT.md §4~§6.

`location`은 좌표 채움률이 100%라 **항상 있다**(지도 마커를 안전하게 찍을 수 있음).
반대로 `scene_description`은 75%가 비어 있어 프론트가 접기 처리를 해야 한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.features.contents.schema import ContentOnPlace
from app.shared.schema import Location, RegionRef


class PlaceInContent(BaseModel):
    """작품의 촬영지 목록 항목. `GET /contents/{id}/places`"""

    place_id: int
    name: str
    location: Location
    address: str | None = None  # 지번(기본)
    road_address: str | None = None  # 15%가 null
    region: RegionRef | None = None
    scene_description: str | None = None  # 75%가 null
    episode: str | None = None  # 드라마 촬영회차. 영화는 항상 null


class PlaceOnMap(BaseModel):
    """지역 내 촬영지 항목. `GET /regions/{id}/places`, `GET /places?near=`

    한 장소에 작품이 여러 개 붙는다(강릉선교장 = 5작품).
    """

    place_id: int
    name: str
    location: Location
    address: str | None = None
    road_address: str | None = None
    region: RegionRef | None = None
    contents: list[ContentOnPlace]
    distance_km: float | None = None  # near= 조회일 때만 채워짐


class TourDetail(BaseModel):
    """TourAPI 실시간 조회 결과 — `GET /places/{id}`의 `detail`.

    ⚠️ 이 값들은 **DB에 저장되지 않는다**(무캐싱 규정). 매 요청 실시간 조회다.
       이미지는 URL만 담는다 — 서버가 파일을 내려받지 않는다.
    """

    tour_content_id: str
    title: str | None = None
    overview: str | None = None
    tel: str | None = None
    homepage: str | None = None
    use_time: str | None = None  # detailIntro2. 타입에 따라 없을 수 있음
    rest_date: str | None = None
    parking: str | None = None
    pet_allowed: str | None = None
    images: list[str] = Field(default_factory=list)


class RelatedTourismPlace(BaseModel):
    """연관 관광지 한 건. content_id/detail_path로 관광지 상세 화면을 연다."""

    related_id: str
    content_id: str
    name: str
    sido_name: str | None = None
    sigungu_name: str | None = None
    detail_path: str


class PlaceDetail(BaseModel):
    """`GET /places/{place_id}` — 우리 데이터 + TourAPI 실시간 상세.

    ★ `detail`은 **null이 정상 경로**다. 촬영지의 절반 가까이는 관광공사에 등록된
      관광지가 아니다(방송사 사옥·스튜디오·세트장·주택가). 실측 매칭 적중률 47%.
      프론트는 "상세정보 없음"을 예외가 아니라 일반적인 화면으로 다뤄야 한다.
    """

    place_id: int
    name: str
    location: Location
    address: str | None = None
    road_address: str | None = None
    region: RegionRef | None = None
    contents: list[ContentOnPlace]
    detail: TourDetail | None = None
    related_places: list[RelatedTourismPlace] = Field(default_factory=list)
