"""배포 문서·설정이 서로 어긋나지 않는가 — KEY-174.

런북(`docs/deploy-runbook.md`)은 **사람이 읽고 그대로 따라 하는 문서**다.
그런데 설정은 코드가 바꾼다. 둘이 어긋나면 문서를 믿고 따라간 사람이
막히는데, 그때는 이미 운영 서버 앞이다.

그래서 문서가 주장하는 것 중 **코드로 잴 수 있는 것**을 여기서 잰다.

여기 나오는 값은 전부 이름과 경로다 — **비밀값을 읽지 않는다.**
"""

import re
from pathlib import Path

import pytest

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
    }
)


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
        placeholder = re.compile(r"^(your[-_]|change[-_]?me|<.*>|xxx+|\.\.\.|example)", re.IGNORECASE)

        leaked = []
        for name in ("envs/example.prod.env", "envs/example.local.env"):
            for line in read(name).splitlines():
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() not in SECRETS:
                    continue
                value = value.strip()
                if value and not placeholder.match(value):
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

    def test_a_real_secret_key_passes(self) -> None:
        from app.core.config import Config, Env

        assert Config(ENV=Env.PROD, DB_PASSWORD="synthetic", SECRET_KEY="synthetic-not-a-default")


class TestTheEnvExampleMatchesWhatTheCodeAsks:
    """예시가 실제 요구보다 짧으면, 그대로 베낀 사람이 서버 앞에서 막힌다."""

    def test_every_setting_is_named_in_the_prod_example(self) -> None:
        from app.core.config import Config

        example = {
            line.split("=", 1)[0]
            for line in read("envs/example.prod.env").splitlines()
            if "=" in line and not line.startswith("#")
        }
        wanted = set(Config.model_fields)

        # `OCR_FIXTURE_FALLBACK` 은 **운영에 있으면 안 된다** — 켜면 서버가 뜨지
        # 않는다. 이름표에 두면 「채워야 하는 것」으로 읽히므로 일부러 뺐고,
        # 주석으로 경고만 적었다.
        missing = wanted - example - {"OCR_FIXTURE_FALLBACK"}

        assert not missing, f"예시에 없는 설정: {sorted(missing)}"

    def test_the_fixture_switch_is_warned_about_instead(self) -> None:
        text = read("envs/example.prod.env")

        assert "OCR_FIXTURE_FALLBACK" in text, "운영에 두면 안 되는 값인데 경고가 없다"
        assert re.search(r"#[^\n]*OCR_FIXTURE_FALLBACK", text), "경고가 주석이 아니다 — 설정처럼 읽힌다"


class TestTheProcedureIsNotMacOnly:
    """「새 환경에서 재현」이 인수조건인데 특정인의 맥에서만 돌면 안 된다."""

    @pytest.mark.parametrize("script", ["scripts/deployment.sh", "scripts/certbot.sh"])
    def test_in_place_edits_go_through_the_portable_helper(self, script: str) -> None:
        text = read(script)
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))

        assert "sed_inplace()" in code, "이식 가능한 헬퍼가 없다"
        assert "sed -i ''" not in code.replace("sed -i '' \"$@\"", ""), "macOS 전용 호출이 남았다"


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
        assert "docker image prune -af" in read("scripts/deployment.sh")

        runbook = read("docs/deploy-runbook.md")
        assert "prune" in runbook, "롤백 전제를 안 적었다"
        assert "APP_VERSION" in runbook

    def test_every_referenced_file_exists(self) -> None:
        """런북이 가리키는 파일이 실제로 있어야 한다."""
        runbook = read("docs/deploy-runbook.md")
        referenced = set(re.findall(r"`((?:infra|scripts|envs|docs|app)/[\w./-]+)`", runbook))
        assert referenced, "참조가 하나도 없다 — 검사가 헛돈다"

        # `envs/.prod.env` 는 **일부러 없다** — 값이 든 파일이라 `.gitignore`
        # 대상이다. 런북이 「이걸 만들어라」고 가리키는 것이 맞다.
        expected_absent = {"envs/.prod.env"}
        missing = sorted(p for p in referenced - expected_absent if not (ROOT / p).exists())
        assert not missing, f"런북이 없는 파일을 가리킨다: {missing}"
