"""SQLAlchemy 모델 패키지 — 1차 활성 7개 테이블.

여기서 import한 모델만 Base.metadata에 등록되어 마이그레이션 대상이 된다.

활성(이번 마이그레이션) 7개:
  users · regions · contents · places · content_place_mappings · courses · course_places

지연(나중에 해당 기능 만들 때, 아래 import만 풀면 활성화):
  - content_translations  → app/models/content_translation.py   (9단계 다국어)
  - place_aliases         → app/models/place_alias.py           (4~5단계 매칭)
  - favorites, search_history → app/models/interaction.py       (즐겨찾기/좋아요·검색기록)
  - api_call_logs         → app/models/api_log.py               (4단계 TourAPI 호출 입증 ⚠️필수)
"""
from app.core.db import Base
from app.models.content import Content
from app.models.course import Course, CoursePlace
from app.models.mapping import ContentPlaceMapping
from app.models.place import Place
from app.models.region import Region
from app.models.user import User

# ── 지연 모델 (활성화 시 주석 해제) ──
# from app.models.content_translation import ContentTranslation
# from app.models.place_alias import PlaceAlias
# from app.models.interaction import Favorite, SearchHistory
# from app.models.api_log import ApiCallLog

__all__ = [
    "Base",
    "User",
    "Region",
    "Content",
    "Place",
    "ContentPlaceMapping",
    "Course",
    "CoursePlace",
]
