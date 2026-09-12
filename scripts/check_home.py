"""현재 DB와 TourAPI로 홈 응답을 만들 수 있는지 확인한다.

실행: ``python -m scripts.check_home``
인증키 자체나 외부 API 응답 본문은 출력하지 않는다.
"""
from __future__ import annotations

import asyncio

from app.core.db import AsyncSessionLocal, engine
from app.features.home.service import home


async def main() -> int:
    try:
        async with AsyncSessionLocal() as db:
            result = await home(db)
        print(f"popular_products={len(result.popular_products)}")
        print(f"popular_tourism_places={len(result.popular_tourism_places)}")
        sources: dict[str, int] = {}
        for item in result.popular_tourism_places:
            sources[item.ranking_source] = sources.get(item.ranking_source, 0) + 1
        print(f"tourism_sources={sources}")
        return 0
    except Exception as exc:  # noqa: BLE001 - 사람이 실행하는 진단 스크립트
        print(f"{type(exc).__name__}: {str(exc)[:200]}")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
