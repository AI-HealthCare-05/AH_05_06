set -eo pipefail

# 색은 `scripts/lib.sh` 한 곳에서 온다 — KEY-345.
#
# 예전에는 이 파일이 제 `color()` 를 갖고 있었다(KEY-308). 그것은 `tput` 이
# **죽는 것**만 막고 **터미널인지**(`[ -t 1 ]`)는 안 봤다. 그래서 CI 로그를 파일로
# 흘리면 `ESC[32m` 이 그대로 박혔다.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/../lib.sh"

cd "$(dirname "$0")/../.."

echo "${COLOR_BLUE}Run Mypy${COLOR_NC}"
# CI(`.github/workflows/checks.yml`)와 같은 인자를 쓴다 — 여기서 통과하고
# CI 에서 갈리면 이 스크립트를 믿을 수 없다.
if ! uv run mypy . --explicit-package-bases ; then
  echo ""
  echo "${COLOR_RED}✖ Mypy found issues.${COLOR_NC}"
  echo "${COLOR_RED}→ Please fix the issues above manually and re-run the command.${COLOR_NC}"
  exit 1
fi

echo "${COLOR_GREEN}Successfully Ended.${COLOR_NC}"
