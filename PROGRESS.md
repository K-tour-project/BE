# K-tour BE — 진행 현황 (한눈에 보기)

> **앱**: 영화 촬영지 기반 관광 코스 앱(Every Trip) / **공모전 1차 마감 2026-09-21(월) 16:00**
> 문서 안내 — **전체 경과 요약: [`DEV_SUMMARY.md`](./DEV_SUMMARY.md)** · 로드맵·결정: [`PROJECT_REPORT.md`](./PROJECT_REPORT.md) · 상세 구현일지: [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md) · 구조 설명: [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) · ERD: [`erd.dbml`](./erd.dbml) · 본 문서: 단계별 현황 스냅샷.

## 전체 로드맵
| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 설계(v3 FastAPI 확정) | ✅ |
| 1 | 프로젝트 뼈대 + `/health` | ✅ |
| 2 | DB 연결 + Alembic + 모델(최소 7테이블) | ✅ |
| **2.5** | **스키마 확장 + 실데이터 적재(CSV 13,761행)** | ✅ **완료 (2026-08-15)** |
| **3** | **회원가입/로그인/로그아웃 (일반 + 구글)** | ✅ **완료 (2026-08-22)** |
| **4** | **place-detail (TourAPI 실시간 + `api_call_logs` 입증)** ⚠️합격핵심 | ✅ **완료 (2026-08-16)** |
| **5** | **검색·지도 엔드포인트 (8종)** | ✅ **완료 (2026-08-15)** |
| 6 | 코스 추천 엔진 | ⬜ |
| 7 | AI(팀원 챗봇) 인터페이스 | ⬜ |
| 8 | 테스트·컴플라이언스 하드닝 | ⬜ |
| 9 | 배포·제출 준비 | ⬜ |

## 2.5단계 세부 진행 (완료 ✅)
| # | 작업 | 상태 |
|---|---|---|
| 2.5-1 | `data/data.csv` 위치 정리 + 데이터 프로파일링(무결성 검증) | ✅ |
| 2.5-2 | 모델 확장 — regions 계층 / contents·places·mappings 컬럼 | ✅ |
| 2.5-3 | 마이그레이션 `c4d4fdb425b1` 생성·검토·적용 | ✅ |
| 2.5-4 | 시드 스크립트 [`scripts/seed_from_csv.py`](./scripts/seed_from_csv.py) (재실행 안전) | ✅ |
| 2.5-5 | 적재 실행 + 유저플로우 쿼리·인덱스·재실행 검증 | ✅ |

## 확정된 설계 결정 (2026-08-15)
| # | 항목 | 결정 |
|---|---|---|
| 1 | 로그인 방식 | ~~소셜 전용~~ → **2026-08-22 변경: 소셜(구글·카카오) + 일반 회원가입(이메일+비번, 이메일 인증)** |
| 2 | 코스 기능 | **유지** — courses·course_places 그대로, 6단계에서 추천 구현 |
| 3 | 장르 저장 | **배열 컬럼** `contents.genre_tags` (+ GIN 인덱스) |
| 4 | 데이터 출처 | **CSV를 우리 DB로**, 장소 상세(운영시간·이미지)는 **TourAPI 실시간** |
| 5 | 드라마 | 1차는 **영화만**. 드라마는 나중에 **INSERT만으로** 추가 가능하게 설계 |

> 5번 근거: CSV가 KMDb(한국영화DB) 출신이라 `tmdb_type=tv`가 24행뿐. 그래서 `content_type` enum은
> `movie/drama/show`를 **그대로 유지**하고, 영화 전용값(`kmdb_code`·`runtime`)은 nullable,
> `source`로 출처 구분, `mappings.episode`(촬영회차)를 **미리** 만들어 뒀다. → 드라마 추가 시 마이그레이션 불필요.

