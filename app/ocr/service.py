from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from fastapi import status
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.models.ocr import (
    OcrDocumentText,
    OcrDocumentType,
    OcrField,
    OcrFieldCandidate,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
    OcrResult,
)
from app.models.prescriptions import AS_NEEDED, Prescription, PrescriptionItem
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import (
    FinalizeOcrResponse,
    OcrCandidateResponse,
    OcrDocumentResponse,
    OcrFieldResponse,
    OcrJobByDocumentResponse,
    OcrJobResponse,
    OcrResultResponse,
    PrescriptionItemResponse,
    UpdateOcrFieldRequest,
)
from app.ocr.security import OcrActor


class OcrRepository(Protocol):
    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob: ...

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None: ...

    async def get_latest_jobs_by_document(
        self, visit_id: int, actor: OcrActor
    ) -> list[tuple[OcrJobDocument, OcrJob]]: ...

    async def get_result(self, ocr_job_id: str, actor: OcrActor) -> OcrResult: ...

    async def get_fields(
        self, ocr_job_id: str, actor: OcrActor, field_type: str | None
    ) -> tuple[Sequence[OcrField], Sequence[OcrDocumentText]]: ...

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> tuple[OcrField, Sequence[OcrDocumentText]]: ...

    async def write_field(
        self, visit_id: int, field_type: str, value: str | None, actor: OcrActor
    ) -> tuple[OcrField | None, Sequence[OcrDocumentText]]: ...

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob: ...

    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> Prescription: ...


def _collect_item_rows(
    fields_by_type: dict[str, "OcrField"],
) -> list[tuple[str, str, int | None]]:
    rows: list[tuple[str, str, int | None]] = []
    for suffix in ("", "_2", "_3", "_4", "_5"):
        med_field = fields_by_type.get(f"MEDICATION_NAME{suffix}")
        if med_field is None or not med_field.value:
            continue
        freq_field = fields_by_type.get(f"FREQUENCY{suffix}")
        frequency = freq_field.value if freq_field is not None and freq_field.value else ""
        dur_field = fields_by_type.get(f"DURATION_DAYS{suffix}")
        duration_days: int | None = None
        if frequency != AS_NEEDED and dur_field is not None and dur_field.value:
            digits = "".join(ch for ch in dur_field.value if ch.isdigit())
            if digits:
                duration_days = int(digits)
        rows.append((med_field.value, frequency, duration_days))
    return rows


def _not_found() -> OcrApiError:
    return OcrApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "OCR 리소스를 찾을 수 없습니다.")


