#!/usr/bin/env bash
# 한 명령으로 로컬 DB·Redis·FastAPI를 재현한다 — KEY-228.
#
#   ./scripts/bootstrap-local.sh
#   ./scripts/bootstrap-local.sh --with-ocr-worker
#   ./scripts/bootstrap-local.sh --rebuild
#
# 기존 .env와 볼륨은 절대 지우거나 덮어쓰지 않는다. 생성한 비밀값은 Git이
# 무시하는 로컬 파일에만 두고 stdout/stderr에는 출력하지 않는다.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
BOOTSTRAP_ENV="${ROOT}/.bootstrap.local.env"
WITH_OCR=false
REBUILD=false
STAGE="사전 검사"
TIMEOUT_SECONDS="${BOOTSTRAP_TIMEOUT_SECONDS:-180}"

say() {
  printf '[bootstrap] %s\n' "$*"
}

fail() {
  printf '[bootstrap][FAIL] %s — %s\n' "$STAGE" "$1" >&2
  exit 1
}

on_error() {
  local code=$?
  printf '[bootstrap][FAIL] %s 단계가 종료 코드 %s로 멈췄습니다. 위 오류를 해결한 뒤 같은 명령을 다시 실행하세요.\n' \
    "$STAGE" "$code" >&2
  exit "$code"
}
trap on_error ERR

usage() {
  printf '사용법: %s [--with-ocr-worker] [--rebuild]\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-ocr-worker) WITH_OCR=true ;;
    --rebuild) REBUILD=true ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "지원하지 않는 옵션입니다: ${1}"
      ;;
  esac
  shift
