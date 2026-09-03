"""인증 엔드포인트 9종을 실제로 호출해 검증한다.

    # 1) 서버를 먼저 띄운다
    .venv/Scripts/python.exe -m uvicorn app.main:app --reload
    # 2) 다른 터미널에서
    .venv/Scripts/python.exe -m scripts.check_auth

무엇을 확인하나 — 성공 경로뿐 아니라 **막혀야 할 것이 막히는지**를 같이 본다.
    ① 이메일 인증 → 회원가입 → 로그인
    ② 잘못된 비밀번호·중복 가입·인증 없이 가입 시도가 각각 401/409/403으로 거부되는지
    ③ access 토큰으로 /auth/me 통과, 토큰 없이는 401
    ④ refresh 회전 — 새 토큰이 나오고 **옛 refresh는 죽는지**
    ⑤ 재사용 감지 — 죽은 refresh를 다시 쓰면 그 계정의 모든 세션이 끊기는지
    ⑥ 로그아웃 → 그 refresh로 재발급 불가

소셜 로그인(구글)은 실제 제공자 토큰이 있어야 해서 여기선 **위조 토큰이 401로
거부되는 것까지만** 확인한다. 정상 경로는 앱 연동 후 수동 확인이 필요하다.
**카카오는 팀 분담상 윤영이 맡아 아직 미구현**이라 케이스가 빠져 있다(구현되면 주석 해제).
"""
from __future__ import annotations

import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"

# Windows 콘솔 기본 인코딩(cp949)에선 한글 일부·기호가 깨진다. UTF-8로 강제한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label}{('  → ' + detail) if detail else ''}")
    (PASSED if ok else FAILED).append(label)
    return ok


