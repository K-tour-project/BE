"""SQLAlchemy 모델 패키지 — 1차 활성 7개 테이블.

여기서 import한 모델만 Base.metadata에 등록되어 마이그레이션 대상이 된다.

활성(이번 마이그레이션) 7개:
  users · regions · contents · places · content_place_mappings · courses · course_places

4단계에서 추가 활성화:
  - api_call_logs         → app/models/api_log.py    (TourAPI 호출 입증 ⚠️실격 방지 필수)

3단계에서 추가 활성화:
  - refresh_tokens, email_verifications → app/models/auth.py  (로그아웃·이메일 인증)

지연(나중에 해당 기능 만들 때, 아래 import만 풀면 활성화):
  - content_translations  → app/models/content_translation.py   (9단계 다국어)
  - place_aliases         → app/models/place_alias.py           (4단계 매칭 별칭 캐시)
  - favorites, search_history → app/models/interaction.py       (즐겨찾기/좋아요·검색기록)
"""
from app.core.db import Base
from app.models.api_log import ApiCallLog
from app.models.auth import EmailVerification, RefreshToken
from app.models.course import Course, CoursePlace
from app.models.place import Place
from app.models.product import Product
from app.models.product_detail import DramaDetail, MovieDetail
from app.models.region import Region
from app.models.user import User

# ── 지연 모델 (활성화 시 주석 해제) ──
# from app.models.content_translation import ContentTranslation
# from app.models.place_alias import PlaceAlias
# from app.models.interaction import Favorite, SearchHistory

__all__ = [
    "Base",
    "User",
    "Region",
    "Place",
    "Product",
    "MovieDetail",
    "DramaDetail",
    "Course",
    "CoursePlace",
    "ApiCallLog",
    "RefreshToken",
    "EmailVerification",
]
