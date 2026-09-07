"""예약 문자 발송 파이프라인 — KEY-249.

`app/tests/messages/test_scheduled_messages.py` 의 주석이 이미 말해 둔 그대로다:
「아직 아무도 HELD·FAILED 를 만들지 않는다. 발송기 자체가 없어서 SCHEDULED 와
CANCELED 만 실제로 쓰인다.」이 파일이 그 발송기다.

`{링크}` 를 채우는 문제는 이 티켓 범위 밖으로 남겼다(PR 코멘트 참고) — 그래서
파이프라인 자체(claim·발송·상태전이·재시도·멱등성)를 검사하는 테스트는
`{링크}` 가 없는 커스텀 템플릿을 만들어서 그 문제를 우회한다. 실서비스
화면(스탭 UI)에서는 `{링크}` 를 지울 수 없지만(`MessageTemplateService`가
막는다), 여기서는 모델을 직접 써서 그 검사를 건너뛴다 — 파이프라인 검사와
링크 문제를 갈라 보기 위해서다.
"""

import asyncio
from datetime import timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.config import SmsProvider
from app.models.catalog import MessageTemplate
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageFailure,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
)
from app.services.message_dispatch import (
    MAX_ATTEMPTS,
    LinkNotAvailableError,
    _finish_failed,
    _finish_retryable,
    _finish_sent,
    backoff_seconds,
    dispatch_due_messages,
    dispatch_message,
    render_message_body,
)
from app.services.message_templates import MessageTemplateKind
from app.services.sms_sender import MockSmsSender, SmsDeliveryStatus, SmsSendError, SmsSendResult

#: {링크} 없는 문구 — 파이프라인 검사에서만 쓴다(실서비스 화면에서는 못 만든다).
LINK_FREE_BODY = "{환자명}님, {의원명}에서 합성 발송 확인용 문자입니다."


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
    hospital_name: str = "KEY-249 합성의원",
    link_free_template: bool = False,
) -> GuideMessage:
    hospital = await Hospital.create(name=hospital_name)
    if link_free_template:
        await MessageTemplate.create(
            hospital_id=hospital.hospital_id,
            kind=MessageTemplateKind(kind.value),
            body=LINK_FREE_BODY,
        )
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


class TestLinkVariableNotYetAvailable(TestCase):
    """{링크}/{예약링크}를 채울 방법이 아직 없다 — PR 코멘트로 남긴 그 문제.

    발송기가 없어서가 아니라, 원문 토큰을 다시 얻을 방법이 없어서다
    (PatientGuideLink는 재발급 정책이 미확정). 조용히 깨진 링크를 보내는
    대신, 명시적으로 실패시킨다.
    """

    async def test_render_raises_when_link_variable_is_required(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.GUIDE)

        try:
            await render_message_body(message)
            raised = False
        except LinkNotAvailableError:
            raised = True
        assert raised, "{링크}를 채울 수 없는데도 조용히 문구를 만들었다"

    async def test_dispatch_fails_immediately_without_retry(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.GUIDE)
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.FAILED
        assert sender.calls == []  # 발송기까지 가지도 않았다.
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.FAILED
        assert updated.attempt_count == 1  # 5번 돌지 않고 바로 종료.
        assert updated.provider_detail == "link_not_available_pending_policy"
        # AC2 — 화면에 실패 사유가 빈 값으로 보이면 안 된다(2heej 리뷰).
        assert updated.failure_code is GuideMessageFailure.CARRIER

    async def test_a_link_free_custom_template_is_unaffected(self) -> None:
        """의원이 링크 없는 커스텀 문구를 쓰면(파이프라인 검사 전용) 정상 발송된다."""
        message = await make_due_message(kind=GuideMessageKind.GUIDE, link_free_template=True)

        result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SENT


class TestDispatchSendsAndTransitions(TestCase):
    async def test_a_due_message_is_sent_and_marked_sent(self) -> None:
        message = await make_due_message(link_free_template=True)
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

    async def test_success_is_not_reported_when_claim_does_not_match(self) -> None:
        message = await make_due_message()
        await GuideMessage.filter(
            guide_message_id=message.guide_message_id,
        ).update(claim_token="current-owner")

        result = SmsSendResult(
            status=SmsDeliveryStatus.SENT,
            provider=SmsProvider.MOCK,
            provider_message_id="accepted-1",
        )

        with self.assertRaisesRegex(RuntimeError, "발송 결과 저장 실패"):
            await _finish_sent(
                message,
                "wrong-owner",
                now(),
                "합성 테스트 본문",
                result,
            )

        saved = await GuideMessage.get(
            guide_message_id=message.guide_message_id,
        )
        assert saved.status is GuideMessageStatus.SCHEDULED
        assert saved.claim_token == "current-owner"
        assert saved.sent_at is None
        assert saved.provider_message_id is None


class TestIdempotentClaim(TestCase):
    async def test_two_concurrent_dispatches_only_send_once(self) -> None:
        """같은 메시지를 두 워커가 동시에 집어도 발송기 호출은 한 번뿐이다."""
        message = await make_due_message(link_free_template=True)
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
        message = await make_due_message(link_free_template=True)
        sender = _CountingSender()
        await dispatch_message(message.guide_message_id, sender)

        again = await dispatch_message(message.guide_message_id, sender)

        assert again is None
        assert len(sender.calls) == 1


