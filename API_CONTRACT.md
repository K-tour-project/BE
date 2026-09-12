# Every Trip — 백엔드 API 계약서 (v1)

> **이 문서는 팀 간 약속입니다.** 프론트엔드(윤영)와 AI(조시현)는 백엔드 완성을 기다리지 않고
> 이 문서만 보고 병렬로 개발할 수 있습니다. 여기 적힌 필드명·타입·null 여부는 **백엔드가 지킵니다.**
>
> 바꿔야 할 부분을 발견하면 **구현 전에** 말해주세요. 각자 완성 후 연결하는 방식이라,
> 계약이 어긋나면 마감 직전에야 드러납니다.
>
> 작성 2026-08-15 · 기준 DB: 작품 1,694 / 촬영지 9,811 / 작품↔촬영지 연결 13,755

---

## 0. 먼저 읽어야 할 데이터 특성 ⚠️

실제 데이터를 넣어보고 발견한 것들입니다. **화면·로직 설계에 직접 영향을 줍니다.**

| # | 사실 | 그래서 해야 할 일 |
|---|---|---|
| 1 | **`poster_url`이 없는 작품이 296편(18%)** | 포스터 자리에 **기본 이미지(placeholder)를 반드시 준비**. null 체크 없이 쓰면 깨진 이미지가 뜸 |
| 2 | **제목이 같은 작품이 존재** — 「만추」(1966·1981), 「순정」(1968·2015) | 목록·후보에 **연도를 함께 표시**. 제목만으로 특정하지 말 것 |
| 3 | **지역명이 같은 곳이 많음** — **「중구」는 6개 시도에**, 「남구」는 5개 시도에 | 지역은 **`region_id`로 주고받기**. 이름으로 보내면 후보가 여러 개 옴 (→ §0.5: 목록으로 처리) |
| 4 | **`scene_description`(장면설명)이 75% 비어 있음** | 있으면 보여주고 없으면 영역을 접는 UI. 항상 있다고 가정 금지 |
| 5 | **1차 데이터는 사실상 전부 영화** (드라마 10편) | 화면 문구를 "영화 촬영지" 기준으로. `content_type`은 `drama`도 올 수 있게 열어둠 |
| 6 | **`road_address`(도로명)가 15% 비어 있음** | 주소 표시는 `address`(지번)를 기본으로, 도로명은 보조 |

---

## 0.5 유저 플로우 ↔ API 매핑

팀에서 합의한 사용자 흐름과, 각 단계에서 부를 API입니다. **"이 화면에서 뭘 부르지?"는 여기를 보세요.**

| # | 화면 · 동작 | 부를 API | 담당 |
|---|---|---|---|
| 1 | 챗봇 인터페이스로 시작 | (AI 내부) | 조시현 |
| 2 | 사용자가 지역 또는 작품 검색 | 아래 3·4로 분기 | 윤영/조시현 |
| 3 | **작품 검색 → 작품 목록 출력** | `GET /contents/search?q=` | 윤영 |
| 4 | **지역 검색 → 지도 + 그 지역의 모든 포스터** | `GET /regions/{region_id}/places` | 윤영 |
| 4b | 지도에서 **영화 하나 선택** → 그 영화 촬영지만 | `GET /regions/{region_id}/places?content_id=` | 윤영 |
| 5 | **결과에서 가고 싶은 장소 여러 개 선택** | *API 불필요* — 앱이 `place_id` 목록을 들고 있으면 됨 | 윤영 |
| 6 | **최적 동선 짜기** | `POST /courses/recommend` (`place_ids` 전달) | 윤영/조시현 |
| 6b | 각 장소의 간단한 정보 표시 | `GET /places/{place_id}` | 윤영 |
| — | 코스 저장 (로그인 필요) | `POST /courses` | 윤영 |

**애매한 검색어 처리 — 되묻지 않고 목록으로 해결합니다**

3·4번이 "목록 출력"이라서 별도의 확인 대화가 필요 없습니다:

```
"만추" 검색 → 목록에 [만추 1981] [만추 1966] 둘 다 표시 → 사용자가 탭
"중구" 검색 → 목록에 [서울 중구] [부산 중구] … 6개 표시 → 사용자가 탭
```

각 리졸브 API가 돌려주는 `candidates` 배열이 **곧 그 목록**입니다. 그대로 화면에 뿌리면 됩니다.
챗봇도 마찬가지로 후보를 목록 UI로 넘기면 되고, 굳이 말로 되물을 필요는 없습니다.

---

## 1. 공통 규약

| 항목 | 규약 |
|---|---|
| Base URL (개발) | `http://127.0.0.1:8000` |
| 형식 | 요청·응답 모두 JSON (`Content-Type: application/json`) |
| 필드 이름 | **snake_case** (`poster_url`, `content_id`) |
| 인증 | 필요한 API만. `Authorization: Bearer <JWT>` 헤더 |
| 좌표 | 항상 **`{"lat": 위도, "lng": 경도}`** 객체. 배열(`[x, y]`)로 주고받지 않음 — 순서 혼동 방지 |
| 목록 응답 | `{"items": [...], "total": 정수}` 고정. 페이지는 쿼리 `limit`(기본 20, 최대 100)·`offset`(기본 0) |
| 에러 | `{"detail": "사람이 읽을 수 있는 메시지"}` + 적절한 HTTP 상태코드 |
| 시각 | ISO 8601 UTC (`2026-08-15T06:12:00Z`) |
| null | 아래 각 API의 **`?` 표시가 붙은 필드는 null이 올 수 있음** |

