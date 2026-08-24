"""D+7 복약·통증 응답 계약 — KEY-151 최소 범위."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.dtos.base import StrictModel
from app.models.visits import CheckInMedication

PainType = Literal["menstrual", "intercourse", "defecation", "chronic_pelvic"]


class CheckInPainRequest(StrictModel):
    had: bool
    score: int | None = Field(default=None, ge=0, le=10)
    types: list[PainType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pain_details(self) -> "CheckInPainRequest":
        if self.had and self.score is None:
            raise ValueError("통증이 있으면 0~10 점수를 입력해야 합니다.")
        if not self.had and (self.score is not None or self.types):
            raise ValueError("통증이 없으면 점수와 유형을 입력할 수 없습니다.")
        if len(self.types) != len(set(self.types)):
            raise ValueError("통증 유형은 중복할 수 없습니다.")
        return self


class CheckInCreateRequest(StrictModel):
    medication: CheckInMedication
    pain: CheckInPainRequest | None = None


class CheckInAnswerContent(StrictModel):
    lead: str
    body: str | None = None
    ask: bool = False
    notify: bool = False


class CheckInPainTypeResponse(StrictModel):
    key: PainType
    label: str


class CheckInReadResponse(StrictModel):
    round_label: Literal["복약 7일째 · 첫 확인"] = "복약 7일째 · 첫 확인"
    drug_name: None = None
    answers: dict[CheckInMedication, CheckInAnswerContent | None]
    pain_types: list[CheckInPainTypeResponse]
    next_checkin: None = None
    next_visit: None = None
    answered: bool
    demo_only: Literal[True] = True


class CheckInPainResponse(StrictModel):
    had: bool
    score: int | None
    types: list[PainType]


class CheckInSaveResponse(StrictModel):
    check_in_id: int
    saved: Literal[True] = True
    medication: CheckInMedication
    pain: CheckInPainResponse | None
    guide_url: None = None
    next_checkin: None = None
    next_visit: None = None
    demo_only: Literal[True] = True


class HospitalCheckInResponse(StrictModel):
    check_in_id: int
    visit_id: int
    medication: CheckInMedication
    pain: CheckInPainResponse | None
    submitted_at: datetime
    demo_only: Literal[True] = True
