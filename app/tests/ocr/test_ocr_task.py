"""OCR Worker 태스크 통합 테스트 — KEY-56.

실제 DB를 사용해 process_ocr_job의 경로를 검증한다.
  - CLOVA 성공 → OcrResult(clova-ocr-v2) + COMPLETED
  - CLOVA 실패 + OCR_FIXTURE_FALLBACK=True → fixture fallback → OcrResult(fixture-v0) + COMPLETED + failure_code=CLOVA_API_ERROR
  - CLOVA 미설정 + OCR_FIXTURE_FALLBACK=True → fixture fallback → OcrResult(fixture-v0) + COMPLETED
  - CLOVA 미설정 + OCR_FIXTURE_FALLBACK=False → FAILED + failure_code=OCR_NOT_CONFIGURED
  - 존재하지 않는 job_id → 예외 없이 종료
  - 이미 완료된 job → 중복 처리 없이 종료
"""

import os
import tempfile
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

from tortoise.contrib.test import TestCase

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, ClovaTextField
from ai_worker.tasks.ocr_task import _CLOVA_MODEL_NAME, process_ocr_job
from app.models.documents import MedicalDocument
from app.models.ocr import (
    OcrDocumentType,
    OcrField,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
    OcrResult,
)
from app.models.patients import Patient
from app.models.visits import Visit
from app.ocr.service import FIXTURE_MODEL_NAME

HOSPITAL_ID = 9100
PATIENT_ID = 910001
VISIT_ID = 910001

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20

_FAKE_CLOVA_RESULT = ClovaOcrResult(
    raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
    fields=[
        ClovaTextField(text="CA-125 : 48 U/mL", confidence=0.95),
        ClovaTextField(text="AMH : 2.8 ng/mL", confidence=0.92),
    ],
)


class TestProcessOcrJob(TestCase):
    def setUp(self) -> None:
        super().setUp()
        # 실제 파일 — _call_clova_for_documents가 파일을 읽은 뒤 call_clova_ocr를 호출한다
        self._tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        self._tmp.write(JPEG_BYTES)
        self._tmp.close()

    def tearDown(self) -> None:
        os.unlink(self._tmp.name)
        super().tearDown()

    async def _seed(self, ocr_job_id: str) -> OcrJob:
        patient = await Patient.create(
            patient_id=PATIENT_ID,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY56",
            name="테스트환자",
            birth_date=date(1990, 1, 1),
            phone="01000000000",
        )
        visit = await Visit.create(
            visit_id=VISIT_ID,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
        )
        med_doc = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job = await OcrJob.create(
            ocr_job_id=ocr_job_id,
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job,
            document_id=med_doc.document_id,
            document_type=OcrDocumentType.LAB_RESULT,
        )
        return job

    # ── CLOVA 성공 경로 ───────────────────────────────────────────────────────

    async def test_clova_success_saves_result_and_completes_job(self) -> None:
        job = await self._seed("ocr_key56_clova_ok")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=_FAKE_CLOVA_RESULT),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED
        assert job.started_at is not None
        assert job.completed_at is not None

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        assert result.model_name == _CLOVA_MODEL_NAME

        fields = await OcrField.filter(ocr_result=result).all()
        field_types = {f.field_type for f in fields}
        # raw_text "CA-125 : 48 U/mL\nAMH : 2.8 ng/mL" 에서 두 필드 모두 추출되어야 한다
        assert "CA_125" in field_types
        assert "AMH" in field_types

    # ── CLOVA 실패 → fixture fallback ────────────────────────────────────────

    async def test_clova_error_falls_back_to_fixture_and_completes(self) -> None:
        job = await self._seed("ocr_key56_clova_err")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(side_effect=ClovaOcrError("CLOVA_TIMEOUT", "timeout")),
            ),
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED
        assert job.failure_code == "CLOVA_API_ERROR"

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        assert result.model_name == FIXTURE_MODEL_NAME

    # ── CLOVA 비활성 → fixture fallback ──────────────────────────────────────

    async def test_clova_disabled_uses_fixture_and_completes(self) -> None:
        job = await self._seed("ocr_key56_no_clova")

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        assert result.model_name == FIXTURE_MODEL_NAME

    async def test_clova_not_configured_marks_job_failed(self) -> None:
        job = await self._seed("ocr_key56_not_configured")

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            mock_cfg.OCR_FIXTURE_FALLBACK = False
            mock_cfg.ENV = "prod"
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "OCR_NOT_CONFIGURED"

    # ── 예외·경계 케이스 ──────────────────────────────────────────────────────

    async def test_unknown_job_id_returns_without_error(self) -> None:
        # 예외가 발생하면 Worker 루프 전체가 멈추므로 조용히 종료해야 한다
        await process_ocr_job("ocr_does_not_exist_key56")

    async def test_already_completed_job_is_skipped(self) -> None:
        job = await self._seed("ocr_key56_already_done")
        job.status = OcrJobStatus.COMPLETED
        await job.save(update_fields=("status",))

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            await process_ocr_job(job.ocr_job_id)

        # 중복 처리가 없어야 한다
        count = await OcrResult.filter(ocr_job=job).count()
        assert count == 0