### 에러 코드
| 코드 | 의미 | 예 |
|---|---|---|
| `400` | 요청 값이 잘못됨 | `radius_km`가 20 초과 · 인증코드 불일치 |
| `401` | 토큰 없음·만료·위조 | 로그인 필요한 API에 토큰 없이 접근 |
| `403` | 인증은 됐지만 자격 미달 | 이메일 인증 없이 회원가입 시도 |
| `404` | 대상 없음 | 존재하지 않는 `content_id` |
| `409` | 이미 존재해서 충돌 | 가입된 이메일로 재가입 · 소셜 계정 이메일과 중복 |
| `422` | 형식 오류 (FastAPI 자동) | 숫자 자리에 문자열 · 비밀번호 규칙 미달 |
| `429` | 너무 잦은 요청 | 인증코드 재발송 쿨다운 · 코드 5회 오입력 |
| `502` | 외부 API 실패 | TourAPI·구글·카카오 서버 장애 |

> `401`은 **토큰 문제**, `403`은 **토큰은 멀쩡한데 조건 미달**입니다. 앱 대응이 다릅니다 —
> `401`은 refresh/재로그인, `403`은 그 화면에서 안내 문구.

---

## 2. 인증 (3단계) — 회원가입 · 로그인 · 로그아웃

> **2026-08-22 변경**: 소셜 전용에서 **소셜 + 일반 회원가입(이메일·비밀번호)** 으로 확장했고,
> 토큰을 **access + refresh 2개**로 나눴습니다. 아래가 최신입니다. 담당: 김은서

### 2.0 토큰 두 개를 어떻게 다루나 (프론트 필독)

| | access_token | refresh_token |
|---|---|---|
| 어디에 쓰나 | **모든 API 호출**의 `Authorization: Bearer <값>` 헤더 | 오직 `POST /auth/refresh` 본문 |
| 수명 | **1시간** | **30일** |
| 만료되면 | `/auth/refresh`로 새로 받는다 | 다시 로그인해야 한다 |

**앱이 해야 할 일 3가지**

1. 로그인 응답의 **두 토큰을 안전한 저장소에 저장**합니다.
   (안드로이드 `EncryptedSharedPreferences` / iOS Keychain / RN `react-native-keychain`.
   일반 SharedPreferences·AsyncStorage는 평문이라 피해주세요.)
2. **API가 `401`을 주면** → `POST /auth/refresh` 호출 → 새 토큰으로 교체 → **원래 요청 재시도**.
   `/auth/refresh`마저 `401`이면 저장된 토큰을 지우고 로그인 화면으로 보냅니다.
3. `/auth/refresh` 응답에는 **새 refresh_token도 함께 옵니다. 반드시 교체 저장하세요.**
   ⚠️ 옛 refresh를 다시 쓰면 서버가 **토큰 탈취로 간주해 그 계정의 모든 세션을 끊습니다.**

> HTTP 클라이언트의 인터셉터(Retrofit `Authenticator` / axios interceptor / dio interceptor)에
> 2번을 한 번만 심어두면 화면 코드는 토큰을 신경 쓸 필요가 없습니다.

**공통 성공 응답** (로그인·소셜·재발급이 같은 모양)
```jsonc
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "Yx7q3f...",          // 48바이트 난수. JWT 아님
  "token_type": "bearer",
  "expires_in": 3600,                     // access_token 남은 초
  "user": {
    "user_id": 1,
    "nickname": "은서",
    "auth_provider": "local",             // local | google | kakao
    "email": "eunseo@example.com",        // ? 카카오는 null일 수 있음
    "email_verified": true,
    "created_at": "2026-08-22T07:48:43Z"
  }
}
```

---

### 2.1 일반 회원가입 — **3번 호출**입니다

이메일 인증이 있어서 화면이 3개로 나뉩니다.

```
[이메일 입력]  POST /auth/email/send-code   → 메일로 6자리 코드 발송
      ↓
[코드 입력]    POST /auth/email/verify-code → 통과 (이후 30분 안에 가입 완료해야 함)
      ↓
[비번·닉네임]  POST /auth/signup            → 계정 생성(이후 로그인 필요)
```

#### `POST /auth/email/send-code`
```jsonc
// 요청
{ "email": "eunseo@example.com" }
// 응답 200
{ "expires_in": 600, "dev_code": "862986" }
```
- `expires_in`: 코드 유효시간(초). 화면에 카운트다운을 띄우면 됩니다.
- ⚠️ **`dev_code`는 개발용입니다.** 서버에 메일 계정이 아직 없어서 코드를 그대로 돌려줍니다.
  메일 발송을 켜면 **항상 `null`** 이 되니, 앱은 이 값을 화면에 쓰지 마세요(디버그 로그까지만).
- `409` 이미 가입된 이메일 — `detail`에 **어느 경로로 가입했는지** 담깁니다
  (예: `"이미 구글 계정으로 가입된 이메일입니다. 구글 로그인을 이용해 주세요."`) → 그대로 노출 가능
- `429` 재발송 쿨다운(60초) — 재발송 버튼은 60초 비활성화해 주세요

