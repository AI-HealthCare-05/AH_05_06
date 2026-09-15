"""README 가 시키는 검사 스크립트가 **제 일을 하는가** — KEY-308.

문서 리뷰는 적힌 대로 따라가 보는 것이다. `README.md` 는 올리기 전에
`scripts/ci/*.sh` 를 돌리라고 한다. 그런데 그 셋이 `TERM` 없는 셸에서
**검사를 한 번도 안 돌린 채 종료코드 2 로 죽고 있었다** — 사람은 통과한 줄
알고 넘어간다.

말로 고치면 다음 사람이 또 `tput` 을 그냥 부른다. 그래서 여기서 **실제로
돌려 본다.**
"""

import re
import subprocess

from app.tests.deploy.conftest import ROOT, read

SCRIPTS = ("check_mypy.sh", "code_fommatting.sh", "run_test.sh")

#: 스크립트가 저장소로 내려가기 전까지 — 색을 정하는 머리말이 여기 있다.
PRELUDE_END = 'cd "$(dirname "$0")/../.."'


def _prelude(name: str) -> str:
    text = read(f"scripts/ci/{name}")
    at = text.find(PRELUDE_END)
    assert at != -1, f"{name}: 머리말의 끝을 못 찾았다 — 검사가 헛돈다"
    return text[:at]


class TestTheScriptsSurviveAShellWithoutTerm:
    """`set -eo pipefail` 아래서 `tput` 이 죽으면 그 자리에서 스크립트가 끝난다."""

    def test_every_script_prelude_runs_with_no_term(self) -> None:
        for name in SCRIPTS:
            done = subprocess.run(
                # 🚩 **`$0` 를 실제 경로로 준다** — KEY-345.
                #
                # `bash -c <글자>` 만 주면 `$0` 가 `bash` 라 `dirname "$0"` 가 `.` 다.
                # 머리말이 `source "$(dirname "$0")/../lib.sh"` 로 옆 파일을 읽게 된
                # 뒤로는, 그 흉내가 실제와 달라서 **스크립트는 멀쩡한데 검사만** 운다.
                # 세 번째 인자가 `$0` 가 된다.
                ["bash", "-c", _prelude(name) + '\necho "여기까지 왔다"', f"scripts/ci/{name}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},  # TERM 없음
            )

            assert done.returncode == 0, (
                f"scripts/ci/{name}: TERM 없는 셸에서 머리말이 죽는다 — "
                f"정작 검사는 한 번도 안 돈다\n{done.stderr[-400:]}"
            )
            assert "여기까지 왔다" in done.stdout, f"scripts/ci/{name}: 머리말을 못 지나갔다"

    def test_no_script_calls_tput_at_all(self) -> None:
        """이제 `tput` 은 **`scripts/lib.sh` 만** 안다 — KEY-345.

        예전에는 셋이 각자 `color()` 를 갖고 있었다(KEY-308). 그것은 `tput` 이
        **죽는 것**만 막고 **터미널인지**(`[ -t 1 ]`)는 안 봐서, CI 로그를 파일로
        흘리면 `ESC[32m` 이 그대로 박혔다. 세 벌을 한 벌로 모았다.
        """
        for name in SCRIPTS:
            text = read(f"scripts/ci/{name}")
            calls = [line for line in text.splitlines() if "tput" in line and not line.lstrip().startswith("#")]

            assert not calls, f"scripts/ci/{name}: `tput` 을 부른다 — `scripts/lib.sh` 의 COLOR_* 를 쓴다: {calls}"
            assert "lib.sh" in text, f"scripts/ci/{name}: 색을 쓰면서 `scripts/lib.sh` 를 안 읽는다"


class TestTheLocalScriptAsksWhatCiAsks:
    """여기서 통과하고 CI 에서 갈리면 이 스크립트를 믿을 수 없다.

    `--explicit-package-bases` 하나가 빠져 있었다. 사람이 두 파일을 나란히
    놓고 볼 일은 없으므로 여기서 맞춰 둔다.
    """

    def _mypy_args(self, text: str) -> set[str]:
        found = re.search(r"uv run mypy ([^\n|]*)", text)
        assert found is not None, "mypy 를 부르는 줄이 없다 — 검사가 헛돈다"
        return {arg for arg in found.group(1).split() if arg.startswith("-")}

    def test_the_flags_are_the_same(self) -> None:
        local = self._mypy_args(read("scripts/ci/check_mypy.sh"))
        ci = self._mypy_args(read(".github/workflows/checks.yml"))

        assert local == ci, (
            f"로컬 스크립트와 CI 의 mypy 인자가 갈렸다 — 로컬만 {sorted(local - ci)}, CI 만 {sorted(ci - local)}"
        )
