# K-tour BE — 개발 현황 및 로드맵 (보고서)

> 영화·드라마 촬영지 기반 관광 코스 앱의 백엔드. 본 문서는 지금까지의 결정·진행 상황과 앞으로의 작업 순서를 한 곳에 정리한 참고용 보고서다.
> 최종 갱신: 2026-06 / 작성 기준 단계: **1단계(서버 뼈대) 완료**

---

## 1. 프로젝트 개요

- **앱**: 작품(영화/드라마) 또는 지역 검색 → 지도에 촬영지·포스터 마커 → 장소 다중 선택 → 최적 관광 동선 추천 → 코스 저장. 자연어 챗봇(팀원 담당).
- **공모전**: 2026 한국관광공사 관광데이터 활용 공모전(앱·웹 부문). **1차 심사 서류 마감 2026-09-21(월) 16:00**, 최종 발표심사 10-28, 시상식 11-05.
- **핵심 자산**: "작품 ↔ 촬영지 관계"(관계유형·추천이유) 큐레이션. **TourAPI에는 이 매핑이 없으므로 우리가 직접 만드는 것이 이 앱의 차별점**이다.

## 2. 기술 스택 (확정)

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어·프레임워크 | **Python + FastAPI** | 비동기 외부 API 호출에 강함, 자동 API 문서(/docs), Pydantic 검증 |
| DB | **PostgreSQL + PostGIS** | 작품↔장소 M:N 관계 + 지도(지오) 쿼리 + 한글 검색 동시 충족 |
| ORM·마이그레이션 | **SQLAlchemy 2.0 (async) + Alembic** | 코드로 스키마 관리, 변경 이력 추적 |
| 인증 | **자체 JWT** (passlib[bcrypt] + python-jose) | Supabase 미사용 결정에 따라 자체 구현 |
| 외부 연동 | **httpx (async)** | KTO TourAPI(필수)·TMDB/KMDb·Kakao/ODsay |
| AI(챗봇) | **팀원 별도 서비스** | 내 백엔드는 AI-불가지론, 검색·추천 REST만 제공 (§7) |

> **결정 경위**: 초기엔 Supabase(관리형 PG + Auth + Edge Functions)를 검토했으나(설계 v1·v2), **FastAPI + 자체 호스팅 PostgreSQL + 자체 JWT 인증**으로 전환(설계 v3, 현행 기준). 상세 설계는 v3 설계서 참조(§9).

## 3. 공모전 핵심 제약 (실격 방지 — 반드시 준수)

1. **KTO TourAPI를 실시간 호출**하고 `api_call_logs`로 입증한다. 파일 데이터만 쓰면 **심사 제외**.
2. **API 응답 무캐싱.** DB 저장은 ①사용자 데이터 ②외부 참조 ID ③우리 큐레이션(+큐레이션 좌표)만.
3. **serviceKey(인증키)는 서버 전용** — 앱·클라이언트에 절대 노출 금지.
4. **이미지는 URL 표시만** — 다운로드·저장 금지.
5. **위치기반서비스 등록 회피** — GPS 좌표를 서버로 보내지 않음(입력은 `place_id`/`region_code`). 위치기반 조회는 반경 **20km** 제한.
6. **금지/폐기 API 차단**: 산악관광정보, 지역코드(`areaCode2`)·서비스코드(`categoryCode2`) 조회.
7. **원천 데이터 무수정 / KTO 로고·명칭 미사용.**

## 4. 데이터 모델 (12 테이블)

`users`(사용자·자체인증) · `regions`(지역) · `contents`(작품) · `places`(장소) · **`content_place_mappings`(작품↔장소, 핵심 자산)** · `place_aliases`(매칭 별칭) · `content_translations`(다국어) · `courses`(코스) · `course_places`(경유지) · `favorites`(즐겨찾기) · `search_history`(검색기록) · `api_call_logs`(KTO 호출 입증).