#### `POST /auth/email/verify-code`
```jsonc
// 요청
{ "email": "eunseo@example.com", "code": "862986" }
// 응답 200
{ "verified": true, "signup_deadline_minutes": 30 }
```
- `400` 코드 불일치·만료, 또는 코드를 요청한 적 없음
- `429` **5회 틀리면 잠깁니다** → 코드를 새로 받아야 합니다. 안내 문구를 띄워주세요

#### `POST /auth/signup`
```jsonc
// 요청
{ "email": "eunseo@example.com", "password": "ktour1234", "nickname": "은서" }
// 응답 201
{ "message": "회원가입이 완료되었습니다.", "user": { ... } }
```
- **비밀번호 규칙: 8자 이상 72바이트 이하, 영문+숫자 필수.** 위반 시 `422`
  (앱에서 미리 검사해 주면 사용자 경험이 좋습니다)
- 닉네임 2~20자
- `403` 이메일 인증을 안 했거나 인증 후 30분이 지남 → 코드 재발송부터 다시
- `409` 이미 가입된 이메일

### 2.2 `POST /auth/login` — 일반 로그인
```jsonc
// 요청
{ "email": "eunseo@example.com", "password": "ktour1234",
  "device_id": "android_550e8400-e29b-41d4-a716-446655440000" }
// 응답 200 → §2.0 공통 성공 응답
```
- 이메일은 **대소문자를 구분하지 않습니다** (`Kim@x.com` = `kim@x.com`)
- `401` `"이메일 또는 비밀번호가 올바르지 않습니다."`
  — **계정 없음과 비밀번호 틀림을 구분해 주지 않습니다**(가입 여부를 캐내지 못하게).
  앱에서도 "없는 계정입니다" 같은 추측 문구를 만들지 마세요.
- `409` 그 이메일은 소셜로 가입돼 있음 → `detail` 문구를 그대로 보여주면 됩니다
- `device_id`는 8~128자의 영문·숫자·`_`·`-`·`.`·`:` 조합이며, 누락·형식 오류는 `422`

### 2.3 소셜 로그인 (간편로그인)

앱이 SDK로 받은 토큰을 넘기면 서버가 구글·카카오에 되물어 검증합니다. **처음이면 자동 가입**됩니다.

> **담당 분담 (2026-08-22)** — 카카오는 지도 API 때문에 개발자센터 앱을 이미 만들어 둔
> **윤영**이 콘솔·앱 SDK·서버 엔드포인트까지 맡기로 했습니다. 구글은 **김은서**가 담당합니다.
>
> | | 서버 상태 | 담당 |
> |---|---|---|
> | `POST /auth/google` | ✅ **구현·동작 중** | 김은서 |
> | `POST /auth/kakao` | ✅ **구현됨** | 윤영 |
>
> ⚠️ **요청·응답 형태는 아래대로 이미 확정된 계약입니다.** 카카오를 구현할 때 이 모양을
> 그대로 지켜주세요. 프론트가 두 버튼을 같은 코드로 처리할 수 있어야 합니다.

```jsonc
// POST /auth/google   ✅ 동작 중
{ "id_token": "eyJhbGciOi...", "device_id": "android_..." }
// POST /auth/kakao    ✅ 구현됨
{ "access_token": "abcd1234...", "device_id": "android_..." }
```
⚠️ **필드 이름이 서로 다릅니다.** 구글은 정보가 담긴 서명된 JWT(`id_token`)를 주고,
카카오는 정보가 없는 불투명 토큰(`access_token`)을 줍니다. 실수가 아니라 제공자 차이입니다.

- 응답 `200` → §2.0 공통 성공 응답 (**두 제공자가 완전히 같은 모양**)
- `401` 토큰이 위조·만료됐거나 **다른 앱용 토큰**
- `409` 그 소셜 계정의 이메일이 이미 다른 경로로 가입돼 있음
- `502` 구글·카카오 서버 연결 실패 → **로그아웃시키지 말고 재시도**를 안내하세요

> 📌 **카카오는 `user.email`이 `null`일 수 있습니다.** 이메일이 선택 동의 항목이라서 정상입니다.
> 이메일을 화면에 꼭 띄워야 한다면 null 처리를 준비해 주세요.

### 2.4 `POST /auth/refresh` — access 재발급
```jsonc
// 요청
{ "refresh_token": "Yx7q3f...", "device_id": "android_..." }
// 응답 200 → §2.0 공통 성공 응답 (access·refresh 둘 다 새것)
```
- `401` refresh가 없음·만료·**이미 사용됨** → 저장된 토큰 전부 지우고 로그인 화면으로
- ⚠️ 위 §2.0 3번 참고 — **새 refresh로 교체 저장**이 필수입니다

### 2.5 `POST /auth/logout` — 로그아웃
```jsonc
// 요청
{ "refresh_token": "Yx7q3f..." }
// 응답 200
{ "message": "로그아웃되었습니다." }
```
- **항상 `200`입니다**(이미 로그아웃된 상태여도). 앱은 응답을 기다리지 말고 바로 토큰을 지워도 됩니다.
- 서버에서 그 refresh를 폐기하므로 재발급이 막힙니다. 남은 access는 최대 1시간 더 유효합니다.

### 2.6 `POST /auth/logout-all` 🔒 — 모든 기기 로그아웃
헤더에 access_token 필요. 본문 없음. "폰을 잃어버렸어요" 대응용입니다.
```jsonc
// 응답 200
{ "message": "3개 기기에서 로그아웃되었습니다." }
```

