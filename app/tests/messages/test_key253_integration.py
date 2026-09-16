"""KEY-253: real dispatch state feeds badge calculation; no external SMS."""

import re

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core import config
from app.models.catalog import MessageTemplate, MessageTemplateKind
from app.models.visits import (
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
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
        await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)
        loaded = await load_flag_inputs(latest, guide.hospital_id)
        assert loaded[visit.patient_id].viewed is True
        assert PatientFlag.UNREAD_STREAK not in flags_of(loaded[visit.patient_id], now().date())

    async def test_resent_same_round_is_counted_once(self) -> None:
        first = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        guide = await first.guide_document
        visit = await Visit.get(visit_id=guide.visit_id)
        first.status = GuideMessageStatus.SENT
        await first.save(update_fields=["status"])
        for kind, sequence in ((GuideMessageKind.CHECK_D7, 1), (GuideMessageKind.CHECK_D15, 0)):
            await GuideMessage.create(
                guide_document=guide,
                kind=kind,
                scheduled_at=first.scheduled_at,
                status=GuideMessageStatus.SENT,
                resend_sequence=sequence,
            )
        loaded = await load_flag_inputs({visit.patient_id: visit}, guide.hospital_id)
        assert loaded[visit.patient_id].checks_sent == 2
        assert PatientFlag.UNREAD_STREAK not in flags_of(loaded[visit.patient_id], now().date())

    async def test_dispatch_uses_latest_saved_hospital_template(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        guide = await message.guide_document
        visit = await Visit.get(visit_id=guide.visit_id)
        template = await MessageTemplate.create(
            hospital_id=guide.hospital_id,
            kind=MessageTemplateKind.CHECK_D7,
            body="이전 문구: {의원명} {환자명} {일차} {링크}",
        )
        template.body = "[{의원명}] {환자명}님 {일차}일 확인: {링크}"
        await template.save(update_fields=["body"])
        sender = _CountingSender()
        result = await dispatch_message(message.pk, sender)
        assert result is not None and result.status == GuideMessageStatus.SENT
        assert len(sender.calls) == 1
        body = sender.calls[0][1]
        await message.refresh_from_db()
        from app.services.message_dispatch import check_day_number

        assert message.sent_at is not None
        day_number = check_day_number(visit.visited_at, message.sent_at)
        expected_head = (
            f"[KEY-249 합성의원] 합성환자님 {day_number}일 확인: "
            f"{config.PATIENT_WEB_BASE_URL.rstrip('/')}/patient_wireframe/html/otp.html#t="
        )
        assert body.startswith(expected_head)
        raw_token = body.removeprefix(expected_head)
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", raw_token)
        assert message.sent_body == expected_head + "[REDACTED]"
        assert raw_token not in message.sent_body
