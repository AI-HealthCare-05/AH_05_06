"""앱 계정이 트리거를 만들 수 있는가 — KEY-358.

2026-09-16 배포가 마이그레이션 단계에서 멈췄다.

    (1419, 'You do not have the SUPER privilege and binary logging is enabled')

KEY-238 의 append-only 트리거 넷이 저장소 첫 사례였는데, 운영 앱 계정
(`DB_USER=ozcoding`)에는 SUPER 가 없고 `log_bin` 은 켜져 있었다. **표는
만들어지고 트리거만 빠진 채** 반쪽으로 남았다 — DDL 은 자동 커밋이라
되돌지도 않는다.

CI 는 `DB_USER: root` 로 돌아서 이것을 구조적으로 못 잡았다. 권한이 모자라
생기는 결함은 **운영보다 센 계정으로 검사하는 한 영영 안 보인다.**

실측으로 확인했다(mysql:8.0, 앱 등급 계정).

    --log-bin-trust-function-creators=0  →  ERROR 1419
    --log-bin-trust-function-creators=1  →  트리거 생성 성공,
                                            UPDATE 가 ERROR 1644 '45000' 로 막힘
"""

import re

from app.tests.deploy.conftest import ROOT, read, service

PROD_COMPOSE = "infra/docker/docker-compose.prod.yml"
TRUST_FLAG = "--log-bin-trust-function-creators=1"

#: 트리거·함수·프로시저를 만드는 줄. 주석은 세지 않는다.
ROUTINE_DDL = re.compile(r"\bCREATE\s+(?:TRIGGER|FUNCTION|PROCEDURE)\b", re.IGNORECASE)


def _mysql_command() -> list[str]:
    command = service(PROD_COMPOSE, "mysql").get("command") or []
    return [str(item) for item in command]


def _migrations_creating_routines() -> list[str]:
    folder = ROOT / "app" / "core" / "db" / "migrations" / "models"
    out = []
    for path in sorted(folder.glob("*.py")):
        body = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
        )
        if ROUTINE_DDL.search(body):
            out.append(path.name)
    return out


def test_the_server_lets_the_app_account_create_triggers() -> None:
    """🚩 **이 한 줄이 빠지면 트리거를 만드는 마이그레이션이 운영에서 죽는다.**

    앱 계정에 `SUPER` 를 주는 쪽은 안 쓴다 — 그 권한이면 서버 설정까지 바꾼다.
    """
    assert TRUST_FLAG in _mysql_command(), (
        f"{PROD_COMPOSE} 의 mysql 에 `{TRUST_FLAG}` 가 없다 — "
        "SUPER 없는 앱 계정이 `CREATE TRIGGER` 에서 1419 로 죽는다 (KEY-358 실측)."
    )


def test_the_flag_is_needed_because_a_migration_actually_creates_one() -> None:
    """**쓰지도 않는 설정을 켜 두지 않는다.**

    트리거를 만드는 마이그레이션이 하나도 없어지면 이 플래그도 걷어야 한다.
    그때 이 검사가 그 사실을 알려 준다 — 위 검사만 있으면 까닭을 잃은 설정이
    영영 남는다.
    """
    creators = _migrations_creating_routines()

    assert creators, (
        f"트리거·함수를 만드는 마이그레이션이 하나도 없다 — 그렇다면 `{TRUST_FLAG}` 도 걷을 때다 ({PROD_COMPOSE})."
    )


def test_the_local_compose_matches_when_it_defines_mysql() -> None:
    """로컬이 운영과 다르면 **여기서 되는 것이 거기서 안 된다.**"""
    local = ROOT / "infra" / "docker" / "docker-compose.yml"
    if not local.exists() or "mysql" not in read("infra/docker/docker-compose.yml"):
        return

    command = service("infra/docker/docker-compose.yml", "mysql").get("command") or []
    if not command:
        return

    assert TRUST_FLAG in [str(item) for item in command], (
        f"로컬 compose 의 mysql 에 `{TRUST_FLAG}` 가 없다 — 운영과 갈린다"
    )
