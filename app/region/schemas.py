"""Schemas for region selection APIs."""
from __future__ import annotations

from pydantic import BaseModel


class RegionOption(BaseModel):
    region_id: int
    name: str


class SidoOption(RegionOption):
    has_sigungu: bool


class SigunguListResponse(BaseModel):
    sido: SidoOption
    disable_sigungu_select: bool
    items: list[RegionOption]


class RegionSelectionRequest(BaseModel):
    sido_id: int
    sigungu_id: int | None = None


class RegionSelectionResponse(BaseModel):
    sido: SidoOption
    sigungu: RegionOption | None = None
    selected_region_id: int
