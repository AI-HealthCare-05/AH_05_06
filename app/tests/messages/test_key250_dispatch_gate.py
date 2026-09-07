"""발송 직전 게이트 + append-only 감사로그 — KEY-250.

게이트가 막는 세 조건 중 "생성 전·후 안전검증"은 이 PR에서 판정 로직을
채우지 않았다(PR 코멘트 참고) — 여기서는 나머지 둘(미승인·원본 미삭제)과
감사 이벤트 네 갈래(시도·성공·실패·보류)만 검사한다.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType
from app.models.visits import (
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageStatus,
)
from app.services.dispatch_gate import gate_hold_reason
from app.services.message_dispatch import dispatch_message
from app.services.sms_sender import MockSmsSender, SmsSendError, SmsSendResult
from app.tests.messages.test_key249_dispatch_pipeline import make_due_message


async def _attach_document(message: GuideMessage, *, file_exists: bool) -> Path:
    """`message`가 딸린 진료에 원본 의료문서 한 건을 붙인다.

    `file_exists=False`면 파일을 실제로 지워서 "이미 삭제됨" 상태를 흉내낸다
    — `app/ocr/api.py`가 삭제 여부를 재는 것과 같은 신호(파일 존재 유무)다.
    """
    guide = await message.guide_document
    tmp = NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(b"synthetic")
    tmp.close()
    path = Path(tmp.name)
    if not file_exists:
        path.unlink()

    await MedicalDocument.create(
        hospital_id=guide.hospital_id,
        visit_id=guide.visit_id,
        document_type=OcrDocumentType.EMR,
        file_path=str(path),
        file_size=9,
        mime_type="image/jpeg",
        uploaded_by=1,
    )
    return path


class TestGateBlocksUnapprovedGuides(TestCase):
    async def test_gate_returns_not_approved_for_an_unapproved_guide(self) -> None:
        message = await make_due_message(approved=False)

        assert await gate_hold_reason(message) is GuideMessageHold.NOT_APPROVED

    async def test_dispatch_holds_instead_of_sending(self) -> None:
        message = await make_due_message(approved=False, link_free_template=True)
        sender = MockSmsSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.HELD
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.status is GuideMessageStatus.HELD
        assert updated.hold_reason is GuideMessageHold.NOT_APPROVED
        assert updated.claim_token is None
        # 승인이 안 됐으니 발송기까지 가지도 않았다 — sent_at·sent_body가 비어 있다.
        assert updated.sent_at is None
        assert updated.sent_body is None


class TestGateBlocksUndeletedSourceDocuments(TestCase):
    async def test_gate_returns_source_not_deleted_when_the_file_still_exists(self) -> None:
        message = await make_due_message(approved=True)
        path = await _attach_document(message, file_exists=True)
        try:
            assert await gate_hold_reason(message) is GuideMessageHold.SOURCE_NOT_DELETED
        finally:
            path.unlink(missing_ok=True)

    async def test_gate_passes_once_the_file_is_deleted(self) -> None:
        message = await make_due_message(approved=True)
        await _attach_document(message, file_exists=False)

        assert await gate_hold_reason(message) is None

    async def test_gate_passes_when_no_document_was_ever_uploaded(self) -> None:
        """지울 원본이 애초에 없으면(EMR 문구만으로 만든 안내 등) 막지 않는다."""
        message = await make_due_message(approved=True)

        assert await gate_hold_reason(message) is None

    async def test_dispatch_holds_with_source_not_deleted(self) -> None:
        message = await make_due_message(approved=True, link_free_template=True)
        path = await _attach_document(message, file_exists=True)
        try:
            result = await dispatch_message(message.guide_message_id, MockSmsSender())
        finally:
            path.unlink(missing_ok=True)

        assert result is not None
        assert result.status is GuideMessageStatus.HELD
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.hold_reason is GuideMessageHold.SOURCE_NOT_DELETED


class TestAuditEventsAreAppendOnly(TestCase):
    async def _events_for(self, message_id: int) -> list[GuideMessageEvent]:
        return await GuideMessageEvent.filter(guide_message_id=message_id).order_by("guide_message_event_id").all()

    async def test_a_successful_send_logs_attempted_then_sent(self) -> None:
        message = await make_due_message(link_free_template=True)

        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await self._events_for(message.guide_message_id)
        assert [e.event_type for e in events] == [
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.SENT,
        ]
        # 성공 이벤트에는 사유가 없다 — 원문 링크가 든 sent_body는 절대 안 옮긴다.
        assert events[-1].reason is None

    async def test_a_held_message_logs_attempted_then_held_with_reason(self) -> None:
        message = await make_due_message(approved=False, link_free_template=True)

        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await self._events_for(message.guide_message_id)
        assert [e.event_type for e in events] == [
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.HELD,
        ]
        assert events[-1].reason == GuideMessageHold.NOT_APPROVED.value

    async def test_a_permanent_failure_logs_attempted_then_failed_with_reason(self) -> None:
        # link_free_template 없이 기본 템플릿을 쓰면 {링크}를 못 채워
        # LinkNotAvailableError로 즉시 FAILED가 된다 — 실패 경로 확인용으로 그대로 쓴다.
        message = await make_due_message()

        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await self._events_for(message.guide_message_id)
        assert [e.event_type for e in events] == [
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.FAILED,
        ]
        assert events[-1].reason is not None

    async def test_retrying_appends_a_new_attempted_row_instead_of_rewriting(self) -> None:
        """재시도해도 예전 시도 기록은 그대로 남는다 — append-only."""

        class _FailOnceSender:
            def __init__(self) -> None:
                self.calls = 0

            async def send(self, to: str, body: str) -> SmsSendResult:
                self.calls += 1
                if self.calls == 1:
                    raise SmsSendError("provider_timeout")
                return await MockSmsSender().send(to, body)

        message = await make_due_message(link_free_template=True)
        sender = _FailOnceSender()

        await dispatch_message(message.guide_message_id, sender)  # 1차 — 일시 실패, 재예약
        # 백오프로 미래로 밀렸을 테니, 바로 재시도되게 시각을 되돌린다.
        await GuideMessage.filter(guide_message_id=message.guide_message_id).update(scheduled_at=now())
        await dispatch_message(message.guide_message_id, sender)  # 2차 — 성공

        events = await self._events_for(message.guide_message_id)
        assert [e.event_type for e in events] == [
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.ATTEMPTED,
            GuideMessageEventType.SENT,
        ]

    async def test_no_event_reason_ever_contains_a_link_looking_value(self) -> None:
        """토큰 원문·URL 조각이 감사 이벤트 reason에 남으면 안 된다."""
        message = await make_due_message(approved=False, link_free_template=True)
        await dispatch_message(message.guide_message_id, MockSmsSender())

        events = await self._events_for(message.guide_message_id)
        for event in events:
            if event.reason:
                assert "http" not in event.reason
                assert "otp.html" not in event.reason
                assert "#t=" not in event.reason
