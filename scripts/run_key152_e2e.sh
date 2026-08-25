#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DB_PASSWORD:-}" ]]; then
  echo "DB_PASSWORD가 필요합니다. 로컬 테스트 DB의 개발용 값만 사용하세요." >&2
  exit 2
fi

uv run pytest -q app/tests/e2e/test_key152_walking_skeleton.py
