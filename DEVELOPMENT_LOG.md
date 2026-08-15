# K-tour BE — 개발 구현 일지 (DEVELOPMENT LOG)

> "무엇을 · 어떻게 · 왜" 관점으로 단계별 구현 과정을 기록한다. 로드맵·기준 문서는
> [`PROJECT_REPORT.md`](./PROJECT_REPORT.md)이고, 본 문서는 그 §10(구현 기록)의 상세판이다.
> 최신 갱신 단계: **2단계 — DB 구동 + 12개 모델 정의 + mockup 정합성 보강 (마이그레이션 직전)**

---

## 2단계 작업 ① — DB 인프라 구동 (PostgreSQL + PostGIS)

| 구분 | 내용 |
|---|---|
| **무엇** | 로컬에 PostgreSQL 16 + PostGIS 컨테이너 `ktour-db`를 띄움 |
| **어떻게** | ① 관리자 PowerShell `wsl --install --no-distribution` → 재부팅 ② Docker Desktop 실행 → 엔진 정상화(Server v29.5.3, Linux 백엔드) ③ `docker compose up -d`로 `postgis/postgis:16-3.4` 기동 |
| **왜** | 백엔드가 처음이라 **`docker compose up` 한 줄로 PostGIS 내장 DB가 통째로** 뜨는 방식이 가장 쉬움. PostGIS를 손으로 설치하면 인코딩·확장설치에서 초보가 가장 많이 막힘. Docker 엔진은 WSL2 위에서 도니 WSL2 설치가 선행 필요(그래서 재부팅 1회). |
| **검증** | `docker version`(Server v29.5.3) · `pg_isready`(연결 OK) · `pg_available_extensions`에서 `postgis_available=1` 확인 |

> ⚠️ 컴플라이언스: 일반 PostgreSQL이 아니라 **PostGIS**가 필요한 이유는 "반경 20km 안의 촬영지" 같은 **지도(지오) 쿼리**가 핵심 기능이기 때문.

---

## 2단계 작업 ② — 옛 설계파일 정리 (단일 기준 확립)

| 구분 | 내용 |
|---|---|
| **무엇** | 상위 폴더의 옛 설계/스키마 파일 7개 삭제 (`01_데이터_정의.md`, `02_DB_설계.md`, `03_API_명세서.md`, `schema.sql`, `erd.dbml`, `공모전_개요.md`, `아이디어_검토.md`) |
| **왜** | 옛 **Supabase 6테이블** 설계와 새 **v3 12테이블** 설계가 섞여 있어 혼동·오작성 위험. 기준 문서를 **`PROJECT_REPORT.md` 하나**로 통일. (옛 `.md`는 git 커밋 `35edf75`에 보존돼 복구 가능) |

---

## 2단계 작업 ③ — 12개 SQLAlchemy 모델 정의

### 구조
- `app/models/`를 도메인별 모듈로 분리: `common`(Enum·믹스인) / `user` / `region` / `content` / `place` / `mapping` / `course` / `interaction` / `api_log`, `__init__`에서 전부 import.
- `app/core/db.py`의 `Base`에 **이름 규칙(naming_convention)** 추가 → FK·인덱스 이름이 일관되게 자동 생성. **왜**: Alembic 마이그레이션의 제약 이름을 예측 가능하게 만들어 이후 스키마 변경이 깔끔해짐.

### 핵심 설계 결정 (대부분 "왜"가 공모전 컴플라이언스 §3에서 나옴)