class TortoiseOcrRepository:
    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob:
        job = await OcrJob.filter(ocr_job_id=ocr_job_id, hospital_id=actor.hospital_id).first()
        if job is None:
            raise _not_found()
        return job

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None:
        # 진행 중인 작업이 있으면 그것이 현재 작업이다.
        # 없으면 같은 진료의 가장 최근 작업을 반환한다.
        job = (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
                status=OcrJobStatus.PROCESSING,
            )
            .order_by("-created_at")
            .first()
        )
        if job is not None:
            return job
        return (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
            )
            .order_by("-created_at")
            .first()
        )

    async def get_latest_jobs_by_document(self, visit_id: int, actor: OcrActor) -> list[tuple[OcrJobDocument, OcrJob]]:
        # Jobs ordered newest-first; first occurrence per document_id is the latest job.
        jobs = await (
            OcrJob.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
            .order_by("-created_at")
            .prefetch_related("source_documents")
        )
        seen: dict[int, tuple[OcrJobDocument, OcrJob]] = {}
        for job in jobs:
            for jd in job.source_documents:
                if jd.document_id not in seen:
                    seen[jd.document_id] = (jd, job)
        return list(seen.values())

    async def get_result(self, ocr_job_id: str, actor: OcrActor) -> OcrResult:
        job = await self.get_job(ocr_job_id, actor)
        if job.status == OcrJobStatus.FAILED:
            raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_FAILED", "OCR 처리가 실패했습니다.")
        if job.status != OcrJobStatus.COMPLETED:
            raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_RESULT_NOT_READY", "OCR 결과가 아직 준비되지 않았습니다.")
        result = (
            await OcrResult.filter(ocr_job_id=ocr_job_id)
            .prefetch_related("documents", "fields", "fields__candidates")
            .first()
        )
        if result is None:
            raise _not_found()
        return result

    async def get_fields(
        self, ocr_job_id: str, actor: OcrActor, field_type: str | None
    ) -> tuple[Sequence[OcrField], Sequence[OcrDocumentText]]:
        result = await self.get_result(ocr_job_id, actor)
        fields = [field for field in result.fields if field_type is None or field.field_type == field_type]
        return sorted(fields, key=lambda field: field.ocr_field_id), list(result.documents)

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> tuple[OcrField, Sequence[OcrDocumentText]]:
        async with in_transaction() as connection:
            field = (
                await OcrField.filter(
                    ocr_field_id=ocr_field_id,
                    ocr_result__ocr_job__hospital_id=actor.hospital_id,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if field is None:
                raise _not_found()
            if field.is_confirmed:
                raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_FIELD_CONFIRMED", "이미 확정된 필드입니다.")
            if field.version != request.base_version:
                raise OcrApiError(status.HTTP_409_CONFLICT, "VERSION_CONFLICT", "필드 버전이 변경되었습니다.")

            corrected_value = request.corrected_value.strip() if request.corrected_value is not None else None
            selected_candidate: OcrFieldCandidate | None = None
            if request.candidate_id is not None:
                selected_candidate = (
                    await OcrFieldCandidate.filter(
                        ocr_field_candidate_id=request.candidate_id,
                        ocr_field_id=field.ocr_field_id,
                    )
                    .using_db(connection)
                    .first()
                )
                if selected_candidate is None:
                    raise OcrApiError(
                        status.HTTP_400_BAD_REQUEST,
                        "INVALID_CANDIDATE",
                        "해당 필드의 후보값이 아닙니다.",
                    )
                corrected_value = selected_candidate.candidate_value
                await (
                    OcrFieldCandidate.filter(ocr_field_id=field.ocr_field_id)
                    .using_db(connection)
                    .update(is_selected=False)
                )
                selected_candidate.is_selected = True
                await selected_candidate.save(update_fields=("is_selected",), using_db=connection)

            changed_at = now()
            if request.corrected_value is not None or selected_candidate is not None:
                field.corrected_value = corrected_value
                field.modified_by = actor.staff_id
                field.modified_at = changed_at
            field.version += 1
            if request.confirm:
                field.is_confirmed = True
                field.confirmed_by = actor.staff_id
                field.confirmed_at = changed_at
            await field.save(using_db=connection)
        await field.fetch_related("candidates")

        doc_text_ids = {field.document_text_id} if field.document_text_id is not None else set()
        doc_text_ids.update(c.document_text_id for c in field.candidates if c.document_text_id is not None)
        doc_texts = (
            await OcrDocumentText.filter(ocr_document_text_id__in=list(doc_text_ids)).all() if doc_text_ids else []
        )
        return field, doc_texts

    async def write_field(
        self, visit_id: int, field_type: str, value: str | None, actor: OcrActor
    ) -> tuple[OcrField | None, Sequence[OcrDocumentText]]:
        """판독이 못 읽은 값을 사람이 적어 넣는다 — 와이어프레임 S1-7 「직접 입력」.

        **고치기(PATCH)와 다른 길이다.** 저쪽은 있는 줄의 값을 바꾸고, 이쪽은
        **줄 자체가 없는** 것을 만든다. 판독이 못 찾은 항목은 레코드로 남지
        않아서, 화면이 값을 적어도 보낼 곳이 없었다.

        `confidence` 는 비운다. 사람이 적은 값에 기계의 확신을 붙이면, 화면이
        「낮은 확신」으로 다시 물어보거나 반대로 확신한 값처럼 보인다.
        """
        job = await self.get_latest_job_by_visit(visit_id, actor)
        if job is None:
            raise _not_found()

        result = await OcrResult.filter(ocr_job_id=job.ocr_job_id).first()
        if result is None:
            raise _not_found()

        text = value.strip() if value is not None else ""

        async with in_transaction() as connection:
            field = (
                await OcrField.filter(ocr_result_id=result.ocr_result_id, field_type=field_type)
                .using_db(connection)
                .select_for_update()
                .first()
            )

            if field is not None and field.is_confirmed:
                raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_FIELD_CONFIRMED", "이미 확정된 필드입니다.")

            # 비우면 지운다 — 「빈 값으로 적었다」를 남기면 안 적은 것과 구별이 안 된다.
            if not text:
                if field is not None:
                    await field.delete(using_db=connection)
                return None, []

            changed_at = now()
            if field is None:
                field = await OcrField.create(
                    ocr_result_id=result.ocr_result_id,
                    field_type=field_type,
                    corrected_value=text,
                    modified_by=actor.staff_id,
                    modified_at=changed_at,
                    using_db=connection,
                )
            else:
                field.corrected_value = text
                field.modified_by = actor.staff_id
                field.modified_at = changed_at
                field.version += 1
                await field.save(using_db=connection)

        await field.fetch_related("candidates")
        return field, []

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob:
        job = await self.get_job(ocr_job_id, actor)
        if not job.excluded_from_guide:
            job.excluded_from_guide = True
            await job.save(update_fields=("excluded_from_guide",))
        return job

    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> Prescription:
        # GuideService.generate()와 동일한 기준으로 job을 선택한다.
        # excluded된 job이나 COMPLETED가 아닌 job으로 처방을 만드는 것을 막는다.
        job = (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
                excluded_from_guide=False,
                status=OcrJobStatus.COMPLETED,
            )
            .order_by("-created_at")
            .first()
        )
        if job is None:
            raise _not_found()

        result = await OcrResult.filter(ocr_job_id=job.ocr_job_id).prefetch_related("fields").first()
        if result is None:
            raise _not_found()

        fields_by_type: dict[str, OcrField] = {f.field_type: f for f in result.fields}

        if not fields_by_type:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "OCR_NOT_CONFIRMED",
                "확정된 OCR 항목이 없습니다.",
            )

        unconfirmed = next((f for f in result.fields if not f.is_confirmed), None)
        if unconfirmed is not None:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "OCR_NOT_CONFIRMED",
                "확정되지 않은 OCR 항목이 있습니다. 모든 항목을 먼저 확정해 주세요.",
            )

        ps_field = fields_by_type.get("PRESCRIPTION_SET")
        if ps_field is None or not ps_field.value:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "MISSING_PRESCRIPTION_SET",
                "처방 세트(PRESCRIPTION_SET) 필드가 없습니다.",
            )

        freq_field = fields_by_type.get("FREQUENCY")
        if freq_field is None or not freq_field.value:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "MISSING_FREQUENCY",
                "복용법(FREQUENCY) 필드가 없습니다.",
            )

        item_rows = _collect_item_rows(fields_by_type)

        async with in_transaction() as connection:
            # Visit 행을 먼저 잠가서 동시 finalize를 직렬화한다.
            # select_for_update()는 매칭 행이 없으면 락을 걸지 못하므로
            # 항상 존재하는 Visit을 진입점으로 쓴다 (guides.py 동일 패턴).
            if (
                await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
                .using_db(connection)
                .select_for_update()
                .first()
            ) is None:
                raise _not_found()

            prescription = await Prescription.filter(visit_id=visit_id).using_db(connection).first()
            if prescription is None:
                prescription = await Prescription.create(
                    visit_id=visit_id,
                    prescription_set=ps_field.value,
                    using_db=connection,
                )
            else:
                prescription.prescription_set = ps_field.value
                await prescription.save(update_fields=("prescription_set",), using_db=connection)

            await PrescriptionItem.filter(prescription_id=prescription.prescription_id).using_db(connection).delete()
            for name, frequency, duration_days in item_rows:
                await PrescriptionItem.create(
                    prescription=prescription,
                    name=name,
                    frequency=frequency,
                    duration_days=duration_days,
                    using_db=connection,
                )

        await prescription.fetch_related("items")
        return prescription