### 2.7 `GET /auth/me` 🔒 — 내 정보
```jsonc
{ "user_id": 1, "nickname": "은서", "auth_provider": "local",
  "email": "eunseo@example.com", "email_verified": true,
  "created_at": "2026-08-22T07:48:43Z" }
```
앱 시작 시 저장된 토큰이 아직 쓸 만한지 확인하는 용도로도 씁니다.

### 2.8 인증이 필요한 API (🔒)
`Authorization: Bearer <access_token>` 헤더를 붙입니다. 없거나 위조·만료면 `401`.
현재 🔒 대상: `/auth/me` · `/auth/logout-all` · (6단계) 코스 저장·조회·삭제.

---

## 3. 검색 · 리졸브 (5단계)

### `GET /contents/search?q=기생충` — 작품 검색
사용자가 검색창에 입력했을 때. 부분일치.

**응답 `200`**
```jsonc
{
  "items": [
    {
      "product_id": 139,
      "title": "기생충",
      "first_air_date": "2019-05-30",
      "category": "MOVIE",                 // MOVIE | DRAMA, DB 값 그대로
      "product_type": null,                // 드라마 상세의 작품유형
      "genres": "코미디|스릴러|드라마",       // ?
      "poster_url": "https://image.tmdb.org/t/p/w185/jjHccoFjbqlfr4VGLVLT7yek0Xn.jpg",  // ? null 가능(18%)
      "rating": 8.5,                        // ? 0.0~10.0
      "place_count": 28                     // 이 작품의 촬영지 수
    }
  ],
  "total": 1
}
```

> ⚠️ **부분일치라 엉뚱한 게 섞입니다.** `q=기생` 으로 검색하면 「기생충」과 「음란 기생」이 함께 나옵니다.
> 정렬은 백엔드가 관련도순으로 처리하지만, 화면에서도 **연도·포스터를 함께 보여줘 사용자가 구분**하게 해주세요.

### `POST /contents/resolve` — 작품명 → 후보 (**AI 전용**)
조시현 님 챗봇이 자연어에서 뽑은 제목 문자열을 `product_id`로 바꾸는 용도.

**요청**
```jsonc
{ "query": "만추" }
```

**응답 `200`**
```jsonc
{
  "candidates": [
    { "product_id": 1115, "title": "만추", "first_air_date": "1981-11-13", "category": "MOVIE",
      "poster_url": "https://image.tmdb.org/t/p/w185/...", "score": 1.0 },
    { "product_id": 499, "title": "만추", "first_air_date": "1966-11-25", "category": "MOVIE",
      "poster_url": "https://image.tmdb.org/t/p/w185/...", "score": 1.0 }
  ]
}
```
- **`candidates`는 항상 배열이며 0개·2개 이상일 수 있습니다.** 동명 작품이 실제로 존재합니다.
- `score`는 0.0~1.0 관련도. 내림차순 정렬.
- 후보가 2개 이상이면 **목록 UI로 넘겨 사용자가 고르게 합니다**(§0.5). 대화로 확인하고 싶다면 연도를 인용하세요.
- 후보가 0개면 `candidates: []` — 에러가 아닙니다.

### `GET /regions/resolve?name=중구` — 지역명 → 후보 (**AI 전용**)

**응답 `200`**
```jsonc
{
  "candidates": [
    { "region_id": 164, "name": "중구", "full_name": "서울특별시 중구",
      "level": "sigungu", "centroid": {"lat": 37.5638, "lng": 126.9975} },
    { "region_id": 139, "name": "중구", "full_name": "부산광역시 중구",
      "level": "sigungu", "centroid": {"lat": 35.1041, "lng": 129.0323} }
    // … 대구·대전·울산·인천 중구까지 총 6개
  ]
}
```
- ⚠️ **「중구」는 6곳, 「남구」는 5곳입니다.** 반드시 후보 처리를 하세요.
- `full_name`은 사용자에게 되물을 때 그대로 쓰라고 넣은 필드입니다.
- 애매하지 않게 하려면 AI가 처음부터 `name=서울 중구` 처럼 시도를 붙여 보내면 후보가 1개로 좁혀집니다.

### `GET /regions` — 지역 목록 (선택 UI용)
**응답 `200`**
```jsonc
{
  "items": [
    { "region_id": 9, "name": "서울특별시", "level": "sido", "parent_region_id": null,
      "centroid": {"lat": 37.5466, "lng": 126.9879},
      "children": [ { "region_id": 164, "name": "중구", "level": "sigungu" } ] }
  ],
  "total": 17
}
```
- 지역은 **시도(17) → 시군구(227)** 2단계입니다.
- `?flat=true`를 주면 `children` 없이 244개를 평평하게 돌려줍니다.

---

## 4. 작품 · 촬영지 (5단계)