## 코드 구조 — 기능별 폴더 (2026-08-16 재편)
계층별(`routers/`·`services/`·`schemas/`)에서 **기능별**로 바꿨다. `catalog.py` 하나에 작품·지역·장소
질의가 444줄로 섞여 있어 3·6·7단계가 들어오면 계속 비대해지는 구조였다.

```
app/
├─ features/          기능 하나 = 폴더 하나 = router.py + service.py + schema.py
│   ├─ contents/      작품 검색·상세                    (5단계 ✅)
│   ├─ places/        촬영지 조회·반경·상세 + matching.py (4·5단계 ✅)
│   ├─ regions/       지역 리졸브·목록                   (5단계 ✅)
│   ├─ health/        헬스체크                          (1단계 ✅)
│   └─ auth/         회원가입·로그인·로그아웃·소셜        (3단계 ✅)
│       └ courses/ (6단계) 가 여기 추가된다
├─ integrations/      tour_api.py · call_log.py  ← 외부 연동은 '기능'이 아니라 어댑터
├─ shared/            schema.py (Location·RegionRef·Page)
├─ core/  deps/       설정·DB·인증 토대
└─ models/            ★ 옮기지 않음 — Alembic이 여기를 읽고, mappings가 contents·places를
                        동시에 FK로 참조해 어느 기능에도 속하지 않는다
```
새 기능 추가 = `features/` 아래 폴더 하나 + [`main.py`](./app/main.py)에 `include_router` 한 줄.

## 현재 DB 상태 (리비전 `9a1c7d2e5b40`)
| 테이블 | 행수 | 주요 컬럼 |
|---|---|---|
| `regions` | **244** (시도 17 + 시군구 227) | region_id, name, **level**, **parent_region_id**, area_code, sigungu_code, centroid |
| `contents` | **1,694** | content_id, content_type, title_ko, poster_url, **kmdb_code**, source, source_url, production_year, original_title, overview, **genre_tags**, tmdb_id, tmdb_type, vote_average, runtime |
| `places` | **9,811** | place_id, name, geom, region_id, tour_content_id, **kmdb_place_id**, source, **address**, road_address |
| `content_place_mappings` ★ | **13,755** | mapping_id, content_id, place_id, **kmdb_case_id**, **scene_description**, characters, **episode** |
| `users` | 0 | user_id, nickname, auth_provider(**local**/google/kakao), provider_user_id?, **email**?, **password_hash**?, **email_verified**, created_at |
| `courses` / `course_places` | 0 / 0 | (6단계에서 사용) |
| `refresh_tokens` 🆕 | 0 | token_id, user_id, **token_hash**(SHA-256), expires_at, revoked_at, user_agent |
| `email_verifications` 🆕 | 0 | verification_id, email, **code_hash**, expires_at, attempt_count, verified_at, consumed_at |

**데이터 품질**: 장소 좌표 100%(9,811/9,811) · 장소↔지역 연결 100% · 지역 중심점 100%(244/244) · 작품 장르 82% · 포스터 82%.
**인덱스**: `idx_places_geom`(GIST, 반경검색 검증됨) · `ix_contents_genre_tags`(GIN) · `ix_places_region_id` · `ix_cpm_place_id`.

> 지연 5테이블(favorites·search_history·content_translations·place_aliases·**api_call_logs⚠️**)은
> [`app/models/__init__.py`](./app/models/__init__.py)에서 import 주석 처리 상태. 해당 기능 단계에서 활성화.

## 팀 분담 (2026-08-22)
백엔드를 둘로 나눴다. **브랜치를 분리해 작업**한다 — `main` 직접 커밋 금지.

| 담당 | 범위 | 브랜치 |
|---|---|---|
| 김은서 | **인증** — 회원가입·로그인·로그아웃·소셜(카카오/구글) | `eunseo` |
| 팀원 | 지도 API 기반 지역 구분 | `yoon` |

`app/models/user.py`·`app/deps/`·`app/main.py`는 인증 쪽에서 건드리므로 병합 시 확인이 필요하다.

