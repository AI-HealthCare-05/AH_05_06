"""**서버가 제 출처를 알아야 한다** — KEY-315.

`~/project` 에는 `.env` · `docker-compose.yml` · `nginx` 셋뿐이고 저장소가 없다.
이미지에도 아무 표시가 없어서, 도는 것이 어느 커밋에서 나왔는지 되짚을 길이
Docker Hub 태그(`app-vX.Y.Z`)뿐이었다 — 그 태그는 사람이 손으로 올리는 값이라
커밋을 말해 주지 않는다.

KEY-201 리뷰에서 실제로 막혔다. 9/4 배포가 develop 에서 나온 것으로 **정황상**
맞았지만(푸시 5분 전 develop 끝이 그 언저리) 단정할 수단이 없었다. 배포 사고를
의심할 때 출처를 못 밝히면 조사 자체가 시작을 못 한다.

여기서 재는 것은 **이름이 아니라 규칙**이다 — 「굽는 자리가 커밋을 붙이는가」.
이미지가 늘어도 따라오도록, 굽는 명령을 세어 그 전부를 본다.
"""

import re

from app.tests.deploy.conftest import read

DEPLOY = "scripts/deployment.sh"

#: 붙어야 하는 표준 이름(OCI). 도구들이 이미 이 이름을 읽는다.
REVISION = "org.opencontainers.image.revision"
REF_NAME = "org.opencontainers.image.ref.name"


def _build_commands(script: str) -> list[str]:
    """`docker build` 한 줄 — 줄바꿈(`\\`)으로 이어진 것을 한 덩이로 본다.

    이어 붙이지 않으면 `--label` 이 다음 줄에 있을 때 **명령에 없다고 읽는다.**
    """
    joined = re.sub(r"\\\s*\n\s*", " ", script)
    return [line.strip() for line in joined.splitlines() if "docker build" in line]


class TestEveryImageSaysWhereItCameFrom:
    def test_the_deploy_builds_something(self) -> None:
        """굽는 자리가 없으면 아래 검사들이 헛돈다."""
        assert _build_commands(read(DEPLOY)), "배포가 이미지를 안 굽는다 — 검사가 헛돈다"

    def test_every_build_labels_the_commit(self) -> None:
        """**전부**에 붙어야 한다 — 하나만 빠져도 그 이미지는 말을 못 한다."""
        for command in _build_commands(read(DEPLOY)):
            assert REVISION in command, f"굽는 명령에 커밋 라벨이 없다 — {command[:90]}"
            assert REF_NAME in command, f"굽는 명령에 브랜치 라벨이 없다 — {command[:90]}"

    def test_the_labels_carry_the_real_revision(self) -> None:
        """라벨 값이 **git 에서 온 것**이어야 한다.

        고정 문자열을 박아 두면 라벨은 있는데 늘 같은 값을 말한다 — 없는 것보다
        나쁘다. 실제로 `git rev-parse` 로 채우는지 본다.
        """
        script = read(DEPLOY)

        assert "git rev-parse HEAD" in script, "커밋을 git 에 안 묻는다 — 라벨이 고정값일 수 있다"
        assert "git rev-parse --abbrev-ref HEAD" in script, "브랜치를 git 에 안 묻는다"

    def test_a_dirty_tree_is_marked_and_announced(self) -> None:
        """커밋 안 된 변경으로 구우면 그 SHA 는 거짓말이 된다.

        라벨은 「이 커밋이다」라고 말하는데 담긴 것은 그 커밋 + 손댄 것이라,
        나중에 그 SHA 를 받아 봐도 같은 판이 안 나온다. 표시와 경고 **둘 다**
        있어야 한다 — 표시만 있으면 굽는 사람이 모르고, 경고만 있으면 나중에
        보는 사람이 모른다.
        """
        script = read(DEPLOY)

        assert "git status --porcelain" in script, "손댄 것이 있는지 안 본다"
        assert "-dirty" in script, "라벨에 표시를 안 남긴다 — 나중에 보는 사람이 모른다"

        at = script.index("git status --porcelain")
        nearby = script[at : at + 700]
        assert "echo" in nearby, "굽는 사람에게 안 알린다 — 그 자리에서 멈출 기회가 없다"


class TestTheRunbookSaysHowToReadIt:
    """붙여 두기만 하고 **읽는 법**이 없으면 아무도 안 본다."""

    def test_the_runbook_shows_the_inspect_command(self) -> None:
        runbook = read("docs/deploy-runbook.md")

        assert "docker inspect" in runbook, "런북이 도는 것의 커밋을 볼 방법을 안 적었다"
        assert REVISION in runbook, "런북이 어느 라벨을 볼지 안 말한다"

    def test_the_runbook_warns_about_dirty(self) -> None:
        """`-dirty` 를 보고도 그냥 믿으면 붙인 뜻이 없다."""
        runbook = read("docs/deploy-runbook.md")

        assert "-dirty" in runbook, "런북이 `-dirty` 를 어떻게 읽을지 안 적었다"
