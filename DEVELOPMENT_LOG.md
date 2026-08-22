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

---

## 코드 구조 재편 — 계층별 → 기능별 (2026-08-16)

`routers/`·`services/`·`schemas/`로 나뉜 계층 구조는 파일 수가 적을 땐 깔끔하지만, 기능 하나를
고치려면 세 폴더를 오가야 한다. 특히 `services/catalog.py`가 작품·지역·장소 질의를 444줄로
떠안고 있어서 3단계(auth)·6단계(courses)가 들어오면 계속 부풀 구조였다.

기능 하나 = 폴더 하나(`router.py`+`service.py`+`schema.py`)로 바꿨다.

### 결정 — models/는 옮기지 않는다
기능별 구조의 교과서적 형태는 모델도 기능 폴더에 넣는 것이지만 여기선 안 맞는다.
- Alembic이 `app/models/__init__.py`를 읽어 마이그레이션을 만든다. 흩어 놓으면 등록 누락이 곧 스키마 사고다.
- `content_place_mappings`는 contents·places를 **동시에** FK로 참조한다. 어느 기능의 소유도 아니다.

### 기능 간 의존 방향
```
contents.router ─┐
regions.router  ─┼─→ places.service ──→ regions.service   (region_ref · region_scope_ids)
places.router   ─┘         └──→ contents.schema (ContentOnPlace)
```
'장소 목록 조립'의 주인을 places로 정했다. 작품 화면·지역 화면의 장소 목록도 결국 같은 조립이라
세 군데에 복제하는 것보다 낫다. schema는 leaf라 순환이 없다.

### 함정 — `__init__.py`에서 router 재수출 금지
처음엔 `features/contents/__init__.py`에 `from .router import router`를 넣어 `main.py`를 짧게
쓰려 했다. 이러면 `router.py`가 `from app.features.contents import service`를 할 때 패키지가
**부분 초기화 상태**라 순환 참조 위험이 생긴다. `main.py`가 `router.py`를 직접 import하도록 바꿨다.

### 검증
리팩터링 전 기록과 응답을 1:1 대조했다 — q=기생 2건 · 관상(559) 촬영지 24곳 ·
resolve(중구) 6개 / (서울 중구) 1개 · 강릉(18) 70곳 → content_id 필터 1곳 ·
반경 5km 44곳 · 400/404 동일. 동작 변화 없음.

---

## 4단계 — TourAPI 실시간 연동 완료 (2026-08-16) ✅ ★합격 핵심★

### 설계 — 호출 입증을 '잊을 수 없게' 만들기
`api_call_logs` 기록을 호출부에 맡기면 언젠가 빠뜨린다. 그리고 그 누락이 곧 실격이다.
그래서 기록을 `TourApiClient._get` **안**에 넣었다. 클라이언트를 거치면 무조건 남는다.

DB 저장은 분리했다(`integrations/call_log.py`). 클라이언트는 DB를 모르고 메모리에만 쌓는다.
→ 클라이언트 테스트에 DB가 필요 없고, 저장 정책을 한 곳에서 바꿀 수 있다.
저장은 `try/finally`라 예외가 나도 기록이 남는다 — '호출을 시도했다'는 사실 자체가 입증 자료다.

### ⚠️ 발견 — httpx가 인증키를 로그에 흘린다
실호출 로그를 보다가 발견했다.
```
INFO httpx: HTTP Request: GET ...KorService2/searchKeyword2?serviceKey=cvFOcS8at... "200 OK"
```
httpx는 INFO 레벨에서 요청 URL을 통째로 남기는데, TourAPI는 serviceKey를 **쿼리스트링**으로
받는다. 로그 파일은 공유·커밋되기 쉬우므로 이건 실질적인 키 유출이다(§3.3 위반).
→ `integrations/tour_api.py` 모듈 로드 시 `logging.getLogger("httpx").setLevel(WARNING)`.
   TourAPI를 쓰는 모든 경로(앱·배치)가 이 모듈을 거치므로 여기서 막으면 샐 곳이 없다.
   `api_call_logs`엔 애초에 serviceKey를 안 넣는다(검증: 유출 행 0건).

