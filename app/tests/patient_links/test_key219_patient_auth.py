"""KEY-219: context·session·re-issue·mock OTP 통합 테스트."""

from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.timezone import now

from app.apis.v1.patient_otp_routers import _otp_service
from app.core.time import as_utc
from app.main import app
from app.models.visits import GuideDocument, GuideStatus
from app.services.patient_links import digest_link_token
from app.services.patient_otp import MockOtpDelivery, PatientOtpService
from app.tests.auth_base import AuthTestCase
from app.tests.patient_links.test_patient_otp import LINK_TOKEN, SECRET, RecordingDelivery, make_link

MOCK_CODE = "000000"


class BaseAuthCase(AuthTestCase):
    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(RecordingDelivery(), secret_key=SECRET)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(_otp_service, None)
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def call_context(self, token: str = LINK_TOKEN):  # type: ignore[return]
        async with self.client() as c:
            return await c.post(
                "/api/v1/patient-auth/context",
                json={"link_token": token},
            )

    async def call_re_issue(self, token: str = LINK_TOKEN):  # type: ignore[return]
        async with self.client() as c:
            return await c.post(
                "/api/v1/patient-auth/link/re-issue",
                json={"link_token": token},
            )


# ── context API ──────────────────────────────────────────────────────────────


class TestPatientAuthContext(BaseAuthCase):
    async def test_active_link_returns_context(self) -> None:
        await make_link()

        res = await self.call_context()

        assert res.status_code == 200
        body = res.json()
        assert body["hospital_name"] == "KEY-91 합성의원"
        assert "****" in body["masked_phone"]
        assert body["masked_phone"].endswith("9100")
        assert "visited_at" in body
        assert "expires_at" in body

    async def test_expires_at_is_utc_and_within_link_ttl(self) -> None:
        await make_link()

        res = await self.call_context()

        expires_at = datetime.fromisoformat(res.json()["expires_at"])
        utcoffset = expires_at.utcoffset()
        assert utcoffset is not None, "expires_at must be timezone-aware"
        assert utcoffset.total_seconds() == 0, "expires_at offset must be UTC(+00:00)"
        expected = as_utc(now() + timedelta(hours=72))
        assert abs((expires_at - expected).total_seconds()) < 5

    async def test_unknown_token_returns_404(self) -> None:
        res = await self.call_context("not-a-real-token")
        assert res.status_code == 404
        assert res.json()["code"] == "LINK_NOT_FOUND"

    async def test_expired_link_returns_410_link_expired(self) -> None:
        link = await make_link()
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        res = await self.call_context()

        assert res.status_code == 410
        assert res.json()["code"] == "LINK_EXPIRED"

    async def test_revoked_link_returns_410_link_revoked(self) -> None:
        link = await make_link()
        guide = await GuideDocument.get(guide_document_id=link.guide_document_id)
        guide.status = GuideStatus.APPROVAL_PENDING
        await guide.save(update_fields=["status"])

        res = await self.call_context()

        assert res.status_code == 410
        assert res.json()["code"] == "LINK_REVOKED"

    async def test_phone_is_masked_in_response(self) -> None:
        await make_link()
        res = await self.call_context()
        assert res.status_code == 200
        body = res.json()
        # 중간 4자리가 노출되지 않아야 한다
        assert "0000" not in body["masked_phone"]
        assert "****" in body["masked_phone"]


# ── session API ───────────────────────────────────────────────────────────────


class TestPatientSession(BaseAuthCase):
    async def test_active_session_returns_expires_in(self) -> None:
        await make_link()
        delivery = RecordingDelivery()
        svc = PatientOtpService(delivery, secret_key=SECRET)
        app.dependency_overrides[_otp_service] = lambda: svc

        async with self.client() as c:
            await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
            _, code = delivery.sent[0]
            await c.post("/api/v1/patient-auth/otp/verify", json={"link_token": LINK_TOKEN, "code": code})

            res = await c.get("/api/v1/patient-auth/session", params={"link_token": LINK_TOKEN})

        assert res.status_code == 200
        body = res.json()
        assert body["active"] is True
        assert body["expires_in_seconds"] > 0

    async def test_no_session_cookie_returns_401(self) -> None:
        await make_link()
        async with self.client() as c:
            res = await c.get("/api/v1/patient-auth/session", params={"link_token": LINK_TOKEN})
        assert res.status_code == 401
        assert res.json()["code"] == "PATIENT_SESSION_EXPIRED"

    async def test_wrong_link_token_returns_401(self) -> None:
        await make_link()
        delivery = RecordingDelivery()
        svc = PatientOtpService(delivery, secret_key=SECRET)
        app.dependency_overrides[_otp_service] = lambda: svc

        async with self.client() as c:
            await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
            _, code = delivery.sent[0]
            await c.post("/api/v1/patient-auth/otp/verify", json={"link_token": LINK_TOKEN, "code": code})

            res = await c.get("/api/v1/patient-auth/session", params={"link_token": "wrong-token"})

        assert res.status_code == 401
        assert res.json()["code"] == "PATIENT_SESSION_EXPIRED"


# ── re-issue API ──────────────────────────────────────────────────────────────


class TestPatientLinkReIssue(BaseAuthCase):
    async def test_expired_link_is_re_issued(self) -> None:
        link = await make_link()
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        res = await self.call_re_issue()

        assert res.status_code == 202
        assert res.json()["requested"] is True
        await link.refresh_from_db()
        assert link.expires_at > now()
        assert link.token_digest != digest_link_token(LINK_TOKEN)

    async def test_revoked_link_is_re_issued(self) -> None:
        link = await make_link()
        guide = await GuideDocument.get(guide_document_id=link.guide_document_id)
        guide.status = GuideStatus.APPROVAL_PENDING
        await guide.save(update_fields=["status"])

        res = await self.call_re_issue()

        assert res.status_code == 202
        assert res.json()["requested"] is True

    async def test_active_link_cannot_be_re_issued(self) -> None:
        await make_link()
        res = await self.call_re_issue()
        assert res.status_code == 409
        assert res.json()["code"] == "LINK_STILL_ACTIVE"

    async def test_unknown_token_returns_404(self) -> None:
        res = await self.call_re_issue("not-a-real-token")
        assert res.status_code == 404
        assert res.json()["code"] == "LINK_NOT_FOUND"


# ── mock OTP ──────────────────────────────────────────────────────────────────


class TestMockOtpDelivery(BaseAuthCase):
    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(
            MockOtpDelivery(),
            secret_key=SECRET,
            fixed_otp_code=MOCK_CODE,
        )

    async def test_fixed_code_is_accepted(self) -> None:
        await make_link()
        async with self.client() as c:
            issue = await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
            assert issue.status_code == 200

            verify = await c.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": LINK_TOKEN, "code": MOCK_CODE},
            )
        assert verify.status_code == 200
        assert verify.json()["verified"] is True

    async def test_wrong_code_is_rejected_even_with_mock(self) -> None:
        await make_link()
        async with self.client() as c:
            await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
            res = await c.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": LINK_TOKEN, "code": "999999"},
            )
        assert res.status_code == 401
        assert res.json()["code"] == "OTP_INVALID"

    async def test_mock_code_not_exposed_in_response(self) -> None:
        await make_link()
        async with self.client() as c:
            res = await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
        assert MOCK_CODE not in res.text