class TestRetryAndBackoff(TestCase):
    async def test_transport_failure_reschedules_with_backoff(self) -> None:
        message = await make_due_message(link_free_template=True)
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
        message = await make_due_message(link_free_template=True, attempt_count=MAX_ATTEMPTS - 1)
        sender = _CountingSender(error=SmsSendError("provider_timeout"))

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.FAILED
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.FAILED
        assert updated.attempt_count == MAX_ATTEMPTS
        assert updated.claim_token is None
        # AC2 — 화면에 실패 사유가 빈 값으로 보이면 안 된다(2heej 리뷰).
        assert updated.failure_code is GuideMessageFailure.CARRIER

    async def test_provider_rejection_fails_immediately_without_retry(self) -> None:
        """공급자가 명시적으로 거절하면(예: 잘못된 번호) 재시도해도 같은 결과다."""
        message = await make_due_message(link_free_template=True)
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
        # AC2 — 화면에 실패 사유가 빈 값으로 보이면 안 된다(2heej 리뷰).
        assert updated.failure_code is GuideMessageFailure.CARRIER

    async def test_provider_rejection_without_a_code_still_gets_a_failure_reason(self) -> None:
        """MockSmsSender(FAILED)처럼 provider_code가 아예 없어도 failure_code는 채운다."""
        message = await make_due_message(link_free_template=True)
        sender = _CountingSender(result=SmsSendResult(status=SmsDeliveryStatus.FAILED, provider=SmsProvider.MOCK))

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.FAILED
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.failure_code is GuideMessageFailure.CARRIER

    def test_backoff_grows_exponentially_and_caps(self) -> None:
        assert backoff_seconds(1) == 60
        assert backoff_seconds(2) == 120
        assert backoff_seconds(3) == 240
        assert backoff_seconds(20) == 3600  # 상한.


class TestDispatchDueMessages(TestCase):
    async def test_processes_every_due_message_once(self) -> None:
        a = await make_due_message(
            kind=GuideMessageKind.GUIDE,
            hospital_name="KEY-249 안내문 합성의원",
            link_free_template=True,
        )
        b = await make_due_message(
            kind=GuideMessageKind.CHECK_D7,
            hospital_name="KEY-249 확인문자 합성의원",
            link_free_template=True,
        )
        not_due = await make_due_message(
            scheduled_at=now() + timedelta(hours=1),
            hospital_name="KEY-249 미래예약 합성의원",
        )

        results = await dispatch_due_messages(MockSmsSender())

        sent_ids = {r.guide_message_id for r in results}
        assert sent_ids == {a.guide_message_id, b.guide_message_id}
        assert not_due.guide_message_id not in sent_ids


class TestDispatchResultOwnership(TestCase):
    async def test_failed_result_requires_matching_claim(self) -> None:
        message = await make_due_message()
        await GuideMessage.filter(
            guide_message_id=message.guide_message_id,
        ).update(claim_token="current-owner")

        with self.assertRaisesRegex(RuntimeError, "발송 결과 저장 실패"):
            await _finish_failed(
                message,
                "wrong-owner",
                provider_detail="provider_rejected",
            )

        saved = await GuideMessage.get(
            guide_message_id=message.guide_message_id,
        )
        assert saved.status is GuideMessageStatus.SCHEDULED
        assert saved.claim_token == "current-owner"
        assert saved.attempt_count == 0
        assert saved.provider_detail is None

    async def test_retry_requires_matching_claim(self) -> None:
        message = await make_due_message()
        original_at = message.scheduled_at
        await GuideMessage.filter(
            guide_message_id=message.guide_message_id,
        ).update(claim_token="current-owner")

        with self.assertRaisesRegex(RuntimeError, "발송 결과 저장 실패"):
            await _finish_retryable(
                message,
                "wrong-owner",
                now(),
                provider_detail="provider_timeout",
            )

        saved = await GuideMessage.get(
            guide_message_id=message.guide_message_id,
        )
        assert saved.status is GuideMessageStatus.SCHEDULED
        assert saved.claim_token == "current-owner"
        assert saved.scheduled_at == original_at
        assert saved.attempt_count == 0
        assert saved.provider_detail is None

    async def test_exhausted_retry_requires_matching_claim(self) -> None:
        message = await make_due_message(attempt_count=MAX_ATTEMPTS - 1)
        await GuideMessage.filter(
            guide_message_id=message.guide_message_id,
        ).update(claim_token="current-owner")

        with self.assertRaisesRegex(RuntimeError, "발송 결과 저장 실패"):
            await _finish_retryable(
                message,
                "wrong-owner",
                now(),
                provider_detail="provider_timeout",
            )

        saved = await GuideMessage.get(
            guide_message_id=message.guide_message_id,
        )
        assert saved.status is GuideMessageStatus.SCHEDULED
        assert saved.claim_token == "current-owner"
        assert saved.attempt_count == MAX_ATTEMPTS - 1
        assert saved.provider_detail is None