### ⚠️ 함정 — alembic autogenerate가 인덱스 3개를 지우려 했다
`api_call_logs` 마이그레이션을 만들었더니 이런 게 딸려 나왔다.
```python
op.drop_index('ix_cpm_place_id', ...)
op.drop_index('ix_contents_genre_tags', ..., postgresql_using='gin')
op.drop_index('ix_places_region_id', ...)
```
이 인덱스들은 이전 마이그레이션에서 `op.create_index`로 **직접** 만들었고 모델엔 선언이 없었다.
autogenerate는 "모델에 없는데 DB에 있다 → 군더더기"로 판단한다. 그대로 적용했으면
N+1 방지 쿼리와 지역 조회, 장르 GIN 필터가 전부 느려졌을 것이다.

그냥 drop 줄을 지우는 건 반쪽짜리다 — **다음 마이그레이션마다 똑같이 재발**하고, 언젠가는
못 보고 넘어간다. 모델 `__table_args__`에 `Index(...)`를 선언해 근본 수정했다.
교훈: **마이그레이션에서만 만든 인덱스는 시한폭탄이다. 모델에도 반드시 선언한다.**

### ⚠️ 오탐 — 좌표만으로는 매칭이 안 된다
사전매칭 배치를 돌렸더니 이런 게 나왔다.
```
서울역 → 게스 롯데아울렛 서울역점 [3305814] 95m   ← 아울렛 안 옷가게
서울역 → 다이소 서울역점          [4027213] 95m   ← 생활용품점
```
좌표 500m 검증은 통과한다. 도심은 500m 안에 무관한 시설이 수십 개고, 상업시설은
"OO 서울역점"처럼 짧은 지명을 통째로 품기 때문이다.
→ **이름 유사도(SequenceMatcher, 공백·구두점 제거 후) 0.7 이상**을 추가 조건으로 걸었다.
   게스 0.43 · 다이소 0.60 탈락 / 강릉 선교장·합천 영상테마파크·용산역사박물관 1.00 통과.
   후보가 여럿이면 유사도 높은 순, 그다음 가까운 순으로 고른다.

### ⚠️ 반대 방향 실패 — 500m는 오히려 좁았다
올림픽공원이 미검출이라 원인을 찍어봤다.
```
올림픽공원        거리=  663m 유사도=1.00  ← 거리초과로 탈락
수원올림픽공원     거리=30041m 유사도=0.83
올림픽공원(창원)   거리=290177m 유사도=0.83
```
넓은 장소는 **우리 촬영지점과 공사 대표좌표가 수백 m 벌어진다**(공원·휴양림·궁궐).
거리 검증이 실제로 막아주는 건 '이름 같은 다른 지역'(30km·290km)이라 1km로 넓혀도 안전하다.
근처 엉뚱한 시설은 거리가 아니라 유사도가 막는다. → **1km로 완화**. 올림픽공원·광안대교 매칭 성공.

### ⚠️ 쿼터 구멍 — 실패를 기억하지 않으면 한도가 마른다
촬영지의 절반 가까이는 관광지가 아니다. 그런데 매칭 실패를 기록하지 않으면 그 장소를 열 때마다
이름검색 3회를 다시 태운다. 남양주종합촬영소(촬영 118회)처럼 **인기 있는데 매칭 안 되는 곳**이
특히 위험하다 — 하루 333회 조회면 1,000건 한도가 그대로 소진된다.
→ `places.tour_matched_at`(시도 시각) 추가. 30일 내 재시도 안 함.
   검증: 같은 장소 1회차 3건 → **2회차 0건**.
   무캐싱 규정과 무관하다 — TourAPI 응답 본문이 아니라 '우리가 언제 시도했나'는 자체 기록이다.

### 실측 매칭 결과 — 16곳 중 11곳(69%)
초기 47%에서 올랐다(괄호제거 변형 + 1km 완화).
미검출 5곳은 방송사 사옥·촬영 스튜디오·세트장·병원·역사(驛舍)로 **애초에 관광지가 아니다**.
계약서의 "`detail`은 null일 수 있다"가 예외가 아니라 정상 경로임이 다시 확인됐다.

### 호출 예산
| 상황 | 호출 |
|---|---|
| 미매칭 장소 첫 조회 | 최대 6건 (이름검색 3 + 상세·소개·이미지 3) |
| 매칭된 장소 조회 | 3건 |
| 매칭 실패가 기억된 장소 | **0건** (상세도 없으므로) |