def serialize_job(job: OcrJob) -> OcrJobResponse:
    return OcrJobResponse(
        ocr_job_id=job.ocr_job_id,
        status=job.status,
        progress=job.progress,
        started_at=job.started_at,
        completed_at=job.completed_at,
        failure_code=job.failure_code,
        excluded_from_guide=job.excluded_from_guide,
    )


LOW_CONFIDENCE_THRESHOLD = 0.75
FIXTURE_MODEL_NAME = "fixture-v0"


async def seed_fixture_result(
    job: OcrJob,
    documents: list[tuple[int, OcrDocumentType]],
    connection: BaseDBAsyncClient,
) -> None:
    """fixture 결과를 DB에 기록하고 job을 COMPLETED로 전환한다 — 업로드 경로에서 job당 한 번 호출, 데모 전용.

    OcrResult.ocr_job 은 OneToOneField, OcrField 는 (ocr_result, field_type) unique 제약이 있으므로
    OcrDocumentText 는 문서마다 생성하고 OcrField 는 결과 전체에 하나만 만든다.
    """
    completed_at = now()
    result = await OcrResult.create(ocr_job=job, model_name=FIXTURE_MODEL_NAME, using_db=connection)
    first_doc_text = None
    for document_id, document_type in documents:
        doc_text = await OcrDocumentText.create(
            ocr_result=result,
            document_id=document_id,
            document_type=document_type,
            raw_text="[fixture] 합성 OCR 텍스트 — 실제 OCR 워커 연결 전 데모용 데이터",
            using_db=connection,
        )
        if first_doc_text is None:
            first_doc_text = doc_text
    await OcrField.create(
        ocr_result=result,
        document_text=first_doc_text,
        field_type="DIAGNOSIS",
        extracted_value="[fixture] 진단명",
        confidence=Decimal("0.85"),
        using_db=connection,
    )
    job.status = OcrJobStatus.COMPLETED
    job.progress = 100
    # 업로드 시 즉시 fixture를 심는 데모 경로에는 시작 시각이 없으므로 완료
    # 시각을 함께 기록한다. 반면 Worker가 실제 CLOVA를 시도한 뒤 fallback으로
    # 들어온 경우에는 이미 `started_at`이 있다. 그것을 덮어쓰면 처리시간이
    # 언제나 0ms가 되어 KEY-69 실행 증적이 사라진다.
    if job.started_at is None:
        job.started_at = completed_at
    job.completed_at = completed_at
    await job.save(
        update_fields=("status", "progress", "started_at", "completed_at"),
        using_db=connection,
    )


