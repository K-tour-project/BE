"""촬영지(places) 응답 스키마 — API_CONTRACT.md §4~§6.

`location`은 좌표 채움률이 100%라 **항상 있다**(지도 마커를 안전하게 찍을 수 있음).
반대로 `scene_description`은 75%가 비어 있어 프론트가 접기 처리를 해야 한다.
"""
from __future__ import annotations

from pydantic import BaseModel

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
