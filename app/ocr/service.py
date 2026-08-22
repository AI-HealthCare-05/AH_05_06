from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from fastapi import status
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.models.documents import MedicalDocument
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
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import (
    OcrCandidateResponse,
    OcrDocumentResponse,
    OcrFieldResponse,
    OcrJobResponse,
    OcrResultResponse,
    UpdateOcrFieldRequest,
)
from app.ocr.security import OcrActor


class OcrRepository(Protocol):
    async def create_job(
        self, document_id: int, visit_id: int, document_type: OcrDocumentType, actor: OcrActor
    ) -> OcrJob: ...

    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob: ...

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None: ...

    async def get_result(self, ocr_job_id: str, actor: OcrActor) -> OcrResult: ...

    async def get_fields(
        self, ocr_job_id: str, actor: OcrActor, field_type: str | None
    ) -> tuple[Sequence[OcrField], Sequence[OcrDocumentText]]: ...

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> tuple[OcrField, Sequence[OcrDocumentText]]: ...


class DocumentOwnershipVerifier(Protocol):
    async def assert_owned(
        self,
        document_id: int,
        visit_id: int,
        hospital_id: int,
        connection: BaseDBAsyncClient,
    ) -> None: ...


def _not_found() -> OcrApiError:
    return OcrApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "OCR 리소스를 찾을 수 없습니다.")


class FailClosedDocumentOwnershipVerifier:
    """Block OCR creation until the authoritative upload model is connected."""

    async def assert_owned(
        self,
        document_id: int,
        visit_id: int,
        hospital_id: int,
        connection: BaseDBAsyncClient,
    ) -> None:
        raise _not_found()


class TortoiseDocumentOwnershipVerifier:
    async def assert_owned(
        self,
        document_id: int,
        visit_id: int,
        hospital_id: int,
        connection: BaseDBAsyncClient,
    ) -> None:
        exists = await (
            MedicalDocument.filter(
                document_id=document_id,
                visit_id=visit_id,
                hospital_id=hospital_id,
            )
            .using_db(connection)
            .exists()
        )
        if not exists:
            raise _not_found()


class TortoiseOcrRepository:
    def __init__(self, document_ownership: DocumentOwnershipVerifier | None = None) -> None:
        self.document_ownership = document_ownership or FailClosedDocumentOwnershipVerifier()

    async def create_job(
        self, document_id: int, visit_id: int, document_type: OcrDocumentType, actor: OcrActor
    ) -> OcrJob:
        async with in_transaction() as connection:
            # Locking the visit serializes starts for documents owned by that visit.
            # The authoritative document verifier must validate the same visit/hospital.
            visit = (
                await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if visit is None:
                raise _not_found()
            await self.document_ownership.assert_owned(
                document_id,
                visit_id,
                actor.hospital_id,
                connection,
            )
            active = await (
                OcrJobDocument.filter(
                    document_id=document_id,
                    ocr_job__hospital_id=actor.hospital_id,
                    ocr_job__status=OcrJobStatus.PROCESSING,
                )
                .using_db(connection)
                .select_for_update()
                .exists()
            )
            if active:
                raise OcrApiError(
                    status.HTTP_409_CONFLICT,
                    "OCR_ALREADY_PROCESSING",
                    "이미 처리 중인 문서입니다.",
                )
            job = await OcrJob.create(
                ocr_job_id=f"ocr_{uuid4().hex}",
                hospital_id=actor.hospital_id,
                visit=visit,
                requested_by=actor.staff_id,
                using_db=connection,
            )
            await OcrJobDocument.create(
                ocr_job=job,
                document_id=document_id,
                document_type=document_type,
                using_db=connection,
            )
        return job

    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob:
        job = await OcrJob.filter(ocr_job_id=ocr_job_id, hospital_id=actor.hospital_id).first()
        if job is None:
            raise _not_found()
        return job

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None:
        # 진행 중인 작업이 있으면 그것이 현재 작업이다.
        # 없으면 같은 진료의 가장 최근 작업을 반환한다.
        job = await OcrJob.filter(
            visit_id=visit_id,
            hospital_id=actor.hospital_id,
            status=OcrJobStatus.PROCESSING,
        ).first()
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


def serialize_job(job: OcrJob) -> OcrJobResponse:
    return OcrJobResponse(
        ocr_job_id=job.ocr_job_id,
        status=job.status,
        progress=job.progress,
        started_at=job.started_at,
        completed_at=job.completed_at,
        failure_code=job.failure_code,
    )


LOW_CONFIDENCE_THRESHOLD = 0.75


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

    async def start(
        self, document_id: int, visit_id: int, document_type: OcrDocumentType, actor: OcrActor
    ) -> OcrJobResponse:
        return serialize_job(await self.repository.create_job(document_id, visit_id, document_type, actor))

    async def job_for_visit(self, visit_id: int, actor: OcrActor) -> OcrJobResponse:
        job = await self.repository.get_latest_job_by_visit(visit_id, actor)
        if job is None:
            raise _not_found()
        return serialize_job(job)

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
