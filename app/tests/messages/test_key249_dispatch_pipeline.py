"""예약 문자 발송 파이프라인 — KEY-249.

`app/tests/messages/test_scheduled_messages.py` 의 주석이 이미 말해 둔 그대로다:
「아직 아무도 HELD·FAILED 를 만들지 않는다. 발송기 자체가 없어서 SCHEDULED 와
CANCELED 만 실제로 쓰인다.」이 파일이 그 발송기다.
"""

import asyncio
from datetime import timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.config import SmsProvider
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    PatientGuideLink,
    Visit,
)
from app.services.message_dispatch import (
    MAX_ATTEMPTS,
    backoff_seconds,
    dispatch_due_messages,
    dispatch_message,
)
from app.services.sms_sender import MockSmsSender, SmsDeliveryStatus, SmsSendError, SmsSendResult


class _CountingSender:
    """실제로 몇 번 호출됐는지 세는 발송기 — 중복 발송 검사에 쓴다."""

    def __init__(self, result: SmsSendResult | None = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._result = result or SmsSendResult(
            status=SmsDeliveryStatus.SENT, provider=SmsProvider.MOCK, provider_message_id="counted-1"
        )
        self._error = error

    async def send(self, to: str, body: str) -> SmsSendResult:
        self.calls.append((to, body))
        if self._error is not None:
            raise self._error
        return self._result


async def make_due_message(
    *,
    status: GuideMessageStatus = GuideMessageStatus.SCHEDULED,
    kind: GuideMessageKind = GuideMessageKind.GUIDE,
    scheduled_at=None,
    attempt_count: int = 0,
    hold: GuideMessageHold | None = None,
) -> GuideMessage:
    hospital = await Hospital.create(name="KEY-249 합성의원")
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-KEY249-01",
        name="합성환자",
        birth_date="1990-01-01",
        gender=PatientGender.FEMALE,
        phone="01000009249",
    )
    visit = await Visit.create(hospital_id=hospital.hospital_id, patient=patient, visited_at=now() - timedelta(days=1))
    guide = await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
    return await GuideMessage.create(
        guide_document=guide,
        kind=kind,
        status=status,
        scheduled_at=scheduled_at or now() - timedelta(minutes=1),
        attempt_count=attempt_count,
        hold_reason=hold,
    )


class TestDispatchSendsAndTransitions(TestCase):
    async def test_a_due_message_is_sent_and_marked_sent(self) -> None:
        message = await make_due_message()
        sender = MockSmsSender(provider_message_id="aligo-999")

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.SENT
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.SENT
        assert updated.sent_at is not None
        assert updated.provider_message_id == "aligo-999"
        assert updated.claim_token is None
        assert updated.attempt_count == 1
        assert updated.sent_body is not None
        assert "합성환자" in updated.sent_body
        assert "KEY-249 합성의원" in updated.sent_body

        # 발송 문구를 조립하며 링크도 하나 발급됐어야 한다.
        assert await PatientGuideLink.filter(guide_document_id=message.guide_document_id).exists()

    async def test_a_message_not_yet_due_is_left_alone(self) -> None:
        message = await make_due_message(scheduled_at=now() + timedelta(hours=1))

        result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is None
        unchanged = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert unchanged.status is GuideMessageStatus.SCHEDULED
        assert unchanged.sent_at is None

    async def test_held_messages_are_never_picked_up(self) -> None:
        await make_due_message(status=GuideMessageStatus.HELD, hold=GuideMessageHold.INVALID_PHONE)

        results = await dispatch_due_messages(MockSmsSender())

        assert results == []


class TestIdempotentClaim(TestCase):
    async def test_two_concurrent_dispatches_only_send_once(self) -> None:
        """같은 메시지를 두 워커가 동시에 집어도 발송기 호출은 한 번뿐이다."""
        message = await make_due_message()
        sender = _CountingSender()

        first, second = await asyncio.gather(
            dispatch_message(message.guide_message_id, sender),
            dispatch_message(message.guide_message_id, sender),
        )

        outcomes = [r for r in (first, second) if r is not None]
        assert len(outcomes) == 1
        assert len(sender.calls) == 1
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.SENT
        assert updated.attempt_count == 1

    async def test_rerunning_the_worker_after_success_does_nothing(self) -> None:
        """같은 메시지를 재실행해도(이미 SENT) 다시 보내지 않는다."""
        message = await make_due_message()
        sender = _CountingSender()
        await dispatch_message(message.guide_message_id, sender)

        again = await dispatch_message(message.guide_message_id, sender)

        assert again is None
        assert len(sender.calls) == 1


class TestRetryAndBackoff(TestCase):
    async def test_transport_failure_reschedules_with_backoff(self) -> None:
        message = await make_due_message()
        sender = _CountingSender(error=SmsSendError("provider_timeout"))
        before = now()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.SCHEDULED
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.SCHEDULED
        assert updated.claim_token is None
        assert updated.attempt_count == 1
        assert updated.provider_detail == "provider_timeout"
        # 다음 시도가 미래로 밀렸다 — 즉시 재시도하지 않는다.
        assert updated.scheduled_at > before + timedelta(seconds=backoff_seconds(1) - 5)

    async def test_retries_exhausted_end_in_failed(self) -> None:
        message = await make_due_message(attempt_count=MAX_ATTEMPTS - 1)
        sender = _CountingSender(error=SmsSendError("provider_timeout"))

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.FAILED
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.FAILED
        assert updated.attempt_count == MAX_ATTEMPTS
        assert updated.claim_token is None

    async def test_provider_rejection_fails_immediately_without_retry(self) -> None:
        """공급자가 명시적으로 거절하면(예: 잘못된 번호) 재시도해도 같은 결과다."""
        message = await make_due_message()
        sender = _CountingSender(
            result=SmsSendResult(status=SmsDeliveryStatus.FAILED, provider=SmsProvider.ALIGO, provider_code="-101")
        )

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.FAILED
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.FAILED
        assert updated.attempt_count == 1
        assert updated.provider_detail == "-101"

    def test_backoff_grows_exponentially_and_caps(self) -> None:
        assert backoff_seconds(1) == 60
        assert backoff_seconds(2) == 120
        assert backoff_seconds(3) == 240
        assert backoff_seconds(20) == 3600  # 상한.


class TestDispatchDueMessages(TestCase):
    async def test_processes_every_due_message_once(self) -> None:
        a = await make_due_message(kind=GuideMessageKind.GUIDE)
        b = await make_due_message(kind=GuideMessageKind.CHECK_D7)
        not_due = await make_due_message(scheduled_at=now() + timedelta(hours=1))

        results = await dispatch_due_messages(MockSmsSender())

        sent_ids = {r.guide_message_id for r in results}
        assert sent_ids == {a.guide_message_id, b.guide_message_id}
        assert not_due.guide_message_id not in sent_ids
