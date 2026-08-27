"""KEY-176 Pilot smoke가 원문을 출력하지 않고 여정을 순서대로 재는가."""

import httpx
import pytest

from scripts.key176_patient_smoke import Check, Reason, report, run_patient_smoke

BASE = "https://pilot.synthetic.invalid"
LINK_TOKEN = "synthetic-key176-smoke-link-token"
OTP = "176176"
PASSWORD = "synthetic-key176-smoke-password"
ACCESS_TOKEN = "synthetic-key176-staff-access-token"


@pytest.mark.asyncio
async def test_patient_smoke_completes_every_stage_without_printing_raw_values() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(200, json={"access_token": ACCESS_TOKEN})
        if request.url.path == "/api/v1/chatbot/responses":
            return httpx.Response(200, json={"fallback": False})
        expected = {
            "/api/v1/patient-auth/otp/issue": 200,
            "/api/v1/patient-auth/otp/verify": 200,
            f"/api/v1/guides/{LINK_TOKEN}": 200,
            "/api/v1/chatbot/responses": 200,
            f"/api/v1/checkins/{LINK_TOKEN}": 201,
            "/api/v1/visits/176/checkin": 200,
        }
        return httpx.Response(expected.get(request.url.path, 404), json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checks = await run_patient_smoke(
            BASE,
            link_token=LINK_TOKEN,
            otp=OTP,
            visit_id="176",
            login_id="synthetic-key176-staff",
            password=PASSWORD,
            client=client,
        )

    assert len(checks) == 7
    assert all(check.ok for check in checks)
    assert paths[-1] == "/api/v1/visits/176/checkin"
    output = report(checks)
    for raw_value in (LINK_TOKEN, OTP, PASSWORD, ACCESS_TOKEN):
        assert raw_value not in output


@pytest.mark.asyncio
async def test_safe_chatbot_fallback_is_warned_but_does_not_stop_the_patient_journey() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/chatbot/responses":
            return httpx.Response(200, json={"fallback": True, "answer": "출력하면 안 되는 합성 fallback 원문"})
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(200, json={"access_token": ACCESS_TOKEN})
        status = 201 if request.url.path == f"/api/v1/checkins/{LINK_TOKEN}" else 200
        return httpx.Response(status, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checks = await run_patient_smoke(
            BASE,
            link_token=LINK_TOKEN,
            otp=OTP,
            visit_id="176",
            login_id="synthetic-key176-staff",
            password=PASSWORD,
            client=client,
        )

    chatbot = next(check for check in checks if check.name == "chatbot")
    assert chatbot.reason is Reason.SAFE_FALLBACK
    assert chatbot.ok is True
    assert chatbot.line().startswith("[WARN] chatbot")
    assert paths[-1] == "/api/v1/visits/176/checkin", "fallback이어도 D+7과 병원 조회를 끝까지 실행해야 한다"
    assert "출력하면 안 되는 합성 fallback 원문" not in report(checks)


@pytest.mark.asyncio
async def test_chatbot_without_a_boolean_fallback_stops_as_a_malformed_contract() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/otp/issue") or request.url.path.endswith("/otp/verify"):
            return httpx.Response(200, json={})
        if request.url.path == f"/api/v1/guides/{LINK_TOKEN}":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"fallback": "false", "raw": LINK_TOKEN})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checks = await run_patient_smoke(
            BASE,
            link_token=LINK_TOKEN,
            otp=OTP,
            visit_id="176",
            login_id="synthetic-key176-staff",
            password=PASSWORD,
            client=client,
        )

    assert checks[-1] == Check("chatbot", Reason.MALFORMED, 200)
    assert paths[-1] == "/api/v1/chatbot/responses"
    assert LINK_TOKEN not in report(checks)


@pytest.mark.asyncio
async def test_patient_smoke_stops_after_a_rejected_unapproved_guide() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/otp/issue") or request.url.path.endswith("/otp/verify"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"code": "LINK_NOT_FOUND", "raw": LINK_TOKEN})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checks = await run_patient_smoke(
            BASE,
            link_token=LINK_TOKEN,
            otp=OTP,
            visit_id="176",
            login_id="synthetic-key176-staff",
            password=PASSWORD,
            client=client,
        )

    assert [check.reason for check in checks] == [Reason.OK, Reason.OK, Reason.REJECTED]
    assert paths[-1] == f"/api/v1/guides/{LINK_TOKEN}"
    assert LINK_TOKEN not in report(checks)
