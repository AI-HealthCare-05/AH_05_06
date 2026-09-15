"""좁은문 플래그가 서버까지 닿는가 — KEY-336.

KEY-264·KEY-284 의 좁은문은 **환경변수와 실행 플래그를 둘 다** 본다(`sys.argv`).
`infra/docker/docker-compose.pilot.yml` 이 그 자리를 위해 있다 — `app.pilot_server`
로 띄우고, **환경변수가 있을 때만** 셸이 플래그를 붙인다.

그런데 그 파일이 **서버에 올라가지 않고 있었다.** `deployment.sh` 가 운영 compose
하나만 `scp` 했다. 켤 수는 있는데 켤 파일이 서버에 없는 상태였다.

이 검사는 그 길이 끊기지 않는지 본다. 특히 **런타임에만 드러나는 자리 하나**를
자동으로 센다 — `pilot.yml` 주석이 「고칠 때마다 눈으로 세어 본다」고 적어 둔
`$$` 다(홑 `$` 는 compose 가 먼저 먹어 셸에는 빈 문자열만 남는다).
"""

import ast
import re

from app.tests.deploy.conftest import ROOT, read, service

PROD_COMPOSE = "infra/docker/docker-compose.prod.yml"
PILOT_OVERLAY = "infra/docker/docker-compose.pilot.yml"
PILOT_ENTRYPOINT = "app.pilot_server"

#: 좁은문을 여는 환경변수. 오버레이는 **이것이 있을 때만** 플래그를 붙인다.
GATE_ENVS = ("PILOT_ALLOW_MOCK_OTP", "OTP_SOLAPI_PROD_ENABLED")
GATE_FLAGS = ("--pilot-confirm-mock-otp", "--otp-confirm-solapi-prod")
WORKER_GATE_ENV = "SMS_DISPATCH_ENABLED"
WORKER_GATE_FLAG = "--sms-dispatch-confirm"


def _pilot_command() -> str:
    command = service(PILOT_OVERLAY, "fastapi").get("command")
    assert command, f"{PILOT_OVERLAY} 의 fastapi 에 `command` 가 없다"
    return "\n".join(command) if isinstance(command, list) else str(command)


def _pilot_worker_command() -> str:
    command = service(PILOT_OVERLAY, "ai-worker").get("command")
    assert command, f"{PILOT_OVERLAY} 의 ai-worker 에 `command` 가 없다"
    return "\n".join(command) if isinstance(command, list) else str(command)


def test_the_overlay_starts_the_pilot_entrypoint() -> None:
    """uvicorn CLI 로 뜨면 플래그를 줄 자리가 없다 — 모르는 인자를 받으면 죽는다."""
    assert PILOT_ENTRYPOINT in _pilot_command(), f"오버레이가 `{PILOT_ENTRYPOINT}` 로 안 띄운다"


def test_the_flags_are_attached_only_when_the_gate_env_is_present() -> None:
    """🚩 **이중 게이트의 핵심.**

    플래그를 상수로 박아 두면 환경변수 하나만으로 좁은문이 열린다 — 서버 `.env`
    에 `OTP_SOLAPI_PROD_ENABLED=1` 이 실수로 들어간 날, 재확인 없이 모든 배포가
    실제 발송 경로로 빠진다.
    """
    command = _pilot_command()

    for env, flag in zip(GATE_ENVS, GATE_FLAGS, strict=True):
        assert flag in command, f"오버레이가 `{flag}` 를 안 붙인다"
        # `.*?` 로 두면 **`fi` 를 넘어간다** — 플래그를 `if` 블록 뒤 `exec` 줄로
        # 옮겨도(= 게이트 없이 늘 붙음) 통과한다 (`2heej` `#309` 리뷰).
        # 그래서 `fi` 를 못 지나가게 막는다.
        guarded = re.search(
            rf"if \[ -n \"?\$+\{{{env}[^\]]*\](?:(?!\bfi\b).)*?{re.escape(flag)}",
            command,
            re.S,
        )
        assert guarded, f"`{flag}` 가 `{env}` 검사 안에 있지 않다 — 상수로 박히면 게이트가 한 겹이 된다"