| 결정 | 어떻게 | 왜 |
|---|---|---|
| Enum을 **네이티브 타입**으로 | `content_type`·`relation_type`·`confidence_level`·`transport_mode`·`auth_provider` | 자유 문자열이면 오타·대소문자 혼입 → DB가 **정해진 값만 허용**해 무결성 보장 |
| `places`에서 **TourAPI 응답 컬럼 제거** | 개요·전화·운영시간·대표이미지 컬럼을 **안 만듦**. 이름·좌표·`tour_content_id`만 보관 | **§3.2 무캐싱** — 옛 설계엔 이 컬럼들이 있었고 그게 실격 사유. v3는 상세를 **실시간 호출** |
| `geom` = PostGIS **`geography(Point,4326)`** | 위경도를 지오 타입으로(GeoAlchemy2) | 단순 숫자 2개가 아니라 **반경·거리 계산**이 되는 타입. 4326=GPS 표준 좌표계. §3.2가 허용하는 **큐레이션 좌표** |
| `api_call_logs`에 **`serviceKey` 없음** | `request_params`(JSONB)엔 키 뺀 값만 | **§3.3** 인증키 저장 금지 + **§3.1** 실시간 호출 입증 |
| `courses`에 **출발 GPS 좌표 없음** | 경유지를 `place_id`로만 참조 | **§3.5** 위치기반서비스 등록 회피 |
| `regions`는 **시드 테이블** | 코드값을 미리 채움 | **§3.6** `areaCode2` 런타임 호출 금지 |
| `content_place_mappings` = **핵심 자산** | `relation_type`(6종)·`relevance_reason`·`confidence`(verified/likely/inferred) | TourAPI에 없는 "작품↔촬영지" 매핑을 우리가 큐레이션 = 이 앱의 차별점 |
| **트라이그램(trgm) 인덱스** | `contents.title_ko`·`places.name`에 GIN + `gin_trgm_ops` | 한글 부분검색·자동완성 가속 (※ `pg_trgm` 확장은 마이그레이션에서 생성) |
| **FK 삭제 정책** | CASCADE / RESTRICT / SET NULL 구분 | 아래 표 참조 |

#### FK `ondelete` 정책과 이유
| 관계 | 정책 | 이유 |
|---|---|---|
| `content_translations`·`place_aliases`·`content_place_mappings`·`favorites` → 부모 | **CASCADE** | 부모(작품/장소/유저)가 사라지면 딸린 데이터도 무의미 |
| `course_places.place_id` | **RESTRICT** | 코스에 담긴 장소는 함부로 삭제되면 안 됨 |
| `search_history.user_id`·`api_call_logs.user_id` | **SET NULL** | 유저가 탈퇴해도 **검색 통계·호출 입증 로그는 보존** (호출 로그는 공모전 입증용) |

### 검증
`python -c "import app.models"` → **12개 테이블 등록 확인** + `configure_mappers()`로 **모든 relationship 정상** 확인. ✅

---

## 2단계 작업 ④ — UI mockup 정합성 보강

앱 화면 mockup(12개 화면 "Every Trip")과 모델을 대조해 **빠진 기능을 점검**하고, 마이그레이션 전(스키마 변경이 가장 싼 시점)에 반영했다.

### 보류 결정 (마감 9/21 고려, 나중에 테이블만 추가)
- **인물(배우·감독) 검색** (화면3 "인물" 탭) — 작품별 출연진 큐레이션 부담이 크고 핵심 차별점(촬영지)과 직결도 약함 → 보류.
- **평점·리뷰** (화면8 ★4.7) — UGC라 신고·스팸·평점집계까지 동반 → 보류.

