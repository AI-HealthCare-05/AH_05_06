"""색 때문에 배포가 죽지 않는가 — KEY-345.

2026-09-14 배포를 파이프로 답을 흘려 돌리자 **첫 줄에서 끝났다.**

    tput: No value for $TERM and no -T specified

`deployment.sh` 가 `COLOR_GREEN=$(tput setaf 2)` 로 색을 잡는데, `TERM` 이
없으면 `tput` 이 실패하고 맨 위의 `set -eo pipefail` 이 그것을 잡는다.
**색은 장식인데 그 장식이 배포를 막았다.**

같은 네 줄이 `certbot.sh` 에도 복제돼 있었다 — `lib.sh` 머리말이 경고한
바로 그 모양이다(`sed_inplace` 가 양쪽에 같은 버그를 갖고 있던 일, `#133`).

막는 방법이 **두 겹**이고, 한 겹만으로는 부족하다.

* `tput` 을 부르는 자리를 `lib.sh` 하나로 묶는다 — 옛 판이 여기서 운다.
* 그 하나가 `TERM` 없이도 사는지 **셸을 실제로 돌려** 잰다.

둘째만으로는 옛 판을 못 잡는다. 옛 `lib.sh` 에는 `tput` 이 없었고 결함은
`deployment.sh` 에 있었기 때문이다 — 실제로 그렇게 짰다가 옛 판에 돌려 보고
알았다. 그래서 첫째가 함께 있어야 한다.

`deployment.sh` 를 통째로 돌리지는 않는다. 색 블록 뒤가 도커·`ssh` 로 나가고,
중간의 `sed_inplace` 가 **저장소 파일을 고친다** — 검사가 작업 트리를 건드리면
안 된다.
"""

import os
import pty
import re
import subprocess
import tempfile
from pathlib import Path

from app.tests.deploy.conftest import ROOT, read

LIB = "scripts/lib.sh"

#: 색을 쓰는 셸 전부. `scripts/ci/` 도 센다 — 거기 셋은 KEY-308 때 제 `color()` 를
#: 따로 갖고 있었고, 그것은 `tput` 이 **죽는 것**만 막고 **터미널인지**는 안 봤다.
#: 그래서 CI 로그를 파일로 흘리면 `ESC[32m` 이 그대로 박혔다 (`2heej` `#318` 리뷰).
SOURCING_SCRIPTS = (
    "scripts/deployment.sh",
    "scripts/certbot.sh",
    "scripts/ci/run_test.sh",
    "scripts/ci/check_mypy.sh",
    "scripts/ci/code_fommatting.sh",
)

#: 색 이름 넷. 스크립트들이 실제로 쓰는 것과 같아야 한다.
COLORS = ("COLOR_GREEN", "COLOR_BLUE", "COLOR_RED", "COLOR_NC")

#: `COLOR_X=$(tput …)` 꼴의 **정의**. 주석(`#` 으로 시작)은 세지 않는다 —
#: `lib.sh` 가 옛 모양을 주석으로 인용하고 있어서 그것까지 세면 헛되이 운다.
COLOR_ASSIGNMENT = re.compile(r"^\s*(COLOR_[A-Z]+)\s*=", re.MULTILINE)

#: `tput` **호출**. 낱말 경계를 준다 — 안 주면 `output` 이 걸린다.
#: `bootstrap-local.sh` 의 `local output code` 가 실제로 걸렸다.
TPUT_CALL = re.compile(r"(?<![A-Za-z0-9_])tput(?![A-Za-z0-9_])")


