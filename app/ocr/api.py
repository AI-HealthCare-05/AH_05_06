from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.ocr.schemas import (
    OcrFieldResponse,
    OcrJobByDocumentResponse,
    OcrJobResponse,
    OcrResultResponse,
    StartOcrRequest,
    UpdateOcrFieldRequest,
)
from app.ocr.security import OcrActor, get_ocr_actor
from app.ocr.service import OcrService, TortoiseDocumentOwnershipVerifier, TortoiseOcrRepository

ocr_router = APIRouter(tags=["ocr"])
service = OcrService(TortoiseOcrRepository(TortoiseDocumentOwnershipVerifier()))


def get_ocr_service() -> OcrService:
    return service


@ocr_router.get("/visits/{visit_id}/ocr-jobs", response_model=list[OcrJobByDocumentResponse])
async def get_visit_ocr_jobs(
    visit_id: Annotated[int, Path(gt=0)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> list[OcrJobByDocumentResponse]:
    return await ocr.jobs_for_visit(visit_id, actor)


@ocr_router.get("/visits/{visit_id}/ocr-job", response_model=OcrJobResponse)
async def get_visit_ocr_job(
    visit_id: Annotated[int, Path(gt=0)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrJobResponse:
    return await ocr.job_for_visit(visit_id, actor)


@ocr_router.post(
    "/documents/{document_id}/ocr",
    response_model=OcrJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_ocr(
    document_id: Annotated[int, Path(gt=0)],
    request: StartOcrRequest,
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrJobResponse:
    return await ocr.start(document_id, request.visit_id, request.document_type, actor)


@ocr_router.get("/ocr/jobs/{ocr_job_id}", response_model=OcrJobResponse)
async def get_ocr_status(
    ocr_job_id: Annotated[str, Path(min_length=1, max_length=64)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrJobResponse:
    return await ocr.status(ocr_job_id, actor)


@ocr_router.get("/ocr/jobs/{ocr_job_id}/result", response_model=OcrResultResponse)
async def get_ocr_result(
    ocr_job_id: Annotated[str, Path(min_length=1, max_length=64)],
    response: Response,
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrResultResponse:
    response.headers["Cache-Control"] = "no-store"
    return await ocr.result(ocr_job_id, actor)


@ocr_router.get("/ocr/jobs/{ocr_job_id}/fields", response_model=list[OcrFieldResponse])
async def get_ocr_fields(
    ocr_job_id: Annotated[str, Path(min_length=1, max_length=64)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
    field_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> list[OcrFieldResponse]:
    return await ocr.fields(ocr_job_id, actor, field_type)


@ocr_router.patch("/ocr/fields/{ocr_field_id}", response_model=OcrFieldResponse)
async def update_ocr_field(
    ocr_field_id: Annotated[int, Path(gt=0)],
    request: UpdateOcrFieldRequest,
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrFieldResponse:
    return await ocr.update_field(ocr_field_id, request, actor)