## 3단계 완료 — 인증 (2026-08-22)

> **⚠️ 카카오 로그인은 윤영 담당** (2026-08-22 분담) — 지도 API 때문에 카카오 개발자센터 앱을
> 이미 만들어 둔 쪽이 콘솔·앱 SDK·서버 엔드포인트까지 맡는다. 서버엔 **자리와 안내 주석만** 있고
> `POST /auth/kakao`는 없다. 공용 부분(`service.social_login`·`SocialProfile`·enum·설정값)은 준비됨.

**설계 결정 — 왜 토큰이 2개인가.** JWT는 서버가 저장하지 않고 서명만 검증한다. 빠른 대신
**발급 후 취소가 불가능**해서 로그아웃 버튼이 무력해진다. 그래서 역할을 쪼갰다.

| | access | refresh |
|---|---|---|
| 정체 | JWT | 난수 48바이트 |
| 수명 | **1시간** | **30일** |
| 저장 | 안 함 | `refresh_tokens`에 **SHA-256 해시로** |
| 취소 | 불가 | 가능 → **이게 로그아웃** |

기존 계약("14일짜리 토큰 1개")은 폐기했다. 실무 표준이고, 짧은 수명과 자동 로그인 유지를
동시에 얻는 유일한 구조다.

| 항목 | 상태 |
|---|---|
| `app/features/auth/` — router·service·schema·social·mailer (기능 폴더 1개로 통합) | ✅ |
| `app/core/security.py` — JWT 2종 · refresh 해시 · bcrypt · 인증코드 | ✅ |
| `app/deps/get_current_user` + `CurrentUser`·`OptionalUser` 별칭 | ✅ |
| 마이그레이션 `9a1c7d2e5b40` — enum `local` 추가 · users 확장 · 테이블 2개 | ✅ |
| 엔드포인트 **9종** 실호출 검증 [`scripts/check_auth.py`](./scripts/check_auth.py) **37/37 통과** | ✅ |
| 실제 메일 발송(SMTP 계정) | 🔶 미설정 — `dev_code`로 개발 가능 |
| `GOOGLE_CLIENT_ID` (구글 웹 클라이언트 ID) | 🔶 미설정 — **배포 전 필수** |

**엔드포인트 9종** (+ 카카오 1종은 윤영 담당)

| 경로 | 역할 |
|---|---|
| `POST /auth/email/send-code` | 가입용 6자리 인증코드 발송 |
| `POST /auth/email/verify-code` | 코드 확인 (30분짜리 가입 통과권) |
| `POST /auth/signup` | 회원가입 + 즉시 토큰 발급 `201` |
| `POST /auth/login` | 이메일+비밀번호 로그인 |
| `POST /auth/google` | 구글 `id_token` 검증 → 자동 가입/로그인 |
| ~~`POST /auth/kakao`~~ | **윤영 담당 — 미구현** (자리·안내 주석만 있음) |
| `POST /auth/refresh` | access 재발급 (**refresh 회전**) |
| `POST /auth/logout` | 이 기기 refresh 폐기 (멱등) |
| `POST /auth/logout-all` 🔒 | 모든 기기 로그아웃 |
| `GET /auth/me` 🔒 | 내 정보 |

**보안 결정 요약**

