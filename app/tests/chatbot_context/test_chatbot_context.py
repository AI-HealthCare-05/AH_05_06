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


async def _make_guide(hospital: Hospital) -> GuideDocument:
    """SCHEDULED_TO_SEND 안내와 패턴 토큰의 PatientGuideLink를 함께 생성한다."""
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="KEY89-P01",
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
        token_digest=digest_link_token(_TOKEN),
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