### 지금 추가한 것 (무엇 / 왜)
| # | 변경 | 무엇을 | 왜 (어느 화면) |
|---|---|---|---|
| A | **소셜 로그인** | `users`에 `auth_provider`(local/google/kakao)·`provider_user_id` 추가, `email`·`password_hash`를 **nullable**로 | 화면11·12가 소셜(구글·카카오)+이메일 로그인. 카카오는 이메일 미제공 가능, 소셜은 비번 없음 → nullable |
| B | **다일(1박2일) 코스** | `course_places.day` 컬럼 | 화면7·10 "1박 2일 코스". `visit_order`는 코스 전체 통합 순번, `day`는 며칠차 |
| C | **코스 좋아요·공유** | `courses.is_public` + 기존 `favorites`에 `course_id` 확장 | 화면8 공유 / 화면10 "좋아요" 탭. 테이블 안 늘리고 `favorites` 재활용 |
| F | **방송사/채널** | `contents.network` | 화면3 "도깨비 · tvN" |
| G | **추천/인기 정렬** | `contents.is_featured` · `places.popularity` | 화면2 "오늘의 추천 작품" · "인기 여행지 TOP" |
| H | **촬영회차** | `content_place_mappings.episode` | 화면8 "촬영회차 도깨비 16화" |
| 🐞 | **중복 즐겨찾기 버그 수정** | `favorites` UNIQUE에 `nulls_not_distinct=True`(PG15+) | PostgreSQL은 기본적으로 NULL을 서로 다르게 봐서 기존 UNIQUE가 **중복 즐겨찾기를 못 막음**. NULLS NOT DISTINCT로 교정 |

> ⚠️ 컴플라이언스 메모: 화면2 "지도로 찾기(**내 주변**)"는 §3.5(GPS 서버 전송 금지)와 충돌 → **raw GPS 대신 지역코드/장소 중심점 + 반경 20km**로 구현해야 함. 스키마(`geom`)는 이미 지원하므로 **API 설계 시 입력값만 주의**.

### 결과
테이블 수는 그대로 **12개**(필드만 풍부해짐). 컬럼 재확인으로 모든 추가 반영 검증 완료. ✅

---

## 2단계 작업 ⑤ — Alembic + 최소 컬럼 전환 + 마이그레이션 적용 ✅

| 구분 | 내용 |
|---|---|
| **무엇** | 7개 테이블을 **꼭 필요한 컬럼만**(테이블당 3~5개)으로 줄여 실제 DB에 생성 |
| **어떻게** | ① Alembic async `env.py` + geoalchemy2 헬퍼 + **`include_name` 필터**(PostGIS tiger/topology 시스템 테이블 DROP 방지) ② 유저 플로우 기준 모델을 최소 컬럼으로 재작성(부가 컬럼·enum 3종 제거) ③ autogenerate → `CREATE EXTENSION postgis` + downgrade enum 정리 보정 ④ `alembic upgrade head` |
| **왜 최소화** | 사용자 요청 "꼭 필요한 것만". 컬럼은 나중에 1줄 마이그레이션으로 추가 가능하므로 부담 적음. 로그인은 구글·카카오만(email/비번 제외), 검색 trgm 인덱스는 나중에. |
| **검증** | `\dt`로 public에 7개 테이블 확인, `places`는 `place_id·name·geom(geography)·region_id·tour_content_id` + GIST 인덱스, enum `content_type`·`auth_provider(google,kakao)` 확인. 마이그레이션 리비전 `439ec7cb835f (head)`. ✅ |

### 트러블슈팅 기록
- **asyncpg `Illegal byte sequence`**: 한글 홈경로(`C:\Users\김은서`)의 기본 SSL 인증서 로딩 실패 → `.env`의 `DATABASE_URL`에 `?ssl=disable` 추가(로컬 Docker DB라 SSL 불필요)로 해결.
- **PostGIS 시스템 테이블 DROP 시도**: 이미지에 내장된 tiger 지오코더·topology 테이블을 Alembic이 삭제하려 함 → `env.py`에 우리 메타데이터 테이블만 비교하는 `include_name` 필터 추가로 해결.

---

## ✅ 2단계 종료 — 다음은 3단계(회원가입/로그인, 구글·카카오 소셜)
실시간 진행 현황은 [`PROGRESS.md`](./PROGRESS.md) 참조.

---

## 2.5단계 — 스키마 확장 + 실데이터 적재 (2026-08-15) ✅

