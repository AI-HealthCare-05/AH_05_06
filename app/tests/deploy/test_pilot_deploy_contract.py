"""배포 문서·설정이 서로 어긋나지 않는가 — KEY-174.

런북(`docs/deploy-runbook.md`)은 **사람이 읽고 그대로 따라 하는 문서**다.
그런데 설정은 코드가 바꾼다. 둘이 어긋나면 문서를 믿고 따라간 사람이
막히는데, 그때는 이미 운영 서버 앞이다.

그래서 문서가 주장하는 것 중 **코드로 잴 수 있는 것**을 여기서 잰다.

여기 나오는 값은 전부 이름과 경로다 — **비밀값을 읽지 않는다.**
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from app.core.config import PLACEHOLDER

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs" / "deploy-runbook.md"

#: 값이 새면 안 되는 것들. 나머지(호스트·포트·시간대 …)는 적어 두는 편이 낫다.
SECRETS = frozenset(
    {
        "SECRET_KEY",
        "DB_PASSWORD",
        "DB_ROOT_PASSWORD",
        "COOKIE_DOMAIN",
        "PATIENT_OTP_SECRET",
        "OPENAI_API_KEY",
    }
)


def run_bash(script: str, *, cwd: Path, stub_dir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """스크립트를 **진짜로 돌린다.**

    `FUNCNEST` 를 걸어 두는 이유가 있다 — 재귀로 잘못 짠 헬퍼는 문자열 검사로는
    안 잡히고, 그냥 돌리면 **검사가 멈춘 것처럼 보인다.** 여기서는 빠르게
    죽어서 실패로 드러나야 한다.
    """
    env_all = dict(os.environ, PATH=f"{stub_dir}:{os.environ['PATH']}", FUNCNEST="40", **env)
    return subprocess.run(["bash", "-c", script], cwd=cwd, env=env_all, capture_output=True, text=True, timeout=30)


def write_stub(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / name
    stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    stub.chmod(0o755)
    return stub


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_the_runbook_exists() -> None:
    """**이 파일의 다른 검사가 조용히 통과하지 않게 한다.**"""
    assert RUNBOOK.exists(), "런북이 없다 — 아래 검사가 전부 헛돈다"
    assert len(RUNBOOK.read_text(encoding="utf-8")) > 2000


class TestSecretsNeverReachTheScreen:
    """PAT 이 화면·프로세스 목록에 안 남는가 — 인수조건이다."""

    def test_the_pat_prompt_is_hidden(self) -> None:
        """예전에는 `read -p` 라 입력이 그대로 찍혔다."""
        script = read("scripts/deployment.sh")

        assert re.search(r"read\s+-r\s+-s\s+-p[^\n]*DOCKER_PAT", script), "PAT 입력이 화면에 보인다"

    def test_docker_login_does_not_take_the_password_as_an_argument(self) -> None:
        """`docker login -p` 는 경고를 내고 `ps` 에 값이 남는다."""
        script = read("scripts/deployment.sh")

        assert "--password-stdin" in script, "비밀번호를 표준입력으로 안 넘긴다"
        assert not re.search(r"docker login[^\n|]*\s-p\s", script), "비밀번호를 명령줄 인자로 넘긴다"

    def test_the_env_file_is_locked_down_right_after_it_lands(self) -> None:
        """`.env` 를 올린 **직후에** 잠근다 — 한금준 님 `#133` 보안 확인.

        `scp` 는 로컬 파일의 권한을 그대로 안 옮긴다. 기본 umask 로 떨어지면
        그 서버의 다른 계정이 읽을 수 있는데, 이 파일에는 `DB_PASSWORD` 와
        `SECRET_KEY` 가 들어 있다.

        **순서를 함께 잰다.** 나중에 잠그면 그 사이가 열려 있고, 배포가 중간에
        끊기면 열린 채로 남는다.
        """
        script = read("scripts/deployment.sh")

        landed = script.index("ubuntu@${ec2_ip}:~/project/.env")
        locked = script.find("chmod 600 ~/project/.env")

        assert locked != -1, "`.env` 를 올려 놓고 잠그지 않는다"
        assert landed < locked, "잠그고 나서 올린다 — 그 사이가 열려 있다"
        # 「바로 다음 줄인가」까지 재려다 **주석 안의 `scp` 라는 글자**에 걸렸다.
        # 그건 과한 단정이라 걷었다 — 순서가 지켜지면 뜻은 이미 지켜진다.

    def test_the_pat_is_not_passed_through_the_ssh_command_line(self) -> None:
        """`ssh "DOCKER_PAT=… bash -s"` 는 **원격의 `ps` 에 남는다.**"""
        script = read("scripts/deployment.sh")
        ssh_block = script[script.index("ssh -i") :]

        assert "DOCKER_PAT=${docker_pw}" not in ssh_block, "PAT 이 ssh 명령줄에 실렸다"

    def test_no_secret_value_lives_in_the_repository(self) -> None:
        """예시 파일은 **이름표**다 — 진짜 값이 들어가면 공개 저장소에 비밀이 생긴다.

        빈칸을 요구하지는 않는다. `your-db-password` 같은 자리표시자는 「여기에
        무엇을 넣는지」를 알려 주는 값이라 오히려 도움이 된다. **재는 것은
        「진짜처럼 보이는 값이 있는가」다.**

        자리표시자는 사람이 보면 바로 안다 — `your-…`·`change-me`·`<…>`.
        그 모양이 아닌 값이 비밀 칸에 있으면 실수로 커밋한 것으로 본다.
        """
        leaked = []
        for name in ("envs/example.prod.env", "envs/example.local.env"):
            for line in read(name).splitlines():
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() not in SECRETS:
                    continue
                value = value.strip()
                if value and not PLACEHOLDER.match(value):
                    leaked.append(f"{name}:{key.strip()}")

        assert not leaked, f"비밀 칸에 진짜처럼 보이는 값이 있다: {leaked}"


class TestTheServerRefusesToStartQuietly:
    """설정을 빠뜨리면 **이름을 대며 멈춘다** — 조용히 뜨지 않는다."""

    @pytest.mark.parametrize("env", ["prod", "dev"])
    def test_a_missing_secret_key_stops_the_server(self, env: str) -> None:
        from app.core.config import Config, Env

        with pytest.raises(ValueError, match="SECRET_KEY"):
            Config(ENV=Env(env), DB_PASSWORD="synthetic", SECRET_KEY="default-secret-key-abcdef")

    def test_local_still_starts_without_one(self) -> None:
        """로컬까지 막으면 아무도 못 띄운다 — 여기는 그대로 둔다."""
        from app.core.config import Config, Env

        assert Config(ENV=Env.LOCAL, DB_PASSWORD="synthetic", SECRET_KEY="default-secret-keyabc")

    @pytest.mark.parametrize(
        "placeholder", ["your-jwt-secret-key-here", "change-me-to-a-real-random-secret", "<SECRET>"]
    )
    def test_the_example_placeholder_also_stops_the_server(self, placeholder: str) -> None:
        """**빈칸보다 자리표시자가 더 위험하다.**

        `DB_PASSWORD` 는 안 채우면 바로 티가 난다. 그런데 `SECRET_KEY` 는 예시에
        값이 적혀 있어서 「이미 뭔가 들어 있다」로 읽히고, 그대로 뜬 서버는
        **공개 저장소에 적힌 값으로 JWT 를 서명한다** (이희진 님 `#133` 리뷰).
        """
        from app.core.config import Config, Env

        with pytest.raises(ValueError, match="SECRET_KEY"):
            Config(ENV=Env.PROD, DB_PASSWORD="synthetic", SECRET_KEY=placeholder)

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_blank_secret_key_stops_the_server(self, blank: str) -> None:
        """**빈 값으로도 뜨고 있었다.**

        `default-secret-key…` 와 자리표시자만 막고 있었더니, `SECRET_KEY=` 로
        비워 둔 `.env` 는 그대로 통과했다. 빈 문자열로 서명한 JWT 는 누구나
        위조한다 — 기본값보다 나쁘다 (KEY-174).
        """
        from app.core.config import Config, Env

        with pytest.raises(ValueError, match="SECRET_KEY"):
            Config(ENV=Env.PROD, DB_PASSWORD="synthetic", SECRET_KEY=blank)

    def test_the_prod_example_would_be_caught_by_that_guard(self) -> None:
        """예시 파일에 적힌 값이 **실제로** 가드에 걸리는지 — 값을 직접 가져와 잰다."""
        from app.core.config import Config, Env

        written = next(
            line.partition("=")[2].strip()
            for line in read("envs/example.prod.env").splitlines()
            if line.startswith("SECRET_KEY=")
        )
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Config(ENV=Env.PROD, DB_PASSWORD="synthetic", SECRET_KEY=written)

    def test_a_real_secret_key_passes(self) -> None:
        from app.core.config import Config, Env

        assert Config(ENV=Env.PROD, DB_PASSWORD="synthetic", SECRET_KEY="synthetic-not-a-default")


class TestTheEnvExampleMatchesWhatTheCodeAsks:
    """예시가 실제 요구보다 짧으면, 그대로 베낀 사람이 서버 앞에서 막힌다."""

    def test_every_setting_is_named_in_the_prod_example(self) -> None:
        from app.core.config import Config

        # **주석도 이름표다.** 어떤 설정은 값을 넣는 것보다 「줄을 두지 않는
        # 것」이 맞다 — `OPENAI_API_KEY` 는 빈 값이면 `SecretStr("")` 이 되어
        # LLM 호출이 켜진 채 빈 키로 나가고, `OCR_FIXTURE_FALLBACK` 은 운영에
        # 있으면 서버가 아예 안 뜬다. 그래도 **이름은 보여야** 베낀 사람이
        # 그런 설정이 있다는 걸 안다. 그래서 주석까지 훑는다.
        #
        # 예외 목록을 두지 않는 이유가 이것이다 — 예외는 계속 늘어나고, 늘어난
        # 뒤에는 아무도 안 본다.
        example = {
            line.lstrip("# ").split("=", 1)[0].strip()
            for line in read("envs/example.prod.env").splitlines()
            if "=" in line
        }
        missing = set(Config.model_fields) - example

        assert not missing, f"예시에 이름조차 없는 설정: {sorted(missing)}"

    def test_the_fixture_switch_is_warned_about_instead(self) -> None:
        text = read("envs/example.prod.env")

        assert "OCR_FIXTURE_FALLBACK" in text, "운영에 두면 안 되는 값인데 경고가 없다"
        assert re.search(r"#[^\n]*OCR_FIXTURE_FALLBACK", text), "경고가 주석이 아니다 — 설정처럼 읽힌다"


class TestTheProcedureIsNotMacOnly:
    """「새 환경에서 재현」이 인수조건인데 특정인의 맥에서만 돌면 안 된다.

    **여기서는 문자열을 보지 않고 돌려 본다.** 예전 판은 `"sed_inplace()" in
    code` 만 봤는데, 그 검사는 헬퍼가 **자기 자신을 부르고 있어도 통과했다** —
    실제로 그 상태로 올라갔고 맥에서는 무한 재귀로 죽었다 (이희진 님 `#133`
    리뷰). 있는지가 아니라 **맞게 부르는지**를 재야 한다.
    """

    @pytest.mark.parametrize("script", ["scripts/deployment.sh", "scripts/certbot.sh"])
    def test_the_scripts_take_the_helper_from_one_place(self, script: str) -> None:
        """복제해 두면 한쪽만 고치게 된다 — 실제로 양쪽에 같은 버그가 있었다."""
        code = "\n".join(line for line in read(script).splitlines() if not line.lstrip().startswith("#"))

        assert "lib.sh" in code, "공용 조각을 안 가져온다"
        assert "sed_inplace()" not in code, f"{script} 가 헬퍼를 또 정의한다 — lib.sh 한 곳에만 둔다"

    @pytest.mark.parametrize(
        ("flavour", "probe", "expected"),
        [
            ("GNU", 'echo "sed (GNU sed) 4.9"; exit 0', ["-i", "s/a/b/", "target.conf"]),
            ("BSD", 'echo "sed: illegal option" >&2; exit 1', ["-i", "", "s/a/b/", "target.conf"]),
        ],
    )
    def test_the_helper_calls_sed_the_way_each_platform_wants(
        self, flavour: str, probe: str, expected: list[str], tmp_path: Path
    ) -> None:
        """BSD 는 `-i` 뒤에 **백업 확장자를 반드시** 요구한다 — 빈 문자열을 낀다."""
        log = tmp_path / "argv.txt"
        write_stub(
            tmp_path / "bin",
            "sed",
            f"""if [ "$1" = "--version" ]; then {probe}; fi
