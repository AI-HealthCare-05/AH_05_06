"""KEY-185 증적의 실행 계약과 내부 일관성을 검사한다.

과거 Pilot 작업이 실제 수행됐다는 사실은 운영 증적과 사람의 검토 대상이다.
pytest가 산문에 ``PASS``가 있는지만 보고 그 사실을 재현했다고 주장하지 않는다.
대신 저장소에서 독립적으로 잴 수 있는 버전 왕복, 런북 절차, smoke 실행기,
시간 순서와 민감정보 비노출 계약을 검사한다.
"""

import re
import subprocess
import sys
from datetime import datetime

from app.tests.deploy.conftest import ROOT, read

EVIDENCE = "docs/qa/KEY-185-pilot-rollback-rehearsal.md"
RUNBOOK = "docs/deploy-runbook.md"


def _section(rel: str, heading: str) -> str:
    prose = read(rel)
    assert heading in prose, f"{rel}에 {heading!r} 절이 없다"
    body = prose.split(heading, 1)[1]
    level = len(heading.split(maxsplit=1)[0])
    following = re.search(rf"\n#{{2,{level}}} ", body)
    return body[: following.start()] if following else body


def _version_rows() -> dict[str, tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    for line in read(EVIDENCE).splitlines():
        match = re.fullmatch(
            r"\| (?P<stage>시작 시 정상 태그|롤백 대상 태그|재복구 태그) "
            r"\| `(?P<app>v\d+\.\d+\.\d+)` \| `(?P<ai>v\d+\.\d+\.\d+)` "
            r"\| `(?P<web>v\d+\.\d+\.\d+)` \|",
            line,
        )
        if match:
            rows[match["stage"]] = (match["app"], match["ai"], match["web"])
    return rows


def test_versions_make_a_real_round_trip_and_match_compose_variables() -> None:
    rows = _version_rows()
    assert set(rows) == {"시작 시 정상 태그", "롤백 대상 태그", "재복구 태그"}
    assert rows["시작 시 정상 태그"] == rows["재복구 태그"]
    assert all(old != current for old, current in zip(rows["롤백 대상 태그"], rows["시작 시 정상 태그"], strict=True))

    compose = read("docker-compose.yml") + read("infra/docker/docker-compose.prod.yml")
    for variable in ("APP_VERSION", "AI_WORKER_VERSION", "WEB_VERSION"):
        assert f"${{{variable}}}" in compose, f"증적의 {variable}가 실제 Compose 계약에 없다"


def test_rollback_and_restore_steps_follow_the_runbook_contract() -> None:
    runbook = _section(RUNBOOK, "## 4. 롤백")
    command_block = re.search(r"```bash\n(?P<commands>.*?)```", runbook, re.DOTALL)
    assert command_block, "런북 롤백 절에 실행 가능한 bash 블록이 없다"
    commands = command_block["commands"]
    assert commands.index("docker compose down") < commands.index("docker compose up -d --pull always")

    for heading in ("### 2. 이전 정상 버전으로 롤백", "### 3. 현재 정상 버전으로 재배포"):
        procedure = _section(EVIDENCE, heading)
        assert procedure.index("docker compose down") < procedure.index("docker compose up -d --pull always"), (
            f"{heading}이 런북의 down → 태그 변경 → up 순서를 따르지 않는다"
        )


def test_documented_smoke_entrypoint_actually_starts() -> None:
    procedure = "\n".join(
        _section(EVIDENCE, heading)
        for heading in (
            "### 1. 기준 상태 확인",
            "### 2. 이전 정상 버전으로 롤백",
            "### 3. 현재 정상 버전으로 재배포",
        )
    )
    assert "scripts/smoke.py" in procedure

    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "smoke.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert done.returncode == 2
    assert "사용법:" in done.stderr


def test_recorded_stages_are_complete_and_chronological() -> None:
    prose = read(EVIDENCE)
    recorded: list[tuple[datetime, datetime]] = []
    for stage in ("기준 smoke", "이전 버전 기동", "롤백 후 smoke", "현재 버전 재기동", "최종 smoke"):
        match = re.search(
            rf"\| {re.escape(stage)} \| (?P<start>[^|]+) \| (?P<end>[^|]+) \| PASS —",
            prose,
        )
        assert match, f"{stage}의 시작·종료·PASS 기록이 없다"
        start = datetime.strptime(match["start"].strip(), "%Y-%m-%d %H:%M KST")
        end = datetime.strptime(match["end"].strip(), "%Y-%m-%d %H:%M KST")
        assert start <= end, f"{stage} 종료가 시작보다 빠르다"
        recorded.append((start, end))

    deployment = recorded[1:]
    assert all(before[1] <= after[0] for before, after in zip(deployment, deployment[1:], strict=False))


def test_evidence_has_no_secret_shaped_values() -> None:
    prose = read(EVIDENCE)
    forbidden = {
        "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        "JWT": r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
        "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    }
    for name, pattern in forbidden.items():
        assert re.search(pattern, prose) is None, f"증적에 {name} 형태의 값이 있다"

    assignments = re.finditer(r"(?m)^\s*(?:export\s+)?(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>[^\n#]+)", prose)
    for assignment in assignments:
        name, value = assignment["name"], assignment["value"].strip()
        if any(marker in name for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY")):
            assert value.startswith("<") and value.endswith(">"), f"{name}에 자리표시자가 아닌 값이 기록됐다"