### 왜 지금 했나
3단계(로그인)로 바로 가지 않고 데이터 적재를 먼저 한 이유:
- **DB가 빈 껍데기(7테이블 전부 0행)였다.** 이 상태로는 4·5·6단계에서 뭘 만들어도 검증이 불가능하다
  — 검색 API를 만들어도 결과가 항상 빈 배열, 지도 API를 만들어도 마커가 0개.
- **데이터 모양이 API 설계를 결정한다.** API를 먼저 만들고 나중에 데이터를 넣으면 데이터에 맞춰 API를 다시 고쳐야 한다.
- 이 CSV가 곧 **앱의 차별점**이다(TourAPI엔 작품↔촬영지 연결이 없다는 게 프로젝트의 전제).
- 마감까지 37일. 데이터가 이미 완비돼 있어 지금이 가장 싸게 끝낼 수 있는 시점이었다.

### 무엇을
`data/data.csv`(KMDb 촬영지 원본 + TMDB 보강, 25컬럼 13,761행)를 4개 테이블로 분해 적재.

### 어떻게
| # | 작업 | 내용 |
|---|---|---|
| ① | **파일 정리** | BE 루트에 있던 `data.csv`를 `data/`로 이동. `app/`은 파이썬 패키지라 14.7MB 데이터가 들어갈 곳이 아님 |
| ② | **프로파일링** | 넣기 전에 무결성부터 확인 — 자연키 고유성·중복쌍·좌표 이상치·빈값 비율 |
| ③ | **모델 확장** | regions 시도→시군구 계층화, contents/places/mappings에 컬럼 추가 |
| ④ | **마이그레이션** | `c4d4fdb425b1` autogenerate → **손으로 검토·보정** → 적용 |
| ⑤ | **시드 스크립트** | [`scripts/seed_from_csv.py`](./scripts/seed_from_csv.py) — 자연키 ON CONFLICT DO NOTHING으로 재실행 안전 |

### 왜 그렇게 설계했나 (핵심 판단들)
- **주소는 지번 기준**: 프로파일 결과 도로명은 15.4%가 비었고 지번은 0.5%만 비었다.
- **장면설명·등장인물을 places가 아니라 mappings에**: 같은 장소라도 작품마다 장면이 다르므로 '연결'의 속성이다.
- **드라마 확장을 미리 열어둠**: CSV가 KMDb(영화DB) 출신이라 `tmdb_type=tv`가 24행뿐 → 1차는 영화로 확정.
  단 `content_type` enum은 movie/drama/show를 **그대로 유지**하고, 영화 전용값(`kmdb_code`·`runtime`)은 nullable,
  `source`로 출처 구분, `mappings.episode`(촬영회차)를 미리 생성. **→ 드라마 추가 시 마이그레이션 불필요, INSERT만.**
- **`area_code`를 nullable로 완화**: 공모전에서 지역코드 조회 API(areaCode2)가 **사용 금지**라 코드를 API로 받아올 수 없다.
- **자연키 3개를 UNIQUE로**: `영화작품코드`·`장소일련번호`·`사건일련번호`. 시드 재실행/중단 후 재개가 안전해진다.

### 검증
- 적재 결과: regions **244**(시도 17 + 시군구 227) · contents **1,694** · places **9,811** · mappings **13,755**
- 품질: 장소 좌표 100%(9,811/9,811) · 장소↔지역 연결 100% · 지역 중심점 100% · 장르 82% · 포스터 82%
- **유저플로우 쿼리 실동작**: '기생충' → 촬영지 28곳(장면설명 포함) / 강릉 반경 5km → 촬영지+작품 포스터
- **인덱스 사용 확인**: `EXPLAIN` 결과 반경검색이 `Bitmap Index Scan on idx_places_geom` (전수 스캔 아님)
- **재실행 안전성**: 시드를 두 번 돌려도 행수 불변(244/1694/9811/13755)

