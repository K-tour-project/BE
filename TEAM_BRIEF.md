# 🎬 K-tour 백엔드 — 팀 공유 브리핑

> 영화·드라마 촬영지 기반 관광 코스 앱 "Every Trip"의 백엔드. 팀원이 빠르게 이해하도록 정리한 한 장 요약.

## 1. 백엔드가 하는 일 (한 줄)
**"어떤 작품이 어디서 촬영됐는지" 데이터를 관리하고, 그걸로 검색·지도·코스 추천을 제공하는 서버.**

## 2. 핵심 컨셉 — 왜 이렇게 설계했나
한국관광공사 **TourAPI에는 "작품 ↔ 촬영지" 연결 데이터가 없습니다.** 관광지 정보(좌표·주소)는 주지만, *"도깨비가 주문진 방파제에서 촬영됨"* 같은 연결은 없음.
→ **이 연결을 우리가 직접 큐레이션해서 DB에 만든 것이 이 앱의 차별점**이며, 그 심장이 `content_place_mappings` 테이블.

## 3. 데이터 구조 (현재 7개 테이블)
```
[데이터]  contents ─┐
                    ├─< content_place_mappings (★작품↔장소 연결★) >─ places ─< regions
          (작품)    ┘                                              (장소)   (지역)

[사용자]  users ─< courses ─< course_places >─ places
          (회원)   (코스)     (경유지·순서)
```
| 테이블 | 무엇 |
|---|---|
| `contents` | 작품(영화·드라마): 제목·유형·포스터 |
| `places` | 장소: 이름·좌표(PostGIS)·TourAPI 연결키 |
| **`content_place_mappings`** ★ | **작품↔장소 연결 (핵심 자산)** |
| `regions` | 지역코드·중심좌표(지역 검색용) |
| `users` | 회원(구글·카카오 소셜 로그인) |
| `courses` / `course_places` | 사용자가 저장한 코스 + 순서 있는 경유지 |

> 상세 ERD: [`erd.dbml`](./erd.dbml) → [dbdiagram.io](https://dbdiagram.io/d)에 붙여넣어 시각화

## 4. 팀원이 백엔드를 쓰는 방법 (API 경계)
- **프론트엔드**: 검색(작품/장소) → 지도 마커 → 장소 선택 → 코스 추천/저장 데이터를 REST로 제공 *(엔드포인트는 5~6단계에서 확정)*.
- **AI/챗봇 팀원**: 챗봇·LLM은 **팀원 소유**. 백엔드는 챗봇이 호출할 **REST 계약 3종**만 제공:
  1. `POST /contents/resolve` — 작품명 텍스트 → 작품 후보
  2. `GET /regions/resolve` — 지역명 → 지역코드 + 중심좌표
  3. `POST /courses/recommend` — place_id 목록 → 최적 코스
  > ⚠️ 위치는 **raw GPS 금지, `place_id`/`region_code`로** 주고받음.

## 5. 공모전 규칙 (설계에 반영된 제약)
| 규칙 | 반영 |
|---|---|
| TourAPI **실시간 호출 + 입증** | 호출 로그 테이블(4단계 활성화) |
| API 응답 **무캐싱** | `places`에 상세(운영시간·이미지) 저장 안 함 → 실시간 호출 |
| 인증키 서버 전용 / 이미지 URL만 / **GPS 미저장** | 코스는 좌표 대신 place_id |

## 6. 기술 스택 & 현재 상태
- **스택**: FastAPI · PostgreSQL+PostGIS · SQLAlchemy(async)+Alembic · 자체 JWT+소셜
- **현재**: DB 구동 + 7개 테이블 생성 완료(2단계) → **다음: 로그인(3단계) → TourAPI 연동(4단계)**
- 진행 현황: [`PROGRESS.md`](./PROGRESS.md)
