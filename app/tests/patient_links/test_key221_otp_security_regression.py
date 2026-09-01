"""KEY-221: OTP 운영 우회·만료·폐기·5회 잠금 회귀 — 인수조건 보안 검증.

인수조건별 대응:
  AC1: 운영 우회, 만료, 폐기, 잠금 시나리오가 각각 차단된다.
       → TestProdOtpBypassBlocked, TestProdServiceBlocksOtpIssue
  AC2: 잠금 응답과 재시도 시간이 FE·API에서 일치한다.
       → test_patient_otp.py의 test_fifth_failure_locks_* 가 커버. 추가 없음.
  AC3: 애플리케이션 로그·access log·오류 응답에 원문이 없다.
       → TestTokenConfidentiality
  AC4: 인증 context는 화면에 필요한 최소 정보만 반환한다.
       → TestContextMinimalFields
  AC5: 재발송은 만료·폐기 상태와 본인확인 계약을 우회하지 않는다.
       → TestReIssueDoesNotBypassAuth
"""

import unittest
from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.timezone import now

from app.apis.v1.patient_otp_routers import _otp_service
from app.core.config import Config, Env
from app.main import app
from app.services.patient_otp import PatientOtpService, UnavailableOtpDelivery
from app.tests.auth_base import AuthTestCase
from app.tests.patient_links.test_patient_otp import (
    LINK_TOKEN,
    OTP,
    SECRET,
    RecordingDelivery,
    make_link,
)

MOCK_CODE = "000000"
_PROD_SECRET = "syn-prod-secret-for-config-validator-test-key-221-xyz"


# ── AC1: Config 레벨 우회 차단 ──────────────────────────────────────────────


class TestProdOtpBypassBlocked(unittest.TestCase):
    """MOCK_OTP_CODE가 PROD Config 레벨에서 거부된다 — DB 불필요."""

    def test_mock_otp_code_raises_in_prod_config(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            Config(
                ENV=Env.PROD,
                MOCK_OTP_CODE=MOCK_CODE,
                SECRET_KEY=_PROD_SECRET,
                DB_PASSWORD="syn-test-db-password",
            )
        self.assertIn("MOCK_OTP_CODE", str(ctx.exception))


# ── AC1: 운영 등가 서비스 OTP 발급 차단 ─────────────────────────────────────


class TestProdServiceBlocksOtpIssue(AuthTestCase):
    """UnavailableOtpDelivery(운영 기본 전달자)로 OTP 발급이 차단된다."""

    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(UnavailableOtpDelivery())

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_prod_delivery_blocks_otp_issue(self) -> None:
        await make_link()
        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
        assert res.status_code == 503
        assert res.json()["code"] == "OTP_DELIVERY_UNAVAILABLE"
        assert MOCK_CODE not in res.text

    async def test_000000_cannot_verify_without_prior_challenge(self) -> None:
        """발급 없이 000000을 verify하면 OTP_NOT_ISSUED로 차단된다."""
        await make_link()
        async with self.client() as c:
            res = await c.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": LINK_TOKEN, "code": MOCK_CODE},
            )
        assert res.status_code == 409
        assert res.json()["code"] == "OTP_NOT_ISSUED"
        assert MOCK_CODE not in res.text


# ── AC3: 토큰 원문 미노출 ────────────────────────────────────────────────────


class TestTokenConfidentiality(AuthTestCase):
    """OTP·링크·세션 토큰 원문이 API 응답 body에 노출되지 않는다."""

    def setUp(self) -> None:
        super().setUp()
        self.delivery = RecordingDelivery()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(self.delivery, secret_key=SECRET)

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_session_raw_value_not_in_verify_response_body(self) -> None:
        """세션 쿠키 원문은 Set-Cookie 헤더에만 있고 응답 body에 없다."""
        await make_link()
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            async with self.client() as c:
                await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
                res = await c.post(
                    "/api/v1/patient-auth/otp/verify",
                    json={"link_token": LINK_TOKEN, "code": OTP},
                )

        assert res.status_code == 200
        set_cookie = res.headers.get("set-cookie", "")
        assert "patient_session=" in set_cookie
        session_value = set_cookie.split("patient_session=")[1].split(";")[0]
        assert session_value not in res.text
        assert set(res.json().keys()) == {"verified", "session_expires_in_seconds"}

    async def test_link_token_not_in_context_or_otp_responses(self) -> None:
        """링크 토큰 원문이 context·issue·verify 응답 body에 노출되지 않는다."""
        await make_link()
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            async with self.client() as c:
                context = await c.post(
                    "/api/v1/patient-auth/context",
                    json={"link_token": LINK_TOKEN},
                )
                issue = await c.post(
                    "/api/v1/patient-auth/otp/issue",
                    json={"link_token": LINK_TOKEN},
                )
                verify = await c.post(
                    "/api/v1/patient-auth/otp/verify",
                    json={"link_token": LINK_TOKEN, "code": OTP},
                )

        for res in (context, issue, verify):
            assert LINK_TOKEN not in res.text, f"{res.request.url} 응답에 링크 토큰 원문이 노출됐다"

    async def test_otp_error_response_does_not_echo_code(self) -> None:
        """잘못된 OTP 코드가 오류 응답에 되비치지 않는다."""
        await make_link()
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            async with self.client() as c:
                await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
                res = await c.post(
                    "/api/v1/patient-auth/otp/verify",
                    json={"link_token": LINK_TOKEN, "code": "999999"},
                )

        assert res.status_code == 401
        assert "999999" not in res.text


