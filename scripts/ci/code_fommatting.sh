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

echo "${COLOR_BLUE}Start Ruff Auto Fix${COLOR_NC}"
uv run ruff check . --fix || true
echo "${COLOR_GREEN}Auto-fix Done${COLOR_NC}"

echo "${COLOR_BLUE}Check remaining issues${COLOR_NC}"
if ! uv run ruff check .; then
  echo ""
  echo "${COLOR_RED}✖ Ruff found issues that could NOT be auto-fixed.${COLOR_NC}"
  echo "${COLOR_RED}→ Please fix the issues above manually and re-run the command.${COLOR_NC}"
  exit 1
fi

echo "${COLOR_BLUE}Start Formatting${COLOR_NC}"
uv run ruff format .

echo "${COLOR_GREEN}Code formatting successfully!${COLOR_NC}"