### 트러블슈팅·함정 기록
- **NULL 유니크 함정(재발)**: `regions`의 `(parent_region_id, name)` UNIQUE에서 시도 행은 parent가 NULL인데
  PostgreSQL은 NULL을 서로 다르게 봐서 '경기도'가 중복 삽입될 수 있었다 → `NULLS NOT DISTINCT`(PG15+)로 차단.
  *(2단계 `favorites`에서 겪은 것과 같은 함정 — 유니크에 nullable 컬럼이 끼면 항상 의심할 것.)*
- **autogenerate의 NOT NULL 함정**: `regions.level`을 `nullable=False`로 그냥 추가하게 생성됐다.
  지금은 0행이라 통과하지만 데이터가 있는 DB에선 실패한다 → 임시 `server_default` 후 제거하도록 손으로 보정.
- **(작품,장소) 중복 6쌍**: UNIQUE에 걸려 트랜잭션이 깨지므로 파이썬에서 미리 첫 행만 남기고 제외.
- **콘솔 인코딩**: Windows 터미널에서 한글이 깨져 보여 `PYTHONIOENCODING=utf-8` 필요(파일 자체는 UTF-8 BOM 정상).

---

## 4단계 준비 — TourAPI 연동 골격 (2026-08-15) 🔶 키 대기

### 무엇을 / 왜
공모전 필수 요건인 **KTO 오픈API 실시간 호출**의 골격을 먼저 세웠다. 인증키는 사용자가 data.go.kr에서
발급받아야 하는데, 키가 없어도 개발이 멈추지 않도록 **키를 나중에 꽂기만 하면 되는 구조**로 만들었다.

### 어떻게
- [`app/services/tour_api.py`](./app/services/tour_api.py) — async 클라이언트.
  상세(detailCommon)·이미지(detailImage)·위치기반(locationBasedList)·키워드(searchKeyword)·관광사진(gallery).
  **금지 오퍼레이션(areaCode2·categoryCode2·산악관광)은 아예 구현하지 않음.** 반경은 20km로 상한 고정.
- [`scripts/check_tour_api.py`](./scripts/check_tour_api.py) — 키 자가진단.
  키가 없으면 발급 안내만 출력하고 조용히 종료, 있으면 우리 DB의 실제 촬영지로 ①검색→②반경→③상세→④이미지를 시연.
- `config.py`에 `TOUR_API_KEY`(빈 기본값)·베이스URL·타임아웃. `.env.example`에 발급 절차·주의사항 문서화.

### 판단: 매칭 전략
`places.tour_content_id`가 0/9,811이다(CSV엔 TourAPI 식별자가 없다). 전수 매칭하려면 개발계정
1,000건/일로 **10일**이 걸려 마감 37일 상황에선 비현실적 → **온디맨드 + 인기곳 사전매칭**으로 결정.
사용자가 실제로 연 장소만 그때 매칭해 기록하고, 시연용 300~500곳만 미리 배치. '실시간 호출' 요건에도 부합.

### 검증
- 키 없는 상태에서 자가진단이 트레이스 없이 안내만 출력 ✅
- 키 없어도 앱 정상 기동, `/health`·`/` 200 응답 ✅ (TourAPI 부재가 다른 기능을 막지 않음)

---

## 5단계 — 검색·지도 엔드포인트 8종 (2026-08-15) ✅

### 왜 이 순서로 했나
계약서(`API_CONTRACT.md`)를 **먼저 확정하고 그다음 구현**했다. 팀이 "각자 파트를 완성한 뒤 연결"하기로 해서,
통합 시점에야 불일치가 드러나면 마감 직전에 손쓸 수 없기 때문. 계약서를 쓰는 과정에서 실제로
설계 결함 하나(플로우 4b용 지역∩작품 조회 누락)를 미리 발견했다.

### 무엇을
| 엔드포인트 | 역할 |
|---|---|
| `GET /contents/search?q=` | 작품 검색(부분일치·관련도순) |
| `POST /contents/resolve` | 제목 → 후보 (AI용) |
| `GET /contents/{id}` · `/{id}/places` | 작품 상세 · 그 작품의 촬영지 |
| `GET /regions/resolve?name=` · `GET /regions` | 지역명 → 후보 · 지역 목록 |
| `GET /regions/{id}/places` | 지역 내 촬영지 + 포스터 (`?content_id=` 필터) |
| `GET /places?near=&radius_km=` | 반경 조회(≤20km) |