> 스키마 **단일 기준은 코드**(`app/models/`)·[`erd.dbml`](./erd.dbml). 현재 **활성 7개**(최소 컬럼: users·regions·contents·places·content_place_mappings·courses·course_places)만 마이그레이션됨. 나머지 5개(content_translations·place_aliases·favorites·search_history·**api_call_logs⚠️**)와 부가 컬럼은 해당 기능 단계에서 추가. 설계 "왜"는 [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md).

## 5. 진행 현황 (체크리스트)

- [x] **0. 설계** — v1(Supabase) → v2(적대적 검증·실격리스크 수정) → **v3(FastAPI 확정)**
- [x] **1. 프로젝트 뼈대 + `/health`** — FastAPI 구조·설정·헬스체크. **서버 구동 검증 완료** ✅
- [x] **2. DB 연결 + Alembic** — ✅ **완료**: 최소 **7개 테이블** 모델 + 마이그레이션 `439ec7cb835f` 적용·검증. 상세 [`PROGRESS.md`](./PROGRESS.md)
- [ ] **3. 회원가입/로그인** — JWT 자체 인증(access/refresh), bcrypt
- [ ] **4. `place-detail`** — KTO TourAPI 실시간 연동 + `api_call_logs` 입증 *(공모전 합격 핵심)*
- [ ] **5. 검색·지도 엔드포인트** — contents/places/regions, 자동완성·초성
- [ ] **6. 코스 추천 엔진** — 거리행렬·방문순서(NN+2opt)·라우팅 폴백
- [ ] **7. AI 연동 인터페이스 확정** — 팀원 챗봇용 REST 계약(§7)
- [ ] **8. 테스트·관측성·컴플라이언스 하드닝** — pytest, request_id 로깅, 금지API 검사
- [ ] **9. 배포·제출 준비** — 다국어(ko/en) 입증, 데모 시나리오

## 6. 다음 단계(2단계) 상세

1. **DB 띄우기** — Docker Desktop 설치 → `docker compose up -d`로 PostgreSQL+PostGIS 구동. *(현재 PC에 Docker 미설치 — 설치 필요. 대안: 로컬 PostgreSQL 설치 또는 관리형 PG)*
2. **패키지 추가** — `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `geoalchemy2`
3. **Alembic 초기화** → 모델 정의 → 첫 마이그레이션으로 12개 테이블 생성
4. ⚠️ **주의**: PostGIS 타입·enum·generated 컬럼·trgm 인덱스는 Alembic autogenerate가 못 잡으므로 **수동 보정** 필요(v3 §3 참조).

## 7. AI 팀원과의 인터페이스 (경계)

챗봇·자연어이해(NLU)·대화 세션·LLM 호출은 **전부 팀원의 별도 서비스가 소유**한다. 내 백엔드는 AI-불가지론이며, 팀원 챗봇이 호출할 **REST 계약 3종**만 제공한다:

| 엔드포인트 | 역할 |
|---|---|
| `POST /contents/resolve` | 작품 제목 텍스트 → content 후보 랭킹 |
| `GET /regions/resolve?name=` | 지역명 → `region_code` + 중심좌표 |
| `POST /courses/recommend` | 해소된 `place_ids`/`region_code` + 조건 → 최적 코스 (raw GPS 금지) |

> 흐름: 팀원이 NLU로 문자열 추출 → (1)(2)로 id 해소 → (3)에 투입. 요청/응답 상세는 v3 설계서 §4 참조.

## 8. 실행 방법

```powershell
cd "D:\workspace\2026 tourism data contest\BE"
python -m venv .venv          # 최초 1회 (이미 생성됨)
.venv\Scripts\activate
pip install -r requirements.txt   # 최초 1회 (이미 설치됨)
uvicorn app.main:app --reload
```

- 헬스체크: http://127.0.0.1:8000/health → `{"status":"ok"}`
- 자동 API 문서: http://127.0.0.1:8000/docs

## 9. 참고 문서

- **본 문서(`PROJECT_REPORT.md`)가 단일 기준** — 로드맵·결정·제약.
- **[`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md)** — 단계별 구현 일지(무엇을·어떻게·왜).
- **스키마의 진짜 기준은 코드**: `app/models/` (12개 테이블).
- 옛 설계문서(개요·데이터정의·DB설계·API명세·Supabase 스키마)는 혼동 방지를 위해 **전부 삭제** — git 커밋 `35edf75`에 보존되어 복구 가능.

