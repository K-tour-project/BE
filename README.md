# K-tour BE

영화·드라마 촬영지 관광 코스 앱 백엔드 (FastAPI + PostgreSQL/PostGIS).

## 실행 (1단계: 서버 띄우기)

```bash
# 1) 가상환경 생성 & 활성화
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell)
# source .venv/bin/activate     # macOS / Linux

# 2) 패키지 설치
pip install -r requirements.txt

# 3) 서버 실행
uvicorn app.main:app --reload
```

- 헬스체크: http://127.0.0.1:8000/health → `{"status":"ok"}`
- 자동 API 문서: http://127.0.0.1:8000/docs

## 폴더 구조

```
app/
  main.py        # 앱 진입점 (uvicorn이 띄우는 대상)
  core/          # 설정·보안·DB연결 등 기반 (config.py)
  routers/       # URL 경로 정의 (창구)   — health.py
  services/      # 비즈니스 로직 (주방)    — 다음 단계
  models/        # DB 테이블 (SQLAlchemy)  — 2단계
  schemas/       # 요청/응답 데이터 모양 (Pydantic)
  deps/          # 공통 의존성 (인증·DB세션)
alembic/         # DB 마이그레이션          — 2단계
docker-compose.yml  # 로컬 PostgreSQL+PostGIS — 2단계
.env / .env.example # 환경설정·비밀값
```

## 개발 단계
1. ✅ 뼈대 + `/health` (서버 구동)
2. DB 연결 + Alembic 마이그레이션 (테이블 생성)
3. 회원가입/로그인 (JWT 인증)
4. `place-detail` (KTO TourAPI 실시간 연동)