### `GET /contents/{product_id}` — 작품 상세
**응답 `200`**
```jsonc
{
  "product_id": 139,
  "title": "기생충",
  "first_air_date": "2019-05-30",       // ? 영화도 이 필드가 개봉일
  "category": "MOVIE",
  "genres": "코미디|스릴러|드라마",      // ?
  "overview": "전원백수로 살 길 막막하지만 사이는 좋은 기택네 가족...",  // ?
  "poster_url": "https://image.tmdb.org/t/p/w185/jjHcc...jpg",       // ?
  "rating": 8.5,                       // ?
  "popularity": 10.5,                  // ?
  "runtime": 131,                      // ? 분 단위. 영화 응답에만 포함
  "place_count": 28,
  "filming_location_count": 2,
  "filming_locations": [
    {
      "place_id": 101,
      "tour_content_id": "126508",
      "name": "촬영지 이름",
      "sido_name": "서울특별시",
      "sigungu_name": "종로구",
      "detail_path": "/places/101"
    }
  ],
  "related_products": [
    {
      "product_id": 499,
      "title": "연관 작품",
      "category": "MOVIE",
      "poster_url": "https://image.tmdb.org/t/p/w185/example.jpg",
      "detail_path": "/contents/499"
    }
  ]
}
```
- `filming_locations`는 TourAPI 관광지와 매칭되어 `tour_content_id`가 확인된 해당 작품의 촬영지를 모두 반환한다.
- `related_products`는 공통 장르가 있는 작품을 별점 내림차순으로 최대 6개 반환한다. 동점이면 장르 유사도와 인기도 순으로 정렬한다.
- 화면에서는 각 항목의 `detail_path`를 사용해 장소 또는 작품 상세로 이동한다.
- 없는 `product_id`면 `404`. `tmdb_id`는 DB와 응답에서 제거했다.
- `category`는 `products.category`의 `MOVIE` 또는 `DRAMA`를 그대로 반환한다.
- 영화: 위 공통 필드와 `movie_details.runtime`을 반환한다.
- 드라마: 공통 필드와 다음 전용 필드를 반환하며 `runtime`은 포함하지 않는다.

| 드라마 응답 필드 | drama_details 컬럼 | 타입 |
|---|---|---|
| is_overview_translated | overview_translated | boolean 또는 null |
| product_type | content_type | string 또는 null |
| networks | networks | string 또는 null |
| episode_count | episode_count | integer 또는 null |
| lead_actors | cast | `배우1\|배우2` 문자열 또는 null |

장소 상세 및 지도 응답의 `contents` 항목은 다음 구조다. 클릭 시 `detail_path`로 요청한다.
ID는 `products.product_id`이며 두 상세 테이블의 PK/FK도 같은 값이다.

```json
{
  "product_id": 139,
  "title": "기생충",
  "category": "MOVIE",
  "poster_url": "https://example.com/poster.jpg",
  "detail_path": "/contents/139"
}
```

## 5. 지역 · 지도 (5단계)

### `GET /regions/{region_id}/places` — 지역 내 촬영지
**응답**: 지역 내 촬영지 `items`와 각 장소에 연결된 `contents` 배열을 반환합니다.

**요청 파라미터**

| 이름 | 필수 | 설명 |
|---|---|---|
| `content_id` | | **작품으로 좁히기.** 유저플로우 4번 "지도에서 영화 하나 선택"에 해당 — 강릉 지도에서 「관상」을 탭하면 `?content_id=559` 로 재요청하면 강릉 안의 관상 촬영지만 남는다 |
| `sort` | | `popular`(기본) = **촬영 횟수 많은 순** · `name` = 가나다순 |
| `limit` / `offset` | | 페이지네이션 |

> 💡 같은 화면에서 **필터 전/후가 같은 응답 구조**입니다. 파라미터만 붙였다 뗐다 하면 되고
> 화면 코드를 두 벌 만들 필요가 없습니다.

> ⚠️ **촬영지가 몰린 지역이 있습니다** — 강남구 473곳 · 마포구 399 · 종로구 399 · 중구 263 · 용산구 227.
> 전체 228개 시군구의 중앙값은 23곳이라 대부분은 한산하지만, 위 지역은 마커를 그대로 뿌리면 안 됩니다.
> **마커 클러스터링을 넣어주세요.**
>
> 목록은 서버가 **대표 촬영지부터** 정렬해 보냅니다. 앞 20개만 받아도 의미 있는 목록이 됩니다.
> ```
> 종로구 popular → 경복궁(10편) · 경희궁(9편) · 낙산공원(9편) · 창덕궁(8편) · 청계천(8편)
> 종로구 name    → 달 · 누리 · 동조 · 모색 · 미크        ← 한 글자 가게들. 쓰지 마세요
> ```
> `contents` 배열 길이가 곧 그 장소의 촬영 편수라 "5개 작품 촬영" 배지로 쓸 수 있습니다.
> (단 `content_id` 필터를 걸면 그 작품만 남으므로 길이가 1이 됩니다.)

```jsonc
{
  "items": [
    {
      "place_id": 2193,
      "name": "강릉선교장",
      "location": {"lat": 37.7865394, "lng": 128.8851189},
      "address": "강원도 강릉시 운정동 431",
      "region": {"region_id": 18, "name": "강릉시", "full_name": "강원도 강릉시"},
      "contents": [                       // ★ 이 장소에서 촬영된 작품들 (지도 포스터 마커용)
        { "product_id": 559, "title": "관상", "category": "MOVIE",
          "poster_url": "https://image.tmdb.org/t/p/w185/...", "detail_path": "/contents/559" }
        // 강릉선교장에는 실제로 5개 작품이 붙는다(관상·식객·인사동 스캔들 등)
      ]
    }
  ],
  "total": 42
}
```
- 한 장소에 **여러 작품이 붙습니다** (강릉선교장은 5개 작품). 마커 하나에 포스터 여러 장을 처리해주세요.

### `GET /places?near={region_id}&radius_km=5` — 반경 내 촬영지
**요청 파라미터**

