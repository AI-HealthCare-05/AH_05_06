#!/bin/bash
set -eo pipefail

# 공용 조각은 `scripts/lib.sh` 한 곳에 둔다 — 복제해 두면 한쪽만 고치게 된다
# (KEY-174).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

COLOR_GREEN=$(tput setaf 2)
COLOR_BLUE=$(tput setaf 4)
COLOR_RED=$(tput setaf 1)
COLOR_NC=$(tput sgr0)

cd "$(dirname "$0")/.."
source ./envs/.prod.env

# ---------- 도커 이미지 빌드 및 푸시 함수 ----------
build_and_push () {
  local docker_user=$1
  local docker_repo=$2
  local name=$3
  local tag=$4
  local dockerfile=$5
  local context=$6
  # **태그 앞머리를 인자로 받는다** — 예전에는 「FastAPI 아니면 ai」였다.
  # 세 번째가 생기는 순간 nginx 이미지가 `ai-` 로 밀려 올라간다 (KEY-189).
  local tag_base=$7
  # 빠뜨리면 **조용히 `:-v1.0.0` 이 올라간다** — 태그 앞머리가 빈 문자열이 되고
  # 아무도 안 운다 (이희진 님 `#145` ②). 이 PR 이 고치려던 실수가 한 칸 옆으로
  # 옮겨간 자리라 여기서 죽인다.
  : "${tag_base:?build_and_push: tag_base(7번째 인자)가 없다 — api|ai|web 중 하나를 넘겨라}"
  echo "${COLOR_BLUE}${name} Docker Image Build Start.${COLOR_NC}"
  docker build --platform linux/amd64 -t ${docker_user}/${docker_repo}:${tag_base}-${tag} -f ${dockerfile} ${context}

  echo "${COLOR_BLUE}${name} Docker Image Push Start.${COLOR_NC}"
  docker push ${docker_user}/${docker_repo}:${tag_base}-${tag}

  echo "${COLOR_GREEN}${name} Done.${COLOR_NC}"
  echo ""
}

# ---------- Docker login ----------
#
# **이미 로그인돼 있으면 묻지 않는다.**
#
# 도커 데스크톱에 구글(SSO)로 들어온 계정에는 **CLI 에 넣을 비밀번호가 없다.**
# 이 자리가 받는 것은 비밀번호가 아니라 PAT 인데, 그것을 모르면 「없는 값」을
# 찾다가 빈 입력으로 `password is empty` 를 맞는다. 2026-09-03 배포가 여기서
# 두 번 막혔다.
#
# 로그인이 이미 돼 있으면 `docker push` 는 키체인의 토큰으로 그냥 된다 —
# 다시 로그인시킬 이유가 없다. 그래서 **저장된 자격증명을 먼저 본다.**
# 사용자명은 거기서 읽는다(뒤의 이미지 이름이 이 값을 쓴다). 비밀값은
# 읽지도 찍지도 않는다 — `sed` 가 `Username` 만 집어 나머지는 흘려보낸다.
docker_user=""
# 원격에 넘길 PAT. 로그인을 건너뛰면 빈 값으로 남고, 그때는 원격도 건너뛴다.
docker_pw=""

#: 도커허브 레지스트리 키. `config.json` 이 이 이름으로 적는다.
DOCKER_REGISTRY='https://index.docker.io/v1/'

# base64 해독 — GNU 는 `--decode`/`-d`, BSD 는 `-D` 를 쓴다.
b64_decode () {
  printf '%s' "$1" | base64 --decode 2>/dev/null \
    || printf '%s' "$1" | base64 -d 2>/dev/null \
    || printf '%s' "$1" | base64 -D 2>/dev/null
}

