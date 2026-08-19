# 로컬 환경 기동·헬스체크 점검 절차

> KEY-19 산출물 — 로컬 개발환경에서 API·DB·Redis 기동 상태를 한 명령으로 확인하는 절차

## 1. 빠른 확인 (한 명령)

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

**정상 응답 (HTTP 200)**

```json
{
  "status": "ok",
  "services": {
    "api":   { "status": "ok" },
    "db":    { "status": "ok" },
    "redis": { "status": "ok" }
  }
}
```

**장애 응답 (HTTP 503)**

```json
{
  "status": "degraded",
  "services": {
    "api":   { "status": "ok" },
    "db":    { "status": "error", "error": "..." },
    "redis": { "status": "ok" }
  }
}
```

## 2. 환경 기동 순서

```bash
# 1. .env 파일 확인 (envs/example.local.env 참고)
cp envs/example.local.env .env   # 최초 1회만

# 2. 컨테이너 기동 (MySQL healthcheck 통과 후 FastAPI 자동 기동)
docker compose up -d

# 3. 헬스체크 확인
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

## 3. 서비스별 실패 원인과 조치

### api — status: error
API 서버 자체가 응답 불가. 헬스체크 엔드포인트가 이 상태를 반환하면 FastAPI 프로세스가 올바로 기동된 것이므로 실제로 이 값이 "error"가 되는 경우는 없다. `curl`이 연결 자체를 실패하면 아래를 확인한다.

```bash
docker compose logs fastapi --tail 50
docker compose ps
```

### db — status: error

| 원인 | 확인 명령 | 조치 |
|------|-----------|------|
| MySQL 컨테이너 미기동 | `docker compose ps mysql` | `docker compose up -d mysql` |
| 헬스체크 통과 전 | `docker compose logs mysql --tail 20` | 10~30초 대기 후 재시도 |
| `.env` DB 설정 불일치 | `.env`의 `DB_*` 값 확인 | `envs/example.local.env` 참고 |
| 포트 충돌 | `lsof -i :3306` | 로컬 MySQL 프로세스 중지 |

```bash
# DB 직접 연결 확인
docker exec -it mysql mysqladmin ping -h localhost -u root -p
```

### redis — status: error

| 원인 | 확인 명령 | 조치 |
|------|-----------|------|
| Redis 컨테이너 미기동 | `docker compose ps redis` | `docker compose up -d redis` |
| 포트 충돌 | `lsof -i :6379` | 로컬 Redis 프로세스 중지 |
| `.env` REDIS_HOST 불일치 | `.env`의 `REDIS_HOST`, `REDIS_PORT` 확인 | 도커 환경은 `redis`, 로컬 직접 실행은 `localhost` |

```bash
# Redis 직접 연결 확인
docker exec -it redis redis-cli ping
# 응답: PONG
```

## 4. 스모크 테스트 실행 (재현 가능 확인)

```bash
# mock 기반 — MySQL·Redis 없이 항상 실행 가능
uv run pytest app/tests/test_smoke.py -v
```

정상 출력 예시:

```
PASSED app/tests/test_smoke.py::test_health_all_ok
PASSED app/tests/test_smoke.py::test_health_db_down
PASSED app/tests/test_smoke.py::test_health_redis_down
PASSED app/tests/test_smoke.py::test_health_response_structure
```

## 5. 전체 초기화가 필요할 때

```bash
docker compose down -v          # 컨테이너 + 볼륨 삭제
docker compose up -d            # 재기동
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```
