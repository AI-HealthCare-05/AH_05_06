"""챗봇 컨텍스트 서비스 정상·예외 케이스 — KEY-89."""

from datetime import timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.auth_errors import AuthError
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientGuideLink,
    Visit,
)
from app.services.chatbot_context import ApprovedChatbotContext, ChatbotContextService
from app.services.patient_links import digest_link_token

_TOKEN = "KEY89testTokenABCDEFGHIJKLMNOP0123456789abcd"
_OTHER_TOKEN = "KEY89testTokenOTHER00000000000000000000000B"
_MIDNIGHT_TOKEN = "KEY89testTokenMIDNIGHT000000000000000000000C"


async def _make_guide(hospital: Hospital, token: str = _TOKEN) -> GuideDocument:
    """SCHEDULED_TO_SEND 안내와 지정 토큰의 PatientGuideLink를 함께 생성한다."""
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no=f"KEY89-{token[-4:]}",
        name="합성환자",
        birth_date="1991-02-03",
        phone="01033334444",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at="2026-08-20T09:00:00+09:00",
    )
    guide = await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=GuideStatus.SCHEDULED_TO_SEND,
        approved_by=1,
        approved_at=now(),
    )
    for key, body in [
        (GuideSectionKey.MEDICATION, "합성 복약 안내"),
        (GuideSectionKey.CAUTION, "합성 주의 안내"),
        (GuideSectionKey.EMERGENCY, "합성 응급 안내"),
        (GuideSectionKey.LIFE, "합성 생활관리 안내"),
        (GuideSectionKey.MESSAGES, "합성 메시지 — 컨텍스트 제외 대상"),
    ]:
        await GuideSection.create(
            guide_document=guide,
            section_key=key,
            generated_body=body,
        )
    await PatientGuideLink.create(
        guide_document=guide,
        token_digest=digest_link_token(token),
        expires_at=now() + timedelta(hours=72),
        issued_by=1,
    )
    return guide


