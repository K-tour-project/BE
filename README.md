# K-tour BE

영화·드라마 촬영지 관광 앱의 FastAPI 백엔드. PostgreSQL/PostGIS를 사용한다.

## 로컬 실행

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`.env`의 개발용 설정을 확인한 뒤 실행한다. 기본 접속 주소는
`http://127.0.0.1:8000`이며 `/health`는 프로세스 상태만 반환한다.
API 문서는 `/docs`에서 확인할 수 있다.

## 초기 데이터

```powershell
.venv\Scripts\python.exe -m scripts.seed_regions
.venv\Scripts\python.exe -m scripts.seed_places_products
```

CSV 형식과 재실행 동작은 [data/IMPORT.md](data/IMPORT.md)를 참고한다.

## 검사

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

## 주요 경로

- `app/`: API, 설정, DB 모델과 외부 연동
- `alembic/`: DB 스키마 변경 이력
- `scripts/`: 데이터 적재와 수동 점검 도구
- `data/`: 초기 적재용 CSV
- `tests/`: 자동 검사
- [API_CONTRACT.md](API_CONTRACT.md): API 계약
- `docs/`: 기능별 API 설명
- [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md): 과거 구현 기록

`docker-compose.yml`은 로컬 PostGIS DB만 실행한다. 운영 환경에서는
`.env`의 개발용 비밀값과 DB 주소를 그대로 사용하지 않는다.