done
[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "BOOTSTRAP_TIMEOUT_SECONDS는 1 이상의 정수여야 합니다."

cd "$ROOT"

for command_name in docker curl openssl python3; do
  command -v "$command_name" >/dev/null 2>&1 || fail "${command_name} 명령이 없습니다. 설치 후 다시 실행하세요."
done
docker info >/dev/null 2>&1 || fail "Docker가 실행 중이 아닙니다. Docker Desktop을 연 뒤 다시 실행하세요."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2를 사용할 수 없습니다. Docker Desktop을 업데이트하세요."

random_hex() {
  openssl rand -hex "$1"
}

env_value() {
  local file="$1" key="$2" line value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#export }"
    if [[ "$line" == "${key}="* ]]; then
      value="${line#*=}"
      value="${value%$'\r'}"
      if [[ "$value" == \"*\" && "$value" == *\" ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
        value="${value:1:${#value}-2}"
      fi
      printf '%s' "$value"
      return 0
    fi
  done < "$file"
  return 1
}

set_env_value() {
  local file="$1" key="$2" value="$3" line found=false tmp
  tmp="${file}.tmp.$$"
  : > "$tmp"
  chmod 600 "$tmp"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "${key}="* ]]; then
      printf '%s=%s\n' "$key" "$value" >> "$tmp"
      found=true
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$file"
  $found || printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$file"
  chmod 600 "$file"
}

placeholder_or_blank() {
  local value="${1:-}"
  [[ -z "$value" || "$value" =~ ^(your[-_]|change[-_]?me|\<|xxx+|\.\.\.|example) ]]
}

STAGE="로컬 환경파일"
if [[ -e "$ENV_FILE" ]]; then
  say "기존 .env를 그대로 사용합니다."
else
  cp envs/example.local.env "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  set_env_value "$ENV_FILE" SECRET_KEY "$(random_hex 32)"
  set_env_value "$ENV_FILE" DB_PASSWORD "$(random_hex 24)"
  set_env_value "$ENV_FILE" DB_ROOT_PASSWORD "$(random_hex 24)"
  set_env_value "$ENV_FILE" MINIO_ROOT_USER "minio$(random_hex 6)"
  set_env_value "$ENV_FILE" MINIO_ROOT_PASSWORD "$(random_hex 24)"
  set_env_value "$ENV_FILE" WEB_VERSION "v1.0.0"
  set_env_value "$ENV_FILE" REDIS_EXPOSE_PORT "6379"
  set_env_value "$ENV_FILE" MINIO_API_PORT "9000"
  set_env_value "$ENV_FILE" MINIO_CONSOLE_PORT "9001"
  set_env_value "$ENV_FILE" UPLOAD_DIR "/tmp/medical_uploads"
  set_env_value "$ENV_FILE" MAX_UPLOAD_SIZE_MB "20"
  set_env_value "$ENV_FILE" OCR_FIXTURE_FALLBACK "false"
  say ".env를 생성했습니다(비밀값은 표시하지 않음)."
fi

for key in SECRET_KEY DB_PASSWORD DB_ROOT_PASSWORD; do
  value="$(env_value "$ENV_FILE" "$key" || true)"
  placeholder_or_blank "$value" && fail ".env의 ${key}가 비었거나 예시값입니다. 실제 로컬 전용 값으로 바꾸세요."
done
env_name="$(env_value "$ENV_FILE" ENV || true)"
[[ "$env_name" == "local" ]] || fail "bootstrap은 ENV=local에서만 실행할 수 있습니다."

if $WITH_OCR; then
  for key in MINIO_ROOT_USER MINIO_ROOT_PASSWORD; do
    value="$(env_value "$ENV_FILE" "$key" || true)"
    placeholder_or_blank "$value" && fail "--with-ocr-worker에는 .env의 ${key}가 필요합니다."
  done
fi

if [[ ! -e "$BOOTSTRAP_ENV" ]]; then
  umask 077
  seed_password="$(random_hex 18)"
  {
    printf 'SEED_STAFF_PASSWORD=%s\n' "$seed_password"
    printf 'SMOKE_LOGIN_ID=staff01\n'
    printf 'SMOKE_PASSWORD=%s\n' "$seed_password"
  } > "$BOOTSTRAP_ENV"
  chmod 600 "$BOOTSTRAP_ENV"
  say "합성 계정용 로컬 설정을 생성했습니다(비밀값은 표시하지 않음)."
else
  say "기존 합성 계정용 로컬 설정을 그대로 사용합니다."
fi

SEED_STAFF_PASSWORD="$(env_value "$BOOTSTRAP_ENV" SEED_STAFF_PASSWORD || true)"
SMOKE_LOGIN_ID="$(env_value "$BOOTSTRAP_ENV" SMOKE_LOGIN_ID || true)"
SMOKE_PASSWORD="$(env_value "$BOOTSTRAP_ENV" SMOKE_PASSWORD || true)"
[[ -n "$SEED_STAFF_PASSWORD" && -n "$SMOKE_LOGIN_ID" && -n "$SMOKE_PASSWORD" ]] || \
  fail ".bootstrap.local.env의 합성 계정 설정이 불완전합니다."

STAGE="compose 설정 검증"
docker compose config --quiet >/dev/null

service_is_running() {
  [[ -n "$(docker compose ps --status running -q "$1" 2>/dev/null)" ]]
}

port_is_free() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
addresses = ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::"))
for family, address in addresses:
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        continue
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((address, port))
    except OSError:
        raise SystemExit(1)
    finally:
        sock.close()
PY
}

check_port() {
  local service="$1" port="$2"
  service_is_running "$service" && return 0
  port_is_free "$port" || fail "포트 ${port}가 이미 사용 중입니다. 해당 프로그램을 종료하거나 .env의 노출 포트를 바꾸세요."
}

STAGE="포트 검사"
db_port="$(env_value "$ENV_FILE" DB_EXPOSE_PORT || true)"
redis_port="$(env_value "$ENV_FILE" REDIS_EXPOSE_PORT || true)"
check_port mysql "${db_port:-3306}"
check_port redis "${redis_port:-6379}"
check_port fastapi 8000