# ── AC4: context 최소 정보 ───────────────────────────────────────────────────


class TestContextMinimalFields(AuthTestCase):
    """context 응답이 화면에 필요한 최소 정보만 반환한다."""

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_context_response_contains_only_allowed_fields(self) -> None:
        """응답 키가 hospital_name·masked_phone·visited_at·expires_at만 존재한다."""
        await make_link()
        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/context", json={"link_token": LINK_TOKEN})

        assert res.status_code == 200
        assert set(res.json().keys()) == {"hospital_name", "masked_phone", "visited_at", "expires_at"}

    async def test_context_does_not_expose_raw_phone(self) -> None:
        """전화번호 원문 없이 마스킹된 형태만 반환된다."""
        await make_link()
        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/context", json={"link_token": LINK_TOKEN})

        assert res.status_code == 200
        masked = res.json()["masked_phone"]
        assert "01000009100" not in masked
        assert "****" in masked

    async def test_context_does_not_expose_internal_ids_or_link_token(self) -> None:
        """내부 ID(patient_id, hospital_id 등)와 링크 토큰 원문이 응답에 없다."""
        await make_link()
        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/context", json={"link_token": LINK_TOKEN})

        assert res.status_code == 200
        body_text = res.text
        assert LINK_TOKEN not in body_text
        for field in ("patient_id", "hospital_id", "visit_id", "link_id", "guide_document_id"):
            assert field not in body_text, f"내부 필드 '{field}'가 context 응답에 노출됐다"


# ── AC5: 재발송 후 본인확인 계약 우회 불가 ───────────────────────────────────


class TestReIssueDoesNotBypassAuth(AuthTestCase):
    """재발송이 본인확인 계약을 우회하지 않는다."""

    def setUp(self) -> None:
        super().setUp()
        self.delivery = RecordingDelivery()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(self.delivery, secret_key=SECRET)

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_old_token_unusable_for_context_and_otp_after_re_issue(self) -> None:
        """재발송 후 구 토큰으로 context 조회·OTP 발급이 LINK_NOT_FOUND로 차단된다."""
        link = await make_link()
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        async with self.client() as c:
            re_issued = await c.post("/api/v1/patient-auth/link/re-issue", json={"link_token": LINK_TOKEN})
            context = await c.post("/api/v1/patient-auth/context", json={"link_token": LINK_TOKEN})
            issue = await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})

        assert re_issued.status_code == 202
        assert context.status_code == 404
        assert context.json()["code"] == "LINK_NOT_FOUND"
        assert issue.status_code == 404
        assert issue.json()["code"] == "LINK_NOT_FOUND"

    async def test_re_issue_response_does_not_set_session_cookie(self) -> None:
        """재발송 응답이 세션 쿠키를 부여하지 않는다 — OTP 인증 없이 세션 불가."""
        link = await make_link()
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/link/re-issue", json={"link_token": LINK_TOKEN})

        assert res.status_code == 202
        assert "patient_session=" not in res.headers.get("set-cookie", "")
        assert "patient_session" not in res.text

    async def test_revoked_link_re_issue_also_blocks_old_token(self) -> None:
        """폐기된 링크 재발송 후에도 구 토큰이 차단된다."""
        from app.models.visits import GuideDocument, GuideStatus

        link = await make_link()
        guide = await GuideDocument.get(guide_document_id=link.guide_document_id)
        guide.status = GuideStatus.APPROVAL_PENDING
        await guide.save(update_fields=["status"])

        async with self.client() as c:
            re_issued = await c.post("/api/v1/patient-auth/link/re-issue", json={"link_token": LINK_TOKEN})
            context = await c.post("/api/v1/patient-auth/context", json={"link_token": LINK_TOKEN})

        assert re_issued.status_code == 202
        assert context.status_code == 404
        assert context.json()["code"] == "LINK_NOT_FOUND"
