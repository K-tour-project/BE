"""DB 연결 설정 — SQLAlchemy 2.0 (async).

- engine: DB와 통신하는 엔진. 실제 연결은 쿼리할 때 맺어진다(지금 import만으론 연결 안 함).
- AsyncSessionLocal: 요청마다 DB 세션을 찍어내는 공장.
- Base: 모든 모델(테이블)이 상속하는 부모 클래스.
- get_db: 라우터에서 Depends(get_db)로 세션을 주입받는 의존성.
"""
from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 비동기 엔진 (연결은 실제 쿼리 시점에 lazy 하게 맺어진다)
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

# 세션 팩토리
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# 제약·인덱스 이름 규칙 — 마이그레이션이 일관된 이름을 갖도록(미지정 FK 등에 적용)
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """모든 모델(테이블)의 부모 클래스. 모델은 이 Base를 상속한다."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 라우터에서 Depends(get_db)로 DB 세션을 주입받는다."""
    async with AsyncSessionLocal() as session:
        yield session
