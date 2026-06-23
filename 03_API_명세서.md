# 03. API 명세서 (ERD 기준)

> 팀 ERD의 실제 테이블·컬럼명에 1:1로 맞춰 작성. Base URL: `/api/v1` · 응답 JSON · WGS84(lat/lng)
> JSON 키는 추적성을 위해 ERD 컬럼명(snake_case)을 그대로 사용한다.

## 0. 기준 스키마 (팀 ERD)
| 테이블 | 컬럼 |
|---|---|
| `users` | user_id(PK), nickname |
| `contents` | content_id(PK), external_id(uq), title |
| `places` | place_id(PK), tour_content_id(uq), place_name, latitude, longitude |
| `content_place_mappings` | mapping_id(PK), content_id(FK), place_id(FK), relation_type, scene_description |
| `courses` | course_id(PK), user_id(FK), title |
| `course_places` | course_place_id(PK), course_id(FK), place_id(FK), visit_order |

### ⚠️ ERD에 없어 런타임 보강이 필요한 값 (응답에 `_ext` 표기)
- **포스터·작품유형·연도** → `contents.external_id`로 KMDb/TMDB 조회
- **주소·운영시간·이미지·개요·썸네일** → `places.tour_content_id`로 TourAPI(`detailCommon2`/`detailIntro2`/`detailImage2`) 조회
- **거리·소요시간·동선** → Kakao Mobility/ODsay (저장 안 함, 계산값)

## 공통 규약
- 페이지네이션: `?page=1&size=20` → `{ items, page, size, total }`
- 에러: `{ "error": { "code": "...", "message": "..." } }`
- 인증: `courses` 생성/조회 등 user 관련만 토큰 필요(나머지 공개)

---

## 1. contents (작품)

### GET `/contents` — 작품 검색 / 지역 기반 작품 조회
- Query(택1 또는 병행):
  - `q` : 제목 검색(부분일치·초성)
  - `bbox=minLng,minLat,maxLng,maxLat` : **지역 검색** — 해당 영역에 매핑된 장소를 가진 작품만 (유저스토리 5)
  - `page`, `size`
- 200:
```json
{ "items": [
  { "content_id": 12, "title": "선재 업고 튀어", "external_id": "K-2024-0001",
    "poster_url_ext": "https://.../poster.jpg",
    "place_count": 7,
    "anchor_lat": 37.28, "anchor_lng": 127.01 }
], "page": 1, "size": 20, "total": 1 }
```
> `bbox` 사용 시 `anchor_lat/lng`(대표 좌표)로 지도에 포스터 마커 표시.

### GET `/contents/{content_id}` — 작품 상세
```json
{ "content_id": 12, "title": "선재 업고 튀어", "external_id": "K-2024-0001",
  "poster_url_ext": "...", "type_ext": "drama", "release_year_ext": 2024,
  "place_count": 7, "has_mappings": true }
```

### GET `/contents/{content_id}/places` — 작품의 장소 (지도 마커) ★핵심
`content_place_mappings ⋈ places` 조인.
- Query: `relation_type`(선택 필터) — 예: `filming_site`만
- 200:
```json
{ "content_id": 12, "has_mappings": true,
  "items": [
    { "mapping_id": 5001, "place_id": 101, "place_name": "수원화성",
      "latitude": 37.2849, "longitude": 127.0095,
      "relation_type": "filming_site", "scene_description": "성곽 데이트 장면" }
  ] }
```
- `has_mappings=false`(매핑 0건)면 클라이언트는 "촬영지 정보 부족" 안내 노출.
- **폴백(유저스토리 9)은 별도 엔드포인트 불필요** — 역사/배경 연관지를 `relation_type`(`historical`/`background`/`nearby_recommend`)으로 미리 매핑해두면 이 엔드포인트가 함께 반환.

---

## 2. places (장소)

### GET `/places` — 지도 영역/반경 조회
- Query(택1): `bbox=minLng,minLat,maxLng,maxLat` 또는 `lat&lng&radius`(m)
- 선택: `content_id`(특정 작품의 장소만)
- 200:
```json
{ "items": [
  { "place_id": 101, "place_name": "수원화성",
    "latitude": 37.2849, "longitude": 127.0095, "tour_content_id": 126508 }
] }
```

