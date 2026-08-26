#!/bin/bash
# 배포 스크립트들이 함께 쓰는 조각 — **한 곳에만 둔다** (KEY-174).
#
# 예전에는 `sed_inplace` 가 `deployment.sh` 와 `certbot.sh` 에 그대로 복제돼
# 있었다. 한쪽만 고치고 다른 쪽을 놓치기 쉬운 모양이었고, 실제로 **양쪽에
# 같은 버그가 같이 들어 있었다** (이희진 님 `#133` 리뷰).

# `sed -i` 는 GNU 와 BSD(macOS)가 인자를 다르게 받는다. GNU 는 `-i` 뒤에 바로
# 스크립트가 오고, BSD 는 **백업 확장자를 반드시 요구**해서 빈 문자열을 끼워
# 넣어야 한다.
sed_inplace() {
  if sed --version >/dev/null 2>&1; then
    sed -i "$@"        # GNU
  else
    sed -i '' "$@"     # BSD / macOS
  fi
}

# 원격에서 돌릴 배포 스크립트를 **통째로 만들어 stdout 으로 낸다.** $1 은 PAT.
#
# **PAT 는 ssh 명령줄에 싣지 않는다** — 원격의 `ps` 에 그대로 남는다. 그래서
# 스크립트를 stdin 으로 흘려보내는데, 예전 판은 PAT 를 **스크립트보다 먼저**
# 한 줄로 얹었다. `bash -s` 는 stdin 을 스크립트로 읽으므로:
#
#     1. 첫 줄(PAT)을 명령으로 실행하려다 실패한다
#        → `bash: line 1: <PAT>: command not found` 로 **stderr 에 그대로 샌다**
#     2. 뒤이은 `read -r DOCKER_PAT` 이 PAT 가 아니라 **다음 스크립트 줄**을
#        삼킨다 (`cd project`)
#     3. 틀린 값으로 `docker login` → 실패 → `set -e` 에 걸려 `compose up` 은
#        아예 안 돈다. **이 경로로는 배포가 100% 실패한다**
#
# 막으려던 노출을 오히려 만들고 있었다 (이희진 님 `#133` 리뷰에서 재현 확인).
#
# 그래서 PAT 를 **스크립트 본문 안의 heredoc** 으로 넘긴다. `read` 가 스크립트
# stdin 과 겹치지 않고, 본문은 여전히 stdin 으로만 가므로 `ps` 에도 안 남는다.
remote_deploy_payload() {
  local pat="$1"
  cat <<EOF
set -e
read -r DOCKER_PAT <<'DOCKER_PAT_EOF'
${pat}
DOCKER_PAT_EOF

$(cat <<'REMOTE'
cd project

echo "Docker login"
printf '%s' "$DOCKER_PAT" | docker login -u "$DOCKER_USERNAME" --password-stdin

echo "Deploying services: $DEPLOY_SERVICES"
docker compose up -d --pull always --no-deps $DEPLOY_SERVICES

docker image prune -af
REMOTE
)
EOF
}