# 저장된 도커허브 사용자명. 없으면 빈 문자열.
#
# **로그인 방식이 셋이라 셋 다 본다.** 처음에는 `credsStore` 만 봤는데,
# 그것은 도커 데스크톱(맥·윈도)의 방식이다. 리눅스나 키체인 헬퍼가 없는
# 환경에서 그냥 `docker login` 하면 자격증명이 `auths` 에 바로 박히고,
# 그러면 「로그인된 계정이 없습니다」가 뜨면서 **이 수정이 없애려던 바로 그
# 증상이 그대로 남는다** (`#202` 리뷰, 2heej — 실제로 재현하심).
stored_docker_user () {
  local cfg store user blob
  cfg="${HOME}/.docker/config.json"
  [ -f "${cfg}" ] || return 0

  # ① 레지스트리별 헬퍼가 있으면 그것이 이긴다.
  store="$(tr -d ' \n' < "${cfg}" \
    | sed -n 's/.*"credHelpers":{[^}]*"[^"]*index\.docker\.io[^"]*":"\([^"]*\)".*/\1/p' | head -1)"
  # ② 없으면 공용 저장소.
  [ -n "${store}" ] || store="$(sed -n 's/.*"credsStore"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${cfg}" | head -1)"

  if [ -n "${store}" ] && command -v "docker-credential-${store}" >/dev/null 2>&1; then
    user="$(printf '%s' "${DOCKER_REGISTRY}" | "docker-credential-${store}" get 2>/dev/null \
      | sed -n 's/.*"Username"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
    if [ -n "${user}" ]; then
      printf '%s' "${user}"
      return 0
    fi
  fi

  # ③ 헬퍼가 없으면 `auths` 에 바로 박혀 있다. **사용자명만 꺼내고**
  #    뒤의 비밀값은 쓰지도 찍지도 않는다 — `cut` 이 첫 `:` 앞만 남긴다.
  blob="$(tr -d ' \n' < "${cfg}" \
    | sed -n 's/.*"auths":{[^}]*"[^"]*index\.docker\.io[^"]*":{[^}]*"auth":"\([^"]*\)".*/\1/p' | head -1)"
  [ -n "${blob}" ] || return 0
  b64_decode "${blob}" | cut -d: -f1
}

echo "${COLOR_BLUE}Docker login${COLOR_NC}"

# **PAT 를 화면에 찍지 않는다** (KEY-174).
#   · `read -s` — 입력이 안 보인다. 예전에는 -p 만 있어 그대로 찍혔다
#   · `--password-stdin` — 예전 `docker login -p` 는 경고를 내고 프로세스
#     목록(`ps`)에 값이 남는다
#   · 환경변수로 미리 주면 묻지 않는다 — CI 에서 비대화형으로 돌릴 수 있다
if [ -n "${DOCKER_USERNAME:-}" ] && [ -n "${DOCKER_PAT:-}" ]; then
  # 둘 다 환경변수로 왔다 — CI 경로. 그대로 로그인한다.
  if ! printf '%s' "${DOCKER_PAT}" | docker login -u "${DOCKER_USERNAME}" --password-stdin ; then
    echo "${COLOR_RED}도커 로그인에 실패했습니다. 유저네임과 PAT 을 확인해주세요.${COLOR_NC}"
    exit 1
  fi
  docker_user="${DOCKER_USERNAME}"
  docker_pw="${DOCKER_PAT}"
  echo "${COLOR_GREEN}도커 로그인 성공!${COLOR_NC}"
else
  docker_user="$(stored_docker_user)"
  if [ -n "${docker_user}" ]; then
    echo "${COLOR_GREEN}이미 로그인돼 있습니다 (${docker_user}) — 건너뜁니다.${COLOR_NC}"
  else
    echo "${COLOR_BLUE}로그인된 계정이 없습니다. 도커 데스크톱에 로그인하거나 PAT 을 넣어주세요.${COLOR_NC}"
    if [ -z "${DOCKER_USERNAME:-}" ]; then
      read -r -p "username: " DOCKER_USERNAME
    fi
    if [ -z "${DOCKER_PAT:-}" ]; then
      read -r -s -p "password (PAT, 화면에 안 보입니다): " DOCKER_PAT
      echo ""
    fi
    if ! printf '%s' "${DOCKER_PAT}" | docker login -u "${DOCKER_USERNAME}" --password-stdin ; then
      echo "${COLOR_RED}도커 로그인에 실패했습니다. 유저네임과 PAT 을 확인해주세요.${COLOR_NC}"
      exit 1
    fi
    docker_user="${DOCKER_USERNAME}"
    docker_pw="${DOCKER_PAT}"
    echo "${COLOR_GREEN}도커 로그인 성공!${COLOR_NC}"
  fi
fi
echo ""

# ---------- Docker Repository Input Prompt ----------
echo "${COLOR_BLUE}도커 이미지를 업로드할 레포지토리 이름을 입력해주세요.${COLOR_NC}"
read -p "Docker Repository Name: " docker_repo
echo ""

# ---------- Select Prompt ----------
echo "${COLOR_BLUE}배포 전 빌드 & 푸시할 이미지를 선택하세요(복수선택 가능, 띄어쓰기로 구분)${COLOR_NC}"
echo "1) fastapi"
echo "2) ai_worker"
echo "3) frontend(nginx)"
read -p "선택 (예: 1 2): " selections
echo ""


# ---------- Docker Image Build & Push ----------
DEPLOY_SERVICES=()

for choice in $selections; do
  case $choice in
    1)
      echo "${COLOR_BLUE}FastAPI 앱의 배포 버젼을 입력하세요(ex. v1.0.0)${COLOR_NC}"
      read -p "FastAPI 앱 버젼: " fastapi_version
      build_and_push ${docker_user} ${docker_repo} "FastAPI" ${fastapi_version} "app/Dockerfile" "." "app"
      DEPLOY_SERVICES+=("fastapi")
      ;;
    2)
      echo "${COLOR_BLUE}AI-worker 앱의 배포 버젼을 입력하세요(ex. v1.0.0)${COLOR_NC}"
      read -p "AI-worker 앱 버젼: " ai_version
      build_and_push ${docker_user} ${docker_repo} "AI Worker" ${ai_version} "ai_worker/Dockerfile" "." "ai"
      DEPLOY_SERVICES+=("ai-worker")
      ;;
    3)
      # 프런트를 구운 nginx 이미지. 설정 파일은 안 굽는다 — 아래 `scp` 가
      # http/https 중 고른 것을 올린다 (KEY-189).
      echo "${COLOR_BLUE}프런트(nginx) 이미지의 배포 버젼을 입력하세요(ex. v1.0.0)${COLOR_NC}"
      read -p "프런트 버젼: " web_version
      build_and_push ${docker_user} ${docker_repo} "Frontend(nginx)" ${web_version} "infra/nginx/Dockerfile" "." "web"
      DEPLOY_SERVICES+=("nginx")
      ;;
    *)
      echo "${COLOR_RED}잘못된 선택입니다: $choice${COLOR_NC}"
      exit 1
      ;;
  esac