### 어떻게
`routers`(얇게: 검증→서비스 호출) → `services/catalog.py`(질의) → `schemas`(계약 형태) 3층.
- **N+1 회피**: 장소 목록의 `contents` 배열은 장소마다 조회하면 N+1이 된다. place_id를 모아 한 번에
  가져와 파이썬에서 묶었다(`_contents_by_place`).
- **관련도 정렬**: 정확일치 1.0 > 접두 0.8 > 부분 0.5. 부분일치라 '기생'에 「음란 기생」이 걸리는데,
  점수 → 촬영지 수 → 최신순으로 정렬해 의도한 작품이 위로 온다.
- **시도로도 조회 가능**: `region_id`가 시도면 자식 시군구의 장소까지 포함(`_region_scope_ids`).
- **지역 힌트 파싱**: "서울 중구"처럼 오면 마지막 토큰을 대상, 앞을 상위 지역 힌트로 써서 후보를 좁힌다.

### 컴플라이언스 반영
- `GET /places`에 **raw GPS 파라미터를 만들지 않았다.** 좌표를 서버가 받으면 위치기반서비스 사업자
  등록이 필요해지므로, 입력은 `region_id`뿐이다.
- `radius_km > 20`이면 `400`. 공모전 위치기반 조회 반경 제한.

### 검증
- `q=기생` → 기생충(28곳)·음란 기생(1곳) — 관련도 정렬 동작
- `resolve("만추")` → 1981·1966 / `resolve("중구")` → **6개** / `"서울 중구"` → **1개**
- 강릉시 70곳 → `?content_id=559`(관상) → **1곳(강릉선교장)** — 유저플로우 4b 실동작
- 강릉 반경 5km → 44곳, `distance_km` 오름차순
- 에러: 반경 초과 `400` · 없는 작품/지역 `404` · 빈 결과 `200 total=0`

### 트러블슈팅 기록
- **`func.case`는 없다**: SQLAlchemy 2.0에서 CASE는 `sqlalchemy.case`를 직접 import해야 한다.
  `func.case(...)`로 쓰면 DB에 `case(...)` 함수 호출로 나가 실패한다.
- **geography에 ST_X/ST_Y 불가**: PostGIS의 ST_X/ST_Y는 geometry용이라 `cast(col, Geometry)`가 필요하다.
- **TestClient + async 엔진 조합 주의**: `fastapi.testclient.TestClient`는 요청마다 이벤트 루프를 새로
  만들어서, 커넥션 풀에 남은 asyncpg 연결이 죽은 루프에 묶이며 두 번째 요청부터
  `'NoneType' object has no attribute 'send'`가 난다. **코드 버그가 아니라 테스트 방식 문제.**
  검증은 `httpx.ASGITransport`로 단일 루프 안에서 돌렸다. (uvicorn 운영은 루프가 하나라 무관.)
- **계약서의 예시 id는 실제 값으로**: 처음엔 `content_id: 77`처럼 임의 값을 적었는데, 그대로 호출하면
  0건이 나와 팀원이 혼란스러워진다. 실제 id(관상=559, 강릉선교장=2193)로 교체했다.

---

## 4단계 — TourAPI 키 연동 + ★매칭 전략 전면 수정 (2026-08-15) 🔶

### 키 연동 결과
data.go.kr 개발계정 인증키를 `.env`에 넣고 실호출 검증 완료. detailCommon·detailImage까지 정상.
- **Encoding 키를 그대로 넣으면 안 된다.** httpx가 파라미터를 한 번 더 인코딩해 `%2B`→`%252B`가 되어
  전부 실패한다. **URL 디코딩한 형태**(`+`, `/`, `=` 그대로)를 `.env`에 넣어야 한다.