def test_the_shell_variables_are_doubled_so_compose_does_not_eat_them() -> None:
    """**홑 `$` 는 compose 가 먼저 먹는다.**

    `command` 블록 안의 `$` 를 compose 가 **호스트 환경 기준으로** 치환해 버려서,
    셸에는 빈 문자열만 남는다. 그러면 조건문이 늘 거짓이 되어 **플래그가 영영 안
    붙는다** — 문법 오류가 아니라 CI 로는 안 잡히고, 켰는데 안 켜지는 모습으로만
    드러난다.

    `pilot.yml` 주석이 「고칠 때마다 원문에서 홑 `$` 개수를 눈으로 세어 본다」고
    적어 둔 자리다. 눈으로 세는 대신 여기서 센다.
    """
    command = _pilot_command()
    singles = [m.start() for m in re.finditer(r"(?<!\$)\$(?!\$)", command)]

    assert not singles, (
        f"`command` 안에 홑 `$` 가 {len(singles)} 개 있다 — compose 가 먼저 치환해 셸에는 빈 값만 간다. `$$` 로 쓴다"
    )


def test_the_overlay_passes_the_gate_envs_through() -> None:
    """값 없이 이름만 적어 **호스트 환경에서** 가져온다 — `.env` 에 안 적으려는 것이다."""
    declared = service(PILOT_OVERLAY, "fastapi").get("environment") or []
    names = {str(item).split("=")[0] for item in declared}

    for env in GATE_ENVS:
        assert env in names, f"오버레이가 `{env}` 를 컨테이너로 안 넘긴다"
        assert f"{env}=" not in " ".join(str(i) for i in declared), (
            f"`{env}` 에 값이 박혀 있다 — 그러면 오버레이를 주는 것만으로 열린다"
        )


def test_the_production_compose_stays_plain() -> None:
    """**운영 compose 는 건드리지 않는다.**

    거기에 `command` 를 박으면 **모든 배포**가 Pilot 진입점으로 뜨고, 게이트
    환경변수를 `.env` 에 적게 되어 다음 배포부터 영구히 켜진다. 오버레이를 따로
    둔 뜻이 사라진다 (`#309` 리뷰).
    """
    assert "command" not in service(PROD_COMPOSE, "fastapi"), (
        f"{PROD_COMPOSE} 의 fastapi 에 `command` 가 생겼다 — Pilot 설정은 오버레이로만 준다"
    )
    assert "command" not in service(PROD_COMPOSE, "ai-worker"), (
        f"{PROD_COMPOSE} 의 ai-worker 에 `command` 가 생겼다 — 문자 발송 플래그는 Pilot 오버레이로만 준다"
    )


def test_the_worker_flag_is_guarded_in_the_pilot_overlay() -> None:
    command = _pilot_worker_command()
    assert "python -m ai_worker.main" in command
    guarded = re.search(
        rf"if \[ -n \"?\$+\{{{WORKER_GATE_ENV}[^\]]*\](?:(?!\bfi\b).)*?{re.escape(WORKER_GATE_FLAG)}",
        command,
        re.S,
    )
    assert guarded, f"`{WORKER_GATE_FLAG}` 가 `{WORKER_GATE_ENV}` 검사 안에 있지 않다"
    assert not list(re.finditer(r"(?<!\$)\$(?!\$)", command)), "ai-worker command 의 셸 변수는 $$로 써야 한다"
    declared = service(PILOT_OVERLAY, "ai-worker").get("environment") or []
    assert WORKER_GATE_ENV in declared
    assert f"{WORKER_GATE_ENV}=" not in " ".join(str(item) for item in declared)


def test_the_deploy_script_ships_the_overlay() -> None:
    """서버에 파일이 없으면 **켤 수가 없다.**

    켜려는 순간 `no such file` 을 만나고, 그때 손으로 `scp` 하느라 사고 한복판에서
    시간을 쓴다. 올려 두기만 한다 — `-f` 로 함께 주지 않으면 아무 일도 안 일어난다.
    """
    script = read("scripts/deployment.sh")

    # **주석에 이름이 있는 것으로는 안 된다.** 「…(`docker-compose.pilot.yml` 참고)」
    # 같은 줄이 하나 있으면 `scp` 를 통째로 지워도 통과한다 (`2heej` `#309` 리뷰 —
    # `#304`·`#309` 에 이어 같은 종류의 헛도는 검사가 세 번째다). **실어 나르는
    # 줄 자체**를 본다.
    shipped = [
        line
        for line in script.splitlines()
        if not line.lstrip().startswith("#") and "scp" in line and "docker-compose.pilot.yml" in line
    ]

    assert shipped, "배포가 Pilot 오버레이를 서버에 안 올린다 — `scp` 줄이 없다"


