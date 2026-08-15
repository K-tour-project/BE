# K-tour BE — 프로젝트 구성 상세 설명서

> **이 문서는** 백엔드가 *어떻게 구성돼 있는지*(폴더·파일·계층·DB·실행법)를 처음 보는 사람도 이해하도록 상세히 설명한다.
> 관련 문서 — 진행 현황: [`PROGRESS.md`](./PROGRESS.md) · 로드맵/결정: [`PROJECT_REPORT.md`](./PROJECT_REPORT.md) · 구현일지: [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md) · ERD: [`erd.dbml`](./erd.dbml)

---

## 0. 프로젝트 개요

- **앱**: 영화·드라마 **촬영지 기반 관광 앱**(Every Trip). 작품/지역을 검색 → 지도에서 촬영지 확인 → 저장 → AI 추천.
- **이 레포(BE)**: 그 앱의 **백엔드 서버**. 모바일 앱(FE, Kotlin)과 AI(팀원)가 이 서버의 API를 호출한다.
- **공모전**: 2026 한국관광공사 관광데이터 활용 공모전. **1차 마감 2026-09-21(월) 16:00**.
- **역할 경계**: 챗봇·NLU·LLM은 **AI 팀원**이 별도로 담당. 이 백엔드는 **검색·추천 REST API + DB**만 책임진다.

---

## 1. 기술 스택 (무엇을 · 왜)

| 구분 | 기술 | 왜 이걸 썼나 |
|---|---|---|
| 언어/프레임워크 | **FastAPI** (Python 3.11) | 비동기(외부 API 병렬 호출에 유리)·자동 문서·빠른 개발 |
| DB | **PostgreSQL 15 + PostGIS** | 관계형(작품↔장소 M:N) + 지오(지도·반경 검색) |
| DB 접근 | **SQLAlchemy 2.0 (async)** + **asyncpg** | 파이썬 코드로 DB 다루기(ORM) |
| 마이그레이션 | **Alembic** | 테이블 변경을 코드로 관리·기록 |
| 지오 타입 | **GeoAlchemy2** | 좌표(위경도) 컬럼·공간 인덱스 |
| 인증 | **python-jose** (JWT) | 로그인 후 "출입증"(토큰) 발급 |
| 외부 통신 | **httpx** | TourAPI·TMDB 등 외부 API 호출(async) |
| 설정 | **pydantic-settings** | `.env`에서 설정값 안전하게 읽기 |
| DB 실행 | **Docker** (`postgis/postgis` 이미지) | PostgreSQL을 설치 꼬임 없이 한 번에 |

> 설치 목록은 [`requirements.txt`](./requirements.txt)에 있다.

---

## 2. 전체 아키텍처

```
┌─────────────┐        ┌─────────────┐
│ 모바일 앱(FE) │        │  AI 서비스   │   ← 팀원 담당(챗봇·NLU·LLM)
│  Kotlin     │        │ (별도)       │
└──────┬──────┘        └──────┬──────┘
       │  HTTP(JSON) + JWT     │  검색·추천 REST 호출
       ▼                       ▼
┌───────────────────────────────────────────┐
│           FastAPI  (이 레포 = 백엔드)         │
│  요청 → 라우터 → 서비스(로직) → 모델(DB)       │
└───────┬───────────────────────┬────────────┘
        │ SQLAlchemy(async)      │ httpx(async)
        ▼                        ▼
┌──────────────────┐   ┌──────────────────────┐
│ PostgreSQL+PostGIS│   │  외부 API (실시간)      │
│  (Docker: ktour-db)│  │  KTO TourAPI / TMDB    │
│  우리 데이터 저장   │   │  (사진·주소·주변 등)     │
└──────────────────┘   └──────────────────────┘
```

- **우리 DB에 저장**: 회원, 작품·장소의 *우리 큐레이션*(이름·좌표·작품↔장소 연결), 저장 기록.
- **저장 안 함(실시간 호출)**: 장소 사진·주소·운영시간·주변장소는 **TourAPI로 매번 조회**. (공모전 규칙 §9 참고)