printf '%s\\n' "$@" >> "{log}"
""",
        )

        done = run_bash(
            f'source "{ROOT}/scripts/lib.sh"; sed_inplace "s/a/b/" target.conf',
            cwd=tmp_path,
            stub_dir=tmp_path / "bin",
        )

        assert log.exists(), (
            f"{flavour}: sed 가 한 번도 안 불렸다 — 헬퍼가 자기 자신을 부르고 있다"
            f" (stderr: {done.stderr.strip()[:200]})"
        )
        assert log.read_text(encoding="utf-8").split("\n")[: len(expected)] == expected, (
            f"{flavour} 에서 sed 를 틀리게 부른다"
        )
        assert done.returncode == 0, done.stderr


class TestThePatReachesDockerAndNothingElse:
    """PAT 를 감추려던 구조가 **오히려 노출하고 배포를 막고 있었다** — `#133` 리뷰.

    `bash -s` 는 stdin 을 스크립트로 읽는다. 예전 판은 PAT 를 스크립트보다 먼저
    한 줄로 얹어서, bash 가 그 줄을 **명령으로 실행하려다 stderr 에 그대로
    찍고**, 뒤의 `read` 는 PAT 대신 다음 스크립트 줄을 삼켰다.

    그래서 여기서는 **payload 를 진짜로 `bash -s` 에 물려 본다.**
    """

    PAT = "SYNTHETIC-PAT-NOT-A-REAL-TOKEN"

    def _deploy(self, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
        seen = tmp_path / "login-stdin.txt"
        write_stub(
            tmp_path / "bin",
            "docker",
            f"""if [ "$1" = "login" ]; then cat > "{seen}"; exit 0; fi
