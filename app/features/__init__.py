"""기능별 패키지. 한 기능 = 한 폴더 = `router.py` + `service.py` + `schema.py`.

새 기능을 추가할 때는 이 아래에 폴더를 하나 만들고
[`app/main.py`](../main.py)에 `include_router`만 한 줄 추가하면 된다.

  contents/  작품 검색·상세          (5단계 ✅)
  places/    촬영지 조회·반경        (5단계 ✅ / 4단계에서 TourAPI 상세 추가)
  regions/   지역 리졸브·목록        (5단계 ✅)
  health/    헬스체크                (1단계 ✅)
  auth/      소셜 로그인             (3단계 예정)
  courses/   코스 추천·저장          (6단계 예정)
"""