| 이름 | 필수 | 설명 |
|---|---|---|
| `near` | ✅ | 중심이 될 `region_id`. 그 지역의 중심점 기준 |
| `radius_km` | | 기본 5, **최대 20**. 초과 시 `400` |
| `limit` / `offset` | | 페이지네이션 |

**응답**: 위와 같은 구조 + 각 항목에 `distance_km`(소수 2자리) 추가. 가까운 순 정렬.

> ⚠️ **좌표(GPS)를 직접 보내는 파라미터는 제공하지 않습니다.** 공모전 규정상 사용자 위치를 서버가 받으면
> 위치기반서비스 사업자 등록이 필요해집니다. **"내 주변" 기능은 앱이 GPS로 가장 가까운 `region_id`를
> 스스로 고른 뒤 그 id를 보내는 방식**으로 구현해주세요.

---

## 6. 장소 상세 — TourAPI 실시간 (4단계) ⚠️합격 핵심

### `GET /places/{place_id}`
우리 데이터 + **한국관광공사 TourAPI 실시간 조회 결과**를 합쳐 돌려줍니다.

**응답 `200`**
```jsonc
{
  "place_id": 48,
  "name": "전주영화종합촬영소",
  "location": {"lat": 35.8144357, "lng": 127.0758878},
  "address": "전라북도 전주시 완산구 상림동 538",
  "region": {"region_id": 214, "name": "전주시", "full_name": "전라북도 전주시"},
  "contents": [ { "product_id": 139, "title": "기생충", "poster_url": "https://...",
                  "category": "MOVIE", "detail_path": "/contents/139" } ],

  "detail": {                       // ★ TourAPI 실시간. null일 수 있음(아래 주의)
    "tour_content_id": "126508",
    "title": "전주영화종합촬영소",
    "overview": "전주영화종합촬영소는 ...",
    "tel": "063-286-0421",
    "homepage": "http://...",
    "use_time": "09:00~18:00",
    "rest_date": "매주 월요일",
    "images": [ "http://tong.visitkorea.or.kr/cms/resource/....jpg" ]
  }
}
```

**`detail`에 대한 중요한 약속**
- **`detail`은 `null`일 수 있습니다.** 촬영지 중 상당수(개인 상점·주택가·도로)는 관광공사에 등록된 관광지가 아닙니다. → **"상세정보 없음" UI를 반드시 준비**하세요.
- **매 요청마다 실시간 호출**합니다. 공모전 규정상 응답을 저장(캐싱)할 수 없어서, 이 API만 응답이 **느립니다(수백 ms~수 초)**. 로딩 표시를 넣어주세요.
- 이미지는 **URL만** 옵니다. 서버가 파일을 내려주지 않습니다(규정).
- TourAPI 장애·할당량 초과 시 `502`. 이때도 우리 데이터(이름·좌표·작품)는 살아 있으니, **`detail`만 빼고 화면을 그리는 fallback**을 권장합니다.

---

## 7. 코스 (6단계)

### `POST /courses/recommend` — 최적 방문순서 (**저장 안 함, 인증 불필요**)
사용자가 고른 촬영지들을 효율적인 동선으로 정렬해서 돌려줍니다.

**요청**
```jsonc
{
  "place_ids": [48, 176, 205],
  "start_place_id": 176,      // ? 출발지 고정. 없으면 백엔드가 알아서
  "options": { "transport": "car" }   // ? car | transit | walk
}
```

**응답 `200`**
```jsonc
{
  "order": [
    { "visit_order": 1, "place_id": 176, "name": "서울종로경찰서 112상황실",
      "location": {"lat": 37.5756879, "lng": 126.984804} },
    { "visit_order": 2, "place_id": 205, "name": "팀PC",
      "location": {"lat": 35.7881889, "lng": 127.1364021} }
  ],
  "legs": [ { "from_place_id": 176, "to_place_id": 205, "distance_km": 201.3, "duration_min": 145 } ],
  "total_distance_km": 213.7,
  "total_duration_min": 158
}
```
- ⚠️ **`place_ids`로만 받습니다.** 좌표를 직접 보내지 마세요(6-1과 같은 이유).
- `duration_min`은 추정치입니다.

### 코스 저장/조회 🔒
| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| `POST /courses` | `{"title": "기생충 투어", "place_ids": [176, 205, 48]}` | `201` + 저장된 코스 |
| `GET /courses` | — | `{"items": [...], "total": n}` 내 코스 목록 |
| `GET /courses/{course_id}` | — | 코스 상세(경유지 포함) |
| `DELETE /courses/{course_id}` | — | `204` |

**코스 상세 응답**
```jsonc
{
  "course_id": 7,
  "title": "기생충 투어",
  "created_at": "2026-08-15T06:12:00Z",
  "places": [
    { "visit_order": 1, "place_id": 176, "name": "서울종로경찰서 112상황실",
      "location": {"lat": 37.5756879, "lng": 126.984804}, "poster_url": "https://..." }
  ]
}
```
- 남의 코스에 접근하면 `404`(존재 여부를 숨기기 위해 403이 아닌 404).

---

## 8. 역할별 요약

### 🤖 조시현 (AI) — 쓸 API는 3개뿐
```
1. POST /contents/resolve   "도깨비 촬영지 알려줘" → 제목 추출 → content_id
2. GET  /regions/resolve    "강릉 쪽으로"        → 지역명 추출 → region_id
3. POST /courses/recommend  place_id 목록        → 최적 동선
```
**꼭 지켜주세요**
- 두 리졸브 모두 **후보 배열**을 돌려줍니다. 1개라고 가정하지 마세요 (중구 6곳, 만추 2편).
- 후보가 여러 개일 때는 **말로 되물을 필요 없이 목록 UI로 넘기면 됩니다** (유저플로우 3·4가 목록 출력이므로).
  대화로 확인하고 싶다면 `full_name`·`production_year`를 그대로 인용하면 자연스럽습니다.
