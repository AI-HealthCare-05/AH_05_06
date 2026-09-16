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
from app.models.ocr import OcrDocumentText, OcrDocumentType, OcrJob, OcrJobStatus, OcrResult
from app.models.visits import (
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    PatientGuideLink,
    Visit,
)
from app.services.dispatch_gate import evaluate_dispatch_gate, gate_hold_reason
from app.services.message_dispatch import MAX_ATTEMPTS, dispatch_message
from app.services.sms_sender import MockSmsSender, SmsDeliveryStatus, SmsSendError, SmsSendResult
from app.tests.messages.test_key249_dispatch_pipeline import _CountingSender, make_due_message


async def _attach_document(
    message: GuideMessage, *, file_exists: bool, source_deleted_at: object = None
) -> tuple[Path, MedicalDocument]:
    """`message`가 딸린 진료에 원본 의료문서 한 건을 붙인다.

    `file_exists=False`면 DB 행만 남은 원본 파일 부재 상태를 흉내낸다.
    `source_deleted_at`을 주면 이미 삭제 기록이 있는 문서를 만든다
    (KEY-349) — 지정 안 하면 삭제 기록 없는(아직 안 지워진) 문서다.
    """
    guide = await message.guide_document
    tmp = NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(b"synthetic")
    tmp.close()
    path = Path(tmp.name)
    if not file_exists:
        path.unlink()

    doc = await MedicalDocument.create(
        hospital_id=guide.hospital_id,
        visit_id=guide.visit_id,
        document_type=OcrDocumentType.EMR,
        file_path=str(path),
        file_size=9,
        mime_type="image/jpeg",
        uploaded_by=1,
        source_deleted_at=source_deleted_at,
    )
    return path, doc


async def _attach_ocr_text(document_id: int, visit: Visit, *, raw_text: str = "합성 OCR 원문") -> OcrDocumentText:
    """`document_id`에 딸린 OCR 원문 한 줄을 만든다 — purge_raw_text() 검사용."""
    job = await OcrJob.create(
        ocr_job_id=f"key349-{document_id}",
        hospital_id=visit.hospital_id,
        visit=visit,
        requested_by=1,
        status=OcrJobStatus.COMPLETED,
    )
    result = await OcrResult.create(ocr_job=job, model_name="synthetic")
    return await OcrDocumentText.create(
        ocr_result=result,
        document_id=document_id,
        document_type=OcrDocumentType.EMR,
        raw_text=raw_text,
    )


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


class _NeverDeletesStorage:
    """delete()는 성공한 척하지만 실제로 파일이 안 지워진 상황을 흉내낸다.

    KEY-349의 "삭제 기록과 실제가 어긋난다" 표의 마지막 행(삭제를
    시도했는데 여전히 파일이 있다)을 재현한다.
    """

    async def delete(self, path: str) -> None:
        return None

    async def exists(self, path: str) -> bool:
        return True


