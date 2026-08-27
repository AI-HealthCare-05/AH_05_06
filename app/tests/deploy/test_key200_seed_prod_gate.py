"""**운영 환경 시딩의 문이 얼마나 좁은가** — KEY-200 계약.

`scripts/seed.py` 는 `Staff` · `Patient` · `Visit` 을 실제로 만든다. 진짜 운영 DB
에서 돌면 합성 환자가 섞인다. 그래서 `ENV=prod` 를 막아 두었는데, Pilot 은
「운영처럼 뜨지만 합성 데이터로 도는 환경」이라 그 가드와 정면으로 부딪혔다
(KEY-192 — Pilot DB 가 빈 채로 떠서 `/login` 이 500).

가드를 없애는 대신 **좁은 문 하나**를 냈다. 이 파일은 그 문이 계속 좁은지 잰다.

여기서 재는 것이 세 가지다.

    ⓐ 플래그 없이 ENV=prod           → 종료 1
    ⓑ `.env` 에만 있고 os.environ 엔 없음 → 종료 1
    ⓒ os.environ + 비번 + --mode      → 진행하고 배너를 낸다

**ⓑ 가 이 파일의 존재 이유다.** `Config` 는 `extra="allow"` 라 `.env` 에 적어 둔
아무 이름이나 소문자로 빨아들인다 — 실측하면 `c.seed_allow_prod` ·
`c.model_extra["seed_allow_prod"]` · `c.model_dump()["seed_allow_prod"]` 셋 다
값이 나온다. 그리고 `scripts/deployment.sh:133` 이 `envs/.prod.env` 를 그대로
`~/project/.env` 로 올린다. 즉 구현이 `Config` 를 한 번이라도 쳐다보면, 파일에
한 줄 적힌 플래그가 **배포될 때마다 따라 올라가** 서버에 영구히 켜져 있게 된다.

## 종료 코드만 보면 안 된다

`ENV=prod` 로 `seed.py` 를 돌리면 `Config()` 가 **임포트 시점**에 돌면서
`SECRET_KEY` 와 `DB_PASSWORD` 를 요구한다. 둘을 안 주고 재면

    pydantic_core.ValidationError: DB_PASSWORD 가 비어 있다 …
    종료 코드 1

가 나온다. **가드가 막은 것이 아니라 설정이 터진 것인데 종료 코드는 같다.**
그래서 이 파일은 합성 `SECRET_KEY`·`DB_PASSWORD` 를 반드시 주고, 종료 코드와
함께 **stderr 문구까지** 단언한다. 그러지 않으면 검사가 재는 척만 한다.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "scripts" / "seed.py"

#: `Config()` 가 임포트 시점에 요구하는 값들. **자리표시자 패턴을 피해야 한다** —
#: `your-`·`changeme`·`<`·`xxx`·`example` 로 시작하면 Config 가 거부하고,
#: `default-secret-key` 로 시작해도 거부한다. 그러면 가드에 닿기도 전에 죽는다.
BASE_ENV = {
    "SECRET_KEY": "synthetic-key200-contract-0123456789abcdef",
    "DB_PASSWORD": "synthetic-key200-db",
}

GATE_CLOSED = "운영 환경(ENV=prod)에서는 seed 를 실행할 수 없습니다"
GATE_OPEN = "⚠ ENV=prod 시딩 허용됨 (SEED_ALLOW_PROD) — Pilot/합성 전용"
MODE_REQUIRED = "운영 환경(ENV=prod)에서는 --mode 를 명시해야 합니다"


def run_seed(cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    """`seed.py` 를 **진짜로 돌린다.**

    환경을 통째로 물려주지 않고 **처음부터 조립한다.** 부모 프로세스에 이미
    `SEED_ALLOW_PROD` 가 있으면 ⓐ·ⓑ 가 조용히 통과해 버린다 — 검사가 재는 척만
    하게 되는 자리라 여기서 막는다.

    `cwd` 를 임시 디렉터리로 옮기는 것도 같은 이유다. `Config` 의 `env_file=".env"`
    는 **실행 시점 CWD 기준**이라, 저장소 루트에서 돌리면 개발자 자신의 `.env`
    가 섞여 들어온다.
    """
    clean = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(cwd)),
        "PYTHONPATH": str(ROOT),
        **BASE_ENV,
        **env,
    }
    return subprocess.run(
        [sys.executable, str(SEED), *args],
        cwd=cwd,
        env=clean,
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestTheProdGateStaysNarrow:
    """가드레일 ①~④ — 문이 좁은가."""

    def test_prod_without_the_flag_refuses(self, tmp_path: Path) -> None:
        """ⓐ **플래그가 없으면 안 열린다.**"""
        done = run_seed(tmp_path, "--mode=empty", ENV="prod")

        assert done.returncode == 1, f"prod 인데 통과했다 — stdout={done.stdout!r}"
        assert GATE_CLOSED in done.stderr, f"막히긴 했는데 **가드가 막은 것이 아니다** — stderr={done.stderr[-400:]!r}"

    def test_a_flag_only_in_the_env_file_does_not_open_it(self, tmp_path: Path) -> None:
        """ⓑ **`.env` 에 적어 두는 것으로는 안 열린다** — 가드레일 ①.

        `deployment.sh:133` 이 `envs/.prod.env` 를 `~/project/.env` 로 올리므로,
        파일로 켜지면 배포될 때마다 따라 올라간다. 그 길을 막는다.
        """
        (tmp_path / ".env").write_text("SEED_ALLOW_PROD=1\n", encoding="utf-8")

        done = run_seed(tmp_path, "--mode=empty", ENV="prod")

        assert done.returncode == 1, (
            "`.env` 에 적은 것만으로 문이 열렸다 — 배포 때마다 따라 올라가 서버에 "
            f"영구히 켜진다. stdout={done.stdout!r}"
        )
        assert GATE_CLOSED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    def test_the_flag_in_the_environment_opens_it_and_says_so(self, tmp_path: Path) -> None:
        """ⓒ **`os.environ` 에 있으면 열리고, 열렸다고 크게 알린다.**

        같은 `.env` 를 둔 채로 잰다 — ⓑ 와 갈리는 것이 오직 `os.environ` 하나임을
        보이기 위해서다.
        """
        (tmp_path / ".env").write_text("SEED_ALLOW_PROD=1\n", encoding="utf-8")

        done = run_seed(
            tmp_path,
            "--mode=empty",
            ENV="prod",
            SEED_ALLOW_PROD="1",
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert GATE_CLOSED not in done.stderr, f"열려야 하는데 막혔다 — stderr={done.stderr[-400:]!r}"
        assert GATE_OPEN in done.stderr, (
            f"열리긴 했는데 **배너가 없다** — 로그를 보는 사람이 모른다. stderr={done.stderr[-400:]!r}"
        )

    @pytest.mark.parametrize("value", ["yes", "Y", "2", "0", "false", "", "truthy"])
    def test_only_one_and_true_count(self, tmp_path: Path, value: str) -> None:
        """**대충 참으로 보이는 값**은 안 받는다 — 오타가 열쇠가 되면 안 된다."""
        done = run_seed(tmp_path, "--mode=empty", ENV="prod", SEED_ALLOW_PROD=value)

        assert done.returncode == 1, f"{value!r} 로 문이 열렸다"
        assert GATE_CLOSED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", " 1 "])
    def test_the_documented_values_do_open_it(self, tmp_path: Path, value: str) -> None:
        """반대쪽도 잰다 — **적어 둔 값은 실제로 열려야 한다.**

        이것이 없으면 앞 검사는 「전부 거부」로도 통과한다.
        """
        done = run_seed(
            tmp_path,
            "--mode=empty",
            ENV="prod",
            SEED_ALLOW_PROD=value,
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert GATE_OPEN in done.stderr, f"{value!r} 로 안 열렸다 — stderr={done.stderr[-400:]!r}"


class TestProdMakesYouSayWhatYouAreSeeding:
    """가드레일 ② — 운영에서는 `--mode` 를 손으로 적게 한다."""

    def test_prod_refuses_an_implicit_mode(self, tmp_path: Path) -> None:
        """예전에는 `default="staff"` 라 인자를 안 주면 **조용히 staff 가 돌았다.**

        로컬에서는 편한 기본값이지만, 문을 연 자리에서는 무엇을 부을지 한 번 더
        적어야 한다 — 안 적으면 나중에 무엇이 들어갔는지 아무도 모른다.
        """
        done = run_seed(
            tmp_path,
            ENV="prod",
            SEED_ALLOW_PROD="1",
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert done.returncode == 1, f"--mode 없이 prod 시딩이 시작됐다 — stdout={done.stdout!r}"
        assert MODE_REQUIRED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    def test_local_still_has_its_convenient_default(self, tmp_path: Path) -> None:
        """**로컬은 그대로 둔다.** 없던 불편을 만들지 않는다.

        `--mode` 없이 돌면 `staff` 로 가고, 그래서 비밀번호를 요구하는 자리까지
        간다 — 그 문구가 「기본값이 살아 있다」는 증거다.
        """
        done = run_seed(tmp_path, ENV="local")

        assert MODE_REQUIRED not in done.stderr, f"로컬인데 --mode 를 요구했다 — stderr={done.stderr[-400:]!r}"
        assert "SEED_STAFF_PASSWORD" in done.stderr, f"staff 기본값으로 안 간 것 같다 — stderr={done.stderr[-400:]!r}"


class TestTheDeployScriptNeverSeedsByItself:
    """가드레일 ⑥ — `deployment.sh` 가 seed 를 자동으로 부르지 않는다.

    지금도 안 부른다. 이 검사는 **그대로 있는지** 지킨다 — 「배포하면 알아서
    데이터도 들어가게」 하고 싶은 마음은 자연스럽고, 그 순간 운영 DB 에 합성
    환자가 들어간다.
    """

    def test_deployment_sh_does_not_call_seed(self) -> None:
        body = (ROOT / "scripts" / "deployment.sh").read_text(encoding="utf-8")
        live = "\n".join(line.split("#", 1)[0] for line in body.splitlines())

        assert "seed" not in live, (
            "deployment.sh 가 seed 를 부른다 — 배포가 곧 시딩이 되면 운영 DB 에 "
            "합성 환자가 들어간다. 런북의 수동 단계로 남겨 둔다."
        )


class TestTheRunbookSaysWhatTheCodeDoes:
    """**문서만 고치면 아무도 안 지킨다** — 런북과 코드를 맞대 본다.

    런북에는 이미 이름이 어긋난 자리가 하나 있었다 — 5절이 시딩 비밀번호를
    `SEED_PASSWORD` 라고 불렀는데 `seed.py` 가 읽는 이름은 `SEED_STAFF_PASSWORD`
    다. 그대로 따라 하면 「환경변수가 없습니다」로 막힌다. 그 종류를 막는다.
    """

    RUNBOOK = ROOT / "docs" / "deploy-runbook.md"

    #: KEY-200 이 더한 절의 제목. 이 절**만** 본다.
    SECTION = "## 4-3. 합성 데이터를 붓는다 (KEY-200)"

    @classmethod
    def _section(cls) -> str:
        """**문서 전체가 아니라 이 절만 떼어 낸다.**

        처음에는 `read(RUNBOOK)` 로 문서 전체를 훑었다. 그런데 `envs/.prod.env`
        는 런북 다른 곳에도 여섯 번 나온다 — 이 절의 경고를 통째로 지워도 검사가
        그 여섯을 보고 통과했다. **재는 척만 하는 자리**였다 (같은 종류를 이희진
        님이 `#155` 에서 짚어 주셨다: 전체 텍스트를 보는 검사는 그 줄이 사라져도
        모른다).

        이제 다음 `## ` 제목 전까지만 잘라서 본다.
        """
        prose = cls.RUNBOOK.read_text(encoding="utf-8")
        assert cls.SECTION in prose, f"런북에 「{cls.SECTION}」 절이 없다"

        body = prose.split(cls.SECTION, 1)[1]
        rest = [i for i in (body.find("\n## "),) if i != -1]
        return body[: rest[0]] if rest else body

    def test_the_runbook_uses_the_real_variable_names(self) -> None:
        section = self._section()
        seed = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")

        for name in ("SEED_ALLOW_PROD", "SEED_STAFF_PASSWORD"):
            assert f'"{name}"' in seed, f"{name} 이 seed.py 에 없다"
            assert name in section, f"4-3 절이 {name} 을 안 알려 준다"

        # 이름 오기는 문서 **전체**에서 없어야 한다 — 5절에 있던 것이 그랬다.
        whole = self.RUNBOOK.read_text(encoding="utf-8")
        assert "`SEED_PASSWORD`" not in whole, "런북이 `SEED_PASSWORD` 라는 없는 이름을 쓴다 — 그대로 따라 하면 막힌다"

    def test_the_runbook_warns_against_putting_the_flag_in_a_file(self) -> None:
        """가드레일 ⑤ — 이 경고가 사라지면 누군가 `.env` 에 적는다."""
        section = self._section()

        assert "명령줄" in section, "4-3 절에 「명령줄에」라는 말이 없다"
        assert "envs/.prod.env" in section, (
            "4-3 절이 `envs/.prod.env` 를 짚지 않는다 — deployment.sh 가 그 파일을 "
            "서버로 나르므로, 거기 적으면 배포마다 따라 올라간다"
        )
        assert "~/project/.env" in section, "4-3 절이 서버 쪽 `.env` 를 안 짚는다"

    def test_the_runbook_lists_the_values_that_actually_work(self) -> None:
        """적어 둔 값과 코드가 받는 값이 같아야 한다."""
        section = self._section()
        seed = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")

        line = next(ln for ln in seed.splitlines() if "SEED_ALLOW_PROD_TRUE = " in ln)
        accepted = {piece.strip().strip("\"'") for piece in line.split("{", 1)[1].rstrip("})").split(",")}

        assert accepted == {"1", "true"}, f"코드가 받는 값이 바뀌었다 — {accepted}"
        for value in accepted:
            assert f"`{value}`" in section, f"4-3 절이 `{value}` 를 안 적었다"
