"""KEY-253: real dispatch state feeds badge calculation; no external SMS."""

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.models.catalog import MessageTemplate, MessageTemplateKind
from app.models.visits import GuideMessage, GuideMessageKind, GuideMessageStatus, Visit
from app.services.message_dispatch import dispatch_message
from app.services.patient_flags import PatientFlag, flags_of, load_flag_inputs
from app.tests.messages.test_key249_dispatch_pipeline import _CountingSender, make_due_message


class TestDispatchBadgeIntegration(TestCase):
    async def test_badge_requires_three_distinct_successful_check_rounds(self) -> None:
        first = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        guide = await first.guide_document
        visit = await Visit.get(visit_id=guide.visit_id)
        latest = {visit.patient_id: visit}
        sender = _CountingSender()
        for index, kind in enumerate(
            (GuideMessageKind.CHECK_D7, GuideMessageKind.CHECK_D15, GuideMessageKind.CHECK_D30)
        ):
            message = (
                first
                if index == 0
                else await GuideMessage.create(
                    guide_document=guide,
                    kind=kind,
                    scheduled_at=first.scheduled_at,
                    status=GuideMessageStatus.SCHEDULED,
                )
            )
            result = await dispatch_message(message.pk, sender)
            assert result is not None and result.status == GuideMessageStatus.SENT
            loaded = await load_flag_inputs(latest, guide.hospital_id)
            assert loaded[visit.patient_id].checks_sent == index + 1
            assert (PatientFlag.UNREAD_STREAK in flags_of(loaded[visit.patient_id], now().date())) == (index == 2)
        assert len(sender.calls) == 3

    async def test_dispatch_uses_latest_saved_hospital_template(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        guide = await message.guide_document
        await MessageTemplate.create(
            hospital_id=guide.hospital_id,
            kind=MessageTemplateKind.CHECK_D7,
            body="[{의원명}] {환자명}님 {일차}일 확인: {링크}",
        )
        sender = _CountingSender()
        result = await dispatch_message(message.pk, sender)
        assert result is not None and result.status == GuideMessageStatus.SENT
        assert len(sender.calls) == 1
        body = sender.calls[0][1]
        assert body.startswith("[KEY-249 합성의원] 합성환자님 7일 확인: ")
        assert "{" not in body
        await message.refresh_from_db()
        assert message.sent_body is not None and "[REDACTED]" in message.sent_body
