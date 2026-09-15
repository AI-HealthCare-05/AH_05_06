"""`ssh` 가 남은 입력을 삼키지 않는가 — KEY-350.

2026-09-15 배포가 **이미지를 다 올린 뒤 조용히 끝났다.** 종료코드 1, 오류 한 줄
없음. `deployment.sh` 의 `chmod 600` 을 거는 `ssh` 가 `-n` 없이 돌아 **남은
stdin 을 통째로 삼켰고**, 그 뒤의 `read -p "Domain: "` 이 EOF 를 받아
`set -eo pipefail` 이 죽음으로 처리했다. `read` 는 실패해도 아무 말을 안 한다.

**삼키는 양은 그때 파이프에 들어와 있던 만큼이라 때마다 다르다** — 전날 같은
방식이 지나갔다. 사람이 손으로 칠 때는 터미널이 stdin 이라 아예 안 드러난다.

`lib.sh` 가 원격 페이로드를 만드는 이유를 적으며 이미 경고해 둔 자리다 —
「`bash -s` 는 stdin 을 스크립트로 읽으므로 … stdin 을 쓰는 것은 전부 이 자리에
걸린다」. 같은 종류를 `#309` 의 `docker compose exec -T` 에서도 한 번 밟았다.

**가려야 할 것이 하나 있다.** 맨 끝의 `remote_deploy_payload | ssh … bash -s` 는
stdin 이 곧 스크립트다. 거기에 `-n` 을 붙이면 배포가 통째로 안 돈다. 그래서 이
검사는 **원격 명령을 인자로 받는** 호출만 본다.
"""

import re

from app.tests.deploy.conftest import ROOT

#: **명령 자리의** `ssh`. 줄 맨 앞이거나 `|`·`;`·`&&` 뒤에 온 것만 본다.
#:
#: 낱말만 찾으면 산문이 걸린다 — `echo "… 발급받은 ssh key 파일명 …"` 이 실제로
#: 걸렸다. 이 저장소는 프롬프트 문구를 한국어로 적어서 그런 줄이 여럿이다.
SSH_CALL = re.compile(r"(?:^|[|;&(]\s*)ssh\s")

#: `-n` 이 붙었는가. 다른 옵션 사이에 있어도 잡는다.
HAS_DASH_N = re.compile(r"(?<![A-Za-z0-9_-])-n(?=\s|$)")

#: stdin 을 **일부러** 쓰는 호출. 파이프로 스크립트를 흘려 넣는 자리다.
STDIN_IS_THE_SCRIPT = "bash -s"


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """줄 이어쓰기(`\\`)를 이어 붙여 **한 명령을 한 줄로** 만든다.

    🚩 이걸 안 하면 배포의 핵심 호출을 못 본다. 그 줄은 이렇게 쪼개져 있다.

        remote_deploy_payload "${docker_pw}" \\
          | ssh -i ~/.ssh/${ssh_key_file} ubuntu@${ec2_ip} \\
              "… bash -s"

    `ssh` 와 `bash -s` 가 **다른 줄**이라, 줄 단위로 훑으면 「stdin 을 쓰는
    호출」로 못 알아보고 `-n` 을 붙이라고 우긴다. 처음에 그렇게 짰다가 걸렸다.
    """
    out: list[tuple[int, str]] = []
    buffer, start = "", 0
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not buffer:
            start = number
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        out.append((start, buffer + stripped))
        buffer = ""
    if buffer:
        out.append((start, buffer))
    return out


def _ssh_lines() -> list[tuple[str, int, str]]:
    """`scripts/` 아래 모든 셸에서 **명령으로** `ssh` 를 부르는 자리. 주석은 뺀다."""
    out: list[tuple[str, int, str]] = []
    for path in sorted((ROOT / "scripts").rglob("*.sh")):
        rel = path.relative_to(ROOT).as_posix()
        for number, line in _logical_lines(path.read_text(encoding="utf-8")):
            if line.startswith("#") or not SSH_CALL.search(line):
                continue
            out.append((rel, number, line))
    return out


def test_every_ssh_that_runs_a_remote_command_passes_dash_n() -> None:
    """`-n` 이 없으면 그 `ssh` 는 **뒤에 올 물음의 답을 먹는다.**"""
    offenders = [
        f"{rel}:{number}  {line}"
        for rel, number, line in _ssh_lines()
        if STDIN_IS_THE_SCRIPT not in line and not HAS_DASH_N.search(line)
    ]

    assert not offenders, (
        "원격 명령을 거는 `ssh` 에 `-n` 이 없다 — 남은 stdin 을 삼켜 뒤의 `read` 가 EOF 로 죽는다:\n"
        + "\n".join(f"  {item}" for item in offenders)
    )


def test_the_piped_payload_call_is_left_alone() -> None:
    """🚩 **stdin 이 곧 스크립트인 호출**에는 `-n` 을 요구하지 않는다.

    붙이면 원격이 빈 스크립트를 받아 **배포가 아무 일도 안 하고 성공한 척한다.**
    위 검사가 그것까지 요구하게 되는 순간이 제일 나쁘므로 여기서 못을 박는다.
    """
    piped = [line for _, _, line in _ssh_lines() if STDIN_IS_THE_SCRIPT in line]

    assert piped, "`bash -s` 로 스크립트를 흘려 넣는 `ssh` 가 사라졌다 — 배포 경로가 바뀌었는지 본다"
    for line in piped:
        assert not HAS_DASH_N.search(line), (
            f"stdin 으로 스크립트를 받는 `ssh` 에 `-n` 이 붙었다 — 원격이 빈 스크립트를 받는다:\n  {line}"
        )
