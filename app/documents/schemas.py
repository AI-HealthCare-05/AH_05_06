from pydantic import BaseModel, ConfigDict

from app.models.ocr import OcrJobStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentUploadResponse(StrictModel):
    document_ids: list[int]
    ocr_job_id: str
    status: OcrJobStatus
