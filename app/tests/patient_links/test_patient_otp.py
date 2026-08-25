"""환자 OTP 3분·5회 실패·10분 잠금 계약 — KEY-91."""

import hashlib
from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.apis.v1.patient_otp_routers import _otp_service
from app.core.redis_client import get_redis
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink, PatientOtpChallenge, Visit
from app.services.patient_links import digest_link_token
from app.services.patient_otp import OTP_LOCK_DURATION, OTP_RESEND_COOLDOWN, OTP_TTL, PatientOtpService
from app.services.patient_sessions import PATIENT_SESSION_SECONDS
from app.tests.fakes import FakeRedis

LINK_TOKEN = "SYN-key91-link-token-not-a-real-patient-token"
OTP = "042731"
SECRET = "synthetic-key91-test-secret-never-used-outside-tests"


class RecordingDelivery:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))


class FailingDelivery:
    async def send(self, phone: str, code: str) -> None:
        raise RuntimeError("synthetic delivery failure without sensitive values")


class PersistedStateDelivery:
    def __init__(self) -> None:
        self.persisted_before_send = False

    async def send(self, phone: str, code: str) -> None:
        challenge = await PatientOtpChallenge.get()
        self.persisted_before_send = challenge.otp_digest != code and challenge.issued_at is not None


async def make_link() -> PatientGuideLink:
    hospital = await Hospital.create(name="KEY-91 합성의원")
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-KEY91-01",
        name="합성환자",
        birth_date="1990-01-02",
        phone="01000009100",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at="2026-08-24T09:00:00+09:00",
    )
    guide = await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=GuideStatus.SCHEDULED_TO_SEND,
        approved_by=1,
        approved_at=now(),
    )
    return await PatientGuideLink.create(
        guide_document=guide,
        token_digest=digest_link_token(LINK_TOKEN),
        expires_at=now() + timedelta(hours=72),
        issued_by=1,
    )


class PatientOtpTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.delivery = RecordingDelivery()
        self.service = PatientOtpService(self.delivery, secret_key=SECRET)
        self.redis = FakeRedis()
        app.dependency_overrides[_otp_service] = lambda: self.service
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def issue(self):
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            async with self.client() as client:
                return await client.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})

    async def verify(self, code: str):
        async with self.client() as client:
            return await client.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": LINK_TOKEN, "code": code},
            )


class TestPatientOtpHappyPath(PatientOtpTestCase):
    async def test_six_digit_otp_expires_in_three_minutes_and_raw_value_is_not_persisted_or_returned(self) -> None:
        await make_link()
        before = now()

        issued = await self.issue()

        assert issued.status_code == 200
        assert issued.json()["retry_after_seconds"] == int(OTP_RESEND_COOLDOWN.total_seconds())
        assert OTP not in issued.text
        assert self.delivery.sent == [("01000009100", OTP)]

        challenge = await PatientOtpChallenge.get()
        assert before + OTP_TTL <= challenge.expires_at <= now() + OTP_TTL
        assert challenge.otp_digest != OTP
        assert challenge.otp_salt != OTP
        assert OTP not in repr(challenge.__dict__)
        assert len(challenge.otp_digest) == hashlib.sha256().digest_size * 2

        verified = await self.verify(OTP)
        assert verified.status_code == 200
        assert verified.json() == {
            "verified": True,
            "session_expires_in_seconds": PATIENT_SESSION_SECONDS,
        }
        cookie = verified.headers["set-cookie"]
        assert "patient_session=" in cookie
        assert "HttpOnly" in cookie
        assert "Max-Age=1800" in cookie
        assert OTP not in verified.text

        reused = await self.verify(OTP)
        assert reused.status_code == 409
        assert reused.json()["code"] == "OTP_ALREADY_USED"
        assert OTP not in reused.text


