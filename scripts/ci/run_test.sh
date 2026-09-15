set -eo pipefail

# 색은 `scripts/lib.sh` 한 곳에서 온다 — KEY-345.
#
# 예전에는 이 파일이 제 `color()` 를 갖고 있었다(KEY-308). 그것은 `tput` 이
# **죽는 것**만 막고 **터미널인지**(`[ -t 1 ]`)는 안 봤다. 그래서 CI 로그를 파일로
# 흘리면 `ESC[32m` 이 그대로 박혔다.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/../lib.sh"

cd "$(dirname "$0")/../.."

source .env

echo "${COLOR_BLUE}Find Tests${COLOR_NC}"

HAS_TESTS=false
MYSQL_CONTAINER_NAME=mysql

if [ -d "./app/tests" ] && find ./app/tests -name 'test_*.py' -print -quit | read ; then
  HAS_TESTS=true
fi

echo "Has tests: $HAS_TESTS"

if [ "$HAS_TESTS" = true ]; then
  if docker ps --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER_NAME}$"; then
    echo "${COLOR_BLUE}→ MySQL container found. Granting privileges...${COLOR_NC}"

    docker exec -i ${MYSQL_CONTAINER_NAME} \
    mysql -u root -p${DB_ROOT_PASSWORD}<<EOF
      GRANT ALL PRIVILEGES ON *.* TO '${DB_USER}'@'%' WITH GRANT OPTION;
      FLUSH PRIVILEGES;
EOF

    echo "${COLOR_BLUE}Run Pytest with Coverage${COLOR_NC}"

    if ! uv run coverage run -m pytest app; then
      echo ""
      echo "${COLOR_RED}✖ Pytest failed.${COLOR_NC}"
      echo "${COLOR_RED}→ Fix the test failures above and re-run.${COLOR_NC}"
      exit 1
    fi

    echo "${COLOR_BLUE}Coverage Report${COLOR_NC}"
    if ! uv run coverage report -m ; then
      echo "${COLOR_RED}✖ Coverage check failed.${COLOR_NC}"
      exit 1
    fi
  else
    echo "${COLOR_RED} MySQL Docker Container Not Found. Run docker compose up mysql.${COLOR_NC}"
  fi
else
  echo "${COLOR_BLUE}No tests found. Skipping tests.${COLOR_NC}"
fi
