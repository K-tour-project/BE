"""GOOGLE_CLIENT_ID(aud) 검증이 실제로 걸리는지 확인한다. **서버를 띄울 필요 없다.**

    .venv/Scripts/python.exe -m scripts.check_google_aud

## 왜 이 검사가 따로 필요한가
소셜 로그인에서 진짜 중요한 검증은 "토큰이 진짜인가"가 아니라 **"우리 앱 토큰인가"**다.
아무 앱에서 발급된 구글 토큰도 '진짜 토큰'이라, 이 관문이 없으면 **남의 앱 사용자가
우리 서버에 로그인할 수 있다.** `.env`의 `GOOGLE_CLIENT_ID`가 그 대조 기준이다.

그런데 `scripts.check_auth`로는 이걸 확인할 수 없다. 거기서 던지는 가짜 토큰은
**구글이 먼저 거부**해서 우리 aud 검사까지 도달하지 못하기 때문이다.
그래서 여기서는 구글 tokeninfo 응답을 흉내 내 `verify_google()`에 직접 먹인다.
실제 구글 토큰 없이도 관문이 동작하는지 볼 수 있다.

⚠️ `GOOGLE_CLIENT_ID`가 비어 있으면 서버가 검증을 건너뛰도록 되어 있으므로(개발 편의),
   이 스크립트는 값이 채워져 있을 때만 의미가 있다. 값이 없으면 안내하고 끝낸다.

※ 8단계에서 pytest를 도입하면 이 파일이 첫 테스트 케이스가 된다.
"""
from __future__ import annotations

import asyncio
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

from fastapi import HTTPException

import app.features.auth.social as social
from app.core.config import settings

if not settings.google_client_ids:
    print(
        "\nGOOGLE_CLIENT_ID가 비어 있습니다.\n"
        ".env에 구글 **웹 애플리케이션** 클라이언트 ID를 넣은 뒤 다시 실행하세요.\n"
        "(비어 있으면 서버가 aud 검증을 건너뜁니다 — 배포 전 필수)"
    )
    sys.exit(1)

OURS = settings.google_client_ids[0]

# 아래 FakeClient가 돌려줄 tokeninfo 응답. 케이스마다 바꿔 끼운다.
PAYLOAD: dict = {}


class _FakeResp:
    status_code = 200

    def json(self) -> dict:
        return PAYLOAD

    @property
    def text(self) -> str:
        return str(PAYLOAD)


class _FakeClient:
    """httpx.AsyncClient 대역 — 네트워크에 나가지 않고 PAYLOAD를 돌려준다."""

    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    async def get(self, *a, **k) -> _FakeResp:
        return _FakeResp()


social.httpx.AsyncClient = _FakeClient  # type: ignore[misc]

# 구글 tokeninfo가 실제로 주는 모양 (값이 전부 문자열인 것에 주의 — "true"지 true가 아니다)
BASE = {
    "iss": "https://accounts.google.com",
    "sub": "1122334455",
    "email": "eunseo@example.com",
    "email_verified": "true",
    "name": "은서",
}

CASES: list[tuple[str, dict, int | None]] = [
    ("우리 앱 토큰 (aud = 우리 웹 클라이언트 ID)", {**BASE, "aud": OURS}, None),
    ("다른 앱 토큰 (aud 불일치)", {**BASE, "aud": "999-other.apps.googleusercontent.com"}, 401),
    ("aud 없음", {**BASE}, 401),
    ("발급자 위조 (iss 변조)", {**BASE, "aud": OURS, "iss": "evil.example.com"}, 401),
    ("사용자 식별자(sub) 없음", {k: v for k, v in BASE.items() if k != "sub"} | {"aud": OURS}, 401),
]


def main() -> int:
    global PAYLOAD
    ok = bad = 0
    print(f"\n검증 기준 GOOGLE_CLIENT_ID = ...{OURS[-36:]}\n")

    for label, payload, expect in CASES:
        PAYLOAD = payload
        try:
            profile = asyncio.run(social.verify_google("dummy"))
            got: int | None = None
            detail = f"{profile.provider_user_id} / {profile.email}"
        except HTTPException as e:
            got, detail = e.status_code, str(e.detail)

        passed = got == expect
        ok, bad = (ok + 1, bad) if passed else (ok, bad + 1)
        print(f"  [{'OK  ' if passed else 'FAIL'}] {label}")
        print(f"          기대={expect or '통과'}  실제={got or '통과'}  → {detail}")

    print(f"\n{'─' * 60}\n통과 {ok} / 실패 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
