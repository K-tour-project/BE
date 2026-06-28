# K-tour BE — 진행 현황 (한눈에 보기)

> **앱**: 영화·드라마 촬영지 기반 관광 코스 앱(Every Trip) / **공모전 1차 마감 2026-09-21(월) 16:00**
> 문서 안내 — 로드맵·결정: [`PROJECT_REPORT.md`](./PROJECT_REPORT.md) · 상세 구현일지: [`DEVELOPMENT_LOG.md`](./DEVELOPMENT_LOG.md) · ERD: [`erd.dbml`](./erd.dbml) · 본 문서: 단계별 현황 스냅샷.

## 전체 로드맵 (9단계)
| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 설계(v3 FastAPI 확정) | ✅ |
| 1 | 프로젝트 뼈대 + `/health` | ✅ |
| **2** | **DB 연결 + Alembic + 모델(최소 7테이블)** | ✅ **완료** |
| **3** | 회원가입/로그인 (구글·카카오 소셜) | ⬜ **다음** |
| 4 | place-detail (TourAPI 실시간 + `api_call_logs` 입증) ⚠️합격핵심 | ⬜ |
| 5 | 검색·지도 엔드포인트 | ⬜ |
| 6 | 코스 추천 엔진 | ⬜ |
| 7 | AI(팀원 챗봇) 인터페이스 | ⬜ |
| 8 | 테스트·컴플라이언스 하드닝 | ⬜ |
| 9 | 배포·제출 준비 | ⬜ |

## 2단계 세부 진행 (완료 ✅)
| # | 작업 | 상태 |
|---|---|---|
| 2-1 | DB 연결 토대(`db.py`·패키지) | ✅ |
| 2-2 | DB 인프라(Docker PostGIS `ktour-db`) | ✅ *(PC 재부팅 시 `docker start ktour-db`)* |
| 2-3 | 옛 설계파일 정리(단일 기준화) | ✅ |
| 2-4 | 모델 정의 + mockup 정합성 점검 | ✅ |
| 2-5 | **유저 플로우 기준 7개 테이블로 축소**(5개 지연) | ✅ |
| 2-6 | Alembic `env.py`(async + geoalchemy2 + 시스템테이블 필터) | ✅ |
| 2-7 | **최소 컬럼 ERD로 모델 재정리**(테이블당 3~5컬럼) | ✅ |
| 2-8 | 마이그레이션 `439ec7cb835f` 적용 → **7개 테이블 DB 생성·검증** | ✅ |

## 현재 DB 테이블 (7개, 최소 컬럼)
| 테이블 | 컬럼 |
|---|---|
| `users` | user_id, nickname, auth_provider, provider_user_id |
| `regions` | region_id, area_code, name, centroid |
| `contents` | content_id, content_type, title_ko, poster_url |
| `places` | place_id, name, geom, region_id, tour_content_id |
| `content_place_mappings` ★ | mapping_id, content_id, place_id |
| `courses` | course_id, user_id, title, created_at |
| `course_places` | course_place_id, course_id, place_id, visit_order |

> 부가 컬럼(연도·줄거리·거리/시간·촬영회차 등)과 지연 5개 테이블(favorites·search_history·content_translations·place_aliases·**api_call_logs⚠️**)은 해당 기능 단계에서 추가.

## 📍 지금 위치 / ▶️ 다음 할 일
- **완료**: 2단계 종료 — 최소 7테이블이 DB에 생성됨. 검색→코스 저장의 데이터 토대 완성.
- **다음(3단계)**: 회원가입/로그인 — 구글·카카오 소셜 인증(JWT 발급), `users`에 사용자 적재.
