"""환경설정. .env 파일 또는 환경변수에서 값을 읽는다.

코드에 비밀값(DB 비번·API 키)을 직접 박지 않고 여기로 모은다.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "K-tour BE"
    ENVIRONMENT: str = "local"

    # --- 아래는 다음 단계에서 사용 (지금은 기본값만 있어도 서버가 뜬다) ---
    # 2단계(DB): PostgreSQL 연결 문자열
    DATABASE_URL: str = "postgresql+asyncpg://ktour:ktour@localhost:5432/ktour"


# 앱 어디서나 `from app.core.config import settings` 로 가져다 쓴다.
settings = Settings()
