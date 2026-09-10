"""OCR Worker 태스크 통합 테스트 — KEY-56 · KEY-199 · KEY-227.

실제 DB를 사용해 process_ocr_job의 경로를 검증한다.
  - CLOVA 성공 → OcrResult(clova-ocr-v2) + COMPLETED
  - CLOVA 저신뢰 → COMPLETED + 저신뢰 OcrField (confidence < 0.75)
  - CLOVA 실패 → FAILED + failure_code=CLOVA_API_ERROR  (워커는 fixture seed 불가 — KEY-199)
  - CLOVA 미설정 → FAILED + failure_code=OCR_NOT_CONFIGURED  (워커는 fixture seed 불가 — KEY-199)
  - 필수 필드 누락 → COMPLETED + 빈 OcrField 행 생성  (못 읽은 필드는 사람이 채운다 — KEY-187)
  - 존재하지 않는 job_id → 예외 없이 종료
  - 이미 완료된 job → 중복 처리 없이 종료, 관측 로그에 ALREADY_PROCESSED
  재시도 (KEY-227):
  - 타임아웃(CLOVA_TIMEOUT) → 최대 2회 재시도 후 FAILED
  - 타임아웃 후 성공 → COMPLETED (재시도로 회복)
  - 구조적 실패(CLOVA_PARSE_ERROR) → 재시도 없이 즉시 FAILED
  멱등성 (KEY-227, KEY-58):
  - 큐에 중복 투입된 job → 두 번째 처리에서 OcrResult 추가 생성 없음
"""

