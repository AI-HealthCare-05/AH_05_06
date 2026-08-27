"""Pilot의 OTP→안내→챗봇→D+7 환류를 합성 데이터로 확인한다 — KEY-176.

민감한 값은 인자가 아니라 환경변수로만 받고, 응답 본문은 출력하지 않는다.
반복 실행 가능한 전용 합성 안내·진료 건을 준비한 뒤 아래처럼 실행한다.

    PATIENT_SMOKE_SYNTHETIC_ONLY=1 \
    PATIENT_SMOKE_LINK_TOKEN=... PATIENT_SMOKE_OTP=... \
    PATIENT_SMOKE_VISIT_ID=... SMOKE_LOGIN_ID=... SMOKE_PASSWORD=... \
    uv run python scripts/key176_patient_smoke.py https://pilot.example.com
"""

import asyncio
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

import httpx


class Reason(StrEnum):
    OK = "정상"
    SAFE_FALLBACK = "안전 fallback 응답 — 챗봇 정상 생성은 확인하지 못했다"
    BAD_URL = "대상 주소가 http/https URL이 아니다"
    MISSING_INPUT = "합성 Pilot 환경변수가 빠졌다"
    SYNTHETIC_ONLY = "합성 데이터 전용 확인 표시가 없다"
    UNREACHABLE = "대상에 닿지 못했다"
    TIMEOUT = "제한 시간 안에 답이 없다"
    REJECTED = "요청이 계약 상태 코드로 완료되지 않았다"
    MALFORMED = "응답 모양이 계약과 다르다"


@dataclass(frozen=True)
class Check:
    name: str
    reason: Reason
    status_code: int | None = None

    @property
    def ok(self) -> bool:
        return self.reason in {Reason.OK, Reason.SAFE_FALLBACK}

    def line(self) -> str:
        if self.reason is Reason.SAFE_FALLBACK:
            mark = "WARN"
        else:
            mark = "PASS" if self.ok else "FAIL"
        suffix = f" ({self.status_code})" if self.status_code is not None else ""
        return f"[{mark}] {self.name} — {self.reason}{suffix}"


REQUIRED_ENV = (
    "PATIENT_SMOKE_LINK_TOKEN",
    "PATIENT_SMOKE_OTP",
    "PATIENT_SMOKE_VISIT_ID",
    "SMOKE_LOGIN_ID",
    "SMOKE_PASSWORD",
)
FIXED_QUESTION = "복약 안내를 다시 설명해 주세요."
FIXED_CHECKIN = {"medication": "taking", "pain": {"had": False}}


def normalize_base(raw: str) -> str | None:
    target = raw.strip().rstrip("/")
    return target if target.startswith(("http://", "https://")) else None


def _json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except Exception:
        return None


def _status(name: str, response: httpx.Response, expected: int) -> Check:
    if response.status_code != expected:
        return Check(name, Reason.REJECTED, response.status_code)
    return Check(name, Reason.OK)


def _chatbot_status(response: httpx.Response) -> Check:
    status = _status("chatbot", response, 200)
    if not status.ok:
        return status
    body = _json_or_none(response)
    if not isinstance(body, dict) or not isinstance(body.get("fallback"), bool):
        return Check("chatbot", Reason.MALFORMED, response.status_code)
    if body["fallback"]:
        return Check("chatbot", Reason.SAFE_FALLBACK, response.status_code)
    return status


def _failure(name: str, error: Exception) -> Check:
    if isinstance(error, httpx.TimeoutException):
        return Check(name, Reason.TIMEOUT)
    return Check(name, Reason.UNREACHABLE)


async def run_patient_smoke(
    base: str,
    *,
    link_token: str,
    otp: str,
    visit_id: str,
    login_id: str,
    password: str,
    client: httpx.AsyncClient,
) -> list[Check]:
    """앞 단계가 실패하면 멈춘다. 원문은 반환값과 출력에 넣지 않는다."""
    checks: list[Check] = []

    async def request(
        name: str,
        expected: int,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        headers: Mapping[str, str] | None = None,
        judge: Callable[[httpx.Response], Check] | None = None,
    ) -> httpx.Response | None:
        try:
            response = await client.request(
                method,
                f"{base}{path}",
                json=json_body,
                headers=headers,
            )
        except Exception as error:
            checks.append(_failure(name, error))
            return None
        checks.append(judge(response) if judge is not None else _status(name, response, expected))
        return response if checks[-1].ok else None

    if (
        await request(
            "otp_issue",
            200,
            "POST",
            "/api/v1/patient-auth/otp/issue",
            json_body={"link_token": link_token},
        )
        is None
    ):
        return checks
    if (
        await request(
            "otp_verify",
            200,
            "POST",
            "/api/v1/patient-auth/otp/verify",
            json_body={"link_token": link_token, "code": otp},
        )
        is None
    ):
        return checks
    if await request("guide", 200, "GET", f"/api/v1/guides/{link_token}") is None:
        return checks
    if (
        await request(
            "chatbot",
            200,
            "POST",
            "/api/v1/chatbot/responses",
            json_body={"link_token": link_token, "question": FIXED_QUESTION},
            judge=_chatbot_status,
        )
        is None
    ):
        return checks
    if (
        await request(
            "checkin_submit",
            201,
            "POST",
            f"/api/v1/checkins/{link_token}",
            json_body=FIXED_CHECKIN,
        )
        is None
    ):
        return checks

    login = await request(
        "staff_auth",
        200,
        "POST",
        "/api/v1/auth/login",
        json_body={"login_id": login_id, "password": password},
    )
    if login is None:
        return checks
    body = _json_or_none(login)
    if not isinstance(body, dict) or not body.get("access_token"):
        checks[-1] = Check("staff_auth", Reason.MALFORMED)
        return checks
    await request(
        "hospital_checkin",
        200,
        "GET",
        f"/api/v1/visits/{visit_id}/checkin",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    return checks


def report(checks: list[Check]) -> str:
    return "\n".join(check.line() for check in checks)


async def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("사용법: uv run python scripts/key176_patient_smoke.py <Pilot URL>", file=sys.stderr)
        return 2
    base = normalize_base(argv[1])
    if base is None:
        print(Check("target", Reason.BAD_URL).line(), file=sys.stderr)
        return 1
    if os.environ.get("PATIENT_SMOKE_SYNTHETIC_ONLY") != "1":
        print(Check("input", Reason.SYNTHETIC_ONLY).line(), file=sys.stderr)
        return 1
    values = {name: os.environ.get(name, "") for name in REQUIRED_ENV}
    if any(not value for value in values.values()):
        print(Check("input", Reason.MISSING_INPUT).line(), file=sys.stderr)
        return 1

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        checks = await run_patient_smoke(
            base,
            link_token=values["PATIENT_SMOKE_LINK_TOKEN"],
            otp=values["PATIENT_SMOKE_OTP"],
            visit_id=values["PATIENT_SMOKE_VISIT_ID"],
            login_id=values["SMOKE_LOGIN_ID"],
            password=values["SMOKE_PASSWORD"],
            client=client,
        )
    print(report(checks))
    return 0 if checks and all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv)))
