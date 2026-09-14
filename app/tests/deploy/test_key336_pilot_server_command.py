"""좁은문 플래그가 컨테이너까지 닿는가 — KEY-336.

KEY-264·KEY-284 의 좁은문은 **환경변수와 실행 플래그를 둘 다** 본다. 환경변수는
`.env` 로 가는데 **플래그는 갈 자리가 없었다** — 이미지 기본 CMD 가 uvicorn CLI 고,
uvicorn 은 모르는 인자를 받으면 죽는다. 그래서 `ENV=prod` + `SMS_PROVIDER=solapi`
로 올려도 `_otp_service()` 가 플래그를 못 보고 `UnavailableOtpDelivery` 로 떨어져
**503 만 나가는** 상태였다.

`app/pilot_server.py` 가 그 자리를 위해 있다. 이 검사는 **운영 compose 가 실제로
그것을 쓰는지**와, 바꿔 다는 과정에서 **조용히 달라질 수 있는 것들**을 잰다.
"""

import ast
import shlex

from app.tests.deploy.conftest import ROOT, read, service

PROD_COMPOSE = "infra/docker/docker-compose.prod.yml"
PILOT_ENTRYPOINT = "app.pilot_server"

#: compose 가 플래그를 받는 자리. 값이 아니라 **이름**만 본다.
FLAG_VAR = "PILOT_SERVER_FLAGS"

#: 저장소에 박혀 있으면 안 되는 것들 — 박히면 모든 배포에 늘 붙는다.
GATE_FLAGS = ("--otp-confirm-solapi-prod", "--pilot-confirm-mock-otp")


def _fastapi_command() -> str:
    command = service(PROD_COMPOSE, "fastapi").get("command")
    assert command, "운영 compose 의 fastapi 에 `command` 가 없다 — 기본 CMD(uvicorn)로 떠서 플래그를 못 받는다"
    return " ".join(command) if isinstance(command, list) else str(command)


def test_the_prod_compose_starts_the_pilot_entrypoint() -> None:
    """uvicorn CLI 로 뜨면 플래그를 줄 자리가 없다."""
    command = _fastapi_command()

    assert PILOT_ENTRYPOINT in command, f"fastapi 가 `{PILOT_ENTRYPOINT}` 로 안 뜬다: {command}"
    assert f"${{{FLAG_VAR}" in command, f"플래그를 `{FLAG_VAR}` 로 안 받는다 — 그러면 좁은문을 열 길이 없다: {command}"


def test_the_gate_flags_are_not_baked_into_the_repository() -> None:
    """🚩 **플래그를 compose 에 박지 않는다.**

    박으면 저장소에 커밋되어 **모든 배포에 늘 붙고**, 「환경변수 + 플래그」가
    사실상 환경변수 하나가 된다. 좁은문을 두 겹으로 만든 뜻이 사라진다.
    """
    command = _fastapi_command()

    for flag in GATE_FLAGS:
        assert flag not in command, f"좁은문 플래그 `{flag}` 가 compose 에 박혀 있다 — `{FLAG_VAR}` 로만 넣는다"