---

## 3. 폴더 · 파일 구조

```
BE/
├─ app/                      # 애플리케이션 코드
│  ├─ main.py                # ▶ 앱 진입점 (uvicorn이 띄우는 대상)
│  │
│  ├─ core/                  # 기반(설정·DB연결·보안)
│  │  ├─ config.py           #   환경설정 (.env 읽기, JWT 키 등)
│  │  ├─ db.py               #   DB 연결 (엔진·세션·Base)
│  │  └─ security.py         #   JWT 발급/검증
│  │
│  ├─ models/                # DB 테이블을 파이썬 클래스로 (SQLAlchemy)
│  │  ├─ common.py           #   공용 enum (AuthProvider, ContentType 등)
│  │  ├─ user.py  region.py  content.py  place.py
│  │  ├─ mapping.py          #   content_place_mappings (작품↔장소) ★
│  │  ├─ course.py           #   courses / course_places
│  │  └─ (지연) content_translation · place_alias · interaction · api_log
│  │
│  ├─ routers/               # URL 창구 (요청을 받는 입구)
│  │  └─ health.py           #   GET /health
│  │
│  ├─ services/              # (예정) 비즈니스 로직 — 검색·추천·외부 API
│  ├─ schemas/               # (예정) 요청/응답 데이터 모양 (Pydantic)
│  └─ deps/                  # (예정) 공통 의존성 (로그인 확인·DB 세션)
│
├─ alembic/                  # DB 마이그레이션(테이블 변경 관리)
│  ├─ env.py                 #   마이그레이션 실행 설정(async + PostGIS)
│  └─ versions/
│     └─ 439ec7cb835f_*.py   #   첫 마이그레이션(7개 테이블)
│
├─ docker-compose.yml        # PostgreSQL+PostGIS 컨테이너 정의
├─ requirements.txt          # 설치할 파이썬 패키지 목록
├─ .env                      # 실제 설정값(비밀) — git 제외
├─ .env.example              # .env 견본(공유용)
├─ alembic.ini               # Alembic 기본 설정
└─ 문서: PROJECT_STRUCTURE.md(본 문서) · PROGRESS.md · PROJECT_REPORT.md · …
```

**계층 요약**: `routers(창구)` → `services(주방=로직)` → `models(DB 테이블)`. `schemas`는 입출력 데이터의 모양, `deps`는 공통 부품, `core`는 설정·DB·보안 같은 기반.

---

## 4. 요청이 흐르는 길 (예: `/health`)

가장 단순한 엔드포인트로 흐름을 보면:

```
브라우저/앱 → uvicorn → main.py(app) → routers/health.py → 응답 {"status":"ok"}
```

1. **`main.py`** — 앱을 만들고 라우터를 등록한다.
   ```python
   app = FastAPI(title=settings.APP_NAME)
   app.include_router(health.router)   # 창구 연결
   ```
2. **`routers/health.py`** — 실제 URL과 처리:
   ```python
   router = APIRouter(tags=["health"])

   @router.get("/health")
   def health_check():
       return {"status": "ok"}
   ```

앞으로 만들 기능(검색·로그인 등)도 이 패턴이다: **router에 URL 정의 → service에 로직 → model로 DB 접근.**

---

## 5. 핵심 부품 상세

### 5.1 설정 — `app/core/config.py` + `.env`
비밀값(DB 비번·JWT 키)을 코드에 박지 않고 `.env`에서 읽는다.
```python
class Settings(BaseSettings):
    APP_NAME: str = "K-tour BE"
    DATABASE_URL: str = "postgresql+asyncpg://ktour:ktour@localhost:5432/ktour"
    SECRET_KEY: str = "dev-only-change-me-in-env"   # JWT 서명 키 (운영선 .env로 교체)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14 # 토큰 유효 14일
    GOOGLE_CLIENT_ID: str = ""                       # 구글 토큰 검증용(선택)

settings = Settings()   # 앱 어디서나 settings.XXX 로 사용
```

