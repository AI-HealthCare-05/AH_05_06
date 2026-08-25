"""환자 OTP 뒤 30분 세션·재인증·폐기가 강제되는가 — KEY-92."""

from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.apis.v1.patient_otp_routers import _otp_service
from app.core.redis_client import get_redis
from app.main import app
from app.models.visits import PatientOtpChallenge
from app.services.patient_otp import OTP_RESEND_COOLDOWN, PatientOtpService
from app.services.patient_sessions import PATIENT_SESSION_SECONDS
from app.tests.fakes import FakeRedis
from app.tests.patient_links.test_patient_otp import LINK_TOKEN, OTP, SECRET, RecordingDelivery, make_link

REPLACEMENT_OTP = "654321"


class PatientSessionTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        self.delivery = RecordingDelivery()
        self.otp = PatientOtpService(self.delivery, secret_key=SECRET)
        app.dependency_overrides[get_redis] = lambda: self.redis
        app.dependency_overrides[_otp_service] = lambda: self.otp

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def authenticate(self, client: AsyncClient, code: str = OTP) -> None:
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(code)):
            issued = await client.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
        assert issued.status_code == 200, issued.text
        verified = await client.post(
            "/api/v1/patient-auth/otp/verify",
            json={"link_token": LINK_TOKEN, "code": code},
        )
        assert verified.status_code == 200, verified.text


class TestPatientSessionJourney(PatientSessionTestCase):
    async def test_otp_opens_one_browser_for_thirty_minutes_without_storing_the_raw_cookie(self) -> None:
        await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)

            opened = await browser.get(f"/api/v1/guides/{LINK_TOKEN}")

            assert opened.status_code == 200, opened.text
            assert self.redis.ttls
            assert set(self.redis.ttls.values()) == {PATIENT_SESSION_SECONDS}
            raw_cookie = browser.cookies.get("patient_session")
            assert raw_cookie
            assert raw_cookie not in repr(self.redis.values)

    async def test_a_new_browser_and_an_expired_session_must_verify_again(self) -> None:
        await make_link()
        async with self.client() as authenticated, self.client() as new_browser:
            await self.authenticate(authenticated)

            fresh = await new_browser.get(f"/api/v1/guides/{LINK_TOKEN}")
            assert fresh.status_code == 401
            assert fresh.json()["code"] == "PATIENT_SESSION_EXPIRED"

            for key in list(self.redis.values):
                if key.startswith("patient_session:"):
                    await self.redis.delete(key)
            expired = await authenticated.get(f"/api/v1/guides/{LINK_TOKEN}")
            assert expired.status_code == 401
            assert expired.json()["code"] == "PATIENT_SESSION_EXPIRED"

    async def test_logout_revokes_the_server_session_and_clears_the_cookie(self) -> None:
        await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)

            logged_out = await browser.delete("/api/v1/patient-auth/otp/session")
            blocked = await browser.get(f"/api/v1/guides/{LINK_TOKEN}")

            assert logged_out.status_code == 204
            assert "Max-Age=0" in logged_out.headers["set-cookie"]
            assert blocked.status_code == 401
            assert blocked.json()["code"] == "PATIENT_SESSION_EXPIRED"

    async def test_reauthentication_rotates_the_session_and_rejects_the_old_browser(self) -> None:
        await make_link()
        async with self.client() as first_browser, self.client() as second_browser:
            await self.authenticate(first_browser)
            first_cookie = first_browser.cookies.get("patient_session")

            challenge = await PatientOtpChallenge.get()
            challenge.issued_at = now() - OTP_RESEND_COOLDOWN - timedelta(seconds=1)
            await challenge.save(update_fields=["issued_at"])
            await self.authenticate(second_browser, REPLACEMENT_OTP)

            assert second_browser.cookies.get("patient_session") != first_cookie
            old = await first_browser.get(f"/api/v1/guides/{LINK_TOKEN}")
            current = await second_browser.get(f"/api/v1/guides/{LINK_TOKEN}")
            assert old.status_code == 401
            assert old.json()["code"] == "PATIENT_SESSION_EXPIRED"
            assert current.status_code == 200

    async def test_a_session_for_one_link_cannot_open_another_token(self) -> None:
        await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)

            wrong = await browser.get("/api/v1/guides/not-the-authenticated-link")

            assert wrong.status_code == 401
            assert wrong.json()["code"] == "PATIENT_SESSION_EXPIRED"