### 트러블슈팅
- **`detailCommon2`엔 운영시간이 없다.** 계약서가 약속한 `use_time`·`rest_date`를 채우려면
  `detailIntro2`를 따로 호출해야 하고, `contentTypeId`가 필수다(detailCommon2 응답에서 얻는다).
  게다가 필드명이 타입마다 다르다 — 관광지 `usetime`, 음식점 `opentimefood`, 쇼핑 `opentime`…
  → `_INTRO_FIELDS` 맵으로 흡수해 계약서의 이름 하나로 통일했다.
- **`homepage`는 앵커 태그로 온다.** `<a href="http://...">...</a>` 그대로 내보내면 앱이 파싱해야
  한다 → href만 뽑아 URL로 정규화. `overview`의 `<br>`도 걷어낸다.

---

## 3단계 — 인증: 회원가입·로그인·로그아웃 + 소셜 (2026-08-22) ✅

브랜치 `eunseo` / 커밋 `160ea64` / 마이그레이션 `9a1c7d2e5b40`

### 왜 지금 했나
백엔드를 둘로 나눴다(팀원=지도 API 지역 구분 `yoon`, 나=인증 `eunseo`). 인증은 6단계 코스
저장(`POST /courses` 🔒)의 **선행 조건**이라, 코스보다 먼저 끝내야 6단계가 막히지 않는다.
그리고 인증은 다른 기능과 파일이 거의 겹치지 않아 **병렬 작업에 가장 안전한 단위**다
(겹치는 건 `models/user.py`·`deps/`·`main.py` 세 곳뿐).

### 무엇을
계약서에 적혀 있던 "소셜 3종"에서 범위가 늘었다.
- **일반 회원가입 추가** — 이메일+비밀번호. 사용자 요청으로 이메일 인증(6자리 코드)까지.
- **로그아웃 신설** — 계약서엔 없던 기능. 이게 토큰 구조를 바꾸게 만들었다(아래).
- 엔드포인트 **10종**: `email/send-code`·`email/verify-code`·`signup`·`login`·`google`·`kakao`
  ·`refresh`·`logout`·`logout-all`🔒·`me`🔒

### 왜 그렇게 설계했나 (핵심 판단들)

**① 토큰을 2개로 쪼갰다 — 로그아웃 때문이다.**
계약서의 원래 설계는 "14일짜리 JWT 1개"였다. 그런데 JWT는 서버가 저장하지 않고 서명만
검증한다. 발급 목록이 없으니 **"이 토큰 무효"라고 표시할 데가 없다.** 로그아웃 버튼을 눌러도
서버가 할 수 있는 게 없고, 유출된 토큰은 14일간 그대로 살아 있다.

| | access | refresh |
|---|---|---|
| 정체 | JWT | 난수 48바이트 |
| 수명 | **1시간** | **30일** |
| 저장 | 안 함 | `refresh_tokens`에 **SHA-256 해시로** |
| 취소 | 불가 | 가능 → **이게 로그아웃** |

이러면 "짧은 수명(안전)"과 "자동 로그인 유지(편의)"를 동시에 얻는다. 무상태 1토큰은
둘 중 하나를 포기해야 하는 구조였다.

**② refresh를 회전시킨다.** 재발급할 때마다 옛 refresh를 즉시 폐기하고 새것을 준다.
안 그러면 유출된 refresh 하나로 30일 내내 access를 뽑아낼 수 있다.

**③ 재사용 감지 — 폐기된 refresh가 다시 오면 전 세션을 끊는다.**
정상 앱은 새 토큰을 받아 갔으므로 옛것을 다시 쓸 이유가 없다. 즉 그 요청은
"토큰을 복사해 둔 누군가"일 가능성이 높다. 누가 진짜인지 구분할 방법이 없으니
**둘 다 끊고 재로그인시키는 게 유일하게 안전한 선택**이다.

**④ refresh는 bcrypt가 아니라 SHA-256이다.** 비밀번호와 성격이 다르다.
난수 48바이트라 사전공격 대상이 아니고(느리게 만들 이유가 없다), `WHERE token_hash = ?`로
**조회 키**로 써야 해서 매번 같은 값이 나와야 한다. bcrypt는 매번 salt가 달라 조회가 안 된다.

