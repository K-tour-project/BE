# 마이페이지 API

모든 `/me/*` 요청에는 `Authorization: Bearer <access_token>`이 필요합니다.
사용자 ID는 토큰에서 결정하며 프론트가 별도 사용자 ID를 보내지 않습니다.

화면과 API 설명에서는 **영화·드라마 작품은 ‘저장’, 관광지 장소는 ‘찜’**으로 구분합니다.

| 대상 | 화면 표현 | 개수 필드 |
|---|---|---|
| 영화·드라마 작품 | 저장한 작품 | `saved_product_count` |
| 관광지 장소(촬영 장소 포함) | 찜한 장소 | `favorite_place_count` |

## 화면 진입과 탭 전환

| 동작 | 요청 |
|---|---|
| 마이페이지 진입 | `GET /me/mypage?limit=20&offset=0` |
| 찜한 장소 더 보기·탭 재조회 | `GET /me/favorite-places?limit=20&offset=20` |
| 저장한 작품 탭 클릭 | `GET /me/saved-products?limit=20&offset=0` |

장소 목록은 최근 찜 순, 작품 목록은 최근 저장 순입니다. `limit`은 1~50, `offset`은 0 이상이며,
`total`은 현재 사용자의 해당 목록 전체 개수입니다. 다음 페이지는 `offset + limit`로 요청합니다.

`GET /me/mypage`는 사용자 정보와 두 개수, **찜한 장소 목록만** 반환합니다.
작품 목록과 작품에 대한 TourAPI 요청은 이때 실행하지 않습니다.

```json
{
  "user": {
    "user_id": 7,
    "nickname": "여행자",
    "email": "user@example.com",
    "profile_image_url": "https://images.example.com/profile.jpg"
  },
  "counts": {
    "favorite_place_count": 2,
    "saved_product_count": 1
  },
  "favorite_places": {
    "items": [{
      "favorite_id": 21,
      "place_id": 123,
      "tour_content_id": "126508",
      "name": "경복궁",
      "thumbnail_url": "https://images.example.com/place.jpg",
      "sido_name": "서울특별시",
      "sigungu_name": "종로구",
      "saved_at": "2026-09-12T05:00:00Z",
      "detail_path": "/places/123",
      "tour_status": "ok"
    }, {
      "favorite_id": 20,
      "place_id": null,
      "tour_content_id": "999999",
      "name": "관광지 예시",
      "thumbnail_url": null,
      "sido_name": "서울특별시",
      "sigungu_name": "종로구",
      "saved_at": "2026-09-12T04:00:00Z",
      "detail_path": "/tourism-places/999999",
      "tour_status": "ok"
    }],
    "total": 2
  }
}
```

예시의 ID·URL은 설명용입니다. 소셜 이메일 동의가 없으면 `email`은 `null`입니다.
등록한 사진이 없으면 `profile_image_url`도 `null`이며 프론트의 기본 이미지를 표시합니다.

장소명과 썸네일은 매 조회마다 TourAPI `detailCommon2`에서 가져옵니다.
시도·시군구 이름은 응답의 법정동 코드(`lDongRegnCd`, `lDongSignguCd`)를
기존 `regions` 데이터에 매핑합니다. 지역코드 API는 추가 호출하지 않습니다.
TourAPI 본문과 이미지는 DB에 저장하지 않고 호출 메타데이터만 기록합니다.

| `tour_status` | 의미와 표시 처리 |
|---|---|
| `ok` | 실시간 조회 성공. 사진이 원래 없으면 썸네일은 `null`. |
| `unmatched` | DB 촬영지에 TourAPI 연결 ID가 없음. DB 장소명·지역명으로 표시. |
| `not_found` | TourAPI에서 해당 콘텐츠를 찾지 못함. 찜 기록과 개수는 유지. |
| `unavailable` | TourAPI 오류·키 미설정. DB 정보가 있으면 사용하며 외부 정보는 `null`. |

장애 시 일반 관광지의 `name`, 지역명, 썸네일은 `null`일 수 있습니다.
조회 실패를 찜 취소로 간주하지 말고 재시도 안내를 표시합니다.

작품 탭 응답:

```json
{
  "items": [{
    "product_id": 42,
    "title": "작품 예시",
    "poster_url": "https://images.example.com/poster.jpg",
    "category": "MOVIE",
    "release_year": 2020,
    "saved_at": "2026-09-12T05:00:00Z",
    "detail_path": "/contents/42"
  }],
  "total": 1
}
```

`category`는 `MOVIE`(영화) / `DRAMA`(드라마)입니다.
`release_year`는 영화 개봉일·드라마 최초 방영일(`first_air_date`)의 연도이며
원본 날짜가 없으면 `null`입니다. 포스터도 없으면 `null`입니다.