def _source_lib(env_overrides: dict[str, str], *, drop: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    """`lib.sh` 를 배포 스크립트와 **같은 조건**(`set -eo pipefail`)에서 읽는다.

    `deployment.sh` 자체를 돌리지 않는 까닭은, 그것이 색 블록 뒤에서 도커와
    `ssh` 로 나가기 때문이다. 재려는 것은 **색 블록이 살아남는가** 하나다.
    """
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_overrides)
    return subprocess.run(
        ["bash", "-c", f'set -eo pipefail; source {LIB}; printf "%s" "${{#COLOR_GREEN}}"'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_tput_is_called_from_one_guarded_place_only() -> None:
    """**이것이 옛 판을 잡는 검사다.**

    `tput` 을 `lib.sh` 밖에서 부르면 그 자리는 가드를 안 거친다. 옛 판의
    `deployment.sh` · `certbot.sh` 가 정확히 그랬다.
    """
    offenders = {}
    for path in sorted((ROOT / "scripts").rglob("*.sh")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == LIB:
            continue
        lines = [
            n
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if TPUT_CALL.search(line) and not line.lstrip().startswith("#")
        ]
        if lines:
            offenders[rel] = lines
    assert not offenders, (
        f"{LIB} 밖에서 tput 을 부른다: {offenders}\n그 자리는 TERM 가드를 안 거친다 — {LIB} 의 COLOR_* 를 쓴다."
    )


def test_sourcing_survives_without_term() -> None:
    """그 하나가 `TERM` 없이도 사는가 — 가드를 지우면 여기서 운다."""
    done = _source_lib({}, drop=("TERM",))
    assert done.returncode == 0, (
        f"TERM 없이 {LIB} 를 읽자 코드 {done.returncode} 로 끝났다.\n"
        f"stderr: {done.stderr.strip()}\n"
        "색은 장식이다 — 없으면 비우고 넘어가야 한다."
    )
    assert done.stdout == "0", f"TERM 이 없는데 색이 잡혔다(길이 {done.stdout})"


def test_no_color_is_respected() -> None:
    """`NO_COLOR` 는 관례다 — 값이 있으면 끈다 (no-color.org)."""
    done = _source_lib({"TERM": "xterm-256color", "NO_COLOR": "1"})
    assert done.returncode == 0, done.stderr
    assert done.stdout == "0", f"NO_COLOR=1 인데 색이 잡혔다(길이 {done.stdout})"


def test_output_to_a_file_carries_no_escape_codes() -> None:
    """터미널이 아니면 비운다.

    파일로 흘릴 때 색을 넣으면 로그에 `ESC[32m` 이 박혀, 나중에 읽는 사람이
    걷어내야 한다. 실제로 이번 배포 로그를 `sed` 로 지우고 읽었다.
    """
    done = _source_lib({"TERM": "xterm-256color"})
    assert done.returncode == 0, done.stderr
    assert done.stdout == "0", f"파이프로 받는데 색이 잡혔다(길이 {done.stdout})"


def test_the_colors_are_defined_in_one_place() -> None:
    """한쪽만 고치는 일이 다시 생기지 않게 — `lib.sh` 가 유일한 정의처다."""
    for rel in SOURCING_SCRIPTS:
        found = set(COLOR_ASSIGNMENT.findall(read(rel)))
        assert not found, f"{rel} 이 색을 스스로 정의한다: {sorted(found)} — {LIB} 것을 쓴다"

    in_lib = set(COLOR_ASSIGNMENT.findall(read(LIB)))
    missing = set(COLORS) - in_lib
    assert not missing, f"{LIB} 이 {sorted(missing)} 를 안 준다 — 쓰는 쪽이 빈 변수를 본다"


def test_every_script_that_uses_colors_sources_the_library() -> None:
    """색을 쓰면서 `lib.sh` 를 안 읽으면 **빈 변수로 조용히 돈다.**"""
    for rel in SOURCING_SCRIPTS:
        text = read(rel)
        if not any(f"${{{name}}}" in text for name in COLORS):
            continue
        assert "lib.sh" in text, f"{rel} 이 색을 쓰면서 {LIB} 를 안 읽는다"


def _run_on_a_pty(body: str, env_overrides: dict[str, str], *, drop: tuple[str, ...] = ()) -> tuple[int, str]:
    """**진짜 터미널을 붙여** 돌리고, 결과는 파일로 받는다 — `2heej` `#318` 리뷰 3번.

    다른 검사들은 `capture_output=True` 라 stdout 이 파이프다. 그러면 `[ -t 1 ]`
    이 늘 거짓이라 **「터미널 아님」 가지만** 탄다 — `TERM` 을 지우든 말든 같다.
    정작 이 티켓이 시작된 사고(**터미널인데 `TERM` 이 없어 `tput` 이 죽는 것**)의
    가지가 자동 검사로는 한 번도 안 돌고 있었다.

    🚩 **pty 는 `[ -t 1 ]` 을 참으로 만드는 데만 쓰고, 답은 파일로 받는다.**
    처음에는 master 쪽에서 읽어 오려 했는데 빈 문자열만 왔다 — 자식이 끝난 뒤
    slave 가 다 닫히면 macOS 의 master 읽기는 남은 것을 안 주고 `EIO` 로 끝난다.
    터미널을 흉내내는 것과 출력을 받아 오는 것을 섞지 않는다.
    """
    env = {key: value for key, value in os.environ.items() if key not in drop}
    env.update(env_overrides)

    with tempfile.TemporaryDirectory() as folder:
        answer = Path(folder) / "answer"
        parent, child = pty.openpty()
        try:
            done = subprocess.run(
                ["bash", "-c", f'set -eo pipefail; source {LIB}; {body} > "{answer}"'],
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=child,
                stderr=child,
            )
        finally:
            os.close(child)
            os.close(parent)
        return done.returncode, answer.read_text(encoding="utf-8") if answer.exists() else ""


def test_a_real_terminal_without_term_does_not_kill_the_script() -> None:
    """🚩 **이 티켓이 시작된 그 상황이다.**

    터미널에 붙어 있는데 `TERM` 이 없다. 고치기 전에는 여기서 `tput` 이
    「No value for $TERM」으로 죽고 `set -eo pipefail` 이 스크립트를 끝냈다.
    """
    code, answer = _run_on_a_pty('printf "%s" "${#COLOR_GREEN}"', {}, drop=("TERM",))

    assert code == 0, f"터미널인데 TERM 이 없자 코드 {code} 로 죽었다"
    assert answer == "0", f"TERM 이 없는데 색이 잡혔다(길이 {answer!r})"


def test_a_real_terminal_with_term_still_gets_colour() -> None:
    """반대쪽도 재 둔다 — 걷어낸 것이 너무 많으면 여기서 걸린다.

    이 검사가 없으면 `_supports_color` 를 `return 1` 하나로 바꿔도 위의 검사들이
    전부 통과한다. **색이 영영 안 나오는 것**도 고장이다.
    """
    code, answer = _run_on_a_pty('printf "%s" "${#COLOR_GREEN}"', {"TERM": "xterm-256color"})

    assert code == 0, "진짜 터미널에서 죽었다"
    assert answer not in ("", "0"), f"진짜 터미널인데 색이 비었다(길이 {answer!r})"