wait_healthy() {
  local service="$1" start now id health
  start="$(date +%s)"
  while true; do
    id="$(docker compose ps -q "$service" 2>/dev/null)"
    if [[ -n "$id" ]]; then
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")"
      [[ "$health" == "healthy" || "$health" == "running" ]] && return 0
      [[ "$health" == "unhealthy" || "$health" == "exited" ]] && \
        fail "${service}가 ${health} 상태입니다. docker compose logs ${service}로 확인하세요."
    fi
    now="$(date +%s)"
    (( now - start < TIMEOUT_SECONDS )) || fail "${service} 준비가 ${TIMEOUT_SECONDS}초를 넘겼습니다. docker compose logs ${service}로 확인하세요."
    sleep 2
  done
}

wait_http() {
  local url="$1" start now
  start="$(date +%s)"
  while ! curl -fsS --max-time 3 "$url" >/dev/null 2>&1; do
    now="$(date +%s)"
    (( now - start < TIMEOUT_SECONDS )) || fail "FastAPI 응답 대기가 ${TIMEOUT_SECONDS}초를 넘겼습니다. docker compose logs fastapi로 확인하세요."
    sleep 2
  done
}

compose=(docker compose)
services=(redis mysql fastapi)
if $WITH_OCR; then
  compose+=(--profile ocr)
  services+=(ai-worker minio)
fi

STAGE="컨테이너 기동"
say "${services[*]}를 기동합니다."
up_args=(up -d)
if $REBUILD; then
  up_args+=(--build)
  say "--rebuild 요청에 따라 이미지를 다시 빌드합니다."
fi
"${compose[@]}" "${up_args[@]}" "${services[@]}"

STAGE="의존 서비스 health"
wait_healthy mysql
wait_healthy redis
$WITH_OCR && wait_healthy minio

STAGE="FastAPI HTTP 대기"
wait_http "http://localhost:8000/api/v1/health"

STAGE="migration"
say "컨테이너 안에서 migration을 적용합니다."
run_migration() {
  local output code
  if output="$(docker compose exec -T fastapi uv run --no-sync aerich upgrade 2>&1)"; then
    [[ -z "$output" ]] || printf '%s\n' "$output"
    return 0
  else
    code=$?
  fi

  [[ -z "$output" ]] || printf '%s\n' "$output" >&2
  if [[ "$output" == *"Access denied for user"* ]]; then
    printf '%s\n' \
      '[bootstrap][HELP] 기존 mysql_data 볼륨의 비밀번호가 현재 .env와 다를 수 있습니다.' \
      '[bootstrap][HELP] 로컬 DB 데이터 삭제가 괜찮을 때만 직접 `docker compose down -v` 후 다시 실행하세요.' \
      '[bootstrap][HELP] 위 명령은 mysql_data 등 로컬 볼륨을 삭제하므로 필요한 데이터는 먼저 백업하세요.' >&2
  fi
  return "$code"
}
run_migration

if $WITH_OCR; then
  STAGE="MinIO 초기화"
  say "MinIO 버킷을 준비하고 익명 접근을 차단합니다."
  "${compose[@]}" run --rm -T --no-deps minio-init
fi

STAGE="합성 seed"
say "합성 직원 seed를 적용합니다."
SEED_STAFF_PASSWORD="$SEED_STAFF_PASSWORD" docker compose exec -T -e SEED_STAFF_PASSWORD fastapi \
  uv run --no-sync python scripts/seed.py --mode staff

STAGE="schema drift"
docker compose exec -T fastapi uv run --no-sync python scripts/check_schema_drift.py

STAGE="smoke"
SMOKE_LOGIN_ID="$SMOKE_LOGIN_ID" SMOKE_PASSWORD="$SMOKE_PASSWORD" docker compose exec -T \
  -e SMOKE_LOGIN_ID \
  -e SMOKE_PASSWORD \
  fastapi uv run --no-sync python scripts/smoke.py http://localhost:8000

STAGE="완료"
say "완료 — health·auth·core가 모두 통과했습니다."
