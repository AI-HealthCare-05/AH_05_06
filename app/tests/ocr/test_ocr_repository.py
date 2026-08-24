import asyncio
from datetime import UTC, date, datetime

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.contrib import test as tortoise_test

from app.models.ocr import (
    OcrDocumentText,
    OcrDocumentType,
    OcrField,
    OcrFieldCandidate,
    OcrJob,
    OcrJobStatus,
    OcrResult,
)
from app.models.patients import Patient
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import UpdateOcrFieldRequest
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository, serialize_field, serialize_job

HOSPITAL_ID = 6000
PATIENT_ID = 600001
VISIT_ID = 600001
DOCUMENT_ID = 600801
ACTOR = OcrActor(staff_id=600101, hospital_id=HOSPITAL_ID, roles=frozenset({"staff"}))


class SyntheticDocumentOwnershipVerifier:
    async def assert_owned(
        self,
        document_id: int,
        visit_id: int,
        hospital_id: int,
        connection: BaseDBAsyncClient,
    ) -> None:
        if (document_id, visit_id, hospital_id) != (DOCUMENT_ID, VISIT_ID, HOSPITAL_ID):
            raise OcrApiError(404, "NOT_FOUND", "OCR 리소스를 찾을 수 없습니다.")


def test_repository_scoping_concurrency_and_field_update_round_trip() -> None:
    tortoise_test._restore_default()
    test_loop = tortoise_test._LOOP
    assert test_loop is not None
    test_loop.run_until_complete(assert_repository_round_trip())


async def assert_repository_round_trip() -> None:
    patient = await Patient.create(
        patient_id=PATIENT_ID,
        hospital_id=HOSPITAL_ID,
        hospital_patient_no="SYNTHETIC-KEY60-001",
        name="Synthetic OCR API Patient",
        birth_date=date(2000, 1, 1),
        phone="01000000000",
    )
    await Visit.create(
        visit_id=VISIT_ID,
        hospital_id=HOSPITAL_ID,
        patient=patient,
        visited_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )
    repository = TortoiseOcrRepository(SyntheticDocumentOwnershipVerifier())

    starts = await asyncio.gather(
        repository.create_job(DOCUMENT_ID, VISIT_ID, OcrDocumentType.EMR, ACTOR),
        repository.create_job(DOCUMENT_ID, VISIT_ID, OcrDocumentType.EMR, ACTOR),
        return_exceptions=True,
    )
    jobs = [item for item in starts if isinstance(item, OcrJob)]
    errors = [item for item in starts if isinstance(item, OcrApiError)]

    assert len(jobs) == 1
    assert len(errors) == 1
    assert errors[0].code == "OCR_ALREADY_PROCESSING"
    job = jobs[0]
    assert serialize_job(job).started_at is None

    job.status = OcrJobStatus.COMPLETED
    await job.save(update_fields=("status",))
    result = await OcrResult.create(ocr_job=job, model_name="synthetic-test-model")
    document = await OcrDocumentText.create(
        ocr_result=result,
        document_id=DOCUMENT_ID,
        document_type=OcrDocumentType.EMR,
        raw_text="synthetic OCR text only",
    )
    field = await OcrField.create(
        ocr_result=result,
        document_text=document,
        field_type="DIAGNOSIS",
        extracted_value="synthetic extracted value",
        unit="mg/dL",
        source_line=5,
        is_pending_report=False,
    )
    await OcrFieldCandidate.create(
        ocr_field=field,
        candidate_value="synthetic candidate",
        rank=1,
    )

    stored_result = await repository.get_result(job.ocr_job_id, ACTOR)
    stored_fields, stored_docs = await repository.get_fields(job.ocr_job_id, ACTOR, "DIAGNOSIS")
    assert stored_result.ocr_job_id == job.ocr_job_id
    assert [item.ocr_field_id for item in stored_fields] == [field.ocr_field_id]

    doc_text_map = {d.ocr_document_text_id: d for d in stored_docs}
    serialized = serialize_field(stored_fields[0], doc_text_map)
    assert serialized.unit == "mg/dL"
    assert serialized.source_line == 5
    assert serialized.is_pending_report is False
    assert serialized.document_id == DOCUMENT_ID

    document.raw_text_purged_at = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    await document.save(update_fields=("raw_text_purged_at",))
    await document.refresh_from_db()
    purged_map = {document.ocr_document_text_id: document}
    purged_serialized = serialize_field(stored_fields[0], purged_map)
    assert purged_serialized.document_id is None

    confirmed, _ = await repository.update_field(
        field.ocr_field_id,
        UpdateOcrFieldRequest(base_version=1, confirm=True),
        ACTOR,
    )
    assert confirmed.corrected_value is None
    assert confirmed.modified_by is None
    assert confirmed.is_confirmed is True
    assert confirmed.confirmed_by == ACTOR.staff_id

    failed_job = await OcrJob.create(
        ocr_job_id="synthetic-key60-failed",
        hospital_id=HOSPITAL_ID,
        visit_id=VISIT_ID,
        requested_by=ACTOR.staff_id,
        status=OcrJobStatus.FAILED,
        failure_code="SYNTHETIC_FAILURE",
    )
    try:
        await repository.get_result(failed_job.ocr_job_id, ACTOR)
    except OcrApiError as exc:
        assert exc.code == "OCR_FAILED"
    else:
        raise AssertionError("FAILED OCR job was reported as pending")

    fail_closed_repository = TortoiseOcrRepository()
    try:
        await fail_closed_repository.create_job(600802, VISIT_ID, OcrDocumentType.EMR, ACTOR)
    except OcrApiError as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("OCR creation bypassed missing document ownership validation")


