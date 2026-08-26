"""원격 Pilot 이 살아 있는가 — KEY-184.

    uv run python scripts/smoke.py https://api.example.com

배포한 뒤 **사람이 눈으로 훑는 대신** 기계가 세 자리를 찔러 본다. 하나라도
어긋나면 0 이 아닌 종료 코드로 끝나므로, 배포 스크립트나 CI 가 그대로 게이트로
쓸 수 있다.

    health   `GET /api/v1/health`      API·DB·Redis 가 다 살아 있나
    auth     `POST /api/v1/auth/login` 합성 계정으로 토큰을 받나
    core     `GET /api/v1/front-desk/visits` 그 토큰으로 실제 조회가 되나

**밖으로 나가는 글자를 어휘로 묶어 둔다.** 진단은 `Reason` 에 적힌 문장과
서비스 이름·상태 코드뿐이고, 응답 본문은 어떤 경로로도 안 찍힌다. `health` 는
로컬에서 예외 문자열을 `detail` 에 실어 주는데(`health_routers.py:27`), 그걸
그대로 흘리면 접속 문자열이 배포 로그에 남는다.

비밀번호는 인자로 받지 않는다 — 원격의 `ps` 와 CI 로그에 남는다. 환경변수로만
받고, 어디에도 다시 쓰지 않는다.
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import httpx

HEALTH_PATH = "/api/v1/health"
LOGIN_PATH = "/api/v1/auth/login"
CORE_PATH = "/api/v1/front-desk/visits"

DEFAULT_TIMEOUT_SECONDS = 10.0


class Reason(StrEnum):
    """**밖으로 나갈 수 있는 말의 전부다.**

    새 진단이 필요하면 여기 한 줄을 더한다. 응답에서 가져온 글자를 끼워 넣지
    않는다 — 그 순간 원문·토큰이 로그로 나가는 길이 열린다.
    """

    OK = "정상"
    BAD_URL = "대상 주소가 http/https URL 이 아니다"
    UNREACHABLE = "대상에 닿지 못했다 (주소·방화벽·기동 여부 확인)"
    TIMEOUT = "제한 시간 안에 답이 없다"
    SERVER_ERROR = "서버가 5xx 로 답했다"
    DEGRADED = "health 가 degraded 다"
    MALFORMED = "health 응답 모양이 계약과 다르다"
    AUTH_REJECTED = "합성 계정 로그인이 거절됐다"
    NO_TOKEN = "로그인은 통과했는데 access_token 이 없다"
    UNEXPECTED_STATUS = "예상 밖 상태 코드"
    MISSING_CREDENTIALS = "SMOKE_LOGIN_ID · SMOKE_PASSWORD 가 없다"


@dataclass(frozen=True)
class Check:
    """한 자리의 판정. `note` 도 어휘 안에서만 채운다 — 이름과 숫자뿐이다."""

    name: str
    reason: Reason
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.reason is Reason.OK

    def line(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        tail = f" ({self.note})" if self.note else ""
        return f"[{mark}] {self.name} — {self.reason}{tail}"


def normalize_base(raw: str) -> str | None:
    """끝의 `/` 만 떼고 돌려준다. http/https 가 아니면 `None`."""
    target = raw.strip().rstrip("/")
    if not target.startswith(("http://", "https://")):
        return None
    return target


def judge_health(status_code: int, body: object) -> Check:
    """`health` 응답을 판정한다 — **본문은 읽되 옮기지 않는다.**

    서비스 이름(`db`·`redis`)은 우리가 정한 이름이라 내보내도 된다. 그 안의
    `detail` 은 예외 문자열이라 절대 안 내보낸다.
    """
    if status_code >= 500 and status_code != 503:
        return Check("health", Reason.SERVER_ERROR, str(status_code))
    if not isinstance(body, dict) or not isinstance(body.get("services"), dict):
        return Check("health", Reason.MALFORMED)

    services: dict = body["services"]
    down = sorted(
        name for name, value in services.items() if not (isinstance(value, dict) and value.get("status") == "ok")
    )
    if down:
        return Check("health", Reason.DEGRADED, "·".join(down))
    if status_code != 200:
        return Check("health", Reason.UNEXPECTED_STATUS, str(status_code))
    return Check("health", Reason.OK)


def judge_login(status_code: int, body: object) -> Check:
    if status_code in (401, 403):
        return Check("auth", Reason.AUTH_REJECTED)
    if status_code >= 500:
        return Check("auth", Reason.SERVER_ERROR, str(status_code))
    if status_code != 200:
        return Check("auth", Reason.UNEXPECTED_STATUS, str(status_code))
    if not isinstance(body, dict) or not body.get("access_token"):
        return Check("auth", Reason.NO_TOKEN)
    return Check("auth", Reason.OK)


def judge_core(status_code: int) -> Check:
    if status_code in (401, 403):
        return Check("core", Reason.AUTH_REJECTED)
    if status_code >= 500:
        return Check("core", Reason.SERVER_ERROR, str(status_code))
    if status_code != 200:
        return Check("core", Reason.UNEXPECTED_STATUS, str(status_code))
    return Check("core", Reason.OK)


def failure_of(name: str, exc: Exception) -> Check:
    """오갈 때 터진 예외를 **어휘 안의 진단**으로 옮긴다."""
    if isinstance(exc, httpx.TimeoutException):
        return Check(name, Reason.TIMEOUT)
    if isinstance(exc, httpx.InvalidURL):
        return Check(name, Reason.BAD_URL)
    if isinstance(exc, httpx.RequestError):
        return Check(name, Reason.UNREACHABLE)
    raise exc


async def run_smoke(base: str, login_id: str, password: str, client: httpx.AsyncClient) -> list[Check]:
    """세 자리를 차례로 찌른다. 앞이 실패하면 뒤는 안 부르고 그대로 남긴다."""
    checks: list[Check] = []

    try:
        response = await client.get(f"{base}{HEALTH_PATH}")
        checks.append(judge_health(response.status_code, _json_or_none(response)))
    except Exception as exc:
        checks.append(failure_of("health", exc))

    if not checks[-1].ok:
        return checks

    token = ""
    try:
        response = await client.post(f"{base}{LOGIN_PATH}", json={"login_id": login_id, "password": password})
        body = _json_or_none(response)
        checks.append(judge_login(response.status_code, body))
        if checks[-1].ok and isinstance(body, dict):
            token = str(body["access_token"])
    except Exception as exc:
        checks.append(failure_of("auth", exc))

    if not checks[-1].ok:
        return checks

    try:
        response = await client.get(
            f"{base}{CORE_PATH}",
            params={"date": date.today().isoformat()},
            headers={"Authorization": f"Bearer {token}"},
        )
        checks.append(judge_core(response.status_code))
    except Exception as exc:
        checks.append(failure_of("core", exc))

    return checks


def _json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except Exception:
        return None


def report(checks: list[Check]) -> str:
    return "\n".join(check.line() for check in checks)


def exit_code(checks: list[Check]) -> int:
    """하나라도 어긋나면 1 — 배포·CI 가 이 값으로 멈춘다."""
    return 0 if checks and all(check.ok for check in checks) else 1


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("사용법: uv run python scripts/smoke.py <대상 URL>", file=sys.stderr)
        return 2

    base = normalize_base(argv[1])
    if base is None:
        print(Check("target", Reason.BAD_URL).line(), file=sys.stderr)
        return 1

    login_id = os.environ.get("SMOKE_LOGIN_ID", "")
    password = os.environ.get("SMOKE_PASSWORD", "")
    if not login_id or not password:
        print(Check("credentials", Reason.MISSING_CREDENTIALS).line(), file=sys.stderr)
        return 1

    timeout = float(os.environ.get("SMOKE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        checks = await run_smoke(base, login_id, password, client)

    print(report(checks))
    return exit_code(checks)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv)))