| 항목 | 선택 | 근거 |
|---|---|---|
| 비밀번호 | **bcrypt** (passlib 미사용) | passlib은 유지보수 중단. 72바이트 한계는 스키마에서 차단 |
| refresh 저장 | SHA-256 해시 | DB 유출돼도 로그인 불가. 난수라 bcrypt 불필요·조회키로 써야 함 |
| refresh 회전 | 재발급 시 옛것 즉시 폐기 | 안 하면 유출 토큰으로 30일 내내 access 발급 가능 |
| **재사용 감지** | 폐기된 refresh 재등장 → **전 세션 차단** | 정상 앱은 새것을 받아갔다 = 탈취 신호 |
| 로그인 실패 문구 | 계정없음·비번틀림 **동일** | 이메일 대입으로 가입 여부를 캐내지 못하게 |
| 소셜 검증 | 토큰 진위 + **앱 소속**(`aud`/`app_id`) | 진위만 보면 **다른 앱 토큰으로도 로그인된다** |
| 인증코드 | 10분 · 5회 · 재발송 60초 · 해시 저장 | 6자리는 100만 조합 — 횟수 제한이 없으면 뚫린다 |
| 유저 테이블 | 한 테이블 + CHECK 제약 | `courses.user_id` FK가 가입 경로별로 갈라지면 안 됨 |

**⚠️ 남은 것**
- `.env`에 `GOOGLE_CLIENT_ID`·`KAKAO_APP_ID`가 비어 있으면 **앱 소속 검증을 건너뛴다**
  (서버 로그에 경고 출력). 배포 전 반드시 채운다.
- SMTP 미설정 상태 — `send-code` 응답의 `dev_code`와 서버 로그로 코드가 나온다.
  Gmail 앱 비밀번호를 `.env`에 넣으면 코드 수정 없이 실제 발송으로 전환된다.
- 소셜 로그인 **정상 경로**는 앱에 SDK가 붙어야 확인 가능(현재는 위조 토큰 401 거부만 검증됨).

## 4단계 완료 — TourAPI 실시간 연동 (2026-08-16) ⚠️합격핵심

| 항목 | 상태 |
|---|---|
| [`app/integrations/tour_api.py`](./app/integrations/tour_api.py) — 클라이언트(상세·소개·이미지·키워드·위치기반·관광사진) | ✅ |
| `TOUR_API_KEY` 발급·연동·실호출 검증 | ✅ |
| **`api_call_logs` 활성화** — 호출 입증 (리비전 `aedbf5168cc3`) | ✅ |
| **`GET /places/{id}`** — 우리 데이터 + TourAPI 실시간 상세 | ✅ |
| 이름기반 매칭 [`features/places/matching.py`](./app/features/places/matching.py) (온디맨드) | ✅ |
| 사전매칭 배치 [`scripts/match_tour_places.py`](./scripts/match_tour_places.py) | ✅ |
| `places.tour_matched_at` — 실패 기억(쿼터 보호, 리비전 `06fb23255fb0`) | ✅ |
| 인기 촬영지 300~500곳 사전매칭 **완주** (현재 11곳) | 🔶 진행 중 |

## 사용 API 3종 (2026-08-16 실호출 검증 — 전부 승인·동작)
⚠️ **경로 뒤 숫자가 서비스마다 다르다. 추측 금지** — KorService만 2이고 나머지 둘은 1이다.

| # | 서비스 (data.go.kr) | 실제 경로 | 쓰는 곳 |
|---|---|---|---|
| ① | 국문 관광정보 `15101578` | `KorService2` | 장소 상세(4단계) · 매칭 |
| ② | 관광사진 정보 `15101914` | `PhotoGalleryService1` | 촬영지 사진 보강 (미연동) |
| ③ | 기초지자체 중심 관광지 `15128559` | `TarRlteTarService1` | 주변 볼거리·코스 추천(6단계) (미연동) |

- ①: `KorService1`은 폐기. `detailCommon2`·`detailIntro2`·`detailImage2`·`searchKeyword2` 사용.
- ②: `PhotoGalleryService2`·`galleryKeywordList2`는 **존재하지 않는 경로**(12번 오류).
  확인된 오퍼레이션 `galleryList1`·`gallerySearchList1`·`galleryDetailList1`.
  응답에 `galPhotographer`(촬영자)가 있어 **저작권 표기와 함께** 노출해야 한다.