### GET `/places/{place_id}` — 장소 상세 (TourAPI 보강)
```json
{ "place_id": 101, "place_name": "수원화성",
  "latitude": 37.2849, "longitude": 127.0095, "tour_content_id": 126508,
  "tour_detail_ext": {
    "address": "경기 수원시 ...", "overview": "...",
    "use_time": "09:00~18:00", "rest_date": "연중무휴",
    "tel": "031-...", "images": ["..."], "thumbnail": "..." },
  "related_contents": [
    { "content_id": 12, "title": "선재 업고 튀어",
      "relation_type": "filming_site", "scene_description": "..." } ] }
```
> `related_contents` = `content_place_mappings ⋈ contents` (이 장소가 등장한 작품들).

### GET `/places/{place_id}/nearby` — 주변 추천(코스 보강)
- Query: `radius`(기본 1500m)
- 200: `places` 동일 형식 items[] (공간쿼리 `ST_DWithin`)

---

## 3. courses (코스)

### POST `/courses/optimize` — 선택 장소 → 최적 동선 ★핵심 (계산, 저장 안 함)
> TourAPI는 길찾기 미제공 → 좌표 기반 거리/시간은 Kakao Mobility(자동차)·ODsay(대중교통), 방문순서는 TSP 근사(≤10개).
- Body:
```json
{ "place_ids": [101, 102, 103],
  "start": { "latitude": 37.26, "longitude": 127.0 },
  "transport": "transit", "available_minutes": 300 }
```
- 200:
```json
{ "ordered_places": [
    { "place_id": 101, "visit_order": 1, "travel_to_next_min_ext": 15 },
    { "place_id": 103, "visit_order": 2, "travel_to_next_min_ext": 20 } ],
  "total_distance_m_ext": 8200, "total_duration_min_ext": 240,
  "polyline_ext": "...",
  "warnings": ["선택 장소가 많아 이동시간이 길어집니다."] }
```

### POST `/courses` — 코스 저장 (인증 필요)
`courses` 1건 + `course_places` N건 생성.
- Body:
```json
{ "user_id": 7, "title": "수원 선재 반나절 코스",
  "items": [ { "place_id": 101, "visit_order": 1 },
             { "place_id": 103, "visit_order": 2 } ] }
```
- 201: `{ "course_id": 555 }`

### GET `/courses/{course_id}` — 코스 조회
`courses ⋈ course_places ⋈ places` (visit_order 순).
```json
{ "course_id": 555, "user_id": 7, "title": "수원 선재 반나절 코스",
  "items": [
    { "course_place_id": 9001, "place_id": 101, "place_name": "수원화성",
      "visit_order": 1, "latitude": 37.2849, "longitude": 127.0095 } ] }
```

### GET `/users/{user_id}/courses` — 사용자의 저장 코스 목록
- 200: `{ "items": [ { "course_id": 555, "title": "..." } ] }`

### DELETE `/courses/{course_id}` — 코스 삭제 (인증)

---

## 4. users (사용자)
> Supabase Auth 등 외부 인증을 쓰면 이 섹션은 대체 가능. ERD 컬럼 기준 최소 명세.

### POST `/users` — 사용자 생성 → `{ "user_id": 7 }`  (body: `{ "nickname": "..." }`)
### GET `/users/{user_id}` — `{ "user_id": 7, "nickname": "..." }`

---

## 5. 외부 API 의존
| 기능 | API |
|---|---|
| 장소 여행정보(주소·시간·이미지) | **한국관광공사 TourAPI** (`tour_content_id`로 조회, 필수 활용) |
| 지도/마커 | **Kakao Map JS SDK** |
| 자동차/대중교통 경로 | Kakao Mobility / ODsay |
| 포스터·작품 메타 | KMDb / TMDB (`external_id`로 조회) |
| 지오코딩(지역명→bbox) | Kakao Local |

## 6. 구현 우선순위
`GET /contents/{id}/places` → `GET /places` → `POST /courses/optimize` → `GET /places/{id}` → courses 저장/조회

---

## 부록. ERD 스키마 보강 제안 (선택)
화면 요구를 ERD가 일부 못 담고 있어, 자주 쓰는 값은 컬럼 추가를 권장:
- `contents`: `type`, `release_year`, `poster_url`(외부 조회 캐시) — 매번 KMDb 호출 회피
- `places`: `address`, `thumbnail_url`, `area_code`(지역검색 성능) — TourAPI 동기화 캐시
- `content_place_mappings`: `confidence`, `relevance_reason`(상세화면 "추천 이유")
- `course_places`: `stay_minutes`(체류시간)
- 지역검색 성능을 위해 `places.latitude/longitude` 공간 인덱스(PostGIS GIST) 권장
