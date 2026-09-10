from app.dtos.base import StrictModel
from app.models.ocr import OcrJobStatus


class DocumentUploadResponse(StrictModel):
    document_ids: list[int]
    ocr_job_ids: list[str]
    status: OcrJobStatus