# KEY-133 — get_latest_job_by_visit 선택 규칙 검증
# 기존 테스트와 ID 충돌을 피하기 위해 별도 병원·환자·진료 ID를 사용한다.
_JOB_VISIT_HOSPITAL_ID = 6100
_JOB_VISIT_PATIENT_ID = 610001
_JOB_VISIT_ID = 610001
_JOB_VISIT_ACTOR = OcrActor(staff_id=610101, hospital_id=_JOB_VISIT_HOSPITAL_ID, roles=frozenset({"staff"}))
_OTHER_HOSPITAL_ACTOR = OcrActor(staff_id=610102, hospital_id=6101, roles=frozenset({"staff"}))


def test_get_latest_job_by_visit_selection_rules() -> None:
    tortoise_test._restore_default()
    test_loop = tortoise_test._LOOP
    assert test_loop is not None
    test_loop.run_until_complete(_assert_get_latest_job_by_visit())


async def _assert_get_latest_job_by_visit() -> None:
    patient = await Patient.create(
        patient_id=_JOB_VISIT_PATIENT_ID,
        hospital_id=_JOB_VISIT_HOSPITAL_ID,
        hospital_patient_no="SYNTHETIC-KEY133-001",
        name="Synthetic Job Visit Patient",
        birth_date=date(2000, 1, 1),
        phone="01000000001",
    )
    visit = await Visit.create(
        visit_id=_JOB_VISIT_ID,
        hospital_id=_JOB_VISIT_HOSPITAL_ID,
        patient=patient,
        visited_at=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
    )
    repository = TortoiseOcrRepository()

    # 작업 없음 → None
    assert await repository.get_latest_job_by_visit(_JOB_VISIT_ID, _JOB_VISIT_ACTOR) is None

    # COMPLETED 두 개: 정렬 방향(-created_at) 검증
    # older가 먼저 생성되므로 newer가 반드시 반환되어야 한다.
    _ = await OcrJob.create(
        ocr_job_id="synthetic-key133-completed-older",
        hospital_id=_JOB_VISIT_HOSPITAL_ID,
        visit=visit,
        requested_by=_JOB_VISIT_ACTOR.staff_id,
        status=OcrJobStatus.COMPLETED,
    )
    newer_completed = await OcrJob.create(
        ocr_job_id="synthetic-key133-completed-newer",
        hospital_id=_JOB_VISIT_HOSPITAL_ID,
        visit=visit,
        requested_by=_JOB_VISIT_ACTOR.staff_id,
        status=OcrJobStatus.COMPLETED,
    )
    result = await repository.get_latest_job_by_visit(_JOB_VISIT_ID, _JOB_VISIT_ACTOR)
    assert result is not None
    assert result.ocr_job_id == newer_completed.ocr_job_id

    # PROCESSING 추가: created_at을 두 COMPLETED보다 과거로 설정해
    # "최신 우선"과 "PROCESSING 우선" 규칙이 서로 다른 작업을 가리키도록 만든다.
    # auto_now_add 필드는 create() 후 update()로 덮어써야 한다.
    processing = await OcrJob.create(
        ocr_job_id="synthetic-key133-processing",
        hospital_id=_JOB_VISIT_HOSPITAL_ID,
        visit=visit,
        requested_by=_JOB_VISIT_ACTOR.staff_id,
        status=OcrJobStatus.PROCESSING,
    )
    await OcrJob.filter(ocr_job_id=processing.ocr_job_id).update(
        created_at=datetime(2026, 8, 23, 8, 0, tzinfo=UTC),
    )
    await processing.refresh_from_db()

    # PROCESSING 분기에서도 타 병원 actor는 None
    assert await repository.get_latest_job_by_visit(_JOB_VISIT_ID, _OTHER_HOSPITAL_ACTOR) is None

    # PROCESSING이 오래된 작업이어도 COMPLETED보다 우선 반환
    result = await repository.get_latest_job_by_visit(_JOB_VISIT_ID, _JOB_VISIT_ACTOR)
    assert result is not None
    assert result.ocr_job_id == processing.ocr_job_id