- 후보 0개도 정상 응답입니다(`candidates: []`). 에러로 처리하지 마세요.
- 위치는 **`place_id`/`region_id` 정수**로만 주고받습니다. 좌표·주소 문자열을 보내지 마세요.

### 📱 윤영 (FE) — 화면 만들기 전 체크리스트
- [ ] 포스터 **기본 이미지** 준비 (`poster_url`이 null인 작품 296편)
- [ ] 작품 목록에 **연도 표시** (동명 작품 존재)
- [ ] 촬영지 상세의 `scene_description` **없을 때 영역 접기** (75%가 빔)
- [ ] `GET /places/{id}`의 **`detail`이 null일 때 "상세정보 없음"** UI
- [ ] `GET /places/{id}`는 **느립니다** → 로딩 인디케이터
- [ ] "내 주변"은 앱이 GPS로 `region_id`를 고른 뒤 그 id를 전송 (좌표 직접 전송 불가)
- [ ] 지도 마커 하나에 **작품 여러 개**가 붙을 수 있음 (강릉선교장 = 5작품)
- [ ] 로그인 화면 **3종**: 카카오 · 구글 · 이메일(회원가입 포함) — §2 참고
- [ ] 회원가입은 **3화면**(이메일 → 인증코드 → 비번·닉네임). 인증코드 카운트다운·재발송(60초) 필요
- [ ] 토큰 **2개**를 안전 저장소에 보관 + `401` 시 `/auth/refresh` 후 재시도하는 인터셉터 1개
- [ ] `/auth/refresh` 응답의 **새 refresh_token으로 교체 저장** (안 하면 전체 세션이 끊김)
- [ ] 카카오 로그인은 `user.email`이 **null일 수 있음** (선택 동의 항목)

---

## 9. 구현 상태

| 구분 | 상태 |
|---|---|
| `GET /health`, `GET /` | ✅ 동작 중 |
| 인증 9종 (회원가입·로그인·구글·refresh·로그아웃) | ✅ **동작 중** (2026-08-22) |
| `POST /auth/kakao` | ⬜ **윤영 담당** — 서버 자리만 마련됨 |
| 검색·리졸브 4종 | ✅ **동작 중** (2026-08-15) |
| 작품·촬영지 2종 | ✅ **동작 중** (2026-08-15) |
| 지역·지도 2종 | ✅ **동작 중** (2026-08-15) |
| `GET /places/{id}` (TourAPI) | ✅ **동작 중** (2026-08-16) |
| 코스 5종 | ⬜ 6단계 |

**엔드포인트 18종이 실제로 붙었습니다.** 서버를 띄우면 바로 호출할 수 있고,
자동 문서는 http://127.0.0.1:8000/docs 에서 확인할 수 있습니다.
(/docs 우측 상단 **Authorize** 버튼에 access_token을 넣으면 🔒 API도 브라우저에서 테스트됩니다.)

> 🔔 **윤영 님 — 인증 관련 지금 바로 개발 가능**
> 서버에 아직 메일 계정이 없어서 `/auth/email/send-code` 응답의 **`dev_code`에 인증코드가
> 그대로 담겨 옵니다.** 그 값으로 `verify-code`를 호출하면 메일함 없이 가입 흐름 전체를
> 붙여볼 수 있습니다. 메일 발송을 켜면 `dev_code`는 `null`이 되니 **화면 로직이 이 값에
> 의존하지 않게** 해주세요.
> 소셜 로그인은 **구글은 서버 검증이 끝났고**, 앱에 SDK를 붙여 받은 `id_token`만 넘겨주면 됩니다.
> **카카오는 윤영 님이 서버 엔드포인트까지 맡기로 해서 아직 없습니다**(§2.3 참고).

> 🔔 **윤영 님 — `GET /places/{id}` 관련 실측 안내**
> - `detail`이 **null인 경우가 흔합니다.** 실측 16곳 중 5곳이 null이었고, 방송사 사옥·촬영
>   스튜디오·세트장·병원처럼 **애초에 관광지가 아닌 촬영지**가 원인입니다. "상세정보 없음"은
>   예외 화면이 아니라 **일반 화면**으로 준비해 주세요.
> - **느립니다.** 실시간 호출이라 매칭된 장소도 300ms 내외, 처음 여는 장소는 1초를 넘길 수
>   있습니다. 로딩 인디케이터가 필요합니다.
> - `detail.images`는 **URL 배열**입니다(빈 배열일 수 있음). 예: 강릉선교장 4장.
> - 바로 써볼 수 있는 실제 값: `GET /places/2193`(강릉선교장, detail 있음) ·
>   `GET /places/230`(남양주종합촬영소, detail null).

```powershell
docker start ktour-db
uvicorn app.main:app --reload
```

