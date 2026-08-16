"""환경설정. .env 파일 또는 환경변수에서 값을 읽는다.

코드에 비밀값(DB 비번·API 키·서명 키)을 직접 박지 않고 여기로 모은다.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "K-tour BE"
    ENVIRONMENT: str = "local"

    # --- 아래는 각 단계에서 사용 (기본값이 있어 값 없이도 서버가 뜬다) ---
    # 2단계(DB): PostgreSQL 연결 문자열
    DATABASE_URL: str = "postgresql+asyncpg://ktour:ktour@localhost:5432/ktour"

    # 3단계(인증) — 우리 서버가 발급하는 JWT
    # SECRET_KEY: JWT 서명 키. 운영에선 반드시 .env로 교체(절대 노출 금지). 기본값은 개발용.
    SECRET_KEY: str = "dev-only-change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14  # 14일 (모바일 앱 편의)

    # 3단계(소셜 검증) — 선택값
    # GOOGLE_CLIENT_ID: 구글 ID 토큰의 aud(수신 대상)가 우리 앱이 맞는지 검증용.
    #   비워두면 aud 검증을 생략한다(개발 단계 허용, 운영에선 채우는 걸 권장).
    GOOGLE_CLIENT_ID: str = ""

    # 4단계(TourAPI) — 한국관광공사 오픈API
    # ⚠️ TOUR_API_KEY는 data.go.kr에서 발급받은 **일반 인증키(Decoding)**를 .env에만 넣는다.
    #    앱(APK)이나 git에 절대 넣지 않는다 — 노출 시 공모전 실격 사유이며 키는 2년 유효.
    #    비어 있으면 TourAPI 호출부가 명확한 에러를 내고 나머지 기능은 정상 동작한다.
    TOUR_API_KEY: str = ""
    # ⚠️ 경로 뒤 숫자는 서비스마다 다르다. 추측하지 말 것 — 아래는 전부 실호출로 확인한 값이다.
    #    (KorService는 1이 폐기되고 2가 살아 있는데, 나머지 둘은 반대로 1만 존재한다.)

    # ① '한국관광공사_국문 관광정보 서비스_GW' (data.go.kr/data/15101578) — ✅ 승인·동작 확인
    #    KorService1은 폐기(NO_OPENAPI_SERVICE_ERROR) → 반드시 KorService2 + `~2` 오퍼레이션.
    TOUR_API_BASE: str = "http://apis.data.go.kr/B551011/KorService2"

    # ② '한국관광공사_관광사진 정보_GW' (data.go.kr/data/15101914) — ⚠️ 키 미승인 상태
    #    PhotoGalleryService2는 존재하지 않는다(12번 오류). Service**1** + galleryList1이 맞다.
    #    현재 이 키로 호출하면 403 SERVICE_KEY_IS_NOT_REGISTERED → data.go.kr에서 활용신청 필요.
    #    확인된 오퍼레이션: galleryList1 · gallerySearchList1 · galleryDetailList1
    TOUR_PHOTO_API_BASE: str = "http://apis.data.go.kr/B551011/PhotoGalleryService1"

    # ③ '한국관광공사_기초지자체 중심 관광지 정보' (data.go.kr/data/15128559) — ✅ 승인·동작 확인
    #    지자체별로 '다른 관광지와 가장 많이 연결되는 중심 관광지'와 그 연관 관광지를 준다.
    #    TarRlteTarService2는 400 → Service**1** + areaBasedList1이 맞다.
    #    ⚠️ 코드 체계가 다르다 — areaCd/signguCd는 TourAPI 지역코드가 아니라 **법정동 코드**다
    #       (강원특별자치도=51, 강릉시=51150). regions 테이블 채우기 전엔 호출할 수 없다.
    TOUR_RLTE_API_BASE: str = "http://apis.data.go.kr/B551011/TarRlteTarService1"
    # 이 서비스는 기준연월(baseYm)이 필수. 202312은 0건, 202606까지 데이터 확인됨.
    TOUR_RLTE_BASE_YM: str = "202606"
    # 공사 요구 식별자(모든 요청에 붙는다)
    TOUR_API_APP_NAME: str = "EveryTrip"
    TOUR_API_TIMEOUT: float = 10.0

    @property
    def tour_api_ready(self) -> bool:
        """TourAPI 키가 꽂혀 있는지. 라우터·스크립트에서 사전 확인용."""
        return bool(self.TOUR_API_KEY.strip())


# 앱 어디서나 `from app.core.config import settings` 로 가져다 쓴다.
settings = Settings()
