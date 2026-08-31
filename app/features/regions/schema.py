"""지역(regions) 응답 스키마 — API_CONTRACT.md §3.

★ 「중구」는 6개 시도에, 「남구」는 5개 시도에 있다. 그래서 이름 조회는
  단일 객체가 아니라 **후보 배열**을 돌려준다. `full_name`은 사용자에게
  "서울특별시 중구"처럼 그대로 보여주라고 넣은 필드.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.shared.schema import Location


class RegionCandidate(BaseModel):
    """`GET /regions/resolve?name=`"""

    region_id: int
    name: str
    full_name: str
    level: str  # sido | sigungu
    centroid: Location | None = None


class RegionResolveResponse(BaseModel):
    candidates: list[RegionCandidate]


class RegionChild(BaseModel):
    region_id: int
    name: str
    level: str


class RegionNode(BaseModel):
    """`GET /regions` — 시도(17) 아래 시군구(227)."""

    region_id: int
    name: str
    level: str
    parent_region_id: int | None = None
    centroid: Location | None = None
    children: list[RegionChild] | None = None  # ?flat=true면 생략
