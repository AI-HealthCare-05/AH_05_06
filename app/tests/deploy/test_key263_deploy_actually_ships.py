"""배포가 프런트를 빠뜨리거나 조용히 끝나지 않는가 — KEY-263.

2026-09-03 배포에서 세 가지가 한꺼번에 드러났다. 셋 다 **소리 없이 깨지는**
종류라 사람 눈으로는 못 잡는다.

1. `.dockerignore` 가 `frontend/` 를 빼서 **web 이미지가 사흘간 안 구워졌다.**
   `fastapi`·`ai_worker` 는 정말로 안 쓰므로 둘은 멀쩡했고, 그래서 아무도
   몰랐다 — 서버 화면이 8/28 에 멈춰 있었다.
2. 원격 `aerich upgrade` 가 **stdin 을 삼켜** 뒤의 `up -d` 가 통째로 안 돌았다.
   `aerich` 는 0 으로 끝나므로 `set -e` 에도 안 걸리고 `✅ Deployment finished`
   가 찍힌다.
3. 배포 스크립트가 **없는 PAT** 을 매번 요구했다 — 도커 데스크톱에 SSO
   (구글)로 들어온 계정에는 CLI 에 넣을 비밀번호가 없다.

값은 안 읽는다 — **이름과 구조만** 본다.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.tests.deploy.conftest import ROOT, nginx_copy_sources, read

#: **stdin 을 먹는 명령들.** `docker compose run|exec` 하나만 보던 것을 넓혔다 —
#: 나중에 `ssh` 나 `docker exec -it` 가 하나 더 붙으면 같은 일이 나는데 옛
#: 패턴은 못 잡았다 (`#202` 리뷰, 2heej).
#:
#: 한 번에 닫는 `exec < /dev/null` 은 **못 쓴다.** 스크립트 자신이 stdin 에
#: 실려 있어서(`bash -s`) 닫는 순간 뒤가 안 읽힌다 — `scripts/lib.sh` 주석 참고.
EATS_STDIN = re.compile(r"docker\s+compose\s+(run|exec)\b|docker\s+exec\b|^\s*ssh\s|^\s*read\b|^\s*cat\s*$")

NGINX_DOCKERFILE = "infra/nginx/Dockerfile"
DOCKERIGNORE = ".dockerignore"
LIB = ROOT / "scripts" / "lib.sh"
DEPLOYMENT = ROOT / "scripts" / "deployment.sh"


def _dockerignore_excludes() -> list[str]:
    """제외 규칙들. `!` 로 시작하는 되살리기 규칙은 뺀다."""
    out: list[str] = []
    for raw in read(DOCKERIGNORE).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        out.append(line.rstrip("/"))
    return out


class TestTheWebImageCanStillSeeTheFrontend:
    def test_dockerignore_does_not_exclude_what_the_nginx_image_copies(self) -> None:
        """🚩 **`.dockerignore` 가 web 이미지의 재료를 빼면 안 된다.**

        `fba3c95`(2026-08-31) 가 `frontend/` 를 「이미지가 안 쓰는 것」 목록에
        넣었다. `fastapi`·`ai_worker` 기준으로는 맞는 말이지만 **web 이미지는
        그게 전부다** — 빌드가 `/frontend/css: not found` 로 죽는다.

        그런데 web 을 굽는 사람이 사흘간 없어서 **아무도 몰랐다.** 그 사이
        배포는 계속 성공했고 화면만 8/28 것이 나갔다.

        경로를 하나하나 적지 않고 **Dockerfile 이 실제로 `COPY` 하는 것**을
        읽는다. 나중에 `frontend/img/` 를 더해도 이 검사가 따라온다.
        """
        excludes = _dockerignore_excludes()
        sources = nginx_copy_sources()
        assert sources, "nginx Dockerfile 에서 COPY 를 하나도 못 읽었다 — 검사가 헛돌고 있다"

        for src in sources:
            head = src.split("/")[0]
            assert head not in excludes, (
                f"`.dockerignore` 가 `{head}` 를 빼는데 `{NGINX_DOCKERFILE}` 이 `{src}` 를 굽는다 — web 빌드가 죽는다"
            )

    def test_the_frontend_files_the_server_serves_are_in_the_context(self) -> None:
        """화면 파일이 실제로 컨텍스트에 남아 있는가.

        위 검사는 규칙을 보고, 이것은 **결과**를 본다. 규칙을 우회하는 다른
        경로로 빠지면 위는 통과하고 이것이 운다.
        """
        for rel in ("frontend/settings.html", "frontend/js/settings.js", "frontend/css/tokens.css"):
            assert (ROOT / rel).exists(), f"{rel} 이 없다"


def _remote_payload(pat: str = "") -> str:
    """`lib.sh` 가 실제로 원격에 보낼 스크립트."""
    out = subprocess.run(
        ["bash", "-c", f'. "{LIB}" && remote_deploy_payload "{pat}"'],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


class TestTheRemoteScriptRunsToTheEnd:
    def test_every_stdin_reading_command_is_fed_from_dev_null(self) -> None:
        """🚨 **원격 본문은 `bash -s` 의 stdin 이다.**

        그 안에서 stdin 을 읽는 명령은 **아직 안 읽은 스크립트 나머지**를
        먹는다. 2026-09-03 에 `aerich upgrade` 가 그렇게 뒤의 `up -d` 와
        `image prune` 을 통째로 삼켰다.

        `read` 는 예전에 같은 함정에 걸려 heredoc 으로 바꿨다(`#133` 리뷰).
        **stdin 을 쓰는 것은 전부** 막아야 하므로 한 줄씩 잰다.
        """
        offenders = [
            line.strip()
            for line in _remote_payload().splitlines()
            if EATS_STDIN.search(line)
            and "< /dev/null" not in line
            and "<<" not in line  # heredoc 은 제 입력을 들고 온다
            and not line.lstrip().startswith("#")
        ]
        assert not offenders, f"원격 스크립트에서 stdin 을 안 막은 줄이 있다 — 뒤가 통째로 안 돈다: {offenders}"

    def test_the_payload_still_reaches_the_container_swap(self) -> None:
        """**`up -d` 가 본문에 있는가.**

        위 검사는 「막았는가」를 재고 이것은 「그래서 도달하는가」를 잰다.
        삼킴 사고의 증상이 바로 이 줄이 안 도는 것이었다.
        **순서(마이그레이션이 `up -d` 보다 먼저)는 여기서 안 잰다** —
        `test_key206_deploy_migrates.py` 가 이미 잰다. 같은 것을 두 방식으로
        재면 둘이 갈린다 (`#202` 리뷰, 2heej).
        """
        assert "docker compose up -d" in _remote_payload(), "컨테이너를 바꾸는 줄이 없다"

    def test_the_pat_never_rides_on_the_command_line(self) -> None:
        """PAT 은 heredoc 으로만 넘어간다 — 원격 `ps` 노출 방지(KEY-174)."""
        body = _remote_payload("SECRET-PAT-VALUE")
        for line in body.splitlines():
            if "SECRET-PAT-VALUE" not in line:
                continue
            assert line.strip() == "SECRET-PAT-VALUE", f"PAT 이 명령 안에 박혔다 — `ps` 에 남는다: {line!r}"


def _run_login_block(
    tmp_path: Path,
    *,
    stored_user: str | None,
    env: dict[str, str],
    config: dict[str, object] | None = None,
) -> str:
    """`deployment.sh` 의 Docker login 구간만 떼어 돌린다.

    통째로 돌릴 수 없다 — 빌드하고 `scp` 한다. 구간 경계는 스크립트에 이미
    있는 두 머리말이라, 그것이 사라지면 이 검사가 먼저 운다.
    """
    text = DEPLOYMENT.read_text(encoding="utf-8")
    start = text.index("# ---------- Docker login ----------")
    end = text.index("# ---------- Docker Repository Input Prompt ----------")
    block = text[start:end]

    home = tmp_path / "home"
    (home / ".docker").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # 가짜 `docker` — 진짜 로그인을 하지 않는다.
    (bin_dir / "docker").write_text('#!/bin/sh\necho "[stub] docker $*"\ncat >/dev/null\n')
    (bin_dir / "docker").chmod(0o755)

    # 헬퍼는 늘 둔다 — 어떤 설정이 그것을 부르는지가 검사의 주제다.
    helper = bin_dir / "docker-credential-teststub"
    helper.write_text(f'#!/bin/sh\ncat >/dev/null\nprintf \'{{"Username":"{stored_user}"}}\'\n')
    helper.chmod(0o755)

    if config is None:
        config = {"credsStore": "teststub"} if stored_user is not None else {"auths": {}}
    (home / ".docker" / "config.json").write_text(json.dumps(config))

    script = 'COLOR_BLUE=""; COLOR_GREEN=""; COLOR_RED=""; COLOR_NC=""\n' + block + '\necho "USER=[${docker_user}]"\n'
    # 🚩 **실행 환경의 자격증명 변수를 흡수하지 않는다.**
    #
    # `os.environ` 을 먼저 펼치면, 돌리는 셸이나 CI 에 `DOCKER_USERNAME` ·
    # `DOCKER_PAT` 가 이미 export 되어 있을 때(이 저장소 문서에도 나오는
    # 이름이라 충분히 있을 수 있다) **「아무것도 저장 안 됨」·「이미
    # 로그인됨」 두 검사가 전부 CI 분기를 타 버린다** — 재려던 갈래를
    # 아예 안 지난다 (`#202` 리뷰, 2heej — 실제로 재현하심).
    runtime = {k: v for k, v in os.environ.items() if k not in ("DOCKER_USERNAME", "DOCKER_PAT")}
    out = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**runtime, **env, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    return out.stdout + out.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 가 없다")
class TestLoginDoesNotAskForAPasswordThatDoesNotExist:
    def test_it_skips_the_prompt_when_credentials_are_already_stored(self, tmp_path: Path) -> None:
        """🚩 **이미 로그인돼 있으면 묻지 않는다.**

        도커 데스크톱에 구글(SSO)로 들어온 계정에는 **CLI 에 넣을 비밀번호가
        없다.** 그 칸이 받는 것은 PAT 인데, 그걸 모르면 빈 입력으로
        `password is empty` 를 맞고 거기서 배포가 끝난다.

        이미 저장된 토큰이 있으면 `docker push` 는 그냥 된다.
        """
        out = _run_login_block(tmp_path, stored_user="iljunk", env={})
        assert "USER=[iljunk]" in out, "이미지 이름에 쓸 사용자명을 못 집었다"
        assert "password" not in out.lower(), f"로그인돼 있는데 비밀번호를 물었다: {out!r}"

    def test_it_still_asks_when_nothing_is_stored(self, tmp_path: Path) -> None:
        """저장된 것이 없으면 **예전처럼 묻는다** — 회귀."""
        out = _run_login_block(tmp_path, stored_user=None, env={})
        assert "로그인된 계정이 없습니다" in out, f"안 물었다: {out!r}"

    def test_it_sees_a_login_that_landed_straight_in_auths(self, tmp_path: Path) -> None:
        """🚩 **`credsStore` 만 보면 리눅스의 로그인을 못 본다.**

        키체인 헬퍼가 없는 환경에서 그냥 `docker login` 하면 자격증명이
        `credsStore` 없이 `auths` 에 바로 박힌다. 처음에는 그 경우를 안 봐서
        **이 수정이 없애려던 「PAT 을 또 묻는」 증상이 그대로 남아 있었다**
        (`#202` 리뷰, 2heej — 실제로 재현하심).

        `auth` 는 `사용자명:비밀값` 을 base64 로 담는데, **앞의 사용자명만**
        꺼낸다. 아래 값은 `iljunk:secret` 이다.
        """
        out = _run_login_block(
            tmp_path,
            stored_user="never-used",
            env={},
            config={"auths": {"https://index.docker.io/v1/": {"auth": "aWxqdW5rOnNlY3JldA=="}}},
        )
        assert "USER=[iljunk]" in out, f"`auths` 에 있는 로그인을 못 봤다: {out!r}"
        assert "password" not in out.lower(), "로그인돼 있는데 PAT 을 또 물었다"
        assert "secret" not in out, "비밀값이 새어 나왔다"

    def test_a_registry_specific_helper_wins(self, tmp_path: Path) -> None:
        """`credHelpers` 는 레지스트리별 덮어쓰기다 — 그것도 봐야 한다."""
        out = _run_login_block(
            tmp_path,
            stored_user="from-helper",
            env={},
            config={"credHelpers": {"index.docker.io": "teststub"}, "auths": {}},
        )
        assert "USER=[from-helper]" in out, f"`credHelpers` 를 못 봤다: {out!r}"

    def test_environment_variables_still_drive_a_real_login(self, tmp_path: Path) -> None:
        """`DOCKER_USERNAME` · `DOCKER_PAT` 를 둘 다 주면 그대로 로그인한다.

        CI 에서 비대화형으로 돌리는 길이다(KEY-174). 저장된 자격증명이 있어도
        **환경변수가 이긴다** — 다른 계정으로 밀어야 할 때가 있다.
        """
        out = _run_login_block(
            tmp_path,
            stored_user="iljunk",
            env={"DOCKER_USERNAME": "ciuser", "DOCKER_PAT": "dummy"},
        )
        assert "docker login -u ciuser" in out, f"환경변수 경로로 안 갔다: {out!r}"
        assert "USER=[ciuser]" in out