## 찜·저장 버튼과 취소

| 대상·동작 | 요청 |
|---|---|
| DB 촬영지 찜 / 취소 | `PUT` / `DELETE /me/favorites/places/{place_id}` |
| TourAPI 관광지 찜 / 취소 | `PUT` / `DELETE /me/favorites/tourism/{content_id}` |
| 마이페이지 장소 목록에서 취소 | `DELETE /me/favorite-places/{favorite_id}` |
| 작품 저장 / 취소 | `PUT` / `DELETE /me/saved-products/{product_id}` |

요청 본문은 없습니다. `PUT` 재시도는 중복 저장되지 않고,
`DELETE`는 이미 취소한 항목이어도 200을 반환합니다. 다른 사용자의 기록에는 영향을 주지 않습니다.
같은 TourAPI ID에 연결된 촬영지와 일반 관광지는 같은 찜으로 인식합니다.
일반 관광지는 처음 찜할 때 TourAPI에 실제 존재하는지 확인합니다.

```json
{
  "is_saved": false,
  "favorite_id": null,
  "favorite_place_count": 1,
  "saved_product_count": 1
}
```

찜 추가 응답의 `favorite_id`는 실제 찜 레코드 ID이며, 작품 저장·취소 응답에서는 `null`입니다.
공통 응답 필드 `is_saved`는 장소 API에서는 찜 여부, 작품 API에서는 저장 여부를 뜻합니다.
프론트 버튼에는 대상에 맞게 ‘찜’ 또는 ‘저장’으로 표시합니다.
취소 응답을 받은 뒤 프론트 목록에서 해당 항목을 제거하고 응답의 두 개수로 카운터를 갱신합니다.

## 상세 화면 이동

프론트는 사용자가 목록 항목을 누르면 해당 상세 화면으로 이동하고,
그 항목의 `detail_path`로 GET 요청해 받은 JSON을 화면에 표시합니다.
`detail_path`는 백엔드 상세 조회 API 경로이며 프론트 화면 URL은 아닙니다.
마이페이지 전용 상세 API를 추가하지 않고 기존 상세 API를 재사용합니다.

| ID | 상세 API |
|---|---|
| 내부 DB `place_id` | `GET /places/{place_id}` |
| TourAPI `content_id` | `GET /tourism-places/{content_id}` |
| 내부 DB `product_id` | `GET /contents/{product_id}` |

작품 코드는 `app/features/products`에 있지만, 기존 프론트 호환을 위해
외부 작품 API 경로 `/contents`는 유지합니다.

## 프로필 사진 등록·수정

회원가입 `POST /auth/signup`에 선택 필드 `profile_image_url`을 추가했습니다.
구글·카카오는 최초 가입 시 제공자가 전달한 사진 URL을 저장합니다.
기존 소셜 회원이 다시 로그인해도 설정 화면에서 수정한 사진을 덮어쓰지 않습니다.

설정 화면에서 `PATCH /me/profile`:

```json
{ "profile_image_url": "https://images.example.com/changed.jpg" }
```

응답은 `user_id`, `nickname`, `email`, `profile_image_url`입니다.
`{"profile_image_url": null}`은 기본 이미지로 초기화합니다.
빈 요청, HTTP(S)가 아닌 URL, 사용자 ID 등 추가 필드는 422입니다.
URL만 저장하며 사진 파일 업로드나 외부 이미지 다운로드는 하지 않습니다.

## 오류

- 401: 로그인 필요 / 유효하지 않은 토큰
- 404: 찜·저장하려는 장소·작품·관광지가 없음
- 422: ID, 페이지 범위, URL 또는 요청 형식 오류
- 502: 관광지를 처음 찜할 때 TourAPI 확인 실패. 저장하지 않았으므로 재시도 가능

## DB 적용과 테스트

기존 DB에 적용됐다가 코드에서 제거된 마이그레이션 세 개를 복원했습니다.
`d4e6f8a0b2c3` 이력과 기존 테이블·데이터를 그대로 이어받으며,
새 리비전 `e5f7a9b1c3d5`가 일반 관광지 찜을 위한 nullable `place_id`와
`tour_content_id`, 유일성·대상 존재 CHECK 제약을 추가합니다.
이전 안내의 `recover_rolled_back_migrations.sql`은 이번 기능과 양립하지 않으므로 실행하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

DB 통합 테스트는 `ktour_mypage_test_*`라는 이름의 별도 DB를 준비해 전체 마이그레이션을 적용한 뒤,
그 URL을 `TEST_DATABASE_URL`로 설정하고 같은 테스트 명령을 실행합니다.
설정하지 않으면 DB 통합 테스트만 skip합니다. 테스트마다 DB 변경은 롤백되고,
TourAPI 응답은 대역으로 검증합니다.