### 5.2 DB 연결 — `app/core/db.py`
DB와 통신하는 부품 3종을 만든다.
```python
engine = create_async_engine(settings.DATABASE_URL, ...)      # 통신 엔진
AsyncSessionLocal = async_sessionmaker(engine, ...)           # 세션 공장

class Base(DeclarativeBase):                                  # 모든 모델의 부모
    metadata = MetaData(naming_convention=NAMING_CONVENTION)  # 제약 이름 규칙 통일

async def get_db():                                           # 라우터에 세션 주입
    async with AsyncSessionLocal() as session:
        yield session
```
- `Base`: 모든 테이블 모델이 상속하는 부모.
- `NAMING_CONVENTION`: FK·인덱스 이름을 일정하게(`fk_…`, `ix_…`) → 마이그레이션이 깔끔.

### 5.3 모델(테이블) — `app/models/`
테이블을 **파이썬 클래스**로 정의한다. 예를 들어 회원:
```python
class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_provider: Mapped[AuthProvider] = mapped_column(SAEnum(AuthProvider, name="auth_provider"))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    # 같은 소셜계정 중복 가입 방지
    __table_args__ = (UniqueConstraint("auth_provider", "provider_user_id", name="uq_users_provider"),)
```
장소는 **좌표(PostGIS)** 를 쓴다:
```python
class Place(Base):
    __tablename__ = "places"
    place_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326))  # 위경도(큐레이션)
    tour_content_id: Mapped[str | None] = mapped_column(String(20))    # TourAPI 조회키
```
> ⚠️ **컴플라이언스**: `places`엔 우리 큐레이션(이름·좌표)과 외부 참조 ID(`tour_content_id`)만 둔다. 주소·사진 등 TourAPI 응답값은 **저장하지 않는다(무캐싱)**.

`models/__init__.py`에서 **import한 모델만** 마이그레이션 대상이 된다 → 지금은 **7개 활성 / 5개 지연**.

### 5.4 마이그레이션 — `alembic/`
테이블을 손으로 안 만들고 **코드로 만들고 기록**한다.
- `alembic/versions/439ec7cb835f_*.py` — 첫 마이그레이션. `postgis` 확장 켜고 7개 테이블 생성.
- 적용 명령: `alembic upgrade head` → 현재 DB가 이 버전(`439ec7cb835f`)까지 적용됨.
- `env.py`는 **async 엔진 + GeoAlchemy2 + 시스템테이블 필터**로 설정돼 있다.

### 5.5 인증 — `app/core/security.py`
소셜 로그인 성공 후 **우리 서버가 발급하는 "출입증"(JWT)**.
```python
def create_access_token(user_id: int) -> str:   # user_id 담은 토큰 발급
    ...
def decode_access_token(token: str) -> int|None: # 토큰 검증 → user_id, 위조/만료면 None
    ...
```
이후 앱은 `Authorization: Bearer <token>` 헤더로 요청 → 서버가 검증. *(로그인 엔드포인트는 3단계에서 완성 예정)*

---

## 6. 데이터베이스 현황

**실행 환경**: Docker 컨테이너 `ktour-db` (`postgis/postgis:16-3.4`), 포트 `5432`.

**현재 테이블 (7개, 최소 컬럼)**

| 테이블 | 컬럼 | 역할 |
|---|---|---|
| `users` | user_id, nickname, auth_provider, provider_user_id | 회원(소셜) |
| `regions` | region_id, area_code, name, centroid | 지역 |
| `contents` | content_id, content_type, title_ko, poster_url | 작품 |
| `places` | place_id, name, geom, region_id, tour_content_id | 장소 |
| `content_place_mappings` ★ | mapping_id, content_id, place_id | **작품↔장소(핵심)** |
| `courses` | course_id, user_id, title, created_at | 코스 |
| `course_places` | course_place_id, course_id, place_id, visit_order | 코스 경유지 |

**지연 테이블 (기능 붙일 때 활성화)**: `favorites`·`search_history`·`content_translations`·`place_aliases`·`api_call_logs`(⚠️ TourAPI 호출 입증용, 4단계 필수).

