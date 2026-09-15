"""중단 작업 정리와 완료 경쟁, 재업로드 복구 — 합성 데이터만 사용한다."""

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from tortoise.contrib.test import TestCase
from tortoise.queryset import QuerySet

from ai_worker import main as worker
from ai_worker.adapters.clova import ClovaOcrError
from ai_worker.tasks.ocr_recovery import PROCESSING_TIMEOUT, PROCESSING_TIMEOUT_CODE, expire_stale_ocr_jobs
from ai_worker.tasks.ocr_task import process_ocr_job
from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType, OcrField, OcrJob, OcrJobDocument, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import UpdateOcrFieldRequest
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository
from app.ocr.utils import assert_ocr_jobs_ready
from app.tests.ocr.test_ocr_task import _FAKE_CLOVA_RESULT, JPEG_BYTES

AT = datetime(2026, 9, 15, 15, tzinfo=ZoneInfo("Asia/Seoul"))


class TestProcessingTimeout(TestCase):
    async def test_retry_stops_if_recovery_finishes_during_error_or_backoff(self) -> None:
        for phase in ("error", "backoff"):
            for code in ("CLOVA_TIMEOUT", "CLOVA_NETWORK_ERROR", "CLOVA_SERVER_ERROR"):
                job = await self.job(f"retry-{phase}-{code}")
                with tempfile.TemporaryDirectory() as folder:
                    filename = Path(folder) / "synthetic.jpg"
                    filename.write_bytes(JPEG_BYTES)
                    await self.attach(job, str(filename))

                    async def expire(job_id=job.pk):
                        await OcrJob.filter(pk=job_id).update(started_at=AT - PROCESSING_TIMEOUT)
                        assert await expire_stale_ocr_jobs(at=AT) == 1

                    async def fail_call(*args, when=phase, error_code=code, **kwargs):
                        if when == "error":
                            await expire()
                        raise ClovaOcrError(error_code, "synthetic")

                    async def backoff(_delay, when=phase):
                        if when == "backoff":
                            await expire()

                    with (
                        patch("ai_worker.tasks.ocr_task.config") as config,
                        patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=fail_call) as clova,
                        patch("ai_worker.tasks.ocr_task.asyncio.sleep", side_effect=backoff),
                    ):
                        config.clova_enabled = True
                        await process_ocr_job(job.pk)
                        assert clova.await_count == 1
                await job.refresh_from_db()
                assert job.status == OcrJobStatus.FAILED
                assert job.failure_code == PROCESSING_TIMEOUT_CODE
                assert job.completed_at == AT and job.progress == 0
                assert not await OcrResult.filter(ocr_job=job).exists()

    async def test_confirmed_field_remains_editable_but_requires_reconfirmation(self) -> None:
        job = await self.job("syn154-confirmed", status=OcrJobStatus.COMPLETED)
        result = await OcrResult.create(ocr_job=job, model_name="synthetic")
        field = await OcrField.create(
            ocr_result=result,
            field_type="DURATION_DAYS",
            extracted_value="28",
            is_confirmed=True,
            confirmed_by=9154,
            confirmed_at=AT,
        )
        actor = OcrActor(staff_id=9154, hospital_id=9154, roles=frozenset({"staff"}))
        repository = TortoiseOcrRepository()
        changed, _ = await repository.update_field(
            field.pk, UpdateOcrFieldRequest(base_version=1, corrected_value="21"), actor
        )
        assert changed.value == "21"
        assert not changed.is_confirmed
        assert changed.confirmed_by is None and changed.confirmed_at is None
        confirmed, _ = await repository.update_field(
            field.pk, UpdateOcrFieldRequest(base_version=changed.version, confirm=True), actor
        )
        assert confirmed.is_confirmed and confirmed.value == "21"

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        patient = await Patient.create(
            hospital_id=9154,
            hospital_patient_no="SYN-154",
            name="합성 환자",
            birth_date=date(2000, 1, 1),
            phone="01000000000",
        )
        self.visit = await Visit.create(hospital_id=9154, patient=patient, visited_at=AT)

    async def job(self, name: str, *, started=None, created=None, status=OcrJobStatus.PROCESSING) -> OcrJob:
        job = await OcrJob.create(
            ocr_job_id="syn154-" + name, hospital_id=9154, visit=self.visit, requested_by=1, status=status
        )
        await OcrJob.filter(pk=job.pk).update(started_at=started, created_at=created or AT)
        await job.refresh_from_db()
        return job

    async def test_only_expired_processing_jobs_fail_and_log_only_id_and_code(self) -> None:
        cutoff = AT - PROCESSING_TIMEOUT
        expired = await self.job("expired", started=cutoff)
        unstarted = await self.job("unstarted", created=cutoff)
        fresh = await self.job("fresh", started=cutoff + timedelta(seconds=1))
        waiting = await self.job("waiting", created=AT)
        restarted = await self.job("recent-start-old-upload", started=AT, created=cutoff - timedelta(hours=1))
        completed = await self.job("completed", started=cutoff, status=OcrJobStatus.COMPLETED)
        failed = await self.job("failed", started=cutoff, status=OcrJobStatus.FAILED)
        with patch("ai_worker.tasks.ocr_recovery.default_logger") as logger:
            assert await expire_stale_ocr_jobs(at=AT) == 2
        for job in (expired, unstarted):
            await job.refresh_from_db()
            assert job.status == OcrJobStatus.FAILED
            assert job.failure_code == PROCESSING_TIMEOUT_CODE
            assert job.progress == 0 and job.completed_at == AT
        for job in (fresh, waiting, restarted, completed, failed):
            before = job.status
            await job.refresh_from_db()
            assert job.status == before
            assert job.failure_code is None
        assert {call.args for call in logger.warning.call_args_list} == {
            ("ocr_job_id=%s code=%s", expired.pk, PROCESSING_TIMEOUT_CODE),
            ("ocr_job_id=%s code=%s", unstarted.pk, PROCESSING_TIMEOUT_CODE),
        }
        assert await expire_stale_ocr_jobs(at=AT) == 0

    async def test_completion_between_scan_and_update_wins(self) -> None:
        job = await self.job("completion-race", started=AT - PROCESSING_TIMEOUT)
        original = QuerySet.update

        async def complete_first(query, **kwargs):
            await original(OcrJob.filter(pk=job.pk), status=OcrJobStatus.COMPLETED, progress=100, completed_at=AT)
            return await original(query, **kwargs)

        with patch.object(QuerySet, "update", complete_first):
            assert await expire_stale_ocr_jobs(at=AT) == 0
        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED and job.progress == 100
        assert job.failure_code is None

    async def test_recent_start_between_scan_and_update_wins(self) -> None:
        job = await self.job("start-race", created=AT - PROCESSING_TIMEOUT)
        original = QuerySet.update

        async def start_first(query, **kwargs):
            await original(OcrJob.filter(pk=job.pk), started_at=AT)
            return await original(query, **kwargs)

        with patch.object(QuerySet, "update", start_first):
            assert await expire_stale_ocr_jobs(at=AT) == 0
        await job.refresh_from_db()
        assert job.status == OcrJobStatus.PROCESSING and job.failure_code is None

    async def attach(self, job: OcrJob, filename: str) -> None:
        doc = await MedicalDocument.create(
            hospital_id=9154,
            visit=self.visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=filename,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        await OcrJobDocument.create(ocr_job=job, document_id=doc.pk, document_type=OcrDocumentType.LAB_RESULT)

    async def test_late_success_and_late_error_cannot_resurrect_timed_out_job(self) -> None:
        for name in ("late-success", "late-error"):
            job = await self.job(name)
            with tempfile.TemporaryDirectory() as folder:
                filename = Path(folder) / "synthetic.jpg"
                filename.write_bytes(JPEG_BYTES)
                await self.attach(job, str(filename))

                async def timeout_during_call(*args, job_id=job.pk, outcome=name, **kwargs):
                    await OcrJob.filter(pk=job_id).update(started_at=AT - PROCESSING_TIMEOUT)
                    assert await expire_stale_ocr_jobs(at=AT) == 1
                    if outcome == "late-error":
                        raise ClovaOcrError("CLOVA_PARSE_ERROR", "synthetic")
                    return _FAKE_CLOVA_RESULT

                with (
                    patch("ai_worker.tasks.ocr_task.config") as config,
                    patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=timeout_during_call),
                ):
                    config.clova_enabled = True
                    await process_ocr_job(job.pk)
            await job.refresh_from_db()
            assert job.status == OcrJobStatus.FAILED and job.failure_code == PROCESSING_TIMEOUT_CODE
            assert job.progress == 0 and job.completed_at == AT
            assert not await OcrResult.filter(ocr_job=job).exists()

    async def test_reupload_completes_and_passes_generation_gate_without_requeue(self) -> None:
        stale = await self.job("stuck", started=AT - PROCESSING_TIMEOUT)
        try:
            await assert_ocr_jobs_ready(self.visit.pk, 9154)
        except OcrApiError as error:
            assert error.code == "OCR_RESULT_NOT_READY"
        else:
            self.fail("처리 중인 작업을 통과시켰다")
        assert await expire_stale_ocr_jobs(at=AT) == 1
        reupload = await self.job("reupload", created=AT + timedelta(seconds=1))
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "synthetic.jpg"
            filename.write_bytes(JPEG_BYTES)
            await self.attach(reupload, str(filename))
            with (
                patch("ai_worker.tasks.ocr_task.config") as config,
                patch("ai_worker.tasks.ocr_task.call_clova_ocr", AsyncMock(return_value=_FAKE_CLOVA_RESULT)),
            ):
                config.clova_enabled = True
                await process_ocr_job(reupload.pk)
        assert [job.pk for job in await assert_ocr_jobs_ready(self.visit.pk, 9154)] == [reupload.pk]
        await stale.refresh_from_db()
        assert stale.failure_code == PROCESSING_TIMEOUT_CODE


