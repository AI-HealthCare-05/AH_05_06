"""OCR Worker 태스크 통합 테스트 — KEY-56 · KEY-199.

실제 DB를 사용해 process_ocr_job의 경로를 검증한다.
  - CLOVA 성공 → OcrResult(clova-ocr-v2) + COMPLETED
  - CLOVA 실패 → FAILED + failure_code=CLOVA_API_ERROR  (워커는 fixture seed 불가 — KEY-199)
  - CLOVA 미설정 → FAILED + failure_code=OCR_NOT_CONFIGURED  (워커는 fixture seed 불가 — KEY-199)
  - 필수 필드 누락 → FAILED + failure_code=REQUIRED_FIELD_MISSING  (워커는 fixture seed 불가 — KEY-199)
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

    async def test_lab_only_job_gets_no_empty_prescription_rows(self) -> None:
        """검사지만 올린 작업에는 처방 항목의 빈 줄을 만들지 않는다.

        EMR이 없으면 처방 항목이 애초에 없다. 그때 빈 줄을 만들면 **안 한 것을
        못 읽은 것처럼** 보이고, 스탭은 채울 수 없는 물음표 셋을 마주한다.
        """
        job = await self._seed("ocr_lab_only_no_blanks")  # _seed 는 LAB_RESULT 하나만 붙인다

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

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        field_types = {f.field_type for f in await OcrField.filter(ocr_result=result).all()}

        for field_type in ("DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"):
            assert field_type not in field_types, f"검사지만 올렸는데 {field_type} 빈 줄이 생겼다"

    # ── CLOVA 실패 → fixture fallback ────────────────────────────────────────

    async def test_clova_error_marks_job_failed(self) -> None:
        job = await self._seed("ocr_key56_clova_err")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(side_effect=ClovaOcrError("CLOVA_TIMEOUT", "timeout")),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "CLOVA_API_ERROR"

        assert await OcrResult.filter(ocr_job=job).count() == 0

    # ── CLOVA 비활성 → FAILED (KEY-199: 워커는 fixture seed 불가) ───────────

    async def test_clova_disabled_marks_job_failed(self) -> None:
        job = await self._seed("ocr_key56_no_clova")

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "OCR_NOT_CONFIGURED"

        assert await OcrResult.filter(ocr_job=job).count() == 0

    async def test_clova_not_configured_marks_job_failed(self) -> None:
        job = await self._seed("ocr_key56_not_configured")

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "OCR_NOT_CONFIGURED"

    # ── 예외·경계 케이스 ──────────────────────────────────────────────────────

    async def test_unknown_job_id_returns_without_error(self) -> None:
        # 예외가 발생하면 Worker 루프 전체가 멈추므로 조용히 종료해야 한다
        await process_ocr_job("ocr_does_not_exist_key56")

    # ── 필수 필드를 못 읽으면 빈 줄로 남긴다 (KEY-187) ────────────────────────

    async def test_required_field_missing_leaves_empty_rows(self) -> None:
        """EMR에서 필수 필드를 못 읽어도 작업은 성공하고, 그 자리는 빈 줄로 남는다.

        예전에는 하나라도 없으면 작업 전체를 FAILED로 보냈다. 그러면 OcrResult
        자체가 안 생겨서 화면에 채워 넣을 항목 목록이 없었고, 스탭은 「판독하지
        못했습니다」 앞에서 막혔다 — 사진은 멀쩡한데 표 한 칸을 못 읽어서 진료가
        멈추는 모양이다.
        """
        patient = await Patient.create(
            patient_id=910002,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY187",
            name="테스트환자2",
            birth_date=date(1990, 1, 1),
            phone="01000000001",
        )
        visit = await Visit.create(
            visit_id=910002,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 8, 28, 9, 0, tzinfo=UTC),
        )
        med_doc = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.EMR,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job = await OcrJob.create(
            ocr_job_id="ocr_key187_required_field_missing",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job,
            document_id=med_doc.document_id,
            document_type=OcrDocumentType.EMR,
        )

        # CLOVA 호출 자체는 성공하지만 필수 EMR 필드(DIAGNOSIS·MEDICATION_NAME·DURATION_DAYS)가 없는 응답
        incomplete_clova_result = ClovaOcrResult(
            raw_text="환자명\n홍길동\n진료일\n2026-08-01",
            fields=[
                ClovaTextField(text="환자명", confidence=0.99),
                ClovaTextField(text="홍길동", confidence=0.97),
            ],
        )

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=incomplete_clova_result),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED

        # fixture 로 덮지 않는다 — 실제로 읽은 것과 못 읽은 것이 그대로 남아야
        # 스탭이 무엇을 채워야 하는지 안다.
        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        assert result.model_name != FIXTURE_MODEL_NAME

        # 못 읽은 필수 항목이 **빈 줄로** 있다
        rows = {f.field_type: f for f in await OcrField.filter(ocr_result=result).all()}
        for field_type in ("DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"):
            assert field_type in rows, f"{field_type} 자리가 없다 — 채워 넣을 대상이 없다"

        # **빈 줄과 「값이 0이다」는 다르다.** 값도 신뢰도도 비어 있어야
        # 화면이 「못 읽음」으로 그린다.
        blank = rows["DIAGNOSIS"]
        assert blank.extracted_value is None
        assert blank.confidence is None
        assert blank.is_confirmed is False

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