> ✅ 2026-08-15 갱신: ERD 재설계분을 마이그레이션 `c4d4fdb425b1`로 반영했다(`genre_tags`·`address` 등 추가, `regions` 시도→시군구 계층화). 실데이터도 적재 완료 — 상세는 [`PROGRESS.md`](./PROGRESS.md).
> `user_saved_contents/regions`는 만들지 않았다. 코스 기능을 유지하기로 해서 `courses`와 역할이 겹치고, 즐겨찾기는 지연 테이블 `favorites`가 이미 있기 때문.

---

## 7. 실행 방법

### 7.1 최초 1회 세팅
```powershell
python -m venv .venv                 # 가상환경 생성
.venv\Scripts\activate               # 활성화
pip install -r requirements.txt      # 패키지 설치
```

### 7.2 DB 켜기 (Docker)
```powershell
docker compose up -d                 # 최초
docker start ktour-db                # 이후(껐다 켤 때)
```

### 7.3 서버 실행
```powershell
uvicorn app.main:app --reload
```
- 헬스체크: http://127.0.0.1:8000/health → `{"status":"ok"}`
- 자동 문서: http://127.0.0.1:8000/docs

### 7.4 DB 마이그레이션
```powershell
alembic upgrade head                 # 최신 스키마 적용
alembic current                      # 현재 버전 확인
alembic revision --autogenerate -m "메시지"   # 모델 바꾼 뒤 새 마이그레이션 생성
```

---

## 8. 개발 규칙 · 제약 (공모전)

1. **KTO TourAPI를 실시간 호출**해야 함 → 호출 내역을 `api_call_logs`에 기록(입증). *파일만 쓰면 실격.*
2. **API 응답을 DB에 저장 금지(무캐싱)** — 주소·사진·운영시간은 매번 실시간.
3. **이미지는 URL로만** 사용(다운로드/저장 금지).
4. **serviceKey 등 외부 키는 서버 환경변수(.env)에만** — 앱/깃허브 노출 금지.
5. **위치기반 회피**: 좌표를 서버로 받지 말고 place_id/region 기준으로.
6. **AI(챗봇)는 팀원 담당** — 이 백엔드엔 LLM 코드 없음.

---

## 9. 개발 진행 순서 (지금까지)

1. **설계** — 앱 컨셉 → 백엔드 설계 v1→v2→v3(FastAPI 확정)
2. **1단계 뼈대** — 폴더구조 + `main.py` + `/health` → 서버 구동 확인 ✅
3. **2단계 DB** — `db.py` → Docker PostgreSQL → 모델 정의 → Alembic → **7테이블 생성** ✅
4. **3단계 인증(착수)** — `config.py` JWT 설정 + `security.py` 추가 (엔드포인트 미완)
5. **2.5단계 데이터 적재** ✅ — 결정 4가지 확정 → 스키마 확장(`c4d4fdb425b1`) → `data/data.csv` 13,761행을
   4테이블로 분해 적재(작품 1,694 · 장소 9,811 · **연결 13,755**). 시드: [`scripts/seed_from_csv.py`](./scripts/seed_from_csv.py)

## 10. 앞으로 할 일

**바로 다음**
1. **3단계 인증 완성**: `/auth/google`·`/auth/kakao`·`/auth/me` 라우터 + 소셜 토큰 검증 + `get_current_user`
2. **4단계 place-detail** ⚠️합격 핵심: `places.tour_content_id` 채우기 → TourAPI 실시간 호출 + `api_call_logs` 활성화
3. 포스터 없는 작품 296편(18%) 보강 방안 결정

**남은 단계**
5. **4단계 place-detail** — TourAPI 실시간 + `api_call_logs` ⚠️합격 핵심
6. 5단계 검색·지도 엔드포인트 → 6~7단계 코스추천/AI 인터페이스 → 8~9단계 테스트·배포

---

*문서 성격: 구조·구성 설명(레퍼런스). 단계별 상황은 `PROGRESS.md`, 상세 일지는 `DEVELOPMENT_LOG.md` 참고.*
