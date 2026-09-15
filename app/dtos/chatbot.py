from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.visits import GuideSectionKey


class ChatbotResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)

    #: 같은 물음을 두 번 보내지 않기 위한 열쇠 — KEY-328. 환자 피드백
    #: (`PatientFeedbackCreateRequest.submission_id`)과 같은 모양이다.
    #:
    #: 오면 **모델을 두 번 부르지 않는다** — `ChatbotSubmissionGuard` 가 그
    #: 열쇠로 이미 답했는지·지금 답하는 중인지를 가른다.
    #:
    #: **없어도 받는다.** 지금 화면은 보내지만 옛 화면·검사·스크립트는 안
    #: 보낸다. 필수로 돌리는 것은 보내는 쪽이 다 갈린 뒤의 일이다 — 그때까지
    #: 열쇠 없는 요청은 **멱등 보장이 없다**(`docs/api/patient.md`).
    submission_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("공백만 입력할 수 없습니다.")
        return stripped


class ChatbotResponse(BaseModel):
    answer: str
    evidence: str
    source: str
    limitation: str
    urgent: bool = False
    fallback: bool = False
    grounded_section: GuideSectionKey | None = None
    response_ref: str | None = None
