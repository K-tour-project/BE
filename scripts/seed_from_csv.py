"""data/data.csv(KMDb 촬영지 + TMDB 보강) → DB 시드.

CSV 한 행은 "작품 하나가 장소 하나에서 촬영됐다"는 사실이라, 4개 테이블로 쪼개 넣는다.

    CSV 1행 ──┬─→ regions   (시도 → 시군구 계층)
              ├─→ contents  (작품, 영화작품코드로 중복 제거)
              ├─→ places    (장소, 장소일련번호로 중복 제거)
              └─→ content_place_mappings (★둘을 잇는 핵심 자산★)

**재실행 안전(idempotent)**: 모든 INSERT가 자연키 기준 ON CONFLICT DO NOTHING이라
여러 번 돌려도 중복이 쌓이지 않는다. 중간에 실패해도 그냥 다시 돌리면 된다.

실행:
    .venv/Scripts/python.exe -m scripts.seed_from_csv
"""
from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from geoalchemy2 import WKTElement
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import AsyncSessionLocal, engine
from app.models import Content, ContentPlaceMapping, Place, Region

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "data.csv"

# asyncpg는 한 문장당 파라미터 32767개가 상한이라 넉넉히 나눠 넣는다.
CHUNK = 1000


def _s(v: str | None) -> str | None:
    """빈 문자열·공백은 NULL로."""
    if v is None:
        return None
    v = v.strip()
    return v or None


