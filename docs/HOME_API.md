# 홈 화면 API

## `GET /home`

로그인 없이 호출한다. 프론트는 이 요청 한 번으로 인기 작품과 인기 관광지 영역을 그린다.

```json
{
  "popular_products": [
    {
      "product_id": 42,
      "title": "작품명",
      "category": "MOVIE",
      "poster_url": "https://...",
      "rating": 9.1,
      "release_year": 2024,
      "detail_path": "/contents/42"
    }
  ],
  "popular_tourism_places": [
    {
      "content_id": "126508",
      "name": "관광지명",
      "image_url": "https://...",
      "thumbnail_url": "https://...",
      "sido_name": "서울특별시",
      "sigungu_name": "종로구",
      "favorite_count": 37,
      "ranking_source": "FAVORITE_COUNT",
      "detail_path": "/tourism-places/126508"
    }
  ],
  "tourism_ranking_basis": "FAVORITE_COUNT_THEN_TOUR_API_RECENT"
}
```

- 작품은 `products.rating DESC NULLS LAST` 순이며, 같은 별점은 `popularity DESC`,
  `product_id ASC` 순으로 고정한다. 최대 10개다.
- 관광지는 앱 사용자의 찜 수 내림차순이다. 촬영지로 연결된 장소와 TourAPI에서 직접
  찜한 장소를 하나의 `content_id`로 묶어 사용자 수를 중복 없이 센다.
- 찜에는 입장료 조건이 없으므로 무료·유료 관광지를 모두 포함한다.
- 이름과 이미지는 한국관광공사 KorService2에서 실시간으로 가져온다.
- 찜 순위가 10개보다 적은 초기 상태에는 대표 이미지가 있는 TourAPI 최근 수정 관광지로
  부족한 수를 채운다. 이 카드의 `favorite_count`는 `0`, `ranking_source`는
  `TOUR_API_RECENT`다. 이는 방문자순을 뜻하지 않는다.
- KorService2에는 관광지별 실제 방문자 수나 방문자순 정렬이 없으며, 공식 방문객 통계는
  주요 유료관광지만 대상으로 한다. 그래서 모든 관광지를 포함해야 하는 홈에서는
  방문자 수라는 이름을 쓰지 않고 `FAVORITE_COUNT`를 순위 기준으로 명시한다.
- 카드 클릭 시 응답의 `detail_path`로 이동하거나 기존
  `GET /tourism-places/{content_id}`를 호출한다.
- 외부 API 응답 본문은 저장하지 않으며 `api_call_logs`에는 호출 메타데이터만 남긴다.

API 키가 없으면 `503`, TourAPI 호출이 모두 실패하면 `502`를 반환한다. 일부 관광지 조회만
실패하면 성공한 카드들은 원래 찜 순서를 유지해 반환한다.

## 상단 찾기 버튼

- **작품으로 찾기**: `GET /contents/search?q={작품명}`으로 작품 후보를 조회한다.
- **지역으로 찾기**: `GET /regions/sidos`로 시도를 보여주고, 시도 선택 후
  `GET /regions/{sido_id}/children`으로 시군구를 보여준다. 지역명을 직접 입력하는 UI라면
  `GET /regions/resolve?name={지역명}`으로 후보를 찾는다.
- 지역을 선택하면 `region_id`로 `GET /regions/{region_id}/tourism-places`를 호출해 관광지를,
  `GET /regions/{region_id}/places`를 호출해 작품 촬영지를 조회한다.

상단 기능은 장소명을 검색하는 방식이 아니다. 이름이 같은 시군구를 구분할 수 있도록
프론트와 백엔드는 지역 선택 이후 `region_id`를 주고받는다.