import os
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from tortoise.contrib.test import TestCase

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, ClovaTextField
from ai_worker.tasks.field_extractor import ExtractedField
from ai_worker.tasks.ocr_task import _CLOVA_MODEL_NAME, _MAX_CLOVA_RETRIES, process_ocr_job
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
from app.tests.fixtures.ocr import (
    SYN_FAIL_CLOVA_CODE,
    SYN_LAB_01_CLOVA_RESULT,
    SYN_LOW_CONF_CLOVA_RESULT,
    SYN_LOW_CONF_EMR_CLOVA_RESULT,
    SYN_TIMEOUT_CLOVA_CODE,
)

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

    async def test_the_worker_carries_the_unit_into_the_field_row(self) -> None:
        """**추출기가 읽은 단위가 `OcrField.unit` 까지 간다** — KEY-291.

        읽는 쪽(`course_days`)은 KEY-271 부터 이 칸으로 통↔일을 환산하는데,
        **쓰는 쪽이 여태 안 채웠다.** 그래서 시드로 부은 진료는 맞고 실제
        판독으로 들어온 진료는 「3통」이 3일로 나갔다.

        추출기는 **문서가 스스로 말한 자리**에만 단위를 적는다 — 헤더가
        「처방일수」인 표, 「84일 처방」 같은 글자(이희진 님 `#259` 리뷰).
        EMR 「총투」 칸처럼 말하지 않은 자리는 `None` 으로 두어 사람이 고른다.

        이 검사는 그 둘 중 **어느 쪽이 오든 행까지 그대로 간다**는 것만 본다 —
        안 그러면 이 한 줄(`unit=field.unit`)을 지워도 아무도 안 운다. 어느
        자리에 무엇을 적는지는 `ai_worker/tests/test_field_extractor.py` 가 잰다.
        """
        job = await self._seed("ocr_key291_unit_carried")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=_FAKE_CLOVA_RESULT),
            ),
            patch(
                "ai_worker.tasks.ocr_task.extract_fields",
                return_value=[
                    ExtractedField(
                        field_type="DURATION_DAYS",
                        extracted_value="3",
                        confidence=Decimal("0.70"),
                        unit="통",
                    ),
                ],
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        row = await OcrField.filter(ocr_result=result, field_type="DURATION_DAYS").first()
        assert row is not None, "처방일수 행이 아예 안 생겼다"
        assert row.extracted_value == "3"
        assert row.unit == "통", f"추출기가 읽은 단위가 행까지 안 갔다 — {row.unit!r}"

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

    # ── CLOVA 실패 → FAILED ──────────────────────────────────────────────────

    async def test_clova_error_marks_job_failed(self) -> None:
        """비재시도 오류(CLOVA_INFER_FAILED)는 즉시 FAILED — call_clova_ocr는 1번만 호출된다."""
        job = await self._seed("ocr_key56_clova_err")
        mock_clova = AsyncMock(side_effect=ClovaOcrError("CLOVA_INFER_FAILED", "infer failed"))

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", mock_clova),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "CLOVA_API_ERROR"
        assert job.progress == 0
        assert mock_clova.call_count == 1
        assert await OcrResult.filter(ocr_job=job).count() == 0

    async def test_failed_job_progress_resets_to_zero_after_partial_clova(self) -> None:
        """다중 문서 중 첫 번째 CLOVA 성공(진행률 중간값)→ 두 번째 실패 시 progress가 0으로 재설정된다."""
        patient = await Patient.create(
            patient_id=910090,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY125-PROGRESS",
            name="테스트환자125",
            birth_date=date(1990, 1, 1),
            phone="01000000099",
        )
        visit = await Visit.create(
            visit_id=910090,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
        )
        doc1 = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        doc2 = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job = await OcrJob.create(
            ocr_job_id="ocr_key125_partial_progress",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(ocr_job=job, document_id=doc1.document_id, document_type=OcrDocumentType.LAB_RESULT)
        await OcrJobDocument.create(ocr_job=job, document_id=doc2.document_id, document_type=OcrDocumentType.LAB_RESULT)

        # 첫 번째 문서는 성공(진행률 35%), 두 번째는 비재시도 오류로 실패
        call_count = 0

        async def clova_first_ok_then_fail(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FAKE_CLOVA_RESULT
            raise ClovaOcrError("CLOVA_INFER_FAILED", "second doc failed")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", side_effect=clova_first_ok_then_fail),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.progress == 0

    # ── CLOVA 비활성 → FAILED (KEY-199: 워커는 fixture seed 불가) ───────────

    async def test_clova_disabled_marks_job_failed(self) -> None:
        job = await self._seed("ocr_key56_no_clova")

        with patch("ai_worker.tasks.ocr_task.config") as mock_cfg:
            mock_cfg.clova_enabled = False
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "OCR_NOT_CONFIGURED"
        assert job.progress == 0

        assert await OcrResult.filter(ocr_job=job).count() == 0

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
        assert result.model_name != "fixture-v0"

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

    # ── 저신뢰 fixture (KEY-227 · KEY-125) ───────────────────────────────────

    async def test_low_confidence_result_completes_job(self) -> None:
        """저신뢰 CLOVA 결과(LAB_RESULT)도 OcrJob을 COMPLETED로 끝낸다.

        confidence < 0.75 항목은 화면이 저신뢰로 표시하지만, job 자체는 성공이다.
        사람이 판단해 확정하면 안내 생성에 쓸 수 있다.
        """
        job = await self._seed("ocr_key227_low_conf")

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=SYN_LOW_CONF_CLOVA_RESULT),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED
        assert job.progress == 100

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None

        fields = await OcrField.filter(ocr_result=result).all()
        conf_map = {f.field_type: f.confidence for f in fields if f.confidence is not None}
        assert any(c < 0.75 for c in conf_map.values()), "저신뢰 필드가 없다"

    async def test_emr_low_confidence_fields_are_saved_and_flaggable(self) -> None:
        """EMR 저신뢰 결과 — confidence·저신뢰 판정 근거 검증 (KEY-125 추가 인수조건).

        기대 필드: DIAGNOSIS(자궁내막증, confidence=0.62) · MEDICATION_NAME(비잔정, confidence=0.58)
        실제 추출값과 confidence가 fixture 정의와 일치해야 한다.
        저신뢰(< 0.75) 필드는 is_confirmed=False 로 저장되며,
        직원 확인 없이 안내 생성 근거로 사용할 수 없다.
        """
        patient = await Patient.create(
            patient_id=910091,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY125-EMR-LOW-CONF",
            name="테스트환자125EMR",
            birth_date=date(1990, 1, 1),
            phone="01000000091",
        )
        visit = await Visit.create(
            visit_id=910091,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
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
            ocr_job_id="ocr_key125_emr_low_conf",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job,
            document_id=med_doc.document_id,
            document_type=OcrDocumentType.EMR,
        )

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=SYN_LOW_CONF_EMR_CLOVA_RESULT),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED
        assert job.progress == 100

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None

        fields = await OcrField.filter(ocr_result=result).all()
        by_type = {f.field_type: f for f in fields}

        # 기대 필드·실제 값·confidence — fixture 정의와 일치해야 한다
        # SYN_LOW_CONF_EMR_CLOVA_BLOCKS: DIAGNOSIS confidence=0.62, MEDICATION_NAME confidence=0.58
        diag = by_type.get("DIAGNOSIS")
        assert diag is not None, "DIAGNOSIS 필드 없음"
        assert diag.extracted_value == "자궁내막증"
        assert diag.confidence == Decimal("0.62"), (
            f"DIAGNOSIS confidence={diag.confidence} — fixture 정의(0.62)와 일치해야 한다"
        )
        assert not diag.is_confirmed, "저신뢰 필드는 직원 확인 전 is_confirmed=False 여야 한다"

        med = by_type.get("MEDICATION_NAME")
        assert med is not None, "MEDICATION_NAME 필드 없음"
        assert med.extracted_value == "비잔정(디에노게스트)2mg", f"약품명 불일치: {med.extracted_value}"
        assert med.confidence == Decimal("0.58"), (
            f"MEDICATION_NAME confidence={med.confidence} — fixture 정의(0.58)와 일치해야 한다"
        )
        assert not med.is_confirmed, "저신뢰 필드는 직원 확인 전 is_confirmed=False 여야 한다"

    async def test_progress_reaches_80_at_field_extraction_stage(self) -> None:
        """필드 추출 완료 시 progress=80이 기록된다 — 대기→판독→추출→저장→완료 중 세 번째 단계."""
        job = await self._seed("ocr_key125_progress_80")
        progress_snapshots: list[int] = []

        original_save = OcrJob.save

        async def capturing_save(self_job, *args, **kwargs):
            await original_save(self_job, *args, **kwargs)
            if "progress" in kwargs.get("update_fields", ()):
                progress_snapshots.append(self_job.progress)

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", AsyncMock(return_value=SYN_LOW_CONF_CLOVA_RESULT)),
            patch.object(OcrJob, "save", capturing_save),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        # CLOVA 완료(70%) → 필드 추출 완료(80%) → 저장 완료(100%) 순으로 갱신되어야 한다
        assert 80 in progress_snapshots, f"progress=80 단계가 없다: {progress_snapshots}"
        assert progress_snapshots[-1] == 100, f"최종 progress가 100이 아니다: {progress_snapshots}"
        assert progress_snapshots == sorted(progress_snapshots), (
            f"progress가 단조 증가하지 않는다: {progress_snapshots}"
        )

    # ── 재시도 로직 (KEY-227) ─────────────────────────────────────────────────

    async def test_timeout_retries_then_fails(self) -> None:
        """CLOVA_TIMEOUT은 재시도 대상이다 — _MAX_CLOVA_RETRIES 소진 후 FAILED.

        call_clova_ocr가 매번 CLOVA_TIMEOUT을 올리면
        총 1 + _MAX_CLOVA_RETRIES 번 호출되고 최종적으로 FAILED가 된다.
        """
        job = await self._seed("ocr_key227_timeout_retry")
        mock_clova = AsyncMock(side_effect=ClovaOcrError(SYN_TIMEOUT_CLOVA_CODE, "timeout"))

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", mock_clova),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "CLOVA_API_ERROR"
        assert mock_clova.call_count == 1 + _MAX_CLOVA_RETRIES

    async def test_timeout_retry_succeeds_on_second_attempt(self) -> None:
        """첫 번째 CLOVA 호출이 타임아웃돼도 재시도에서 성공하면 COMPLETED.

        재시도 후 성공 시 OcrResult·OcrField가 단 한 번만 생성된다 (인수조건 6).
        """
        job = await self._seed("ocr_key227_retry_ok")
        mock_clova = AsyncMock(
            side_effect=[
                ClovaOcrError(SYN_TIMEOUT_CLOVA_CODE, "timeout"),
                _FAKE_CLOVA_RESULT,
            ]
        )

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", mock_clova),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED
        assert mock_clova.call_count == 2

        # 재시도 성공 후에도 OcrResult는 한 건만 생성된다
        assert await OcrResult.filter(ocr_job=job).count() == 1

    async def test_non_retryable_error_fails_immediately(self) -> None:
        """CLOVA_PARSE_ERROR 같은 구조적 실패는 재시도 없이 즉시 FAILED.

        call_clova_ocr는 정확히 1번만 호출된다.
        """
        job = await self._seed("ocr_key227_parse_err")
        mock_clova = AsyncMock(side_effect=ClovaOcrError(SYN_FAIL_CLOVA_CODE, "parse error"))

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", mock_clova),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.FAILED
        assert job.failure_code == "CLOVA_API_ERROR"
        assert mock_clova.call_count == 1

    # ── 중복 실행 방지 / 멱등성 (KEY-227, KEY-58) ─────────────────────────────

    async def test_already_processed_is_logged(self) -> None:
        """이미 COMPLETED인 job이 큐에 재투입돼도 재처리되지 않는다.

        _observe가 error_code="ALREADY_PROCESSED"로 호출되고 OcrResult는 추가 생성되지 않는다.
        """
        job = await self._seed("ocr_key227_dup_queue")
        job.status = OcrJobStatus.COMPLETED
        await job.save(update_fields=("status",))

        with patch("ai_worker.tasks.ocr_task._observe") as mock_observe:
            await process_ocr_job(job.ocr_job_id)

        observed_codes = [c.kwargs.get("error_code") for c in mock_observe.call_args_list]
        assert "ALREADY_PROCESSED" in observed_codes, "ALREADY_PROCESSED가 관측 로그에 없다"
        assert await OcrResult.filter(ocr_job=job).count() == 0

    # ── EMR로 업로드된 검사결과지 자동 재분류 (KEY-278) ──────────────────────────

    async def test_lab_result_uploaded_as_emr_is_reclassified(self) -> None:
        """검사결과지를 EMR로 업로드해도 OCR 후 LAB_RESULT로 자동 재분류된다.

        업로드 시 document_type을 보내지 않아 EMR로 저장된 검사결과지가
        CLOVA 판독 후 올바른 유형으로 갱신되어야 한다 (KEY-278 인수조건).
        """
        patient = await Patient.create(
            patient_id=910010,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY278",
            name="테스트환자278",
            birth_date=date(1990, 1, 1),
            phone="01000000010",
        )
        visit = await Visit.create(
            visit_id=910010,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 9, 7, 9, 0, tzinfo=UTC),
        )
        med_doc = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.EMR,  # 업로드 시 기본값
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job = await OcrJob.create(
            ocr_job_id="ocr_key278_auto_reclassify",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        job_doc = await OcrJobDocument.create(
            ocr_job=job,
            document_id=med_doc.document_id,
            document_type=OcrDocumentType.EMR,  # 업로드 시 기본값
        )

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=SYN_LAB_01_CLOVA_RESULT),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job.ocr_job_id)

        await job.refresh_from_db()
        assert job.status == OcrJobStatus.COMPLETED

        await med_doc.refresh_from_db()
        assert med_doc.document_type == OcrDocumentType.LAB_RESULT, "검사결과지가 LAB_RESULT로 재분류되지 않았다"

        await job_doc.refresh_from_db()
        assert job_doc.document_type == OcrDocumentType.LAB_RESULT, "OcrJobDocument의 document_type이 갱신되지 않았다"

        result = await OcrResult.filter(ocr_job=job).first()
        assert result is not None
        fields = await OcrField.filter(ocr_result=result).all()
        field_types = {f.field_type for f in fields}
        assert "AST" in field_types, "LAB_RESULT 파서가 실행되지 않았다"
        for emr_field in ("DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"):
            assert emr_field not in field_types, f"검사결과지에 EMR 필드 {emr_field}가 생성됐다"

    async def test_duplicate_queue_entry_creates_single_result(self) -> None:
        """같은 job_id가 큐에 두 번 들어와도 OcrResult·OcrField는 한 건만 생성된다.

        첫 번째 처리 후 job.status=COMPLETED가 되므로,
        두 번째 process_ocr_job 호출은 ALREADY_PROCESSED로 종료된다 (인수조건 6).
        """
        job = await self._seed("ocr_key227_dup_result")
        mock_clova = AsyncMock(return_value=_FAKE_CLOVA_RESULT)

        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch("ai_worker.tasks.ocr_task.call_clova_ocr", mock_clova),
        ):
            mock_cfg.clova_enabled = True
            # 첫 번째 처리
            await process_ocr_job(job.ocr_job_id)
            # 두 번째 처리 — 큐에 중복 투입된 상황
            await process_ocr_job(job.ocr_job_id)

        # CLOVA 호출은 첫 번째 처리에서만 발생해야 한다
        assert mock_clova.call_count == 1
        # OcrResult는 단 한 건
        assert await OcrResult.filter(ocr_job=job).count() == 1