class TestGateBlocksUndeletedSourceDocuments(TestCase):
    async def test_gate_holds_when_a_deletion_record_disagrees_with_the_file(self) -> None:
        """삭제 기록은 있는데 파일이 여전히 있으면 기록과 실제가 어긋난다 — KEY-349."""
        message = await make_due_message(approved=True)
        path, _ = await _attach_document(message, file_exists=True, source_deleted_at=now())
        try:
            assert await gate_hold_reason(message) is GuideMessageHold.SOURCE_NOT_DELETED
        finally:
            path.unlink(missing_ok=True)

    async def test_gate_passes_and_reports_a_document_with_no_deletion_record_yet(self) -> None:
        """삭제 기록이 아직 없으면 막지 않는다 — 그게 곧 "지울 차례"라는 뜻이다."""
        message = await make_due_message(approved=True)
        path, doc = await _attach_document(message, file_exists=True)
        try:
            decision = await evaluate_dispatch_gate(message)

            assert decision.hold_reason is None
            assert decision.pending_source_document_ids == (doc.document_id,)
        finally:
            path.unlink(missing_ok=True)

    async def test_gate_passes_when_the_deletion_record_matches_a_missing_file(self) -> None:
        message = await make_due_message(approved=True)
        await _attach_document(message, file_exists=False, source_deleted_at=now())

        assert await gate_hold_reason(message) is None

    async def test_gate_passes_when_no_document_was_ever_uploaded(self) -> None:
        """지울 원본이 애초에 없으면(EMR 문구만으로 만든 안내 등) 막지 않는다."""
        message = await make_due_message(approved=True)

        assert await gate_hold_reason(message) is None

    async def test_dispatch_purges_an_undeleted_document_and_still_sends(self) -> None:
        """다른 게이트를 통과했고 삭제 기록만 없으면, 발송 전에 지우고 계속 보낸다."""
        message = await make_due_message(approved=True, link_free_template=True)
        path, doc = await _attach_document(message, file_exists=True)
        guide = await message.guide_document
        visit = await Visit.filter(visit_id=guide.visit_id).first()
        assert visit is not None
        text = await _attach_ocr_text(doc.document_id, visit)
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.SENT
        assert sender.calls, "삭제 뒤에도 발송이 이어져야 한다"
        assert not path.exists(), "실제 파일이 지워지지 않았다"
        await doc.refresh_from_db()
        assert doc.source_deleted_at is not None
        await text.refresh_from_db()
        assert text.raw_text is None
        assert text.raw_text_purged_at is not None
        events = await GuideMessageEvent.filter(guide_message_id=message.guide_message_id).values_list(
            "event_type", flat=True
        )
        assert GuideMessageEventType.SOURCE_PURGED in events

    async def test_dispatch_marks_an_already_missing_file_as_such(self) -> None:
        """삭제 단계 전부터 파일이 없었으면 SOURCE_PURGED가 아니라 별도로 남긴다."""
        message = await make_due_message(approved=True, link_free_template=True)
        await _attach_document(message, file_exists=False)
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None and result.status is GuideMessageStatus.SENT
        events = await GuideMessageEvent.filter(guide_message_id=message.guide_message_id).values_list(
            "event_type", flat=True
        )
        assert GuideMessageEventType.SOURCE_ALREADY_PURGED in events
        assert GuideMessageEventType.SOURCE_PURGED not in events

    async def test_a_second_message_does_not_retry_an_already_purged_document(self) -> None:
        """삭제된 진료의 다음 문자(D7 등)는 삭제를 다시 시도하지 않고 통과한다."""
        first = await make_due_message(approved=True)
        await _attach_document(first, file_exists=False, source_deleted_at=now())
        guide = await first.guide_document
        second = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D7,
            status=GuideMessageStatus.SCHEDULED,
            scheduled_at=now(),
        )

        decision = await evaluate_dispatch_gate(second)

        assert decision.hold_reason is None
        assert decision.pending_source_document_ids == ()

    async def test_deletion_confirmation_failure_retries_then_holds_not_fails(self) -> None:
        """삭제 확인이 실패하면 재시도하고, 소진되면 FAILED가 아니라 HELD로 끝낸다."""
        message = await make_due_message(approved=True, link_free_template=True, attempt_count=MAX_ATTEMPTS - 1)
        path, _ = await _attach_document(message, file_exists=True)
        sender = _CountingSender()

        try:
            with patch("app.services.message_dispatch.LocalFileStorage", return_value=_NeverDeletesStorage()):
                result = await dispatch_message(message.guide_message_id, sender)

            assert result is not None
            assert result.status is GuideMessageStatus.HELD
            assert sender.calls == [], "삭제가 안 끝났으면 발송기를 부르면 안 된다"
            updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
            assert updated.hold_reason is GuideMessageHold.SOURCE_NOT_DELETED
            assert updated.failure_code is None, "GuideMessageFailure는 이 경우에 안 맞는다 — HELD여야 한다"
        finally:
            # _NeverDeletesStorage를 목으로 갈아끼워 실제 삭제 경로를 안 탔으니
            # 여기서 직접 정리한다 — 2heej 리뷰(임시 파일 미정리).
            path.unlink(missing_ok=True)


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