def _resolve_document_id(doc_text: OcrDocumentText | None) -> int | None:
    """원문 파기 후에는 None — document_id·source_line으로 원문 우회 노출 방지."""
    return doc_text.document_id if (doc_text is not None and doc_text.raw_text_purged_at is None) else None


def serialize_candidate(
    candidate: OcrFieldCandidate, doc_text_map: dict[int, OcrDocumentText] | None = None
) -> OcrCandidateResponse:
    confidence = float(candidate.confidence) if isinstance(candidate.confidence, Decimal) else candidate.confidence
    doc_text_map = doc_text_map or {}
    return OcrCandidateResponse(
        ocr_field_candidate_id=candidate.ocr_field_candidate_id,
        value=candidate.candidate_value,
        confidence=confidence,
        rank=candidate.rank,
        source_date=candidate.source_date,
        source_line=candidate.source_line,
        document_id=_resolve_document_id(
            doc_text_map.get(candidate.document_text_id) if candidate.document_text_id is not None else None
        ),
        is_selected=candidate.is_selected,
    )


def _serialize_candidates(field: OcrField, doc_text_map: dict[int, OcrDocumentText]) -> list[OcrCandidateResponse]:
    rel = getattr(field, "candidates", None)
    if rel is None or not getattr(rel, "_fetched", False):
        return []
    return [serialize_candidate(item, doc_text_map) for item in rel]


def serialize_field(field: OcrField, doc_text_map: dict[int, OcrDocumentText] | None = None) -> OcrFieldResponse:
    doc_text_map = doc_text_map or {}
    confidence = float(field.confidence) if isinstance(field.confidence, Decimal) else field.confidence
    return OcrFieldResponse(
        ocr_field_id=field.ocr_field_id,
        field_type=field.field_type,
        extracted_value=field.extracted_value,
        corrected_value=field.corrected_value,
        value=field.value,
        unit=field.unit,
        confidence=confidence,
        is_low_confidence=confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD,
        version=field.version,
        is_confirmed=field.is_confirmed,
        is_pending_report=field.is_pending_report,
        document_id=_resolve_document_id(
            doc_text_map.get(field.document_text_id) if field.document_text_id is not None else None
        ),
        source_line=field.source_line,
        modified_by=field.modified_by,
        modified_at=field.modified_at,
        confirmed_by=field.confirmed_by,
        confirmed_at=field.confirmed_at,
        candidates=_serialize_candidates(field, doc_text_map),
    )


