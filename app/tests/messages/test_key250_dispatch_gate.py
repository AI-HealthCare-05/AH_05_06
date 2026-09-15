"""발송 직전 게이트 + append-only 감사로그 — KEY-250.

게이트가 막는 세 조건 중 "생성 전·후 안전검증"은 이 PR에서 판정 로직을
채우지 않았다(PR 코멘트 참고) — 여기서는 나머지 둘(미승인·원본 미삭제)과
감사 이벤트 네 갈래(시도·성공·실패·보류)만 검사한다.
"""

import ast
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, patch

from pydantic import SecretStr
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

import app.core as core_config
from app.core.config import SmsProvider
from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType
from app.models.visits import (
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    PatientGuideLink,
)
from app.services.dispatch_gate import gate_hold_reason
from app.services.message_dispatch import dispatch_message
from app.services.sms_sender import MockSmsSender, SmsDeliveryStatus, SmsSendError, SmsSendResult
from app.tests.messages.test_key249_dispatch_pipeline import _CountingSender, make_due_message


async def _attach_document(message: GuideMessage, *, file_exists: bool) -> Path:
    """`message`가 딸린 진료에 원본 의료문서 한 건을 붙인다.

    `file_exists=False`면 DB 행만 남은 원본 파일 부재 상태를 흉내낸다.
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


class _UnavailableStorage:
    async def save(self, content: bytes, mime_type: str) -> str:
        raise NotImplementedError

    async def delete(self, path: str) -> None:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise PermissionError(path)


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

    async def test_gate_blocks_when_the_document_row_has_no_file(self) -> None:
        message = await make_due_message(approved=True)
        await _attach_document(message, file_exists=False)

        assert await gate_hold_reason(message) is GuideMessageHold.SOURCE_NOT_DELETED

    async def test_gate_blocks_when_only_one_of_two_files_is_missing(self) -> None:
        message = await make_due_message(approved=True)
        present = await _attach_document(message, file_exists=True)
        await _attach_document(message, file_exists=False)
        try:
            assert await gate_hold_reason(message) is GuideMessageHold.SOURCE_NOT_DELETED
        finally:
            present.unlink(missing_ok=True)

    async def test_missing_file_never_sends_or_issues_a_link(self) -> None:
        message = await make_due_message(approved=True)
        await _attach_document(message, file_exists=False)
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None and result.status is GuideMessageStatus.HELD
        assert sender.calls == []
        assert not await PatientGuideLink.filter(guide_document_id=message.guide_document_id).exists()

    async def test_gate_passes_when_no_document_was_ever_uploaded(self) -> None:
        """지울 원본이 애초에 없으면(EMR 문구만으로 만든 안내 등) 막지 않는다."""
        message = await make_due_message(approved=True)

        assert await gate_hold_reason(message) is None

    async def test_storage_lookup_failure_is_not_mistaken_for_deletion(self) -> None:
        """권한·저장소 장애 때는 fail-safe로 발송을 막는다."""
        message = await make_due_message(approved=True)
        await _attach_document(message, file_exists=False)

        assert await gate_hold_reason(message, storage=_UnavailableStorage()) is GuideMessageHold.SOURCE_NOT_DELETED

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
        # 공급자가 명시적으로 거절하면(FAILED) 재시도 없이 바로 종료한다 —
        # 실패 경로 확인용으로 link_free_template을 써서 링크 발급과는
        # 무관하게 이 경로만 본다.
        message = await make_due_message(link_free_template=True)

        await dispatch_message(message.guide_message_id, MockSmsSender(SmsDeliveryStatus.FAILED))

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

    def test_application_code_never_updates_or_deletes_message_events(self) -> None:
        """감사 행은 create만 허용한다 — QuerySet 변조를 원문 대조로 막는다."""

        def root_name(node: ast.AST) -> str | None:
            while isinstance(node, (ast.Attribute, ast.Call)):
                node = node.value if isinstance(node, ast.Attribute) else node.func
            return node.id if isinstance(node, ast.Name) else None

        violations: list[str] = []
        for path in Path("app").rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"update", "delete"}
                    and root_name(node.func.value) == "GuideMessageEvent"
                ):
                    violations.append(f"{path}:{node.lineno}")

        assert violations == [], f"GuideMessageEvent 감사 행을 변경·삭제한다: {violations}"


class TestClaimIsReleasedAfterPreSendFailure(TestCase):
    async def _assert_retryable(self, message: GuideMessage) -> None:
        saved = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert saved.status is GuideMessageStatus.SCHEDULED
        assert saved.claim_token is None
        assert saved.attempt_count == 1
        assert saved.provider_detail == "worker_exception"
        assert saved.scheduled_at > now()

    async def test_attempt_event_failure_releases_the_claim(self) -> None:
        message = await make_due_message(link_free_template=True)

        with patch(
            "app.services.message_dispatch._log_event",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ):
            result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SCHEDULED
        await self._assert_retryable(message)

    async def test_gate_failure_releases_the_claim(self) -> None:
        message = await make_due_message(link_free_template=True)

        with patch(
            "app.services.message_dispatch.evaluate_dispatch_gate",
            new=AsyncMock(side_effect=RuntimeError("storage unavailable")),
        ):
            result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SCHEDULED
        await self._assert_retryable(message)


class TestGateBlocksUnapprovedRecipients(TestCase):
    """승인 번호로만 발송 — KEY-338.

    SMS_PROVIDER=solapi일 때만 보는 게이트다. mock(기본값, 로컬·개발·CI)
    에서는 이 게이트 자체를 안 본다 — 기존 게이트 순서와 mock 동작은
    안 바뀐다는 인수조건을 값으로 잰다.
    """

    async def test_unapproved_phone_is_held_when_provider_is_solapi(self) -> None:
        message = await make_due_message(link_free_template=True, phone="01099998888")

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            reason = await gate_hold_reason(message)

        assert reason is GuideMessageHold.RECIPIENT_NOT_APPROVED

    async def test_unapproved_phone_never_sends_or_issues_a_link(self) -> None:
        message = await make_due_message(phone="01099998888")
        sender = _CountingSender()

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None and result.status is GuideMessageStatus.HELD
        assert sender.calls == []
        assert not await PatientGuideLink.filter(guide_document_id=message.guide_document_id).exists()

    async def test_approved_phone_passes_when_provider_is_solapi(self) -> None:
        message = await make_due_message(link_free_template=True, phone="01011112222")

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            reason = await gate_hold_reason(message)

        assert reason is None

    async def test_hyphenated_entries_in_the_allowlist_still_match(self) -> None:
        """목록의 하이픈 표기(010-1111-2222)도 정규화해서 맞춘다 — 인수조건."""
        message = await make_due_message(link_free_template=True, phone="01011112222")

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("010-1111-2222")),
        ):
            reason = await gate_hold_reason(message)

        assert reason is None

    async def test_mock_provider_ignores_the_allowlist(self) -> None:
        """SMS_PROVIDER=mock(기본값)에서는 이 게이트가 없다 — 기존 동작 그대로."""
        message = await make_due_message(link_free_template=True, phone="01099998888")

        with patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")):
            reason = await gate_hold_reason(message)

        assert reason is None

    async def test_the_existing_gate_order_still_runs_first(self) -> None:
        """미승인 → 원본 미삭제 → 예약링크 없음, 그 다음에야 이 게이트를 본다 — 인수조건.

        미승인 안내는 목록에 없는 번호라도 NOT_APPROVED로 먼저 막혀야 한다.
        """
        message = await make_due_message(approved=False, phone="01099998888")

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            reason = await gate_hold_reason(message)

        assert reason is GuideMessageHold.NOT_APPROVED

    async def test_a_resent_message_goes_through_the_same_gate(self) -> None:
        """재발송 작업 행도 수신번호 게이트를 우회하지 않는다."""
        source = await make_due_message(
            link_free_template=True,
            phone="01099998888",
            kind=GuideMessageKind.GUIDE,
            status=GuideMessageStatus.SENT,
        )
        message = await GuideMessage.create(
            guide_document_id=source.guide_document_id,
            kind=source.kind,
            status=GuideMessageStatus.SCHEDULED,
            scheduled_at=source.scheduled_at,
            resend_of_message_id=source.guide_message_id,
            resend_sequence=1,
        )

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            reason = await gate_hold_reason(message)

        assert reason is GuideMessageHold.RECIPIENT_NOT_APPROVED
