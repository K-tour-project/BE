"""Active SQLAlchemy models, including My Page saves and profile images.

Importing a model registers it in Base.metadata. Deferred translation, alias and
search-history models remain inactive until their own migrations are implemented.
"""
from app.core.db import Base
from app.models.api_log import ApiCallLog
from app.models.auth import EmailVerification, RefreshToken
from app.models.course import Course, CoursePlace
from app.models.favorite import PlaceFavorite, ProductFavorite
from app.models.place import Place
from app.models.product import Product
from app.models.product_detail import DramaDetail, MovieDetail
from app.models.region import Region
from app.models.user import User
from app.models.user_profile import UserProfile

# ── 지연 모델 (활성화 시 주석 해제) ──
# from app.models.content_translation import ContentTranslation
# from app.models.place_alias import PlaceAlias
# from app.models.interaction import SearchHistory

__all__ = [
    "Base",
    "User",
    "UserProfile",
    "PlaceFavorite",
    "ProductFavorite",
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
