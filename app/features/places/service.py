"""촬영지 조회 로직 (5단계).

계약서(API_CONTRACT.md §4~§6)의 응답을 만들기 위한 DB 질의.

★ 장소 목록을 만드는 함수는 **작품 화면·지역 화면에서도 쓰인다**(작품의 촬영지, 지역 내 촬영지).
  장소 응답을 조립하는 주인이 여기이므로, contents·regions 라우터가 여기 함수를 가져다 쓴다.

설계 메모
- 좌표는 `geography` 컬럼이라 ST_X/ST_Y를 쓰려면 geometry로 캐스팅해야 한다.
- 장소에 붙는 `contents` 배열은 장소마다 따로 조회하면 N+1이 되므로,
  place_id 목록을 모아 **한 번에** 가져와 파이썬에서 묶는다.
- 지역이 시도면 그 아래 시군구의 장소까지 포함한다(`region_scope_ids`).

`GET /places/{place_id}`(TourAPI 실시간 상세)는 4단계에서 여기에 추가한다.
그때 [`app/integrations/tour_api.py`](../../integrations/tour_api.py)를 호출한다.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape

from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.features.products.schema import ContentOnPlace
from app.features.places.matching import RETRY_AFTER_DAYS, match_place, title_similarity
from app.features.places.schema import (
    PlaceDetail,
    PlaceOnMap,
    RelatedTourismPlace,
    TourDetail,
)
from app.features.regions.service import region_ref, region_scope_ids
from app.integrations.call_log import save_calls
from app.integrations.tour_api import (
    TourApiClient,
    TourApiKeyMissing,
    intro_details,
)
from app.models import Place, Product, Region
from app.shared.schema import Location

logger = logging.getLogger(__name__)

# geography → geometry 캐스팅 후 좌표 추출
_LAT = func.ST_Y(cast(Place.geom, Geometry))
_LNG = func.ST_X(cast(Place.geom, Geometry))


def _place_select():
    """장소 + 소속 지역(+상위 지역명)을 한 번에 뽑는 공통 select."""
    parent = aliased(Region)
    return (
        select(
            Place.place_id,
            Place.name,
            Place.address,
            Place.road_address,
            Place.region_id,
            Region.name.label("region_name"),
            Region.bjd_cd.label("region_bjd_cd"),
            parent.name.label("parent_name"),
            _LAT.label("lat"),
            _LNG.label("lng"),
        )
        .select_from(Place)
        .outerjoin(Region, Region.region_id == Place.region_id)
        .outerjoin(parent, parent.region_id == Region.parent_id)
    )


async def _contents_by_place(
    db: AsyncSession, place_ids: list[int], content_id: int | None = None
) -> dict[int, list[ContentOnPlace]]:
    """같은 장소명의 작품을 연결하고 products.category를 그대로 반환한다."""
    if not place_ids:
        return {}
    anchors = (await db.execute(select(Place.place_id, Place.name).where(Place.place_id.in_(place_ids)))).all()
    names = {r.name for r in anchors}
    stmt = (
        select(
            Place.name,
            Product.product_id,
            Product.title,
            Product.category,
            Product.poster_url,
        )
        .join(Product, Product.title == Place.title)
        .where(Place.name.in_(names))
        .distinct()
        .order_by(Product.product_id)
    )
    if content_id is not None:
        stmt = stmt.where(Product.product_id == content_id)
    products_by_name: dict[str, list[ContentOnPlace]] = {}
    for r in (await db.execute(stmt)).all():
        products_by_name.setdefault(r.name, []).append(
            ContentOnPlace(
                product_id=r.product_id,
                title=r.title,
                category=r.category,
                poster_url=r.poster_url,
                detail_path=f"/contents/{r.product_id}",
            )
        )
    out: dict[int, list[ContentOnPlace]] = {}
    for anchor in anchors:
        out[anchor.place_id] = products_by_name.get(anchor.name, [])
    return out


def _shoot_count_sq():
    """동일 장소명의 촬영 작품 수."""
    sibling = aliased(Place)
    return select(func.count(func.distinct(sibling.title))).where(sibling.name == Place.name).scalar_subquery()


async def places_in_region(
    db: AsyncSession,
    region_id: int,
    content_id: int | None,
    limit: int,
    offset: int,
    sort: str = "popular",
) -> tuple[list[PlaceOnMap], int]:
    """지역 내 촬영지. (`GET /regions/{id}/places`)

    ★ 기본 정렬이 '촬영 횟수순'인 이유
      강남구 473곳·종로구 399곳처럼 촬영지가 몰린 지역이 있다. 여기서 이름 가나다순으로
      앞 20개를 주면 「달」·「누리」·「모색」 같은 한 글자 가게들이 나오고 경복궁은 안 보인다.
      사용자가 지역을 눌렀을 때 기대하는 건 그 동네의 **대표 촬영지**다.
      (종로구 촬영횟수순 = 경복궁 10편 · 경희궁 9편 · 낙산공원 9편 · 창덕궁 8편)
    """
    scope = await region_scope_ids(db, region_id)

    stmt = _place_select().where(Place.region_id.in_(scope))
    count_stmt = select(func.count()).select_from(Place).where(Place.region_id.in_(scope))

    if content_id is not None:
        product_title = select(Product.title).where(Product.product_id == content_id).scalar_subquery()
        stmt = stmt.where(Place.title == product_title)
        count_stmt = count_stmt.where(Place.title == product_title)

    order = (
        [Place.name] if sort == "name" else [_shoot_count_sq().desc(), Place.name]
    )

    total = await db.scalar(count_stmt)
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    by_place = await _contents_by_place(db, [r.place_id for r in rows], content_id)

    return [
        PlaceOnMap(
            place_id=r.place_id,
            name=r.name,
            location=Location(lat=r.lat, lng=r.lng),
            address=r.address,
            road_address=r.road_address,
            region=region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
        )
        for r in rows
    ], (total or 0)


async def _place_row(db: AsyncSession, place_id: int):
    """장소 한 건 + 소속 지역 + 저장된 TourAPI 연결키."""
    return (
        await db.execute(
            _place_select()
            .add_columns(Place.tour_content_id, Place.tour_matched_at)
            .where(Place.place_id == place_id)
        )
    ).first()


async def _related_tourism_places(
    api: TourApiClient, common: dict, row, *, limit: int = 6
) -> list[RelatedTourismPlace]:
    """연관관광지 서비스 결과를 상세 조회 가능한 TourAPI content ID와 연결한다."""
    bjd_cd = str(row.region_bjd_cd or "")
    area_cd = str(common.get("lDongRegnCd") or bjd_cd[:2])
    signgu_cd = str(common.get("lDongSignguCd") or bjd_cd[:5])
    # KorService2는 시도(2자리)와 시군구(3자리)를 분리해서 주지만,
    # 연관 관광지 API는 둘을 합친 5자리 법정동 코드를 요구한다.
    if area_cd and signgu_cd and len(signgu_cd) <= 3:
        signgu_cd = f"{area_cd}{signgu_cd}"
    if not area_cd or not signgu_cd:
        return []

    # 한 지역에 관계 행이 100건을 넘는 경우가 흔하다. 첫 페이지만 보면 현재 장소가
    # 뒤쪽에 있어도 "연관 관광지 없음"으로 오판하므로 API 허용 범위 내에서 넉넉히 조회한다.
    rows = await api.related_spots(area_cd, signgu_cd, rows=1000)
    title = str(common.get("title") or row.name or "")
    direct = [
        item for item in rows
        if title_similarity(str(item.get("tAtsNm") or ""), [title]) >= 0.75
    ]

    # 현재 장소가 중심관광지가 아니라 연관관광지 쪽에만 있으면 중심관광지를 역으로 제안한다.
    candidates = direct
    reverse = False
    if not candidates:
        candidates = [
            item for item in rows
            if title_similarity(str(item.get("rlteTatsNm") or ""), [title]) >= 0.75
        ]
        reverse = True

    candidates.sort(key=lambda item: int(item.get("rlteRank") or 999999))
    unique: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        name_key = "tAtsNm" if reverse else "rlteTatsNm"
        name = str(item.get(name_key) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(item)
        # 일부 항목은 TourAPI 상세 ID로 연결되지 않을 수 있어 여유 있게 조회한다.
        if len(unique) >= limit * 2:
            break

    searches = await asyncio.gather(
        *(api.search_keyword(str(item.get("tAtsNm" if reverse else "rlteTatsNm") or ""), rows=5) for item in unique),
        return_exceptions=True,
    )
    resolved: list[RelatedTourismPlace] = []
    for item, hits in zip(unique, searches):
        if isinstance(hits, Exception):
            continue
        name_key = "tAtsNm" if reverse else "rlteTatsNm"
        id_key = "tAtsCd" if reverse else "rlteTatsCd"
        sido_key = "areaNm" if reverse else "rlteRegnNm"
        sigungu_key = "signguNm" if reverse else "rlteSignguNm"
        name = str(item.get(name_key) or "")
        ranked = sorted(
            hits,
            key=lambda hit: title_similarity(str(hit.get("title") or ""), [name]),
            reverse=True,
        )
        hit = next(
            (
                candidate for candidate in ranked
                if candidate.get("contentid")
                and title_similarity(str(candidate.get("title") or ""), [name]) >= 0.75
            ),
            None,
        )
        if hit is None:
            continue
        content_id = str(hit["contentid"])
        resolved.append(
            RelatedTourismPlace(
                related_id=str(item.get(id_key) or ""),
                content_id=content_id,
                name=name,
                sido_name=item.get(sido_key) or None,
                sigungu_name=item.get(sigungu_key) or None,
                detail_path=f"/tourism-places/{content_id}",
            )
        )
        if len(resolved) >= limit:
            break
    return resolved


# TourAPI 응답의 homepage는 보통 `<a href="http://...">...</a>` 형태로 온다.
_HREF = re.compile(r'href\s*=\s*[\'"]?([^\'" >]+)', re.IGNORECASE)
_URL = re.compile(r'https?://[^\s<>\'"]+', re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def _clean_url(raw: str | None) -> str | None:
    """homepage 필드에서 URL만 뽑는다. 앵커 태그를 그대로 내보내면 앱이 처리해야 한다."""
    if not raw:
        return None
    decoded = unescape(raw)
    href = _HREF.search(decoded)
    if href:
        return href.group(1).strip()
    text = _TAGS.sub(" ", decoded)
    url = _URL.search(text)
    return url.group(0).rstrip(".,);]") if url else None


def _clean_text(raw: str | None) -> str | None:
    """개요에 섞여 오는 <br> 등을 걷어낸다."""
    if not raw:
        return None
    text = _BR.sub("\n", raw)
    text = unescape(_TAGS.sub("", text)).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.strip() for line in text.split("\n")).strip() or None


def _recently_attempted(attempted_at: datetime | None) -> bool:
    """최근에 매칭을 시도했었나 — 실패한 곳을 매 조회마다 재시도하지 않기 위함."""
    if attempted_at is None:
        return False
    return datetime.now(timezone.utc) - attempted_at < timedelta(days=RETRY_AFTER_DAYS)


async def get_place_detail(
    db: AsyncSession, place_id: int, *, request_id: str | None = None
) -> PlaceDetail | None:
    """장소 상세 = 우리 데이터 + **TourAPI 실시간 조회** (4단계 ★공모전 합격 핵심★).

    장소가 없으면 None(라우터가 404). TourAPI 상세 호출이 실패하면 `TourApiError`를
    올려보낸다(라우터가 502) — 계약서 §6의 약속이다.

    ⚠️ 무캐싱: TourAPI 응답 본문은 저장하지 않는다. 매 요청 실시간 조회다.
       예외적으로 `tour_content_id`(연결키)만 저장한다 — 이건 응답 본문이 아니라
       '우리 장소 ↔ 관광공사 관광지' 참조 ID라서 §3.2가 허용한다.

    ⚠️ 호출 예산(개발계정 1,000건/일)
       매칭 안 된 장소 첫 조회: 최대 3(이름검색) + 3(상세·소개·이미지) = 6건
       이미 매칭된 장소: 3건 → 하루 약 330회 조회 분량.

    설계 메모 — 언제 502이고 언제 null인가
      · 이미 연결키가 있는데 상세 조회가 실패 → **502** (장애·할당량)
      · 아직 매칭 안 된 장소의 이름 검색 실패 → **detail=null로 200**
        어차피 절반은 관광지가 아니라 null이 정상이고, 장애 때 검색까지 502로 만들면
        "원래 상세가 없는 장소"와 구분이 안 된다.
    """
    row = await _place_row(db, place_id)
    if row is None:
        return None

    by_place = await _contents_by_place(db, [place_id])
    base = dict(
        place_id=row.place_id,
        name=row.name,
        location=Location(lat=row.lat, lng=row.lng),
        address=row.address,
        road_address=row.road_address,
        region=region_ref(row.region_id, row.region_name, row.parent_name),
        contents=by_place.get(place_id, []),
    )

    try:
        api = TourApiClient()
    except TourApiKeyMissing:
        # 키가 없어도 우리 데이터는 정상 제공한다(팀원 로컬 개발 시나리오).
        logger.warning("TOUR_API_KEY 없음 — detail 없이 응답합니다 (place_id=%s)", place_id)
        return PlaceDetail(**base, detail=None)

    try:
        async with api:
            tour_id = row.tour_content_id

            # ① 아직 연결 안 된 장소면 지금 매칭한다(온디맨드).
            if not tour_id:
                # 최근에 시도해서 실패한 곳이면 다시 태우지 않는다 — 관광지가 아닌 촬영지를
                # 열 때마다 검색 3회를 쓰면 일일 한도가 금방 마른다.
                if _recently_attempted(row.tour_matched_at):
                    return PlaceDetail(**base, detail=None)

                hit = await match_place(
                    api,
                    name=row.name,
                    lat=row.lat,
                    lng=row.lng,
                    region_name=row.region_name,
                )
                # 성공·실패 무관하게 '시도했음'을 남긴다. 연결키는 찾았을 때만.
                # (연결키는 응답 본문이 아니라 참조 ID라 §3.2가 허용하는 저장 대상이다.)
                values: dict = {"tour_matched_at": func.now()}
                if hit is not None:
                    values["tour_content_id"] = hit.tour_content_id
                await db.execute(
                    update(Place).where(Place.place_id == place_id).values(**values)
                )
                await db.commit()

                if hit is None:
                    logger.info(
                        "매칭 실패 place_id=%s '%s' — %d일간 재시도하지 않습니다",
                        place_id, row.name, RETRY_AFTER_DAYS,
                    )
                    return PlaceDetail(**base, detail=None)

                tour_id = hit.tour_content_id
                logger.info(
                    "매칭 성공 place_id=%s '%s' → contentid=%s ('%s', 검색어='%s', %.0fm, 유사도=%.2f)",
                    place_id, row.name, tour_id, hit.matched_title, hit.keyword,
                    hit.distance_m, hit.similarity,
                )

            # ② 상세 — 여기 실패는 502로 올린다.
            common = await api.detail_common(tour_id)
            if common is None:
                return PlaceDetail(**base, detail=None)

            # ③ 운영시간·휴무일, ④ 이미지 — 부가 정보라 실패해도 본문은 살린다.
            use_time = rest_date = parking = pet_allowed = None
            try:
                intro = await api.detail_intro(tour_id, str(common.get("contenttypeid") or ""))
                use_time, rest_date, parking, pet_allowed = intro_details(
                    intro, common.get("contenttypeid")
                )
            except Exception:  # noqa: BLE001
                logger.warning("detailIntro2 실패 (contentid=%s) — 이용정보 생략", tour_id)

            images: list[str] = []
            try:
                images = [
                    url
                    for img in await api.detail_images(tour_id)
                    if (url := img.get("originimgurl"))
                ]
            except Exception:  # noqa: BLE001
                logger.warning("detailImage2 실패 (contentid=%s) — 이미지 생략", tour_id)

            related_places: list[RelatedTourismPlace] = []
            try:
                related_places = await _related_tourism_places(api, common, row, limit=6)
            except Exception:  # noqa: BLE001
                logger.warning("연관 관광지 조회 실패 (contentid=%s) — 목록 생략", tour_id)

            return PlaceDetail(
                **base,
                detail=TourDetail(
                    tour_content_id=tour_id,
                    title=common.get("title"),
                    overview=_clean_text(common.get("overview")),
                    tel=common.get("tel") or None,
                    homepage=_clean_url(common.get("homepage")),
                    use_time=_clean_text(use_time),
                    rest_date=_clean_text(rest_date),
                    parking=_clean_text(parking),
                    pet_allowed=_clean_text(pet_allowed),
                    images=images,
                    image_count=len(images),
                ),
                related_places=related_places,
            )
    finally:
        # ★ 성공·실패·예외 무관하게 호출 내역을 남긴다 — 이게 '실시간 호출' 입증이다.
        await save_calls(db, api.calls, request_id=request_id)


async def places_near_region(
    db: AsyncSession, region_id: int, radius_km: float, limit: int, offset: int
) -> tuple[list[PlaceOnMap], int] | None:
    """지역 중심점 반경 내 장소. 중심점이 없으면 None. (`GET /places?near=`)"""
    centroid = (
        await db.execute(
            select(cast(func.ST_PointOnSurface(Region.boundary), Geography)).where(
                Region.region_id == region_id
            )
        )
    ).scalar_one_or_none()
    if centroid is None:
        return None

    radius_m = radius_km * 1000
    dist = func.ST_Distance(Place.geom, centroid).label("dist_m")
    where = func.ST_DWithin(Place.geom, centroid, radius_m)

    total = await db.scalar(select(func.count()).select_from(Place).where(where))
    rows = (
        await db.execute(
            _place_select().add_columns(dist).where(where).order_by(dist).limit(limit).offset(offset)
        )
    ).all()
    by_place = await _contents_by_place(db, [r.place_id for r in rows])

    return [
        PlaceOnMap(
            place_id=r.place_id,
            name=r.name,
            location=Location(lat=r.lat, lng=r.lng),
            address=r.address,
            road_address=r.road_address,
            region=region_ref(r.region_id, r.region_name, r.parent_name),
            contents=by_place.get(r.place_id, []),
            distance_km=round(r.dist_m / 1000, 2),
        )
        for r in rows
    ], (total or 0)
