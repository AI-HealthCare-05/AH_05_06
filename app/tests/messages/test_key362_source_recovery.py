"""No provider calls until verified purge; retries use the same message."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise
from tortoise.contrib.test import TestCase, TruncationTestCase
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.storage import LocalFileStorage
from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.main import app
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
)
from app.services.message_dispatch import dispatch_due_messages, dispatch_message
from app.services.source_retry import SourceRetryService
from app.tests.messages.test_key249_dispatch_pipeline import _CountingSender, make_due_message
from app.tests.messages.test_key250_dispatch_gate import _attach_document, _attach_ocr_text


class TestSourceRecovery(TestCase):
    async def test_answered_d7_recovery_cancels_without_deletion_or_sms(self):
        message = await make_due_message(kind=GuideMessageKind.CHECK_D7, link_free_template=True)
        path, doc = await _attach_document(message, file_exists=True, source_deleted_at=now())
        self.addCleanup(path.unlink, missing_ok=True)
        sender = _CountingSender()
        await dispatch_message(message.guide_message_id, sender)
        guide = await message.guide_document
        actor = ClinicalActor(1, guide.hospital_id, frozenset({"doctor"}))
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        await CheckIn.create(guide_document_id=guide.pk, medication=CheckInMedication.TAKING)
        await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.status == GuideMessageStatus.CANCELED
        assert path.exists() and not sender.calls

    async def held(self):
        message = await make_due_message(link_free_template=True)
        path, doc = await _attach_document(message, file_exists=True, source_deleted_at=now())
        self.addCleanup(path.unlink, missing_ok=True)
        sender = _CountingSender()
        await dispatch_message(message.guide_message_id, sender)
        await message.refresh_from_db()
        guide = await message.guide_document
        actor = ClinicalActor(1, guide.hospital_id, frozenset({"doctor"}))
        return message, doc, path, sender, actor

    async def test_mismatch_visible_then_recovered_once(self):
        message, doc, path, sender, actor = await self.held()
        assert message.source_failure_type == "DELETION_RECORD_MISMATCH"
        assert message.source_failure_at is not None
        visit = await (await message.guide_document).visit
        raw = await _attach_ocr_text(doc.document_id, visit)
        original_deleted_at = now()
        _, deleted_doc = await _attach_document(message, file_exists=False, source_deleted_at=original_deleted_at)
        first = await SourceRetryService().request(actor, message.guide_message_id, 0)
        duplicate = await SourceRetryService().request(actor, message.guide_message_id, 0)
        assert first == duplicate
        assert first.status == GuideMessageStatus.HELD
        assert path.exists()
        assert not sender.calls
        await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.status == GuideMessageStatus.SCHEDULED
        assert not path.exists()
        await deleted_doc.refresh_from_db()
        assert deleted_doc.source_deleted_at == original_deleted_at
        await raw.refresh_from_db()
        assert raw.raw_text is None
        assert not sender.calls
        await asyncio.gather(
            dispatch_message(message.guide_message_id, sender), dispatch_message(message.guide_message_id, sender)
        )
        assert len(sender.calls) == 1
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        await dispatch_due_messages(sender)
        assert len(sender.calls) == 1
        assert await GuideMessage.all().count() == 1
        events = await GuideMessageEvent.filter(guide_message_id=message.guide_message_id).values_list(
            "event_type", flat=True
        )
        for event in (
            GuideMessageEventType.SOURCE_RETRY,
            GuideMessageEventType.SOURCE_VERIFIED,
            GuideMessageEventType.SOURCE_REQUEUED,
        ):
            assert events.count(event) == 1

    async def test_failure_stays_held_and_old_request_cannot_retry_again(self):
        message, doc, path, sender, actor = await self.held()
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        with patch.object(LocalFileStorage, "delete", AsyncMock(side_effect=OSError("secret-path"))):
            await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.status == GuideMessageStatus.HELD
        assert message.source_failure_type == "PURGE_RETRY_FAILED"
        assert not message.source_retry_requested
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        assert await dispatch_due_messages(sender) == []
        assert path.exists() and not sender.calls
        reasons = await GuideMessageEvent.all().values_list("reason", flat=True)
        assert all("secret-path" not in (reason or "") for reason in reasons)
        await SourceRetryService().request(actor, message.guide_message_id, 1)
        await dispatch_due_messages(sender)
        assert not path.exists()

    async def test_failed_absence_verification_never_schedules(self):
        message, doc, path, sender, actor = await self.held()
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        with patch.object(LocalFileStorage, "delete", AsyncMock()):
            await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.status == GuideMessageStatus.HELD
        assert path.exists() and not sender.calls

    async def test_storage_probe_failure_is_safe_and_visible(self):
        message, doc, path, sender, actor = await self.held()
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        with patch.object(LocalFileStorage, "exists", AsyncMock(side_effect=PermissionError("secret-path"))):
            await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.source_failure_type == "STORAGE_UNAVAILABLE"
        assert message.status == GuideMessageStatus.HELD
        assert not sender.calls

    async def test_other_gate_blocks_before_deletion(self):
        message, doc, path, sender, actor = await self.held()
        await SourceRetryService().request(actor, message.guide_message_id, 0)
        guide = await message.guide_document
        guide.approved_at = None
        await guide.save(update_fields=["approved_at"])
        await dispatch_due_messages(sender)
        await message.refresh_from_db()
        assert message.hold_reason == GuideMessageHold.NOT_APPROVED
        assert not message.source_retry_requested
        assert path.exists() and not sender.calls

    async def test_cross_hospital_request_not_found(self):
        message, doc, path, sender, actor = await self.held()
        other = ClinicalActor(1, actor.hospital_id + 100, frozenset({"doctor"}))
        with pytest.raises(ApiError):
            await SourceRetryService().request(other, message.guide_message_id, 0)
        assert not sender.calls

    async def test_api_roles_payload_and_idempotence(self):
        message, doc, path, sender, actor = await self.held()
        url = f"/api/v1/messages/{message.guide_message_id}/source-retry"
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                app.dependency_overrides[get_clinical_actor] = lambda: ClinicalActor(
                    1, actor.hospital_id, frozenset({"admin"})
                )
                assert (await client.post(url, json={"generation": 0})).status_code == 403
                app.dependency_overrides[get_clinical_actor] = lambda: actor
                assert (await client.post(url, json={"generation": -1})).status_code == 400
                first = await client.post(url, json={"generation": 0})
                assert first.status_code == 202, first.text
                assert (await client.post(url, json={"generation": 0})).json() == first.json()
                assert first.json()["status"] == "HELD"
                assert path.exists() and not sender.calls
        finally:
            app.dependency_overrides.clear()


class TestRecoveryConcurrency(TruncationTestCase):
    # Real commits/connections: TestCase's shared savepoint cannot test races.
    async def _tearDownDB(self):  # noqa: N802
        async with in_transaction() as connection:
            await connection.execute_script("SET FOREIGN_KEY_CHECKS=0")
            for models in Tortoise.apps.values():
                for model in models.values():
                    await connection.execute_script(f"DELETE FROM `{model._meta.db_table}`")
            await connection.execute_script("SET FOREIGN_KEY_CHECKS=1")

    async def test_request_and_worker_races_only_delete_and_send_once(self):
        message = await make_due_message(link_free_template=True)
        path, doc = await _attach_document(message, file_exists=True, source_deleted_at=now())
        self.addCleanup(path.unlink, missing_ok=True)
        sender = _CountingSender()
        await dispatch_message(message.guide_message_id, sender)
        guide = await message.guide_document
        actor = ClinicalActor(1, guide.hospital_id, frozenset({"staff"}))
        responses = await asyncio.gather(
            *[SourceRetryService().request(actor, message.guide_message_id, 0) for _ in range(3)]
        )
        assert all(item.source_retry_generation == 1 for item in responses)
        real_delete = LocalFileStorage.delete
        deletions = []

        async def counted_delete(storage, filename):
            deletions.append(1)
            await real_delete(storage, filename)

        with patch.object(LocalFileStorage, "delete", counted_delete):
            await asyncio.gather(*[dispatch_message(message.guide_message_id, sender) for _ in range(3)])
            await asyncio.gather(*[dispatch_message(message.guide_message_id, sender) for _ in range(3)])
        assert len(deletions) == 1
        assert len(sender.calls) == 1
        assert (
            await GuideMessageEvent.filter(
                guide_message_id=message.guide_message_id,
                event_type=GuideMessageEventType.SOURCE_RETRY,
            ).count()
            == 1
        )
