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
                ["bash", "-c", _prelude(name) + '\necho "여기까지 왔다"'],
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

    def test_no_script_calls_tput_bare(self) -> None:
        """감싼 자리(`color()`) 하나만 `tput` 을 안다."""
        for name in SCRIPTS:
            calls = [
                line
                for line in read(f"scripts/ci/{name}").splitlines()
                if "tput" in line and not line.lstrip().startswith("#") and not line.startswith("color()")
            ]

            assert not calls, f"scripts/ci/{name}: `tput` 을 그냥 부르는 줄이 있다 — {calls}"


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
