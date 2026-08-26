"""OCR 관측 로그 테스트 — KEY-175.

검증 경로:
  민감정보 비노출
    - _observe() 로그에 raw_text·파일경로·오류 원문이 포함되지 않는다.
    - ClovaOcrError 경고 로그에 예외 원문이 포함되지 않는다.

  구조화 로그 형식
    - 성공(mode=clova): elapsed_ms·clova_elapsed_ms·error_code=none 확인
    - fallback(mode=fixture): error_code=CLOVA_TIMEOUT·CLOVA_NETWORK_ERROR 확인
    - 실패(mode=failed): fallback 비활성 시 error_code=OCR_NOT_CONFIGURED 확인

  모든 종료 경로에서 ocr_job_complete 한 줄만 남긴다.
"""

import os
import tempfile
from datetime import UTC, date, datetime
from time import perf_counter
from unittest.mock import AsyncMock, patch

from tortoise.contrib.test import TestCase

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, ClovaTextField
from ai_worker.tasks.ocr_task import _observe, process_ocr_job
from app.models.documents import MedicalDocument
from app.models.ocr import (
    OcrDocumentType,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
)
from app.models.patients import Patient
from app.models.visits import Visit

_LOGGER = "ai_worker"

HOSPITAL_ID = 9175
PATIENT_ID = 917501
VISIT_ID = 917501

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20

_FAKE_CLOVA = ClovaOcrResult(
    raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
    fields=[ClovaTextField(text="CA-125 : 48 U/mL", confidence=0.95)],
    elapsed_ms=1800,
)


# ---------------------------------------------------------------------------
# _observe() 단위 테스트 — DB 불필요, TestCase는 conftest 요구로 사용
# ---------------------------------------------------------------------------


class TestObserveUnit(TestCase):
    """_observe() 함수가 올바른 구조화 로그를 남기는지 검증한다."""

    def test_clova_success_log_format(self) -> None:
        t0 = perf_counter()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            _observe(ocr_job_id="unit-test-001", mode="clova", t0=t0, error_code=None, clova_elapsed_ms=1800)
        log = "\n".join(cap.output)
        assert "ocr_job_complete" in log
        assert "mode=clova" in log
        assert "elapsed_ms=" in log
        assert "clova_elapsed_ms=1800" in log
        assert "error_code=none" in log
        assert "ocr_job_id=unit-test-001" in log

    def test_fixture_fallback_log_format(self) -> None:
        t0 = perf_counter()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            _observe(ocr_job_id="unit-test-002", mode="fixture", t0=t0, error_code="CLOVA_TIMEOUT")
        log = "\n".join(cap.output)
        assert "mode=fixture" in log
        assert "clova_elapsed_ms=none" in log
        assert "error_code=CLOVA_TIMEOUT" in log

    def test_failed_log_format(self) -> None:
        t0 = perf_counter()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            _observe(ocr_job_id="unit-test-003", mode="failed", t0=t0, error_code="PROCESSING_ERROR")
        log = "\n".join(cap.output)
        assert "mode=failed" in log
        assert "error_code=PROCESSING_ERROR" in log

    def test_no_sensitive_data_in_observe_log(self) -> None:
        """_observe() 로그에 환자정보·OCR 원문·파일 경로·비밀값이 없어야 한다."""
        sensitive = [
            "CA-125",  # OCR 원문
            "/tmp/upload",  # 파일 경로
            "sk-secret-key",  # API 키 패턴
            "환자이름",  # 환자 개인정보 패턴
        ]
        t0 = perf_counter()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            _observe(ocr_job_id="unit-test-004", mode="clova", t0=t0, error_code=None, clova_elapsed_ms=500)
        log = "\n".join(cap.output)
        for secret in sensitive:
            assert secret not in log, f"민감정보 노출: {secret!r}"

    def test_elapsed_ms_is_positive_integer(self) -> None:
        import re

        t0 = perf_counter()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            _observe(ocr_job_id="unit-test-005", mode="clova", t0=t0, error_code=None)
        log = "\n".join(cap.output)
        m = re.search(r"elapsed_ms=(\d+)", log)
        assert m is not None, "elapsed_ms 필드 없음"
        assert int(m.group(1)) >= 0


# ---------------------------------------------------------------------------
# process_ocr_job() 통합 테스트 — 실제 DB + assertLogs
# ---------------------------------------------------------------------------


