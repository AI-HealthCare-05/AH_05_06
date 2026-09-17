"""앱 계정이 트리거를 만들 수 있는가 — KEY-358.

2026-09-16 배포가 마이그레이션 단계에서 멈췄다.

    (1419, 'You do not have the SUPER privilege and binary logging is enabled')

KEY-238 의 append-only 트리거 넷이 저장소 첫 사례였는데, 운영 앱 계정
(`DB_USER=ozcoding`)에는 SUPER 가 없고 `log_bin` 은 켜져 있었다. **표는
만들어지고 트리거만 빠진 채** 반쪽으로 남았다 — DDL 은 자동 커밋이라
되돌지도 않는다.

CI 는 `DB_USER: root` 로 돌아서 이것을 구조적으로 못 잡았다. 권한이 모자라
생기는 결함은 **운영보다 센 계정으로 검사하는 한 영영 안 보인다.**

**로컬 쪽은 여기서 안 잰다.** `test_key230_schema_drift.py` 의
`test_local_mysql_allows_migration_triggers_without_super` 가 루트
`docker-compose.yml` 을 이미 잰다. 그 검사가 KEY-230 때 로컬에만 플래그를
넣었고 **운영에는 빠뜨린 것**이 이 사고의 뿌리다 — 그래서 여기는 운영 쪽만
본다. 둘이 모이면 「로컬과 운영이 같다」가 선다.

(이 파일에 로컬을 재는 검사가 하나 더 있었는데, **없는 경로**
`infra/docker/docker-compose.yml` 을 읽고 조기 반환해 늘 통과만 했다.
`2heej` `#344` 리뷰로 걷었다.)

실측으로 확인했다(mysql:8.0, 앱 등급 계정).

    --log-bin-trust-function-creators=0  →  ERROR 1419
    --log-bin-trust-function-creators=1  →  트리거 생성 성공,
                                            UPDATE 가 ERROR 1644 '45000' 로 막힘
"""

import re

from app.tests.deploy.conftest import ROOT, service

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