def main() -> int:
    # 실행할 때마다 새 이메일 — 재발송 쿨다운(60초)과 중복 가입을 피하려고.
    email = f"check-{uuid.uuid4().hex[:10]}@example.com"
    password = "ktour1234"
    nickname = "테스트유저"

    with httpx.Client(base_url=BASE, timeout=10.0) as c:
        print(f"\n대상 서버: {BASE}   테스트 계정: {email}\n")

        # ── ① 이메일 인증 ────────────────────────────────────────────────
        print("① 이메일 인증")
        r = c.post("/auth/email/send-code", json={"email": email})
        check("인증코드 발송 200", r.status_code == 200, f"{r.status_code}")
        if r.status_code != 200:
            print("\n서버가 안 떠 있거나 DB 연결이 안 됩니다. 먼저 uvicorn을 실행하세요.")
            return 1
        code = r.json().get("dev_code")
        check(
            "SMTP 미설정이라 dev_code가 응답에 담김",
            bool(code),
            "SMTP를 설정했다면 dev_code=null이 정상 — 메일함을 확인하세요",
        )
        if not code:
            return 1

        r = c.post("/auth/email/send-code", json={"email": email})
        check("60초 내 재발송은 429로 차단", r.status_code == 429, f"{r.status_code}")

        r = c.post("/auth/email/verify-code", json={"email": email, "code": "000000"})
        check("틀린 코드는 400", r.status_code == 400, f"{r.status_code}")

        r = c.post(
            "/auth/signup",
            json={"email": email, "password": password, "nickname": nickname},
        )
        check("인증 전 회원가입은 403", r.status_code == 403, f"{r.status_code}")

        r = c.post("/auth/email/verify-code", json={"email": email, "code": code})
        check("올바른 코드로 인증 200", r.status_code == 200, f"{r.status_code}")

        # ── ② 회원가입 ──────────────────────────────────────────────────
        print("\n② 회원가입")
        r = c.post(
            "/auth/signup",
            json={"email": email, "password": "short1", "nickname": nickname},
        )
        check("8자 미만 비밀번호는 422", r.status_code == 422, f"{r.status_code}")

        r = c.post(
            "/auth/signup",
            json={"email": email, "password": "abcdefghij", "nickname": nickname},
        )
        check("숫자 없는 비밀번호는 422", r.status_code == 422, f"{r.status_code}")

        r = c.post(
            "/auth/signup",
            json={"email": email, "password": password, "nickname": nickname},
        )
        check("회원가입 201", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        if r.status_code != 201:
            return 1
        signed = r.json()
        check(
            "가입 응답에 토큰 없음 + 사용자 정보",
            not {"access_token", "refresh_token", "expires_in"} & signed.keys()
            and {"message", "user"} <= signed.keys(),
        )
        check(
            "비밀번호 해시가 응답에 새지 않음",
            "password" not in r.text and "hash" not in r.text,
        )
        check(
            "auth_provider=local, email_verified=true",
            signed["user"]["auth_provider"] == "local"
            and signed["user"]["email_verified"] is True,
            str(signed["user"]),
        )

        # ── ③ 로그인 ───────────────────────────────────────────────────
        print("\n③ 로그인")
        r = c.post("/auth/signup", json={"email": email, "password": password, "nickname": nickname})
        check("같은 이메일 재가입은 409", r.status_code == 409, f"{r.status_code}")

        r = c.post("/auth/login", json={"email": email, "password": "wrongpass1"})
        check("틀린 비밀번호는 401", r.status_code == 401, f"{r.status_code}")
        check(
            "실패 메시지가 이메일/비번을 구분하지 않음",
            "이메일 또는 비밀번호" in r.text,
            r.json().get("detail", ""),
        )

        r = c.post("/auth/login", json={"email": "nobody-here@example.com", "password": password})
        check("없는 계정도 같은 401 문구", r.status_code == 401 and "이메일 또는 비밀번호" in r.text)

        r = c.post("/auth/login", json={"email": email.upper(), "password": password})
        check("이메일 대소문자를 구분하지 않음", r.status_code == 200, f"{r.status_code}")
        if r.status_code != 200:
            return 1
        tokens = r.json()
        check(
            "로그인 응답에 두 토큰 + 사용자 정보",
            {"access_token", "refresh_token", "expires_in", "user"} <= tokens.keys(),
        )
        access, refresh = tokens["access_token"], tokens["refresh_token"]
        check("access 수명이 1시간(3600초)", tokens["expires_in"] == 3600, str(tokens["expires_in"]))

        # ── ④ 보호된 API ────────────────────────────────────────────────
        print("\n④ 인증이 필요한 API")
        r = c.get("/auth/me")
        check("토큰 없이 /auth/me는 401", r.status_code == 401, f"{r.status_code}")

        r = c.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        check("위조 토큰은 401", r.status_code == 401, f"{r.status_code}")

        r = c.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
        check("정상 토큰으로 /auth/me 200", r.status_code == 200, f"{r.status_code}")
        check("내 정보가 가입한 계정과 일치", r.json().get("email") == email, r.text[:120])

        r = c.get("/auth/me", headers={"Authorization": f"Bearer {refresh}"})
        check(
            "refresh 토큰을 출입증으로 쓰면 401 (토큰 혼동 차단)",
            r.status_code == 401,
            f"{r.status_code}",
        )

        # ── ⑤ 토큰 회전 ─────────────────────────────────────────────────
        print("\n⑤ refresh 회전")
        time.sleep(1.1)  # iat/exp가 초 단위라 새 access가 문자열까지 달라지도록
        r = c.post("/auth/refresh", json={"refresh_token": refresh})
        check("refresh로 재발급 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        if r.status_code != 200:
            return 1
        rotated = r.json()
        new_access, new_refresh = rotated["access_token"], rotated["refresh_token"]
        check("새 refresh가 발급됨(회전)", new_refresh != refresh)
        check("새 access가 발급됨", new_access != access)

        r = c.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        check("새 access로 /auth/me 200", r.status_code == 200, f"{r.status_code}")

        # ── ⑥ 재사용 감지 ───────────────────────────────────────────────
        print("\n⑥ 재사용 감지 (탈취 방어)")
        r = c.post("/auth/refresh", json={"refresh_token": refresh})
        check("이미 쓴 refresh 재사용은 401", r.status_code == 401, f"{r.status_code}")
        check("모든 기기 로그아웃 안내", "모든 기기" in r.text, r.json().get("detail", ""))

        r = c.post("/auth/refresh", json={"refresh_token": new_refresh})
        check(
            "재사용 감지로 살아있던 refresh까지 폐기됨",
            r.status_code == 401,
            f"{r.status_code}",
        )

        # ── ⑦ 로그아웃 ─────────────────────────────────────────────────
        print("\n⑦ 로그아웃")
        r = c.post("/auth/login", json={"email": email, "password": password})
        check("재로그인 200", r.status_code == 200, f"{r.status_code}")
        t = r.json()

        r = c.post("/auth/logout", json={"refresh_token": t["refresh_token"]})
        check("로그아웃 200", r.status_code == 200, f"{r.status_code}")

        r = c.post("/auth/refresh", json={"refresh_token": t["refresh_token"]})
        check("로그아웃한 refresh로 재발급 불가 401", r.status_code == 401, f"{r.status_code}")

        r = c.post("/auth/logout", json={"refresh_token": t["refresh_token"]})
        check("로그아웃 재호출도 200 (멱등)", r.status_code == 200, f"{r.status_code}")

        # 두 기기에서 로그인한 뒤 전체 로그아웃
        a = c.post("/auth/login", json={"email": email, "password": password}).json()
        b = c.post("/auth/login", json={"email": email, "password": password}).json()
        r = c.post("/auth/logout-all", headers={"Authorization": f"Bearer {a['access_token']}"})
        check("logout-all 200", r.status_code == 200, r.text[:80])
        r1 = c.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
        r2 = c.post("/auth/refresh", json={"refresh_token": b["refresh_token"]})
        check(
            "두 기기 refresh가 모두 죽음",
            r1.status_code == 401 and r2.status_code == 401,
            f"{r1.status_code}/{r2.status_code}",
        )

        # ── ⑧ 소셜 (위조 토큰 거부만) ────────────────────────────────────
        print("\n⑧ 소셜 로그인 (위조 토큰 거부 확인)")
        r = c.post("/auth/google", json={"id_token": "fake.token.value"})
        check("가짜 구글 토큰은 401", r.status_code == 401, f"{r.status_code} {r.text[:80]}")
        # 카카오는 윤영 담당으로 아직 엔드포인트가 없다. 구현되면 아래 두 줄을 살린다.
        # r = c.post("/auth/kakao", json={"access_token": "fake-kakao-token"})
        # check("가짜 카카오 토큰은 401", r.status_code == 401, f"{r.status_code} {r.text[:80]}")

    print(f"\n{'─' * 60}")
    print(f"통과 {len(PASSED)} / 실패 {len(FAILED)}")
    if FAILED:
        for f in FAILED:
            print(f"  ✗ {f}")
        return 1
    print("전부 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
