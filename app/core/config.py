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

    # ── 3단계(인증) — 우리 서버가 발급하는 토큰 ──────────────────────────────
    # SECRET_KEY: JWT 서명 키. 운영에선 반드시 .env로 교체(절대 노출 금지). 기본값은 개발용.
    SECRET_KEY: str = "dev-only-change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "EveryTrip"
    JWT_AUDIENCE: str = "EveryTrip API"
    # access는 짧게. 취소가 불가능한 토큰이라 유출 시 피해창을 좁히는 게 유일한 방어다.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1시간
    # refresh는 길게. DB에 있어서 언제든 취소할 수 있으므로 길어도 안전하다.
    #   → 사용자는 30일간 재로그인 없이 앱을 쓴다(access는 뒤에서 자동 갱신).
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # 운영 프록시가 X-Forwarded-Proto를 올바르게 전달하도록 설정한 뒤 활성화한다.
    # True이면 HTTP 요청을 HTTPS로 307 리다이렉트한다.
    FORCE_HTTPS: bool = False

    # ── 3단계(소셜 로그인 검증) ────────────────────────────────────────────
    # 앱이 카카오/구글 SDK로 받은 토큰을 우리 서버가 **제공자에게 되물어** 검증한다.
    # 따라서 client secret은 필요 없다(서버 OAuth 리다이렉트 방식이 아니므로).
    #
    # GOOGLE_CLIENT_ID: 구글 ID 토큰의 aud(수신 대상)가 우리 앱이 맞는지 검증용.
    #   ⚠️ 비워두면 aud 검증을 건너뛴다. 그러면 **다른 앱용 구글 토큰으로도 우리 서버에
    #      로그인할 수 있다.** 개발 중에만 비워두고, 배포 전엔 반드시 채운다.
    #   여러 플랫폼(안드로이드·iOS·웹)을 쓰면 쉼표로 나열한다.
    GOOGLE_CLIENT_ID: str = ""
    # KAKAO_APP_ID: 카카오 '앱 ID'(숫자). 토큰정보 조회 응답의 `app_id`와 대조한다.
    #   비워두면 마찬가지로 검증을 건너뛴다. 카카오 개발자센터 > 앱 설정 > 요약 정보.
    KAKAO_APP_ID: str = ""
    SOCIAL_API_TIMEOUT: float = 5.0

    # ── 3단계(이메일 인증) ────────────────────────────────────────────────
    # ⚠️ SMTP_HOST가 비어 있으면 메일을 보내지 않고 **서버 로그에 인증코드를 출력**한다.
    #    개발·시연은 이 상태로 가능하다. 실제 발송이 필요할 때만 아래를 채운다.
    #    Gmail 예: SMTP_HOST=smtp.gmail.com / SMTP_PORT=587 / SMTP_USER=내주소@gmail.com
    #              SMTP_PASSWORD=앱비밀번호16자리(계정 비밀번호 아님) / SMTP_STARTTLS=true
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = ""  # 비우면 SMTP_USER를 발신자로 쓴다
    SMTP_FROM_NAME: str = "Every Trip"
    # 인증코드 정책 — 짧은 수명 + 시도 제한이 6자리 코드를 지키는 두 축이다.
    EMAIL_CODE_EXPIRE_MINUTES: int = 3
    EMAIL_CODE_MAX_ATTEMPTS: int = 5
    EMAIL_CODE_RESEND_COOLDOWN_SECONDS: int = 60
    # 코드 확인 후 이 시간 안에 회원가입을 마쳐야 한다(인증만 해두고 방치하는 것 방지).
    EMAIL_VERIFIED_VALID_MINUTES: int = 30

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

    # ② '한국관광공사_관광사진 정보_GW' (data.go.kr/data/15101914) — ✅ 승인·동작 확인
    #    PhotoGalleryService2는 존재하지 않는다(12번 오류). Service**1** + `~1` 오퍼레이션이 맞다.
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

    @property
    def smtp_ready(self) -> bool:
        """SMTP가 설정됐는지. False면 인증코드를 서버 로그로 출력한다(개발 모드)."""
        return bool(self.SMTP_HOST.strip())

    @property
    def google_client_ids(self) -> list[str]:
        """구글 aud 검증에 허용할 client_id 목록. 빈 리스트면 검증을 건너뛴다."""
        return [c.strip() for c in self.GOOGLE_CLIENT_ID.split(",") if c.strip()]


# 앱 어디서나 `from app.core.config import settings` 로 가져다 쓴다.
settings = Settings()
