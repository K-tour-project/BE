# K-tour BE — 진행 현황 (한눈에 보기)

> **앱**: 영화 촬영지 기반 관광 코스 앱(Every Trip) / **공모전 1차 마감 2026-09-21(월) 16:00**
> 문서 안내 — 로드맵·결정: [`PROJECT_REPORT.md`](./PROJECT_REPORT.md) · 상세 구현일지: [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md) · 구조 설명: [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) · ERD: [`erd.dbml`](./erd.dbml) · 본 문서: 단계별 현황 스냅샷.

## 전체 로드맵
| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 설계(v3 FastAPI 확정) | ✅ |
| 1 | 프로젝트 뼈대 + `/health` | ✅ |
| 2 | DB 연결 + Alembic + 모델(최소 7테이블) | ✅ |
| **2.5** | **스키마 확장 + 실데이터 적재(CSV 13,761행)** | ✅ **완료 (2026-08-15)** |
| 3 | 회원가입/로그인 (구글·카카오 소셜) | 🔶 착수(JWT 토대만) |
| **4** | **place-detail (TourAPI 실시간 + `api_call_logs` 입증) ⚠️합격핵심** | 🔶 **골격 완성 → 키 대기 중** |
| 5 | 검색·지도 엔드포인트 | ⬜ |
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
| 1 | 로그인 방식 | **소셜(구글·카카오) 전용** — 이메일+비번 없음, passlib/bcrypt 미사용 |
| 2 | 코스 기능 | **유지** — courses·course_places 그대로, 6단계에서 추천 구현 |
| 3 | 장르 저장 | **배열 컬럼** `contents.genre_tags` (+ GIN 인덱스) |
| 4 | 데이터 출처 | **CSV를 우리 DB로**, 장소 상세(운영시간·이미지)는 **TourAPI 실시간** |
| 5 | 드라마 | 1차는 **영화만**. 드라마는 나중에 **INSERT만으로** 추가 가능하게 설계 |

> 5번 근거: CSV가 KMDb(한국영화DB) 출신이라 `tmdb_type=tv`가 24행뿐. 그래서 `content_type` enum은
> `movie/drama/show`를 **그대로 유지**하고, 영화 전용값(`kmdb_code`·`runtime`)은 nullable,
> `source`로 출처 구분, `mappings.episode`(촬영회차)를 **미리** 만들어 뒀다. → 드라마 추가 시 마이그레이션 불필요.

## 현재 DB 상태 (리비전 `c4d4fdb425b1`)
| 테이블 | 행수 | 주요 컬럼 |
|---|---|---|
| `regions` | **244** (시도 17 + 시군구 227) | region_id, name, **level**, **parent_region_id**, area_code, sigungu_code, centroid |
| `contents` | **1,694** | content_id, content_type, title_ko, poster_url, **kmdb_code**, source, source_url, production_year, original_title, overview, **genre_tags**, tmdb_id, tmdb_type, vote_average, runtime |
| `places` | **9,811** | place_id, name, geom, region_id, tour_content_id, **kmdb_place_id**, source, **address**, road_address |
| `content_place_mappings` ★ | **13,755** | mapping_id, content_id, place_id, **kmdb_case_id**, **scene_description**, characters, **episode** |
| `users` | 0 | user_id, nickname, auth_provider, provider_user_id |
| `courses` / `course_places` | 0 / 0 | (3~6단계에서 사용) |

**데이터 품질**: 장소 좌표 100%(9,811/9,811) · 장소↔지역 연결 100% · 지역 중심점 100%(244/244) · 작품 장르 82% · 포스터 82%.
**인덱스**: `idx_places_geom`(GIST, 반경검색 검증됨) · `ix_contents_genre_tags`(GIN) · `ix_places_region_id` · `ix_cpm_place_id`.

> 지연 5테이블(favorites·search_history·content_translations·place_aliases·**api_call_logs⚠️**)은
> [`app/models/__init__.py`](./app/models/__init__.py)에서 import 주석 처리 상태. 해당 기능 단계에서 활성화.

## 4단계 준비 (TourAPI) — 골격 완성, 키 대기 중
| 항목 | 상태 |
|---|---|
| [`app/services/tour_api.py`](./app/services/tour_api.py) — 클라이언트(상세·이미지·위치기반·키워드·관광사진) | ✅ |
| [`scripts/check_tour_api.py`](./scripts/check_tour_api.py) — 키 자가진단(실호출 시연) | ✅ |
| `config.py` — `TOUR_API_KEY`·베이스URL·타임아웃 (키 없으면 나머지 기능 정상 동작) | ✅ |
| [`.env.example`](./.env.example) — 발급 절차·주의사항 문서화 | ✅ |
| **`TOUR_API_KEY` 실제 발급** (data.go.kr) | ⬜ **은서 님 작업** |
| `places.tour_content_id` 매칭 (현재 0/9,811) | ⬜ |
| `api_call_logs` 테이블 활성화(호출 입증) | ⬜ |

**신청할 서비스 2개** (같은 계정의 인증키 하나로 공용)
- 한국관광공사_국문 관광정보 서비스_GW — https://www.data.go.kr/data/15101578/openapi.do
- 한국관광공사_관광사진 정보_GW — https://www.data.go.kr/data/15101914/openapi.do

**매칭 전략(결정)**: **온디맨드 + 인기곳 사전매칭**. 개발계정이 1,000건/일이라 9,811곳 전수 매칭은
10일이 걸려 비현실적 → 사용자가 실제로 연 장소만 그때 매칭해 `tour_content_id`를 기록하고,
시연용 인기 촬영지 300~500곳만 미리 배치 매칭한다. '실시간 호출' 요건에도 자연스럽게 부합.

## 📍 지금 위치 / ▶️ 다음 할 일
- **완료**: DB가 더 이상 빈 껍데기가 아님. 작품 1,694편 ↔ 촬영지 9,811곳의 연결 13,755건이 실제로 조회된다.
  - 검증된 쿼리: 작품→촬영지(장면설명 포함) · 지역 반경 5km→촬영지+포스터(GIST 인덱스 사용) · 시드 재실행 무중복.
- **막힘 해소**: 4·5·6단계가 데이터 부재로 막혀 있었으나 이제 착수 가능.
- **바로 다음**: `TOUR_API_KEY` 발급 → `python -m scripts.check_tour_api` 로 확인 → 매칭 배치 + `/places/{id}` 구현.
- **그다음(3단계)**: 소셜 로그인 완성. JWT 토대([`app/core/security.py`](./app/core/security.py))는 있고
  **`/auth/google`·`/auth/kakao`·`/auth/me` 라우터 + 소셜 토큰 검증 + `deps/get_current_user`가 미구현.**
- **알려진 갭**: 작품 296편(18%)에 포스터 없음 · 드라마 10편뿐(영화 1,684편).
- **미커밋**: 이번 작업분 전체가 아직 커밋 전(main HEAD `d3a8bfc`). `data/data.csv`(14.7MB) 커밋 여부 결정 필요.
