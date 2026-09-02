from datetime import date, datetime

from pydantic import Field, model_validator

from app.dtos.base import StrictModel
from app.models.ocr import OcrDocumentType, OcrJobStatus


class OcrJobResponse(StrictModel):
    ocr_job_id: str
    status: OcrJobStatus
    progress: int = Field(ge=0, le=100)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None


class OcrCandidateResponse(StrictModel):
    ocr_field_candidate_id: int
    value: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    rank: int = Field(ge=1)
    source_date: date | None = None
    source_line: int | None = None
    document_id: int | None = None
    is_selected: bool


class OcrFieldResponse(StrictModel):
    ocr_field_id: int
    field_type: str
    extracted_value: str | None
    corrected_value: str | None
    value: str | None
    unit: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_low_confidence: bool = False
    version: int = Field(ge=1)
    is_confirmed: bool
    is_pending_report: bool = False
    document_id: int | None = None
    source_line: int | None = None
    modified_by: int | None = None
    modified_at: datetime | None = None
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    candidates: list[OcrCandidateResponse] = Field(default_factory=list)


class OcrDocumentResponse(StrictModel):
    document_id: int
    document_type: OcrDocumentType
    raw_text: str | None
    raw_text_purged_at: datetime | None = None


class OcrResultResponse(StrictModel):
    ocr_result_id: int
    ocr_job_id: str
    model_name: str
    model_version: str | None
    version: int = Field(ge=1)
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    documents: list[OcrDocumentResponse]
    fields: list[OcrFieldResponse]


class OcrJobByDocumentResponse(StrictModel):
    document_id: int
    document_type: OcrDocumentType
    ocr_job_id: str
    status: OcrJobStatus
    progress: int = Field(ge=0, le=100)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None


class UpdateOcrFieldRequest(StrictModel):
    base_version: int = Field(ge=1)
    corrected_value: str | None = Field(default=None, max_length=10000)
    candidate_id: int | None = Field(default=None, gt=0)
    confirm: bool = False

    @model_validator(mode="after")
    def require_one_value_source(self) -> "UpdateOcrFieldRequest":
        if self.corrected_value is not None and self.candidate_id is not None:
            raise ValueError("corrected_value와 candidate_id는 함께 보낼 수 없습니다")
        if not self.confirm and self.corrected_value is None and self.candidate_id is None:
            raise ValueError("수정값 또는 후보를 선택해 주세요")
        if self.corrected_value is not None and not self.corrected_value.strip():
            raise ValueError("corrected_value는 공백일 수 없습니다")
        return self


class WriteOcrFieldRequest(StrictModel):
    """판독이 못 읽은 값을 사람이 적어 넣는다 — 와이어프레임 S1-7 「직접 입력」.

    **고치기(PATCH)와 다른 길이다.** 저쪽은 이미 있는 줄의 값을 바꾸는 것이고,
    이쪽은 **줄 자체가 없는** 것을 만든다. 판독이 못 찾은 항목은 레코드로 남지
    않아서, 화면이 값을 적어도 보낼 곳이 없었다 — 「저장 안 됨」이라 적어 두고
    새로고침하면 사라졌다.

    `value` 가 비면 **그 줄을 지운다**. 잘못 적은 것을 「빈 값으로 적었다」로
    남겨 두면, 안 적은 것과 구별이 안 된다.
    """

    value: str | None = Field(default=None, max_length=10000)
