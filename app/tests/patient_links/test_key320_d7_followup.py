"""D+7 저장 뒤 예약 문자와 완료 화면이 같은 DB 상태를 보는지 확인한다."""

from datetime import timedelta

from tortoise.timezone import now

from app.core.time import DISPLAY_TIMEZONE
from app.models.visits import (
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
    VisitStatus,
)
from app.services.message_dispatch import dispatch_message
from app.services.patient_flags import PatientFlag, flags_of, load_flag_inputs, stopped_dosing
from app.tests.messages.test_key249_dispatch_pipeline import _CountingSender, make_due_message
from app.tests.patient_links.test_key151_checkins import TOKEN, CheckInTestCase, make_linked_guide
from app.tests.patient_links.test_patient_links import make_hospital, make_staff


class TestD7FinalAnswer(CheckInTestCase):
    async def test_save_cancels_d7_and_returns_only_known_next_dates(self) -> None:
        hospital = await make_hospital("KEY-320 합성의원")
        guide = await make_linked_guide(hospital)
        visit = await Visit.get(visit_id=guide.visit_id)
        d7 = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D7,
            scheduled_at=now() + timedelta(days=1),
        )
        d15 = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D15,
            scheduled_at=now() + timedelta(days=8),
        )
        planned_visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient_id=visit.patient_id,
            visited_at=now() + timedelta(days=10),
            status=VisitStatus.SCHEDULED,
        )

        async with self.client() as client:
            saved = await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "stopped_side_effect"})
            form = await client.get(f"/api/v1/checkins/{TOKEN}")

        assert saved.status_code == 201
        await d7.refresh_from_db()
        assert d7.status is GuideMessageStatus.CANCELED
        assert saved.json()["next_checkin"] == d15.scheduled_at.astimezone(DISPLAY_TIMEZONE).date().isoformat()
        assert saved.json()["next_visit"] == planned_visit.visited_at.astimezone(DISPLAY_TIMEZONE).date().isoformat()
        assert form.json()["next_checkin"] == saved.json()["next_checkin"]
        assert form.json()["next_visit"] == saved.json()["next_visit"]
        assert visit.patient_id in await stopped_dosing({visit.patient_id: visit})

    async def test_no_known_next_dates_are_null(self) -> None:
        hospital = await make_hospital("KEY-320 일정 없는 합성의원")
        await make_linked_guide(hospital)

        async with self.client() as client:
            saved = await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking"})

        assert saved.status_code == 201
        assert saved.json()["next_checkin"] is None
        assert saved.json()["next_visit"] is None

    async def test_answered_d7_cannot_be_requested_from_history_again(self) -> None:
        hospital = await make_hospital("KEY-320 재발송 합성의원")
        guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key320-staff", ["staff"])
        sent = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D7,
            status=GuideMessageStatus.SENT,
            scheduled_at=now() - timedelta(minutes=1),
            sent_at=now(),
        )

        async with self.client() as client:
            assert (await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking"})).status_code == 201
            blocked = await client.post(
                f"/api/v1/messages/history/{sent.guide_message_id}/resend",
                headers=await self.headers(staff),
            )

        assert blocked.status_code == 409
        assert blocked.json()["code"] == "MESSAGE_NOT_RESENDABLE"
        assert not await GuideMessage.filter(resend_of_message_id=sent.guide_message_id).exists()

    async def test_late_d7_job_cannot_send_after_answer(self) -> None:
        hospital = await make_hospital("KEY-320 늦은 작업 합성의원")
        guide = await make_linked_guide(hospital)
        async with self.client() as client:
            assert (await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking"})).status_code == 201
        message = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D7,
            scheduled_at=now() - timedelta(minutes=1),
        )
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None and result.status is GuideMessageStatus.CANCELED
        assert sender.calls == []

    async def test_three_unread_check_rounds_raise_the_existing_flag(self) -> None:
        hospital = await make_hospital("KEY-320 무응답 합성의원")
        guide = await make_linked_guide(hospital)
        visit = await Visit.get(visit_id=guide.visit_id)
        for kind in (GuideMessageKind.CHECK_D7, GuideMessageKind.CHECK_D15, GuideMessageKind.CHECK_D30):
            await GuideMessage.create(
                guide_document=guide,
                kind=kind,
                status=GuideMessageStatus.SENT,
                scheduled_at=now(),
                sent_at=now(),
            )

        inputs = await load_flag_inputs({visit.patient_id: visit}, hospital.hospital_id)

        assert PatientFlag.UNREAD_STREAK in flags_of(inputs[visit.patient_id], now().date())

    async def test_d7_is_sent_once_with_the_actual_day_and_masked_storage(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        guide = await message.guide_document
        visit = await Visit.get(visit_id=guide.visit_id)
        # check_day_number() 자체로 기대값을 계산하면 그 함수의 off-by-one·
        # 타임존 버그를 이 테스트가 못 잡는다(2heej 리뷰) — visited_at을
        # 정확히 7일 전으로 고정하고, 기대 일차를 리터럴 7로 박아 둔다.
        visit.visited_at = now() - timedelta(days=7)
        await visit.save(update_fields=["visited_at"])
        sender = _CountingSender()

        first = await dispatch_message(message.guide_message_id, sender)
        second = await dispatch_message(message.guide_message_id, sender)

        assert first is not None and first.status is GuideMessageStatus.SENT
        assert second is None
        assert len(sender.calls) == 1
        await message.refresh_from_db()
        assert message.sent_at is not None and message.sent_body is not None
        assert "복약 7일째" in sender.calls[0][1]
        assert "복약 7일째" in message.sent_body
        assert "#t=[REDACTED]" in message.sent_body