class TestPatientOtpFailurePolicy(PatientOtpTestCase):
    async def test_sms_opt_out_blocks_issue_without_creating_or_sending_an_otp(self) -> None:
        link = await make_link()
        patient = await Patient.get(patient_id=link.guide_document.visit.patient_id)
        patient.sms_consent = False
        await patient.save(update_fields=["sms_consent"])

        blocked = await self.issue()

        assert blocked.status_code == 409
        assert blocked.json()["code"] == "SMS_OPT_OUT"
        assert self.delivery.sent == []
        assert await PatientOtpChallenge.all().count() == 0

    async def test_issue_persists_challenge_before_calling_the_delivery_provider(self) -> None:
        await make_link()
        delivery = PersistedStateDelivery()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(delivery, secret_key=SECRET)

        issued = await self.issue()

        assert issued.status_code == 200
        assert delivery.persisted_before_send is True

    async def test_reissue_is_limited_for_sixty_seconds_without_sending_or_rotating_the_code(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200
        original = await PatientOtpChallenge.get()
        original_digest = original.otp_digest

        repeated = await self.issue()

        assert repeated.status_code == 429
        assert repeated.json()["code"] == "OTP_RESEND_TOO_SOON"
        assert 59 <= repeated.json()["retry_after_seconds"] <= int(OTP_RESEND_COOLDOWN.total_seconds())
        assert repeated.headers["retry-after"] == str(repeated.json()["retry_after_seconds"])
        assert len(self.delivery.sent) == 1
        saved = await PatientOtpChallenge.get()
        assert saved.otp_digest == original_digest

    async def test_fifth_failure_locks_issue_and_verify_for_ten_minutes(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200

        for remaining in (4, 3, 2, 1):
            failed = await self.verify("000000")
            assert failed.status_code == 401
            assert failed.json() == {
                "code": "OTP_INVALID",
                "message": "인증번호가 올바르지 않습니다.",
                "remaining_attempts": remaining,
            }
            assert "000000" not in failed.text

        locked = await self.verify("000000")
        assert locked.status_code == 429
        assert locked.json()["code"] == "OTP_LOCKED"
        assert 599 <= locked.json()["retry_after_seconds"] <= int(OTP_LOCK_DURATION.total_seconds())
        assert locked.headers["retry-after"] == str(locked.json()["retry_after_seconds"])

        issue_while_locked = await self.issue()
        correct_while_locked = await self.verify(OTP)
        assert issue_while_locked.status_code == 429
        assert correct_while_locked.status_code == 429
        assert len(self.delivery.sent) == 1

    async def test_reissue_invalidates_old_code_but_does_not_reset_failures(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200
        assert (await self.verify("000000")).json()["remaining_attempts"] == 4
        challenge = await PatientOtpChallenge.get()
        challenge.issued_at = now() - OTP_RESEND_COOLDOWN - timedelta(seconds=1)
        await challenge.save(update_fields=["issued_at"])

        replacement = "654321"
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(replacement)):
            async with self.client() as client:
                reissued = await client.post(
                    "/api/v1/patient-auth/otp/issue",
                    json={"link_token": LINK_TOKEN},
                )
        assert reissued.status_code == 200
        assert (await self.verify(OTP)).json()["remaining_attempts"] == 3
        assert (await self.verify(replacement)).status_code == 200

    async def test_elapsed_lock_is_released_and_failure_count_starts_again(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200
        challenge = await PatientOtpChallenge.get()
        challenge.failed_attempts = 5
        challenge.locked_until = now() - timedelta(seconds=1)
        challenge.issued_at = now() - OTP_RESEND_COOLDOWN - timedelta(seconds=1)
        await challenge.save(update_fields=["failed_attempts", "locked_until", "issued_at"])

        failed_after_unlock = await self.verify("000000")

        assert failed_after_unlock.status_code == 401
        assert failed_after_unlock.json()["remaining_attempts"] == 4
        released = await PatientOtpChallenge.get()
        assert released.locked_until is None
        assert released.failed_attempts == 1

        reissued = await self.issue()
        assert reissued.status_code == 200
        assert len(self.delivery.sent) == 2

    async def test_expired_otp_is_rejected(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200
        challenge = await PatientOtpChallenge.get()
        challenge.expires_at = now() - timedelta(seconds=1)
        await challenge.save(update_fields=["expires_at"])

        expired = await self.verify(OTP)

        assert expired.status_code == 410
        assert expired.json()["code"] == "OTP_EXPIRED"

    async def test_issue_and_verify_use_the_time_after_row_locks_are_acquired(self) -> None:
        await make_link()
        before_lock = now()
        after_lock = before_lock + timedelta(seconds=4)
        with patch("app.services.patient_otp.now", side_effect=[before_lock, after_lock]):
            issued = await self.issue()
        assert issued.status_code == 200
        challenge = await PatientOtpChallenge.get()
        assert challenge.issued_at == after_lock
        assert challenge.expires_at == after_lock + OTP_TTL

        challenge.expires_at = after_lock + timedelta(seconds=2)
        await challenge.save(update_fields=["expires_at"])
        with patch(
            "app.services.patient_otp.now",
            side_effect=[after_lock + timedelta(seconds=1), after_lock + timedelta(seconds=3)],
        ):
            expired = await self.verify(OTP)
        assert expired.status_code == 410
        assert expired.json()["code"] == "OTP_EXPIRED"

    async def test_delivery_failure_rolls_back_the_challenge(self) -> None:
        await make_link()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(FailingDelivery(), secret_key=SECRET)

        failed = await self.issue()

        assert failed.status_code == 503
        assert failed.json()["code"] == "OTP_DELIVERY_UNAVAILABLE"
        assert OTP not in failed.text
        assert await PatientOtpChallenge.all().count() == 0

    async def test_failed_reissue_restores_the_previous_otp_without_resetting_failures(self) -> None:
        await make_link()
        assert (await self.issue()).status_code == 200
        challenge = await PatientOtpChallenge.get()
        challenge.failed_attempts = 1
        challenge.issued_at = now() - OTP_RESEND_COOLDOWN - timedelta(seconds=1)
        await challenge.save(update_fields=["failed_attempts", "issued_at"])
        previous = (
            challenge.otp_digest,
            challenge.otp_salt,
            challenge.expires_at,
            challenge.issued_at,
        )
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(FailingDelivery(), secret_key=SECRET)

        failed = await self.issue()

        assert failed.status_code == 503
        restored = await PatientOtpChallenge.get()
        assert (
            restored.otp_digest,
            restored.otp_salt,
            restored.expires_at,
            restored.issued_at,
        ) == previous
        assert restored.failed_attempts == 1

    async def test_missing_expired_and_unapproved_links_do_not_issue_an_otp(self) -> None:
        link = await make_link()

        async with self.client() as client:
            missing = await client.post(
                "/api/v1/patient-auth/otp/issue",
                json={"link_token": "not-a-real-link"},
            )
        assert missing.status_code == 404
        assert missing.json()["code"] == "LINK_NOT_FOUND"

        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])
        expired = await self.issue()
        assert expired.status_code == 410
        assert expired.json()["code"] == "LINK_EXPIRED"

        link.expires_at = now() + timedelta(hours=1)
        await link.save(update_fields=["expires_at"])
        guide = await GuideDocument.get(guide_document_id=link.guide_document_id)
        guide.status = GuideStatus.APPROVAL_PENDING
        await guide.save(update_fields=["status"])
        unapproved = await self.issue()
        assert unapproved.status_code == 404
        assert unapproved.json()["code"] == "LINK_NOT_FOUND"
