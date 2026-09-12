"""작품 유형을 프론트 표시용 한글 카테고리로 변환한다."""


def category_label(product_type: str | None) -> str:
    normalized = (product_type or "").strip().casefold()
    if normalized in {"movie", "film"}:
        return "영화"
    return "드라마"
