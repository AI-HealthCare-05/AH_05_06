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

    confirmed = await repository.update_field(
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