done

echo "${COLOR_GREEN}모든 선택된 이미지 빌드 & 푸시 완료! 🎉${COLOR_NC}"
echo "${COLOR_BLUE}배포 대상 서비스: ${DEPLOY_SERVICES[*]}${COLOR_NC}"
echo ""

# ---------- SSH 접속 정보 입력 prompt ----------
echo "${COLOR_BLUE}EC2 인스턴스 생성시 발급받은 ssh key 파일의 파일명을 입력하세요.(ex. ai_health_key.pem)${COLOR_NC}"
read -p "SSH 키 파일명: " ssh_key_file
echo ""

echo "${COLOR_BLUE}EC2 인스턴스의 IP를 입력하세요.${COLOR_NC}"
read -p "EC2-IP: " ec2_ip
echo ""

echo "${COLOR_BLUE}배포중인 서버의 https 여부를 선택하세요.${COLOR_NC}"
echo "1) http 사용중"
echo "2) https 사용중"
read -p "선택(ex. 1): " is_https
echo ""

# ---------- EC2 내에 배포 준비 파일 복사  ----------
scp -i ~/.ssh/${ssh_key_file} envs/.prod.env ubuntu@${ec2_ip}:~/project/.env
# **올린 직후에 잠근다** — `scp` 는 로컬 파일의 권한을 그대로 안 옮긴다.
# 기본 umask 로 떨어지면 그 서버의 다른 계정이 읽을 수 있고, 이 파일에는
# `DB_PASSWORD` 와 `SECRET_KEY` 가 들어 있다 (한금준 님 `#133` 보안 확인).
ssh -i ~/.ssh/${ssh_key_file} ubuntu@${ec2_ip} "chmod 600 ~/project/.env"
scp -i ~/.ssh/${ssh_key_file} infra/docker/docker-compose.prod.yml ubuntu@${ec2_ip}:~/project/docker-compose.yml
if [[ "$is_https" == "1" ]] ; then
  # ---------- prod_http.conf 파일의 server_name 자동 수정 ----------
  sed_inplace "s/server_name .*/server_name ${ec2_ip};/g" infra/nginx/prod_http.conf
  scp -i ~/.ssh/${ssh_key_file} infra/nginx/prod_http.conf ubuntu@${ec2_ip}:~/project/nginx/default.conf
else
  echo "${COLOR_BLUE} 사용중인 도메인을 입력하세요. (ex. api.ozcoding.site)${COLOR_NC}"
  read -p "Domain: " domain
  # ---------- prod_https.conf 파일의 server_name, ssl_certificate 자동 수정 ----------
  sed_inplace "s/server_name .*/server_name ${domain};/g" infra/nginx/prod_https.conf
  sed_inplace "s|/etc/letsencrypt/live/[^/]*|/etc/letsencrypt/live/${domain}|g" infra/nginx/prod_https.conf
  scp -i ~/.ssh/${ssh_key_file} infra/nginx/prod_https.conf ubuntu@${ec2_ip}:~/project/nginx/default.conf
fi

# ---------- EC2 배포 자동화  ----------
echo "${COLOR_BLUE}EC2 인스턴스에 SSH 접속을 시도합니다.${COLOR_NC}"
chmod 400 ~/.ssh/${ssh_key_file}
# **PAT 를 ssh 명령줄에 싣지 않는다** — 원격의 `ps` 에 그대로 남는다.
# 스크립트를 통째로 stdin 으로 흘려보낸다. 자세한 사정은 `lib.sh` 참고.
remote_deploy_payload "${docker_pw}" \
  | ssh -i ~/.ssh/${ssh_key_file} ubuntu@${ec2_ip} \
      "DOCKER_USERNAME=${docker_user} \
       DEPLOY_SERVICES='${DEPLOY_SERVICES[*]}' \
       bash -s"

echo "✅ Deployment finished."