class TestRecoveryLoop(TestCase):
    async def test_worker_entrypoint_runs_recovery_alongside_existing_loops(self) -> None:
        with (
            patch.object(worker.Tortoise, "init", AsyncMock()),
            patch.object(worker.Tortoise, "close_connections", AsyncMock()),
            patch.object(worker, "close_redis", AsyncMock()),
            patch.object(worker, "_run_ocr_recovery_loop", AsyncMock()) as recovery,
            patch.object(worker, "_run_ocr_loop", AsyncMock()) as ocr,
            patch.object(worker, "_run_message_dispatch_loop", AsyncMock()) as sms,
            patch.object(worker, "_run_guide_generation_loop", AsyncMock()) as guide,
        ):
            await worker._run()
            for loop in (recovery, ocr, sms, guide):
                loop.assert_awaited_once()

    async def test_recovery_runs_at_start_and_periodically_and_survives_errors(self) -> None:
        calls = []

        async def sweep():
            calls.append("sweep")
            if len(calls) == 1:
                raise RuntimeError("synthetic private details must not be logged")
            worker._shutdown = True

        with (
            patch.object(worker, "_shutdown", False),
            patch.object(worker, "RECOVERY_INTERVAL_SECONDS", 1),
            patch.object(worker, "expire_stale_ocr_jobs", side_effect=sweep),
            patch.object(worker.asyncio, "sleep", AsyncMock()) as sleep,
            patch.object(worker, "default_logger") as logger,
        ):
            await worker._run_ocr_recovery_loop()
            assert calls == ["sweep", "sweep"]
            sleep.assert_awaited_once_with(1)
            logger.error.assert_called_once_with("code=OCR_RECOVERY_FAILED")
