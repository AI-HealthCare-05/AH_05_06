set -eo pipefail

# 색은 `scripts/lib.sh` 한 곳에서 온다 — KEY-345.
#
# 예전에는 이 파일이 제 `color()` 를 갖고 있었다(KEY-308). 그것은 `tput` 이
# **죽는 것**만 막고 **터미널인지**(`[ -t 1 ]`)는 안 봤다. 그래서 CI 로그를 파일로
# 흘리면 `ESC[32m` 이 그대로 박혔다.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/../lib.sh"

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
