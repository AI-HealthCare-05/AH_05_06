"""Patient feedback request and response contracts for KEY-239."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.dtos.base import StrictModel
from app.models.feedback import PatientFeedbackCategory, PatientFeedbackSourceScreen, PatientFeedbackTarget


class PatientFeedbackCreateRequest(StrictModel):
    submission_id: UUID
    target: PatientFeedbackTarget
    source_screen: PatientFeedbackSourceScreen
    category: PatientFeedbackCategory
    response_ref: str | None = Field(default=None, min_length=16, max_length=100)
    section_key: str | None = Field(default=None, min_length=1, max_length=50)
    content_key: str | None = Field(default=None, min_length=1, max_length=100)
    detected_tab: str | None = Field(default=None, min_length=1, max_length=100)
    details: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_target_reference(self) -> "PatientFeedbackCreateRequest":
        if self.target is PatientFeedbackTarget.CHATBOT_RESPONSE:
            if self.response_ref is None:
                raise ValueError("챗봇 응답 평가에는 response_ref가 필요합니다.")
            if self.section_key is not None or self.content_key is not None:
                raise ValueError("챗봇 응답 평가에는 안내 섹션 식별자를 함께 보낼 수 없습니다.")
        if self.target is PatientFeedbackTarget.CHATBOT_RESPONSE:
            if self.source_screen is not PatientFeedbackSourceScreen.P6:
                raise ValueError("챗봇 응답 평가는 P6 화면에서만 제출할 수 있습니다.")
        else:
            if self.section_key is None or self.content_key is None:
                raise ValueError("안내 피드백에는 section_key와 content_key가 필요합니다.")
            if self.response_ref is not None:
                raise ValueError("안내 피드백에는 response_ref를 함께 보낼 수 없습니다.")
            if self.source_screen is not PatientFeedbackSourceScreen.P9:
                raise ValueError("안내 오류 신고는 P9 화면에서만 제출할 수 있습니다.")

        if self.details is not None:
            self.details = self.details.strip() or None
        return self


class PatientFeedbackCreateResponse(StrictModel):
    feedback_id: int
    saved: bool = True


class AdminPatientFeedbackListItem(StrictModel):
    feedback_id: int
    visit_id: int
    target: PatientFeedbackTarget
    source_screen: PatientFeedbackSourceScreen
    category: PatientFeedbackCategory
    has_details: bool
    created_at: datetime


class AdminPatientFeedbackListResponse(StrictModel):
    items: list[AdminPatientFeedbackListItem]
    page: int
    page_size: int
    total: int


class AdminPatientFeedbackDetailResponse(AdminPatientFeedbackListItem):
    section_key: str | None
    content_key: str | None
    detected_tab: str | None
    details: str | None
