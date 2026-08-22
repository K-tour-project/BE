# K-tour BE — 프로젝트 구성 상세 설명서

> 백엔드가 **어떻게 구성돼 있는지**를 파일·테이블·엔드포인트 단위까지 설명한다.
> 처음 보는 사람이 이 문서 하나로 구조를 파악하고, 어디를 고쳐야 할지 찾을 수 있게 쓴다.
>
> 최종 갱신 **2026-08-22** (3단계 인증 완료 시점) · 마이그레이션 리비전 `9a1c7d2e5b40`
>
> 관련 문서 — 전체 경과: [`DEV_SUMMARY.md`](./DEV_SUMMARY.md) · 현황 스냅샷: [`PROGRESS.md`](./PROGRESS.md)
> · 판단 근거 상세: [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md) · 팀 API 약속: [`API_CONTRACT.md`](./API_CONTRACT.md)

---

## 목차

| # | 내용 |
|---|---|
| [1](#1-프로젝트-개요와-역할-경계) | 프로젝트 개요와 역할 경계 |
| [2](#2-시스템-구성도) | 시스템 구성도 — 누가 누구를 부르는가 |
| [3](#3-기술-스택--무엇을--왜) | 기술 스택 — 무엇을 · 왜 |
| [4](#4-폴더--파일-구성) | 폴더 · 파일 구성 (파일별 역할) |
| [5](#5-계층-설계--요청이-흐르는-길) | 계층 설계 — 요청이 흐르는 길 |
| [6](#6-데이터베이스-구성) | 데이터베이스 구성 (10테이블 전부) |
| [7](#7-api-구성-19종) | API 구성 (19종) |
| [8](#8-핵심-플로우-5가지) | 핵심 플로우 5가지 |
| [9](#9-외부-연동-구성) | 외부 연동 구성 |
| [10](#10-공모전-컴플라이언스--어디에-어떻게-구현했나) | 공모전 컴플라이언스 대응 매핑 |
| [11](#11-개발-진행-경과) | 개발 진행 경과 |
| [12](#12-작업-워크플로우) | 작업 워크플로우 |
| [13](#13-실행--검증-방법) | 실행 · 검증 방법 |
| [14](#14-남은-일) | 남은 일 |

---

## 1. 프로젝트 개요와 역할 경계

### 앱
**Every Trip** — 영화·드라마 **촬영지 기반 관광 코스 앱**.
작품 제목이나 지역을 검색하면 지도에 촬영지와 포스터 마커가 뜨고, 가고 싶은 곳을 여러 개 고르면
최적 동선으로 코스를 짜준다.

### 이 레포(BE)의 책임
모바일 앱(Kotlin)과 AI 챗봇(팀원)이 호출하는 **REST API 서버 + 데이터베이스**.

### 역할 경계 (누가 무엇을 소유하나)

```
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  FE (윤영)     │   │  AI (조시현)   │   │  BE (김은서)   │
│  Kotlin 안드로 │   │  챗봇·NLU·LLM  │   │  이 레포       │
│  이드 앱       │   │  별도 서비스    │   │               │
└───────┬───────┘   └───────┬───────┘   └───────────────┘
        │                   │
        └─────── REST ──────┴────────────→  BE
```

- **AI 경계**: 챗봇·대화 세션·자연어이해·LLM 호출은 **전부 팀원의 별도 서비스**가 소유한다.
  이 백엔드는 **AI-불가지론**이며, 챗봇이 부를 REST 3종만 제공한다.
  `POST /contents/resolve` · `GET /regions/resolve` · `POST /courses/recommend`(6단계)
- **백엔드 내부 분업** (2026-08-22~): 인증=김은서(`eunseo` 브랜치), 지도 API 지역 구분=팀원(`yoon` 브랜치)

### 프로젝트 전체를 지배하는 사실

> **한국관광공사 TourAPI에는 "영화 ↔ 촬영지" 매핑이 없다.**

- 작품↔장소 연결(`content_place_mappings`)은 **우리가 직접 큐레이션** → 이 앱의 차별점이자 핵심 자산
- TourAPI는 **"장소의 여행정보"(주소·운영시간·이미지) 백본**으로만 쓴다

이 전제가 데이터 모델·API 설계·컴플라이언스 대응을 전부 결정했다.

---

## 2. 시스템 구성도

```
        ┌──────────────────┐        ┌──────────────────┐
        │  모바일 앱 (FE)   │        │  AI 챗봇 (팀원)   │
        │  Kotlin/안드로이드│        │  NLU·LLM         │
        └────────┬─────────┘        └────────┬─────────┘
                 │                            │
                 │  HTTPS / JSON (snake_case) │
                 │  Authorization: Bearer     │
                 ▼                            ▼
    ╔═══════════════════════════════════════════════════════╗
    ║           K-tour BE   (FastAPI + uvicorn)             ║
    ║                                                       ║
    ║   app/main.py  ─ 라우터 등록                           ║
    ║        │                                              ║
    ║        ├─ features/auth      회원가입·로그인·소셜       ║
    ║        ├─ features/contents  작품 검색·상세             ║
    ║        ├─ features/regions   지역 리졸브·목록           ║
    ║        ├─ features/places    촬영지·반경·상세           ║
    ║        ├─ features/health    헬스체크                   ║
    ║        └─ features/courses   (6단계 예정)               ║
    ╚════════╤═══════════════════════════════╤══════════════╝
             │                                │
             ▼                                ▼
  ┌────────────────────────┐   ┌──────────────────────────────┐
  │ PostgreSQL 16 + PostGIS│   │  외부 API (httpx async)       │
  │ Docker: ktour-db       │   │                              │
  │                        │   │  ① KTO TourAPI ×3 ⚠️합격핵심  │
  │ · 우리 큐레이션 데이터   │   │     KorService2               │
  │   (작품·장소·매핑)      │   │     PhotoGalleryService1      │
  │ · 사용자·인증           │   │     TarRlteTarService1        │
  │ · 호출 입증 로그        │   │  ② Google  tokeninfo          │
  │                        │   │  ③ Kakao   kapi.kakao.com     │
  │ ※ TourAPI 응답 본문은   │   │  ④ SMTP    인증코드 메일       │
  │    저장하지 않는다      │   │                              │
  └────────────────────────┘   └──────────────────────────────┘
```

### 데이터 소유 경계 ⚠️ (가장 중요한 설계선)

```
┌─ 우리 DB에 저장한다 ─────────────────────┐  ┌─ 절대 저장하지 않는다 ───────────┐
│  ★ 작품↔장소 매핑 (큐레이션 자산)          │  │  TourAPI 응답 본문               │
│    contents · places · mappings          │  │   운영시간·전화·개요·이미지        │
│    ← data.csv (KMDb+TMDB) 13,761행       │  │   → 매 요청 실시간 호출           │
│                                          │  │                                  │
│  외부 참조 ID만                           │  │  serviceKey (인증키)              │
│    tour_content_id · kmdb_code · tmdb_id │  │   → .env에만. 로그에도 안 남김     │
│    poster_url (URL 문자열)                │  │                                  │
│                                          │  │  raw GPS 좌표                    │
│  사용자 데이터                            │  │   → 입력은 place_id/region_id 정수│
│    users · courses · refresh_tokens      │  │                                  │
│                                          │  │  이미지 파일                      │
│  호출 입증 메타데이터 (본문 제외)          │  │   → URL만 전달, 다운로드 금지     │
│    api_call_logs                         │  │                                  │
└──────────────────────────────────────────┘  └──────────────────────────────────┘
        왼쪽 = 차별점                                    오른쪽 = 실격 방지선
```

`places` 테이블에 운영시간 컬럼이 없는 것은 **빠뜨린 게 아니라 의도적으로 안 만든 것**이다.

---

## 3. 기술 스택 — 무엇을 · 왜

| 영역 | 선택 | 버전 | 왜 이걸 골랐나 |
|---|---|---|---|
| 언어 | Python | 3.11 | 팀 역량 + 데이터 처리 생태계 |
| 프레임워크 | **FastAPI** | 0.138 | ① 외부 API를 **비동기 동시 호출**하는 게 이 앱의 주 업무 ② `/docs` 자동 생성 → 팀원이 서버 코드 없이 테스트 ③ Pydantic이 요청 검증을 스키마로 해결 |
| 서버 | uvicorn | — | FastAPI 표준 ASGI 서버 |
| DB | **PostgreSQL + PostGIS** | 16 / 3.4 | 세 가지를 **한 DB에서** — 작품↔장소 M:N · "반경 20km" 지오 쿼리 · 한글 부분검색 |
| DB 구동 | Docker Compose | — | `docker compose up -d` 한 줄로 PostGIS 내장 DB가 통째로. 손으로 설치하면 인코딩·확장에서 막힘 |
| ORM | **SQLAlchemy (async)** | 2.0.51 | FastAPI가 async라 DB도 async여야 이점이 산다 |
| DB 드라이버 | asyncpg | 0.31 | SQLAlchemy async용 PostgreSQL 드라이버 |
| 마이그레이션 | **Alembic** | 1.18 | 스키마 변경을 코드로. 팀원 DB와 내 DB가 같은 상태임을 보장하는 유일한 수단 |
| 지오 타입 | GeoAlchemy2 | 0.20 | 위경도를 숫자 2개가 아니라 **거리 계산이 되는 타입**(`geography(Point,4326)`)으로 |
| HTTP 클라이언트 | **httpx (async)** | 0.28 | TourAPI·구글·카카오 호출. `requests`는 동기라 이벤트 루프를 멈춘다 |
| JWT | python-jose | 3.5 | access 토큰 서명·검증 |
| 비밀번호 | **bcrypt** | 5.0 | 일부러 느린 해시. passlib을 쓰지 않은 이유는 아래 |
| 이메일 검증 | email-validator | 2.3 | Pydantic `EmailStr` |
| 설정 | pydantic-settings | 2.14 | 비밀값을 코드에서 분리해 `.env` 한 곳으로 |

### 골랐다가 버린 것

| | 왜 안 썼나 |
|---|---|
| **Supabase** | 초기 설계 v1은 Supabase(관리형 PG + Auth + Edge Functions)였다. v2의 적대적 검증에서 굳어진 제약 3가지 — 실시간 호출 입증 · 응답 무캐싱 · 인증키 서버 전용 — 가 **서버를 직접 소유해야 통제되는 것**이라 v3에서 전환 |
| **passlib[bcrypt]** | 파이썬 인증 예제의 표준처럼 쓰이지만 **유지보수가 사실상 멈췄고** 최신 bcrypt와 버전 경고가 난다. 우리가 쓰는 함수는 `hashpw`·`checkpw` 둘뿐이라 래퍼가 감춰줄 복잡함이 없다 |
| **TourAPI 응답 캐싱** | 규정상 비권장. 하려면 운영계정 신청 시 '로컬서버 저장신청서 + 동기화 계획' 승인 필요 |
| **`locationBasedList2`** (좌표 기반 조회) | 실호출 결과 **관광지(`contenttypeid=12`)를 반환하지 않는다** — 매칭에 못 쓴다. 코드에는 남겨뒀지만 '주변 맛집' 보강 용도로만 |

---

## 4. 폴더 · 파일 구성

### 4-1. 전체 트리

```
BE/
├─ app/                       ★ 애플리케이션 코드
│  ├─ main.py                 FastAPI 앱 + 라우터 등록 (새 기능 = 여기 한 줄)
│  │
│  ├─ features/               ★ 기능별. 폴더 하나 = 기능 하나
│  │  ├─ auth/                회원가입·로그인·로그아웃·소셜        (3단계 ✅)
│  │  ├─ contents/            작품 검색·리졸브·상세·촬영지목록      (5단계 ✅)
│  │  ├─ regions/             지역 리졸브·목록·지역내 촬영지        (5단계 ✅)
│  │  ├─ places/              반경 조회 + 장소 상세(TourAPI)       (4·5단계 ✅)
│  │  ├─ health/              헬스체크                            (1단계 ✅)
│  │  └─ courses/             ← 6단계에 추가된다
│  │
│  ├─ integrations/           외부 연동 어댑터 ('기능'이 아니다)
│  │  ├─ tour_api.py          KTO TourAPI 클라이언트 (3개 서비스)
│  │  └─ call_log.py          호출 입증 기록 저장
│  │
│  ├─ core/                   토대 — 설정 · DB 엔진 · 암호 원시도구
│  │  ├─ config.py            .env 로딩 (비밀값은 전부 여기로)
│  │  ├─ db.py                async engine · Base · get_db · 명명규칙
│  │  └─ security.py          JWT 2종 · refresh 해시 · bcrypt · 인증코드
│  │
│  ├─ deps/__init__.py        CurrentUser · OptionalUser · DbSession
│  ├─ shared/schema.py        Location · RegionRef · Page (공통 응답 모양)
│  └─ models/                 ★ 옮기지 않음 (아래 설명)
│
├─ alembic/                   마이그레이션 (versions/ 에 5개)
├─ scripts/                   실행 스크립트 3종
├─ data/data.csv              ★ 핵심 데이터 자산 (14.7MB, git untracked)
│
├─ docker-compose.yml         PostgreSQL+PostGIS 컨테이너
├─ requirements.txt           의존성
├─ .env / .env.example        비밀값 (.env는 git 제외)
├─ erd.dbml                   ERD
└─ *.md                       문서 6종 (§12-3 참조)
```

### 4-2. `app/features/` — 기능 하나 = 폴더 하나

각 폴더는 **`router.py` + `service.py` + `schema.py`** 3종이 기본이고, 필요하면 파일을 더 둔다.

| 폴더 | 파일 | 역할 |
|---|---|---|
| **auth/** | `router.py` | 엔드포인트 10종. 얇게 — 판단은 service로 넘긴다 |
| | `service.py` | 가입/로그인 판단, 토큰 발급·회전·폐기, 인증코드 검사 |
| | `schema.py` | 요청·응답 계약 + 비밀번호 규칙(8자↑, 영문+숫자, ≤72바이트) |
| | `social.py` | 구글·카카오에 "이 토큰 주인 누구야?" 문의 |
| | `mailer.py` | 인증코드 메일 발송. SMTP 미설정 시 로그로 출력 |
| **contents/** | `router.py` | `/contents/*` 4종 |
| | `service.py` | 제목 검색(관련도 점수), 리졸브, 상세 |
| | `schema.py` | `ContentSummary`·`ContentCandidate`·`ContentDetail`·`ContentOnPlace` |
| **regions/** | `router.py` | `/regions/*` 3종 |
| | `service.py` | 지역명 리졸브(시도 힌트 처리), 계층 목록, 하위 지역 ID 수집 |
| | `schema.py` | `RegionCandidate`·`RegionNode` |
| **places/** | `router.py` | `/places` 반경 조회 + `/places/{id}` 상세 |
| | `service.py` | 반경·지역내·작품별 장소 질의 + **TourAPI 실시간 상세 조립** |
| | `schema.py` | `PlaceOnMap`·`PlaceInContent`·`PlaceDetail`·`TourDetail` |
| | `matching.py` | 우리 장소 ↔ 관광공사 관광지 **이름 기반 매칭** 알고리즘 |
| **health/** | `router.py` | `GET /health` |

**`social.py`는 왜 `integrations/`가 아닌가** — TourAPI는 여러 기능(places·courses)이 쓰는 공용
어댑터지만, **소셜 검증은 인증만 쓴다.** 쓰는 곳이 하나면 그 옆에 두는 게 맞다.

### 4-3. `app/core/` — 토대 (DB도 기능도 모른다)

| 파일 | 내용 |
|---|---|
| `config.py` | `Settings` 클래스 하나. `.env`/환경변수를 읽는다. 기본값이 있어 `.env` 없이도 서버가 뜬다. 편의 프로퍼티 `tour_api_ready`·`smtp_ready`·`google_client_ids` |
| `db.py` | 비동기 `engine` · `AsyncSessionLocal`(세션 공장) · `Base`(모델 부모) · `get_db`(의존성) · **명명규칙**(`ix_`/`uq_`/`ck_`/`fk_`/`pk_`) |
| `security.py` | **암호 기술만.** access JWT 발급·검증 / refresh 난수 생성·SHA-256 해시 / 인증코드 생성·대조(`compare_digest`) / bcrypt 해싱·검증 |

`security.py`는 **DB를 아예 import하지 않는다.** 서명하고 해시할 뿐, "누구를 가입시킬지"는
`features/auth/service.py`가 정한다. 이렇게 나누면 암호 부분만 따로 테스트할 수 있다.

### 4-4. `app/models/` — 왜 features 아래로 안 옮겼나

구조를 기능별로 재편할 때 `models/`만 그대로 뒀다. 두 가지 이유다.

1. **Alembic이 여기를 읽는다** — `alembic/env.py`가 `import app.models`로 메타데이터를 모은다.
2. **`content_place_mappings`가 `contents`와 `places`를 동시에 FK로 참조한다** —
   어느 기능에도 속하지 않는다. 억지로 나누면 순환 import가 생긴다.

### 4-5. `scripts/` — 실행 스크립트 3종

| 스크립트 | 역할 | 특징 |
|---|---|---|
| `seed_from_csv.py` | `data/data.csv` 13,761행 → 4개 테이블 분해 적재 | **재실행 안전** — 자연키 `ON CONFLICT DO NOTHING` |
| `match_tour_places.py` | 인기 촬영지를 TourAPI 관광지에 사전 매칭 | `--limit`으로 일일 한도(1,000건) 보호, `--dry-run` 지원 |
| `check_auth.py` | 인증 38케이스 실호출 검증 | 성공 9 + **거부 29** |
| `check_tour_api.py` | TourAPI 키·경로·오퍼레이션 실호출 검증 | 4단계에서 경로 3종 실측에 사용 |

---

## 5. 계층 설계 — 요청이 흐르는 길

### 5-1. 3단 구조

```
   HTTP 요청
      │
      ▼
 ┌──────────────────────────────────────────────────────────┐
 │  router.py   ← 얇게. HTTP 입출구만                         │
 │    · 쿼리·본문 검증은 schema.py(Pydantic)가 자동 처리       │
 │    · 로그인 필요하면 deps의 CurrentUser 한 줄               │
 │    · 어떤 에러 코드가 나올 수 있는지 docstring에 명시        │
 └──────────────────────────────────────────────────────────┘
      │
      ▼
 ┌──────────────────────────────────────────────────────────┐
 │  service.py  ← 판단과 질의가 전부 여기                      │
 │    · "가입시킬 수 있나" "이 토큰이 살아있나" 같은 결정        │
 │    · SQLAlchemy 질의 조립                                  │
 │    · 외부 API 호출 (integrations 경유)                     │
 └──────────────────────────────────────────────────────────┘
      │                                    │
      ▼                                    ▼
 ┌────────────────────┐        ┌──────────────────────────┐
 │ models/ → PostGIS   │        │ integrations/tour_api.py │
 └────────────────────┘        └──────────────────────────┘
      │                                    │
      ▼                                    ▼
 ┌──────────────────────────────────────────────────────────┐
 │  schema.py   ← 응답 모양 (계약서를 코드로 옮긴 것)          │
 └──────────────────────────────────────────────────────────┘
```

**라우터를 보면 "이 API가 무슨 에러를 낼 수 있나"만 읽히고, "왜 그 에러인가"는 service에 있다.**

### 5-2. 실제 예시 — `GET /regions/{id}/places`

```python
# router.py — 얇다
@router.get("/{region_id}/places", response_model=Page[PlaceOnMap])
async def get_region_places(region_id: int, content_id: int | None = Query(None), ...):
    items, total = await places_in_region(db, region_id, content_id, limit, offset, sort)
    if total == 0 and not items:
        if not await service.resolve_region_exists(db, region_id):
            raise HTTPException(404, "해당 지역을 찾을 수 없습니다.")
    return Page[PlaceOnMap](items=items, total=total)
```

- `region_id`가 시도면 **하위 시군구 장소까지** 포함한다(`region_scope_ids`가 재귀 수집)
- `content_id`를 주면 그 작품 촬영지만 남는다 — **필터 전/후 응답 구조는 동일**
- "지역이 없음(404)"과 "장소가 0건(200)"을 구분해준다

### 5-3. 공통 응답 모양 (`app/shared/schema.py`)

```python
class Location(BaseModel):   # 배열이 아니라 객체 — [x,y] 순서 혼동 원천 차단
    lat: float
    lng: float

class RegionRef(BaseModel):  # 다른 응답에 끼워 넣는 지역 요약
    region_id: int
    name: str
    full_name: str           # "전라북도 전주시" — 화면에 그대로 노출 가능

class Page(BaseModel, Generic[T]):   # 목록 응답 고정 형태
    items: list[T]
    total: int
```

### 5-4. 인증 의존성 (`app/deps/`)

```python
CurrentUser  = Annotated[User, Depends(get_current_user)]           # 필수 (없으면 401)
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]  # 선택 (없으면 None)
DbSession    = Annotated[AsyncSession, Depends(get_db)]
```

6단계 코스에 로그인을 붙이는 건 한 줄이다.

```python
async def create_course(user: CurrentUser, db: DbSession, ...):
    ...   # 여기 도달했으면 이미 인증된 사용자
```

### 5-5. N+1 회피

장소 목록에 작품 포스터를 붙일 때 장소마다 질의하면 20개 조회에 21번 쿼리가 나간다.
→ `place_id`를 모아 **한 번에** 조회하고 파이썬에서 묶는다(`_contents_by_place`).
그래서 `ix_cpm_place_id` 인덱스가 가장 뜨거운 경로다.

---

## 6. 데이터베이스 구성

**PostgreSQL 16 + PostGIS 3.4** (Docker 컨테이너 `ktour-db`) · 리비전 `9a1c7d2e5b40` · **활성 10테이블**

### 6-1. 테이블 관계도

```
                    ┌──────────────┐
                    │   regions    │ 자기참조 (시도 → 시군구)
                    │  244행       │◄──┐
                    └──────┬───────┘   │ parent_region_id
                           │           └──┘
                    region_id (SET NULL)
                           │
   ┌──────────────┐        ▼          ┌──────────────┐
   │  contents    │   ┌─────────┐     │    users     │
   │  1,694행     │   │ places  │     │              │
   └──────┬───────┘   │ 9,811행 │     └──┬────────┬──┘
          │           └────┬────┘        │        │
          │ CASCADE        │ CASCADE     │CASCADE │CASCADE
          └───────┬────────┘             │        │
                  ▼                      ▼        ▼
      ┌───────────────────────┐   ┌──────────┐ ┌────────────────┐
      │ content_place_mappings│   │ courses  │ │ refresh_tokens │
      │      13,755행  ★핵심   │   └────┬─────┘ └────────────────┘
      └───────────────────────┘        │ CASCADE
                                       ▼
                                ┌──────────────┐   place_id
                                │ course_places│───(RESTRICT)──→ places
                                └──────────────┘

   독립 테이블:  api_call_logs (user_id SET NULL)  ·  email_verifications
```

### 6-2. 테이블별 상세

#### ① `regions` — 지역 (244행: 시도 17 + 시군구 227)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `region_id` | bigserial PK | |
| `name` | varchar(100) | '경기도' / '용인시' |
| `level` | varchar(10) | `'sido'` \| `'sigungu'` — **문자열**로 둬서 3단계(읍면동) 확장 시 마이그레이션 불필요 |
| `parent_region_id` | FK→self (CASCADE) | 시도 행은 NULL |
| `area_code` · `sigungu_code` | varchar(10), null | ⚠️ **현재 0/244로 비어 있다** |
| `centroid` | geography(Point,4326) | 지도 중심 좌표 (소속 장소들의 평균으로 시드) |

- **UNIQUE `(parent_region_id, name)` + `NULLS NOT DISTINCT`** —
  PostgreSQL은 기본적으로 NULL을 서로 다르게 봐서 시도 행('경기도')이 **두 번 들어갈 수 있다.**
  PG15+ 옵션으로 차단했다.
- `area_code`가 비어 있는 이유: 공모전에서 **지역코드 조회 API(`areaCode2`)가 사용 금지**라
  코드를 API로 받아올 수 없다. 필요해지면 정적 매핑표로 채운다.
  → 이게 **TourAPI ③(기초지자체 중심 관광지) 연동의 선행 과제**다.

#### ② `contents` — 작품 (1,694행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `content_id` | bigserial PK | |
| `content_type` | enum | `movie` \| `drama` \| `show` |
| `title_ko` | varchar(200) | |
| `poster_url` | text, null | **URL 문자열만** (18%가 null) |
| `kmdb_code` | varchar(20) **UNIQUE**, null | KMDb 영화작품코드(K17686) — **재시드 자연키** |
| `source` · `source_url` | | 'KMDb' \| 'manual' \| 'TMDB' |
| `production_year`·`original_title`·`overview` | null | |
| `genre_tags` | **varchar(50)[]** | 배열 컬럼 + **GIN 인덱스** |
| `tmdb_id`·`tmdb_type`·`vote_average`·`runtime` | null | TMDB 보강 |

- **장르를 별도 테이블이 아니라 배열 컬럼으로** — GIN 인덱스로 '이 장르 포함' 필터가 가능해
  조인 없이 끝난다. B-tree로는 배열 포함 검색이 안 된다.
- **드라마 확장을 미리 열어뒀다**: enum에 `drama`/`show`를 남기고, 영화 전용값(`kmdb_code`·`runtime`)은
  nullable, `mappings.episode`(촬영회차)를 미리 생성 → **드라마 추가 시 마이그레이션 없이 INSERT만.**

#### ③ `places` — 촬영지 (9,811행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `place_id` | bigserial PK | |
| `name` | varchar(200) | |
| `geom` | **geography(Point,4326)** | 큐레이션 좌표. **GIST 인덱스** `idx_places_geom` |
| `region_id` | FK→regions (SET NULL) | 인덱스 `ix_places_region_id` |
| `tour_content_id` | varchar(20), null | **TourAPI `contentid`** — 우리 장소 ↔ 관광공사 관광지 연결키 |
| `tour_matched_at` | timestamptz, null | **마지막 매칭 시도 시각 (성공·실패 무관)** |
| `kmdb_place_id` | varchar(30) **UNIQUE**, null | 재시드 자연키 (GG-P-1113) |
| `address` / `road_address` | varchar(300), null | **지번이 기준** |

- ⚠️ **운영시간·전화·개요·이미지 컬럼이 없다.** 무캐싱 규정 때문에 **의도적으로 안 만들었다.**
  옛 설계엔 있었고 그게 실격 사유였다.
- **주소는 지번 기준** — 프로파일링 결과 도로명은 15.4%가 비었고 지번은 0.5%만 비었다.
- **`tour_matched_at`이 왜 필요한가**: 촬영지의 절반 가까이는 관광공사 등록 관광지가 아니다.
  이 기록이 없으면 그런 장소를 열 때마다 이름검색 3회를 다시 태워 일일 한도를 갉아먹는다.
  남양주종합촬영소(촬영 118회)처럼 **인기 있는데 매칭 안 되는 곳**이 특히 위험하다.
  → 30일 내 재시도 안 함. 검증: 같은 장소 1회차 3건 → **2회차 0건.**
  ※ 무캐싱 규정과 무관하다 — TourAPI 응답 본문이 아니라 '우리가 언제 시도했나'는 자체 기록이다.

#### ④ `content_place_mappings` — 작품↔장소 (13,755행) ★핵심 자산★

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `mapping_id` | bigserial PK | |
| `content_id` / `place_id` | FK (양쪽 CASCADE) | **UNIQUE `(content_id, place_id)`** |
| `kmdb_case_id` | varchar(40) **UNIQUE**, null | 재시드 자연키 (K17686-A-011) |
| `scene_description` | text, null | 장면설명 — **74.9%가 비어 있다** |
| `characters` | varchar(300), null | 등장인물 — 95.2%가 비어 있다 |
| `episode` | varchar(50), null | 촬영회차. 드라마 확장 대비, 영화는 전부 NULL |

- **장면설명·등장인물을 `places`가 아니라 여기에 둔 이유**: 같은 장소라도 작품마다 장면이 다르다.
  이건 장소의 속성이 아니라 **'연결'의 속성**이다.
- `ix_cpm_place_id` — 장소 목록에 작품을 붙이는 **N+1 방지 쿼리가 가장 뜨거운 경로**다.

#### ⑤ `users` — 사용자 (0행)

| 컬럼 | 타입 | local | google/kakao |
|---|---|---|---|
| `user_id` | bigserial PK | | |
| `nickname` | varchar(50) | 필수 | 제공자 닉네임 or `여행자XXXX` |
| `auth_provider` | enum(`local`,`google`,`kakao`) | | |
| `provider_user_id` | varchar(255), null | **NULL** | **필수** (구글 sub / 카카오 id) |
| `email` | varchar(255) **UNIQUE**, null | **필수** | 있으면 저장 (카카오는 null 가능) |
| `password_hash` | varchar(255), null | **필수** (bcrypt 60자) | **NULL** |
| `email_verified` | boolean | 코드 확인 후 true | 제공자가 확인해줬으면 true |
| `created_at` | timestamptz | | |

- **CHECK 제약 `ck_users_provider_fields`** — 위 표의 규칙을 **DB가 강제**한다.
  코드에 버그가 나도 반쪽짜리 계정이 저장되지 않는다.
- **UNIQUE `(auth_provider, provider_user_id)`** + **`email` 전역 UNIQUE**
- 이메일을 전역 유일로 한 이유: 같은 주소로 구글 가입 후 다시 일반 가입하면 계정이 둘로 쪼개져
  "내 코스가 사라졌다"가 된다.

#### ⑥ `refresh_tokens` — 로그아웃을 가능하게 하는 테이블 (0행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `token_id` | bigserial PK | |
| `user_id` | FK→users (CASCADE) | 인덱스 `ix_refresh_tokens_user_id` |
| `token_hash` | varchar(64) **UNIQUE** | **SHA-256 hex. 원문은 저장하지 않는다** |
| `expires_at` | timestamptz | 발급 + 30일 |
| `revoked_at` | timestamptz, null | NULL이면 살아있음. **로그아웃 = 여기 시각을 찍는 것** |
| `user_agent` | varchar(200), null | 어느 기기에서 로그인했는지 |

**왜 bcrypt가 아니라 SHA-256인가** — 난수 48바이트라 사전공격 대상이 아니고,
`WHERE token_hash = ?`로 **조회 키**가 되어야 해서 매번 같은 값이 나와야 한다.
bcrypt는 매번 salt가 달라 조회 자체가 불가능하다.

#### ⑦ `email_verifications` — 회원가입 인증코드 (0행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `verification_id` | bigserial PK | |
| `email` | varchar(255) | 인덱스 `(email, created_at)` |
| `code_hash` | varchar(64) | SHA-256 — 6자리 평문이 로그·DB에 안 남게 |
| `expires_at` | timestamptz | 발급 + 10분 |
| `attempt_count` | integer | **5회 제한** |
| `verified_at` / `consumed_at` | timestamptz, null | 확인 시각 / 실제 가입에 쓰인 시각 |

**`users` 행을 먼저 만들지 않는다** — 인증을 포기한 유령 계정이 쌓여 이메일 UNIQUE를 점유하면,
나중에 진짜 가입하려는 사람을 막는다.

#### ⑧ `api_call_logs` — TourAPI 호출 입증 ⚠️합격 핵심

| 컬럼 | 설명 |
|---|---|
| `operation` | `searchKeyword2` · `detailCommon2` … |
| `request_params` | **JSONB — `serviceKey` 제외** |
| `http_status` · `response_time_ms` · `result_count` | |
| `request_id` | 요청 추적용 |
| `user_id` | FK→users (**SET NULL** — 탈퇴해도 입증 로그는 보존) |
| `called_at` | 인덱스 `(operation, called_at)` |

**응답 본문은 저장하지 않는다.** 남기는 건 '언제·무엇을·얼마나 걸려 호출했나'뿐이다.

#### ⑨⑩ `courses` / `course_places` — 저장 코스 (0행, 6단계에서 사용)

- `courses`: `user_id`(CASCADE) · `title` · `created_at`
- `course_places`: `course_id`(CASCADE) · `place_id`(**RESTRICT** — 코스에 담긴 장소는 함부로 삭제 금지)
  · `visit_order` · UNIQUE `(course_id, visit_order)`

### 6-3. FK 삭제 정책과 이유

| 관계 | 정책 | 이유 |
|---|---|---|
| `mappings` → contents/places, `courses` → users, `refresh_tokens` → users | **CASCADE** | 부모가 사라지면 딸린 데이터도 무의미 |
| `course_places.place_id` | **RESTRICT** | 코스에 담긴 장소는 함부로 삭제되면 안 됨 |
| `places.region_id` | **SET NULL** | 지역이 개편돼도 장소는 남아야 함 |
| `api_call_logs.user_id` | **SET NULL** | 유저가 탈퇴해도 **호출 입증 로그는 보존** |

### 6-4. 인덱스

| 인덱스 | 대상 | 용도 |
|---|---|---|
| `idx_places_geom` | GIST | **반경 검색.** `EXPLAIN`으로 Bitmap Index Scan 확인 (전수 스캔 아님) |
| `ix_contents_genre_tags` | GIN | 배열 컬럼 장르 필터 |
| `ix_places_region_id` | B-tree | 지역 내 촬영지 (지도 화면 기본 필터) |
| `ix_cpm_place_id` | B-tree | 장소↔작품 N+1 방지 쿼리 |
| `ix_refresh_tokens_user_id` | B-tree | 모든 기기 로그아웃 |
| `ix_email_verifications_email_created` | B-tree | 이 이메일의 최근 인증건 |

> ⚠️ **함정**: 마이그레이션에서 `op.create_index`로만 만들고 **모델에 선언하지 않은 인덱스는
> autogenerate가 "군더더기"로 보고 DROP 문을 생성한다.** 실제로 위 3~4번을 지우려 한 적이 있다.
> 지금은 전부 모델 `__table_args__`에 `Index(...)`로 선언해 막아뒀다.

### 6-5. 마이그레이션 이력

| 리비전 | 내용 |
|---|---|
| `439ec7cb835f` | 초기 7테이블 (최소 컬럼) |
| `c4d4fdb425b1` | 스키마 확장 — regions 계층, contents·places·mappings 컬럼 (2.5단계) |
| `aedbf5168cc3` | `api_call_logs` 활성화 (4단계) |
| `06fb23255fb0` | `places.tour_matched_at` 추가 |
| **`9a1c7d2e5b40`** | **인증 — enum `local` 추가, users 확장, `refresh_tokens`·`email_verifications`** (3단계) |

---

## 7. API 구성 (19종)

공통 규약 — JSON **snake_case** · 좌표는 항상 `{"lat":…, "lng":…}` **객체** · 목록은 `{"items":[…], "total":n}`
· 에러는 `{"detail":"…"}` · 페이지는 `limit`(기본20, 최대100)/`offset`

### 7-1. 인증 (10종) — 3단계 ✅

| 메서드·경로 | 요청 | 응답 | 주요 에러 |
|---|---|---|---|
| `POST /auth/email/send-code` | `{email}` | `{expires_in, dev_code?}` | `409` 이미 가입 · `429` 쿨다운 60초 |
| `POST /auth/email/verify-code` | `{email, code}` | `{verified, signup_deadline_minutes}` | `400` 불일치·만료 · `429` 5회 초과 |
| `POST /auth/signup` | `{email, password, nickname}` | `201` + 토큰쌍 | `403` 인증 미완 · `409` 중복 · `422` 비번 규칙 |
| `POST /auth/login` | `{email, password}` | 토큰쌍 | `401` 불일치 · `409` 소셜 가입자 |
| `POST /auth/google` | `{id_token}` | 토큰쌍 | `401` 위조·타앱 · `502` 구글 장애 |
| `POST /auth/kakao` | `{access_token}` | 토큰쌍 | `401` 위조·타앱 · `502` 카카오 장애 |
| `POST /auth/refresh` | `{refresh_token}` | 토큰쌍(둘 다 새것) | `401` 만료·**재사용 감지** |
| `POST /auth/logout` | `{refresh_token}` | `{message}` | 없음 (항상 200, 멱등) |
| `POST /auth/logout-all` 🔒 | — | `{message}` | `401` |
| `GET /auth/me` 🔒 | — | `UserOut` | `401` |

**공통 성공 응답** (가입·로그인·소셜·재발급이 전부 같은 모양)
```jsonc
{
  "access_token": "eyJhbGci...",   // JWT, 1시간
  "refresh_token": "Yx7q3f...",    // 난수 48바이트, 30일 (JWT 아님)
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "user_id":1, "nickname":"은서", "auth_provider":"local",
            "email":"…", "email_verified":true, "created_at":"…" }
}
```

⚠️ **구글은 `id_token`, 카카오는 `access_token`** — 필드명이 다른 건 실수가 아니다.
구글은 정보가 담긴 서명된 JWT를, 카카오는 정보가 없는 불투명 토큰을 준다.

### 7-2. 작품 (4종) — 5단계 ✅

| 메서드·경로 | 역할 | 특징 |
|---|---|---|
| `GET /contents/search?q=` | 작품 검색(부분일치) | **관련도 정렬** — 정확일치 1.0 > 접두 0.8 > 부분 0.5. `place_count` 포함 |
| `POST /contents/resolve` | 제목 → 후보 (**AI 전용**) | **항상 배열** (만추 1966·1981) |
| `GET /contents/{id}` | 작품 상세 | |
| `GET /contents/{id}/places` | 그 작품의 전국 촬영지 | `scene_description`·`episode` 포함 |

> ⚠️ 부분일치라 `q=기생` → 「기생충」과 「음란 기생」이 함께 나온다. 화면에서 연도·포스터로 구분 필요.

### 7-3. 지역 (3종) — 5단계 ✅

| 메서드·경로 | 역할 | 특징 |
|---|---|---|
| `GET /regions/resolve?name=` | 지역명 → 후보 (**AI 전용**) | 「중구」→ **6개**, 「서울 중구」→ **1개로 좁혀짐** |
| `GET /regions?flat=` | 지역 목록 | 시도(17) → 시군구(227) 2단계. `?flat=true`면 평평하게 |
| `GET /regions/{id}/places` | 지역 내 촬영지 + 포스터 | `?content_id=`로 작품 필터 · `?sort=popular\|name` |

`sort=popular`(기본)인 이유 — 강남구 473곳·종로구 399곳처럼 몰린 지역에서 앞 20개만 봐도
경복궁·창덕궁이 나오게 하기 위함이다.

### 7-4. 장소 (2종) — 4·5단계 ✅

| 메서드·경로 | 역할 |
|---|---|
| `GET /places?near={region_id}&radius_km=` | 지역 중심점 반경 조회. **≤20km**(초과 시 400), `distance_km` 부여 |
| `GET /places/{id}` ⚠️ | **장소 상세 — TourAPI 실시간** (§8-3 참조) |

⚠️ **raw GPS를 받는 파라미터가 없다.** "내 주변"은 앱이 GPS로 `region_id`를 고른 뒤 그 id를 보낸다.

### 7-5. 코스 (5종) — 6단계 ⬜ 미구현

`POST /courses/recommend`(저장 안 함, 인증 불필요) · `POST/GET/DELETE /courses`🔒

---

## 8. 핵심 플로우 5가지

### 8-1. 작품 검색 → 촬영지 (유저플로우 3·4c)

```
[앱] 검색창에 "기생충"
  │
  ├─→ GET /contents/search?q=기생충
  │      service: 제목 부분일치 + 관련도 점수 + place_count 서브쿼리
  │   ← { items:[{content_id:139, title_ko:"기생충", place_count:28, poster_url:…}] }
  │
  │  사용자가 목록에서 탭
  │
  └─→ GET /contents/139/places
         service: mappings JOIN places JOIN regions
      ← { items:[{place_id, name, location:{lat,lng}, scene_description, region}], total:28 }
```

### 8-2. 지역 검색 → 지도 (유저플로우 4·4b)

```
[앱] "강릉"                              [AI 챗봇] "강릉 쪽으로"
  │                                         │
  └────────→ GET /regions/resolve?name=강릉 ←┘
             ← { candidates:[{region_id, name, full_name:"강원특별자치도 강릉시", centroid}] }
                 ★ 항상 배열 — 「중구」는 6곳이다
  │
  └─→ GET /regions/{id}/places?sort=popular
         service: region_scope_ids(재귀) → places → mappings 한 번에 조회(N+1 회피)
      ← { items:[{place_id, name, location, contents:[{title_ko, poster_url, scene_description}]}] }
                                              ▲ 한 마커에 작품 여러 개 (강릉선교장 = 5작품)
  │
  │  사용자가 지도에서 영화 하나 선택 (4b)
  │
  └─→ GET /regions/{id}/places?content_id=559
      ← 1곳(강릉선교장)   ※ 필터 전/후 응답 구조 동일
```

### 8-3. 장소 상세 — TourAPI 실시간 ⚠️합격 핵심

**이 플로우가 공모전 합격 요건 그 자체다.**

```
GET /places/2193 (강릉선교장)
  │
  ├─ ① 우리 DB 조회 — 이름·좌표·주소·지역·이 장소에서 찍은 작품들
  │
  ├─ ② tour_content_id가 있나?
  │     ├─ 있음 → ④로
  │     ├─ 없고 tour_matched_at이 30일 이내 → detail=null로 즉시 반환 (호출 0건)
  │     └─ 없고 시도한 적 없음 → ③
  │
  ├─ ③ matching.py — 이름 기반 매칭
  │     · 이름 변형 최대 3개 생성
  │         원본 → 괄호제거 → 지역접두 절단 → "지역 이름"
  │     · 각각 searchKeyword2 호출
  │     · 후보 검증:  좌표 ≤1km  AND  이름 유사도 ≥0.7
  │     · 성공 → places.tour_content_id 저장 / 실패 → tour_matched_at만 기록
  │
  ├─ ④ TourAPI 3연속 호출 (매 요청 실시간, 저장 안 함)
  │     · detailCommon2  → 이름·개요·전화·홈페이지
  │     · detailIntro2   → 운영시간·휴무일  ← contentTypeId 필요, 필드명이 타입마다 다름
  │     · detailImage2   → 이미지 URL 배열
  │
  ├─ ⑤ 정규화 — homepage의 <a href> 벗기기, overview의 <br> 제거,
  │              intro_hours()로 타입별 필드명을 use_time/rest_date 하나로 흡수
  │
  └─ ⑥ ★ api_call_logs에 호출 전부 기록 (TourApiClient._get 안에서 자동)
     ← { place_id, name, location, contents:[…], detail:{ tour_content_id, overview,
                                                          use_time, rest_date, images:[…] } }
```

**호출 예산**

| 상황 | 호출 |
|---|---|
| 미매칭 장소 첫 조회 | 최대 6건 (검색3 + 상세3) |
| 매칭된 장소 조회 | 3건 |
| 매칭 실패가 기억된 장소 | **0건** |

**`detail`이 null인 것은 정상 경로다.** 실측 16곳 중 5곳이 null이었고, 원인은 방송사 사옥·촬영
스튜디오·세트장·병원처럼 **애초에 관광지가 아닌 곳**이다.

### 8-4. 회원가입 — 3단계 호출

```
① POST /auth/email/send-code  {email}
     · 이미 가입된 이메일인가? → 409 (어느 경로로 가입했는지 안내)
     · 60초 내 재발송인가? → 429
     · 이전 미사용 코드 전부 무효화 → 새 코드 생성 → email_verifications INSERT
     · mailer.send_verification_code()
         SMTP 설정됨   → 실제 발송, dev_code=null
         SMTP 미설정   → 서버 로그 출력, 응답 dev_code에 코드 담김 (개발용)
   ← { expires_in:600, dev_code:"862986" }

② POST /auth/email/verify-code  {email, code}
     · 최근 미사용 건 조회 → 만료? → 400 / 5회 초과? → 429
     · ★ 대조 **전에** attempt_count 증가 후 커밋
         (나중에 올리면 응답을 끊어 카운트를 회피할 수 있다)
     · compare_digest로 대조 → 불일치 400
     · verified_at 기록  ← 30분짜리 '가입 통과권'
   ← { verified:true, signup_deadline_minutes:30 }

③ POST /auth/signup  {email, password, nickname}
     · 이메일 중복? → 409
     · verified_at이 30분 이내인 미사용 건이 있나? → 없으면 403
     · bcrypt 해싱 → users INSERT (auth_provider=local, email_verified=true)
     · verification.consumed_at 기록 (재사용 차단)
     · 토큰쌍 발급
   ← 201 + { access_token, refresh_token, expires_in, user }
```

**②까지는 `users` 행을 만들지 않는다** — 유령 계정 방지.

### 8-5. 로그인 → API 호출 → 갱신 → 로그아웃

```
① 로그인/소셜/가입     앱 ──→ 서버 ──→ DB
                       access(1h) + refresh(30d) 발급
                       refresh는 SHA-256 해시로만 저장
                       (원문은 이 응답에 한 번 실려 나가고 끝)

② 평소 API 호출        앱 ──→ 서버
                       Authorization: Bearer <access>
                       deps.get_current_user가 서명 검증 → DB에서 User 조회
                       typ 클레임 확인 (refresh를 출입증으로 못 쓰게)

③ access 만료          앱 ←──→ 서버 ──→ DB
                       401 → POST /auth/refresh → 새 한 쌍
                       옛 refresh는 즉시 revoked_at 기록 (회전)
                       ⚠️ 앱은 새 refresh로 교체 저장 필수

④ 폐기된 refresh 재등장 앱 ──✗ 서버
                       정상 앱은 새것을 받아 갔으므로 옛것을 다시 쓸 이유가 없다
                       → 탈취로 간주 → revoke_all_tokens() → 전 세션 차단

⑤ 로그아웃             앱 ──→ 서버 ──→ DB
                       그 refresh에 revoked_at 기록
                       없는 토큰이어도 200 (멱등)
                       남은 access는 최대 1시간 더 유효
```

**소셜 로그인 분기** (①의 변형)

```
POST /auth/kakao {access_token}
  ├─ social.verify_kakao()
  │    · KAKAO_APP_ID 설정됨 → access_token_info로 app_id 대조 (다른 앱 토큰 차단)
  │    · user/me로 id·닉네임·이메일 조회 (필요한 항목만 요청 — 최소수집)
  ├─ service.social_login()
  │    · (provider, provider_user_id)로 조회 ← ★ 이메일이 아니다
  │      (이메일은 사용자가 바꿀 수 있지만 id는 안 바뀐다)
  │    · 있으면 로그인 / 없으면 자동 가입
  │    · 신규인데 그 이메일이 이미 다른 경로로 쓰이면 → 409
  └─ 토큰쌍 발급
```

**프론트가 구현할 것은 ③ 하나다.** HTTP 클라이언트 인터셉터에
*"401이면 refresh 부르고 원래 요청 재시도"*를 한 번 심으면 화면 코드는 토큰을 몰라도 된다.

---

## 9. 외부 연동 구성

### 9-1. KTO TourAPI 3종 — 전부 실호출로 경로 확인 (2026-08-16)

⚠️ **경로 뒤 숫자가 서비스마다 다르다. 추측 금지.**

| # | 서비스 (data.go.kr) | 실제 경로 | 쓰는 곳 |
|---|---|---|---|
| ① | 국문 관광정보 `15101578` | **KorService2** | 장소 상세(4단계) · 매칭 |
| ② | 관광사진 정보 `15101914` | **PhotoGalleryService1** | 촬영지 사진 보강 (미연동) |
| ③ | 기초지자체 중심 관광지 `15128559` | **TarRlteTarService1** | 주변 볼거리·코스 추천(6단계) (미연동) |

- ①: `KorService1`은 **폐기**(NO_OPENAPI_SERVICE_ERROR). 오퍼레이션도 `~2`
  (`detailCommon2`·`detailIntro2`·`detailImage2`·`searchKeyword2`·`locationBasedList2`)
- ②: `PhotoGalleryService2`·`galleryKeywordList2`는 **존재하지 않는 경로**(12번 오류).
  확인된 오퍼레이션 `galleryList1`·`gallerySearchList1`·`galleryDetailList1`.
  응답에 `galPhotographer`가 있어 **저작권 표기와 함께** 노출해야 한다.
- ③: `TarRlteTarService2`는 400. `areaBasedList1` + `baseYm` 필수(`202606` 확인).
  ⚠️ **`areaCd`/`signguCd`가 법정동 코드다** (강원=51, 강릉시=51150). TourAPI 지역코드(강원=32)와 **다르다.**
  `regions.area_code`가 0/244라 채우기 전엔 호출 불가 — ③ 연동의 선행 과제.
  실측: 강릉시 → 관광지 1위 **「도깨비촬영지/(영진해변)」**

### 9-2. `TourApiClient` 설계 — 입증을 빠뜨릴 수 없는 구조

```python
class TourApiClient:
    async def _get(self, base, operation, **params):
        record = CallRecord(operation=operation, params=safe_params)  # serviceKey 없음
        self.calls.append(record)          # ★ 모든 호출이 여기 쌓인다
        ...                                 # 성공·실패 무관하게 기록
```

- **모든 오퍼레이션이 `_get`을 지난다** → 호출부가 입증 기록을 잊을 수 없다.
  입증 누락은 곧 실격이라 **옵션으로 두지 않았다.**
- **클라이언트는 DB를 모른다.** 저장은 `integrations/call_log.py`가 맡는다
  → 클라이언트 테스트에 DB가 필요 없고, 저장 정책을 한 곳에서만 바꾸면 된다.
- **저장 실패가 요청을 깨뜨리지 않는다** — 다만 조용히 넘기지 않고 경고를 남긴다.
- ⚠️ **httpx 로거를 WARNING으로 낮춰뒀다** — 지우지 말 것.
  httpx는 INFO에서 요청 URL을 통째로 남기는데, TourAPI는 `serviceKey`를 **쿼리스트링**으로 받아
  그대로 두면 **인증키가 서버 로그에 평문으로 쌓인다.**

### 9-3. 매칭 알고리즘 (`features/places/matching.py`)

| 규칙 | 값 | 근거 (실측) |
|---|---|---|
| 이름 변형 | 최대 **3개** | 원본 → 괄호제거 → 지역접두 절단 → "지역 이름". 일 1,000건 한도 보호 |
| 좌표 검증 | **≤1km** | 500m는 좁았다 — 올림픽공원은 우리 촬영지점↔공사 대표좌표가 **663m** |
| 이름 유사도 | **≥0.7** | 「다이소 서울역점」(0.60)·「게스 롯데아울렛 서울역점」(0.43) 오탐 차단 |
| 실패 재시도 | **30일 후** | 실패를 기억 안 하면 조회할 때마다 검색 3회 재소모 |

**실측 결과**: 시도 16곳 중 **11곳 매칭(69%)**. 초기 47%에서 올랐다.
미검출 5곳은 방송사 사옥·스튜디오·세트장·병원·역사(驛舍)로 **애초에 관광지가 아니다.**

### 9-4. 소셜 로그인 (`features/auth/social.py`)

**앱 SDK 토큰 전달 방식** — 서버 OAuth 리다이렉트가 아니라서 **client secret도 redirect_uri도 필요 없다.**

| 제공자 | 호출 | 검증 항목 |
|---|---|---|
| **구글** | `oauth2.googleapis.com/tokeninfo?id_token=` | ① 서명·만료(구글이 대신 검증) ② `iss` ③ **`aud` == `GOOGLE_CLIENT_ID`** ④ `sub` 존재 |
| **카카오** | `kapi.kakao.com/v1/user/access_token_info` → `/v2/user/me` | ① **`app_id` == `KAKAO_APP_ID`** ② `id`·닉네임·이메일 |

- ⚠️ 설정값이 비면 **앱 소속 검증을 건너뛰고 경고 로그를 남긴다.**
  비어 있으면 **아무 앱의 토큰으로도 우리 서버에 로그인된다** — 배포 전 필수.
- 구글 `tokeninfo`는 값을 **전부 문자열로** 준다(`"true"`). bool 비교하면 항상 false.
- 카카오 이메일은 **선택 동의**라 `user.email`이 null일 수 있다(정상).
- 제공자 장애는 `401`이 아니라 **`502`** — 401을 주면 앱이 사용자를 로그아웃시킨다.

### 9-5. 메일 (`features/auth/mailer.py`)

- 발송처는 오직 `.env`가 정한다 → **Gmail → 네이버 → SendGrid 전환도 코드를 안 건드린다.**
- `SMTP_HOST`가 비면 발송하지 않고 서버 로그 + 응답 `dev_code`로 코드를 내보낸다.
- 동기 `smtplib`을 **스레드로 밀어** 호출한다 — 이벤트 루프에서 직접 붙잡으면 그동안 서버 전체가 멈춘다.

---

## 10. 공모전 컴플라이언스 — 어디에 어떻게 구현했나

| # | 규정 | 구현 위치 | 방식 |
|---|---|---|---|
| 1 | **실시간 호출 + 입증** (미준수 시 심사 제외) | `integrations/tour_api.py::_get` → `call_log.py` → `api_call_logs` | 모든 오퍼레이션이 `_get`을 지나므로 **빠뜨릴 수 없다** |
| 2 | **응답 무캐싱** | `models/place.py` | 운영시간·전화·개요·이미지 **컬럼을 아예 안 만듦.** `GET /places/{id}`가 매 요청 조회 |
| 3 | **serviceKey 서버 전용** | `core/config.py` · `tour_api.py` | `.env`에만. `CallRecord.params`에서 제외 + **httpx 로거 WARNING** |
| 4 | **이미지 URL만** | `schema.TourDetail.images` · `contents.poster_url` | URL 문자열만 전달. 서버가 내려받지 않음 |
| 5 | **raw GPS 미수신** | `places/router.py` | 좌표 파라미터를 **제공하지 않음**. 입력은 `region_id` 정수 |
| 5 | 반경 ≤20km | `places/router.py::MAX_RADIUS_KM` · `tour_api.MAX_RADIUS_M` | 초과 시 `400` |
| 6 | 금지 API 미사용 | `tour_api.py` | `areaCode2`·`categoryCode2`·산악관광정보를 **구현하지 않음**. `regions`는 시드 테이블 |
| 7 | 원천 데이터 무수정 | 전반 | 공사 값은 그대로, 우리 큐레이션과 섞되 수정 안 함 |

**검증 결과** — 강릉선교장 조회 시 `searchKeyword2`×2 → `detailCommon2`·`detailIntro2`·`detailImage2`,
전 호출이 `api_call_logs`에 기록되고 **`serviceKey` 유출 0건.** 재조회 시 이름검색을 건너뛰어 3건만 사용.

---

## 11. 개발 진행 경과

### 11-1. 단계별

| 단계 | 내용 | 상태 | 산출물 |
|---|---|---|---|
| 0 | 설계 v1(Supabase) → v2(적대적 검증) → **v3(FastAPI)** | ✅ | 설계 확정 |
| 1 | 프로젝트 뼈대 + `/health` | ✅ | `main.py`·`config.py`·`docker-compose.yml` |
| 2 | DB 연결 + Alembic + 모델 | ✅ | 7테이블, 리비전 `439ec7cb835f` |
| 2.5 | 스키마 확장 + **실데이터 적재** | ✅ 08-15 | 13,755 매핑, `seed_from_csv.py` |
| 5 | 검색·지도 엔드포인트 8종 | ✅ 08-15 | `API_CONTRACT.md` 먼저 확정 후 구현 |
| 4 | **TourAPI 실시간 + 호출 입증** ⚠️ | ✅ 08-16 | `tour_api.py`·`matching.py`·`api_call_logs` |
| — | 계층별 → **기능별 폴더 재편** | ✅ 08-16 | `app/features/*` |
| **3** | **인증 10종** | ✅ **08-22** | `features/auth/`, 리비전 `9a1c7d2e5b40` |
| 6 | 코스 추천 엔진 | ⬜ | |
| 8 | 테스트·하드닝 | ⬜ | pytest 0개 |
| 9 | 배포·제출 | ⬜ | |

### 11-2. 계획에서 바뀐 것 ★

| # | 바뀐 것 | 왜 |
|---|---|---|
| ① | **3단계(로그인)를 건너뛰고 데이터 적재를 먼저** | DB가 7테이블 전부 0행이라 뭘 만들어도 검증 불가(검색 결과가 항상 빈 배열). 게다가 **데이터 모양이 API 설계를 결정**한다 |
| ② | 테이블 **12 → 활성 7 → 현재 10** | "꼭 필요한 것만". 모델 코드는 남기고 import만 주석 처리해 '지연'. 기능을 실제로 만들 때 되살렸다 |
| ③ | **계층별 → 기능별 폴더** | `services/catalog.py`가 444줄까지 자람. 3·6·7단계가 들어오면 계속 비대해질 구조 |
| ④ | TourAPI 매칭 **좌표 → 이름 기반** | `locationBasedList2`가 관광지를 반환하지 않아 **원래 계획이 성립하지 않았다** |
| ⑤ | 인증 **소셜 전용 → 소셜 + 일반가입 + 이메일 인증** | 요구 변경. enum에 `local` 부활, bcrypt 재도입 |
| ⑥ | 토큰 **14일 1개 → access 1h + refresh 30d** | 로그아웃을 넣는 순간 기존 구조가 성립 안 함. JWT는 취소가 불가능하다 |
| ⑦ | 백엔드 **1인 → 2인 브랜치 분업** | 팀원이 지도 API 담당. 인증은 파일이 거의 안 겹쳐 병렬에 안전 |

---

## 12. 작업 워크플로우

### 12-1. 관통하는 원칙

> **되돌리기 비싼 것부터 확정한다.**

```
비쌈 ↑   설계 결정 ─── 팀과의 API 계약 ─── DB 스키마 ─── 코드 ─── 문서   ↓ 쌈
        (바꾸면 전부   (바꾸면 프론트가   (바꾸면 팀원   (파일    (혼자
         다시 함)       깨짐)             DB까지 영향)   몇 개)   고침)
```

여기서 나온 실제 판단:
- **갈림길은 코드 한 줄 쓰기 전에 확정** — 3단계에서 로그아웃 방식·소셜 방식·이메일 인증·브랜치를 먼저 정했다
- **계약서를 코드보다 먼저** — 5단계는 `API_CONTRACT.md`를 확정하고 그대로 구현.
  덕분에 프론트·AI가 **서버 완성 전에 목(mock)으로** 개발 시작
- **스키마 변경은 가장 싼 시점에 몰아서** — 2단계에서 UI mockup과 모델을 대조해 마이그레이션 직전에 반영

### 12-2. 단계마다 도는 8스텝

| # | 스텝 | 왜 이 순서인가 |
|---|---|---|
| 1 | 기존 코드·계약서 읽기 | 팀과 합의된 계약이 출발점. 모르고 만들면 프론트 코드를 깨뜨린다 |
| 2 | 갈림길 확정 | 나중에 바꾸면 스키마·계약서를 같이 뜯어야 하는 것들 |
| 3 | 브랜치 분리 | 커밋 시작 뒤 옮기는 것보다 시작 전이 훨씬 싸다 |
| 4 | 모델 → 마이그레이션 | 스키마는 늦게 바꿀수록 비싸다(팀원 DB까지 영향) |
| 5 | **아래에서 위로** 구현 (core → service → router) | 위부터 만들면 아래가 없어 가짜 값으로 때워야 한다 |
| 6 | 적용 + **드리프트 검사** | `upgrade head` 후 autogenerate 한 번 더 → **빈 diff 확인** 후 파일 삭제. 모델과 DB가 어긋나면 다음 마이그레이션이 멀쩡한 걸 지운다 |
| 7 | 실호출 검증 | 성공 경로뿐 아니라 **막혀야 할 것이 막히는지** |
| 8 | 문서 갱신 → 커밋 | 중간에 쓰면 결정 바뀔 때마다 다시 씀. 단 **커밋 전엔 반드시** |

### 12-3. 문서 체계 — 6개가 각자 다른 질문에 답한다

| 문서 | 답하는 질문 | 갱신 시점 |
|---|---|---|
| `DEV_SUMMARY.md` | 처음부터 지금까지 어떻게 온 거지? | 큰 변곡점마다 |
| **`PROJECT_STRUCTURE.md`** (이 문서) | 무엇이 어떻게 구성돼 있지? | 구조 변경 시 |
| `PROGRESS.md` | **지금** 어디까지 됐지? | 단계마다 (스냅샷) |
| `DEVELOPMENT_LOG.md` | 그때 **왜** 그렇게 했지? | 단계마다 (누적, 안 지움) |
| `API_CONTRACT.md` | 프론트·AI가 뭘 부르면 되지? | **구현 전에** 먼저 |
| `PROJECT_REPORT.md` | 로드맵·제약이 뭐지? | ⚠️ **1단계 기준에서 멈춤 — 정리 필요** |

### 12-4. 검증 철학 — "막혀야 할 것이 막히는가"

pytest는 아직 없다(8단계). 대신 **실제로 뜬 서버에 호출하는 스크립트**를 단계마다 남겼다.

`check_auth.py` 38케이스 중 **성공 9 / 거부 29**인 게 의도다.
인증에서 진짜 위험한 건 "로그인이 안 되는 것"이 아니라 **"막혔어야 할 게 통과하는 것"**이다.

---

## 13. 실행 · 검증 방법

### 13-1. 서버 띄우기

```powershell
cd "D:\workspace\2026 tourism data contest\BE"

docker start ktour-db                    # PC 재부팅 후엔 이것부터 (Docker Desktop 실행 필요)
.venv\Scripts\python.exe -m alembic upgrade head    # 스키마 최신화
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- 헬스체크 http://127.0.0.1:8000/health → `{"status":"ok"}`
- **자동 문서 http://127.0.0.1:8000/docs**
  우측 상단 **Authorize** 버튼에 `access_token`을 넣으면 🔒 API도 브라우저에서 테스트된다

### 13-2. 검증 스크립트

```powershell
.venv\Scripts\python.exe -m scripts.check_auth        # 인증 38케이스 (서버 먼저 띄울 것)
.venv\Scripts\python.exe -m scripts.check_tour_api    # TourAPI 키·경로 실호출
```

### 13-3. 데이터 적재 / 사전 매칭

```powershell
.venv\Scripts\python.exe -m scripts.seed_from_csv                    # 재실행 안전
.venv\Scripts\python.exe -m scripts.match_tour_places --limit 50     # 일 1,000건 한도 주의
.venv\Scripts\python.exe -m scripts.match_tour_places --limit 50 --dry-run
```

### 13-4. 마이그레이션

```powershell
.venv\Scripts\python.exe -m alembic current                          # 현재 리비전
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "설명"  # ★ 반드시 손으로 검토
.venv\Scripts\python.exe -m alembic upgrade head
```

⚠️ autogenerate 결과에 **`drop_index`가 있으면 멈추고 확인**할 것. 모델에 선언 안 된 인덱스를 지우려는 것이다.

---

## 14. 남은 일

### 기능
| | 내용 |
|---|---|
| **6단계 코스 추천** | `POST /courses/recommend`(저장 안 함) + 저장·조회·삭제🔒. 인증이 끝나 `CurrentUser` 한 줄로 붙는다. 동선은 PostGIS 직선거리 → 필요 시 Kakao Mobility/ODsay |
| 8단계 pytest | 현재 0개. 실호출 스크립트뿐이라 서버를 띄워야 검증된다 |
| 9단계 배포 | 다국어(ko/en) 입증 · 데모 시나리오 |

### 설정 (배포 전 필수)
| | 내용 |
|---|---|
| ⚠️ `GOOGLE_CLIENT_ID`·`KAKAO_APP_ID` | 비면 **"우리 앱 토큰인가" 검증을 건너뛴다** → 다른 앱 토큰으로도 로그인됨 |
| SMTP 계정 | 미설정. Gmail 앱 비밀번호를 `.env`에 넣으면 코드 수정 없이 실제 발송 전환 |
| 운영계정 신청 | 개발계정 **1,000건/일**로 심사·시연을 감당할 수 있는지 확인. 승인에 시간 소요 |

### 데이터
| | 내용 |
|---|---|
| 사전매칭 완주 | `tour_content_id` 현재 **11/9,811**. 인기 촬영지 300~500곳을 나눠 채워야 한다 |
| `regions.area_code` | **0/244.** TourAPI ③(기초지자체 중심 관광지) 연동의 선행 과제 |
| **드라마 10편뿐** | CSV가 KMDb(영화DB) 출신. 스키마는 **INSERT만으로 추가 가능**하게 설계됨 |
| 포스터 없는 작품 296편(18%) | 프론트에 기본 이미지 필요 |

### 팀·문서
- `eunseo` 브랜치 push·병합 시점 합의. `origin/yoon`이 `main`보다 뒤처진 시점에서 갈라져 있어,
  팀원이 `main`을 먼저 머지하면 충돌이 줄어든다.
- `PROJECT_REPORT.md`가 1단계 기준(12테이블·자체JWT 표기)에서 멈춰 있어 정리 필요.

---

*갱신 이력 — 2026-06 최초(1단계) / 2026-08-15 구조·DB 반영 / **2026-08-22 전면 재작성**(기능별 폴더 구조·인증 10종·10테이블 반영).*
