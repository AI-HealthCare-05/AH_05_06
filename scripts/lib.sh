#!/bin/bash
# 배포 스크립트들이 함께 쓰는 조각 — **한 곳에만 둔다** (KEY-174).
#
# 예전에는 `sed_inplace` 가 `deployment.sh` 와 `certbot.sh` 에 그대로 복제돼
# 있었다. 한쪽만 고치고 다른 쪽을 놓치기 쉬운 모양이었고, 실제로 **양쪽에
# 같은 버그가 같이 들어 있었다** (이희진 님 `#133` 리뷰).

# 색은 **장식이다.** 장식 때문에 배포가 멈추면 안 된다.
#
# 예전에는 `deployment.sh` 와 `certbot.sh` 가 각각 이렇게 잡았다.
#
#     COLOR_GREEN=$(tput setaf 2)
#
# `TERM` 이 없으면 `tput` 이 실패하고, 두 파일 맨 위의 `set -eo pipefail` 이
# 그것을 잡아 **첫 줄에서 배포가 끝난다.** 2026-09-14 배포가 실제로 그랬다 —
# 파이프로 답을 흘려 넣는 실행에는 `TERM` 이 없다. CI·`cron`·원격 셸도 같다.
#
# 그래서 **되면 쓰고 안 되면 비운다.** 색이 빠져도 글은 그대로 읽힌다.
#
# 네 가지를 본다. `[ -t 1 ]` 이 먼저인 것이 중요하다 — 파일로 흘릴 때 색을
# 넣으면 로그에 `ESC[32m` 이 그대로 박혀 나중에 읽는 사람이 걷어내야 한다.
_supports_color() {
  [ -t 1 ] || return 1                        # 터미널이 아니다
  [ -z "${NO_COLOR:-}" ] || return 1          # 관례 — no-color.org
  command -v tput >/dev/null 2>&1 || return 1 # tput 이 없는 최소 이미지가 있다

  # **아래에서 실제로 부르는 넷을 그대로 재 본다** (`2heej` `#318` 리뷰).
  # 하나만 재면, 그것은 되는데 다른 것이 안 되는 단말에서 `if` 본문이 죽는다 —
  # 본문은 조건 자리가 아니라 `set -e` 가 그대로 잡는다. 고치려던 것과 같은 모양이다.
  tput setaf 2 >/dev/null 2>&1 &&
    tput setaf 4 >/dev/null 2>&1 &&
    tput setaf 1 >/dev/null 2>&1 &&
    tput sgr0 >/dev/null 2>&1
}

# **`if` 안에서 부른다.** `set -e` 는 조건 자리의 실패를 죽음으로 치지 않는다 —
# 맨몸으로 부르면 색을 못 쓰는 자리에서 이 파일이 스크립트를 죽인다.
if _supports_color; then
  COLOR_GREEN=$(tput setaf 2)
  COLOR_BLUE=$(tput setaf 4)
  COLOR_RED=$(tput setaf 1)
  COLOR_NC=$(tput sgr0)
else
  COLOR_GREEN=""
  COLOR_BLUE=""
  COLOR_RED=""
  COLOR_NC=""
fi

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

# **PAT 가 없으면 로그인을 건너뛴다.**
#
# 로컬에서 도커 데스크톱 SSO(구글 로그인)로 들어오면 넘겨 줄 PAT 자체가 없다.
# 그런데 `set -e` 가 위에 있어서, 빈 값으로 `docker login` 을 부르면
# `password is empty` 로 **배포가 여기서 끝난다** (2026-09-03 에 그랬다).
#
# `iljunk/ai-health` 는 **공개 레포**라 아래 `pull` 은 로그인 없이도 된다.
# 레포를 비공개로 돌리는 날 이 자리가 「pull access denied」로 멈추므로,
# 그때는 `DOCKER_PAT` 을 주고 돌려야 한다.
if [ -n "$DOCKER_PAT" ]; then
  echo "Docker login"
  printf '%s' "$DOCKER_PAT" | docker login -u "$DOCKER_USERNAME" --password-stdin