# ── KEY-288 파일별 부분 실패 격리 ──────────────────────────────────────────────

VISIT_ID_KEY288 = 910010
PATIENT_ID_KEY288 = 910010


class TestPerFileJobIsolation(TestCase):
    """파일별 OcrJob 구조에서 한 파일 실패가 다른 파일 결과를 덮지 않음을 검증한다.

    인수조건 2, 5 (KEY-288):
    - 파일 하나가 CLOVA 하드 실패해도 나머지 파일의 OcrResult/OcrField는 정상 저장된다.
    - 실패한 파일은 FAILED 상태로만 표시된다.
    """

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        self._tmp.write(JPEG_BYTES)
        self._tmp.close()

    def tearDown(self) -> None:
        os.unlink(self._tmp.name)
        super().tearDown()

    async def _seed_two_jobs(self) -> tuple[OcrJob, OcrJob]:
        """같은 진료에 파일 2개를 별도 job으로 생성한다 (옵션 A 구조)."""
        patient = await Patient.create(
            patient_id=PATIENT_ID_KEY288,
            hospital_id=HOSPITAL_ID,
            hospital_patient_no="TEST-KEY288",
            name="테스트환자288",
            birth_date=date(1990, 1, 1),
            phone="01000000001",
        )
        visit = await Visit.create(
            visit_id=VISIT_ID_KEY288,
            hospital_id=HOSPITAL_ID,
            patient=patient,
            visited_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        )

        doc1 = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.EMR,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job1 = await OcrJob.create(
            ocr_job_id="ocr_key288_job1_success",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job1,
            document_id=doc1.document_id,
            document_type=OcrDocumentType.EMR,
        )

        doc2 = await MedicalDocument.create(
            hospital_id=HOSPITAL_ID,
            visit=visit,
            document_type=OcrDocumentType.LAB_RESULT,
            file_path=self._tmp.name,
            file_size=len(JPEG_BYTES),
            mime_type="image/jpeg",
            uploaded_by=1,
        )
        job2 = await OcrJob.create(
            ocr_job_id="ocr_key288_job2_fail",
            hospital_id=HOSPITAL_ID,
            visit=visit,
            requested_by=1,
        )
        await OcrJobDocument.create(
            ocr_job=job2,
            document_id=doc2.document_id,
            document_type=OcrDocumentType.LAB_RESULT,
        )
        return job1, job2

    async def test_failed_file_does_not_destroy_successful_file_result(self) -> None:
        """파일 2(CLOVA 하드 실패) → FAILED, 파일 1(성공) → COMPLETED + OcrResult/OcrField 보존."""
        job1, job2 = await self._seed_two_jobs()

        # job1: CLOVA 성공
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(return_value=_FAKE_CLOVA_RESULT),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job1.ocr_job_id)

        # job2: CLOVA 하드 실패
        with (
            patch("ai_worker.tasks.ocr_task.config") as mock_cfg,
            patch(
                "ai_worker.tasks.ocr_task.call_clova_ocr",
                AsyncMock(side_effect=ClovaOcrError(SYN_FAIL_CLOVA_CODE, "hard failure")),
            ),
        ):
            mock_cfg.clova_enabled = True
            await process_ocr_job(job2.ocr_job_id)

        # job2는 FAILED
        await job2.refresh_from_db()
        assert job2.status == OcrJobStatus.FAILED
        assert job2.failure_code == "CLOVA_API_ERROR"
        assert await OcrResult.filter(ocr_job=job2).count() == 0, "실패한 job에 OcrResult가 생성되면 안 된다"

        # job1은 COMPLETED이고 OcrResult/OcrField가 정상 보존된다
        await job1.refresh_from_db()
        assert job1.status == OcrJobStatus.COMPLETED, "성공한 파일의 job이 FAILED가 됐다"
        result1 = await OcrResult.filter(ocr_job=job1).first()
        assert result1 is not None, "성공한 파일의 OcrResult가 사라졌다"
        fields1 = await OcrField.filter(ocr_result=result1).all()
        assert len(fields1) > 0, "성공한 파일의 OcrField가 비어 있다"