class OcrService:
    def __init__(self, repository: OcrRepository) -> None:
        self.repository = repository

    async def job_for_visit(self, visit_id: int, actor: OcrActor) -> OcrJobResponse:
        job = await self.repository.get_latest_job_by_visit(visit_id, actor)
        if job is None:
            raise _not_found()
        return serialize_job(job)

    async def jobs_for_visit(self, visit_id: int, actor: OcrActor) -> list[OcrJobByDocumentResponse]:
        pairs = await self.repository.get_latest_jobs_by_document(visit_id, actor)
        return [
            OcrJobByDocumentResponse(
                document_id=jd.document_id,
                document_type=jd.document_type,
                ocr_job_id=job.ocr_job_id,
                status=job.status,
                progress=job.progress,
                started_at=job.started_at,
                completed_at=job.completed_at,
                failure_code=job.failure_code,
                excluded_from_guide=job.excluded_from_guide,
            )
            for jd, job in pairs
        ]

    async def status(self, ocr_job_id: str, actor: OcrActor) -> OcrJobResponse:
        return serialize_job(await self.repository.get_job(ocr_job_id, actor))

    async def result(self, ocr_job_id: str, actor: OcrActor) -> OcrResultResponse:
        result = await self.repository.get_result(ocr_job_id, actor)
        doc_text_map = {d.ocr_document_text_id: d for d in result.documents}
        return OcrResultResponse(
            ocr_result_id=result.ocr_result_id,
            ocr_job_id=result.ocr_job_id,
            model_name=result.model_name,
            model_version=result.model_version,
            version=result.version,
            confirmed_by=result.confirmed_by,
            confirmed_at=result.confirmed_at,
            documents=[
                OcrDocumentResponse(
                    document_id=item.document_id,
                    document_type=item.document_type,
                    raw_text=item.raw_text,
                    raw_text_purged_at=item.raw_text_purged_at,
                )
                for item in result.documents
            ],
            fields=[serialize_field(item, doc_text_map) for item in result.fields],
        )

    async def fields(self, ocr_job_id: str, actor: OcrActor, field_type: str | None) -> list[OcrFieldResponse]:
        fields, doc_texts = await self.repository.get_fields(ocr_job_id, actor, field_type)
        doc_text_map = {d.ocr_document_text_id: d for d in doc_texts}
        return [serialize_field(item, doc_text_map) for item in fields]

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> OcrFieldResponse:
        field, doc_texts = await self.repository.update_field(ocr_field_id, request, actor)
        doc_text_map = {d.ocr_document_text_id: d for d in doc_texts}
        return serialize_field(field, doc_text_map)

    async def write_field(
        self, visit_id: int, field_type: str, value: str | None, actor: OcrActor
    ) -> OcrFieldResponse | None:
        """판독이 못 읽은 값을 적어 넣는다. 비우면 지우고 `None` 을 준다."""
        field, doc_texts = await self.repository.write_field(visit_id, field_type, value, actor)
        if field is None:
            return None
        return serialize_field(field, {d.ocr_document_text_id: d for d in doc_texts})

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJobResponse:
        """잘못 올린 문서의 job을 안내 생성에서 제외한다 — 멱등 처리."""
        job = await self.repository.exclude_job(ocr_job_id, actor)
        return serialize_job(job)

    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> FinalizeOcrResponse:
        """확정된 OcrField에서 Prescription·PrescriptionItem을 생성하거나 재확정한다."""
        prescription = await self.repository.finalize_ocr(visit_id, actor)
        return FinalizeOcrResponse(
            prescription_id=prescription.prescription_id,
            prescription_set=prescription.prescription_set,
            items=[
                PrescriptionItemResponse(
                    prescription_item_id=item.prescription_item_id,
                    name=item.name,
                    frequency=item.frequency,
                    duration_days=item.duration_days,
                )
                for item in prescription.items
            ],
        )
