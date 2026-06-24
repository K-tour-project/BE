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

> 컬럼·관계·DDL 전체는 v3 설계서 §3 참조.

## 5. 진행 현황 (체크리스트)

- [x] **0. 설계** — v1(Supabase) → v2(적대적 검증·실격리스크 수정) → **v3(FastAPI 확정)**
- [x] **1. 프로젝트 뼈대 + `/health`** — FastAPI 구조·설정·헬스체크. **서버 구동 검증 완료** ✅ ← *현재 위치*
- [ ] **2. DB 연결 + Alembic** — PostgreSQL+PostGIS 연결, 12개 테이블 첫 마이그레이션 *(Docker 필요)*
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

- **설계서 v3** (현행 기준, FastAPI): `K-tour-backend-design-v3.md`
- 설계서 v1·v2 (Supabase 기반, 변천 기록 및 적대적 검증 결과)
- 이전 팀 설계문서(개요·데이터정의·DB설계·API명세)는 새 출발을 위해 제거됨 — git 히스토리(원격 `main` 커밋 `35edf75`)에 보존되어 복구 가능.

---

*본 보고서는 단계가 진행될 때마다 §5 체크리스트와 현황을 갱신한다.*