def test_the_pilot_entrypoint_keeps_the_image_defaults() -> None:
    """**바꿔 달면서 조용히 달라지는 것**을 막는다.

    `pilot_server` 는 `--host`·`--port`·`--workers` 에 제 기본값을 갖는다. 그
    값이 이미지 기본 CMD 와 어긋나면, 좁은문을 켠 날 **워커 수나 바인딩이 함께
    바뀐다** — 아무도 의도하지 않았고, 부하가 달라져도 원인을 못 찾는다.
    """
    dockerfile = read("app/Dockerfile")
    cmd_line = next(line for line in dockerfile.splitlines() if line.strip().startswith("CMD"))
    image_cmd = ast.literal_eval(cmd_line.strip()[len("CMD") :].strip())
    image_args = {
        image_cmd[i].lstrip("-"): image_cmd[i + 1]
        for i in range(len(image_cmd) - 1)
        if image_cmd[i].startswith("--") and not image_cmd[i + 1].startswith("--")
    }

    defaults: dict[str, str] = {}
    for node in ast.walk(ast.parse(read("app/pilot_server.py"))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"):
            continue
        first = node.args[0] if node.args else None
        if not isinstance(first, ast.Constant):
            continue
        for keyword in node.keywords:
            if keyword.arg == "default":
                defaults[str(first.value).lstrip("-")] = str(ast.literal_eval(keyword.value))

    for option in ("host", "port", "workers"):
        assert option in image_args, f"이미지 CMD 에 `--{option}` 이 없다 — 검사가 헛돈다"
        assert defaults.get(option) == image_args[option], (
            f"`--{option}` 이 갈렸다 — 이미지 CMD 는 {image_args[option]}, "
            f"pilot_server 는 {defaults.get(option)}. 좁은문을 켜는 날 이것도 함께 바뀐다"
        )


def test_the_runbook_tells_how_to_turn_it_on_from_the_server() -> None:
    """런북이 로컬 `--build` 시절 명령만 적고 있으면, 서버 앞에서 멈춘다."""
    runbook = read("docs/deploy-runbook.md")

    assert "-f docker-compose.pilot.yml" in runbook, "런북에 서버에서 오버레이를 주는 명령이 없다"
    assert (ROOT / PILOT_OVERLAY).exists(), f"{PILOT_OVERLAY} 가 없다 — 검사가 헛돈다"


#: 런북은 **명령을 담은 문서**다. `test_key185_rollback_rehearsal.py` 가
#: ```` ```bash ```` 블록을 정규식으로 떠다 쓰는 것처럼, 이 문서의 코드펜스는
#: 사람뿐 아니라 검사도 읽는다.
RUNBOOK = "docs/deploy-runbook.md"

#: 펜스 줄로 인정하는 꼴 — 여는 ```` ```bash ````, 닫는 ```` ``` ````. 그 외에
#: **뒤에 산문이 붙은 펜스**는 결함이다.
FENCE_LINE = re.compile(r"```[A-Za-z0-9_+-]*$")


def _fence_lines() -> list[tuple[int, str]]:
    return [(i, line) for i, line in enumerate(read(RUNBOOK).splitlines(), 1) if line.lstrip().startswith("```")]


def test_no_fence_line_carries_prose() -> None:
    """닫는 펜스 뒤에 문장이 붙으면 **그 문장이 사라진다.**

    실제로 두 번 그랬다. 4-3-2 절에 오버레이 명령을 끼워 넣으면서 원래 있던
    「이 둘이 갖춰지면 실제 솔라피로 나가되…」가 닫는 펜스 줄에 붙어 버렸다
    (`2heej` `#309` 리뷰 3번이 같은 절의 앞선 사례를 짚었고, 고치면서 새로
    하나를 더 만들었다).

    눈으로는 안 보인다 — 렌더러가 펜스로 읽고 뒤를 버리거나, 코드 블록 안으로
    끌어들인다. **읽는 쪽이 사람만이 아니라서** 더 나쁘다.
    """
    carriers = [(n, line.strip()) for n, line in _fence_lines() if not FENCE_LINE.search(line.strip())]
    assert not carriers, (
        f"{RUNBOOK} 의 코드펜스 줄에 산문이 붙었다:\n"
        + "\n".join(f"  {n}행: {text}" for n, text in carriers)
        + "\n펜스는 제 줄에 혼자 둔다 — 붙은 문장은 렌더에서 사라진다."
    )


def test_every_fence_is_closed() -> None:
    """열고 안 닫으면 **그 뒤 문서 전체가 코드 블록이 된다.**"""
    count = len(_fence_lines())
    assert count % 2 == 0, f"{RUNBOOK} 의 코드펜스가 {count} 개 — 홀수다. 어딘가 안 닫혔다."