- ③: `TarRlteTarService2`는 400. `areaBasedList1` + `baseYm` 필수(`202606` 확인, `202312`은 0건).
  ⚠️ **`areaCd`/`signguCd`가 법정동 코드다** (강원특별자치도=`51`, 강릉시=`51150`).
  TourAPI 자체 지역코드(강원=32)와 **다르다.** `regions.area_code`·`sigungu_code`가
  현재 **0/244**라 채우기 전엔 호출 불가 — ③ 연동의 선행 과제.
  실측: 강릉시 → 관광지 1위 **「도깨비촬영지/(영진해변)」**, 숙박 1위 블리스펜션, 음식 1위 금성해장국.

**호출 입증 (`api_call_logs`)** — 모든 호출이 `TourApiClient._get` 안에서 자동 기록된다(빠뜨릴 수 없는 구조).
남기는 것은 `operation`·`request_params`·`http_status`·`response_time_ms`·`result_count`·`called_at`뿐 —
**응답 본문은 저장하지 않는다(무캐싱)**. `request_params`에 `serviceKey`는 들어가지 않는다(검증: 유출 0건).

**매칭 전략**: **온디맨드 + 인기곳 사전매칭**. 개발계정 1,000건/일이라 9,811곳 전수 매칭은 비현실적 →
사용자가 연 장소를 그때 매칭하고, 인기 촬영지만 배치로 미리 채운다.

| 규칙 | 값 | 근거 |
|---|---|---|
| 이름 변형 | 최대 3개 | 원본 → 괄호제거 → 지역접두 절단 → "지역 이름". 일 1,000건 보호 |
| 좌표 검증 | **≤1km** | 500m는 좁았다 — 올림픽공원은 우리 촬영지점↔공사 대표좌표가 663m |
| 이름 유사도 | **≥0.7** | 「다이소 서울역점」(0.60)·「게스 롯데아울렛 서울역점」(0.43) 오탐 차단 |
| 실패 재시도 | 30일 후 | 실패를 기억 안 하면 조회할 때마다 검색 3회 재소모 |

**호출량**: 미매칭 장소 첫 조회 최대 6건(검색3+상세3) · 매칭된 장소 3건 · **실패 기억된 장소 0건**.

## 매칭 실측 결과 (2026-08-16)
시도 16곳 중 **11곳 매칭(69%)**. 초기 47%에서 올랐다 — 괄호제거 변형 + 좌표 1km 완화 효과.

**성공**: 강릉선교장 · 인천국제공항 · 부산영화촬영스튜디오 · 합천영상테마파크 · 서대문형무소역사관 ·
용산역사박물관 · 한국민속촌 · 설매재자연휴양림 · 문경새재도립공원 · 올림픽공원 · 광안대교

**미검출(정상)**: 남양주종합촬영소 · DMC첨단산업센터 · YTN본사 · 익산교도소세트장 · 스튜디오112 ·
문화역서울284 · 서울역 · 국립경찰병원 · 서울교통공사본사 · 전주영화종합촬영소 등
→ **애초에 관광지가 아니다**(방송사 사옥·촬영 스튜디오·세트장·병원). 계약서의
"`detail`은 null일 수 있다"가 예외가 아니라 **정상 경로**임이 실측으로 확인됐다.

## 5단계 완료 — 검색·지도 엔드포인트 8종 (2026-08-15)
계약서([`API_CONTRACT.md`](./API_CONTRACT.md))를 먼저 확정하고 그대로 구현했다.

| 엔드포인트 | 역할 |
|---|---|
| `GET /contents/search?q=` | 작품 검색(부분일치, 관련도순) |
| `POST /contents/resolve` | 제목 → 후보 (AI용) |
| `GET /contents/{id}` | 작품 상세 |
| `GET /contents/{id}/places` | 작품의 촬영지 목록 |
| `GET /regions/resolve?name=` | 지역명 → 후보 (AI용) |
| `GET /regions` | 지역 목록(시도→시군구, `?flat=true`) |
| `GET /regions/{id}/places` | 지역 내 촬영지 + 포스터 (`?content_id=`로 작품 필터) |
| `GET /places?near=&radius_km=` | 반경 조회(≤20km, `distance_km` 부여) |
| `GET /places/{id}` ⚠️ | **장소 상세 — TourAPI 실시간** (4단계에서 추가) |