## 10. 구현 기록 (단계별 상세)

단계가 진행될 때마다 "무엇을 · 어떻게 구현했는지 · 어떻게 검증했는지"를 여기에 누적 기록한다.

### 1단계 — 프로젝트 뼈대 + `/health` ✅ 완료
- **구현 내용**
  - `app/main.py` — FastAPI 인스턴스 생성, 라우터 등록, 루트(`/`) 엔드포인트.
  - `app/core/config.py` — `pydantic-settings`로 `.env`/환경변수 로딩(`APP_NAME`, `ENVIRONMENT`, `DATABASE_URL`). 기본값을 둬서 `.env` 없이도 구동.
  - `app/routers/health.py` — `GET /health` → `{"status":"ok"}`.
  - `app/{services,models,schemas,deps}/` — 다음 단계용 빈 패키지(역할 주석만).
  - 부가 파일 — `requirements.txt`, `docker-compose.yml`(PostgreSQL+PostGIS), `.env`/`.env.example`, Python `.gitignore`, `README.md`.
- **검증**: `python -m venv .venv` → `pip install`(fastapi·uvicorn·pydantic-settings) → `uvicorn app.main:app`. 실제 구동 후 `GET /health` → `{"status":"ok"}`, `GET /` 정상, `/docs` 자동 문서 확인. ✅
- **커밋**: 브랜치 `feat/fastapi-scaffold`, 커밋 `2c8d0f7`.

### 2단계 — DB 연결 + Alembic + 모델 🔧 진행 중
- **(2-1) DB 연결 토대 — 완료**
  - `requirements.txt`에 DB 패키지 추가: `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `geoalchemy2`. (설치 확인: SQLAlchemy 2.0.51 / asyncpg 0.31 / alembic 1.18 / GeoAlchemy2 0.20)
  - `app/core/db.py` 생성 — 비동기 `engine`, `AsyncSessionLocal`(세션 팩토리), `Base`(모델 부모 클래스), `get_db`(라우터 주입용 의존성).
  - **검증**: `import app.core.db` + `import app.main` 정상 임포트(DB 미연결 상태에서 코드 유효성만 확인), `DATABASE_URL`이 비밀번호 가린 채 로드됨. ✅
- **(2-2) DB 인프라 구동 — 완료 ✅** (재시작 후): WSL2 설치+재부팅 → Docker 엔진(Server v29.5.3) → `docker compose up -d`로 PostGIS 컨테이너 `ktour-db` 기동. `pg_isready`·`postgis` 확장 확인.
- **(2-3) 옛 설계파일 정리 — 완료 ✅**: 상위 폴더 옛 파일 7개 삭제, 단일 기준 = 본 문서.
- **(2-4) 12개 모델 정의 — 완료 ✅**: `app/models/`를 도메인별 모듈로 작성, 컴플라이언스(§3)를 스키마에 반영. import+`configure_mappers`+12테이블 등록 검증.
- **(2-5) UI mockup 정합성 보강 — 완료 ✅**: 소셜로그인·다일코스·코스좋아요·채널·추천/인기·촬영회차 필드 추가, 즐겨찾기 중복방지 버그 수정. (인물·리뷰는 보류)
- **(2-6) 남은 작업**: Alembic 첫 마이그레이션 작성·검토 → `alembic upgrade head`로 12개 테이블 DB 생성.

> 📓 위 (2-2)~(2-5)의 "무엇을·어떻게·왜" 상세는 [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md)에 정리.

---

*본 보고서는 단계가 진행될 때마다 §5 체크리스트와 §10 구현 기록을 갱신한다. 상세 구현 일지는 [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md).*
