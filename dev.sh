#!/usr/bin/env bash
# 로컬 개발 공통 명령 진입점 — KEY-229
#
#   ./dev.sh start                    서비스 기동 (bootstrap-local.sh 위임)
#   ./dev.sh start --with-ocr-worker  OCR 워커·MinIO 포함 기동
#   ./dev.sh start --rebuild          이미지 재빌드 후 기동
#   ./dev.sh stop                     서비스 중단 (볼륨 유지)
#   ./dev.sh logs [service]           로그 스트림
#   ./dev.sh check                    smoke 검사 (health · auth · core)
#   ./dev.sh check-e2e                종단 검사 (walking skeleton E2E)
#   ./dev.sh reset                    삭제 예정 항목 안내만 (데이터 유지)
#   ./dev.sh reset --confirm-reset    컨테이너·볼륨·설정 파일 삭제

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_ENV="${ROOT}/.bootstrap.local.env"
ENV_FILE="${ROOT}/.env"

say()  { printf '[dev] %s\n' "$*"; }
fail() { printf '[dev][FAIL] %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
사용법: ./dev.sh <명령> [옵션]

  start [--with-ocr-worker] [--rebuild]   서비스 기동 (bootstrap-local.sh 위임)
  stop                                     서비스 중단 (볼륨 유지)
  logs [service]                           로그 스트림 (service 생략 시 전체)
  check                                    smoke 검사 (health · auth · core)
  check-e2e                                종단 검사 (walking skeleton E2E)
  reset [--confirm-reset]                  데이터 삭제 (플래그 없이는 안내만)

경로 구분:
  기본 경로 (OCR 없음)    ./dev.sh start
  OCR 포함 경로           ./dev.sh start --with-ocr-worker
    → ai-worker · minio 추가, check-e2e 에서 OCR 경로까지 검증 가능
USAGE
}

_read_env() {
  local file="$1" key="$2" value
  value="$(grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-)" || true
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'*\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  start)
    exec "${ROOT}/scripts/bootstrap-local.sh" "$@"
    ;;

  stop)
    say "서비스를 중단합니다 (볼륨 유지)."
    cd "$ROOT"
    docker compose --profile web --profile ocr down
    ;;

  logs)
    cd "$ROOT"
    if [[ $# -gt 0 ]]; then
      docker compose logs -f "$@"
    else
      docker compose logs -f
    fi
    ;;

  check)
    cd "$ROOT"
    [[ -f "$BOOTSTRAP_ENV" ]] || \
      fail ".bootstrap.local.env 가 없습니다. ./dev.sh start 를 먼저 실행하세요."
    login_id="$(_read_env "$BOOTSTRAP_ENV" SMOKE_LOGIN_ID)"
    password="$(_read_env  "$BOOTSTRAP_ENV" SMOKE_PASSWORD)"
    [[ -n "$login_id" && -n "$password" ]] || \
      fail ".bootstrap.local.env 에 SMOKE_LOGIN_ID · SMOKE_PASSWORD 가 없습니다."
    say "smoke 검사를 실행합니다 (health · auth · core)."
    SMOKE_LOGIN_ID="$login_id" SMOKE_PASSWORD="$password" \
      docker compose exec -T \
        -e SMOKE_LOGIN_ID \
        -e SMOKE_PASSWORD \
        fastapi uv run --no-sync python scripts/smoke.py http://localhost:8000
    ;;

  check-e2e)
    cd "$ROOT"
    [[ -f "$ENV_FILE" ]] || \
      fail ".env 가 없습니다. ./dev.sh start 를 먼저 실행하세요."
    db_password="$(_read_env "$ENV_FILE" DB_PASSWORD)"
    [[ -n "$db_password" ]] || \
      fail ".env 에 DB_PASSWORD 가 없습니다."
    say "종단 검사를 실행합니다 (walking skeleton E2E — fixture 기반, ai-worker 불필요)."
    DB_PASSWORD="$db_password" uv run pytest -q app/tests/e2e/test_key152_walking_skeleton.py
    ;;

  reset)
    cd "$ROOT"
    confirm=false
    for arg in "$@"; do
      [[ "$arg" == "--confirm-reset" ]] && confirm=true
    done

    if ! $confirm; then
      printf '[dev] --confirm-reset 없이는 아무것도 삭제하지 않습니다.\n\n'
      printf '삭제 예정 항목:\n'
      printf '  컨테이너·네트워크 : docker compose down\n'
      printf '  볼륨               : mysql_data  static_volume  minio_data\n'
      printf '  로컬 파일          : .env  .bootstrap.local.env\n\n'
      printf '실제로 삭제하려면:\n'
      printf '  ./dev.sh reset --confirm-reset\n'
      exit 0
    fi

    say "컨테이너·볼륨·설정 파일을 삭제합니다."
    docker compose --profile web --profile ocr down -v
    rm -f "${ROOT}/.env" "${ROOT}/.bootstrap.local.env"
    say "완료. 다시 시작하려면 ./dev.sh start 를 실행하세요."
    ;;

  ""|--help|-h)
    usage
    exit 0
    ;;

  *)
    printf '[dev] 알 수 없는 명령: %s\n\n' "$cmd" >&2
    usage >&2
    exit 1
    ;;
esac