class TestOcrObservabilityIntegration(TestCase):
    """process_ocr_job() 각 경로에서 ocr_job_complete 로그가 올바르게 남는지 검증."""

    def setUp(self) -> None:
        super().setUp()
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
            hospital_patient_no="TEST-KEY175",
            name="합성환자175",
            birth_date=date(1990, 1, 1),
            phone="01099990001",
        )
        visit = await Visit.create(
            visit_id=VISIT_ID,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 8, 26, 9, 0, tzinfo=UTC),
        )
        med_doc = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=self._tmp.name,
            mime_type="image/jpeg",
            original_filename="lab.jpg",
            file_size=len(JPEG_BYTES),
            uploaded_by=1,
        )
        job = await OcrJob.create(
            ocr_job_id=ocr_job_id,
            hospital_id=HOSPITAL_ID,
            visit=visit,
            status=OcrJobStatus.PROCESSING,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job,
            document_id=med_doc.document_id,
            document_type=OcrDocumentType.LAB_RESULT,
        )
        return job

    # --- 정상 경로 ---

    async def test_clova_success_logs_mode_clova(self) -> None:
        """CLOVA 성공 시 mode=clova, clova_elapsed_ms>0 로그."""
        job = await self._seed("obs-175-success-001")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", new=AsyncMock(return_value=_FAKE_CLOVA)),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert "ocr_job_complete" in log
        assert "mode=clova" in log
        assert "clova_elapsed_ms=1800" in log
        assert "error_code=none" in log

    # --- CLOVA 오류 → fixture fallback ---

    async def test_clova_timeout_logs_mode_fixture_with_error_code(self) -> None:
        """CLOVA_TIMEOUT 발생 시 mode=fixture, error_code=CLOVA_TIMEOUT 로그."""
        job = await self._seed("obs-175-timeout-001")
        timeout_err = ClovaOcrError("CLOVA_TIMEOUT", "CLOVA OCR 요청 시간 초과")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=timeout_err),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert "ocr_job_complete" in log
        assert "mode=fixture" in log
        assert "error_code=CLOVA_TIMEOUT" in log

    async def test_clova_timeout_records_clova_elapsed_ms(self) -> None:
        """CLOVA_TIMEOUT 발생 시 elapsed_ms가 clova_elapsed_ms로 로그에 기록된다."""
        job = await self._seed("obs-175-timeout-elapsed-001")
        timeout_err = ClovaOcrError("CLOVA_TIMEOUT", "CLOVA OCR 요청 시간 초과", elapsed_ms=29800)
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=timeout_err),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert "clova_elapsed_ms=29800" in log, "타임아웃 시 elapsed_ms가 로그에 없으면 P95 계산에서 제외됨"

    async def test_clova_network_error_logs_mode_fixture(self) -> None:
        """CLOVA_NETWORK_ERROR 발생 시 mode=fixture, error_code=CLOVA_NETWORK_ERROR 로그."""
        job = await self._seed("obs-175-network-001")
        net_err = ClovaOcrError("CLOVA_NETWORK_ERROR", "CLOVA OCR 네트워크 오류")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=net_err),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert "mode=fixture" in log
        assert "error_code=CLOVA_NETWORK_ERROR" in log

    # --- fallback 비활성 → FAILED ---

    async def test_clova_disabled_fallback_disabled_logs_mode_failed(self) -> None:
        """CLOVA 미설정 + fallback 비활성 시 mode=failed, error_code=OCR_NOT_CONFIGURED 로그."""
        job = await self._seed("obs-175-failed-001")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = False
            mock_cfg.OCR_FIXTURE_FALLBACK = False
            mock_cfg.ENV = "test"
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert "ocr_job_complete" in log
        assert "mode=failed" in log
        assert "error_code=OCR_NOT_CONFIGURED" in log

    # --- 민감정보 비노출 (통합 경로) ---

    async def test_no_raw_text_in_logs_on_clova_success(self) -> None:
        """CLOVA 성공 경로 로그에 OCR 원문이 남지 않는다."""
        job = await self._seed("obs-175-secret-001")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", new=AsyncMock(return_value=_FAKE_CLOVA)),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        # _FAKE_CLOVA.raw_text 원문과 파일 경로가 없어야 한다
        assert _FAKE_CLOVA.raw_text not in log
        assert self._tmp.name not in log

    async def test_no_error_message_in_clova_warning_log(self) -> None:
        """CLOVA 오류 경고 로그에 예외 원문(사람용 메시지)이 포함되지 않는다."""
        job = await self._seed("obs-175-secret-002")
        secret_msg = "CLOVA SECRET MESSAGE 민감정보"
        err = ClovaOcrError("CLOVA_HTTP_ERROR", secret_msg)
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=err),
            self.assertLogs(_LOGGER, level="WARNING") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        log = "\n".join(cap.output)
        assert secret_msg not in log
        # error code는 있어야 한다
        assert "CLOVA_HTTP_ERROR" in log

    # --- ocr_job_complete 중복 없음 ---

    async def test_exactly_one_observe_log_per_job(self) -> None:
        """하나의 job 처리에서 ocr_job_complete 로그가 정확히 한 줄 남는다."""
        job = await self._seed("obs-175-once-001")
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", new=AsyncMock(return_value=_FAKE_CLOVA)),
            self.assertLogs(_LOGGER, level="INFO") as cap,
        ):
            mock_cfg.clova_enabled = True
            mock_cfg.OCR_FIXTURE_FALLBACK = True
            await process_ocr_job(str(job.ocr_job_id))

        observe_lines = [line for line in cap.output if "ocr_job_complete" in line]
        assert len(observe_lines) == 1, f"ocr_job_complete가 {len(observe_lines)}번 기록됨"
