from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import FileResponse

from app.models.documents import MedicalDocument
from app.ocr.schemas import (
    FinalizeOcrResponse,
    OcrFieldResponse,
    OcrJobByDocumentResponse,
    OcrJobResponse,
    OcrResultResponse,
    UpdateOcrFieldRequest,
    WriteOcrFieldRequest,
)
from app.ocr.security import OcrActor, get_ocr_actor
from app.ocr.service import (
    OcrService,
    TortoiseOcrRepository,
)

ocr_router = APIRouter(tags=["ocr"])
service = OcrService(TortoiseOcrRepository())


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


@ocr_router.post("/visits/{visit_id}/ocr-finalize", response_model=FinalizeOcrResponse)
async def finalize_ocr(
    visit_id: Annotated[int, Path(gt=0)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> FinalizeOcrResponse:
    """확정된 OCR 필드에서 처방 정보를 구조화 저장한다.

    모든 OCR 필드가 확정된 상태여야 한다. 이미 처방이 있으면 재확정으로 덮어쓴다.
    """
    return await ocr.finalize_ocr(visit_id, actor)


@ocr_router.put("/visits/{visit_id}/ocr-fields/{field_type}", response_model=OcrFieldResponse | None)
async def write_ocr_field(
    visit_id: Annotated[int, Path(gt=0)],
    field_type: Annotated[str, Path(min_length=1, max_length=64)],
    request: WriteOcrFieldRequest,
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrFieldResponse | None:
    """판독이 못 읽은 값을 적어 넣는다 — 와이어프레임 S1-7 「직접 입력」.

    **고치기(PATCH)와 다른 길이다.** 저쪽은 있는 줄의 값을 바꾸고, 이쪽은 줄
    자체가 없는 것을 만든다. 그래서 항목 이름(`field_type`)으로 짚는다 — 줄이
    없으면 가리킬 번호도 없기 때문이다.

    비우면 그 줄을 지우고 `null` 을 준다.
    """
    return await ocr.write_field(visit_id, field_type, request.value, actor)


@ocr_router.get("/ocr/documents/{document_id}/image")
async def get_document_image(
    document_id: Annotated[int, Path(gt=0)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
) -> FileResponse:
    """업로드된 원본 이미지를 반환한다 — 판독 확인 화면의 문서 미리보기용.

    - 병원 범위 검증: document.hospital_id == actor.hospital_id
    - 원본이 삭제된 경우(file_path 없음 또는 파일 부재) 404 반환
    """
    from app.ocr.errors import OcrApiError

    doc = await MedicalDocument.filter(
        document_id=document_id,
        hospital_id=actor.hospital_id,
    ).first()
    if doc is None:
        raise OcrApiError(404, "NOT_FOUND", "문서를 찾을 수 없습니다.")

    file = FilePath(doc.file_path)
    if not file.exists():
        raise OcrApiError(404, "FILE_PURGED", "원본 이미지가 이미 삭제됐습니다.")

    return FileResponse(
        path=str(file),
        media_type=doc.mime_type,
        filename=file.name,
        headers={"Cache-Control": "private, max-age=300"},
    )


@ocr_router.patch("/ocr/jobs/{ocr_job_id}/exclude", response_model=OcrJobResponse)
async def exclude_ocr_job(
    ocr_job_id: Annotated[str, Path(min_length=1, max_length=64)],
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrJobResponse:
    """잘못 올린 문서의 job을 안내 생성 게이트에서 제외한다.

    제외된 job은 안내 생성 시 최신 job 판정에서 건너뛴다.
    같은 job을 다시 호출해도 멱등 처리된다.
    """
    return await ocr.exclude_job(ocr_job_id, actor)


@ocr_router.patch("/ocr/fields/{ocr_field_id}", response_model=OcrFieldResponse)
async def update_ocr_field(
    ocr_field_id: Annotated[int, Path(gt=0)],
    request: UpdateOcrFieldRequest,
    actor: Annotated[OcrActor, Depends(get_ocr_actor)],
    ocr: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrFieldResponse:
    return await ocr.update_field(ocr_field_id, request, actor)
