"""작품(contents) 기능 — API_CONTRACT.md §3~§4.

  router.py   엔드포인트 (얇게: 검증 → service 호출 → 반환)
  service.py  DB 질의
  schema.py   요청/응답 모양

작품의 '촬영지 목록'만은 장소 도메인이라 `app.features.places.service`에 있다.
"""