class TestApprovedChatbotContext(TestCase):
    async def test_approved_guide_returns_context(self) -> None:
        hospital = await Hospital.create(name="KEY-89 합성의원")
        guide = await _make_guide(hospital)

        ctx = await ChatbotContextService().get_context(_TOKEN)

        assert isinstance(ctx, ApprovedChatbotContext)
        assert ctx.guide_document_id == guide.guide_document_id
        assert ctx.visit_id == guide.visit_id
        assert ctx.clinic_name == "KEY-89 합성의원"
        assert ctx.encounter_date.isoformat() == "2026-08-20"
        assert ctx.approved_at is not None

    async def test_medication_section_goes_into_medication_slots(self) -> None:
        hospital = await Hospital.create(name="KEY-89 섹션매핑 합성의원")
        await _make_guide(hospital)

        ctx = await ChatbotContextService().get_context(_TOKEN)

        assert len(ctx.medication_sections) == 1
        assert ctx.medication_sections[0].key == "medication"
        assert ctx.medication_sections[0].body == "합성 복약 안내"

    async def test_caution_and_emergency_go_into_caution_slots_in_order(self) -> None:
        hospital = await Hospital.create(name="KEY-89 주의섹션 합성의원")
        await _make_guide(hospital)

        ctx = await ChatbotContextService().get_context(_TOKEN)

        assert len(ctx.caution_sections) == 2
        assert ctx.caution_sections[0].key == "caution"
        assert ctx.caution_sections[1].key == "emergency"

    async def test_life_section_goes_into_lifestyle_slots(self) -> None:
        hospital = await Hospital.create(name="KEY-89 생활관리 합성의원")
        await _make_guide(hospital)

        ctx = await ChatbotContextService().get_context(_TOKEN)

        assert len(ctx.lifestyle_sections) == 1
        assert ctx.lifestyle_sections[0].key == "life"
        assert ctx.lifestyle_sections[0].body == "합성 생활관리 안내"

    async def test_messages_section_is_excluded_from_context(self) -> None:
        hospital = await Hospital.create(name="KEY-89 메시지제외 합성의원")
        await _make_guide(hospital)

        ctx = await ChatbotContextService().get_context(_TOKEN)

        all_keys = (
            [s.key for s in ctx.medication_sections]
            + [s.key for s in ctx.caution_sections]
            + [s.key for s in ctx.lifestyle_sections]
        )
        assert "messages" not in all_keys

    async def test_edited_body_takes_priority_over_generated_body(self) -> None:
        hospital = await Hospital.create(name="KEY-89 수정본 합성의원")
        guide = await _make_guide(hospital)

        section = await GuideSection.get(
            guide_document=guide,
            section_key=GuideSectionKey.MEDICATION,
        )
        section.edited_body = "의사가 수정한 복약 안내"
        await section.save(update_fields=["edited_body", "updated_at"])

        ctx = await ChatbotContextService().get_context(_TOKEN)

        assert ctx.medication_sections[0].body == "의사가 수정한 복약 안내"

    async def test_expired_token_is_rejected(self) -> None:
        hospital = await Hospital.create(name="KEY-89 만료 합성의원")
        guide = await _make_guide(hospital)

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        with self.assertRaises(AuthError) as cm:
            await ChatbotContextService().get_context(_TOKEN)
        assert cm.exception.code == "LINK_EXPIRED"

    async def test_unknown_token_is_rejected(self) -> None:
        with self.assertRaises(AuthError) as cm:
            await ChatbotContextService().get_context("nonexistent-token-xyz")
        assert cm.exception.code == "LINK_NOT_FOUND"

    async def test_encounter_date_uses_kst_not_utc(self) -> None:
        """KST 자정~오전 9시 방문은 UTC 날짜와 달라 .date() 직접 호출 시 하루 밀린다."""
        hospital = await Hospital.create(name="KEY-89 자정방문 합성의원")
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no="KEY89-MIDNIGHT",
            name="자정합성환자",
            birth_date="1991-02-03",
            phone="01099998888",
            sms_consent=True,
        )
        # KST 00:30 — UTC 로 옮기면 전날이 되는 시각이다. 지금은 ORM 이 Asia/Seoul 을
        # 붙여 돌려주므로 어느 쪽으로 뽑아도 08-20 이지만, 저장을 UTC 로 정규화하는
        # 날 이 케이스가 먼저 운다.
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            visited_at="2026-08-20T00:30:00+09:00",
        )
        guide = await GuideDocument.create(
            hospital_id=hospital.hospital_id,
            visit=visit,
            status=GuideStatus.SCHEDULED_TO_SEND,
            approved_by=1,
            approved_at=now(),
        )
        await GuideSection.create(
            guide_document=guide,
            section_key=GuideSectionKey.MEDICATION,
            generated_body="자정 복약 안내",
        )
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=digest_link_token(_MIDNIGHT_TOKEN),
            expires_at=now() + timedelta(hours=72),
            issued_by=1,
        )

        ctx = await ChatbotContextService().get_context(_MIDNIGHT_TOKEN)

        assert ctx.encounter_date.isoformat() == "2026-08-20"

    async def test_token_is_scoped_to_issuing_hospital(self) -> None:
        hospital_a = await Hospital.create(name="KEY-89 병원A")
        hospital_b = await Hospital.create(name="KEY-89 병원B")
        guide_a = await _make_guide(hospital_a, token=_TOKEN)
        guide_b = await _make_guide(hospital_b, token=_OTHER_TOKEN)

        ctx_a = await ChatbotContextService().get_context(_TOKEN)
        ctx_b = await ChatbotContextService().get_context(_OTHER_TOKEN)

        assert ctx_a.clinic_name == "KEY-89 병원A"
        assert ctx_b.clinic_name == "KEY-89 병원B"
        assert ctx_a.guide_document_id == guide_a.guide_document_id
        assert ctx_b.guide_document_id == guide_b.guide_document_id
