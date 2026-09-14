"""발송 직전 게이트 — 생성 후 안전검증 미통과 시 HELD — KEY-289.

guide_safety_check(POST_GENERATE, BLOCK) 레코드가 있으면 SAFETY_CHECK_FAILED로 막고,
기존 미승인·원본 미삭제 게이트와 독립적으로 동작함을 검증한다.
"""

from tortoise.contrib.test import TestCase

from app.models.visits import (
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageStatus,
    GuideSafetyCheck,
    SafetyCheckStage,
    SafetyCheckVerdict,
)
from app.services.dispatch_gate import gate_hold_reason
from app.services.message_dispatch import dispatch_message
from app.services.safety_check import CHECKER_VERSION
from app.services.sms_sender import MockSmsSender
from app.tests.messages.test_key249_dispatch_pipeline import make_due_message


async def _attach_safety_check(
    message: GuideMessage,
    *,
    stage: SafetyCheckStage,
    verdict: SafetyCheckVerdict,
    reason_code: str | None = None,
) -> GuideSafetyCheck:
    return await GuideSafetyCheck.create(
        guide_document_id=message.guide_document_id,
        stage=stage,
        verdict=verdict,
        reason_code=reason_code,
        checker_version=CHECKER_VERSION,
    )


class TestSafetyCheckGate(TestCase):
    async def test_no_safety_check_record_passes(self) -> None:
        """레코드 없음(고정 템플릿 경로)은 통과한다."""
        message = await make_due_message(approved=True)

        assert await gate_hold_reason(message) is None

    async def test_post_generate_pass_record_passes(self) -> None:
        """POST_GENERATE PASS 레코드가 있으면 통과한다."""
        message = await make_due_message(approved=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.PASS,
        )

        assert await gate_hold_reason(message) is None

    async def test_post_generate_block_record_is_held(self) -> None:
        """POST_GENERATE BLOCK 레코드가 있으면 SAFETY_CHECK_FAILED를 반환한다."""
        message = await make_due_message(approved=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.BLOCK,
            reason_code="EXTRA_DRUG",
        )

        assert await gate_hold_reason(message) is GuideMessageHold.SAFETY_CHECK_FAILED

    async def test_pre_generate_block_does_not_trigger_safety_gate(self) -> None:
        """PRE_GENERATE BLOCK은 이 게이트 대상이 아니다."""
        message = await make_due_message(approved=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.PRE_GENERATE,
            verdict=SafetyCheckVerdict.BLOCK,
            reason_code="UNVERIFIED_CONTEXT",
        )

        assert await gate_hold_reason(message) is None

    async def test_dispatch_holds_message_with_safety_check_failed(self) -> None:
        """안전검증 미통과 진료는 HELD 상태로 전환되고 발송되지 않는다."""
        message = await make_due_message(approved=True, link_free_template=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.BLOCK,
            reason_code="DRUG_CHANGE_ADVICE",
        )
        sender = MockSmsSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.HELD
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.HELD
        assert updated.hold_reason is GuideMessageHold.SAFETY_CHECK_FAILED
        assert updated.sent_at is None
        assert updated.sent_body is None

    async def test_held_audit_event_records_safety_check_failed_reason(self) -> None:
        """HELD 감사 이벤트의 reason이 SAFETY_CHECK_FAILED로 기록된다."""
        message = await make_due_message(approved=True, link_free_template=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.BLOCK,
        )

        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await GuideMessageEvent.filter(
            guide_message_id=message.guide_message_id
        ).order_by("guide_message_event_id").all()
        assert [e.event_type for e in events] == [
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.HELD,
        ]
        assert events[-1].reason == GuideMessageHold.SAFETY_CHECK_FAILED.value

    async def test_no_sensitive_data_in_held_event_reason(self) -> None:
        """감사 이벤트 reason에 토큰 원문·환자정보가 남지 않는다."""
        message = await make_due_message(approved=True, link_free_template=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.BLOCK,
            reason_code="EXTRA_DRUG",
        )

        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await GuideMessageEvent.filter(
            guide_message_id=message.guide_message_id
        ).all()
        for event in events:
            if event.reason:
                assert "http" not in event.reason
                assert "otp.html" not in event.reason
                assert "#t=" not in event.reason
                assert "합성환자" not in event.reason

    async def test_safety_gate_is_independent_of_not_approved_gate(self) -> None:
        """미승인 게이트는 안전검증 레코드와 무관하게 독립적으로 동작한다."""
        message = await make_due_message(approved=False)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.PASS,
        )

        assert await gate_hold_reason(message) is GuideMessageHold.NOT_APPROVED

    async def test_safety_check_does_not_block_after_pass(self) -> None:
        """PASS 레코드가 있고 다른 게이트도 통과하면 발송까지 도달한다."""
        message = await make_due_message(approved=True, link_free_template=True)
        await _attach_safety_check(
            message,
            stage=SafetyCheckStage.POST_GENERATE,
            verdict=SafetyCheckVerdict.PASS,
        )

        result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SENT
