set -eo pipefail

# 색은 붙으면 좋고 없어도 그만이다. **`tput` 을 그냥 부르면 안 된다** — `TERM` 이
# 없는 셸(CI 단계·`sh -c`·비대화형)에서 「No value for $TERM」으로 죽고, `set -e`
# 아래라 그 자리에서 스크립트가 끝난다. 종료코드 2 로 죽으면서 정작 검사는 한 번도
# 안 돈다 — 통과한 줄 알고 넘어가게 된다 (KEY-308).
color() { command -v tput >/dev/null 2>&1 && tput "$@" 2>/dev/null || true; }

COLOR_GREEN=$(color setaf 2)
COLOR_BLUE=$(color setaf 4)
COLOR_RED=$(color setaf 1)
COLOR_NC=$(color sgr0)

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
