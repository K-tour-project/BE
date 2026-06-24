"""SQLAlchemy 모델 패키지 (12개 테이블).

Alembic autogenerate와 매퍼(relationship) 설정이 모든 모델을 인식하려면 여기서
한 번씩 import 해줘야 한다 → Base.metadata에 12개 테이블이 모두 등록된다.
"""
from app.core.db import Base
from app.models.api_log import ApiCallLog
from app.models.content import Content, ContentTranslation
from app.models.course import Course, CoursePlace
from app.models.interaction import Favorite, SearchHistory
from app.models.mapping import ContentPlaceMapping
from app.models.place import Place, PlaceAlias
from app.models.region import Region
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Region",
    "Content",
    "ContentTranslation",
    "Place",
    "PlaceAlias",
    "ContentPlaceMapping",
    "Course",
    "CoursePlace",
    "Favorite",
    "SearchHistory",
    "ApiCallLog",
]
