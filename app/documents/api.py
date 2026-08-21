from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status

from app.core.api_errors import ContractRoute
from app.core.config import Config
from app.core.storage import LocalFileStorage
from app.dependencies.patient_access import ClinicalActor, require_patient_access
from app.documents.schemas import DocumentUploadResponse
from app.documents.service import DocumentUploadService
from app.models.ocr import OcrDocumentType

_cfg = Config()
_service = DocumentUploadService(
    storage=LocalFileStorage(_cfg.UPLOAD_DIR),
    max_upload_bytes=_cfg.MAX_UPLOAD_SIZE_MB * 1024 * 1024,
)

document_router = APIRouter(prefix="/front-desk", tags=["documents"], route_class=ContractRoute)


def get_document_service() -> DocumentUploadService:
    return _service


@document_router.post(
    "/visits/{visit_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents(
    visit_id: Annotated[int, Path(gt=0)],
    files: Annotated[list[UploadFile], File(description="진료기록 이미지 또는 PDF (JPEG·PNG·PDF)")],
    actor: Annotated[ClinicalActor, Depends(require_patient_access)],
    service: Annotated[DocumentUploadService, Depends(get_document_service)],
    document_type: Annotated[OcrDocumentType | None, Form()] = None,
) -> DocumentUploadResponse:
    # require_patient_access 가 hospital_id None 을 이미 차단한다.
    assert actor.hospital_id is not None
    return await service.upload(
        visit_id=visit_id,
        files=files,
        document_type=document_type,
        hospital_id=actor.hospital_id,
        staff_id=actor.staff_id,
    )
