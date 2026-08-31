"""인증코드 메일 발송. 어디로 보낼지는 오직 `.env`가 정한다 — 코드는 안 바뀐다.

`SMTP_HOST`가 **비어 있으면 메일을 보내지 않고 서버 로그에 코드를 출력**한다.
덕분에 메일 계정 없이도 회원가입 흐름 전체를 개발·시연할 수 있다.
나중에 `.env`에 아래 4줄만 채우면 코드 수정 없이 실제 발송으로 바뀐다.

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=내주소@gmail.com
    SMTP_PASSWORD=앱비밀번호16자리   ← 구글 계정 비밀번호가 아니다

Gmail·네이버·SendGrid 전환도 이 4줄 교체가 전부다.

⚠️ 동기 `smtplib`을 **스레드로 밀어** 호출한다. FastAPI는 async라, 이벤트 루프에서
   직접 SMTP를 붙잡으면 그동안 서버 전체가 멈춘다(메일 서버는 수 초씩 걸린다).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import anyio

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_message(to: str, code: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[Every Trip] 이메일 인증코드 {code}"
    sender = settings.SMTP_FROM.strip() or settings.SMTP_USER.strip()
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{sender}>"
    msg["To"] = to
    minutes = settings.EMAIL_CODE_EXPIRE_MINUTES
    msg.set_content(
        f"""Every Trip 회원가입 인증코드입니다.

    인증코드: {code}

앱 화면에 위 6자리를 입력해 주세요. {minutes}분 뒤 만료됩니다.
본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.
"""
    )
    return msg


def _send_sync(to: str, code: str) -> None:
    """실제 SMTP 발송. 스레드에서 실행된다."""
    msg = _build_message(to, code)
    if settings.SMTP_STARTTLS:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        # 포트 465(SMTPS)처럼 처음부터 TLS인 경우
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=10,
            context=ssl.create_default_context(),
        ) as smtp:
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)


async def send_verification_code(to: str, code: str) -> bool:
    """인증코드를 보낸다. 실제로 메일을 보냈으면 True, 로그 출력으로 대체했으면 False.

    False가 돌아오면 라우터가 응답에 `dev_code`를 실어 준다(개발 편의).
    """
    if not settings.smtp_ready:
        logger.warning(
            "[개발모드] SMTP 미설정 — 메일을 보내지 않습니다. %s 인증코드: %s", to, code
        )
        return False

    try:
        await anyio.to_thread.run_sync(_send_sync, to, code)
    except Exception:
        # 메일 서버 장애로 500을 던지면 사용자는 원인을 알 수 없다.
        # 코드는 이미 DB에 저장됐으므로, 실패를 로그에 남기고 재발송을 유도한다.
        logger.exception("인증코드 메일 발송 실패: %s", to)
        raise

    logger.info("인증코드 메일 발송 완료: %s", to)
    return True
