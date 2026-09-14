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
import re
import subprocess

from app.tests.deploy.conftest import ROOT, read

LIB = "scripts/lib.sh"
SOURCING_SCRIPTS = ("scripts/deployment.sh", "scripts/certbot.sh")

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
    for path in sorted((ROOT / "scripts").glob("*.sh")):
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
