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

## 다음 단계 (2단계 마무리)
1. **Alembic 초기화** — async 템플릿으로 `alembic/`·`alembic.ini` 생성 (완료).
2. **첫 마이그레이션 작성** — autogenerate 후 **수동 보정**: `CREATE EXTENSION postgis/pg_trgm`, enum, trgm GIN 인덱스, 공간 인덱스, `nulls_not_distinct` 확인. *(적용 전 검토)*
3. **`alembic upgrade head`** → 실제 DB에 12개 테이블 생성·검증.