**⑤ 비밀번호는 passlib이 아니라 bcrypt 직접.** passlib은 유지보수가 멈췄고 최신 bcrypt와
버전 경고가 난다. 어차피 쓰는 함수가 `hashpw`/`checkpw` 둘뿐이라 래퍼가 필요 없다.

**⑥ users를 한 테이블로 유지하고 CHECK 제약을 걸었다.**
가입 경로별로 테이블을 나누면 `courses.user_id` FK가 어디를 봐야 할지 갈라진다.
대신 경로마다 채워지는 칼럼이 달라지므로 DB가 직접 막게 했다 —
`local`이면 email·password_hash 필수 + provider_user_id는 NULL, 소셜이면 그 반대.

**⑦ 이메일은 전역 UNIQUE.** 같은 주소로 구글 가입 후 다시 일반 가입하면 계정이 둘로 쪼개져
"내 코스가 사라졌다"가 된다. 중복이면 409로 막고 **어느 경로로 가입했는지 알려준다.**
계정 존재를 노출하는 트레이드오프지만, 안 알려주면 사용자가 영원히 헤맨다. 회원가입은
어차피 중복을 알려줘야 하므로 숨겨서 얻는 실익도 없다.

**⑧ 로그인 실패는 계정없음·비번틀림을 같은 문구로.** 다르게 답하면 이메일 목록을 대입해
가입 여부를 캐낼 수 있다. 단 **소셜 가입자에게는 예외적으로 알려준다**(409) — 그 사람은
비밀번호 자체가 없어서 아무리 시도해도 영원히 못 들어간다.

**⑨ 소셜은 앱 SDK 토큰 전달 방식.** 프론트가 안드로이드 앱이라 이게 맞다. 서버 OAuth
리다이렉트는 웹용이고, 앱에선 웹뷰가 떠서 UX가 나쁘며 redirect_uri 등록·관리가 붙는다.
이 방식은 **client secret도 redirect_uri도 필요 없다.**

**⑩ 소셜 검증에서 진짜 중요한 건 "우리 앱 토큰인가"다.** 토큰이 진짜인지만 보면 부족하다 —
아무 앱에서 발급된 구글/카카오 토큰도 "진짜"이기 때문이다. 구글은 `aud`, 카카오는 `app_id`를
우리 것과 대조한다. 설정이 비면 건너뛰되 **경고 로그를 남긴다**(개발 편의 vs 배포 사고 방지).

**⑪ users 행은 이메일 인증이 끝난 뒤에 만든다.** 먼저 만들면 인증을 포기한 유령 계정이
쌓이고, 그 주소로 나중에 진짜 가입하려는 사람을 막는다.

**⑫ 인증코드는 시도 횟수를 대조 *전에* 올린다.** 나중에 올리면 틀렸을 때 응답을 중간에
끊는 식으로 카운트를 회피할 수 있다. 6자리는 100만 조합이라 횟수 제한이 유일한 방어다.

**⑬ SMTP 미설정이면 코드를 로그와 응답(`dev_code`)으로 내보낸다.** 메일 계정 발급을
기다리느라 개발이 멈추지 않게. `.env`만 채우면 코드 수정 없이 실제 발송으로 바뀐다.

### 어떻게 (구조)
기능 폴더 하나에 인증 전체를 모았다.
```
app/features/auth/
  router.py   엔드포인트 10종 (얇게 — 판단은 service로)
  service.py  가입/로그인 판단, 토큰 발급·회전·폐기
  schema.py   요청·응답 계약
  social.py   구글·카카오 검증 어댑터
  mailer.py   인증코드 발송 (SMTP 미설정 시 로그 출력)
app/core/security.py   JWT 2종 · refresh 해시 · bcrypt · 인증코드  ← 암호 '기술'만
app/deps/__init__.py   get_current_user + CurrentUser/OptionalUser/DbSession 별칭
app/models/auth.py     refresh_tokens · email_verifications
```
`social.py`를 `integrations/`가 아니라 `features/auth/` 안에 둔 이유: TourAPI는 여러 기능이
쓰는 공용 어댑터지만, 소셜 검증은 **인증만 쓴다.** 쓰는 곳이 하나면 그 옆에 두는 게 맞다.

6단계에서 코스에 로그인을 붙이는 건 이제 한 줄이다.
```python
from app.deps import CurrentUser
async def create_course(user: CurrentUser, ...):  # 여기 오면 이미 인증됨
```

