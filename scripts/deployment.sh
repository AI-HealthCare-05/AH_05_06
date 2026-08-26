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
  echo "${COLOR_BLUE}${name} Docker Image Build Start.${COLOR_NC}"
  docker build --platform linux/amd64 -t ${docker_user}/${docker_repo}:${tag_base}-${tag} -f ${dockerfile} ${context}

  echo "${COLOR_BLUE}${name} Docker Image Push Start.${COLOR_NC}"
  docker push ${docker_user}/${docker_repo}:${tag_base}-${tag}

  echo "${COLOR_GREEN}${name} Done.${COLOR_NC}"
  echo ""
}

# ---------- Docker login ----------
#
# **PAT 를 화면에 찍지 않는다** (KEY-174).
#   · `read -s` — 입력이 안 보인다. 예전에는 -p 만 있어 그대로 찍혔다
#   · `--password-stdin` — 예전 `docker login -p` 는 경고를 내고 프로세스
#     목록(`ps`)에 값이 남는다
#   · 환경변수로 미리 주면 묻지 않는다 — CI 에서 비대화형으로 돌릴 수 있다
echo "${COLOR_BLUE}Docker login${COLOR_NC}"
if [ -z "${DOCKER_USERNAME:-}" ]; then
  read -r -p "username: " DOCKER_USERNAME
fi
if [ -z "${DOCKER_PAT:-}" ]; then
  read -r -s -p "password (PAT, 화면에 안 보입니다): " DOCKER_PAT
  echo ""
fi
docker_user="${DOCKER_USERNAME}"
docker_pw="${DOCKER_PAT}"

if ! printf '%s' "${docker_pw}" | docker login -u "${docker_user}" --password-stdin ; then
  echo "${COLOR_RED}도커 로그인에 실패했습니다. 유저네임과 PAT 을 확인해주세요.${COLOR_NC}"
  exit 1
fi
echo "${COLOR_GREEN}도커 로그인 성공!${COLOR_NC}"
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