def _i(v: str | None) -> int | None:
    v = _s(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _f(v: str | None) -> float | None:
    v = _s(v)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _genres(v: str | None) -> list[str] | None:
    """'판타지,코미디,액션' → ['판타지','코미디','액션']"""
    v = _s(v)
    if v is None:
        return None
    tags = [t.strip() for t in v.split(",") if t.strip()]
    return tags or None


def _content_type(tmdb_type: str | None) -> str:
    """TMDB가 TV로 매칭한 건 drama, 그 외(영화·미매칭)는 movie.

    1차 데이터는 KMDb(한국영화DB) 출신이라 사실상 전부 movie다.
    """
    return "drama" if _s(tmdb_type) == "tv" else "movie"


async def _insert_chunks(session, table, rows: list[dict], *, constraint: str) -> None:
    """ON CONFLICT DO NOTHING으로 나눠 넣는다."""
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        stmt = pg_insert(table).values(chunk).on_conflict_do_nothing(constraint=constraint)
        await session.execute(stmt)


async def seed() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"CSV 로드: {len(rows):,}행  ({CSV_PATH})")

    async with AsyncSessionLocal() as session:
        # ── 1) regions: 시도 → 시군구 2단계 ──────────────────────────────
        sidos = sorted({r["시도"].strip() for r in rows if r["시도"].strip()})
        sido_id = {
            name: rid
            for rid, name in (
                await session.execute(
                    select(Region.region_id, Region.name).where(Region.level == "1")
                )
            ).all()
        }

        # 시군구가 빈 행(21건)은 시도에 직접 매단다 → 별도 자식 행을 만들지 않는다.
        sigungus = sorted(
            {
                (r["시도"].strip(), r["시군구"].strip())
                for r in rows
                if r["시도"].strip() and r["시군구"].strip()
            }
        )
        sigungu_id = {
            (parent, name): rid
            for rid, name, parent in (
                await session.execute(
                    select(Region.region_id, Region.name, Region.parent_id).where(
                        Region.level == "2"
                    )
                )
            ).all()
        }

        def region_of(row: dict) -> int | None:
            sd, sg = row["시도"].strip(), row["시군구"].strip()
            if not sd:
                return None
            parent = sido_id.get(sd)
            if sg and parent is not None:
                return sigungu_id.get((parent, sg), parent)
            return parent

        print(f"  regions  : 시도 {len(sidos)} + 시군구 {len(sigungus)} = {len(sidos) + len(sigungus)}")

        # ── 2) contents: 영화작품코드로 중복 제거(먼저 나온 행 채택) ──────
        seen_c: dict[str, dict] = {}
        for r in rows:
            code = _s(r["영화작품코드"])
            if not code or code in seen_c:
                continue
            seen_c[code] = {
                "kmdb_code": code,
                "content_type": _content_type(r["tmdb_type"]),
                "title_ko": _s(r["작품명"]) or "(제목없음)",
                "poster_url": _s(r["poster_url"]),
                "source": _s(r["출처"]) or "KMDb",
                "source_url": _s(r["출처 웹페이지주소(URL)"]),
                "production_year": _i(r["제작연도"]),
                "original_title": _s(r["original_title"]),
                "overview": _s(r["overview"]),
                "genre_tags": _genres(r["genre_names"]),
                "tmdb_id": _i(r["tmdb_id"]),
                "tmdb_type": _s(r["tmdb_type"]),
                "vote_average": _f(r["vote_average"]),
                "runtime": _i(r["runtime"]),
            }
        await _insert_chunks(
            session, Content.__table__, list(seen_c.values()), constraint="uq_contents_kmdb_code"
        )
        await session.flush()
        print(f"  contents : {len(seen_c):,}건")

        # ── 3) places: 장소일련번호로 중복 제거 ───────────────────────────
        # 같은 번호에 이름/좌표가 여러 개인 경우가 있어(이름 200건·좌표 20건) 첫 행을 채택한다.
        seen_p: dict[str, dict] = {}
        for r in rows:
            pid = _s(r["장소일련번호"])
            if not pid or pid in seen_p:
                continue
            lat, lon = _f(r["위도"]), _f(r["경도"])
            seen_p[pid] = {
                "kmdb_place_id": pid,
                "name": _s(r["촬영장소명"]) or "(이름없음)",
                "geom": WKTElement(f"POINT({lon} {lat})", srid=4326)
                if lat is not None and lon is not None
                else None,
                "region_id": region_of(r),
                "address": _s(r["지번주소"]),
                "road_address": _s(r["도로명주소"]),
                "source": _s(r["출처"]) or "KMDb",
            }
        await _insert_chunks(
            session, Place.__table__, list(seen_p.values()), constraint="uq_places_kmdb_place_id"
        )
        await session.flush()
        print(f"  places   : {len(seen_p):,}건")

        # ── 4) content_place_mappings: 핵심 자산 ──────────────────────────
        content_id = dict(
            (await session.execute(select(Content.kmdb_code, Content.content_id))).all()
        )
        place_id = dict(
            (await session.execute(select(Place.kmdb_place_id, Place.place_id))).all()
        )

        # (작품,장소) 쌍이 6건 중복이라 UNIQUE에 걸린다 → 여기서 미리 첫 행만 남긴다.
        seen_pair: set[tuple[int, int]] = set()
        mapping_rows: list[dict] = []
        skipped_dup = 0
        for r in rows:
            cid = content_id.get(_s(r["영화작품코드"]))
            plid = place_id.get(_s(r["장소일련번호"]))
            if cid is None or plid is None:
                continue
            if (cid, plid) in seen_pair:
                skipped_dup += 1
                continue
            seen_pair.add((cid, plid))
            mapping_rows.append(
                {
                    "content_id": cid,
                    "place_id": plid,
                    "kmdb_case_id": _s(r["사건일련번호"]),
                    "scene_description": _s(r["장면설명"]),
                    "characters": _s(r["등장인물"]),
                    "episode": None,  # 드라마 확장용. 영화 시드에선 비움.
                }
            )
        await _insert_chunks(
            session,
            ContentPlaceMapping.__table__,
            mapping_rows,
            constraint="uq_cpm_content_place",
        )
        print(f"  mappings : {len(mapping_rows):,}건  (중복쌍 {skipped_dup}건 제외)")

        # ── 5) region geometry is managed by data/regions.csv ───────────────
        # 시군구는 자기 장소들로, 시도는 자식 시군구의 장소들까지 합쳐서 계산.
        await session.execute(
            text(
                """
                SELECT 1
                """
            )
        )
        await session.execute(
            text(
                """
                SELECT 1
                """
            )
        )

        await session.commit()
        print("커밋 완료.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