else
  echo "Docker login 건너뜀 — PAT 없음. 공개 레포는 로그인 없이 받는다."
fi

echo "Pulling images: $DEPLOY_SERVICES"
docker compose pull $DEPLOY_SERVICES

# **마이그레이션을 앱보다 먼저 건다** (KEY-206).
#
# 여태 배포 경로에 이 단계가 아예 없었다. 새 이미지를 올려도 DB 는 그대로
# 남아서, KEY-197 을 하다가 Pilot 에서 `guide_section.drug_caution_content_id`
# 가 통째로 없는 것을 발견했다. 사고가 아니라 이 구조의 당연한 결과였다.
#
# 순서가 중요하다. `up -d` **뒤**에 걸면 실패해도 새 코드는 이미 돌고 있어
# 「실패하면 배포가 멈춘다」가 뜻을 잃는다. 멈출 것이 남아 있지 않다.
# 그래서 이미지만 받아 두고, 그 이미지로 한 번 돌리고, 통과하면 그때 바꾼다.
#
# `set -e` 가 위에 있으므로 실패하면 여기서 배포가 끝난다.
if printf '%s\n' $DEPLOY_SERVICES | grep -qx fastapi; then
  echo "Applying migrations"
  # 🚨 **`< /dev/null` 을 빼면 배포가 여기서 조용히 끝난다.**
  #
  # 이 본문 전체가 `bash -s` 의 **stdin** 으로 흘러 들어온다. `docker compose
  # run -T` 는 stdin 을 컨테이너에 그대로 이어 주므로, 막지 않으면 **아직 안
  # 읽은 스크립트 나머지**를 aerich 가 통째로 빨아들인다. 그러면 뒤의
  # `up -d` 와 `image prune` 이 실행되지 않는데, `set -e` 에 걸리지도 않아서
  # (aerich 는 0 으로 끝난다) **성공한 것처럼 보인다.**
  #
  # 2026-09-03 배포가 정확히 이렇게 됐다 — 마이그레이션 16 개가 올라가고
  # `✅ Deployment finished` 가 찍혔는데 **컨테이너는 하나도 안 바뀌었다.**
  # 새 이미지는 받아만 놓고 옛 이미지가 계속 돌았다.
  #
  # 위 `read -r DOCKER_PAT` 주석이 적어 둔 것과 같은 함정이다. 그때는 `read`
  # 였고 이번엔 `docker compose run` 이었다 — **stdin 을 쓰는 것은 전부** 이
  # 자리에서 막아야 한다.
  #
  # 🚩 **`exec < /dev/null` 로 한 번에 닫는 방법은 못 쓴다.** `#202` 리뷰에서
  # 그 편이 구조적으로 안전하다는 제안을 받아 넣어 봤는데, **스크립트 자신이
  # stdin 에 실려 있어서**(`bash -s`) 닫는 순간 뒤가 통째로 안 읽힌다.
  #
  #     printf 'echo A\nexec < /dev/null\necho B\n' | bash -s   # → A 만 나온다
  #     printf 'echo A\ncat < /dev/null\necho B\n'   | bash -s   # → A B 둘 다
  #
  # 그래서 **명령마다** 막는다. 빠뜨리기 쉬운 것이 이 방식의 약점이라,
  # `test_key263_deploy_actually_ships.py` 가 stdin 을 쓰는 명령을 전부 훑어
  # 리다이렉션이 없으면 운다.
  docker compose run --rm -T --no-deps fastapi uv run --no-sync aerich upgrade < /dev/null
fi

echo "Deploying services: $DEPLOY_SERVICES"
docker compose up -d --no-deps $DEPLOY_SERVICES

docker image prune -af
REMOTE
)
EOF
}
