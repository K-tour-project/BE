"""공통 응답 스키마. API_CONTRACT.md §2(공통 규약)를 코드로 옮긴 것.

여기서 정한 모양이 곧 팀과의 약속이므로, 바꾸려면 계약서도 함께 고친다.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Location(BaseModel):
    """좌표. 배열이 아니라 객체로 주고받는다 — [x,y] 순서 혼동을 원천 차단."""

    lat: float
    lng: float


class RegionRef(BaseModel):
    """다른 응답에 끼워 넣는 지역 요약."""

    region_id: int
    name: str
    full_name: str  # "전라북도 전주시" — 화면에 그대로 노출 가능


class Page(BaseModel, Generic[T]):
    """목록 응답 고정 형태: {"items": [...], "total": n}."""

    items: list[T]
    total: int


class PageParams(BaseModel):
    """목록 API 공통 쿼리."""

    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