def test_the_pilot_entrypoint_keeps_the_image_defaults() -> None:
    """**바꿔 달면서 조용히 달라지는 것**을 막는다.

    `pilot_server` 는 `--host`·`--port`·`--workers` 에 제 기본값을 갖는다. 그
    값이 이미지 기본 CMD 와 어긋나면, 플래그를 켠 날 **워커 수나 바인딩이 함께
    바뀐다** — 아무도 그걸 의도하지 않았고, 부하가 달라져도 원인을 못 찾는다.
    """
    dockerfile = read("app/Dockerfile")
    cmd_line = next(line for line in dockerfile.splitlines() if line.strip().startswith("CMD"))
    image_cmd = ast.literal_eval(cmd_line.strip()[len("CMD") :].strip())
    image_args = {
        image_cmd[i].lstrip("-"): image_cmd[i + 1]
        for i in range(len(image_cmd) - 1)
        if image_cmd[i].startswith("--") and not image_cmd[i + 1].startswith("--")
    }

    source = read("app/pilot_server.py")
    tree = ast.parse(source)
    defaults: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"):
            continue
        first = node.args[0] if node.args else None
        if not isinstance(first, ast.Constant):
            # `add_argument(PILOT_ALLOW_MOCK_OTP_FLAG, …)` 처럼 상수 이름으로
            # 등록하는 것들 — 기본값을 안 갖는 스위치라 여기서 볼 것이 없다.
            continue
        name = str(first.value).lstrip("-")
        for keyword in node.keywords:
            if keyword.arg == "default":
                defaults[name] = str(ast.literal_eval(keyword.value))

    for option in ("host", "port", "workers"):
        assert option in image_args, f"이미지 CMD 에 `--{option}` 이 없다 — 검사가 헛돈다"
        assert option in defaults, f"`pilot_server` 에 `--{option}` 기본값이 없다"
        assert defaults[option] == image_args[option], (
            f"`--{option}` 이 갈렸다 — 이미지 CMD 는 {image_args[option]}, "
            f"pilot_server 는 {defaults[option]}. 플래그를 켜는 날 이것도 함께 바뀐다"
        )


def test_the_pilot_entrypoint_accepts_both_gate_flags() -> None:
    """`config.py` 가 찾는 이름과 `pilot_server` 가 받는 이름이 같아야 한다.

    한쪽 이름만 바뀌면 **플래그를 줘도 조용히 안 먹는다** — 그러면 좁은문이
    열리지 않아 503 만 나가고, 설정은 맞게 돼 있어 보인다.
    """
    from app.core.config import OTP_SOLAPI_PROD_ENABLED_FLAG, PILOT_ALLOW_MOCK_OTP_FLAG

    source = read("app/pilot_server.py")

    for flag in (OTP_SOLAPI_PROD_ENABLED_FLAG, PILOT_ALLOW_MOCK_OTP_FLAG):
        assert flag in source, f"`pilot_server` 가 `{flag}` 를 안 받는다 — config 는 그 이름을 찾는다"


def test_the_command_is_a_single_shell_word_list() -> None:
    """`sh -c` 한 덩어리로 넘겨야 `${…}` 치환이 먹는다.

    compose 는 리스트 형태 `command` 의 각 조각을 셸 없이 그대로 `exec` 한다.
    변수를 쓰면서 `sh -c` 를 빼면 빈 값일 때 **빈 인자 하나**가 그대로 넘어가
    argparse 가 죽는다.
    """
    command = service(PROD_COMPOSE, "fastapi")["command"]

    assert isinstance(command, list) and command[:2] == ["sh", "-c"], (
        f"`sh -c` 로 감싸지 않았다 — 빈 `{FLAG_VAR}` 가 빈 인자로 넘어간다: {command}"
    )
    assert "exec " in command[2], "`exec` 없이 돌면 시그널이 앱까지 안 간다 — 재배포가 느려진다"
    assert shlex.split(command[2].replace(f"${{{FLAG_VAR}:-}}", "")), "명령이 비어 있다"


def test_the_example_env_names_the_flag_variable() -> None:
    """예시 파일에 이름이 없으면, 그 파일을 베껴 쓴 사람은 넣을 자리를 모른다."""
    example = read("envs/example.prod.env")

    assert FLAG_VAR in example, f"`envs/example.prod.env` 에 `{FLAG_VAR}` 이름이 없다"


def test_the_runbook_tells_how_to_pass_the_flag() -> None:
    """런북이 「플래그를 넣어라」까지만 적고 **넣는 방법**을 안 적으면, 그 자리에서 멈춘다."""
    runbook = read("docs/deploy-runbook.md")

    assert FLAG_VAR in runbook, f"런북에 `{FLAG_VAR}` 가 없다 — 플래그를 넣는 방법이 안 적혀 있다"


def test_the_root_stays_where_the_helpers_expect() -> None:
    """위 검사들이 저장소 밖을 읽고 있지 않은지 — 조용한 통과를 막는다."""
    assert (ROOT / PROD_COMPOSE).exists(), f"{PROD_COMPOSE} 를 못 찾았다"
