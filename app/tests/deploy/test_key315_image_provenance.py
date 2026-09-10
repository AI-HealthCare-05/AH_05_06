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
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from app.tests.deploy.conftest import read

DEPLOY = "scripts/deployment.sh"

#: 붙어야 하는 표준 이름(OCI). 도구들이 이미 이 이름을 읽는다.
REVISION = "org.opencontainers.image.revision"
REF_NAME = "org.opencontainers.image.ref.name"


def _section(heading: str) -> str:
    """런북에서 그 절만 떼어 온다 — 다음 같은 깊이의 제목까지."""
    runbook = read("docs/deploy-runbook.md")
    at = runbook.index(heading)
    return runbook[at : runbook.index("\n## ", at + 5)]


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
        나쁘다.

        🚩 처음엔 `git rev-parse HEAD` 라는 **글자가 파일 어딘가에 있는지**만
        봤다. 그러면 SHA 를 로그용으로만 계산하고 라벨 값은 하드코딩하는 회귀가
        그대로 통과한다 (2heej 님 리뷰 ④). 이제 **라벨이 그 변수를 참조하는지**
        와 **그 변수가 git 에서 채워지는지**를 이어서 본다.
        """
        script = read(DEPLOY)

        for label, what in ((REVISION, "커밋"), (REF_NAME, "브랜치")):
            for command in _build_commands(script):
                found = re.search(rf"{re.escape(label)}=\$\{{(\w+)\}}", command)
                assert found, f"{what} 라벨이 변수를 안 쓴다 — 고정값일 수 있다: {command[:90]}"

                name = found.group(1)
                assigned = re.search(rf"^{name}=\$\((.+?)\)$", script, re.M)
                assert assigned, f"{name} 이 어디서 채워지는지 없다"
                assert "git " in assigned.group(1), f"{what} 를 git 에 안 묻는다 — {name}={assigned.group(1)[:60]}"

    def test_the_branch_label_survives_a_detached_head(self) -> None:
        """`rev-parse --abbrev-ref` 는 detached 에서 문자열 `HEAD` 를 **성공적으로**
        돌려준다 — `|| echo` 가 안 타서 라벨이 조용히 무의미해진다
        (2heej 님 리뷰 ③). `symbolic-ref` 는 그때 실패해서 갈 길을 준다.
        """
        script = read(DEPLOY)

        assert "rev-parse --abbrev-ref HEAD" not in script, (
            "detached 에서 브랜치 이름이 문자열 `HEAD` 가 된다 — symbolic-ref 를 쓴다"
        )
        assert "symbolic-ref" in script, "브랜치를 detached 에서도 옳게 읽지 않는다"

    def test_dirty_looks_only_at_what_lands_in_the_image(self) -> None:
        """저장소 전체를 보면 **빌드에 안 들어가는 잡파일** 하나에도 `-dirty` 가
        붙어, 재현 가능한 빌드인데 겁을 준다 (2heej 님 리뷰 ②).

        세 Dockerfile 의 `COPY` 가 가리키는 자리만 본다.
        """
        script = read(DEPLOY)

        found = re.search(r"^BUILD_CONTEXT_PATHS=\((.+?)\)$", script, re.M)
        assert found, "빌드에 담기는 자리를 안 적었다 — 저장소 전체를 dirty 로 본다"

        paths = set(found.group(1).split())
        assert {"app", "ai_worker", "frontend"} <= paths, f"이미지에 담기는 자리가 빠졌다 — {sorted(paths)}"
        assert 'git status --porcelain -- "${BUILD_CONTEXT_PATHS[@]}"' in script, "dirty 판정이 그 자리를 안 쓴다"

    def test_dirty_also_watches_what_decides_the_build(self) -> None:
        """**굽는 법을 정하는 파일도 봐야 한다** (한금준 님 리뷰 ②).

        `COPY` 가 가리키는 자리만 보면, `infra/nginx/Dockerfile` 의 베이스
        이미지를 커밋 없이 바꿔도 **깨끗한 SHA** 가 박힌다 — 실제 이미지는
        달라졌는데 라벨은 그 커밋이라고 말한다. 출처를 말하라고 붙인 라벨이
        거짓말을 하는 것이라, 없는 것보다 나쁘다.

        `.dockerignore` 는 무엇이 컨텍스트에 들어가고 빠지는지를 정한다.

        **굽는 명령이 실제로 쓰는 Dockerfile 을 세어** 확인한다 — 목록을 손으로
        적으면 네 번째 이미지가 생겼을 때 이 검사가 모른다.
        """
        script = read(DEPLOY)
        listed = re.search(r"^BUILD_CONTEXT_PATHS=\((.+?)\)$", script, re.M)
        assert listed, "빌드에 담기는 자리를 안 적었다 — 검사가 헛돈다"
        paths = set(listed.group(1).split())

        used = set(re.findall(r'"([\w./-]+Dockerfile)"', script))
        assert used, "굽는 명령이 어느 Dockerfile 을 쓰는지 못 읽었다 — 검사가 헛돈다"

        for dockerfile in used:
            covered = dockerfile in paths or any(dockerfile.startswith(one + "/") for one in paths)
            assert covered, f"{dockerfile} 을 고쳐도 -dirty 가 안 붙는다 — {sorted(paths)}"

        assert ".dockerignore" in paths, "컨텍스트에 무엇이 들어갈지 정하는 파일을 안 본다"

    def test_touching_only_the_nginx_dockerfile_marks_it_dirty(self, tmp_path: Path) -> None:
        """**돌려서 확인한다** — 목록에 적혀 있어도 실제로 걸리는지는 다른 문제다.

        저장소와 같은 모양을 세우고 `infra/nginx/Dockerfile` **하나만** 고친 뒤,
        배포 스크립트의 그 판정 덩이를 그대로 돌려 `-dirty` 가 붙는지 본다.
        """
        git = shutil.which("git")
        if git is None:  # pragma: no cover
            pytest.skip("git 이 없다")

        def run_git(*args: str) -> None:
            subprocess.run([git, *args], cwd=tmp_path, capture_output=True, check=True)

        (tmp_path / "infra" / "nginx").mkdir(parents=True)
        (tmp_path / "infra" / "nginx" / "Dockerfile").write_text("FROM nginx:1.27\n", encoding="utf-8")
        (tmp_path / ".dockerignore").write_text(".git\n", encoding="utf-8")
        (tmp_path / "elsewhere.txt").write_text("이미지에 안 담긴다\n", encoding="utf-8")
        run_git("init", "-q", ".")
        run_git("config", "user.email", "probe@example.invalid")
        run_git("config", "user.name", "probe")
        run_git("add", "-A")
        run_git("commit", "-qm", "seed")

        script = read(DEPLOY)
        listed = re.search(r"^BUILD_CONTEXT_PATHS=\((.+?)\)$", script, re.M)
        assert listed, "빌드에 담기는 자리를 안 적었다 — 검사가 헛돈다"
        paths = listed.group(1)
        block = _dirty_block(script)

        def revision_after(touch: Path) -> str:
            touch.write_text(touch.read_text(encoding="utf-8") + "# 손댔다\n", encoding="utf-8")
            probe = (
                "set -eo pipefail\n"
                'COLOR_RED=""\n'
                'COLOR_NC=""\n'
                'SOURCE_REVISION="cafe1234"\n'
                f"BUILD_CONTEXT_PATHS=({paths})\n"
                f"{block}\n"
                'echo "REVISION=$SOURCE_REVISION"\n'
            )
            done = subprocess.run(["bash", "-c", probe], cwd=tmp_path, capture_output=True, text=True)
            assert done.returncode == 0, done.stderr[-400:]
            run_git("checkout", "--", ".")
            return done.stdout

        assert "REVISION=cafe1234-dirty" in revision_after(tmp_path / "infra" / "nginx" / "Dockerfile"), (
            "nginx Dockerfile 만 고쳤는데 깨끗한 SHA 가 박힌다"
        )
        assert "REVISION=cafe1234-dirty" in revision_after(tmp_path / ".dockerignore"), (
            ".dockerignore 만 고쳤는데 깨끗한 SHA 가 박힌다"
        )
        #: **아무 파일이나 걸리면 안 된다** — 그러면 「저장소 전체를 본다」로
        #: 되돌아간 것이고, 이 목록을 둔 뜻이 없어진다.
        assert "REVISION=cafe1234\n" in revision_after(tmp_path / "elsewhere.txt"), (
            "이미지에 안 담기는 파일에도 -dirty 가 붙는다"
        )

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

    def test_the_documented_command_actually_runs(self, tmp_path: Path) -> None:
        """**적어 둔 명령을 돌려 본다** — 읽어서는 인용 부호를 못 잰다.

        이 명령은 셸 두 겹을 지난다: 로컬이 `"` 를 풀고, 원격이 다시 푼다. 그
        사이에서 Go 템플릿의 따옴표가 살아남아야 한다. 눈으로는 안 보인다 —
        실제로 이 검사를 쓰기 전에 **고친다고 손댔다가 오히려 깨뜨렸다**
        (역따옴표를 큰따옴표 안에 두어 로컬 셸이 명령으로 실행했다).

        그래서 `ssh` 를 흉내내 **마지막 인자(원격이 받는 문자열)를 그대로 셸에
        넘긴다.** 라벨은 진짜 이미지에서 읽는다.
        """
        docker = shutil.which("docker")
        if docker is None:
            pytest.skip("docker 가 없다 — 라벨을 읽을 이미지를 못 만든다")

        section = _section("### 도는 것이 어느 커밋인가")
        found = re.search(r"```bash\n(ssh -i.*?)\n```", section, re.S)
        assert found, "런북에 그 명령이 없다 — 검사가 헛돈다"
        command = found.group(1)

        #: **런북은 진짜 서비스 이름을 말해야 한다.** 아래에서 이름을 바꿔 돌리므로,
        #: 그 이름이 맞는지는 여기서 따로 잰다 — 안 그러면 런북이 아무 이름이나
        #: 적어도 검사가 통과한다.
        real = ["fastapi", "ai-worker", "nginx"]
        assert f"for s in {' '.join(real)}" in command, f"런북이 세 서비스를 안 부른다 — {command[:120]}"

        #: **고정 이름으로 안 돌린다.** 처음에는 `fastapi` · `ai-worker` · `nginx`
        #: 그대로 띄우면서 앞에 `docker rm -f` 를 했다 — 같은 판에서 개발용
        #: 컨테이너가 돌고 있으면 **그것을 지운다.** 검사가 남의 것을 부수면
        #: 그것은 검사가 아니다 (한금준 님 리뷰 ①).
        #:
        #: 이름만 바꿔 끼운다. 재려는 것은 인용이지 이름이 아니다.
        mark = uuid.uuid4().hex[:8]
        probes = [f"key315-{mark}-{name}" for name in real]
        image = f"key315-probe:{mark}"
        command = command.replace(f"for s in {' '.join(real)}", f"for s in {' '.join(probes)}")
        command = command.replace("~/.ssh/<키>.pem", "/dev/null").replace("ubuntu@<IP>", "user@host")

        (tmp_path / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
        built = subprocess.run(
            [
                docker,
                "build",
                "-q",
                "--label",
                f"{REVISION}=cafe1234",
                "--label",
                f"{REF_NAME}=develop",
                "-t",
                image,
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        if built.returncode != 0:
            pytest.skip(f"이 판에서 이미지를 못 굽는다:\n{built.stderr[-300:]}")

        #: **치우는 것은 이름이 아니라 내가 만든 id 다.** 이름으로 지우면 그
        #: 사이에 같은 이름이 다른 것을 가리키게 됐을 때 남의 것을 지운다.
        made: list[str] = []
        try:
            for name in probes:
                started = subprocess.run(
                    [docker, "run", "-d", "--rm", "--name", name, image, "sleep", "60"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                made.append(started.stdout.strip())

            #: `ssh` 대신 **마지막 인자를 그대로 실행**한다. `cd ~/project` 는
            #: 서버에만 있는 자리라 여기서는 걷는다 — 재려는 것은 인용이다.
            harness = 'ssh () { printf "%s" "${@: -1}" > cmd.sh; sh cmd.sh; }\n'
            done = subprocess.run(
                ["bash", "-c", harness + command.replace("cd ~/project && \\\n", "")],
                capture_output=True,
                text=True,
                cwd=tmp_path,
            )
        finally:
            for container in made:
                subprocess.run([docker, "rm", "-f", container], capture_output=True)
            subprocess.run([docker, "rmi", "-f", image], capture_output=True)

        for name in probes:
            assert name in done.stdout, f"{name} 줄이 없다 — 명령이 안 돌았다\n{done.stdout}{done.stderr}"
        assert done.stdout.count("cafe1234 (develop)") == len(probes), (
            f"라벨을 못 읽는다 — 인용이 두 겹 셸을 못 지났다\nstdout:\n{done.stdout}\nstderr:\n{done.stderr}"
        )


def _dirty_block(script: str) -> str:
    """`-dirty` 를 붙이는 `if` 덩이만 떼어 온다 — 여는 줄부터 짝 `fi` 까지."""
    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("if [[ -n ") and "git status --porcelain" in line)
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "fi")
    return "\n".join(lines[start : end + 1])


class TestTheDirtyWarningCannotKillTheDeploy:
    """**경고 한 줄이 배포를 죽이면 안 된다.**

    이 스크립트는 `set -eo pipefail` 로 연다. 그 아래에서 `... | head -10` 을
    쓰면, 앞이 파이프 버퍼(64KB)보다 많이 쓸 때 `head` 가 먼저 파이프를 닫아
    앞이 SIGPIPE 로 죽고 `pipefail` 이 141 을 전파한다 — **경고만 찍히고 굽지도
    올리지도 않은 채 배포가 끝난다.**

    한 번 실제로 넣었다. `-dirty` 판정 범위를 좁히면서(리뷰 ②) 미리보기 줄에
    `head` 를 썼고, 2heej 님이 잡아 주셨다. 눈으로는 안 보인다 — **더러운 자리가
    많을 때만** 터지기 때문이다. 그래서 여기서는 읽지 않고 **돌린다.**
    """

    def test_the_guard_finds_the_block(self) -> None:
        """덩이를 못 떼면 아래가 빈 스크립트를 돌리고 조용히 지나간다."""
        block = _dirty_block(read(DEPLOY))
        assert "git status --short" in block, "미리보기 줄이 덩이 안에 없다 — 검사가 헛돈다"
        assert block.endswith("fi"), f"덩이가 `fi` 로 안 끝난다 — 잘못 떼었다\n{block[-120:]}"

    def test_a_big_dirty_tree_does_not_stop_the_deploy(self, tmp_path: Path) -> None:
        """**출력이 파이프 버퍼를 넘겨도 뒤가 이어져야 한다.**

        진짜 저장소를 만들어 추적 파일 수천 개를 고친다 — 상태 출력이 64KB 를
        넘어야 이 자리가 재현된다. 그 위에서 배포 스크립트의 그 덩이를 **그대로**
        `set -eo pipefail` 아래 돌리고, 뒤 줄까지 가는지 본다.

        `head -10` 으로 되돌리면 이 검사가 종료코드 141 로 빨개진다.
        """
        git = shutil.which("git")
        if git is None:  # pragma: no cover - 개발 판에는 늘 있다
            pytest.skip("git 이 없다")

        def run_git(*args: str) -> None:
            subprocess.run([git, *args], cwd=tmp_path, capture_output=True, check=True)

        many = tmp_path / "app" / "many"
        many.mkdir(parents=True)
        # 이름을 길게 둬야 줄 하나가 길어져 적은 파일로도 버퍼를 넘긴다.
        names = [many / f"file_{i:05d}_{'n' * 40}.txt" for i in range(4000)]
        for path in names:
            path.write_text("a", encoding="utf-8")
        run_git("init", "-q", ".")
        run_git("config", "user.email", "probe@example.invalid")
        run_git("config", "user.name", "probe")
        run_git("add", "-A")
        run_git("commit", "-qm", "seed")
        for path in names:
            path.write_text("b", encoding="utf-8")

        status = subprocess.run(
            [git, "status", "--short", "--", "app"], cwd=tmp_path, capture_output=True, text=True, check=True
        )
        assert len(status.stdout) > 65536, (
            f"상태 출력이 {len(status.stdout)}B 뿐이다 — 파이프 버퍼를 안 넘겨 이 검사가 헛돈다"
        )

        block = _dirty_block(read(DEPLOY))
        script = (
            "set -eo pipefail\n"
            'COLOR_RED=""\n'
            'COLOR_NC=""\n'
            'SOURCE_REVISION="cafe1234"\n'
            "BUILD_CONTEXT_PATHS=(app)\n"
            f"{block}\n"
            'echo "REACHED_THE_BUILD"\n'
        )
        done = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True)

        assert done.returncode == 0, (
            f"더러운 자리가 많을 때 배포가 종료코드 {done.returncode} 로 멈춘다 — "
            f"굽기 전에 끝난다\nstdout:\n{done.stdout[-400:]}\nstderr:\n{done.stderr[-400:]}"
        )
        assert "REACHED_THE_BUILD" in done.stdout, (
            f"경고 뒤로 못 간다 — 굽는 자리에 도달 못 했다\nstdout:\n{done.stdout[-400:]}"
        )
