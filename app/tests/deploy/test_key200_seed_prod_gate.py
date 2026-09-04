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

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.tests.deploy.conftest import compose

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "scripts" / "seed.py"

#: `Config()` 가 임포트 시점에 요구하는 값들. **자리표시자 패턴을 피해야 한다** —
#: `your-`·`changeme`·`<`·`xxx`·`example` 로 시작하면 Config 가 거부하고,
#: `default-secret-key` 로 시작해도 거부한다. 그러면 가드에 닿기도 전에 죽는다.
BASE_ENV = {
    "SECRET_KEY": "synthetic-key200-contract-0123456789abcdef",
    "DB_PASSWORD": "synthetic-key200-db",
}


def _func_in(source: str, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    """소스에서 그 이름의 함수 노드를 찾는다."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 을 못 찾았다")


GATE_CLOSED = "운영 환경(ENV=prod)에서는 seed 를 실행할 수 없습니다"
GATE_OPEN = "⚠ ENV=prod 시딩 허용됨 (SEED_ALLOW_PROD + --allow-prod-seed) — Pilot/합성 전용"

#: 이번 실행에 사람이 직접 적어야 생기는 것. `env_file` 은 이것을 못 만든다.
ALLOW_ARGV = "--allow-prod-seed"
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
        """ⓑ **호스트에서 `.env` 에 적어 두는 것으로는 안 열린다** — 가드레일 ①.

        `deployment.sh:133` 이 `envs/.prod.env` 를 `~/project/.env` 로 올리므로,
        파일로 켜지면 배포될 때마다 따라 올라간다. 그 길을 막는다.

        **여기서 재는 것은 호스트에서 직접 돌릴 때뿐이다.** 컨테이너 안은 다르다 —
        `docker-compose.prod.yml` 이 `env_file: .env` 를 쓰므로 도커가 그 값을
        **진짜 환경변수로** 실어 준다. 파이썬이 시작하기 전 일이라 `os.environ` 만
        보는 가드로는 구별할 수 없고, 그 경우엔 **열린다**.

        한금준 님이 `#158` 에서 짚었고 재현했다. 아래 검사가 그 사실을 못박는다 —
        이 검사만 보고 「파일로는 절대 안 열린다」고 읽지 말라는 뜻이다.
        """
        (tmp_path / ".env").write_text("SEED_ALLOW_PROD=1\n", encoding="utf-8")

        done = run_seed(tmp_path, "--mode=empty", ENV="prod")

        assert done.returncode == 1, (
            "`.env` 에 적은 것만으로 문이 열렸다 — 배포 때마다 따라 올라가 서버에 "
            f"영구히 켜진다. stdout={done.stdout!r}"
        )
        assert GATE_CLOSED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    def test_the_prod_containers_hand_the_env_file_to_the_process(self) -> None:
        """**위 검사가 못 재는 자리를 사실로 적어 둔다** — 한금준 님 `#158`.

        운영 compose 가 `env_file: .env` 를 쓰는 한, 서버 `.env` 에 적힌
        `SEED_ALLOW_PROD` 는 컨테이너의 `os.environ` 에 그대로 들어온다.
        가드가 못 막는다.

        재현(2026-08-28):

            .env: SEED_ALLOW_PROD=1  →  컨테이너에서 os.environ.get(...) == "1"

        이 사실이 바뀌면 — 누가 `env_file` 을 걷어내면 — 이 검사가 울고,
        런북의 설명도 함께 고치게 된다. 지금은 규칙(런북)으로만 막고 있고,
        코드로 막을지는 팀 합의 뒤에 정한다.
        """
        prod = compose("infra/docker/docker-compose.prod.yml")
        carriers = {name: svc.get("env_file") for name, svc in prod["services"].items() if svc.get("env_file")}

        assert carriers, (
            "운영 compose 에 `env_file` 이 하나도 없다 — 그렇다면 런북의 "
            "「파일에 적으면 서버에서는 켜진다」 설명이 낡았다. 함께 고쳐라"
        )
        assert "fastapi" in carriers, f"시드를 돌리는 서비스가 `env_file` 을 안 쓴다 — 설명을 다시 보라: {carriers}"

    def test_the_environment_variable_alone_does_not_open_it(self, tmp_path: Path) -> None:
        """ⓒ **환경변수만으로는 안 열린다** — 가드레일 ① 개정.

        예전 판은 여기서 열렸다. 그게 결함이었다.

        `os.environ` 에 값이 있다는 것은 「사람이 이번에 명령줄에 적었다」를
        **뜻하지 않는다.** 운영 compose 가 `env_file: .env` 를 쓰므로, 서버
        `.env` 에 한 줄 적혀 있기만 하면 도커가 그 값을 진짜 환경변수로 실어
        준다. 파이썬이 시작하기 전 일이라 출처를 구별할 수가 없다.

        실제로 재현했다 — 서버 `.env` 에 적고 `--force-recreate` 한 뒤
        명령줄에 아무것도 안 붙이고 돌렸더니 문이 열렸다.
        """
        done = run_seed(
            tmp_path,
            "--mode=empty",
            ENV="prod",
            SEED_ALLOW_PROD="1",
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert done.returncode == 1, (
            "환경변수 하나로 문이 열렸다 — 서버 `.env` 에 적어 두면 배포 때마다 "
            f"따라 올라가 영구히 켜진다. stdout={done.stdout!r}"
        )
        assert GATE_CLOSED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    def test_the_command_line_flag_alone_does_not_open_it(self, tmp_path: Path) -> None:
        """ⓓ **명령줄 인자만으로도 안 열린다.**

        argv 는 위조가 어렵지만, 그것 하나로 여는 것은 문을 넓히는 일이다.
        환경변수는 「이 서버가 Pilot 이다」를 뜻하고, argv 는 「이번 실행을
        사람이 뜻했다」를 뜻한다. 둘은 다른 것을 증명하므로 둘 다 받는다.
        """
        done = run_seed(
            tmp_path,
            "--mode=empty",
            ALLOW_ARGV,
            ENV="prod",
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert done.returncode == 1, f"명령줄 인자 하나로 문이 열렸다 — stdout={done.stdout!r}"
        assert GATE_CLOSED in done.stderr, f"stderr={done.stderr[-400:]!r}"

    def test_both_together_open_it_and_say_so(self, tmp_path: Path) -> None:
        """ⓔ **둘 다 있어야 열리고, 열렸다고 크게 알린다.**

        `.env` 를 둔 채로 잰다 — ⓑ 와 갈리는 것이 무엇인지 보이게.
        """
        (tmp_path / ".env").write_text("SEED_ALLOW_PROD=1\n", encoding="utf-8")

        done = run_seed(
            tmp_path,
            "--mode=empty",
            ALLOW_ARGV,
            ENV="prod",
            SEED_ALLOW_PROD="1",
            SEED_STAFF_PASSWORD="synthetic-key200-staff",
        )

        assert GATE_CLOSED not in done.stderr, f"둘 다 줬는데 막혔다 — stderr={done.stderr[-400:]!r}"
        assert GATE_OPEN in done.stderr, (
            f"열리긴 했는데 **배너가 없다** — 로그를 보는 사람이 모른다. stderr={done.stderr[-400:]!r}"
        )

    def test_the_gate_needs_the_argv_that_a_file_cannot_forge(self) -> None:
        """**왜 argv 인가** — 이 이유가 흐려지면 다음 사람이 되돌린다.

        가드가 `sys.argv` 를 봐야 한다. `Config` 나 `.env` 를 보면 같은 구멍이
        다시 생긴다. 코드가 실제로 무엇을 읽는지 구문 나무로 확인한다.
        """
        tree = ast.parse(SEED.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_prod_override_granted")
        body = ast.dump(fn)

        assert "argv" in body, "가드가 argv 를 안 본다 — 파일에서 온 값과 구별할 수가 없다"
        assert "environ" in body, "가드가 환경변수를 안 본다"
        assert "_CONFIG" not in body, "가드가 `Config` 를 본다 — `.env` 가 다시 새어 든다"

    @pytest.mark.parametrize("value", ["yes", "Y", "2", "0", "false", "", "truthy"])
    def test_only_one_and_true_count(self, tmp_path: Path, value: str) -> None:
        """**대충 참으로 보이는 값**은 안 받는다 — 오타가 열쇠가 되면 안 된다."""
        done = run_seed(tmp_path, "--mode=empty", ALLOW_ARGV, ENV="prod", SEED_ALLOW_PROD=value)

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
            ALLOW_ARGV,
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
        """적어 둔 값과 코드가 받는 값이 같아야 한다.

        값 집합은 이제 app/core/utils/narrow_gate.py 에 하나만 있다(KEY-264
        리뷰 반영) — seed.py 는 그 값을 그대로 가져다 쓴다.
        """
        section = self._section()
        narrow_gate = (ROOT / "app" / "core" / "utils" / "narrow_gate.py").read_text(encoding="utf-8")

        line = next(ln for ln in narrow_gate.splitlines() if "TRUE_VALUES = " in ln)
        accepted = {piece.strip().strip("\"'") for piece in line.split("{", 1)[1].rstrip("})").split(",")}

        assert accepted == {"1", "true"}, f"코드가 받는 값이 바뀌었다 — {accepted}"
        for value in accepted:
            assert f"`{value}`" in section, f"4-3 절이 `{value}` 를 안 적었다"


class TestTheRunbookCommandCanActuallyRun:
    """**문서에 적힌 명령이 서버에서 실제로 도는가.**

    처음에 적었던 것은 못 도는 명령이었다.

        docker compose exec -T fastapi uv run python scripts/seed.py --mode full

    세 군데가 틀렸다. 로컬에서 그대로 밟아 보고 하나씩 잡았다.

        scripts/seed.py 가 이미지에 없다   app/Dockerfile 은 pyproject·uv.lock·./app 셋만
                                          복사한다 → `ls: cannot access '/app/scripts/seed.py'`
        환경변수가 안 넘어간다              `docker compose exec` 는 호스트 값을 자동으로
                                          안 준다 → `-e NAME` 이 필요하다
        `python` 이 시스템 파이썬이다       → `ModuleNotFoundError: No module named 'tortoise'`

    문서만 읽고 따라 하는 사람이 시연 당일에 이 셋을 차례로 밟게 둘 수는 없다.
    """

    RUNBOOK = ROOT / "docs" / "deploy-runbook.md"
    SECTION = "## 4-3. 합성 데이터를 붓는다 (KEY-200)"

    @classmethod
    def _section(cls) -> str:
        prose = cls.RUNBOOK.read_text(encoding="utf-8")
        assert cls.SECTION in prose, f"런북에 「{cls.SECTION}」 절이 없다"
        body = prose.split(cls.SECTION, 1)[1]
        cut = body.find("\n## ")
        return body[:cut] if cut != -1 else body

    def test_the_app_image_really_does_not_carry_the_seed_script(self) -> None:
        """이 절의 전제가 아직 사실인가.

        누가 `app/Dockerfile` 에 `COPY ./scripts` 를 더하면 이 절의 설명이 낡는다.
        그때 이 검사가 먼저 운다.
        """
        dockerfile = (ROOT / "app" / "Dockerfile").read_text(encoding="utf-8")
        copied = [ln.split()[1] for ln in dockerfile.splitlines() if ln.startswith("COPY ") and "--from" not in ln]

        assert not any("scripts" in c for c in copied), (
            f"app 이미지가 이제 scripts 를 담는다 — 런북 4-3 절의 `docker cp` 설명이 낡았다. {copied}"
        )

    def test_it_creates_the_directory_before_copying(self) -> None:
        """`docker cp` 는 대상 디렉터리를 안 만든다 — 없으면 죽는다."""
        section = "\n".join(self._bash())
        assert "mkdir -p /app/scripts" in section, (
            "`docker cp` 앞에 `mkdir` 이 없다 — 「Could not find the file /app/scripts」로 죽는다"
        )

    def test_it_passes_the_environment_through(self) -> None:
        """**`seed.py` 를 부르는 블록마다** 확인한다.

        처음에는 4-3 절의 bash 를 통째로 이어 붙여 `-e` 를 찾았다. 그런데 이 절에는
        `seed.py` 를 부르는 블록이 **둘**(기본 시딩 · KEY-176 fixture)이라, 한쪽에서
        `-e` 를 지워도 다른 쪽 것을 보고 통과했다. 오늘 세 번 밟은 것과 같은 함정이라
        블록 단위로 갈랐다.
        """
        blocks = [b for b in self._bash_blocks() if any("scripts/seed.py" in ln for ln in b)]
        assert blocks, "4-3 절에 seed 를 부르는 bash 블록이 없다"

        for block in blocks:
            text = "\n".join(block)
            for name in ("-e SEED_ALLOW_PROD", "-e SEED_STAFF_PASSWORD"):
                assert name in text, (
                    f"`{name}` 이 없는 블록이 있다 — 값이 컨테이너에 안 들어가 seed 가 거부한다:\n{text}"
                )

    @classmethod
    def _bash_blocks(cls) -> list[list[str]]:
        """` ```bash ` 블록을 **각각 따로** 돌려준다."""
        blocks: list[list[str]] = []
        current: list[str] | None = None
        for line in cls._section().splitlines():
            if line.startswith("```"):
                if current is not None:
                    blocks.append(current)
                    current = None
                elif line.strip() == "```bash":
                    current = []
                continue
            if current is not None:
                current.append(line)
        if current:
            blocks.append(current)
        return blocks

    @classmethod
    def _bash(cls) -> list[str]:
        """**따라 칠 명령만 뽑는다** — ` ```bash ` 블록 안.

        이 절은 「이렇게 하면 죽는다」를 일부러 적어 둔다.

            python scripts/seed.py  →  ModuleNotFoundError: No module named 'tortoise'

        그것까지 잡으면 검사가 **문서가 경고하려는 바로 그 문장**에 걸려 빨간불이
        난다. 반례는 ` ```text ` 에, 실행할 것은 ` ```bash ` 에 있으므로 그것으로
        가른다. (처음에는 산문까지 잡혔다 — 글자를 훑는 검사가 자기 문서를 잡는
        자리는 오늘만 세 번째다.)
        """
        return [line for block in cls._bash_blocks() for line in block]

    def test_it_uses_the_interpreter_that_has_the_dependencies(self) -> None:
        seed_lines = [ln for ln in self._bash() if "scripts/seed.py" in ln and "docker cp" not in ln]

        assert seed_lines, "4-3 절의 bash 블록에 seed 실행 줄이 없다"
        for line in seed_lines:
            assert "uv run --no-sync" in line or ".venv/bin/python" in line, (
                f"시스템 파이썬으로 돌린다 — tortoise 가 없어 죽는다: 「{line.strip()}」"
            )

    def test_it_cleans_up_afterwards(self) -> None:
        """운영 이미지에 시딩 도구를 남기지 않는다."""
        section = "\n".join(self._bash())
        assert "rm -rf /app/scripts" in section, "밀어 넣은 것을 도로 치우는 단계가 없다"


class TestTheNarrowDoorIsTheOnlyWayPastTheFixtureGuard:
    """**공용 안전핀은 그대로 두고 좁은 문 하나만 낸다** — 이희진 님 `#158` B안.

    `SEED_ALLOW_PROD` 로 `seed.py` 의 문을 열어도, 그 다음에 `all_staff()` 가
    `_refuse_in_production()` 으로 다시 막는다. 실제로 막혔다 —

        ProductionFixtureError: 합성 직원 계정은 운영 환경에서 읽지 않는다 (ENV=prod)

    그 가드에 `SEED_ALLOW_PROD` 조건을 넣는 길도 있었지만 그러면 「합성 계정은
    운영에서 절대 못 읽는다」는 KEY-110 의 규칙이 **조건부**로 바뀐다. `seed.py`
    말고 다른 코드가 실수로 그 경로를 타도 조용히 통과하게 된다.

    그래서 가드는 한 글자도 안 건드리고 `read_staff_csv_for_seed_override()`
    하나를 새로 냈다. 이 검사가 그 경계를 지킨다.
    """

    STAFF = ROOT / "app" / "tests" / "fixtures" / "staff.py"
    SEED = ROOT / "scripts" / "seed.py"

    def test_the_common_guard_is_untouched(self) -> None:
        """`all_staff()` 는 조건 없이 가드를 거친다."""
        source = self.STAFF.read_text(encoding="utf-8")
        fn = ast.get_source_segment(source, _func_in(source, "all_staff")) or ""

        assert "_refuse_in_production()" in fn, "`all_staff()` 가 가드를 안 거친다"
        assert "SEED_ALLOW_PROD" not in fn, "공용 가드에 조건이 붙었다 — 「운영에서 절대 안 읽는다」가 조건부가 된다"

        guard = ast.get_source_segment(source, _func_in(source, "_refuse_in_production")) or ""
        assert "SEED_ALLOW_PROD" not in guard, "가드 자체에 예외가 뚫렸다"

    def test_the_override_skips_the_guard_and_says_so(self) -> None:
        source = self.STAFF.read_text(encoding="utf-8")
        fn = ast.get_source_segment(source, _func_in(source, "read_staff_csv_for_seed_override")) or ""

        assert fn, "좁은 문이 없다"
        assert "_refuse_in_production" not in fn.split('"""')[-1], "좁은 문이 가드를 거친다 — 그러면 낼 이유가 없다"
        assert "seed" in fn.lower(), "이름·설명에 이것이 시드 전용 예외 경로임이 안 드러난다"

    def test_the_seed_checks_the_flag_before_using_it(self) -> None:
        """**순서가 뒤집히면 아무 문턱 없이 합성 계정을 읽는다.**

        시드가 그 함수를 부르는 모든 자리는 `_prod_override_granted()` 로 갈려
        있어야 한다.
        """
        source = self.SEED.read_text(encoding="utf-8")
        live = "\n".join(line.split("#", 1)[0] for line in source.splitlines())

        calls = [ln for ln in live.splitlines() if "read_staff_csv_for_seed_override(" in ln]
        assert calls, "시드가 좁은 문을 안 쓴다 — 운영에서 가드에 막힌다"

        for line in calls:
            assert "_prod_override_granted()" in line, f"플래그 확인 없이 좁은 문을 쓴다 — 「{line.strip()}」"

    def test_nothing_else_uses_the_override(self) -> None:
        """**`seed.py` 밖에서는 아무도 못 쓴다.**

        이 함수가 여기저기 퍼지면 공용 가드를 남겨 둔 뜻이 없어진다.
        """
        users = []
        for path in (ROOT / "app").rglob("*.py"):
            if path == self.STAFF:
                continue
            if "read_staff_csv_for_seed_override" in path.read_text(encoding="utf-8"):
                users.append(str(path.relative_to(ROOT)))

        allowed = {"app/tests/deploy/test_key200_seed_prod_gate.py"}
        assert set(users) <= allowed, f"시드 밖에서 좁은 문을 쓴다 — {sorted(set(users) - allowed)}"
