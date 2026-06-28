import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from geoalchemy2 import alembic_helpers

# 앱 설정 + 모델 메타데이터 로드
from app.core.config import settings
from app.core.db import Base
import app.models  # noqa: F401  (활성 7개 모델을 Base.metadata에 등록)

# Alembic Config 객체 (alembic.ini 값 접근)
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# .env의 DATABASE_URL(asyncpg)을 Alembic에 주입. ConfigParser 보간 때문에 %는 %%로 이스케이프.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

# autogenerate 대상 메타데이터
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """우리 메타데이터에 정의한 테이블만 비교 대상에 포함.

    PostGIS 이미지에 기본 내장된 tiger 지오코더·topology 시스템 테이블
    (addr·county·edges·topology 등)을 Alembic이 'DROP'하려는 것을 막는다.
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


# 공통 옵션: 타입 비교 + 우리 테이블만 + GeoAlchemy2 헬퍼(geography 렌더링·공간인덱스 처리)
CONFIGURE_KWARGS = dict(
    target_metadata=target_metadata,
    compare_type=True,
    include_name=include_name,
    render_item=alembic_helpers.render_item,
    include_object=alembic_helpers.include_object,
    process_revision_directives=alembic_helpers.writer,
)


def run_migrations_offline() -> None:
    """오프라인(SQL 스크립트만 출력) 모드."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONFIGURE_KWARGS,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **CONFIGURE_KWARGS)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """비동기 엔진을 만들어 커넥션을 컨텍스트에 연결."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """온라인(실DB 연결) 모드."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
