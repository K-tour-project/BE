"""auth — 회원가입 · 로그인 · 로그아웃 · 소셜 로그인 · 이메일 인증.

기능 하나 = 폴더 하나 규칙(PROJECT_STRUCTURE.md)에 따라 인증 관련 코드를 여기 모았다.

```
router.py   엔드포인트 정의(얇게) — 검증·분기는 service로 넘긴다
service.py  가입/로그인 판단, 토큰 발급·회전·폐기 등 실제 로직
schema.py   요청·응답 모양 (= API_CONTRACT.md §2를 코드로 옮긴 것)
social.py   구글·카카오에 "이 토큰 주인 누구야?"를 물어보는 어댑터
mailer.py   인증코드 메일 발송(SMTP 미설정이면 서버 로그로 출력)
```

암호 기술 자체(JWT 서명·bcrypt·해시)는 `app/core/security.py`에 있다.
여기(features/auth)는 그걸 **언제 어떻게 쓸지 판단**하는 층이다.
"""