echo "docker $*"
""",
        )
        (tmp_path / "project").mkdir(exist_ok=True)

        done = run_bash(
            f'source "{ROOT}/scripts/lib.sh"; remote_deploy_payload "{self.PAT}" | bash -s',
            cwd=tmp_path,
            stub_dir=tmp_path / "bin",
            DOCKER_USERNAME="synthetic-user",
            DEPLOY_SERVICES="api nginx",
        )
        return done, seen

    def test_docker_login_receives_exactly_the_pat(self, tmp_path: Path) -> None:
        done, seen = self._deploy(tmp_path)

        assert seen.exists(), f"docker login 이 아예 안 불렸다 — {done.stderr.strip()[:300]}"
        assert seen.read_text(encoding="utf-8") == self.PAT, "login 이 PAT 아닌 것을 받았다"

    def test_the_deploy_actually_continues_past_login(self, tmp_path: Path) -> None:
        """예전 구조에서는 `set -e` 에 걸려 여기까지 오지도 못했다."""
        done, _ = self._deploy(tmp_path)

        assert "compose up -d --pull always" in done.stdout, f"배포가 중간에 끊겼다 — {done.stdout}"
        assert "image prune -af" in done.stdout, "옛 이미지 정리까지 못 갔다"

    def test_the_pat_never_shows_up_in_the_output(self, tmp_path: Path) -> None:
        """`bash: line 1: <PAT>: command not found` 로 새던 자리다."""
        done, _ = self._deploy(tmp_path)

        assert self.PAT not in done.stderr, "PAT 이 stderr 로 샜다"
        assert self.PAT not in done.stdout, "PAT 이 stdout 으로 샜다"


class TestTheExampleEnvActuallyBoots:
    """런북 0단계를 **그대로 따라 하면 뜨는가.**

    빈 칸으로 둔 정수 넷 때문에 `cp` 하고 두 칸만 채운 사람은 pydantic 검증에서
    막혔다. 「기본값이 있어 비워도 뜬다」고 적어 뒀지만 사실이 아니었다
    (이희진 님 `#133` 리뷰). 이름만 대조하던 검사로는 안 잡혔다.
    """

    def test_filling_only_the_two_required_blanks_is_enough(self) -> None:
        from app.core.config import Config

        values = {}
        for line in read("envs/example.prod.env").splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() in Config.model_fields:
                values[key.strip()] = value.strip()  # 빈 값도 그대로 넘긴다

        values["SECRET_KEY"] = "synthetic-random-value-for-this-check"
        values["DB_PASSWORD"] = "synthetic"

        # `.env` 에서 온 값은 전부 문자열이다 — pydantic 이 변환하는 것이 요점이라
        # 여기서는 그대로 넘긴다.
        assert Config(**values), "예시를 그대로 베끼면 서버가 안 뜬다"  # type: ignore[arg-type]


class TestTheRunbookTellsTheTruth:
    """문서가 주장하는 것 중 **코드로 잴 수 있는 것**을 잰다."""

    def test_it_admits_the_frontend_is_not_served_in_prod(self) -> None:
        """**아직 못 하는 것을 못 한다고 적었는가.**

        이게 이 검사의 핵심이다. 운영 nginx 가 `/` 를 404 로 막고 있어서
        「공유 가능한 URL」을 줘도 볼 화면이 없다. 문서가 그걸 감추면 형제
        일감들이 없는 환경 위에 계획을 세운다.
        """
        for conf in ("infra/nginx/prod_http.conf", "infra/nginx/prod_https.conf"):
            assert re.search(r"location\s+/\s*\{\s*return\s+404", read(conf)), (
                f"{conf} 가 이제 `/` 를 준다 — 런북의 「아직 못 하는 것」을 고칠 때다"
            )

        runbook = read("docs/deploy-runbook.md")
        assert "아직 못 하는 것" in runbook
        assert "return 404" in runbook, "런북이 이 제약을 안 적었다"

    def test_it_names_the_rollback_precondition(self) -> None:
        """되돌림은 **Hub 에 옛 태그가 남아 있을 때만** 된다.

        배포 스크립트가 EC2 에서 `docker image prune -af` 를 돌리므로 로컬
        캐시로는 못 되돌린다. 그 전제를 안 적으면 롤백하려다 못 한다.
        """
        assert "docker image prune -af" in read("scripts/lib.sh")

        runbook = read("docs/deploy-runbook.md")
        assert "prune" in runbook, "롤백 전제를 안 적었다"
        assert "APP_VERSION" in runbook

    def test_the_runbook_carries_the_smoke_command(self) -> None:
        """「런북에서 실행 명령을 찾을 수 있음」이 KEY-184 인수조건이다.

        실행기만 있고 문서에 없으면, 배포하는 사람이 그것이 있는 줄 모른다.
        **게이트로 쓰는 법까지** 적혀 있어야 배포·CI 가 그대로 붙인다.
        """
        runbook = read("docs/deploy-runbook.md")

        assert "scripts/smoke.py" in runbook, "실행기를 가리키지 않는다"
        for name in ("SMOKE_LOGIN_ID", "SMOKE_PASSWORD"):
            assert name in runbook, f"{name} 를 어디서 주는지 안 적었다"
        assert re.search(r"scripts/smoke\.py[^\n]*(\|\||\$\?)", runbook), (
            "실패했을 때 멈추는 법이 없다 — 게이트로 못 쓴다"
        )

    def test_every_referenced_file_exists(self) -> None:
        """런북이 가리키는 파일이 실제로 있어야 한다."""
        runbook = read("docs/deploy-runbook.md")

        # **백틱 안만 보면 안 된다.** 예전 판은 홑백틱만 찾아서 6절 「아직 못
        # 하는 것」이 통째로 사각지대였다 — 파일 목록이 코드블록 안에 있어
        # 하나도 안 걸렸다. 이 문서에서 **가장 정직해야 하는 구간**이 검사 밖에
        # 있었던 셈이다 (이희진 님 `#133` 리뷰).
        referenced = {path.rstrip(".,)") for path in re.findall(r"(?:infra|scripts|envs|docs|app)/[\w./-]+", runbook)}
        assert referenced, "참조가 하나도 없다 — 검사가 헛돈다"

        # 6절이 실제로 걸리는지 못 박는다. 이게 없으면 정규식이 다시 좁아져도
        # 조용히 통과한다.
        assert "infra/nginx/prod_http.conf" in referenced, "6절 코드블록이 여전히 안 보인다"

        # `envs/.prod.env` 는 **일부러 없다** — 값이 든 파일이라 `.gitignore`
        # 대상이다. 런북이 「이걸 만들어라」고 가리키는 것이 맞다.
        expected_absent = {"envs/.prod.env"}
        missing = sorted(p for p in referenced - expected_absent if not (ROOT / p).exists())
        assert not missing, f"런북이 없는 파일을 가리킨다: {missing}"
