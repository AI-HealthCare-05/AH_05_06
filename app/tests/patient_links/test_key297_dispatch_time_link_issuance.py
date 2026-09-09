"""발송 직전 환자 링크 발급·회전 — KEY-297.

`PatientLinkService.issue_for_dispatch()`가 이 티켓의 핵심이다: 예약 승인
시점이 아니라 **워커가 실제로 문자를 보내는 순간** 원문을 새로 만든다.
"""

import asyncio
from datetime import timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideMessageKind,
    GuideStatus,
    PatientGuideLink,
    PatientOtpChallenge,
    Visit,
)
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

        raw_token, expires_at = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=111,
            message_kind=GuideMessageKind.GUIDE,
        )

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest == digest_link_token(raw_token)
        assert link.issued_by == SYSTEM_ISSUER_ID
        assert link.last_message_id == 111
        assert link.issued_at is not None
        assert (link.expires_at - link.issued_at) == DISPATCH_LINK_TTL
        assert expires_at == link.expires_at

    async def test_the_raw_token_is_not_the_stored_digest(self) -> None:
        """당연해 보이지만, 이걸 틀리면 DB 덤프만으로 환자 화면이 열린다."""
        guide = await make_approved_guide()

        raw_token, _ = await PatientLinkService().issue_for_dispatch(
            guide.guide_document_id,
            message_id=1,
            message_kind=GuideMessageKind.GUIDE,
        )

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest != raw_token
        assert len(link.token_digest) == 64  # sha256 hex


class TestRotationOnSubsequentDispatch(TestCase):
    async def test_a_second_dispatch_rotates_to_a_different_token(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first_raw, _ = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=1,
            message_kind=GuideMessageKind.GUIDE,
        )
        second_raw, _ = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=2,
            message_kind=GuideMessageKind.CHECK_D7,
        )

        assert first_raw != second_raw
        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert link.token_digest == digest_link_token(second_raw)
        assert link.token_digest != digest_link_token(first_raw)
        # 링크는 하나만 있다 — 새 행을 또 만들지 않고 같은 행을 회전한다.
        assert await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).count() == 1

    async def test_rotation_updates_last_message_id_and_issued_at(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=1,
            message_kind=GuideMessageKind.GUIDE,
        )
        first = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)

        await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=2,
            message_kind=GuideMessageKind.CHECK_D7,
        )
        second = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)

        assert second.last_message_id == 2
        assert second.issued_at is not None
        assert first.issued_at is not None
        assert second.issued_at >= first.issued_at

    async def test_the_old_token_stops_working_after_rotation(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first_raw, _ = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=1,
            message_kind=GuideMessageKind.GUIDE,
        )
        await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=2,
            message_kind=GuideMessageKind.CHECK_D7,
        )

        assert await PatientGuideLink.filter(token_digest=digest_link_token(first_raw)).exists() is False


class TestRotationInvalidatesTheOldOtpChallenge(TestCase):
    async def test_an_active_otp_challenge_is_expired_on_rotation(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()
        await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=1,
            message_kind=GuideMessageKind.GUIDE,
        )
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

        await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=2,
            message_kind=GuideMessageKind.CHECK_D7,
        )

        challenge = await PatientOtpChallenge.get(patient_guide_link_id=link.patient_guide_link_id)
        assert challenge.expires_at <= now()
        # 실패 횟수·잠금은 건드리지 않는다 — _invalidate_otp의 기존 계약(KEY-223)과 같다.
        assert challenge.failed_attempts == 0


class TestDispatchAuditTrail(TestCase):
    async def test_each_issuance_and_rotation_is_append_only_and_contains_no_token(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first_raw, _ = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=11,
            message_kind=GuideMessageKind.GUIDE,
        )
        second_raw, _ = await service.issue_for_dispatch(
            guide.guide_document_id,
            message_id=12,
            message_kind=GuideMessageKind.CHECK_D7,
        )

        events = await GuideEvent.filter(
            guide_document_id=guide.guide_document_id,
            event_type=GuideEventType.LINK_REISSUED,
        ).order_by("guide_event_id")
        assert len(events) == 2
        assert events[0].actor_id == SYSTEM_ISSUER_ID
        assert "action=ISSUED" in (events[0].reason or "")
        assert "message_kind=GUIDE" in (events[0].reason or "")
        assert "message_id=11" in (events[0].reason or "")
        assert "action=ROTATED" in (events[1].reason or "")
        assert "message_kind=CHECK_D7" in (events[1].reason or "")
        assert "message_id=12" in (events[1].reason or "")
        audit_text = " ".join(event.reason or "" for event in events)
        assert "issued_at=" in audit_text
        assert "expires_at=" in audit_text
        assert first_raw not in audit_text
        assert second_raw not in audit_text


class TestConcurrentFirstIssuance(TestCase):
    async def test_two_first_dispatches_do_not_raise_an_integrity_error(self) -> None:
        guide = await make_approved_guide()
        service = PatientLinkService()

        first, second = await asyncio.gather(
            service.issue_for_dispatch(
                guide.guide_document_id,
                message_id=21,
                message_kind=GuideMessageKind.GUIDE,
            ),
            service.issue_for_dispatch(
                guide.guide_document_id,
                message_id=22,
                message_kind=GuideMessageKind.CHECK_D7,
            ),
        )

        assert first[0] != second[0]
        assert await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).count() == 1
        assert await GuideEvent.filter(guide_document_id=guide.guide_document_id).count() == 2
