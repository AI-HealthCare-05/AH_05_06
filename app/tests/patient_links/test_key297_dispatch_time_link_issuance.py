"""발송 직전 환자 링크 발급·회전 — KEY-297.

`PatientLinkService.issue_for_dispatch()`가 이 티켓의 핵심이다: 예약 승인
시점이 아니라 **워커가 실제로 문자를 보내는 순간** 원문을 새로 만든다.
"""

from datetime import timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink, PatientOtpChallenge, Visit
from app.services.patient_links import DISPATCH_LINK_TTL, SYSTEM_ISSUER_ID, PatientLinkService, digest_link_token
from app.services.patient_otp import OTP_TTL, _otp_digest


async def make_approved_guide() -> GuideDocument:
    hospital = await Hospital.create(name="KEY-297 합성의원")
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-KEY297-01",
        name="합성환자",
        birth_date="1990-01-02",
        phone="01000009297",
        sms_consent=True,
    )
    visit = await Visit.create(hospital_id=hospital.hospital_id, patient=patient, visited_at=now() - timedelta(days=1))
    return await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=GuideStatus.SCHEDULED_TO_SEND,
        approved_by=1,
        approved_at=now(),
    )


class TestFirstIssuance(TestCase):
    async def test_creates_a_link_row_when_none_exists(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        raw_token = await service.issue_for_dispatch(guide.guide_document_id, message_id=111)

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest == digest_link_token(raw_token)
        assert link.issued_by == SYSTEM_ISSUER_ID
        assert link.last_message_id == 111
        assert link.issued_at is not None
        assert (link.expires_at - link.issued_at) == DISPATCH_LINK_TTL

    async def test_the_raw_token_is_not_the_stored_digest(self) -> None:
        """당연해 보이지만, 이걸 틀리면 DB 덤프만으로 환자 화면이 열린다."""
        guide = await make_approved_guide()

        raw_token = await PatientLinkService().issue_for_dispatch(guide.guide_document_id, message_id=1)

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest != raw_token
        assert len(link.token_digest) == 64  # sha256 hex


class TestRotationOnSubsequentDispatch(TestCase):
    async def test_a_second_dispatch_rotates_to_a_different_token(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first_raw = await service.issue_for_dispatch(guide.guide_document_id, message_id=1)
        second_raw = await service.issue_for_dispatch(guide.guide_document_id, message_id=2)

        assert first_raw != second_raw
        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest == digest_link_token(second_raw)
        assert link.token_digest != digest_link_token(first_raw)
        # 링크는 하나만 있다 — 새 행을 또 만들지 않고 같은 행을 회전한다.
        assert await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).count() == 1

    async def test_rotation_updates_last_message_id_and_issued_at(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        await service.issue_for_dispatch(guide.guide_document_id, message_id=1)
        first = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)

        await service.issue_for_dispatch(guide.guide_document_id, message_id=2)
        second = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)

        assert second.last_message_id == 2
        assert second.issued_at is not None
        assert first.issued_at is not None
        assert second.issued_at >= first.issued_at

    async def test_the_old_token_stops_working_after_rotation(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first_raw = await service.issue_for_dispatch(guide.guide_document_id, message_id=1)
        await service.issue_for_dispatch(guide.guide_document_id, message_id=2)

        assert await PatientGuideLink.filter(token_digest=digest_link_token(first_raw)).exists() is False


class TestRotationInvalidatesTheOldOtpChallenge(TestCase):
    async def test_an_active_otp_challenge_is_expired_on_rotation(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()
        await service.issue_for_dispatch(guide.guide_document_id, message_id=1)
        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)

        secret = "synthetic-key297-test-secret"
        salt = "aa" * 16  # 유효한 hex 문자열 — _otp_digest가 bytes.fromhex로 읽는다
        await PatientOtpChallenge.create(
            patient_guide_link_id=link.patient_guide_link_id,
            otp_digest=_otp_digest("000000", salt, secret),
            otp_salt=salt,
            expires_at=now() + OTP_TTL,
            issued_at=now(),
        )

        await service.issue_for_dispatch(guide.guide_document_id, message_id=2)

        challenge = await PatientOtpChallenge.get(patient_guide_link_id=link.patient_guide_link_id)
        assert challenge.expires_at <= now()
        # 실패 횟수·잠금은 건드리지 않는다 — _invalidate_otp의 기존 계약(KEY-223)과 같다.
        assert challenge.failed_attempts == 0