**검증된 실제 응답**
- `q=기생` → 기생충(28곳)·음란 기생(1곳) — 관련도 정렬 동작
- `resolve("만추")` → 1981·1966 두 후보 / `resolve("중구")` → **6개** / `"서울 중구"` → **1개로 좁혀짐**
- 강릉시 70곳 → `?content_id=559`(관상) → **1곳(강릉선교장)** — 유저플로우 4b 동작
- 강릉 반경 5km → 44곳, 가까운 순
- 에러: 반경 20km 초과 `400` · 없는 작품/지역 `404` · 빈 결과 `200 total=0`

**구조**: `router`(얇게) → `service`(질의) → `schema`(계약 형태), 기능 폴더 안에서 3단.
장소 목록의 `contents` 배열은 place_id를 모아 한 번에 조회해 **N+1을 피했다.**

## 📍 지금 위치 / ▶️ 다음 할 일
- **합격 핵심 요건 충족**: TourAPI를 매 요청 실시간 호출하고 `api_call_logs`로 입증한다.
  검증 완료 — 강릉선교장 조회 시 `searchKeyword2`×2 → `detailCommon2`·`detailIntro2`·`detailImage2`,
  전 호출이 기록되고 `serviceKey` 유출 0건. 재조회 시 이름검색을 건너뛰어 3건만 사용.
- **엔드포인트 9종 동작**: 5단계 8종 + `GET /places/{id}`.
- **바로 다음**: 사전매칭 배치 완주 — `python -m scripts.match_tour_places --limit 50`을
  하루 여러 번 나눠 돌려 인기 촬영지 300~500곳을 채운다(현재 11곳, 일 1,000건 한도).
- **3단계 완료(2026-08-22)**: 인증 9종(카카오는 윤영 담당으로 이관). 위 「3단계 완료」 절 참고.
  `deps/CurrentUser`가 생겨 6단계 코스 저장에 바로 `🔒`를 붙일 수 있다.
- **알려진 갭**
  - **pytest가 0개** — 검증은 실호출 스크립트([`check_tour_api.py`](./scripts/check_tour_api.py) ·
    [`check_auth.py`](./scripts/check_auth.py) 37케이스)로만 해왔다. 8단계에서 pytest 도입 필요.
  - **소셜 로그인 정상 경로 미검증** — 앱에 카카오/구글 SDK가 붙어야 확인 가능. 현재는
    위조 토큰이 401로 거부되는 것까지만 확인됨.
  - **`GOOGLE_CLIENT_ID`·`KAKAO_APP_ID` 미설정** — 비어 있으면 "이 토큰이 우리 앱 것인가"
    검증을 건너뛴다. ⚠️ 배포 전 필수.
  - 매칭 `tour_content_id` 11/9,811 (온디맨드로 계속 늘어남)
  - 작품 296편(18%)에 포스터 없음 · **드라마 10편뿐**(영화 1,684편) — 앱 컨셉이 "영화·드라마"인데
    드라마가 사실상 없다. 스키마는 INSERT만으로 추가 가능하므로 데이터 확보 여부가 관건.
  - **운영계정 필요 여부 확인** — 개발계정 1,000건/일로 심사·시연 트래픽을 감당할 수 있는지.
    승인에 시간이 걸리므로 미리 확인해야 한다.
- **커밋**: 5단계까지는 `main`. **인증(3단계)은 `eunseo` 브랜치** — 팀원이 `yoon`에서 작업 중이라
  분리했다. `main` 직접 push 금지.
- **다음 후보**: 6단계 코스(인증 붙일 준비 끝) · 사전매칭 배치 완주 · 8단계 pytest 도입.