검증된 실제 응답 (2026-08-15)
- `q=기생충` → 기생충(2019), 촬영지 28곳
- `q=기생` → 기생충(28곳) · 음란 기생(1곳) — 관련도순 정렬 확인
- `resolve("만추")` → 1981·1966 두 후보
- `resolve("중구")` → **6개 후보** / `resolve("서울 중구")` → **1개로 좁혀짐**
- 강릉시 촬영지 70곳 → `?content_id=559`(관상) 필터 → **1곳(강릉선교장)**
- 강릉 중심 반경 5km → 44곳, 가까운 순 `distance_km` 부여

아직 붙지 않은 4·6단계는 위 JSON 예시를 목(mock)으로 쓰세요.

---

## 10. 변경 이력
| 날짜 | 내용 |
|---|---|
| 2026-08-15 | v1 최초 작성. 실데이터 적재 후 실제 값 기준으로 확정 |
| 2026-08-22 | **§2.3 소셜 담당 분담** — 카카오는 윤영(콘솔·앱·서버), 구글은 김은서.<br>`POST /auth/kakao`는 **아직 없습니다.** 요청·응답 계약은 확정돼 있으니 구현 시 그대로 지켜주세요 |
| 2026-08-22 | **§2 인증 전면 개정** (김은서). ⚠️ 아래 3가지가 기존 계약과 다릅니다.<br>① **일반 회원가입 추가** — 소셜 전용이 아니게 됨. 이메일 인증(6자리 코드) 포함<br>② **토큰이 2개로 분리** — access 1시간 + refresh 30일. 기존 "14일짜리 토큰 1개"는 폐기<br>③ **로그아웃 API 신설** — 서버에서 실제로 무효화됨<br>§1 에러 코드에 `403`·`409`·`429` 추가 |

> 계약 변경이 필요하면 이 표에 기록하고 팀에 공유합니다. **말 없이 필드를 바꾸지 않습니다.**
# 지역 관광지 지도·하단 목록 API

`GET /regions/{region_id}/tourism-places?page=1&size=20`

지역 선택 API에서 받은 `region_id`를 전달한다. `page`는 1 이상,
`size`는 1~100이며 기본값은 20이다. 국문관광정보 `areaBasedList2`를
매 요청 호출하며 현재 대상은 관광지(`contentTypeId=12`)다.

```json
{
  "items": [{
    "content_id": "123456",
    "name": "관광지 이름",
    "image_url": "https://example.com/main.jpg",
    "thumbnail_url": "https://example.com/thumb.jpg",
    "location": {"lat": 37.58, "lng": 126.98},
    "sido_code": "11",
    "sigungu_code": "110",
    "sido_name": "서울특별시",
    "sigungu_name": "종로구",
    "category": "촬영지",
    "place_ids": [7, 15]
  }],
  "total": 45,
  "count": 1,
  "page": 1,
  "size": 20,
  "has_next": true
}
```

위 응답은 필드 설명용 예시다. `total`은 TourAPI의 `totalCount`로 선택 지역의
전체 관광지 수이고, `count`는 현재 응답 항목 수다. 다음 페이지는 `page+1`로
요청한다. 지도와 하단 목록은 같은 `items`를 사용하며 전체 지도 표시가 필요하면
`has_next`가 false가 될 때까지 페이지를 추가로 조회한다.

`sido_code`와 `sigungu_code`는 법정동 시도 2자리와 시군구 3자리 코드다.
기존 TourAPI `areaCode`/`sigunguCode` 코드 체계와 다르다. `regions.bjd_cd`와
연결하여 지역명을 제공한다. 이미지는 없으면 null이고, 좌표가 없거나 유효하지
않으면 `location=null`이므로 해당 항목은 목록에만 표시한다.

`category`는 `촬영지` 또는 `관광지`다. `places.tour_content_id` 일치를 우선하고,
연결 ID가 없는 데이터는 공백·문장부호를 제거한 장소명이 같고 좌표가 200m 이내인
경우 촬영지로 분류한다. 좌표가 없는 경우에는 같은 이름과 동일 주소를 요구한다.
이름 표기가 다르면 매칭되지 않을 수 있다. 한 촬영지에 CSV 행이 여러 개 있으면
해당 `place_ids`를 모두 반환하며 관광지 목록 항목은 늘어나지 않는다.

`GET /tourism-places/{content_id}`

마커 또는 목록 클릭 시 목록에서 받은 **TourAPI content_id**를 전달한다.
기존 작품 `contents.content_id`나 DB `places.place_id`가 아니다.
`detailCommon2`와 `detailImage2`를 실시간 호출한다.

```json
{
  "content_id": "123456",
  "name": "관광지 이름",
  "overview": "관광지 소개 및 설명",
  "homepage": "https://example.com",
  "tel": "02-123-4567",
  "address": "서울특별시 종로구 ...",
  "address_detail": null,
  "images": ["https://example.com/original.jpg"]
  ,"related_places": [{
    "related_id": "related-1",
    "content_id": "456",
    "name": "연관 관광지",
    "sido_name": "서울특별시",
    "sigungu_name": "종로구",
    "detail_path": "/tourism-places/456"
  }]
}
```

홈페이지는 앵커 태그에서 URL을 추출하고 소개는 HTML 태그를 제거한다.
이미지는 `originimgurl`의 중복 없는 URL 목록이며 이미지 페이지 전체를 조회한다.
정보가 없는 선택 필드는 null, 이미지가 없으면 빈 배열이다.
지역/상세가 없으면 404, 잘못된 페이지·ID는 422, 외부 API 실패(이미지 조회 포함)는
502를 반환한다. 응답 본문은 DB에 저장하지 않으며 호출 메타데이터만 기록한다.