- 승인된 3개 서비스(국문 관광정보·관광공모전 사진 수상작·연관 관광지)가 **인증키 하나를 공용**한다.

### ★ 발견 1 — KorService1은 폐기됐다
`KorService1/searchKeyword1` → `NO_OPENAPI_SERVICE_ERROR`("해당 오픈API 서비스가 없거나 폐기됨").
**`KorService2` + `~2` 오퍼레이션**을 써야 한다. 인터넷의 예제 상당수가 구버전이라 그대로 쓰면 실패한다.

### ★ 발견 2 — locationBasedList2가 관광지(contenttypeid=12)를 반환하지 않는다 ⚠️
원래 4단계 계획은 "우리 좌표로 반경 검색해서 TourAPI contentid를 찾는다"였는데 **이 방식이 통하지 않는다.**

검증 (강릉선교장 기준):
- 우리 좌표 vs TourAPI 좌표 = **7m 차이** (좌표 자체는 거의 완벽히 일치)
- `searchKeyword2("선교장")` → 「강릉 선교장」 contentid=125800 **찾음**
- `locationBasedList2` 반경 1km/2km/5km → **선교장 없음.** `contentTypeId=12`를 명시해도 **0건**
- 반환된 타입 분포: 39(음식점)·38(쇼핑)·28(레포츠)·14(문화시설)·32(숙박) — **12(관광지)만 통째로 빠짐**

→ **매칭 주(主) 수단을 좌표에서 이름으로 뒤집었다.**
   ① `searchKeyword2`(이름 변형) → ② 후보의 좌표가 우리 것과 500m 이내인지로 **검증** → 채택.
   `locationBasedList2`는 매칭용이 아니라 **"촬영지 주변 맛집·카페" 보강용**으로 용도 변경.

### ★ 발견 3 — 이름이 정확히 일치하지 않는다
TourAPI는 「강릉 선교장」(공백 있음), 우리 CSV는 「강릉선교장」(붙임) → 완전일치 검색이 0건.
`searchKeyword2("강릉선교장")`=0건 / `searchKeyword2("선교장")`=1건.
→ 이름 변형(괄호 제거, 지역 접두 절단)을 순차 시도하는 방식이 필요하다.

### 실측 매칭 적중률 — 47%
촬영 횟수 상위 15곳에 이름검색+좌표검증(≤500m)을 적용한 결과 **7/15 적중** (API 42회 소모).
- 성공: 인천국제공항 · 부산영화촬영스튜디오 · 합천영상테마파크 · 서대문형무소역사관 ·
  용산역사박물관 · 한국민속촌 · 설매재자연휴양림
- 실패: 남양주종합촬영소 · DMC첨단산업센터 · YTN본사 · 익산 교도소 세트장 · 스튜디오112 ·
  문화역서울284 · 부안영상테마파크 · 올림픽공원

실패 상당수는 **애초에 관광지가 아니다**(방송사 사옥·촬영 스튜디오·세트장). 다만 올림픽공원·
문화역서울284처럼 실재하는데 놓친 것도 있어 이름 변형 규칙을 더 다듬으면 올라갈 여지가 있다.

### 그래서 계약서가 맞았다
`GET /places/{id}`의 `detail`이 **null일 수 있다**고 계약에 명시해둔 게 정확했다.
실측상 **촬영지의 절반 가까이는 TourAPI에 없다.** FE의 "상세정보 없음" UI는 예외 처리가 아니라
**정상 경로**로 다뤄야 한다.

### 트러블슈팅
- **Shapely 미설치**: `geoalchemy2.shape.to_shape()`는 선택 의존성 Shapely를 요구한다.
  좌표는 SQL에서 `ST_Y(geom::geometry)`로 뽑으면 되므로 의존성을 추가하지 않고 스크립트를 수정했다.
