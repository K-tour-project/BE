# 영화·드라마·장소 import

SQLAlchemy Entity는 `app/models`, 응답 DTO는 `app/features/contents/schema.py`,
조회 Service는 `app/features/contents/service.py`에 있다. 기존 프로젝트에는 별도
Repository 계층이 없어 새 Repository를 도입하지 않고 AsyncSession을 사용한다.

## 스키마

`a12b34c56d78` migration은 기존 products를 삭제하거나 재생성하지 않는다.
기존 PK `product_id` 및 모든 공통 컬럼을 재사용하고 category만 MOVIE/DRAMA로 변환한다.
기존 드라마 전용 컬럼과 match_similarity도 보존한다. 드라마 전용 값은 새 상세 테이블로
복사하고, 이후 import 및 상세 조회에서는 새 상세 테이블을 사용한다.

- MovieDetail / movie_details: product_id(BIGINT PK/FK), runtime(INT).
- DramaDetail / drama_details: product_id(BIGINT PK/FK), overview_translated(BOOLEAN),
  content_type(TEXT), networks(TEXT), episode_count(INT), cast(TEXT).
- 두 FK 모두 products.product_id 참조, ON DELETE CASCADE. Product 관계는 각각 1:0..1.
- 상세 응답은 category로 구분한다. 영화는 공통 필드+runtime, 드라마는 공통 필드+
  is_overview_translated/product_type/networks/episode_count/lead_actors를 반환한다.
- `b23c45d67e89`는 tmdb_id를 제거하고 import hash를 category+title+first_air_date 기준으로
  전환한다. products.product_id와 모든 상세 FK는 유지한다. 제거된 tmdb_id 값은 downgrade로 복구되지 않는다.
- downgrade는 드라마 값을 기존 컬럼으로 복사하지만 영화 전용 값은 상세 테이블 제거 시 소실된다.

## 실제 CSV 매핑

| 영화 CSV | 드라마 CSV | products 컬럼 |
|---|---|---|
| title | 제목 | title |
| overview | 줄거리 | overview |
| release_date | 최초방영일 | first_air_date |
| genres | 장르 | genres |
| poster | 포스터 | poster_url |
| vote_average | 평점 | rating |
| popularity | 인기도 | popularity |
| category | 카테고리 | category |

영화 runtime은 movie_details.runtime에 저장한다. tmdb_id는 CSV에 남아 있어도 무시하며 없어도 된다.
드라마 줄거리_번역여부→overview_translated, 작품유형→content_type,
networks→networks, 에피소드수→episode_count, 주연배우→cast로 저장한다.
genres는 두 파일 모두 `|` 구분으로 정규화한다. 배우 목록은 원래 `|` 구분 TEXT를 유지한다.
빈 문자열은 NULL, 날짜/숫자/BOOLEAN은 타입 변환·검증한다.

## 실행과 중복 방지

대상 DB에 기존 products가 있는지 먼저 확인한다. 오래된 DB에서 무조건 upgrade head를
실행하면 과거 migration도 실행되므로 대상 DB와 현재 revision을 반드시 확인한다.

```powershell
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m scripts.seed_places_products --dry-run
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m scripts.seed_places_products
```

`--only products` 또는 `--only places`로 선택 가능. 두 작품 CSV는 각각 읽으며 합치지 않는다.
공통 Product를 저장·flush하여 ID를 얻은 후 같은 ID로 상세 행을 upsert한다.
영화와 드라마 모두 category+title+first_air_date를 import 식별자로 사용한다.
이 식별자는 중복 확인용이며 PK가 아니다. PK는 products의 PostgreSQL 시퀀스가 생성하고,
movie_details/drama_details에서는 별도의 ID를 생성하지 않는다.
기존 데이터는 제목·카테고리·날짜가 일치하면 ID를 재사용한다. 모호한 작품은 오류로 중단한다.
식별자 hash를 기존 csv_row_hash UNIQUE 컬럼에 저장하여 내용이 바뀌어도 갱신한다.
동일 식별자의 완전 중복은 제거하고 값이 충돌하면 중단한다. 날짜/제목이 변경된 작품은
외부 고유 ID가 없으므로 새 작품으로 취급될 수 있다.
전체 import는 단일 트랜잭션이며 advisory lock으로 동시 실행을 직렬화한다.
오류 시 전체 rollback, 어떤 기존 행도 삭제하지 않는다.

places.csv의 제목/장소명/주소/위도/경도/source_url/데이터출처/위치정보출처는 각각
places.title/name/address/latitude/longitude/source_url/source/location_source에 대응한다.
없어진 장소유형 컬럼은 필수가 아니며 기존 place_type은 유지한다.
장소는 제목·이름·출처·주소·URL·좌표로 식별한다. 같은 제목·이름·출처가 유일할 때는
주소/좌표 변경도 기존 ID에 반영한다. 복수 출처 URL/좌표는 별도 행으로 보존한다.
기존 중복 행과 CSV에서 사라진 행은 삭제하지 않는다. 장소명이 바뀌면 새 장소일 수 있다.
좌표는 DB의 소수점 7자리로 맞추고 geom도 갱신한다. 위치 변경 시 region_id와 TourAPI 매칭은
초기화하여 예전 위치의 연결이 노출되지 않게 한다. 재매칭은 별도 작업이다.

검증: `python -m unittest discover -s tests`. dry-run은 DB 연결 없이 CSV만 검증한다.