### 검증
[`scripts/check_auth.py`](./scripts/check_auth.py) — 실제 서버에 호출하는 38케이스. **전부 통과.**
성공 경로뿐 아니라 **막혀야 할 것이 막히는지**를 같이 본다.

| 확인 | 결과 |
|---|---|
| 인증 없이 가입 시도 | `403` |
| 코드 5회 오입력 · 60초 내 재발송 | `429` |
| 8자 미만 · 숫자 없는 비밀번호 | `422` |
| 없는 계정 vs 틀린 비밀번호 | **같은 401 문구** |
| 이메일 대소문자(`Kim@x.com`=`kim@x.com`) | 통과 |
| refresh를 출입증으로 사용 | `401` (토큰 혼동 차단) |
| 이미 쓴 refresh 재사용 | `401` + **전 세션 차단** 확인 |
| 로그아웃한 refresh로 재발급 | `401` |
| 로그아웃 재호출 | `200` (멱등) |
| 위조 구글·카카오 토큰 | `401` |

pytest는 여전히 0개(8단계 과제). 소셜 **정상** 경로는 앱에 SDK가 붙어야 확인 가능하다.

### 트러블슈팅·함정 기록

- **★PostgreSQL enum에 값 추가 — `autocommit_block` 없으면 실패한다.**
  Alembic은 마이그레이션 전체를 한 트랜잭션으로 감싸는데, PG는 **새로 추가한 enum 값을
  같은 트랜잭션 안에서 사용하지 못하게** 막는다. `auth_provider`에 `local`을 넣고 곧바로
  `auth_provider = 'local'`을 참조하는 CHECK 제약을 걸면 *unsafe use of new value* 로 죽는다.
  → `with op.get_context().autocommit_block():` 안에서 `ALTER TYPE ... ADD VALUE IF NOT EXISTS`.
  참고로 **enum에서 값을 빼는 문법은 PostgreSQL에 없다** — downgrade는 타입을 새로 만들어
  갈아끼우는 방식이고, local 사용자가 남아 있으면 실패한다(데이터를 지우지 않기 위한 의도).

- **★`op.create_check_constraint`는 명명규칙을 한 번 더 적용한다.**
  `alembic.ini`의 `ck_%(table_name)s_%(constraint_name)s` 때문에 `"ck_users_provider_fields"`를
  넘겼더니 실제로 만들어진 이름이 **`ck_users_ck_users_provider_fields`**였다.
  → `op.f("ck_users_provider_fields")`로 감싸야 한다(op.f = "이 이름은 이미 완성됐다" 표시).
  인덱스·UNIQUE는 규칙이 칼럼명 기반이라 우연히 같은 이름이 나와 티가 안 났다 —
  **`\d 테이블`로 실제 생성된 이름을 눈으로 확인하는 습관이 필요하다.**

- **bcrypt는 72바이트까지만 본다.** 초과분이 조용히 잘려 서로 다른 긴 비밀번호가 같은 것으로
  취급된다. → 스키마에서 `max_length=72` + UTF-8 바이트 길이까지 검사(한글은 글자당 3바이트라
  24자만 넘어도 걸린다).

- **구글 `tokeninfo`는 값을 전부 문자열로 준다.** `email_verified`가 `true`가 아니라 `"true"`다.
  bool로 비교하면 **항상 False**가 된다. → `str(...).lower() == "true"`.

- **카카오 이메일은 선택 동의 항목이다.** 동의 안 하면 응답에 아예 안 온다. 게다가 사업자
  심사를 통과해야 항목을 켤 수 있어 개발 중엔 대개 없다. → `user.email`이 **null인 게 정상**.
  계약서와 FE 체크리스트에 명시했다.

- **Windows 콘솔(cp949)이 검증 스크립트 출력을 깨뜨린다.** `—`·`→` 같은 문자에서
  `UnicodeEncodeError`로 스크립트가 죽었다. → `sys.stdout.reconfigure(encoding="utf-8")`.

- **curl로 한글 JSON 본문을 보내면 깨진다.** `{"nickname":"은서"}`가 서버에서
  *There was an error parsing the body* 로 400이 됐다(셸이 cp949로 인코딩). 임시방편을 찾는
  대신 **파이썬 검증 스크립트로 전환**했고, 결과적으로 재실행 가능한 자산이 남았다.
