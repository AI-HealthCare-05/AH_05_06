#!/usr/bin/env bash
#
# 버킷을 만들고 **익명 접근을 명시적으로 닫는다** — KEY-191.
#
# 첫 판은 「익명 GET 이 403 이더라」를 손으로 한 번 확인하고 문서에 적었다.
# 그런데 버킷이 다른 서버에서 다시 만들어지거나 누가 `mc anonymous set public`
# 을 한 번 돌리면, 이 저장소의 어떤 것도 그걸 못 잡는다 (이희진 님 `#149` ④).
#
# MinIO 기본값이 private 이지만 **기대지 않는다.** 기본값은 판이 바뀌면 같이
# 바뀔 수 있고, 「팀 6인만」은 그런 것에 걸어 둘 약속이 아니다.
#
# 사용법:
#
#   export MC_HOST_team="http://<사용자>:<비밀번호>@<서버>:9000"
#   ./scripts/minio_init.sh            # 별칭 기본값은 team
#   ./scripts/minio_init.sh myalias
#
# **비밀번호를 인자로 주지 않는다** — `ps` 와 셸 기록에 남는다. `MC_HOST_<별칭>`
# 환경변수로 넘긴다 (`deployment.sh` 가 PAT 에 대해 같은 이유로 고쳐졌다,
# KEY-174).
set -euo pipefail

ALIAS="${1:-team}"
BUCKET="${MINIO_BUCKET:-ocr-fixtures}"

MC_HOST_VAR="MC_HOST_${ALIAS}"
if [[ -z "${!MC_HOST_VAR:-}" ]]; then
  echo "MC_HOST_${ALIAS} 가 없다 — 자격증명을 환경변수로 넘겨라 (명령줄에 쓰면 ps 에 남는다)" >&2
  exit 1
fi

echo "버킷 준비: ${ALIAS}/${BUCKET}"
mc mb --ignore-existing "${ALIAS}/${BUCKET}"

# **여기가 요점이다.** 만들 때마다 다시 닫는다 — 멱등이라 몇 번 돌려도 된다.
echo "익명 접근 차단"
mc anonymous set none "${ALIAS}/${BUCKET}"

echo "현재 정책:"
mc anonymous get "${ALIAS}/${BUCKET}"