class TestSourcePurgeIsIdempotentAndAuditSafe(TestCase):
    """KEY-349 인수조건 — 멱등성과 감사 이벤트에 민감정보가 없는지."""

    async def test_retrying_after_the_file_is_already_gone_does_not_call_delete_again(self) -> None:
        """파일 삭제 후 기록 전 중단 → 재시도에서 중복 오류 없이 기록까지 끝난다.

        `_purge_source_documents`를 두 번 부른다 — 1차는 정상 삭제, 2차는
        "기록 전에 워커가 죽었다"를 흉내내려고 `source_deleted_at`을 강제로
        `None`으로 되돌린 뒤 다시 부른다. 이미 지워진 파일이라 2차에서는
        `delete()`를 다시 부르지 않고도 기록까지 끝나야 한다.
        """
        from app.core.storage import LocalFileStorage
        from app.services.message_dispatch import _purge_source_documents

        message = await make_due_message(approved=True)
        path, doc = await _attach_document(message, file_exists=True)
        storage = LocalFileStorage(str(path.parent))

        await _purge_source_documents(message.guide_message_id, (doc.document_id,), storage)
        await doc.refresh_from_db()
        assert doc.source_deleted_at is not None
        assert not path.exists()

        # "기록 전에 죽었다"를 흉내낸다 — 실제 파일은 이미 없는 채로 기록만
        # 되돌린다.
        doc.source_deleted_at = None  # type: ignore[assignment]
        await doc.save(update_fields=["source_deleted_at"])

        # 재시도 — 이미 없는 파일에 delete()를 또 불러도 예외가 없어야
        # 하고(LocalFileStorage.delete는 missing_ok), 기록까지 다시
        # 끝나야 한다.
        await _purge_source_documents(message.guide_message_id, (doc.document_id,), storage)
        await doc.refresh_from_db()
        assert doc.source_deleted_at is not None

        events = list(
            await GuideMessageEvent.filter(guide_message_id=message.guide_message_id).values_list(
                "event_type", flat=True
            )
        )
        # 1차는 SOURCE_PURGED(실제로 지움), 2차는 SOURCE_ALREADY_PURGED(재시도
        # 시점엔 이미 없었음)로 구분되어야 한다 — 사실 그대로다.
        assert events.count(GuideMessageEventType.SOURCE_PURGED) == 1  # type: ignore[arg-type]
        assert events.count(GuideMessageEventType.SOURCE_ALREADY_PURGED) == 1  # type: ignore[arg-type]

    async def test_a_document_uploaded_after_the_first_purge_is_purged_on_the_next_message(self) -> None:
        """발송 뒤 추가 업로드된 문서는 다음 문자에서 지워진다."""
        first = await make_due_message(approved=True)
        await _attach_document(first, file_exists=False, source_deleted_at=now())
        guide = await first.guide_document
        # 첫 문자가 나간 뒤 새로 업로드된 문서 — 삭제 기록이 없다.
        new_path, new_doc = await _attach_document(first, file_exists=True)
        second = await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.CHECK_D7,
            status=GuideMessageStatus.SCHEDULED,
            scheduled_at=now(),
        )

        decision = await evaluate_dispatch_gate(second)

        assert decision.hold_reason is None
        assert decision.pending_source_document_ids == (new_doc.document_id,)
        new_path.unlink(missing_ok=True)

    async def test_source_purge_audit_events_carry_only_a_document_id(self) -> None:
        """감사 이벤트에 파일 경로·파일명·환자정보·OCR 원문이 없다 — document_id만."""
        message = await make_due_message(approved=True, link_free_template=True)
        path, doc = await _attach_document(message, file_exists=True)
        sender = _CountingSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None and result.status is GuideMessageStatus.SENT
        purge_events = await GuideMessageEvent.filter(
            guide_message_id=message.guide_message_id,
            event_type=GuideMessageEventType.SOURCE_PURGED,
        ).all()
        assert len(purge_events) == 1
        assert purge_events[0].reason == f"document_id={doc.document_id}"
        assert str(path) not in (purge_events[0].reason or "")

    async def test_a_message_blocked_by_a_later_gate_does_not_purge_the_source(self) -> None:
        """인수조건 2 — 예약링크 없음·안전검증·승인 번호로 막히는 문자는
        원본을 지우지 않는다. 삭제는 되돌릴 수 없다(2heej 리뷰).

        RECIPIENT_NOT_APPROVED는 dispatch_gate.py에서
        _source_deletion_state 판정 이후에 체크되는 게이트다 —
        pending_source_document_ids가 이미 채워진 상태에서 그 게이트가
        막으므로, dispatch_message()가 실제로 그 순서를 지켜 삭제
        블록에 도달하지 않는지를 코드 순서가 아니라 값으로 잰다.
        """
        message = await make_due_message(link_free_template=True, phone="01099998888")
        path, doc = await _attach_document(message, file_exists=True)
        sender = _CountingSender()

        with (
            patch.object(core_config.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_config.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222")),
        ):
            result = await dispatch_message(message.guide_message_id, sender)

        try:
            assert result is not None and result.status is GuideMessageStatus.HELD
            assert sender.calls == [], "다른 게이트에 막혔는데 발송기를 불렀다"
            await doc.refresh_from_db()
            assert doc.source_deleted_at is None, "다른 게이트에 막힌 문자의 원본을 지웠다 — 되돌릴 수 없는 일이다"
            assert path.exists(), "실제 파일이 지워졌다"
            events = await GuideMessageEvent.filter(guide_message_id=message.guide_message_id).values_list(
                "event_type", flat=True
            )
            assert GuideMessageEventType.SOURCE_PURGED not in events
        finally:
            path.unlink(missing_ok=True)
